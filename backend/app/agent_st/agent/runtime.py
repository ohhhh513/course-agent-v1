from __future__ import annotations

import json
from collections.abc import Iterator

from app.agent_st.agent import llm
from app.agent_st.agent.config import get_settings
from app.agent_st.agent.context import ToolContext
from app.agent_st.agent.loader import build_system_prompt, load_flow, load_persona
from app.agent_st.agent.registry import execute, openai_tools
from app.agent_st.agent.store import AgentStore, allocate_question_id
from app.agent_st.rag.bank import get_question, search_similar
from app.agent_st.rag.ingest import ensure_bank_indexed
from app.agent_st.rag.validate import validate_question

# 注册工具
from app.agent_st.agent.tools import bank, draft, rag, topic, validate  # noqa: F401

EMPTY_RETRIEVAL_TEXT = "未检索到原文。请换一个章节关键词、题号或问法后再试。我不会用记忆补定义。"
NEED_TOPIC_TEXT = "请先指定章节或题号，例如：「讲解 KMP」「第4章」「题12」。不确定主题时不会全库检索。"
# 讲解流没走检索就出结论时，同样要求用户明确主题，措辞与演示模式保持一致。
NO_RETRIEVAL_TEXT = "讲解前必须先检索原文，不能凭记忆作答。" + NEED_TOPIC_TEXT

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
    if retrieval.get("empty"):
        return EMPTY_RETRIEVAL_TEXT
    hits = retrieval.get("hits") or []
    topic = ctx.turn.get("topic") or {}
    lines = [
        "【演示模式，未配置 LLM_API_KEY】以下讲解只根据检索片段整理。",
        "",
        f"结论：该问题对应 {topic.get('course_title') or ''} {topic.get('section') or ''}。",
        "",
    ]
    for hit in hits[:3]:
        qid = hit.get("question_id")
        cite = f"[题号 {qid}]" if qid else f"[小节 {hit.get('section')}]"
        lines.append(f"依据：{hit.get('text', '')[:220]} {cite}")
        lines.append("")
    lines.append("易错点：请以引用片段为准，不要用课外定义替换。")
    lines.append("若需要同类练习，请切换到「智能出题」。")
    return "\n".join(lines)


def _demo_generate(message: str, ctx: ToolContext) -> str:
    topic = ctx.turn.get("topic") or {}
    similar = ctx.turn.get("similar") or []
    if not similar:
        similar = search_similar(
            course_chapter=topic.get("course_chapter"),
            section_prefix=topic.get("section_prefix"),
            limit=1,
            include_answer=True,
        )
    if not similar:
        return "未找到可复用的同章题目骨架。请指定章节或源题号。"
    src = similar[0]
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
        "请到草稿列表查看。配置 API Key 后可真正改写相似题。\n\n"
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
    if isinstance(topic, dict) and topic.get("question_id"):
        ev, _ = _run_tool("get_question", {"question_id": topic["question_id"]}, ctx)
        yield from ev
    if isinstance(topic, dict) and topic.get("uncertain") and flow_id == "explain":
        for chunk in llm.chunk_text(NEED_TOPIC_TEXT):
            yield {"type": "text", "delta": chunk}
        yield {"type": "citations", "items": []}
        return

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
    return bool(retrieval.get("empty"))


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
        yield {"type": "done", "demo": True, "drafts": ctx.turn.get("drafts") or []}
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
        # 真实 token 流式：本轮产出的文本 delta 先收集，确定非 tool_calls 轮后转发
        buffer: list[Event] = []

        def on_text_delta(t: str, _buf: list[Event] = buffer) -> None:
            _buf.append({"type": "text", "delta": t})

        try:
            reply = llm.complete_stream(messages, tools, on_text_delta=on_text_delta)
        except Exception as exc:  # noqa: BLE001
            yield {"type": "error", "message": f"模型调用失败：{exc}"}
            yield {"type": "done"}
            return

        if reply["tool_calls"]:
            # 编排轮：过渡文本照常转发，随后执行工具
            for ev in buffer:
                yield ev
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
                    {"name": tc["name"], "args": args,
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

        # 最终回答轮：delta 来自真实 token 流
        for ev in buffer:
            yield ev
        final_text = reply["content"] or ""
        break

    if flow_id == "explain" and _retrieval_empty(ctx):
        final_text = EMPTY_RETRIEVAL_TEXT
        yield {"type": "text", "delta": final_text}
    elif flow_id == "explain" and "retrieval" not in ctx.turn:
        final_text = NO_RETRIEVAL_TEXT
        yield {"type": "text", "delta": final_text}
    elif not final_text:
        final_text = "（模型没有返回文本）"
        yield {"type": "text", "delta": final_text}

    yield {"type": "citations", "items": _citations_from_turn(ctx.turn)}
    store.add_message(session_id, "assistant", final_text)
    if ctx.tool_log:
        store.set_last_tool_log(session_id, ctx.tool_log, draft_id=_first_draft_id(ctx))
    yield {"type": "done", "drafts": ctx.turn.get("drafts") or []}


def _first_draft_id(ctx: ToolContext) -> str:
    drafts = ctx.turn.get("drafts") or []
    if drafts and isinstance(drafts[0], dict):
        return drafts[0].get("draft_id") or ""
    return ""
