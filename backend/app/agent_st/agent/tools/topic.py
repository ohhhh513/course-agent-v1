from __future__ import annotations

from app.agent_st.agent.context import ToolContext
from app.agent_st.agent.registry import tool
from app.agent_st.rag import structure
from app.agent_st.rag.topic import resolve_topic as resolve_topic_impl


@tool(
    name="resolve_topic",
    description=(
        "根据用户问题、题号或知识点定位到本课程的「章(CH0x) + 知识点(KP0xx)」。"
        "规则优先于猜测：先按本课程知识点名称匹配，命中不了才做检索投票兜底。"
        "返回 kp_ids 表示涉及多个知识点，kp_id 是主知识点。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "用户原话或知识点描述（整句传入，不要拆词）"},
            "kp_id": {"type": "string", "description": "已知知识点 id，如 KP014"},
            "chapter_id": {"type": "string", "description": "已知章 id，如 CH06"},
            "q_id": {"type": "string", "description": "已知题号，如 Q8FE3AE1"},
        },
    },
    flows=("explain", "generate_items"),
)
def resolve_topic(
    ctx: ToolContext,
    text: str = "",
    kp_id: str | None = None,
    chapter_id: str | None = None,
    q_id: str | None = None,
):
    extra = ctx.extra or {}
    course_id = extra.get("courseId") or ""
    target_q = q_id or extra.get("q_id")
    if not target_q:
        example_ids = extra.get("example_question_ids") or []
        if example_ids:
            target_q = example_ids[0]

    # 上下文里的知识点：教师端一次可勾选多个（kp_ids 列表），单值 kpId 兼容保留
    ctx_kps = [str(x) for x in (extra.get("kp_ids") or []) if str(x).strip()]
    single = str(kp_id or extra.get("kpId") or "").strip()
    if single:
        ctx_kps = [single] + [k for k in ctx_kps if k != single]

    result = resolve_topic_impl(
        course_id=course_id,
        text=text or extra.get("message") or "",
        kp_id=ctx_kps[0] if ctx_kps else None,
        chapter_id=chapter_id or extra.get("chapterId"),
        q_id=target_q,
    )

    # 上下文显式给了多个知识点时，整体作为定位结果（与主库多 KP 口径一致：
    # kp_id = 主 KP，kp_ids = 完整列表）。显式选择优先于任何推断。
    if len(ctx_kps) > 1:
        infos = [i for i in (structure.kp_info(course_id, k) for k in ctx_kps) if i]
        if infos:
            result.update({
                "kp_id": infos[0]["kp_id"],
                "kp_ids": [i["kp_id"] for i in infos],
                "kp_name": infos[0]["kp_name"],
                "kp_names": [i["kp_name"] for i in infos],
                "chapter_id": infos[0]["chapter_id"],
                "chapter_name": infos[0]["chapter_name"],
                "uncertain": False,
                "matched_by": result.get("matched_by") or "context_kp_multi",
            })
    ctx.turn["topic"] = result
    return result
