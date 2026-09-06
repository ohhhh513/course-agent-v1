from __future__ import annotations

from app.agent_st.agent.context import ToolContext
from app.agent_st.agent.registry import tool
from app.agent_st.rag.bank import get_question as load_one
from app.agent_st.rag.bank import search_similar


@tool(
    name="get_question",
    description="按题号读取题库中的题目。讲解某题时使用。默认不返回标准答案。",
    parameters={
        "type": "object",
        "properties": {
            "question_id": {"type": "integer"},
            "include_answer": {"type": "boolean"},
        },
        "required": ["question_id"],
    },
    flows=("explain", "generate_items"),
)
def get_question(ctx: ToolContext, question_id: int, include_answer: bool = False):
    item = load_one(int(question_id), include_answer=include_answer)
    if item is None:
        return {"error": "题目不存在", "question_id": question_id}
    ctx.turn["question"] = item
    return item


@tool(
    name="search_similar_questions",
    description="检索同章、同配图形态的原题作为出题骨架。默认不返回 answer/analysis。",
    parameters={
        "type": "object",
        "properties": {
            "course_chapter": {"type": "integer"},
            "section_prefix": {"type": "string"},
            "figure_mode": {"type": "string"},
            "graph_type": {"type": "string"},
            "exclude_id": {"type": "integer"},
            "limit": {"type": "integer"},
        },
    },
    flows=("generate_items",),
)
def search_similar_questions(
    ctx: ToolContext,
    course_chapter: int | None = None,
    section_prefix: str | None = None,
    figure_mode: str | None = None,
    graph_type: str | None = None,
    exclude_id: int | None = None,
    limit: int = 3,
):
    topic = ctx.turn.get("topic") or {}
    question = ctx.turn.get("question") or {}
    raw = (question.get("raw") or {}) if isinstance(question, dict) else {}
    gtype = graph_type or (raw.get("graph") or {}).get("type")
    fig = figure_mode or (question.get("figureMode") if question else None)
    hits = search_similar(
        course_chapter=course_chapter or topic.get("course_chapter"),
        section_prefix=section_prefix or topic.get("section_prefix"),
        figure=fig,
        graph_type=gtype,
        exclude_id=exclude_id or topic.get("question_id"),
        limit=limit or 3,
        include_answer=False,
    )
    ctx.turn["similar"] = hits
    return hits
