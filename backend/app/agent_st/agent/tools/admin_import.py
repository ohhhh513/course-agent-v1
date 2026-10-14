"""管理员「账号批量录入」工具（平台治理流的写入口之一，另一个是 `admin_delete.py` 的删号）。

场景：管理员在智能助手里上传学生 / 教师信息文件（xlsx / docx / csv / txt），
说一句「把这些账号录入系统」，助手据此生成**待批准动作**，管理员点「确认执行」后落库。

两个工具分工
------------
- `preview_account_import`（只读）：读取本轮附件在服务端已完成的结构化解析结果
  （`ctx.extra['account_import']`，由 /admin/agent/chat/stream 预解析），
  再用**与批量导入向导同一套** `validate_records` 逐行校验（valid / dup / error），
  返回可直接提交的 `validAccounts` 与需跳过的行。不写任何数据。
- `import_accounts`（写，挂 `ApprovalSpec`）：参数是 `preview` 给出的记录。
  被闸门拦下时排入「待批准」；只有管理员在确认卡片上点确认（approve 接口回放，
  带 `approval_replay` 标记）才真正执行 —— 执行时**重新校验一遍**（不信任前端），
  有效行落库、重名跳过、失败行进报告，不整体回滚（与向导 commit 同一语义）。

口径一致性：解析 / 校验 / 落库复用 `services.account_import`，不写第二套实现。
"""
from __future__ import annotations

from app.agent_st import persistence
from app.agent_st.agent.context import ToolContext
from app.agent_st.agent.registry import ApprovalSpec, tool
from app.services.account_import import MAX_ASSIST_ROWS, insert_user, validate_records

_ADMIN_ROLES = ("admin",)
_FLOW = ("admin_ops",)

_ROLE_LABEL = {"student": "学生", "teacher": "教师"}
_FIELDS = ("username", "name", "password", "className", "studentNo", "dept", "title")


def _norm_account(row: dict) -> dict:
    """模型传来的行 → 规范化记录（只保留已知字段，去空白）。"""
    return {f: str((row or {}).get(f) or "").strip() for f in _FIELDS}


def _summarize(args: dict) -> str:
    role = str((args or {}).get("role") or "").strip().lower()
    label = _ROLE_LABEL.get(role, role or "？")
    rows = [a for a in ((args or {}).get("accounts") or []) if isinstance(a, dict)]
    names = [str(a.get("username") or "").strip() for a in rows]
    names = [n for n in names if n]
    head = "、".join(names[:3])
    if len(names) > 3:
        head += f" 等 {len(names)} 个"
    return f"批量创建 {len(rows)} 个{label}账号：{head or '（无用户名）'}"


def _precheck(ctx: ToolContext, args: dict) -> list[str]:
    """写操作前置校验 —— 在**拦截那一刻**跑（审批回放时同轮内存已为空，不能依赖）。"""
    role = str((args or {}).get("role") or "").strip().lower()
    rows = [a for a in ((args or {}).get("accounts") or []) if isinstance(a, dict)]
    errs: list[str] = []
    if role not in _ROLE_LABEL:
        errs.append("role 必须是 student 或 teacher")
    if not rows:
        errs.append("accounts 不能为空：请先调用 preview_account_import 并传入其 validAccounts")
    if len(rows) > MAX_ASSIST_ROWS:
        errs.append(f"单次最多录入 {MAX_ASSIST_ROWS} 个账号，请分批处理")
    bad = []
    for i, a in enumerate(rows):
        rec = _norm_account(a)
        if not rec["username"] or not rec["name"] or len(rec["password"]) < 6:
            bad.append(f"第 {i + 1} 行（{rec['username'] or '无用户名'}）缺用户名/姓名或密码不足 6 位")
    if bad:
        errs.append("以下记录不完整，请只传 preview_account_import 返回的 status=valid 记录："
                    + "；".join(bad[:5]))
    return errs


@tool(
    name="preview_account_import",
    description=(
        "查看**本轮附件**里学生/教师账号表的解析与校验结果（只读，不写库）："
        "每行的 valid / dup（重名）/ error 状态、可直接提交的 validAccounts 数组。"
        "当管理员上传了学生或教师信息文件，并要「录入系统 / 导入账号 / 批量建号」时，先调用本工具；"
        "然后把某个文件的 validAccounts **原样**传给 import_accounts（不要自己改动字段）。"
        "若这轮没有可解析的账号文件，会返回 error。"
    ),
    parameters={"type": "object", "properties": {}},
    flows=_FLOW,
    roles=_ADMIN_ROLES,
)
def preview_account_import(ctx: ToolContext):
    imp = (ctx.extra or {}).get("account_import") or {}
    files = [f for f in (imp.get("files") or []) if isinstance(f, dict)]
    if not files:
        return {"error": "当前这轮没有可解析的学生/教师账号文件（请先上传 xlsx / docx / csv / txt 名单再试）"}

    db = persistence.SessionLocal()
    try:
        out = []
        for f in files:
            role = str(f.get("role") or "student").strip().lower()
            if role not in _ROLE_LABEL:
                role = "student"
            records = [dict(r) for r in (f.get("records") or [])]
            if not records:
                continue
            validate_records(records, role, "", db)
            valid = [r for r in records if r.get("status") == "valid"]
            skipped = [r for r in records if r.get("status") != "valid"]
            out.append({
                "name": f.get("name") or "文件",
                "role": role,
                "roleLabel": _ROLE_LABEL[role],
                "totalRows": f.get("totalRows") or len(records),
                "truncated": bool(f.get("truncated")),
                "counts": {
                    "total": len(records),
                    "valid": len(valid),
                    "dup": sum(1 for r in records if r.get("status") == "dup"),
                    "error": sum(1 for r in records if r.get("status") == "error"),
                },
                # 可直接透传给 import_accounts 的行（含密码字段，仅供服务端写库使用）
                "validAccounts": [{k: r.get(k) or "" for k in _FIELDS} for r in valid],
                "skippedRows": [
                    {"rowIndex": r.get("rowIndex"), "username": r.get("username") or "",
                     "name": r.get("name") or "", "status": r.get("status"), "error": r.get("error") or ""}
                    for r in skipped[:50]
                ],
            })
        if not out:
            return {"error": "附件里没有解析出有效的账号数据行"}
        return {
            "files": out,
            "note": ("validAccounts 是可直接提交的记录；重复（dup）与错误（error）行不要提交。"
                     "提交前用一两句话向管理员确认这些账号确实要录入。"),
            "basis": ("解析与校验口径与「账号管理 → 批量导入」完全一致（表头别名容错、"
                      "密码至少 6 位、文件内与库内重名会跳过）。"),
        }
    finally:
        db.close()


