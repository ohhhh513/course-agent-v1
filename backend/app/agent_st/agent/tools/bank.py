from __future__ import annotations

from app.agent_st.agent.context import ToolContext
from app.agent_st.agent.registry import tool
from app.agent_st.rag.bank import get_question as load_one
from app.agent_st.rag.bank import search_similar


def _course_id(ctx: ToolContext) -> str:
    """课程上下文是本层的隔离边界；缺失时一律查不到题（fail-closed）。"""
    return (ctx.extra or {}).get("courseId") or ""


@tool(
    name="get_question",
    description="按题号读取本课程题库中的题目。讲解默认不返回答案；出题流可读答案以便避开原解题路径。",
    parameters={
        "type": "object",
        "properties": {
            "q_id": {"type": "string", "description": "题号，如 KHD001 / AI003"},
            "include_answer": {"type": "boolean"},
        },
        "required": ["q_id"],
    },
    flows=("explain", "generate_items"),
)
def get_question(ctx: ToolContext, q_id: str, include_answer: bool | None = None):
    if include_answer is None:
        include_answer = ctx.flow_id == "generate_items"
    course_id = _course_id(ctx)
    if not course_id:
        return {"error": "缺少课程上下文，无法读取题目", "q_id": q_id}
    item = load_one(course_id, str(q_id), include_answer=bool(include_answer))
    if item is None:
        return {"error": "题目不存在", "q_id": q_id}
    ctx.turn["question"] = item
    examples = ctx.turn.setdefault("example_questions", [])
    if not any(x.get("q_id") == item["q_id"] for x in examples if isinstance(x, dict)):
        examples.append(item)
    return item


@tool(
    name="search_similar_questions",
    description="检索同章/同知识点题目作为防抄黑名单。不要把命中题当可微调骨架，不要抄题干或选项。默认不返回 answer/analysis。",
    parameters={
        "type": "object",
        "properties": {
            "chapter_id": {"type": "string", "description": "章 id，如 CH06"},
            "kp_id": {"type": "string", "description": "知识点 id，如 KP014"},
            "kp_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "多个知识点 id（命中任一即算），如 [\"KP014\",\"KP013\"]",
            },
            "figure_mode": {"type": "string"},
            "graph_type": {"type": "string"},
            "exclude_q_id": {"type": "string"},
            "limit": {"type": "integer"},
        },
    },
    flows=("generate_items",),
)
def search_similar_questions(
    ctx: ToolContext,
    chapter_id: str | None = None,
    kp_id: str | None = None,
    kp_ids: list[str] | None = None,
    figure_mode: str | None = None,
    graph_type: str | None = None,
    exclude_q_id: str | None = None,
    limit: int = 3,
):
    course_id = _course_id(ctx)
    if not course_id:
        return {"error": "缺少课程上下文，无法检索同章题目", "hits": []}

    topic = ctx.turn.get("topic") or {}
    exclude: set[str] = set()
    for raw in (ctx.extra or {}).get("example_question_ids") or []:
        exclude.add(str(raw))
    if exclude_q_id:
        exclude.add(str(exclude_q_id))
    elif topic.get("q_id"):
        exclude.add(str(topic["q_id"]))

    want = limit or 3
    # 知识点：显式传入优先，其次用 resolve_topic 的多 KP 结果（成员匹配，避免漏题）
    want_kps = [str(x).strip() for x in (kp_ids or []) if str(x).strip()]
    if kp_id and str(kp_id).strip() and str(kp_id).strip() not in want_kps:
        want_kps.insert(0, str(kp_id).strip())
    if not want_kps:
        want_kps = [str(x) for x in (topic.get("kp_ids") or []) if str(x).strip()]
        if not want_kps and topic.get("kp_id"):
            want_kps = [str(topic["kp_id"])]

    hits = search_similar(
        course_id=course_id,
        chapter_id=chapter_id or topic.get("chapter_id"),
        kp_ids=want_kps or None,
        figure=figure_mode,
        graph_type=graph_type,
        exclude_q_id=None,
        limit=want + len(exclude),
        include_answer=False,
    )
    if exclude:
        hits = [h for h in hits if str(h.get("q_id")) not in exclude][:want]
    ctx.turn["similar"] = hits
    return hits
