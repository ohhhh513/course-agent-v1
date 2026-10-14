"""管理员「账号删除」工具（平台治理流的第二个写入口，与账号录入对称）。

场景：管理员在智能助手里上传学生 / 教师名单（xlsx / docx / csv / txt）说「把这些账号删掉」，
或直接点名（「把 stu11、stu12 删掉」），助手据此生成**待批准动作**，
管理员点「确认执行」后才真正级联删除。

两个工具分工
------------
- `preview_account_delete`（只读）：把候选账号（本轮附件解析出的用户名，或点名给的用户名 /
  userId）在库里逐个核对，分成「可删」与「被拒并说明原因」两组，返回可删清单。不写任何数据。
- `delete_accounts`（写，挂 `ApprovalSpec`）：参数是 `preview` 给出的可删账号。
  被闸门拦下时排入「待批准」；只有管理员在确认卡片上点确认（approve 接口回放，
  带 `approval_replay` 标记）才真正执行 —— 执行时**重新核对一遍**（不信任前端、也防期间变化），
  逐行级联删除、被拒 / 失败的行进报告，不整体回滚（与批量删除同一语义）。

口径一致性：定位 / 保护规则 / 级联范围复用 `services.account_import`
（find_user / delete_block_reason / delete_user_cascade / DELETION_SCOPE），不写第二套实现。
"""
from __future__ import annotations

from app.agent_st import persistence
from app.agent_st.agent.context import ToolContext
from app.agent_st.agent.registry import ApprovalSpec, tool
from app.services.account_import import (DELETION_SCOPE, MAX_BATCH_DELETE,
                                         delete_user_cascade, find_user,
                                         resolve_for_delete)

_ADMIN_ROLES = ("admin",)
_FLOW = ("admin_ops",)


def _clean_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    return [str(x).strip() for x in value if str(x).strip()]


def _idents_from_args(args: dict) -> list[str]:
    """从工具入参收集候选标识：显式 usernames / userIds 优先（去重由服务层负责）。"""
    return _clean_list((args or {}).get("userIds")) + _clean_list((args or {}).get("usernames"))


def _idents_from_attachments(ctx: ToolContext) -> list[str]:
    """本轮附件（账号表）解析出的用户名 —— 复用 chat 端点预解析的 extra.account_import。"""
    imp = (ctx.extra or {}).get("account_import") or {}
    out: list[str] = []
    for f in (imp.get("files") or []):
        if not isinstance(f, dict):
            continue
        for r in (f.get("records") or []):
            if isinstance(r, dict):
                uname = str(r.get("username") or "").strip()
                if uname:
                    out.append(uname)
    return out


def _summarize(args: dict) -> str:
    rows = [a for a in ((args or {}).get("accounts") or []) if isinstance(a, dict)]
    names = [str(a.get("username") or a.get("userId") or "").strip() for a in rows]
    names = [n for n in names if n]
    head = "、".join(names[:3])
    if len(names) > 3:
        head += f" 等 {len(names)} 个"
    return f"批量删除 {len(rows)} 个账号：{head or '（无用户名）'}"


def _precheck(ctx: ToolContext, args: dict) -> list[str]:
    """写操作前置校验 —— 在**拦截那一刻**跑（审批回放时同轮内存已为空，不能依赖）。

    只做形状校验（是否为空 / 超限 / 有没有标识）；能不能删由执行时按库内真实状态判定 ——
    否则一个被保护的账号会把整批都挡下，而正确语义是「删掉能删的、其余进报告」。
    """
    rows = [a for a in ((args or {}).get("accounts") or []) if isinstance(a, dict)]
    errs: list[str] = []
    if not rows:
        errs.append("accounts 不能为空：请先调用 preview_account_delete 并传入其 deletableAccounts")
    if len(rows) > MAX_BATCH_DELETE:
        errs.append(f"单次最多删除 {MAX_BATCH_DELETE} 个账号，请分批处理")
    missing = [i + 1 for i, a in enumerate(rows)
               if not str(a.get("userId") or a.get("username") or "").strip()]
    if missing:
        errs.append("以下记录既没有 userId 也没有 username，无法定位账号：第 "
                    + "、".join(str(i) for i in missing[:10]) + " 条")
    return errs


