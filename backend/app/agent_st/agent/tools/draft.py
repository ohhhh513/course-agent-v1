from __future__ import annotations

import json

from app.agent_st.agent.context import ToolContext
from app.agent_st.agent.registry import tool
from app.agent_st.agent.store import allocate_question_id
from app.agent_st.rag.validate import validate_question as validate_impl


@tool(
    name="save_question_draft",
    description="把已校验通过的题目写入草稿库，不会修改 after_class.json。每题调用一次。",
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
    check = validate_impl(question)
    batch_id = (ctx.extra or {}).get("batch_id") or ""
    if not check["ok"]:
        saved = ctx.store.save_draft(question, batch_id=batch_id)
        return {
            "ok": False,
            "hint": "校验未通过，已写入 invalid 草稿，请按 errors 修改。不要声称已进入正式题库。",
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
