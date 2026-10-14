from __future__ import annotations

import json

from app.agent_st.agent.context import ToolContext
from app.agent_st.agent.registry import ApprovalSpec, is_approval_replay, tool
from app.agent_st.rag.bank import AI_QID_RE, next_ai_q_id
from app.agent_st.rag.novelty import question_fingerprint
from app.agent_st.rag.validate import validate_question as validate_impl


def _as_dict(value) -> dict:
    """模型可能把 question 传成 JSON 字符串（而不是对象），统一成 dict。"""
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


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


def _precheck(ctx: ToolContext, args: dict) -> list[str]:
    """写操作的前置校验 —— 在**拦截那一刻**跑（审批时 ctx.turn 已经是空的）。"""
    return _plan_ready(ctx) + _novelty_ready(ctx, _as_dict(args.get("question")))


def _summarize(args: dict) -> str:
    """确认卡片上那句「在做什么」：章节 · 知识点 · 题号 · 题面摘要。"""
    question = _as_dict(args.get("question"))
    bits = []
    if question.get("chapter_id"):
        bits.append(str(question["chapter_id"]))
    if question.get("kp_id"):
        bits.append(f"知识点 {question['kp_id']}")
    bits.append(f"题号 {question.get('q_id') or '（系统分配）'}")
    stem = str(question.get("question") or "").strip().replace("\n", " ")
    head = (stem[:36] + "…") if len(stem) > 36 else stem
    title = f"保存题目草稿：{' · '.join(bits)}"
    return f"{title}｜「{head}」" if head else title


@tool(
    name="save_question_draft",
    description="把已通过结构校验与较大变动校验的题目写入草稿库，不会写入正式题库。每题调用一次。",
    parameters={
        "type": "object",
        "properties": {
            "question": {"description": "一道题的 JSON 对象", "type": "object"},
        },
        "required": ["question"],
    },
    flows=("generate_items",),
    roles=("teacher",),  # 2026-10-06 收紧：管理员改用平台治理工具，不再共享出题流,
    # 写操作：必须由用户在界面上点「确认执行」后才真正落库（P2c）
    approval=ApprovalSpec(
        summarize=_summarize,
        precheck=_precheck,
        impact="写入你的个人草稿箱（st_question_drafts），不会进入正式题库；"
               "之后可在「AI 出题与题库」里编辑、发布或删除。",
    ),
)
def save_question_draft(ctx: ToolContext, question):
    if isinstance(question, str):
        question = json.loads(question)
    if not isinstance(question, dict):
        return {"error": "question 必须是对象"}
    course_id = (ctx.extra or {}).get("courseId") or ""
    if not course_id:
        return {"error": "缺少课程上下文，拒绝写入草稿"}

    question = dict(question)
    # 题号一律由系统分配，不信任模型给的值：
    # 模型常把提示词里的示例串（如 `AI###`）或自编号写进 JSON，也可能复用已占用的号。
    # 只有「规范 AI 号且尚未被占用」才沿用（幂等重试场景），其余一律重新分配。
    reserved = ctx.store.reserved_q_ids()
    given = str(question.get("q_id") or "").strip()
    if not AI_QID_RE.match(given) or given in reserved:
        question["q_id"] = next_ai_q_id(course_id, reserved=reserved)

    # 正常轮次不会走到这里（写操作已在 execute() 被拦成「待批准」并完成前置校验）；
    # 审批回放时不再重跑构思/查重 —— 那是原轮的内存状态，新请求里已经拿不到，
    # 且当时已校验过。这里只保留结构校验与写入。
    if not is_approval_replay(ctx):
        blockers = _plan_ready(ctx) + _novelty_ready(ctx, question)
        if blockers:
            return {
                "ok": False,
                "errors": blockers,
                "hint": "未通过构思或较大变动校验，草稿未保存。请按 errors 修改后重试。",
                "payload": question,
            }

    batch_id = (ctx.extra or {}).get("batch_id") or ""
    check = validate_impl(question, course_id=course_id, used_q_ids=ctx.store.reserved_q_ids())
    # 归一化结构归属：模型可能只给 kp_id 或只给 kp_ids，落库前统一成
    # 「kp_id = 主 KP，kp_ids = 完整列表」（与主库/题库管理侧口径一致），
    # 发布链路直接复用，不用再猜。
    if check.get("kp_ids"):
        question["kp_ids"] = check["kp_ids"]
    if check.get("kp_id"):
        question["kp_id"] = check["kp_id"]
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
        "hint": "已写入草稿，请教师确认后再发布进正式题库。不要说已经加入正式题库。",
        "payload": question,
        **saved,
    }
