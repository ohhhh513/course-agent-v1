from __future__ import annotations

from app.agent_st.agent.context import ToolContext
from app.agent_st.agent.registry import tool
from app.agent_st.rag.bank import get_question as load_one
from app.agent_st.rag.bank import search_similar


@tool(
    name="get_question",
    description="按题号读取题库中的题目。讲解默认不返回答案；出题流可读答案以便避开原解题路径。",
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
def get_question(ctx: ToolContext, question_id: int, include_answer: bool | None = None):
    if include_answer is None:
        include_answer = ctx.flow_id == "generate_items"
    item = load_one(int(question_id), include_answer=bool(include_answer))
    if item is None:
        return {"error": "题目不存在", "question_id": question_id}
    ctx.turn["question"] = item
    examples = ctx.turn.setdefault("example_questions", [])
    try:
        qid = int(item.get("id") or question_id)
    except (TypeError, ValueError):
        qid = int(question_id)
    if not any(int(x.get("id") or 0) == qid for x in examples if isinstance(x, dict)):
        examples.append(item)
    return item


@tool(
    name="search_similar_questions",
    description="检索同章题目作为防抄黑名单。不要把命中题当可微调骨架，不要抄题干或选项。默认不返回 answer/analysis。",
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
    exclude: set[int] = set()
    for raw_id in (ctx.extra or {}).get("example_question_ids") or []:
        try:
            exclude.add(int(raw_id))
        except (TypeError, ValueError):
            continue
    if exclude_id is not None:
        exclude.add(int(exclude_id))
    elif topic.get("question_id"):
        exclude.add(int(topic["question_id"]))
    want = limit or 3
    hits = search_similar(
        course_chapter=course_chapter or topic.get("course_chapter"),
        section_prefix=section_prefix or topic.get("section_prefix"),
        figure=figure_mode,
        graph_type=graph_type,
        exclude_id=None,
        limit=want + len(exclude),
        include_answer=False,
    )
    if exclude:
        hits = [h for h in hits if int(h["id"]) not in exclude][:want]
    ctx.turn["similar"] = hits
    return hits
