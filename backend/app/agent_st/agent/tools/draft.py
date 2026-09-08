from __future__ import annotations

import json

from app.agent_st.agent.context import ToolContext
from app.agent_st.agent.registry import tool
from app.agent_st.agent.store import allocate_question_id
from app.agent_st.rag.novelty import question_fingerprint
from app.agent_st.rag.validate import validate_question as validate_impl


def _plan_ready(ctx: ToolContext) -> list[str]:
    plan = ctx.turn.get("item_plan") or {}
    if not isinstance(plan, dict) or not plan.get("ok"):
        return ["请先调用 submit_item_plan，并写清逐步解题过程后再保存"]
    inner = plan.get("plan") or {}
    if len(str(inner.get("solution_trace") or "").strip()) < 40:
        return ["submit_item_plan 的解题过程过短，请补全后再保存"]
    return []


def _novelty_ready(ctx: ToolContext, question: dict) -> list[str]:
    novelty = ctx.turn.get("last_novelty") or {}
    if not isinstance(novelty, dict) or not novelty.get("ok"):
        errors = []
        if isinstance(novelty, dict) and novelty.get("errors"):
            errors.extend(str(e) for e in novelty["errors"])
        if not errors:
            errors.append("请先对当前题目调用 check_novelty 且通过后再保存")
        return errors
    expected = novelty.get("fingerprint") or ""
    actual = question_fingerprint(question)
    if expected and actual != expected:
        return ["当前题面与上次 check_novelty 不一致，请对修改后的 JSON 重新校验较大变动"]
    return []


@tool(
    name="save_question_draft",
    description="把已通过结构校验与较大变动校验的题目写入草稿库，不会修改 after_class.json。每题调用一次。",
    parameters={
        "type": "object",
        "properties": {
            "question": {"description": "一道题的 JSON 对象", "type": "object"},
        },
        "required": ["question"],
    },
    flows=("generate_items",),
)
def save_question_draft(ctx: ToolContext, question):
    if isinstance(question, str):
        question = json.loads(question)
    if not isinstance(question, dict):
        return {"error": "question 必须是对象"}
    if question.get("id") in (None, 0, "auto"):
        question = dict(question)
        question["id"] = allocate_question_id(ctx.store)

    blockers = _plan_ready(ctx) + _novelty_ready(ctx, question)
    if blockers:
        return {
            "ok": False,
            "errors": blockers,
            "hint": "未通过构思或较大变动校验，草稿未保存。请按 errors 修改后重试。",
            "payload": question,
        }

    check = validate_impl(question)
    batch_id = (ctx.extra or {}).get("batch_id") or ""
    if not check["ok"]:
        saved = ctx.store.save_draft(question, batch_id=batch_id)
        return {
            "ok": False,
            "hint": "结构校验未通过，已写入 invalid 草稿，请按 errors 修改。不要声称已进入正式题库。",
            "payload": question,
            **saved,
        }
    saved = ctx.store.save_draft(question, batch_id=batch_id)
    drafts = ctx.turn.setdefault("drafts", [])
    drafts.append(saved)
    return {
        "ok": True,
        "hint": "已写入草稿，请教师确认后再合并进正式题库。不要说已经加入 after_class.json。",
        "payload": question,
        **saved,
    }
