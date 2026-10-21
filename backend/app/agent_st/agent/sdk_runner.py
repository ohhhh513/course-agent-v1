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
from .chat_skills import bind_skill
from .loader import bind_course_identity, build_system_prompt, load_flow, load_persona
from .registry import execute, openai_tools
from .store import AgentStore
from ..net import async_client

Event = dict

# 注册工具（与 runtime 保持一致： import 即注册，逐个显式列出）
from .tools import (admin_ops, analytics, bank, batch_draft, draft, plan, rag,  # noqa: E402,F401
                    teacher_analytics, topic, validate, ui_actions)

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
    from .runtime import _log_tool, draft_events_for_tool  # 函数内导入，避免循环引用

    async def _invoke(_run_ctx, args_json: str) -> str:
        from . import cancel

        try:
            args = json.loads(args_json or "{}")
        except json.JSONDecodeError:
            args = {}
        if not isinstance(args, dict):
            args = {}
        cancel_key = str((ctx.extra or {}).get("cancelKey") or "")
        if cancel_key and cancel.is_requested(cancel_key):
            return json.dumps({"ok": False, "cancelled": True}, ensure_ascii=False)
        emit({"type": "tool_start", "name": tool_name, "args": args})
        # registry.execute 是同步的（DB / 向量检索），丢线程池执行
        result = await asyncio.to_thread(execute, tool_name, args, ctx)
        saved_batch = (
            tool_name == "save_question_batch"
            and isinstance(result, dict)
            and result.get("ok") is True
        )
        if cancel_key and cancel.is_requested(cancel_key) and not saved_batch:
            return json.dumps({"ok": False, "cancelled": True}, ensure_ascii=False)
        _log_tool(ctx, tool_name, args, result)
        preview = result if not isinstance(result, list) else result[:4]
        emit({"type": "tool_end", "name": tool_name, "ok": True, "preview": preview})
        for event in draft_events_for_tool(tool_name, result, ctx):
            emit(event)
        if cancel_key and cancel.is_requested(cancel_key) and not saved_batch:
            return json.dumps({"ok": False, "cancelled": True}, ensure_ascii=False)
        return json.dumps(result, ensure_ascii=False)

    return _invoke


def _build_tools(flow_id: str, whitelist: list[str], ctx: ToolContext,
                 emit: Callable[[Event], None], role: str = ""):
    """按 flow 白名单把注册表工具适配成 SDK FunctionTool（schema 原样复用）。

    role 非空时只把该角色可用的工具交给模型——模型看不到就调不到；
    执行前 registry.execute 还会再校验一次（双层）。
    """
    tools = []
    for spec in openai_tools(flow_id, whitelist, role=role):
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


def _map_raw_event(data: Any, emit: Callable[[Event], None], text_parts: list[str] | None = None) -> None:
    """把 SDK 透出的原始事件映射成我们的事件（只关心文本/推理增量）。"""
    kind = getattr(data, "type", "") or ""
    if kind == "response.output_text.delta":
        delta = getattr(data, "delta", "")
        if delta:
            if text_parts is not None:
                text_parts.append(delta)
            emit({"type": "text", "delta": delta})
    elif kind in ("response.reasoning_text.delta", "response.reasoning_summary_text.delta"):
        delta = getattr(data, "delta", "")
        if delta:
            emit({"type": "think", "delta": delta})


