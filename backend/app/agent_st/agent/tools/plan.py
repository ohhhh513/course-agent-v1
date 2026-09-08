from __future__ import annotations

from app.agent_st.agent.context import ToolContext
from app.agent_st.agent.registry import tool
from app.agent_st.agent.tools.validate import _parse_question
from app.agent_st.rag.bank import get_question as load_one
from app.agent_st.rag.bank import search_similar
from app.agent_st.rag.novelty import check_novelty as check_novelty_impl
from app.agent_st.rag.novelty import question_fingerprint

_PLAN_FIELDS = (
    ("asked_target", 4, "提问目标"),
    ("instance_sketch", 8, "实例草图"),
    ("solution_trace", 40, "逐步解题过程"),
    ("correct_answer_content", 1, "正确结论"),
    ("distractor_rationale", 8, "干扰项易错点"),
    ("change_note", 4, "相对对照题的变动说明"),
)


def _collect_references(ctx: ToolContext) -> list[dict]:
    refs: list[dict] = []
    seen: set[int] = set()

    def add(item: dict | None) -> None:
        if not isinstance(item, dict):
            return
        raw_id = item.get("id") if item.get("id") is not None else item.get("question_id")
        try:
            qid = int(raw_id) if raw_id is not None else None
        except (TypeError, ValueError):
            qid = None
        if qid is not None:
            if qid in seen:
                return
            seen.add(qid)
        refs.append(item)

    for item in ctx.turn.get("example_questions") or []:
        add(item)
    extra = ctx.extra or {}
    for raw_id in extra.get("example_question_ids") or []:
        try:
            qid = int(raw_id)
        except (TypeError, ValueError):
            continue
        if qid in seen:
            continue
        loaded = load_one(qid, include_answer=True)
        add(loaded)
    for item in ctx.turn.get("similar") or []:
        add(item)
    if not refs:
        topic = ctx.turn.get("topic") or {}
        auto_hits = search_similar(
            course_chapter=topic.get("course_chapter"),
            section_prefix=topic.get("section_prefix"),
            limit=3,
            include_answer=False,
        )
        for item in auto_hits:
            add(item)
    return refs


@tool(
    name="submit_item_plan",
    description="先提交新题构思：提问目标、实例草图、逐步解题与正确结论、干扰项易错点、相对对照题如何较大变动。保存前必须调用。",
    parameters={
        "type": "object",
        "properties": {
            "asked_target": {"type": "string", "description": "这道题问的是什么（如 Kruskal 第一条边）"},
            "instance_sketch": {"type": "string", "description": "新实例草图：规模、图/数组/树的要点"},
            "solution_trace": {"type": "string", "description": "逐步解题过程与计算"},
            "correct_answer_content": {"type": "string", "description": "正确结论（内容，不只是字母）"},
            "distractor_rationale": {"type": "string", "description": "三个错误选项分别对应哪类易错"},
            "change_note": {"type": "string", "description": "相对例题/题库对照题的较大变动说明"},
            "kp_or_section": {"type": "string", "description": "目标知识点或王道小节"},
        },
        "required": [
            "asked_target",
            "instance_sketch",
            "solution_trace",
            "correct_answer_content",
            "distractor_rationale",
            "change_note",
        ],
    },
    flows=("generate_items",),
)
def submit_item_plan(
    ctx: ToolContext,
    asked_target: str,
    instance_sketch: str,
    solution_trace: str,
    correct_answer_content: str,
    distractor_rationale: str,
    change_note: str,
    kp_or_section: str = "",
):
    values = {
        "asked_target": asked_target,
        "instance_sketch": instance_sketch,
        "solution_trace": solution_trace,
        "correct_answer_content": correct_answer_content,
        "distractor_rationale": distractor_rationale,
        "change_note": change_note,
        "kp_or_section": kp_or_section or "",
    }
    errors: list[str] = []
    for key, min_len, label in _PLAN_FIELDS:
        text = str(values.get(key) or "").strip()
        values[key] = text
        if len(text) < min_len:
            errors.append(f"{label}过短，请写清楚（至少 {min_len} 字）")
    payload = {"ok": not errors, "errors": errors, "plan": values}
    ctx.turn["item_plan"] = payload
    return payload


@tool(
    name="check_novelty",
    description="对照教师例题与 search_similar_questions 命中，检查是否只是数值/标签微扰。未通过禁止保存。",
    parameters={
        "type": "object",
        "properties": {
            "question": {
                "description": "待检查的题目 JSON 对象",
                "type": "object",
            }
        },
        "required": ["question"],
    },
    flows=("generate_items",),
)
def check_novelty(ctx: ToolContext, question):
    parsed = _parse_question(question)
    if not isinstance(parsed, dict):
        payload = {"ok": False, "errors": ["无法解析 question"], "fingerprint": ""}
        ctx.turn["last_novelty"] = payload
        return payload
    result = check_novelty_impl(parsed, _collect_references(ctx))
    result["fingerprint"] = result.get("fingerprint") or question_fingerprint(parsed)
    ctx.turn["last_novelty"] = result
    ctx.turn["pending_questions"] = [parsed]
    return result
