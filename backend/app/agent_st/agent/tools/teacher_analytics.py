"""教师视角的学情只读工具（P2b）。

设计原则
--------
- **课程由服务端注入**：一律从 `ctx.extra['courseId']` 取，工具签名里没有 course_id / user_id，
  模型无法指定别的课程（越权在参数层面就不成立）。
- **隐私边界**：任何按学生取数的工具，先校验「该学生在当前课程内」
  （`services.kp_stats.course_student_ids`，名单来自 user_courses 成员关系）；
  不属于本课程时返回明确错误，且**错误信息不回显该生姓名 / 学号**。
- **复用业务口径**：正确率走 `services/scoring`（按题去重取最近一次；主 KP 权重 1.0 / 标签 0.3），
  掌握率走 `services/kp_stats.mastery_by_kp`，预警门槛复用 `services/alert_detector` 的常量。
  工具本身不实现统计口径。
- **只读**：这些工具都不写库。提问热点只聚合已有 tool_log，不把学生私聊全文返回。
- **结果截断**：全班规模不可控，`class_alerts` / `kp_heatmap` / `hot_wrong_questions`
  都在工具里强制截断 —— 不指望模型自己克制。
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func

from app.agent_st import persistence
from app.agent_st.agent.context import ToolContext
from app.agent_st.agent.registry import tool
from app.utils import fmt_dt

# 教师专用：学生与管理员都不能调（registry 会按 roles 过滤，execute 再校验一次）。
# 2026-10-06 收紧：管理员改用「平台治理」工具（flow=admin_ops，见 tools/admin_ops.py），
# 不再共享班级学情视角 —— 管理员的职责边界是平台治理，不是某一门课的教学。
_TEACHER_ROLES = ("teacher",)
_FLOW = ("explain",)

_ACTIVE_DAYS = 7          # 「活跃」= 近 N 天有练习作答
_MAX_STUDENTS = 80        # 矩阵最多展示的学生数（超过则截断并标注）
_EPOCH = datetime(2020, 1, 1)


def _course_id(ctx: ToolContext) -> str:
    return str((ctx.extra or {}).get("courseId") or ctx.store.course_id or "").strip()


def _clamp(value, low: int, high: int, default: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = default
    return max(low, min(high, n))


def _students(db, course_id: str) -> list[str]:
    """课程内学生 user_id 列表（唯一口径：user_courses 成员关系）。"""
    from app.services.kp_stats import course_student_ids

    return course_student_ids(db, course_id)


def _student_names(db, uids: list[str]) -> dict:
    """user_id → (姓名, 学号)。只用于**已确认属于本课程**的 id。"""
    ids = [u for u in (uids or []) if u]
    if not ids:
        return {}
    rows = db.query(
        persistence.User.user_id, persistence.User.name, persistence.User.student_no,
    ).filter(persistence.User.user_id.in_(ids)).all()
    return {uid: (name or uid, no or "") for uid, name, no in rows}


def _overall_accuracy(acc_map: dict) -> float | None:
    """把「每知识点 (正确率%, 不同题数)」汇总成该生的整体答题正确率（按题数加权）。

    权重用「不同题数」而不是知识点个数：题做得多的知识点更能代表该生的真实水平。
    """
    total = sum(hits for _rate, hits in acc_map.values())
    if not total:
        return None
    return round(sum(rate * hits for rate, hits in acc_map.values()) / total, 1)


_ACCURACY_BASIS = (
    "正确率口径与预警/学情页一致：每道题只取最近一次作答，主知识点权重 1.0、"
    "标签命中的其它知识点权重 0.3；此处按题数加权汇总为个人整体正确率。"
)


def _question_count(db, course_id: str, kp_id: str) -> int:
    """已发布、且主知识点或标签命中该点的题数。口径与练习组卷一致。"""
    from app.services.catalog_helpers import question_kp_clause

    clause = question_kp_clause(persistence.Question, [kp_id])
    if clause is None:
        return 0
    return int(db.query(persistence.Question).filter(
        persistence.Question.course_id == course_id,
        persistence.Question.status == "published",
        clause,
    ).count())


def _suggest_items(rate, question_count: int) -> dict:
    """备课用的出题建议。只根据班级正确率和已有题量，不代替教师点生成。"""
    if question_count <= 0:
        return {"count": 3, "type": "单选题",
                "reason": "这个知识点还没有已发布的题"}
    if rate is None:
        return {"count": 2, "type": "单选题",
                "reason": "还没有学生作答，先备少量基础单选"}
    if rate < 60:
        return {"count": 3, "type": "单选题",
                "reason": "班级正确率低于 60%，适合再出几道单选"}
    return {"count": 2, "type": "单选题",
            "reason": "班级正确率已达到 60%，少量巩固即可"}


def _kp_brief(db, course_id: str, kp_id: str, uids: list[str]) -> dict:
    """单个知识点的备课摘要：班正确率、资源数、题量、建议题量和题型。"""
    node = db.query(persistence.GraphNode).filter(
        persistence.GraphNode.id == kp_id,
        persistence.GraphNode.graph_type == "knowledge",
        persistence.GraphNode.course_id == course_id,
    ).first()
    if node is None:
        return {"error": f"知识点 {kp_id} 不属于当前课程"}

    from app.services.learning_path import resource_count_map
    from app.services.scoring import quiz_accuracy_by_kp

    rates = []
    for uid in uids:
        hit = quiz_accuracy_by_kp(db, uid).get(kp_id)
        if hit:
            rates.append(hit[0])
    avg = round(sum(rates) / len(rates), 1) if rates else None
    questions = _question_count(db, course_id, kp_id)
    return {
        "courseId": course_id,
        "kpId": node.id,
        "kpName": node.name,
        "chapter": node.chapter or "",
        "accuracy": avg,
        "answeredStudents": len(rates),
        "studentCount": len(uids),
        "resourceCount": int(resource_count_map(db, course_id).get(kp_id, 0)),
        "questionCount": questions,
        "suggest": _suggest_items(avg, questions),
        "basis": _ACCURACY_BASIS,
        "note": "这是指定知识点的备课摘要，不含学生姓名。没有明确要求出题时不要打开出题页。",
    }


@tool(
    name="class_overview",
    description=(
        "查看**当前课程**全班的整体学情：学生人数、近 7 天活跃人数、"
        "班级平均答题正确率、红/黄预警数量。教师问「我班上整体情况怎么样」"
        "「谁最需要关注」之前，先调用它拿到全局数字，再决定要不要下钻。"
        "课程由服务端注入，不需要也不能指定课程 id。"
    ),
    parameters={"type": "object", "properties": {}},
    flows=_FLOW,
    roles=_TEACHER_ROLES,
)
def class_overview(ctx: ToolContext):
    course_id = _course_id(ctx)
    if not course_id:
        return {"error": "缺少课程上下文，无法统计班级学情"}
    db = persistence.SessionLocal()
    try:
        uids = _students(db, course_id)
        if not uids:
            return {"courseId": course_id, "studentCount": 0,
                    "note": "当前课程还没有学生成员"}

        from app.services.scoring import quiz_accuracy_by_kp

        since = datetime.utcnow() - timedelta(days=_ACTIVE_DAYS)
        active = db.query(func.count(func.distinct(persistence.AnswerRecord.user_id))).filter(
            persistence.AnswerRecord.user_id.in_(uids),
            persistence.AnswerRecord.created_at >= since,
        ).scalar() or 0
        last_answer = db.query(func.max(persistence.AnswerRecord.created_at)).filter(
            persistence.AnswerRecord.user_id.in_(uids),
        ).scalar()

        accs: list[float] = []
        for uid in uids:
            one = _overall_accuracy(quiz_accuracy_by_kp(db, uid))
            if one is not None:
                accs.append(one)

        alert_rows = db.query(
            persistence.Alert.level, func.count(persistence.Alert.alert_id),
        ).filter(
            persistence.Alert.course_id == course_id,
            persistence.Alert.status != "ignored",
            persistence.Alert.level.in_(("red", "yellow")),
        ).group_by(persistence.Alert.level).all()
        by_level = {level: int(n) for level, n in alert_rows}
        stu_with_alert = db.query(func.count(func.distinct(persistence.Alert.user_id))).filter(
            persistence.Alert.course_id == course_id,
            persistence.Alert.status != "ignored",
            persistence.Alert.level.in_(("red", "yellow")),
        ).scalar() or 0

        return {
            "courseId": course_id,
            "studentCount": len(uids),
            "activeStudents": int(active),
            "activeBasis": f"近 {_ACTIVE_DAYS} 天内有练习作答记录的学生数；"
                           "若某段时间没人练习，这里会是 0 —— 这是真实情况，不要编数字",
            "lastAnswerAt": fmt_dt(last_answer) if last_answer else "",
            "avgQuizAccuracy": round(sum(accs) / len(accs), 1) if accs else None,
            "studentsWithRecords": len(accs),
            "accuracyBasis": _ACCURACY_BASIS + "「班级平均」只统计有作答记录的学生，未练习的不计入分母。",
            "alerts": {
                "red": by_level.get("red", 0),
                "yellow": by_level.get("yellow", 0),
                "total": by_level.get("red", 0) + by_level.get("yellow", 0),
                "students": int(stu_with_alert),
            },
            "alertsBasis": "有效预警（教师未忽略、状态 open/read/reviewed 的红黄项），与学生端「预警与提醒」同源",
        }
    finally:
        db.close()


@tool(
    name="class_alerts",
    description=(
        "读**当前课程**全班的预警清单（含学生姓名、学号、知识点、等级、当前正确率）。"
        "教师问「谁有预警」「哪些学生需要关注」「某个知识点全班谁没过」时调用。"
        "可用 level 只看红或黄，limit 控制返回条数（默认 20，最多 50）。"
        "回答时只引用需要的那几个人，不要把全班名单无差别倒出来。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "level": {"type": "string", "enum": ["all", "red", "yellow"],
                      "description": "只看某一等级；默认 all"},
            "limit": {"type": "integer", "description": "返回条数上限，默认 20（最多 50）"},
        },
    },
    flows=_FLOW,
    roles=_TEACHER_ROLES,
)
def class_alerts(ctx: ToolContext, level: str = "all", limit: int = 20):
    course_id = _course_id(ctx)
    if not course_id:
        return {"error": "缺少课程上下文，无法读取班级预警"}
    want = (level or "all").strip().lower()
    if want not in ("all", "red", "yellow"):
        want = "all"
    top = _clamp(limit, 1, 50, 20)

    db = persistence.SessionLocal()
    try:
        q = db.query(persistence.Alert).filter(
            persistence.Alert.course_id == course_id,
            persistence.Alert.status != "ignored",
            persistence.Alert.level.in_(("red", "yellow")),
        )
        if want != "all":
            q = q.filter(persistence.Alert.level == want)
        rows = q.all()
        # 先按时间倒序，再按等级稳定排序 → 红在前，组内新的在前
        rows.sort(key=lambda a: a.created_at or _EPOCH, reverse=True)
        rows.sort(key=lambda a: 0 if a.level == "red" else 1)

        names = _student_names(db, [a.user_id for a in rows])
        from app.services.scoring import quiz_accuracy_by_kp

        acc_cache: dict[str, dict] = {}

        def _rate(uid: str, kp_id: str):
            if uid not in acc_cache:
                acc_cache[uid] = quiz_accuracy_by_kp(db, uid)
            hit = acc_cache[uid].get(kp_id)
            return round(hit[0], 1) if hit else None

        items = []
        by_kp: dict[str, dict] = {}
        for a in rows[:top]:
            name, no = names.get(a.user_id, (a.user_id, ""))
            rate = _rate(a.user_id, a.kp_id)
            items.append({
                "studentId": a.user_id, "name": name, "studentNo": no,
                "level": a.level, "kpId": a.kp_id, "kpName": a.kp_name,
                "rate": rate, "desc": a.desc, "createdAt": fmt_dt(a.created_at),
            })
            bucket = by_kp.setdefault(a.kp_id, {
                "kpId": a.kp_id, "kpName": a.kp_name, "red": 0, "yellow": 0, "students": 0,
            })
            bucket[a.level] = bucket.get(a.level, 0) + 1
            bucket["students"] += 1

        red = sum(1 for a in rows if a.level == "red")
        return {
            "courseId": course_id,
            "total": len(rows),
            "returned": len(items),
            "byLevel": {"red": red, "yellow": len(rows) - red},
            "byKp": sorted(by_kp.values(), key=lambda x: (-x["red"], -x["yellow"], x["kpId"])),
            "items": items,
            "note": "rate 为该生在该知识点上的当前正确率（与预警口径一致）；"
                    "结果已按「红在前、新的在前」排序并截断到 limit 条",
        }
    finally:
        db.close()


@tool(
    name="student_profile",
    description=(
        "看**当前课程内**某个学生的学情画像：整体正确率、预警条数、薄弱知识点、最近作答。"
        "教师问「XX 最近怎么样」「他为什么会被预警」时调用。"
        "student_id 用 class_alerts / class_overview 返回的 studentId，"
        "或学生学号（studentNo）；不属于本课程的学生会返回错误，不会返回该生任何数据。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "student_id": {"type": "string",
                           "description": "学生 user_id（如 2026010101）或学号"},
            "limit": {"type": "integer", "description": "薄弱知识点返回条数，默认 5（最多 10）"},
        },
        "required": ["student_id"],
    },
    flows=_FLOW,
    roles=_TEACHER_ROLES,
)
def student_profile(ctx: ToolContext, student_id: str = "", limit: int = 5):
    course_id = _course_id(ctx)
    sid = (student_id or "").strip()
    if not course_id:
        return {"error": "缺少课程上下文，无法读取学生画像"}
    if not sid:
        return {"error": "请给出学生 id（class_alerts 返回的 studentId，或学生学号）"}
    top = _clamp(limit, 1, 10, 5)

    db = persistence.SessionLocal()
    try:
        uids = _students(db, course_id)
        if sid not in uids:                      # 也允许用学号指定
            matched = db.query(persistence.User.user_id).filter(
                persistence.User.user_id.in_(uids or ["-"]),
                persistence.User.student_no == sid,
            ).first()
            sid = matched[0] if matched else ""
        if not sid or sid not in uids:
            # 隐私：错误信息里不带任何该生信息
            return {"error": "该学生不在当前课程中，无法查看其学情"}

        name, no = _student_names(db, [sid]).get(sid, (sid, ""))
        from app.services.alert_detector import ENGAGE_MIN, YELLOW_BELOW
        from app.services.scoring import quiz_accuracy_by_kp

        acc = quiz_accuracy_by_kp(db, sid)
        weak = [
            {"kpId": kp, "rate": round(rate, 1), "questions": hits}
            for kp, (rate, hits) in acc.items()
            if hits >= ENGAGE_MIN and rate < YELLOW_BELOW
        ]
        weak.sort(key=lambda x: (x["rate"], -x["questions"], x["kpId"]))
        weak = weak[:top]
        if weak:
            node_names = dict(db.query(
                persistence.GraphNode.id, persistence.GraphNode.name,
            ).filter(persistence.GraphNode.id.in_([w["kpId"] for w in weak])).all())
            for w in weak:
                w["kpName"] = node_names.get(w["kpId"], w["kpId"])

        alert_rows = db.query(persistence.Alert).filter(
            persistence.Alert.course_id == course_id,
            persistence.Alert.user_id == sid,
            persistence.Alert.status != "ignored",
            persistence.Alert.level.in_(("red", "yellow")),
        ).order_by(persistence.Alert.created_at.desc()).all()

        recent = db.query(persistence.AnswerRecord).filter(
            persistence.AnswerRecord.user_id == sid,
        ).order_by(persistence.AnswerRecord.id.desc()).limit(5).all()

        return {
            "courseId": course_id,
            "studentId": sid, "name": name, "studentNo": no,
            "overallAccuracy": _overall_accuracy(acc),
            "accuracyBasis": _ACCURACY_BASIS,
            "answeredQuestions": sum(hits for _r, hits in acc.values()),
            "alerts": {
                "red": sum(1 for a in alert_rows if a.level == "red"),
                "yellow": sum(1 for a in alert_rows if a.level == "yellow"),
                "items": [{"kpId": a.kp_id, "kpName": a.kp_name, "level": a.level,
                           "desc": a.desc} for a in alert_rows],
            },
            "weakPoints": weak,
            "weakBasis": f"只列命中的不同题数 ≥ {ENGAGE_MIN} 且正确率 < {YELLOW_BELOW}% 的知识点",
            "recentAnswers": [{
                "qId": r.q_id, "kpId": r.kp_id, "isCorrect": bool(r.is_correct),
                "answeredAt": fmt_dt(r.created_at),
            } for r in recent],
        }
    finally:
        db.close()


@tool(
    name="kp_heatmap",
    description=(
        "取**当前课程**「知识点 × 学生」的矩阵：每格是该生在该知识点上的掌握率或正确率，"
        "每行带一个班均值，按均值升序排列（最弱的排在前面）。"
        "教师问「这个知识点全班错在哪」「哪个知识点整体最差」时调用。"
        "备课指定某一节时传入 kp_id，返回该点的班级正确率、资源数、已发布题量和建议题量，"
        "不再返回全班矩阵。"
        "dimension=accuracy（默认，答题正确率）或 mastery（综合掌握率=正确率与资源完成率的较优值）。"
        "行数由 limit 控制（默认 10，最多 20），学生过多时自动截断。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "dimension": {"type": "string", "enum": ["accuracy", "mastery"],
                          "description": "accuracy=答题正确率（默认）；mastery=综合掌握率"},
            "limit": {"type": "integer", "description": "返回的知识点行数，默认 10（最多 20）"},
            "kp_id": {"type": "string",
                      "description": "备课指定知识点时传入，如 KP014。传入后只返回这一节的摘要"},
        },
    },
    flows=_FLOW,
    roles=_TEACHER_ROLES,
)
def kp_heatmap(ctx: ToolContext, dimension: str = "accuracy", limit: int = 10, kp_id: str = ""):
    course_id = _course_id(ctx)
    if not course_id:
        return {"error": "缺少课程上下文，无法生成知识点矩阵"}
    dim = (dimension or "accuracy").strip().lower()
    if dim not in ("accuracy", "mastery"):
        dim = "accuracy"
    rows_limit = _clamp(limit, 1, 20, 10)
    focus = (kp_id or "").strip()

    db = persistence.SessionLocal()
    try:
        uids = _students(db, course_id)
        if focus:
            if not uids:
                return {"courseId": course_id, "kpId": focus, "studentCount": 0,
                        "note": "当前课程还没有学生成员"}
            return _kp_brief(db, course_id, focus, uids)
        if not uids:
            return {"courseId": course_id, "note": "当前课程还没有学生成员"}
        shown = uids[:_MAX_STUDENTS]
        names = _student_names(db, shown)

        per_student: dict[str, dict] = {}
        for uid in shown:
            if dim == "mastery":
                from app.services.kp_stats import mastery_by_kp
                per_student[uid] = {k: round(float(v or 0), 1)
                                    for k, v in mastery_by_kp(db, uid).items()}
            else:
                from app.services.scoring import quiz_accuracy_by_kp
                per_student[uid] = {k: round(rate, 1)
                                    for k, (rate, _h) in quiz_accuracy_by_kp(db, uid).items()}

        kp_ids = sorted({kp for m in per_student.values() for kp in m})
        if not kp_ids:
            return {"courseId": course_id, "dimension": dim,
                    "students": [], "rows": [],
                    "note": "本课程目前没有任何答题/学习记录，矩阵为空"}
        node_names = dict(db.query(
            persistence.GraphNode.id, persistence.GraphNode.name,
        ).filter(persistence.GraphNode.id.in_(kp_ids)).all())

        table = []
        for kp in kp_ids:
            values = [per_student[uid].get(kp) for uid in shown]
            nums = [v for v in values if v is not None]
            if not nums:
                continue
            table.append({
                "kpId": kp, "kpName": node_names.get(kp, kp),
                "avg": round(sum(nums) / len(nums), 1),
                "answered": len(nums),
                "values": values,
            })
        table.sort(key=lambda r: (r["avg"], r["kpId"]))
        picked = table[:rows_limit]

        return {
            "courseId": course_id,
            "dimension": dim,
            "basis": ("掌握率 = max(答题正确率, 资源完成率) 的知识点均值口径（与学生端「我的学情」一致）"
                      if dim == "mastery" else _ACCURACY_BASIS),
            "students": [{"studentId": u, "name": names.get(u, (u, ""))[0],
                          "studentNo": names.get(u, (u, ""))[1]} for u in shown],
            "rows": picked,
            "truncated": {
                "kp": len(table) > len(picked),
                "students": len(uids) > len(shown),
                "totalKp": len(table), "totalStudents": len(uids),
            },
            "note": "values 与 students 按顺序一一对应；null 表示该生在这道知识点上没有记录；"
                    "结果已按班均值升序截断（最弱的知识点在前）",
        }
    finally:
        db.close()


def _clip_question(text: str) -> str:
    compact = " ".join((text or "").split())
    if len(compact) > 80:
        return compact[:80] + "…"
    return compact


def _resolve_logged_topic(course_id: str, args: dict) -> dict:
    """从已落库的 resolve_topic 参数还原知识点。不读取助手回答正文。"""
    from app.agent_st.rag.topic import resolve_topic as resolve_topic_impl

    kp_id = str((args or {}).get("kp_id") or "").strip()
    text = str((args or {}).get("text") or "").strip()
    q_id = str((args or {}).get("q_id") or "").strip()
    if not kp_id and not text and not q_id:
        return {}
    return resolve_topic_impl(
        course_id=course_id, text=text, kp_id=kp_id or None, q_id=q_id or None,
    ) or {}


@tool(
    name="class_question_hotspots",
    description=(
        "统计**当前课程学生**最近一段时间在智能答疑里问得最多的知识点和章节。"
        "只根据助手消息 tool_log 里已经记录的 resolve_topic 聚合，不返回私聊全文，"
        "也不返回学生姓名。每个知识点最多带 3 条匿名问句样例。"
        "教师问「这周学生都在问什么」「哪一章提问最多」时调用。"
        "days 默认 7，问今天传 1，问这个月最多传 30。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "days": {"type": "integer", "description": "统计最近几天，默认 7，范围 1～30"},
            "limit": {"type": "integer", "description": "返回前几个知识点，默认 5，最多 8"},
        },
    },
    flows=_FLOW,
    roles=_TEACHER_ROLES,
)
def class_question_hotspots(ctx: ToolContext, days: int = 7, limit: int = 5):
    import json

    course_id = _course_id(ctx)
    if not course_id:
        return {"error": "缺少课程上下文，无法统计学生提问"}
    window = _clamp(days, 1, 30, 7)
    top = _clamp(limit, 1, 8, 5)
    since = datetime.utcnow() - timedelta(days=window)

    db = persistence.SessionLocal()
    try:
        uids = _students(db, course_id)
        if not uids:
            return {"courseId": course_id, "days": window, "total": 0, "items": [],
                    "note": "当前课程还没有学生成员"}
        sessions = db.query(persistence.ChatSession.session_id).filter(
            persistence.ChatSession.course_id == course_id,
            persistence.ChatSession.user_id.in_(uids),
        ).all()
        sids = [row[0] for row in sessions]
        if not sids:
            return {"courseId": course_id, "days": window, "total": 0, "items": [],
                    "chapters": [], "unlocated": 0,
                    "note": "这段时间没有学生答疑记录"}
        rows = db.query(persistence.ChatMessage).filter(
            persistence.ChatMessage.session_id.in_(sids),
            persistence.ChatMessage.created_at >= since,
        ).order_by(
            persistence.ChatMessage.session_id,
            persistence.ChatMessage.id,
        ).all()

        buckets: dict[str, dict] = {}
        chapters: dict[str, int] = {}
        unlocated = 0
        unlocated_samples: list[str] = []
        last_question: dict[str, str] = {}
        total = 0
        for row in rows:
            if row.role == "me":
                sample = _clip_question(row.content or "")
                if sample:
                    last_question[row.session_id] = sample
                continue
            if row.role != "ai":
                continue
            try:
                logged = json.loads(row.tool_log or "[]")
            except (TypeError, json.JSONDecodeError):
                continue
            if not isinstance(logged, list):
                continue
            sample = last_question.get(row.session_id) or ""
            for item in logged:
                if not isinstance(item, dict) or item.get("name") != "resolve_topic":
                    continue
                if item.get("kind") not in (None, "tool"):
                    continue
                located = _resolve_logged_topic(course_id, item.get("args") or {})
                kp_id = str(located.get("kp_id") or "").strip()
                chapter_only = str(located.get("chapter_name") or "").strip()
                if not kp_id:
                    if chapter_only and not located.get("uncertain"):
                        chapters[chapter_only] = chapters.get(chapter_only, 0) + 1
                    else:
                        unlocated += 1
                        if sample and sample not in unlocated_samples and len(unlocated_samples) < 3:
                            unlocated_samples.append(sample)
                    total += 1
                    continue
                bucket = buckets.setdefault(kp_id, {
                    "kpId": kp_id,
                    "kpName": located.get("kp_name") or kp_id,
                    "chapter": located.get("chapter_name") or "",
                    "count": 0,
                    "samples": [],
                })
                bucket["count"] += 1
                if sample and sample not in bucket["samples"] and len(bucket["samples"]) < 3:
                    bucket["samples"].append(sample)
                chapter = bucket["chapter"] or "未分章"
                chapters[chapter] = chapters.get(chapter, 0) + 1
                total += 1

        items = sorted(buckets.values(), key=lambda r: (-r["count"], r["kpName"]))[:top]
        chapter_rows = sorted(
            ({"chapter": name, "count": count} for name, count in chapters.items()),
            key=lambda r: (-r["count"], r["chapter"]),
        )[:top]
        return {
            "courseId": course_id,
            "days": window,
            "total": total,
            "unlocated": unlocated,
            "unlocatedSamples": unlocated_samples,
            "items": items,
            "chapters": chapter_rows,
            "note": ("按学生答疑里已记录的知识点定位聚合，问句已截断且不含姓名。"
                     "点名某个学生时改用 student_profile，不要从这里推断是谁。"),
        }
    finally:
        db.close()


@tool(
    name="hot_wrong_questions",
    description=(
        "取**当前课程**全班错得最多的题（题号 + 错误率 + 涉及学生数），可限定某个知识点。"
        "教师问「哪几道题全班都错」「这个知识点的题错在哪」时调用。"
        "kp_id 用 resolve_topic 或 class_alerts 给出的知识点 id；不给则统计全课程。"
        "注意口径：这里的知识点归属取作答记录里的 kp_id（作答当时的归属）。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "kp_id": {"type": "string", "description": "知识点 id（可省略）"},
            "limit": {"type": "integer", "description": "返回题数，默认 10（最多 30）"},
        },
    },
    flows=_FLOW,
    roles=_TEACHER_ROLES,
)
def hot_wrong_questions(ctx: ToolContext, kp_id: str = "", limit: int = 10):
    course_id = _course_id(ctx)
    if not course_id:
        return {"error": "缺少课程上下文，无法统计错题"}
    kp = (kp_id or "").strip()
    top = _clamp(limit, 1, 30, 10)

    db = persistence.SessionLocal()
    try:
        uids = _students(db, course_id)
        if not uids:
            return {"courseId": course_id, "note": "当前课程还没有学生成员"}
        if kp:
            node = db.query(persistence.GraphNode.id).filter(
                persistence.GraphNode.id == kp,
                persistence.GraphNode.course_id == course_id,
                persistence.GraphNode.graph_type == "knowledge",
            ).first()
            if not node:
                return {"error": f"知识点 {kp} 不属于当前课程"}

        q = db.query(
            persistence.AnswerRecord.q_id.label("q_id"),
            func.count(persistence.AnswerRecord.id).label("total"),
            func.sum(persistence.AnswerRecord.is_correct).label("correct"),
            func.count(func.distinct(persistence.AnswerRecord.user_id)).label("students"),
        ).filter(
            persistence.AnswerRecord.user_id.in_(uids),
            persistence.AnswerRecord.q_id.isnot(None),
        )
        if kp:
            q = q.filter(persistence.AnswerRecord.kp_id == kp)
        rows = q.group_by(persistence.AnswerRecord.q_id).all()
        if not rows:
            return {"courseId": course_id, "kpId": kp, "items": [],
                    "note": "没有符合条件的作答记录"}

        stat = []
        for r in rows:
            total = int(r.total or 0)
            correct = int(r.correct or 0)
            stat.append({
                "qId": r.q_id, "total": total, "wrong": total - correct,
                "wrongRate": round((total - correct) / total * 100, 1) if total else 0.0,
                "students": int(r.students or 0),
            })
        stat.sort(key=lambda x: (-x["wrong"], -x["wrongRate"], x["qId"]))
        picked = stat[:top]

        qids = [x["qId"] for x in picked]
        q_rows = db.query(persistence.Question.q_id, persistence.Question.kp_id).filter(
            persistence.Question.q_id.in_(qids),
        ).all()
        q_kp = {qid: (k or "") for qid, k in q_rows}
        node_names = dict(db.query(
            persistence.GraphNode.id, persistence.GraphNode.name,
        ).filter(persistence.GraphNode.id.in_([k for k in q_kp.values() if k] or ["-"])).all())
        for x in picked:
            x["kpId"] = q_kp.get(x["qId"], "")
            x["kpName"] = node_names.get(x["kpId"], x["kpId"])

        return {
            "courseId": course_id, "kpId": kp,
            "basis": "按全班作答记录聚合：错误率 = 答错次数 ÷ 作答次数；知识点归属取作答记录里的 kp_id",
            "items": picked,
            "note": f"共 {len(stat)} 道题有作答记录，已按错误次数降序截断到 {len(picked)} 道",
        }
    finally:
        db.close()