async def _run_async(message: str, flow_id: str, session_id: str, context: dict | None,
                     store: AgentStore, user_id: str, cancel_key: str,
                     emit: Callable[[Event], None]) -> None:
    """真正的执行体（异步）：跑一轮 SDK Agent，把事件交给 emit。"""
    from ..rag.ingest import ensure_bank_indexed
    from . import cancel
    from .runtime import (_citations_from_turn, _explain_out_of_scope, attachment_ground_text,
                          attachment_image_parts,
                          action_events, persist_side_effects)

    settings = get_settings()
    flow = load_flow(flow_id)
    persona = load_persona(str(flow.get("persona") or "course_tutor"))
    ensure_bank_indexed(course_id=store.course_id or None)

    extra = dict(context or {})
    extra["message"] = message
    if store.course_id:
        extra.setdefault("courseId", store.course_id)
    skill, skill_tools, skill_err = bind_skill(flow, extra)
    if skill_err:
        emit({"type": "error", "message": skill_err})
        emit({"type": "done"})
        return
    ctx = ToolContext(store=store, flow_id=flow_id, extra=extra,
                      user_id=user_id or store.user_id)

    history = store.history(session_id, limit=12)
    from ..rag import structure as _structure

    catalog = _structure.kp_catalog_text(store.course_id) if store.course_id else ""
    # 与 legacy 路径一致：附件正文与账号解析结果都不进 system 提示词
    # （附件正文只拼进本轮用户消息；账号表由 preview_account_import 工具按需读取）
    _atts = [a for a in (extra.get("attachments") or []) if isinstance(a, dict)]
    instructions = build_system_prompt(
        persona, flow,
        bind_course_identity(
            {k: v for k, v in extra.items() if k not in ("attachments", "account_import")},
            store.course_id,
        ),
        course_catalog=catalog,
        skill=skill)

    role = str(extra.get("role") or "").strip()
    tools = _build_tools(flow_id, skill_tools, ctx, emit, role=role)
    max_turns = int(flow.get("max_steps") or persona.get("max_steps") or settings.max_steps)

    model = OpenAIChatCompletionsModel(
        model=settings.llm_model,
        openai_client=async_client(settings.llm_base_url, settings.llm_api_key),
    )
    agent = Agent(name=persona.get("name") or "course_tutor", instructions=instructions,
                  model=model, tools=tools)

    user_content = message + attachment_ground_text(_atts)
    image_parts = attachment_image_parts(_atts, sdk_input=True)
    if image_parts:
        user_content = [{"type": "input_text", "text": user_content}, *image_parts]
    run_input = list(history) + [{"role": "user", "content": user_content}]
    result = Runner.run_streamed(agent, input=run_input, context=ctx, max_turns=max_turns)

    text_parts: list[str] = []
    event_stream = result.stream_events().__aiter__()
    stopped = False
    while True:
        if cancel.is_requested(cancel_key):
            stopped = True
            break
        next_event = asyncio.create_task(event_stream.__anext__())
        while True:
            completed, _ = await asyncio.wait({next_event}, timeout=0.1)
            if completed:
                try:
                    ev = next_event.result()
                except StopAsyncIteration:
                    ev = None
                break
            if cancel.is_requested(cancel_key):
                stopped = True
                next_event.cancel()
                await asyncio.gather(next_event, return_exceptions=True)
                ev = None
                break
        if stopped or ev is None:
            break
        data = getattr(ev, "data", None)
        if data is not None:
            _map_raw_event(data, emit, text_parts)

    if stopped:
        cancel_runner = getattr(result, "cancel", None)
        if callable(cancel_runner):
            try:
                cancelled = cancel_runner()
                if asyncio.iscoroutine(cancelled):
                    await cancelled
            except (Exception, asyncio.CancelledError):
                pass
        close_stream = getattr(event_stream, "aclose", None)
        if callable(close_stream):
            try:
                await close_stream()
            except (Exception, asyncio.CancelledError):
                pass
        partial = "".join(text_parts).strip()
        if partial:
            store.add_message(session_id, "assistant", partial)
        emit({"type": "citations", "items": []})
        emit({"type": "done", "drafts": ctx.turn.get("drafts") or [], "out_of_scope": False})
        return

    final_text = getattr(result, "final_output", "") or ""
    if not isinstance(final_text, str):
        final_text = str(final_text)
    if not final_text:
        final_text = "（模型没有返回文本）"
        emit({"type": "text", "delta": final_text})

    emit({"type": "citations", "items": _citations_from_turn(ctx.turn)})
    out_of_scope = _explain_out_of_scope(ctx, message) if flow_id == "explain" else False
    ctx.turn["out_of_scope"] = out_of_scope        # 落库前写入，persist_side_effects 从 ctx.turn 取
    store.add_message(session_id, "assistant", final_text)
    persist_side_effects(store, session_id, ctx)
    # 界面动作：只读建议 + 写操作的待批准卡片（P2c），与 legacy 路径一致地透出
    for ev in action_events(ctx):
        emit(ev)
    emit({
        "type": "done",
        "drafts": ctx.turn.get("drafts") or [],
        "out_of_scope": out_of_scope,
    })


def run_turn_sdk(message: str, flow_id: str | None = None, session_id: str | None = None,
                 context: dict | None = None, store: AgentStore | None = None,
                 user_id: str = "", course_id: str = "") -> Iterator[Event]:
    """与 runtime.run_turn 同签名的同步生成器（内部用线程 + 事件循环驱动 async SDK）。"""
    flow_id = flow_id or load_persona().get("default_flow", "explain")
    if flow_id in {"qa", "tutoring"}:
        flow_id = "explain"

    # 与 legacy 路径同序的校验：先确认任务流存在、再确认角色可用，之后才建会话。
    try:
        flow = load_flow(flow_id)
    except FileNotFoundError:
        yield {"type": "error", "message": f"未知任务流 {flow_id}"}
        yield {"type": "done"}
        return
    persona = load_persona(str(flow.get("persona") or "course_tutor"))
    role = str((context or {}).get("role") or "").strip()
    allowed_roles = flow.get("roles") or persona.get("roles") or []
    if role and allowed_roles and role not in allowed_roles:
        yield {"type": "error",
               "message": f"当前角色（{role}）不能使用「{flow.get('name') or flow_id}」"}
        yield {"type": "done"}
        return
    bound_context = dict(context or {})
    _, _, skill_err = bind_skill(flow, bound_context)
    if skill_err:
        yield {"type": "error", "message": skill_err}
        yield {"type": "done"}
        return

    store = store or AgentStore(user_id=user_id, course_id=course_id)
    if user_id and not store.user_id:
        store.user_id = user_id
    if course_id and not store.course_id:
        store.course_id = course_id
    session_id = store.ensure_session(session_id, flow_id)
    from . import cancel

    cancel_key = str((context or {}).get("cancelKey") or session_id)
    if cancel_key == session_id:
        cancel.clear(session_id)
    yield {"type": "session", "session_id": session_id, "flow_id": flow_id}
    # 附件随消息落库的标记（与 legacy 路径一致）：历史会话据此回显附件名
    from .runtime import attachment_log_entries

    _atts = [a for a in (bound_context.get("attachments") or []) if isinstance(a, dict)]
    store.add_message(session_id, "user", message, tool_log=attachment_log_entries(_atts))

    out: "queue.Queue[Event | None]" = queue.Queue()

    def emit(ev: Event) -> None:
        out.put(ev)

    def worker() -> None:
        try:
            asyncio.run(_run_async(message, flow_id, session_id, bound_context, store,
                                   user_id, cancel_key, emit))
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
