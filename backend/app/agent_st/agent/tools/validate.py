from __future__ import annotations

import json

from app.agent_st.agent.context import ToolContext
from app.agent_st.agent.registry import tool
from app.agent_st.agent.store import existing_draft_and_bank_ids
from app.agent_st.rag.validate import validate_question as validate_impl


def _parse_question(question) -> dict | list | None:
    if isinstance(question, (dict, list)):
        return question
    if isinstance(question, str):
        text = question.strip()
        if text.startswith("```"):
            text = text.strip("`")
            text = text[text.find("\n") + 1 :] if "\n" in text else text
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                return json.loads(text[start : end + 1])
            raise
    return None


@tool(
    name="validate_question",
    description="用确定性规则校验出题 JSON：必填字段、章节前缀、graph 闭集与结点/边一致性。失败必须按 errors 修改后再保存。",
    parameters={
        "type": "object",
        "properties": {
            "question": {
                "description": "一道题的 JSON 对象，或对象数组",
                "type": "object",
            }
        },
        "required": ["question"],
    },
    flows=("generate_items",),
)
def validate_question(ctx: ToolContext, question):
    parsed = _parse_question(question)
    if parsed is None:
        return {"ok": False, "errors": ["无法解析 question"]}
    items = parsed if isinstance(parsed, list) else [parsed]
    used = existing_draft_and_bank_ids(ctx.store)
    results = [validate_impl(item, used_ids=used) for item in items]
    payload = {"ok": all(r["ok"] for r in results), "results": results}
    ctx.turn["last_validate"] = payload
    ctx.turn["pending_questions"] = items
    return payload
