"""系统管理员的平台治理**只读查询**工具（管理员端智能体）。
（同流的写操作在 `admin_import.py` / `admin_delete.py`，都挂审批闸门。）

设计原则
--------
- **系统级作用域**：这些工具**不吃 `courseId`** —— 管理员的视角是全平台，
  不应该被"必须先加入某门课程"挡住（`get_current_course_id` 对未加课的用户会直接 400）。
  需要针对某门课的治理查询用**显式参数** `course_id`，并在工具内校验课程确实存在。
- **全部实时 COUNT**：不读 `courses` 表那几个冗余统计列 —— 实测它们已经漂移
  （`courses.questions = 228`，而 `questions` 实表 229 条），一律查真实业务表。
  冗余列只在 `data_check` 里作为「对账对象」出现。
- **复用现成实现**：运行模式 / 模型信息复用 `/agent/status` 那套
  （`chat_available()` + `settings`），知识库统计直接用 `ChunkStore` 的
  `course_counts` / `source_counts` / `kp_coverage` / `embedding_model_counts` / `stale_chunks`，
  不新写统计口径。
- **只读**：本模块这五个查询工具都不写库；账号录入 / 删除是同流的另外两个模块（写操作，走审批闸门）。
- **结果截断**：清单类返回都在工具内强制截断，不指望模型自己克制。
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import exists, func

from app.agent_st import persistence
from app.agent_st.agent.context import ToolContext
from app.agent_st.agent.registry import tool
from app.utils import fmt_dt, loads

# 管理员专用：教师/学生都拿不到（registry 按 roles 过滤，execute 再校验一次）
_ADMIN_ROLES = ("admin",)
_FLOW = ("admin_ops",)

_MAX_COURSES = 50      # 课程总览最多列出的课程数
_MAX_LIST = 50         # 各类清单返回条数上限
_MAX_KP = 40           # 知识点覆盖面最多列出的知识点数
_ACTIVE_DAYS = 7       # 「活跃」= 近 N 天有练习作答


def _clamp(value, low: int, high: int, default: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = default
    return max(low, min(high, n))


def _count(db, model, *criteria) -> int:
    """真实表计数（不经任何冗余列）。"""
    q = db.query(func.count()).select_from(model)
    if criteria:
        q = q.filter(*criteria)
    return int(q.scalar() or 0)


def _group_count(db, column, *criteria) -> dict:
    """按某列分组计数 → {值: 条数}（空值统一记成空串）；criteria 与主查询同口径过滤。"""
    q = db.query(column, func.count()).group_by(column)
    if criteria:
        q = q.filter(*criteria)
    rows = q.all()
    return {(str(k) if k is not None else ""): int(n) for k, n in rows}


def _course_exists(db, course_id: str) -> bool:
    return bool(db.query(persistence.Course.course_id)
                .filter(persistence.Course.course_id == course_id).first())


def _course_ids(db) -> list[str]:
    return [c.course_id for c in db.query(persistence.Course).order_by(persistence.Course.course_id).all()]


_REDUNDANT_NOTE = (
    "课程规模一律按真实业务表实时统计（questions / resources / kp_details），"
    "不使用 courses 表里的冗余统计列 —— 那几列会随增删题漂移。"
)


@tool(
    name="system_overview",
    description=(
        "查看**整个平台**的运行总览（不针对某一门课程）：账号与课程规模、题库/资源/答题/预警/"
        "会话/报告/草稿的数量、智能体当前的运行模式（live 还是 demo）与模型、知识库索引切片总数。"
        "管理员问「系统现在什么状态」「平台一共有多少数据」「现在是演示模式还是真实模式」"
        "「知识库索引有多大」时，先调用它。"
    ),
    parameters={"type": "object", "properties": {}},
    flows=_FLOW,
    roles=_ADMIN_ROLES,
)
def system_overview(ctx: ToolContext):
    db = persistence.SessionLocal()
    try:
        P = persistence

        accounts = {
            "total": _count(db, P.User),
            "byRole": _group_count(db, P.User.role),
        }
        memberships = {
            "total": _count(db, P.UserCourse),
            "byRoleInCourse": _group_count(db, P.UserCourse.role_in_course),
            "courses": _count(db, P.Course),
        }
        content = {
            "questions": _count(db, P.Question),
            "resources": _count(db, P.Resource),
            "knowledgePoints": _count(db, P.KpDetail),
            "chapters": int(
                db.query(func.count(func.distinct(P.Question.chapter_id)))
                .filter(P.Question.chapter_id != "").scalar() or 0
            ),
        }
        learning = {
            "answerRecords": _count(db, P.AnswerRecord),
            "alerts": _count(db, P.Alert),
            "learningPaths": _count(db, P.LearningPath),
        }
        agent = {
            "sessions": _count(db, P.ChatSession),
            "messages": _count(db, P.ChatMessage),
            "drafts": _count(db, P.STQuestionDraft),
            "reports": _count(db, P.Report),
            "notifications": _count(db, P.Message),
        }

        # 运行模式 / 模型：与 /agent/status 同源
        from app.agent_st.agent.llm import chat_available
        from app.agent_st.rag.embed import active_model_name
        from app.config import settings

        live = chat_available()
        runtime = {
            "mode": "live" if live else "demo",
            "model": settings.LLM_MODEL,
            "embeddingModel": active_model_name(),
            "hint": "" if live else "未配置 LLM_API_KEY，当前为演示模式（真实检索、无生成）",
        }

        # 知识库索引：直接用 ChunkStore，不新写统计
        from app.agent_st.rag.store import ChunkStore

        chunk_store = ChunkStore()
        chunks_by_course = chunk_store.course_counts()
        rag = {
            "totalChunks": sum(chunks_by_course.values()),
            "byCourse": chunks_by_course,
        }

        return {
            "accounts": accounts,
            "memberships": memberships,
            "content": content,
            "learning": learning,
            "agent": agent,
            "runtime": runtime,
            "rag": rag,
            "basis": (
                "全部为真实业务表的实时计数（users / courses / user_courses / questions / resources / "
                "kp_details / answer_records / alerts / chat_sessions / chat_messages / st_question_drafts / "
                "reports / messages）；运行模式与模型来自服务端配置；切片数来自 RAG 索引库。"
            ),
        }
    finally:
        db.close()


@tool(
    name="account_overview",
    description=(
        "查看**账号治理**情况：账号按角色/部门分布、**没有加入任何课程的账号**、"
        "**从来没有过练习作答的学生**（僵尸账号）、教师各自的授课课程数、最近新增的账号。"
        "管理员问「有多少账号」「哪些账号没分配课程」「哪些学生一直没练习」时调用它。"
        "可选 `role` 只看教师或学生（teacher / student），`limit` 控制各类清单条数。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "role": {"type": "string", "description": "只看某个角色：teacher / student；留空看全部"},
            "limit": {"type": "integer", "description": "各类清单返回条数上限，默认 20（最多 50）"},
        },
    },
    flows=_FLOW,
    roles=_ADMIN_ROLES,
)
def account_overview(ctx: ToolContext, role: str = "", limit: int = 20):
    top = _clamp(limit, 1, _MAX_LIST, 20)
    role = (role or "").strip().lower()
    db = persistence.SessionLocal()
    try:
        P = persistence
        only = []
        if role in ("teacher", "student"):
            only.append(P.User.role == role)

        accounts = _count(db, P.User, P.User.role != "admin", *only)

        def _rows(model_q, cap=top):
            # SQLAlchemy 2.0 的 Row 不是 (key, value) 序列，必须走 _mapping 才能转 dict
            return [dict(r._mapping) for r in (model_q.limit(cap).all() if cap else [])]

        # 没加入任何课程的账号（admin 自身不算）
        no_course = _rows(
            db.query(P.User.user_id.label("userId"), P.User.username.label("username"),
                     P.User.name.label("name"), P.User.role.label("role"))
            .filter(P.User.role != "admin", *only)
            .filter(~exists().where(P.UserCourse.user_id == P.User.user_id))
            .order_by(P.User.user_id.asc())
        )

        # 从来没有过练习作答的学生
        no_answers = _rows(
            db.query(P.User.user_id.label("userId"), P.User.username.label("username"),
                     P.User.name.label("name"), P.User.class_name.label("className"))
            .filter(P.User.role == "student")
            .filter(~exists().where(P.AnswerRecord.user_id == P.User.user_id))
            .order_by(P.User.user_id.asc())
        )

        # 教师 → 授课课程数（按课程成员关系，不是 classes 维）
        teacher_rows = db.query(
            P.User.user_id, P.User.username, P.User.name,
            func.count(P.UserCourse.course_id),
        ).outerjoin(
            P.UserCourse, P.UserCourse.user_id == P.User.user_id,
        ).filter(P.User.role == "teacher").group_by(
            P.User.user_id, P.User.username, P.User.name,
        ).all()
        teachers = [
            {"userId": uid, "username": un, "name": nm, "courseCount": int(n)}
            for uid, un, nm, n in teacher_rows
        ]

        recent = _rows(
            db.query(P.User.user_id.label("userId"), P.User.username.label("username"),
                     P.User.name.label("name"), P.User.role.label("role"),
                     P.User.created_at.label("createdAt"))
            .filter(P.User.role != "admin", *only)
            .order_by(P.User.created_at.desc())
        , cap=5)
        for r in recent:
            r["createdAt"] = fmt_dt(r.get("createdAt"))

        by_dept = _group_count(db, P.User.dept, *only)
        by_dept = {("(未填写)" if k == "" else k): v for k, v in by_dept.items()}

        return {
            "total": accounts,
            "byRole": _group_count(db, P.User.role, *only),
            "byDept": by_dept,
            "noCourseCount": _count(
                db, P.User, P.User.role != "admin", *only,
                ~exists().where(P.UserCourse.user_id == P.User.user_id),
            ),
            "noCourse": no_course,
            "noAnswerStudentCount": _count(
                db, P.User, P.User.role == "student",
                ~exists().where(P.AnswerRecord.user_id == P.User.user_id),
            ),
            "noAnswerStudents": no_answers,
            "teachers": teachers,
            "recentAccounts": recent,
            "truncated": any(len(x) >= top for x in (no_course, no_answers)) or len(teachers) >= top,
            "basis": (
                "账号来自 users 表；「没有课程」按 user_courses 成员关系判断；"
                "「没作答」按 answer_records 是否存在该学生的记录判断。"
                "users 表没有启用状态 / 最后登录字段，所以这两条是当前唯一可判定的失活信号。"
            ),
        }
    finally:
        db.close()


@tool(
    name="course_overview",
    description=(
        "查看**课程规模与活跃度**：每门课的教师/学生人数、题目 / 资源 / 知识点 / 章节数、"
        "答题记录数、近 7 天活跃学生数、最近一次作答时间、课程创建者。"
        "管理员问「一共几门课」「这门课有多少数据」「哪门课最近没人用」时调用它。"
        "可传 `course_id` 只看某一门课；留空则列出全部课程。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "course_id": {"type": "string", "description": "课程 ID（如 CCHYJTKE）；留空则列出全部课程"},
        },
    },
    flows=_FLOW,
    roles=_ADMIN_ROLES,
)
def course_overview(ctx: ToolContext, course_id: str = ""):
    cid = (course_id or "").strip()
    db = persistence.SessionLocal()
    try:
        P = persistence
        if cid and not _course_exists(db, cid):
            return {"error": f"课程 {cid} 不存在"}

        q = db.query(P.Course)
        if cid:
            q = q.filter(P.Course.course_id == cid)
        courses = q.order_by(P.Course.course_id).limit(_MAX_COURSES).all()

        since = datetime.utcnow() - timedelta(days=_ACTIVE_DAYS)
        items = []
        for c in courses:
            member_rows = db.query(
                P.UserCourse.role_in_course, func.count(),
            ).filter(P.UserCourse.course_id == c.course_id).group_by(P.UserCourse.role_in_course).all()
            members = {(r or ""): int(n) for r, n in member_rows}

            last_answer = db.query(func.max(P.AnswerRecord.created_at)).filter(
                P.AnswerRecord.course_id == c.course_id,
            ).scalar()
            active = int(db.query(func.count(func.distinct(P.AnswerRecord.user_id))).filter(
                P.AnswerRecord.course_id == c.course_id,
                P.AnswerRecord.created_at >= since,
            ).scalar() or 0)

            owner = db.query(P.User.name).filter(P.User.user_id == c.owner_id).scalar() if c.owner_id else None

            items.append({
                "courseId": c.course_id,
                "name": c.name,
                "term": c.term or "",
                "inviteCode": c.invite_code or "",
                "owner": c.owner_id or "",
                "ownerName": owner or "",
                "members": {
                    "teachers": members.get("teacher", 0),
                    "students": members.get("student", 0),
                    "total": sum(members.values()),
                },
                "content": {
                    "questions": _count(db, P.Question, P.Question.course_id == c.course_id),
                    "resources": _count(db, P.Resource, P.Resource.course_id == c.course_id),
                    "knowledgePoints": _count(db, P.KpDetail, P.KpDetail.course_id == c.course_id),
                    "chapters": int(
                        db.query(func.count(func.distinct(P.Question.chapter_id))).filter(
                            P.Question.course_id == c.course_id, P.Question.chapter_id != "",
                        ).scalar() or 0
                    ),
                },
                "learning": {
                    "answerRecords": _count(db, P.AnswerRecord, P.AnswerRecord.course_id == c.course_id),
                    "alerts": _count(db, P.Alert, P.Alert.course_id == c.course_id),
                    "activeStudents": active,
                    "activeBasis": f"近 {_ACTIVE_DAYS} 天内有练习作答记录的学生数",
                    "lastAnswerAt": fmt_dt(last_answer) if last_answer else "",
                },
            })

        return {
            "total": len(items),
            "courses": items,
            "truncated": len(items) >= _MAX_COURSES,
            "basis": _REDUNDANT_NOTE + "「活跃」按 answer_records 的作答时间判断，成员按 user_courses 成员关系。",
        }
    finally:
        db.close()


@tool(
    name="kb_status",
    description=(
        "查看**知识库（RAG）索引状态**：各课程切片数、切片来源分布、知识点覆盖、"
        "embedding 模型分布，以及**哪些切片是用旧 embedding 模型生成的（需要重建索引）**。"
        "管理员问「知识库索引情况」「要不要重建索引」「某个课程的资料入库了没有」时调用它。"
        "可传 `course_id` 看单门课的明细；留空看各课程汇总。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "course_id": {"type": "string", "description": "课程 ID；留空则给出各课程汇总"},
        },
    },
    flows=_FLOW,
    roles=_ADMIN_ROLES,
)
def kb_status(ctx: ToolContext, course_id: str = ""):
    cid = (course_id or "").strip()
    db = persistence.SessionLocal()
    try:
        if cid and not _course_exists(db, cid):
            return {"error": f"课程 {cid} 不存在"}

        from app.agent_st.rag.embed import active_model_name
        from app.agent_st.rag.store import ChunkStore

        chunk_store = ChunkStore()
        active = active_model_name()
        by_course = chunk_store.course_counts()

        out = {
            "activeEmbeddingModel": active,
            "totalChunks": sum(by_course.values()),
            "byCourse": by_course,
        }

        if cid:
            by_source = chunk_store.source_counts(cid)
            kp_cov = chunk_store.kp_coverage(cid)
            by_model = chunk_store.embedding_model_counts(cid)
            stale = chunk_store.stale_chunks(active, cid)
            out.update({
                "courseId": cid,
                "chunks": by_course.get(cid, 0),
                "bySource": dict(list(by_source.items())[:20]),
                "kpCoverage": dict(list(sorted(kp_cov.items()))[:_MAX_KP]),
                "kpCoveredCount": len(kp_cov),
                "byEmbeddingModel": by_model,
                "staleChunkCount": len(stale),
                "needRebuild": bool(stale),
            })
        else:
            stale_all = chunk_store.stale_chunks(active)
            stale_by_course: dict[str, int] = {}
            for item in stale_all:
                key = item[0] if isinstance(item, (list, tuple)) and item else str(item)
                stale_by_course[key] = stale_by_course.get(key, 0) + 1
            out.update({
                "staleChunkCount": len(stale_all),
                "staleByCourse": stale_by_course,
                "needRebuildCourses": sorted(stale_by_course),
            })

        out["basis"] = (
            f"切片数来自 RAG 索引库；「旧模型切片」= 生成时用的 embedding 模型不是当前生效的 {active}，"
            "重建索引可消除。"
        )
        return out
    finally:
        db.close()


@tool(
    name="data_check",
    description=(
        "对**全平台数据做一次一致性体检**（只读）：课程冗余统计列与实表是否一致、"
        "课程成员/创建者是否指向不存在的账号、学生是否缺学号或班级、"
        "答题记录与预警是否有孤儿数据、学情报告是否缺少课程标记。"
        "管理员问「数据有没有问题」「有什么脏数据」「帮我体检一下」时调用它。"
    ),
    parameters={"type": "object", "properties": {}},
    flows=_FLOW,
    roles=_ADMIN_ROLES,
)
def data_check(ctx: ToolContext):
    db = persistence.SessionLocal()
    try:
        P = persistence
        checks: list[dict] = []

        # ① 课程冗余统计列 vs 实表（幂等对账；实测 questions 列曾漂移）
        drifted = []
        for c in db.query(P.Course).order_by(P.Course.course_id).all():
            real = {
                "questions": _count(db, P.Question, P.Question.course_id == c.course_id),
                "resources": _count(db, P.Resource, P.Resource.course_id == c.course_id),
            }
            declared = {
                "questions": int(c.questions or 0),
                "resources": int(c.resources or 0),
            }
            for key, actual in real.items():
                if int(declared.get(key) or 0) != actual:
                    drifted.append({
                        "courseId": c.course_id, "field": key,
                        "declared": int(declared.get(key) or 0), "actual": actual,
                    })
        checks.append({
            "name": "课程冗余统计列与实表一致",
            "ok": not drifted,
            "detail": "courses 表的 questions / resources 列与真实表条数不一致（该列仅用于展示，业务查询已改用实表）",
            "items": drifted[:20],
        })

        # ② 课程成员指向不存在的账号
        known_users = db.query(P.User.user_id).subquery()
        orphan_members = [
            {"userId": uid, "courseId": cid}
            for uid, cid in db.query(P.UserCourse.user_id, P.UserCourse.course_id)
            .outerjoin(known_users, known_users.c.user_id == P.UserCourse.user_id)
            .filter(known_users.c.user_id.is_(None)).limit(20).all()
        ]
        checks.append({
            "name": "课程成员都指向真实账号",
            "ok": not orphan_members,
            "detail": "user_courses 里有指向已不存在账号的成员关系（会导致课程人数虚高）",
            "items": orphan_members,
        })

        # ③ 课程创建者缺失 / 不在成员里
        #    注意（2026-10-26）：「无成员的课」按新口径本来就该是无负责人状态
        #    （退绑到 0 人时 owner_id 会被清空），不算异常；
        #    只有「有成员却没有有效负责人」才是真问题。
        owner_issues = []
        for c in db.query(P.Course).all():
            member_ids = [
                uid for (uid,) in db.query(P.UserCourse.user_id)
                .filter(P.UserCourse.course_id == c.course_id).all()
            ]
            if not member_ids:
                continue          # 无成员 = 无负责人，属正常状态
            if not (c.owner_id or "").strip():
                owner_issues.append({"courseId": c.course_id, "issue": "课程有成员但未设置负责人 owner_id"})
                continue
            if c.owner_id not in member_ids:
                owner_issues.append({"courseId": c.course_id, "ownerId": c.owner_id,
                                     "issue": "负责人不是该课程成员"})
        checks.append({
            "name": "课程负责人有效",
            "ok": not owner_issues,
            "detail": "课程有成员时，负责人应存在且是课程成员（无成员的课不要求负责人）",
            "items": owner_issues[:20],
        })

        # ④ 学生缺学号 / 班级
        missing_students = [
            {"userId": uid, "username": un, "name": nm,
             "missing": [k for k, v in (("studentNo", no), ("className", cn)) if not (v or "").strip()]}
            for uid, un, nm, no, cn in db.query(
                P.User.user_id, P.User.username, P.User.name, P.User.student_no, P.User.class_name,
            ).filter(P.User.role == "student").all()
            if not (no or "").strip() or not (cn or "").strip()
        ]
        checks.append({
            "name": "学生学号与班级完整",
            "ok": not missing_students,
            "detail": "学生缺 student_no 或 class_name（导出名单、按班筛选会缺失）",
            "items": missing_students[:20],
        })

        # ⑤ 孤儿答题记录 / 预警（指向不存在的课程或题）
        known_courses = db.query(P.Course.course_id).subquery()
        orphan_answers = int(db.query(func.count()).select_from(P.AnswerRecord)
                             .outerjoin(known_courses, known_courses.c.course_id == P.AnswerRecord.course_id)
                             .filter(known_courses.c.course_id.is_(None)).scalar() or 0)
        known_questions = db.query(P.Question.q_id).subquery()
        orphan_answers += int(db.query(func.count()).select_from(P.AnswerRecord)
                              .outerjoin(known_questions, known_questions.c.q_id == P.AnswerRecord.q_id)
                              .filter(known_questions.c.q_id.is_(None)).scalar() or 0)
        orphan_alerts = int(db.query(func.count()).select_from(P.Alert)
                            .outerjoin(known_courses, known_courses.c.course_id == P.Alert.course_id)
                            .filter(known_courses.c.course_id.is_(None)).scalar() or 0)
        checks.append({
            "name": "答题记录 / 预警无孤儿数据",
            "ok": (orphan_answers == 0 and orphan_alerts == 0),
            "detail": "存在指向不存在课程或题目的答题记录 / 预警",
            "items": [{"orphanAnswerRecords": orphan_answers, "orphanAlerts": orphan_alerts}]
            if (orphan_answers or orphan_alerts) else [],
        })

        # ⑥ 学情报告缺课程标记（教师报告归档按 detail_json.meta.courseId 过滤，缺了会永远看不到）
        no_meta = 0
        for (detail_json,) in db.query(P.Report.detail_json).all():
            meta = (loads(detail_json) or {}).get("meta") or {}
            if not str(meta.get("courseId") or "").strip():
                no_meta += 1
        checks.append({
            "name": "学情报告都带课程标记",
            "ok": no_meta == 0,
            "detail": "reports.detail_json.meta 缺 courseId（教师端报告归档按它过滤，缺了不会显示）",
            "items": [{"reportsWithoutCourse": no_meta}] if no_meta else [],
        })

        issues = [c for c in checks if not c["ok"]]
        return {
            "checked": len(checks),
            "issueCount": len(issues),
            "checks": checks,
            "conclusion": "全部通过" if not issues else f"{len(issues)} 项需要处理：" + "、".join(c["name"] for c in issues),
            "basis": "全部为只读一致性检查，不改动任何数据；判据是主外键关系与既有字段口径，不含业务规则推断。",
        }
    finally:
        db.close()