@tool(
    name="preview_account_delete",
    description=(
        "核对**待删除账号**（只读，不写库）："
        "本轮附件里解析出的账号表，或你点名给的用户名 / userId，逐个在库里核对，"
        "返回可删清单 deletableAccounts 与不能删的 skippedRows（含原因）。"
        "当管理员要「删除 / 移除 / 清理账号」时先调用本工具；"
        "然后把 deletableAccounts **原样**传给 delete_accounts（不要自己改动）。"
        "若没有任何候选账号，会返回 error 提示。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "usernames": {
                "type": "array",
                "description": "（可选）要点名核对的用户名列表；不传则用本轮附件解析出的名单",
                "items": {"type": "string"},
            },
            "userIds": {
                "type": "array",
                "description": "（可选）用户 ID 列表（通常不需要，用户名即可）",
                "items": {"type": "string"},
            },
        },
    },
    flows=_FLOW,
    roles=_ADMIN_ROLES,
)
def preview_account_delete(ctx: ToolContext, usernames=None, userIds=None):
    explicit = _clean_list(userIds) + _clean_list(usernames)
    from_files = _idents_from_attachments(ctx)
    idents = explicit or from_files
    if not idents:
        return {"error": ("没有可核对的账号：请上传学生/教师名单（xlsx / docx / csv / txt），"
                          "或直接告诉我要删哪些用户名（例如「把 stu11、stu12 删掉」）")}

    source = "点名" if explicit else "本轮附件名单"
    db = persistence.SessionLocal()
    try:
        res = resolve_for_delete(db, idents, str(ctx.user_id or ""))
        return {
            "source": source,
            "checked": len(set(idents)),
            "counts": {"deletable": len(res["deletable"]), "skipped": len(res["skipped"])},
            "deletableAccounts": res["deletable"],
            "skippedRows": res["skipped"][:50],
            "scope": DELETION_SCOPE,
            "note": ("deletableAccounts 是当前可删的账号；被拒的行（管理员账号、你自己、"
                     "课程创建者、账号不存在）不要提交。提交前用一两句话向管理员确认这些账号确实要删。"),
            "basis": ("账号定位与保护规则和「账号管理 → 删除 / 批量删除」完全一致；"
                      "删除会级联清理其个人数据，不可撤销。"),
        }
    finally:
        db.close()


@tool(
    name="delete_accounts",
    description=(
        "把学生/教师账号**批量删除**（写操作：会先生成「待批准」确认卡片，"
        "管理员点确认后才真正删除，并级联清理其个人数据）。"
        "只传 preview_account_delete 返回的 deletableAccounts（原样，不要自己增删或改字段）。"
        "执行时会重新核对一遍：期间变得不可删（如成为课程 owner）或已不存在的行会被拒绝、"
        "在原报告里列出，不会整体回滚。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "accounts": {
                "type": "array",
                "description": "账号数组（来自 preview_account_delete 的 deletableAccounts）",
                "items": {
                    "type": "object",
                    "properties": {
                        "userId": {"type": "string", "description": "用户 ID"},
                        "username": {"type": "string", "description": "用户名"},
                    },
                },
            },
        },
        "required": ["accounts"],
    },
    flows=_FLOW,
    roles=_ADMIN_ROLES,
    # 写操作：必须由管理员在界面上点「确认执行」后才真正删库（P2c 审批闸门）
    approval=ApprovalSpec(
        summarize=_summarize,
        precheck=_precheck,
        impact=(DELETION_SCOPE + " 管理员账号、当前登录账号、课程创建者(owner)会被拒绝。"
                "**该操作不可撤销**，请核对清单后再确认。"),
    ),
)
def delete_accounts(ctx: ToolContext, accounts=None):
    rows = [a for a in (accounts or []) if isinstance(a, dict)]
    if not rows:
        return {"ok": False, "error": "accounts 不能为空"}
    if len(rows) > MAX_BATCH_DELETE:
        return {"ok": False, "error": f"单次最多删除 {MAX_BATCH_DELETE} 个账号，请分批处理"}

    idents: list[str] = []
    for a in rows:
        ident = str(a.get("userId") or a.get("username") or "").strip()
        if ident:
            idents.append(ident)
    if not idents:
        return {"ok": False, "error": "没有可定位的账号（每行需要 userId 或 username）"}

    db = persistence.SessionLocal()
    try:
        # 执行前重新核对一遍（不信任入参、也不信任审批前的那份状态）：
        # 期间库内可能已删掉、或该用户变成了课程 owner → 这里会正确判成不可删并列进 refused。
        res = resolve_for_delete(db, idents, str(ctx.user_id or ""))
        refused_rows = [{"username": s.get("username") or s.get("ident") or "",
                         "userId": s.get("userId") or "", "reason": s.get("reason") or ""}
                        for s in res["skipped"]]
        deleted = failed = 0
        deleted_users: list[str] = []
        failed_rows: list[dict] = []
        for row in res["deletable"]:
            user = None
            try:
                user = find_user(db, row["userId"])
                if user is None:                     # 竞态：核对后被别处删掉
                    refused_rows.append({"username": row.get("username") or "",
                                         "userId": row.get("userId") or "", "reason": "账号不存在"})
                    continue
                from app.services.chat_attachments import delete_chat_attachments, user_session_attachment_ids

                attachment_ids = user_session_attachment_ids(db, user.user_id)
                delete_user_cascade(db, user)
                db.commit()
                delete_chat_attachments(attachment_ids)
                deleted += 1
                deleted_users.append(row.get("username") or row.get("userId") or "")
            except Exception as e:  # noqa: BLE001 —— 单行失败不阻塞其余行
                db.rollback()
                failed += 1
                failed_rows.append({"username": row.get("username") or "",
                                    "userId": row.get("userId") or "", "reason": str(e)})
        return {
            "ok": True,
            "deleted": deleted,
            "refused": len(refused_rows),
            "failed": failed,
            "deletedUsers": deleted_users,
            "refusedRows": refused_rows[:20],
            "failedRows": failed_rows[:20],
            "scope": DELETION_SCOPE,
            "hint": ("账号已从 users 表删除并级联清理其个人数据；"
                     "请如实向管理员汇报成功 / 被拒 / 失败的数量与原因，不要夸大，"
                     "也不要声称删掉了未成功的行。"),
        }
    finally:
        db.close()
