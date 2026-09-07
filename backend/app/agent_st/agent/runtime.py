from __future__ import annotations

import json
import queue
import threading
from collections.abc import Iterator

from app.agent_st.agent import llm
from app.agent_st.agent.config import get_settings
from app.agent_st.agent.context import ToolContext
from app.agent_st.agent.loader import build_system_prompt, load_flow, load_persona
from app.agent_st.agent.registry import execute, openai_tools
from app.agent_st.agent.store import AgentStore, allocate_question_id
from app.agent_st.rag.bank import get_question, search_similar
from app.agent_st.rag.ingest import ensure_bank_indexed
from app.agent_st.rag.topic import looks_like_course_question
from app.agent_st.rag.validate import validate_question

# 注册工具
from app.agent_st.agent.tools import bank, draft, plan, rag, topic, validate  # noqa: F401

Event = dict  # run_turn 产出的事件统一为 dict：{"type": ...}


def _citations_from_turn(turn: dict) -> list[dict]:
    hits = turn.get("citations") or (turn.get("retrieval") or {}).get("hits") or []
    out = []
    for hit in hits:
        out.append(
            {
                "chunk_id": hit.get("chunk_id"),
                "section": hit.get("section"),
                "source_type": hit.get("source_type"),
                "source_id": hit.get("source_id"),
                "question_id": hit.get("question_id"),
                "snippet": hit.get("text"),
                "score": hit.get("score"),
            }
        )
    return out


def _run_tool(name: str, args: dict, ctx: ToolContext) -> tuple[list[Event], object]:
    events: list[Event] = [
        {"type": "tool_start", "name": name, "args": args},
    ]
    result = execute(name, args, ctx)
    ctx.tool_log.append(
        {"name": name, "args": args, "ok": not (isinstance(result, dict) and result.get("error"))}
    )
    events.append(
        {"type": "tool_end", "name": name, "ok": True,
         "preview": result if not isinstance(result, list) else result[:4]}
    )
    return events, result


def _demo_explain(message: str, ctx: ToolContext) -> str:
    retrieval = ctx.turn.get("retrieval") or {}
    hits = retrieval.get("hits") or []
    topic = ctx.turn.get("topic") or {}
    lines = [
        "【演示模式，未配置 LLM_API_KEY】",
        "",
        f"结论：该问题对应 {topic.get('course_title') or '本课'} {topic.get('section') or ''}。",
        "",
    ]
    if retrieval.get("empty") or not hits:
        lines.append("未检索到课程原文。")
        lines.append("【补充】以下内容基于课程常识，并非教材或题库原文，请以课堂材料为准。")
        lines.append("请补充章节、题号或换一种问法，以便引用原文。")
        return "\n".join(lines)
    lines.insert(1, "以下讲解根据检索片段整理。")
    for hit in hits[:3]:
        qid = hit.get("question_id")
        cite = f"[题号 {qid}]" if qid else f"[小节 {hit.get('section')}]"
        lines.append(f"依据：{hit.get('text', '')[:220]} {cite}")
        lines.append("")
    lines.append("易错点：请以引用片段为准；若需课外说明请看【补充】并自行核对教材。")
    return "\n".join(lines)


