"""基于 OpenAI Agents SDK 的对话运行层（P0）。

与 `runtime.run_turn` **同契约**：同样的入参，产出同样的事件 dict 流
（session / text / think / tool_start / tool_end / draft / citations / error / done），
因此 `/ai/chat/stream` 与前端无需任何改动。

设计要点
--------
- **工具不重写**：直接复用 `registry` 里的 JSON Schema 与 `execute()`，
  只是把它们适配成 SDK 的 `FunctionTool`（按 flow 白名单过滤，权限规则不变）；
- **同步工具进线程池**：`asyncio.to_thread(execute, ...)`，避免阻塞事件循环
  导致 SSE 卡住不吐字；
- **逐 token 流式保留**：SDK 对 OpenAI 兼容端点走 chat completions，
  原始的 `ResponseTextDeltaEvent` 会包在 `RawResponsesStreamEvent` 里透出，
  这里把它们映射回 `text` / `think` 事件（与旧实现一致的体验）；
- **轨迹不外发**：`set_tracing_disabled(True)`，不依赖任何 OpenAI key
  （以后要可回放，再挂自己的 trace processor）。
"""
from __future__ import annotations

import asyncio
import json
import queue
import threading
from collections.abc import Iterator
from typing import Any, Callable

from . import llm
from .config import get_settings
from .context import ToolContext
from .loader import build_system_prompt, load_flow, load_persona
from .registry import execute, openai_tools
from .store import AgentStore
from ..net import async_client

Event = dict

# 注册工具（与 runtime 保持一致：import 即注册）
from .tools import bank, draft, plan, rag, topic, validate  # noqa: E402,F401

_SDK_ERROR: str = ""
try:  # 依赖缺失时不炸 import，交给 available() 判断
    from agents import (Agent, FunctionTool, OpenAIChatCompletionsModel,  # noqa: E402
                        Runner, set_tracing_disabled)

    set_tracing_disabled(True)
except Exception as exc:  # pragma: no cover - 环境未安装 openai-agents
    _SDK_ERROR = str(exc)


def available() -> bool:
    """SDK 路径是否可用：装了 openai-agents + 配了可用的模型密钥。"""
    return not _SDK_ERROR and llm.chat_available()


def _make_invoker(tool_name: str, ctx: ToolContext, emit: Callable[[Event], None]):
    """把 registry 里的工具包成 SDK 的 on_invoke_tool(ctx, json_args) -> str。"""

    async def _invoke(_run_ctx, args_json: str) -> str:
        try:
            args = json.loads(args_json or "{}")
        except json.JSONDecodeError:
            args = {}
        if not isinstance(args, dict):
            args = {}
        emit({"type": "tool_start", "name": tool_name, "args": args})
        # registry.execute 是同步的（DB / 向量检索），丢线程池执行
        result = await asyncio.to_thread(execute, tool_name, args, ctx)
        ctx.tool_log.append({
            "kind": "tool", "name": tool_name, "args": args,
            "ok": not (isinstance(result, dict) and result.get("error")),
        })
        preview = result if not isinstance(result, list) else result[:4]
        emit({"type": "tool_end", "name": tool_name, "ok": True, "preview": preview})
        # 与旧实现一致：每保存一道题就推一个 draft 事件（教师端流式预览用）
        if tool_name == "save_question_draft" and isinstance(result, dict) and result.get("draft_id"):
            emit({"type": "draft", **result})
        return json.dumps(result, ensure_ascii=False)

    return _invoke


def _build_tools(flow_id: str, whitelist: list[str], ctx: ToolContext,
                 emit: Callable[[Event], None]):
    """按 flow 白名单把注册表工具适配成 SDK FunctionTool（schema 原样复用）。"""
    tools = []
    for spec in openai_tools(flow_id, whitelist):
        fn = spec.get("function") or {}
        name = fn.get("name") or ""
        if not name:
            continue
        tools.append(FunctionTool(
            name=name,
            description=fn.get("description") or "",
            params_json_schema=fn.get("parameters") or {"type": "object", "properties": {}},
            on_invoke_tool=_make_invoker(name, ctx, emit),
            strict_json_schema=False,        # 注册表里的 schema 不是 strict 模式
        ))
    return tools