@tool(
    name="import_accounts",
    description=(
        "把学生/教师账号**批量录入系统**（写操作：会先生成「待批准」确认卡片，"
        "管理员点确认后才真正写入 users 表，随后可用初始密码登录）。"
        "只传 preview_account_import 返回的 validAccounts（原样，不要自己增删字段或改密码）。"
        "重复 / 错误行不要传入 —— 已存在的用户名执行时也会自动跳过、不覆盖原账号。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "role": {"type": "string", "description": "student（学生）或 teacher（教师）"},
            "accounts": {
                "type": "array",
                "description": "账号数组（来自 preview_account_import 的 validAccounts）",
                "items": {
                    "type": "object",
                    "properties": {
                        "username": {"type": "string", "description": "用户名（登录名）"},
                        "name": {"type": "string", "description": "姓名"},
                        "password": {"type": "string", "description": "初始密码（至少 6 位）"},
                        "className": {"type": "string", "description": "班级（学生）"},
                        "studentNo": {"type": "string", "description": "学号（学生）"},
                        "dept": {"type": "string", "description": "部门/院系（教师）"},
                        "title": {"type": "string", "description": "职称（教师）"},
                    },
                },
            },
        },
        "required": ["role", "accounts"],
    },
    flows=_FLOW,
    roles=_ADMIN_ROLES,
    # 写操作：必须由管理员在界面上点「确认执行」后才真正落库（P2c 审批闸门）
    approval=ApprovalSpec(
        summarize=_summarize,
        precheck=_precheck,
        impact=("在 users 表新增账号并立即生效（可用初始密码登录）；用户名已存在的行会跳过、"
                "不覆盖原账号。请先核对名单与角色后再确认。"),
    ),
)
def import_accounts(ctx: ToolContext, role: str = "", accounts=None):
    role = (role or "").strip().lower()
    if role not in _ROLE_LABEL:
        return {"ok": False, "error": "role 只能是 student 或 teacher"}
    rows = [a for a in (accounts or []) if isinstance(a, dict)]
    if not rows:
        return {"ok": False, "error": "accounts 不能为空"}
    if len(rows) > MAX_ASSIST_ROWS:
        return {"ok": False, "error": f"单次最多录入 {MAX_ASSIST_ROWS} 个账号，请分批处理"}

    db = persistence.SessionLocal()
    try:
        # 执行前重新校验一遍（不信任入参、也不信任审批前的那份状态）：
        # 期间库内可能已新增同名账号 → 这里会正确判成 dup 并跳过。
        records = []
        for i, a in enumerate(rows):
            rec = _norm_account(a)
            rec["rowIndex"] = i + 1
            records.append(rec)
        validate_records(records, role, "", db)

        created = skipped = failed = 0
        created_users: list[str] = []
        skipped_rows: list[dict] = []
        failed_rows: list[dict] = []
        for r in records:
            if r["status"] != "valid":
                skipped += 1
                skipped_rows.append({"rowIndex": r["rowIndex"], "username": r["username"],
                                     "reason": r["error"] or r["status"]})
                continue
            try:
                uid = insert_user(db, role, r["username"], r["name"], r["password"],
                                  r["className"], r["studentNo"], r["dept"], r["title"])
                db.commit()
                created += 1
                created_users.append(r["username"])
            except Exception as e:  # noqa: BLE001 —— 单行失败不阻塞其余行
                db.rollback()
                failed += 1
                failed_rows.append({"rowIndex": r["rowIndex"], "username": r["username"], "reason": str(e)})
        return {
            "ok": True,
            "role": role,
            "created": created,
            "skipped": skipped,
            "failed": failed,
            "createdUsers": created_users,
            "skippedRows": skipped_rows[:20],
            "failedRows": failed_rows[:20],
            "hint": ("账号已写入 users 表：请如实向管理员汇报成功 / 跳过 / 失败的数量，"
                     "不要夸大，也不要声称完成了未创建的行。"),
        }
    finally:
        db.close()
