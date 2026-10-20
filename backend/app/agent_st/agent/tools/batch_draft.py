from __future__ import annotations

from app.agent_st.agent.context import ToolContext
from app.agent_st.agent.registry import ApprovalSpec, is_approval_replay, tool
from app.agent_st.agent.tools.plan import _PLAN_FIELDS, _collect_references
from app.agent_st.agent.tools.plan import submit_item_plan
from app.agent_st.rag.novelty import check_novelty as check_novelty_impl
from app.agent_st.rag.validate import validate_question as validate_impl


def _items(args: dict) -> list[dict]:
    items = args.get("items")
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def _validate_batch(ctx: ToolContext, args: dict, *, check_quality: bool = True) -> tuple[list[dict], list[str]]:
    extra = ctx.extra or {}
    items = _items(args)
    try:
        configured_count = extra.get("count")
        expected_count = max(1, min(int(configured_count if configured_count is not None else len(items) or 1), 10))
    except (TypeError, ValueError):
        expected_count = 1
    errors: list[str] = []
    if len(items) != expected_count:
        errors.append(f"题目数量应为 {expected_count} 道，当前收到 {len(items)} 道")
    if len(items) != len(args.get("items") or []):
        errors.append("items 中的每一项都必须是对象")

    question_types = [str(value or "").strip() for value in (extra.get("question_types") or [])]
    selected_kps = {str(value).strip() for value in (extra.get("kp_ids") or []) if str(value).strip()}
    allowed_chapters = {
        str(value).strip() for value in (extra.get("allowed_chapter_ids") or []) if str(value).strip()
    }
    course_id = str(extra.get("courseId") or "").strip()
    if not course_id:
        errors.append("缺少课程上下文，拒绝保存题目草稿")
    if not items:
        return [], errors

    plans: list[dict] = []
    questions: list[dict] = []
    reserved = ctx.store.reserved_q_ids()
    for index, item in enumerate(items, start=1):
        label = f"第 {index} 道题"
        plan = item.get("plan")
        question = item.get("question")
        if not isinstance(plan, dict):
            errors.append(f"{label}缺少 plan 构思对象")
            plan = {}
        if not isinstance(question, dict):
            errors.append(f"{label}缺少 question 题目对象")
            question = {}

        if check_quality:
            plan_result = submit_item_plan(ctx, **{
                field: str(plan.get(field) or "") for field, _, _ in _PLAN_FIELDS
            }, kp_or_section=str(plan.get("kp_or_section") or ""))
            for issue in plan_result.get("errors") or []:
                errors.append(f"{label}构思不完整：{issue}")

        normalized = dict(question)
        normalized.pop("q_id", None)
        if index <= len(question_types) and question_types[index - 1]:
            expected_type = question_types[index - 1]
            actual_type = str(normalized.get("type") or "").strip()
            if actual_type != expected_type:
                errors.append(f"{label}题型应为 {expected_type}，当前为 {actual_type or '未填写'}")

        question_kps = normalized.get("kp_ids") if isinstance(normalized.get("kp_ids"), list) else []
        primary_kp = str(normalized.get("kp_id") or "").strip()
        question_kps = list(dict.fromkeys(
            [str(value).strip() for value in question_kps if str(value).strip()]
            + ([primary_kp] if primary_kp else [])
        ))
        if selected_kps:
            if not question_kps:
                errors.append(f"{label}未标注知识点")
            elif not set(question_kps).issubset(selected_kps):
                errors.append(f"{label}包含教师未选择的知识点")
        chapter_id = str(normalized.get("chapter_id") or "").strip()
        if allowed_chapters and chapter_id not in allowed_chapters:
            errors.append(f"{label}章节不在本次选择范围内")

        if course_id:
            checked = validate_impl(normalized, course_id=course_id, used_q_ids=reserved)
            for issue in checked.get("errors") or []:
                errors.append(f"{label}结构校验失败：{issue}")
            if checked.get("kp_ids"):
                normalized["kp_ids"] = checked["kp_ids"]
            if checked.get("kp_id"):
                normalized["kp_id"] = checked["kp_id"]
        plans.append(plan)
        questions.append(normalized)

    if check_quality and len(questions) == len(items):
        references = _collect_references(ctx)
        for index, question in enumerate(questions):
            peers = [peer for peer_index, peer in enumerate(questions) if peer_index != index]
            novelty = check_novelty_impl(question, references + peers)
            for issue in novelty.get("errors") or []:
                errors.append(f"第 {index + 1} 道题与例题或同批题目差异不足：{issue}")

    return questions, errors