def _demo_generate(message: str, ctx: ToolContext) -> str:
    topic = ctx.turn.get("topic") or {}
    examples = [x for x in (ctx.turn.get("example_questions") or []) if isinstance(x, dict)]
    similar = ctx.turn.get("similar") or []
    src = examples[0] if examples else None
    if src is None:
        if not similar:
            similar = search_similar(
                course_chapter=topic.get("course_chapter"),
                section_prefix=topic.get("section_prefix"),
                limit=1,
                include_answer=True,
            )
        if not similar:
            return "未找到可复用的同章题目骨架。请指定章节、知识点或源题号。"
        src = similar[0]
    full = src
    if src.get("id") is not None:
        full = get_question(src["id"], include_answer=True) or src
    payload = {
        "id": allocate_question_id(ctx.store),
        "chapter": full.get("section") or src.get("chapter"),
        "question": full.get("question") or src.get("question"),
        "options": full.get("options") or src.get("options"),
        "answer": full.get("answer") or "A",
        "analysis": "【演示模式】此草稿复制自原题骨架，仅更换了 id。配置 LLM_API_KEY 后将改写题面并重算答案。",
        "has_image": bool(full.get("has_image") or src.get("has_image")),
    }
    if full.get("graph") or src.get("graph"):
        payload["graph"] = full.get("graph") or src.get("graph")
    if full.get("options_graph") or src.get("options_graph"):
        payload["options_graph"] = full.get("options_graph") or src.get("options_graph")
    check = validate_question(payload)
    saved = ctx.store.save_draft(payload, batch_id=ctx.extra.get("batch_id") or "")
    saved["payload"] = payload  # demo 分支同样携带完整题面，供前端草稿卡渲染
    ctx.turn["drafts"] = [saved]
    return (
        "【演示模式，未配置 LLM_API_KEY】已按同章原题骨架写入 1 道草稿"
        f"（draft_id={saved['draft_id']}，status={saved['status']}）。\n"
        f"校验：{'通过' if check['ok'] else '失败'} {check.get('errors')}\n"
        "演示模式未走「较大变动」构思与 novelty 校验。配置 API Key 后将按新工作流改写出题。\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )


def _demo_turn(flow_id: str, message: str, ctx: ToolContext) -> Iterator[Event]:
    extra = ctx.extra or {}
    events, topic = _run_tool(
        "resolve_topic",
        {"text": message, "chapter": extra.get("chapter"), "question_id": extra.get("question_id")},
        ctx,
    )
    yield from events
    example_ids = extra.get("example_question_ids") or []
    if isinstance(topic, dict) and topic.get("question_id") and topic["question_id"] not in example_ids:
        ev, _ = _run_tool("get_question", {"question_id": topic["question_id"]}, ctx)
        yield from ev
    if flow_id == "generate_items":
        for qid in example_ids:
            ev, _ = _run_tool(
                "get_question",
                {"question_id": qid, "include_answer": True},
                ctx,
            )
            yield from ev

    query = message
    if isinstance(topic, dict) and topic.get("section"):
        query = f"{topic.get('section')} {message}"
    ev, retrieval = _run_tool("retrieve_chunks", {"query": query}, ctx)
    yield from ev

    if flow_id == "generate_items":
        args = {
            "course_chapter": (topic or {}).get("course_chapter") if isinstance(topic, dict) else None,
            "section_prefix": (topic or {}).get("section_prefix") if isinstance(topic, dict) else None,
        }
        ev, _ = _run_tool("search_similar_questions", args, ctx)
        yield from ev
        text = _demo_generate(message, ctx)
        # 与 live 分支保持一致：每保存一道题即推送 draft 事件
        for saved in ctx.turn.get("drafts") or []:
            yield {"type": "draft", **saved}
    else:
        text = _demo_explain(message, ctx)

    for chunk in llm.chunk_text(text):
        yield {"type": "text", "delta": chunk}
    yield {"type": "citations", "items": _citations_from_turn(ctx.turn)}
    ctx.turn["final_text"] = text


def _retrieval_empty(ctx: ToolContext) -> bool:
    retrieval = ctx.turn.get("retrieval") or {}
    hits = retrieval.get("hits") or []
    return bool(retrieval.get("empty") or not hits)


def _explain_out_of_scope(ctx: ToolContext, message: str) -> bool:
    """越界判定：主题不确定 + 不像本课问题 + 检索证据分低于越界阈值。

    注意检索混合了向量分，生活类问题（如菜谱）也可能捞到几个低分切片，
    因此不能用「有命中就算相关」，必须看最高分是否达到课程问题的水平。
    """
    topic = ctx.turn.get("topic") or {}
    if not topic.get("uncertain", True):
        return False
    if looks_like_course_question(message):
        return False
    retrieval = ctx.turn.get("retrieval") or {}
    max_score = float(retrieval.get("max_score") or 0.0)
    return max_score < get_settings().off_topic_score


def run_turn(
    message: str,
    flow_id: str | None = None,
    session_id: str | None = None,
    context: dict | None = None,
    store: AgentStore | None = None,
    user_id: str = "",
    stream: bool = True,
) -> Iterator[Event]:
    """执行一轮对话，产出事件 dict 流。

    事件类型：session / text / tool_start / tool_end / draft / citations / error / done。
    live 模式下文本 delta 来自 LLM 的真实 token 流（stream=True，两段式：
    工具编排轮的过渡文本照常转发，最终回答轮逐 token 转发）；
    demo 模式回退为 chunk_text 假流式。
    """
    ensure_bank_indexed()
    persona = load_persona()
    flow_id = flow_id or persona.get("default_flow", "explain")
    if flow_id in {"qa", "tutoring"}:
        flow_id = "explain"
    try:
        flow = load_flow(flow_id)
    except FileNotFoundError:
        yield {"type": "error", "message": f"未知任务流 {flow_id}"}
        yield {"type": "done"}
        return

    store = store or AgentStore(user_id=user_id)
    if user_id and not store.user_id:
        store.user_id = user_id
    session_id = store.ensure_session(session_id, flow_id)
    yield {"type": "session", "session_id": session_id, "flow_id": flow_id}

    extra = dict(context or {})
    extra["message"] = message
    store.add_message(session_id, "user", message)
    ctx = ToolContext(store=store, flow_id=flow_id, extra=extra, user_id=user_id or store.user_id)

    if not llm.chat_available():
        final = ""
        for event in _demo_turn(flow_id, message, ctx):
            if event.get("type") == "text":
                final += event.get("delta") or ""
            yield event
        store.add_message(session_id, "assistant", ctx.turn.get("final_text") or final)
        yield {
            "type": "done",
            "demo": True,
            "drafts": ctx.turn.get("drafts") or [],
            "out_of_scope": _explain_out_of_scope(ctx, message) if flow_id == "explain" else False,
        }
        return

    history = store.history(session_id, limit=12)
    messages = [{"role": "system", "content": build_system_prompt(persona, flow, extra)}]
    messages.extend(history)
    whitelist = flow.get("tools") or persona.get("tools") or []
    tools = openai_tools(flow_id, whitelist)
    settings = get_settings()
    max_steps = int(flow.get("max_steps") or persona.get("max_steps") or settings.max_steps)
    final_text = ""

    for _ in range(max_steps):
        # 真实 token 流式：complete_stream 在工作线程中生成，delta 经队列实时
        # 转发给 SSE 生成器——token 到一个发一个，不再等整轮生成完毕（修复
        # "一瞬间给出大段回复"的体验问题）。
        q: "queue.Queue[tuple[str, object]]" = queue.Queue()
        holder: dict = {}

        def _worker(msgs=messages, _tools=tools, _q=q, _holder=holder):
            try:
                _holder["reply"] = llm.complete_stream(
                    msgs, _tools,
                    on_text_delta=lambda t: _q.put(("delta", t)),
                    on_reasoning_delta=lambda t: _q.put(("think", t)),
                )
                _q.put(("done", None))
            except Exception as exc:  # noqa: BLE001
                _q.put(("error", exc))

        threading.Thread(target=_worker, daemon=True).start()
        reply: dict | None = None
        round_text_parts: list[str] = []
        round_think_parts: list[str] = []
        while True:
            try:
                kind, payload = q.get(timeout=0.1)
            except queue.Empty:
                continue
            if kind == "delta":
                round_text_parts.append(payload)
                yield {"type": "text", "delta": payload}
            elif kind == "think":
                round_think_parts.append(payload)
                yield {"type": "think", "delta": payload}
            elif kind == "error":
                yield {"type": "error", "message": f"模型调用失败：{payload}"}
                yield {"type": "done"}
                return
            else:
                reply = holder.get("reply")
                break
        assert reply is not None

        def _log_think(text: str) -> None:
            text = (text or "").strip()
            if text:
                ctx.tool_log.append({"kind": "think", "text": text})

        if reply["tool_calls"]:
            # 编排轮：思考内容与本轮过渡文本归入"思考"日志（前端在 tool_start 时
            # 将过渡文本收进折叠面板），随后执行工具
            _log_think("".join(round_think_parts))
            _log_think("".join(round_text_parts))
            messages.append(
                {
                    "role": "assistant",
                    "content": reply["content"] or None,
                    "tool_calls": [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {"name": tc["name"], "arguments": tc["arguments"]},
                        }
                        for tc in reply["tool_calls"]
                    ],
                }
            )
            for tc in reply["tool_calls"]:
                try:
                    args = json.loads(tc["arguments"] or "{}")
                except json.JSONDecodeError:
                    args = {}
                yield {"type": "tool_start", "name": tc["name"], "args": args}
                result = execute(tc["name"], args, ctx)
                ctx.tool_log.append(
                    {"kind": "tool", "name": tc["name"], "args": args,
                     "ok": not (isinstance(result, dict) and result.get("error"))}
                )
                preview = result if not isinstance(result, list) else result[:4]
                yield {"type": "tool_end", "name": tc["name"], "ok": True, "preview": preview}
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )
                # 每保存一道题即推送 draft 事件（教师端流式预览的关键）
                if tc["name"] == "save_question_draft" and isinstance(result, dict) and result.get("draft_id"):
                    yield {"type": "draft", **result}
            continue

        # 最终回答轮：delta 已实时转发，无需重发；思考内容也入日志
        _log_think("".join(round_think_parts))
        final_text = reply["content"] or ""
        break

    if not final_text:
        final_text = "（模型没有返回文本）"
        yield {"type": "text", "delta": final_text}

    yield {"type": "citations", "items": _citations_from_turn(ctx.turn)}
    store.add_message(session_id, "assistant", final_text)
    if ctx.tool_log:
        store.set_last_tool_log(session_id, ctx.tool_log, draft_id=_first_draft_id(ctx))
    yield {
        "type": "done",
        "drafts": ctx.turn.get("drafts") or [],
        "out_of_scope": _explain_out_of_scope(ctx, message) if flow_id == "explain" else False,
    }


def _first_draft_id(ctx: ToolContext) -> str:
    drafts = ctx.turn.get("drafts") or []
    if drafts and isinstance(drafts[0], dict):
        return drafts[0].get("draft_id") or ""
    return ""
