from __future__ import annotations

from app.agent_st.agent.context import ToolContext
from app.agent_st.agent.registry import tool
from app.agent_st.rag.topic import resolve_topic as resolve_topic_impl


@tool(
    name="resolve_topic",
    description="根据用户问题、题号或章节定位课程大章与王道小节。规则优先于猜测。不确定时不要全库检索。",
    parameters={
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "用户原话或知识点描述"},
            "chapter": {"type": "string", "description": "已知章节字符串，如 6.4 图的应用"},
            "question_id": {"type": "integer", "description": "已知题号"},
        },
    },
    flows=("explain", "generate_items"),
)
def resolve_topic(ctx: ToolContext, text: str = "", chapter: str | None = None, question_id: int | None = None):
    extra = ctx.extra or {}
    result = resolve_topic_impl(
        text=text or extra.get("message") or "",
        chapter=chapter or extra.get("chapter"),
        question_id=question_id if question_id is not None else extra.get("question_id"),
    )
    ctx.turn["topic"] = result
    return result