def _precheck(ctx: ToolContext, args: dict) -> list[str]:
    _, errors = _validate_batch(ctx, args, check_quality=True)
    return errors


def _summarize(args: dict) -> str:
    count = len(_items(args))
    return f"保存 {count} 道 AI 题目草稿"


@tool(
    name="save_question_batch",
    description=(
        "一次提交一批新题。每项都必须带完整 plan 和 question；服务端逐题检查构思、题型、"
        "课程章节/知识点、题目结构与新颖度。全部通过后才会原子写入草稿库。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "minItems": 1,
                "maxItems": 10,
                "items": {
                    "type": "object",
                    "properties": {
                        "plan": {
                            "type": "object",
                            "properties": {
                                "asked_target": {"type": "string"},
                                "instance_sketch": {"type": "string"},
                                "solution_trace": {"type": "string"},
                                "correct_answer_content": {"type": "string"},
                                "distractor_rationale": {"type": "string"},
                                "change_note": {"type": "string"},
                                "kp_or_section": {"type": "string"},
                            },
                            "required": [
                                "asked_target", "instance_sketch", "solution_trace",
                                "correct_answer_content", "distractor_rationale", "change_note",
                            ],
                        },
                        "question": {
                            "type": "object",
                            "properties": {
                                "type": {"type": "string"},
                                "chapter_id": {"type": "string"},
                                "kp_id": {"type": "string"},
                                "kp_ids": {"type": "array", "items": {"type": "string"}},
                                "question": {"type": "string"},
                                "options": {"type": "object", "additionalProperties": {"type": "string"}},
                                "answer": {"type": "string"},
                                "analysis": {"type": "string"},
                                "has_image": {"type": "boolean"},
                                "graph": {"type": "object"},
                                "options_graph": {"type": "object"},
                            },
                            "required": [
                                "type", "chapter_id", "kp_ids", "question", "options",
                                "answer", "analysis", "has_image",
                            ],
                        },
                    },
                    "required": ["plan", "question"],
                },
            },
        },
        "required": ["items"],
    },
    flows=("generate_items",),
    roles=("teacher",),
    approval=ApprovalSpec(
        summarize=_summarize,
        precheck=_precheck,
        impact="一次写入当前教师在当前课程下的题目草稿；不会进入正式题库。",
    ),
)
def save_question_batch(ctx: ToolContext, items):
    from .. import cancel

    cancel_key = str((ctx.extra or {}).get("cancelKey") or "")
    if cancel_key and cancel.is_requested(cancel_key):
        return {"ok": False, "cancelled": True,
                "hint": "出题任务已停止，本批题目没有写入草稿。"}

    args = {"items": items}
    questions, errors = _validate_batch(
        ctx, args, check_quality=not is_approval_replay(ctx)
    )
    if errors:
        return {"ok": False, "errors": errors[:30],
                "hint": "草稿未保存。请只修正返回错误对应的题目，再提交完整题目批次。"}

    batch_id = str((ctx.extra or {}).get("batch_id") or "")
    if cancel_key:
        active, saved = cancel.run_if_active(
            cancel_key,
            lambda: ctx.store.save_drafts(questions, batch_id=batch_id),
        )
        if not active:
            return {"ok": False, "cancelled": True,
                    "hint": "出题任务已停止，本批题目没有写入草稿。"}
    else:
        saved = ctx.store.save_drafts(questions, batch_id=batch_id)
    ctx.turn.setdefault("drafts", []).extend(saved)
    return {
        "ok": True,
        "count": len(saved),
        "draft_ids": [item["draft_id"] for item in saved],
        "hint": "整批题目已写入草稿，尚未发布到正式题库。",
    }
