from __future__ import annotations

from app.agent_st.agent.config import get_settings
from app.agent_st.agent.context import ToolContext
from app.agent_st.agent.registry import tool
from app.agent_st.rag.retrieve import retrieve_chunks as retrieve_impl

DEFAULT_EXPLAIN = ["question_analysis", "textbook", "ppt", "transcript"]
DEFAULT_GENERATE = ["question_stem", "question_analysis", "textbook"]


@tool(
    name="retrieve_chunks",
    description="按当前课的切片检索原文。必须先 resolve_topic。返回带 score 的片段，禁止编造未出现的内容。",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "course_chapter": {"type": "integer"},
            "section_prefix": {"type": "string"},
            "source_types": {
                "type": "array",
                "items": {"type": "string"},
                "description": "question_stem / question_analysis / textbook / ppt / transcript",
            },
            "top_k": {"type": "integer"},
        },
        "required": ["query"],
    },
    flows=("explain", "generate_items"),
)
def retrieve_chunks(
    ctx: ToolContext,
    query: str,
    course_chapter: int | None = None,
    section_prefix: str | None = None,
    source_types: list[str] | None = None,
    top_k: int | None = None,
):
    settings = get_settings()
    topic = ctx.turn.get("topic") or {}
    chapter = course_chapter or topic.get("course_chapter")
    prefix = section_prefix or topic.get("section_prefix")
    if ctx.flow_id == "generate_items":
        types = source_types or DEFAULT_GENERATE
    else:
        types = source_types or DEFAULT_EXPLAIN
    # 课程上下文是整个链路的隔离边界：缺失时不做「不过滤」兜底，
    # 直接返回空证据，让模型按 refuse_hint 诚实声明而不是混搜其它课程。
    course_id = (ctx.extra or {}).get("courseId") or ""
    hits = retrieve_impl(
        query=query,
        course_id=course_id or None,
        course_chapter=chapter,
        section_prefix=prefix,
        source_types=types,
        top_k=top_k or settings.retrieve_top_k,
    )
    this_call_empty = (not hits) or hits[0]["score"] < settings.min_retrieve_score

    # 同一轮里模型常会换关键词或换来源再检一次（例如先查解析再查教材）。
    # 如果第二次没命中就把上一次的原文丢掉，会误判成“未检索到原文”，
    # 因此同一章节范围内把历次命中按最高分合并保留。
    scope = (course_id, chapter, prefix)
    prev_hits = ctx.turn.get("retrieval_hits") or []
    if ctx.turn.get("retrieval_scope") != scope:
        prev_hits = []
    merged: dict[str, dict] = {}
    for hit in list(prev_hits) + list(hits):
        key = str(hit.get("chunk_id"))
        if key in merged and merged[key]["score"] >= hit["score"]:
            continue
        merged[key] = hit
    merged_hits = sorted(merged.values(), key=lambda item: item["score"], reverse=True)

    max_score = merged_hits[0]["score"] if merged_hits else 0.0
    empty = (not merged_hits) or max_score < settings.min_retrieve_score
    limit = max(1, top_k or settings.retrieve_top_k)
    if not course_id:
        refuse_hint = (
            "本轮未取得课程上下文（courseId 缺失），因此**没有检索任何切片**。"
            "请直接说明无法在未确定课程的情况下作答，不得凭记忆或常识补全，禁止伪造引用。"
        )
    elif empty:
        refuse_hint = (
            "未检索到课程原文。若问题与数据结构课程明显无关（日常生活等），直接简短说明本助手只覆盖数据结构课程内容，"
            "不得讲解该问题本身；若属课程相关但证据不足，可用【补充】声明非课程原文。不得伪造引用。"
        )
    else:
        refuse_hint = None
    payload = {
        "hits": merged_hits[:limit],
        "empty": empty,
        "max_score": max_score,
        "course_id": course_id,
        "course_chapter": chapter,
        "section_prefix": prefix,
        "source_types": types,
        "empty_this_call": this_call_empty,
        "refuse_hint": refuse_hint,
    }
    ctx.turn["retrieval"] = payload
    ctx.turn["retrieval_scope"] = scope
    ctx.turn["retrieval_hits"] = merged_hits
    ctx.turn["citations"] = payload["hits"]
    return payload