def _map_raw_event(data: Any, emit: Callable[[Event], None]) -> None:
    """把 SDK 透出的原始事件映射成我们的事件（只关心文本/推理增量）。"""
    kind = getattr(data, "type", "") or ""
    if kind == "response.output_text.delta":
        delta = getattr(data, "delta", "")
        if delta:
            emit({"type": "text", "delta": delta})
    elif kind in ("response.reasoning_text.delta", "response.reasoning_summary_text.delta"):
        delta = getattr(data, "delta", "")
        if delta:
            emit({"type": "think", "delta": delta})


async def _run_async(message: str, flow_id: str, session_id: str, context: dict | None,
                     store: AgentStore, user_id: str, emit: Callable[[Event], None]) -> None:
    """真正的执行体（异步）：跑一轮 SDK Agent，把事件交给 emit。"""
    from ..rag.ingest import ensure_bank_indexed
    from .runtime import _citations_from_turn, _explain_out_of_scope, _first_draft_id

    settings = get_settings()
    persona = load_persona()
    flow = load_flow(flow_id)
    ensure_bank_indexed(course_id=store.course_id or None)

    extra = dict(context or {})
    extra["message"] = message
    if store.course_id:
        extra.setdefault("courseId", store.course_id)
    ctx = ToolContext(store=store, flow_id=flow_id, extra=extra,
                      user_id=user_id or store.user_id)

    history = store.history(session_id, limit=12)
    from ..rag import structure as _structure

    catalog = _structure.kp_catalog_text(store.course_id) if store.course_id else ""
    instructions = build_system_prompt(persona, flow, extra, course_catalog=catalog)

    whitelist = flow.get("tools") or persona.get("tools") or []
    tools = _build_tools(flow_id, whitelist, ctx, emit)
    max_turns = int(flow.get("max_steps") or persona.get("max_steps") or settings.max_steps)

    model = OpenAIChatCompletionsModel(
        model=settings.llm_model,
        openai_client=async_client(settings.llm_base_url, settings.llm_api_key),
    )
    agent = Agent(name=persona.get("name") or "course_tutor", instructions=instructions,
                  model=model, tools=tools)

    run_input = list(history) + [{"role": "user", "content": message}]
    result = Runner.run_streamed(agent, input=run_input, context=ctx, max_turns=max_turns)

    async for ev in result.stream_events():
        data = getattr(ev, "data", None)
        if data is not None:
            _map_raw_event(data, emit)

    final_text = getattr(result, "final_output", "") or ""
    if not isinstance(final_text, str):
        final_text = str(final_text)
    if not final_text:
        final_text = "（模型没有返回文本）"
        emit({"type": "text", "delta": final_text})

    emit({"type": "citations", "items": _citations_from_turn(ctx.turn)})
    store.add_message(session_id, "assistant", final_text)
    if ctx.tool_log:
        store.set_last_tool_log(session_id, ctx.tool_log, draft_id=_first_draft_id(ctx))
    emit({
        "type": "done",
        "drafts": ctx.turn.get("drafts") or [],
        "out_of_scope": _explain_out_of_scope(ctx, message) if flow_id == "explain" else False,
    })


def run_turn_sdk(message: str, flow_id: str | None = None, session_id: str | None = None,
                 context: dict | None = None, store: AgentStore | None = None,
                 user_id: str = "", course_id: str = "") -> Iterator[Event]:
    """与 runtime.run_turn 同签名的同步生成器（内部用线程 + 事件循环驱动 async SDK）。"""
    persona = load_persona()
    flow_id = flow_id or persona.get("default_flow", "explain")
    if flow_id in {"qa", "tutoring"}:
        flow_id = "explain"

    store = store or AgentStore(user_id=user_id, course_id=course_id)
    if user_id and not store.user_id:
        store.user_id = user_id
    if course_id and not store.course_id:
        store.course_id = course_id
    session_id = store.ensure_session(session_id, flow_id)
    yield {"type": "session", "session_id": session_id, "flow_id": flow_id}
    store.add_message(session_id, "user", message)

    out: "queue.Queue[Event | None]" = queue.Queue()

    def emit(ev: Event) -> None:
        out.put(ev)

    def worker() -> None:
        try:
            asyncio.run(_run_async(message, flow_id, session_id, context, store, user_id, emit))
        except Exception as exc:  # noqa: BLE001 - 任何异常都要变成可读事件
            emit({"type": "error", "message": f"模型调用失败：{exc}"})
            emit({"type": "done", "drafts": [], "out_of_scope": False})
        finally:
            out.put(None)

    threading.Thread(target=worker, daemon=True).start()
    while True:
        ev = out.get()
        if ev is None:
            return
        yield ev
