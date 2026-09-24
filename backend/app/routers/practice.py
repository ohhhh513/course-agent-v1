"""
智能练习接口：/practice/*
"""
import json, re, uuid
from datetime import datetime
from fastapi import APIRouter, Depends, Query, Body
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List

from ..database import get_db
from ..models.practice import PracticeSession, AnswerRecord
from ..models.question import Question
from ..models.graph import GraphNode
from ..models.user import User
from ..models.intervention import TeacherClassDashboard
from ..models.course import Resource
from ..middleware.auth import get_current_user
from ..dependencies import get_current_course_id
from ..schemas.common import ok, fail, list_response
from ..utils import loads, fmt_dt
from sqlalchemy import func

router = APIRouter(prefix="/api/v1/practice", tags=["智能练习"])


def _order_pool(db: Session, user_id: str, course_id: str, rows: list, target_kps: list[str]) -> list:
    """抽题池排序：最薄弱知识点 → 做错过的题 → 难度升序 → 同档随机打散。

    target_kps 的顺序即优先级（前端按答题正确率升序给出，最薄弱在前）。
    「做错过的题」= 该生在该题上最近一次作答是错的（与全站"按题取最近一次"口径一致）。
    """
    from collections import defaultdict
    import random

    kp_rank = {kp: i for i, kp in enumerate(target_kps)}
    wrong_qids: set[str] = set()
    qids = [r.q_id for r in rows]
    if qids:
        latest = db.query(
            AnswerRecord.q_id, func.max(AnswerRecord.id).label("last_id"),
        ).filter(
            AnswerRecord.user_id == user_id,
            AnswerRecord.course_id == course_id,
            AnswerRecord.q_id.in_(qids),
        ).group_by(AnswerRecord.q_id).subquery()
        for qid, ok in db.query(AnswerRecord.q_id, AnswerRecord.is_correct).join(
                latest, AnswerRecord.id == latest.c.last_id).all():
            if not ok:
                wrong_qids.add(qid)

    buckets: dict = defaultdict(list)
    for r in rows:
        rank = kp_rank.get(r.kp_id, len(kp_rank))
        tier = 0 if r.q_id in wrong_qids else 1      # 做错过的题排前
        diff = int(r.difficulty or 3)                 # 同档先易后难
        buckets[(rank, tier, diff)].append(r)
    out: list = []
    for key in sorted(buckets):
        group = buckets[key]
        random.shuffle(group)                         # 同档内随机，顺序每次不同
        out.extend(group)
    return out


def _random_scope_kp_ids(db: Session, user_id: str, course_id: str) -> list[str]:
    """「随机练习」的抽题范围：**学过且有错**的知识点（2026-09-24 重定义）。

    - 学过 = 有作答记录；
    - 有错 = 按题去重取最近一次作答后，存在答错的题 —— 即加权正确率 < 100%；
    - 全对 / 从没做过 → 不进入范围（调用方据此返回空池并提示，不再随机抽整门课）。

    口径与 `services/scoring.quiz_accuracy_by_kp` 一致（含多标签的加权：主 KP 1.0 / 其它 0.3）。

    **课程隔离**（2026-09-24 核实后更正）：`quiz_accuracy_by_kp(db, user_id)` 只按 user 聚合、
    **没有 course 参数**，返回的是该生「所有课程」的知识点正确率表 —— 所以它的**键集合跨课程**。
    但每个 KP 的**数值本身不跨课**：KP id 全局唯一（`teacher._next_graph_id` 全表取 max+1），
    一道题只属一门课、其主 KP 与其它标签都指向本课的知识点（库副本实测 0 条例外），
    且「只取该课程作答记录」重算的结果与全量口径**逐点完全一致**。
    因此这里按"本课程的知识点"过滤，是为了确定**这门课该在哪些知识点里抽题**
    （否则切到另一门课时会拿别的课的知识点当范围，那些点在本课根本无题可抽），
    而不是因为正确率算错了。
    """
    from ..services.scoring import quiz_accuracy_by_kp

    acc = quiz_accuracy_by_kp(db, user_id)
    course_kps = {r[0] for r in db.query(GraphNode.id).filter(
        GraphNode.graph_type == "knowledge",
        GraphNode.course_id == course_id,
    ).all()}
    return [kp for kp, (rate, _n) in acc.items() if rate < 100 and kp in course_kps]


def _figure_of(q: Question):
    """解析图题规格（graph/options_graph/has_image），纯文本题返回 None"""
    raw = getattr(q, "figure_json", None)
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except (TypeError, ValueError):
        return None


# ===== 工具函数：从真实答题记录计算题目统计 =====
def _calc_question_stats(db: Session, q_id: str, course_id: str = ""):
    """基于 answer_records 返回班级正确率、平均用时、错误数、总答题数"""
    filters = [AnswerRecord.q_id == q_id]
    if course_id:
        filters.append(AnswerRecord.course_id == course_id)
    total, correct, avg_dur = db.query(
        func.count(AnswerRecord.id),
        func.sum(AnswerRecord.is_correct),
        func.avg(AnswerRecord.duration_seconds),
    ).filter(*filters).first()
    total = total or 0
    correct = correct or 0
    class_rate = round(correct / total * 100, 1) if total else 0
    avg_sec = round(avg_dur or 0, 1)
    wrong = total - correct
    return class_rate, avg_sec, wrong, total


def _mastery_delta(correct: bool, difficulty: int, score: int) -> float:
    """根据难度、分值、正误计算掌握度变化量"""
    base = score / 10.0
    if correct:
        return round(base * (1 + difficulty / 10.0), 2)
    return round(-base * (1 + difficulty / 5.0), 2)


# ===== 请求体 =====
class CreateSessionReq(BaseModel):
    mode: str = "weak"
    kpIds: Optional[List[str]] = None
    qIds: Optional[List[str]] = None
    count: int = 10
    difficulty: Optional[int] = None


class SubmitAnswerReq(BaseModel):
    sessionId: str
    qId: str
    answer: str
    durationSeconds: int = 60


# ===== 练习模式（推荐 count 动态计算） =====
_BASE_COUNTS = {"weak": 10, "order": 20, "random": 15, "wrong": 12}

@router.get("/modes")
def practice_modes(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    course_id: str = Depends(get_current_course_id),
):
    # 题库总题数
    total_qs = db.query(Question).filter(
        Question.course_id == course_id,
        Question.status == "published",
    ).count()
    # 当前用户错题数（答题记录中 is_correct=0）
    wrong_count = db.query(AnswerRecord).filter(
        AnswerRecord.user_id == user.user_id,
        AnswerRecord.course_id == course_id,
        AnswerRecord.is_correct == 0,
    ).count()

    base = [
        {"key": "weak", "name": "薄弱点强化", "desc": "系统按掌握率自动组卷，命中薄弱知识点", "icon": "target", "recommend": True},
        {"key": "order", "name": "顺序练习", "desc": "按章节与知识点前后置顺序逐题推进", "icon": "list"},
        {"key": "random", "name": "随机练习", "desc": "只在「学过且做错过」的知识点里随机抽题", "icon": "shuffle"},
        {"key": "wrong", "name": "错题重练", "desc": "重做历史错题，验证是否真正掌握", "icon": "refresh"},
    ]
    # 随机练习的题量按"学过且有错"的范围统计（与组卷口径一致，避免卡片写着 15 题、实际只有几道）
    random_scope = _random_scope_kp_ids(db, user.user_id, course_id)
    random_cap = 0
    if random_scope:
        random_cap = db.query(func.count(Question.q_id)).filter(
            Question.course_id == course_id,
            Question.status == "published",
            Question.kp_id.in_(random_scope),
        ).scalar() or 0
    for m in base:
        key = m["key"]
        cap = {"weak": total_qs, "order": total_qs, "random": random_cap, "wrong": wrong_count}[key]
        m["count"] = min(_BASE_COUNTS[key], cap)
        if cap == 0:
            m["count"] = 0
    return ok(base)


@router.get("/kp-pool")
def practice_kp_pool(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    course_id: str = Depends(get_current_course_id),
):
    """各知识点的**已发布题量**（「顺序练习」选章节用：没有题的知识点不展示）。

    口径与组卷一致 —— 只统计**主 KP**（`questions.kp_id`），不按 `kp_ids` 多标签扩散：
    `create_session` 带 kpIds 时就是按主 KP 过滤抽题的，按多标签统计会出现
    「这里显示有题、进去却抽不到」的偏差。只统计当前课程、status='published' 的题。
    """
    rows = db.query(Question.kp_id, func.count(Question.q_id)).filter(
        Question.course_id == course_id,
        Question.status == "published",
        Question.kp_id.isnot(None),
    ).group_by(Question.kp_id).all()
    counts = {kp: int(n or 0) for kp, n in rows if (kp or "").strip()}
    return ok({"counts": counts, "total": sum(counts.values())})


@router.post("/sessions")
def create_session(
    req: CreateSessionReq,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    course_id: str = Depends(get_current_course_id),
):
    """创建练习会话（组卷）"""
    target_kps: list[str] = []
    q = db.query(Question).filter(
        Question.course_id == course_id,
        Question.status == "published",
    )
    if req.qIds:
        # 重做指定题目（错题本“重做本题”）
        q = q.filter(Question.q_id.in_(req.qIds))
    elif req.kpIds:
        # 只取「当前课程真实存在」的目标知识点，**不扩散到同章**（2026-09-24 改）：
        # 学生在「薄弱点强化 / 靶向出题」里指定的是知识点，抽到的题就必须属于这些知识点。
        # 旧实现按章节扩散，会出现「点 KP001 却抽到同章其它（甚至已达标）知识点的题」。
        want = [str(k).strip() for k in req.kpIds if str(k).strip()]
        valid = {r[0] for r in db.query(GraphNode.id).filter(
            GraphNode.graph_type == "knowledge",
            GraphNode.course_id == course_id,
            GraphNode.id.in_(want),
        ).all()}
        target_kps = [k for k in want if k in valid]     # 保留传入顺序（= 正确率升序）
        if target_kps:
            q = q.filter(Question.kp_id.in_(target_kps))
        else:
            # 传了 kpIds 但都不属于本课程（多为切换课程后的残留状态）：
            # 显式返回空池，不再静默回退成「整门课随机」，避免学生以为在练薄弱点。
            print(f"[practice] kpIds={req.kpIds} 不属于当前课程 {course_id}，返回空池", flush=True)
            return ok({"sessionId": "", "mode": req.mode, "total": 0, "questions": []})
    elif req.mode == "wrong":
        # 错题重练：只抽该用户错过的题
        wrong_q_ids = [r[0] for r in db.query(AnswerRecord.q_id).filter(
            AnswerRecord.user_id == user.user_id,
            AnswerRecord.course_id == course_id,
            AnswerRecord.is_correct == 0,
        ).distinct().all()]
        q = q.filter(Question.q_id.in_(wrong_q_ids))
    elif req.mode == "random":
        # 随机练习（2026-09-24 重定义）：只在「学过且有错」的知识点范围内随机抽题。
        # 已学的全对、或压根没做过 → 显式返回空池 + emptyReason，由前端弹提示，
        # 不再静默抽整门课（那样等于"没学过也在练"）。
        scope = _random_scope_kp_ids(db, user.user_id, course_id)
        if scope:
            q = q.filter(Question.kp_id.in_(scope))
        else:
            print("[practice] random 模式但无「学过且有错」的知识点，返回空池", flush=True)
            return ok({"sessionId": "", "mode": req.mode, "total": 0, "questions": [],
                       "emptyReason": "random_scope_empty"})
    if req.mode == "weak" and not target_kps and not req.qIds:
        # 「薄弱点强化 / 靶向出题」但没有任何可定位的薄弱点（未作答，或题量不足 2 道）：
        # 显式返回空池并提示前端，不再静默退化成"整门课随机抽"（2026-09-24）。
        print("[practice] weak 模式但无可定位的薄弱点（kpIds 为空），返回空池", flush=True)
        return ok({"sessionId": "", "mode": req.mode, "total": 0, "questions": []})
    if req.difficulty:
        q = q.filter(Question.difficulty == req.difficulty)
    import random
    all_qs = q.all()
    count = min(req.count, len(all_qs))
    if target_kps:
        # 指定了知识点：按「最薄弱 → 做错过的题 → 难度升序 → 同档随机」取前 count 题
        picked = _order_pool(db, user.user_id, course_id, all_qs, target_kps)[:count]
    else:
        # 未指定知识点（顺序/随机/错题重练等）：保持随机抽样
        picked = random.sample(all_qs, count) if all_qs else []

    # 同一模式只保留一个进行中「存档」：新开练习时，把旧的 running 会话标记为 abandoned
    db.query(PracticeSession).filter(
        PracticeSession.user_id == user.user_id,
        PracticeSession.course_id == course_id,
        PracticeSession.mode == req.mode,
        PracticeSession.status == "running",
    ).update({"status": "abandoned"})

    session_id = "PS" + uuid.uuid4().hex[:10]
    session = PracticeSession(
        session_id=session_id,
        user_id=user.user_id,
        course_id=course_id,
        mode=req.mode,
        total=count,
        status="running",
        questions_snapshot=json.dumps(
            [{"qId": q.q_id, "type": q.type, "stem": q.stem, "options": loads(q.options) or []} for q in picked],
            ensure_ascii=False,
        ),
    )
    db.add(session)
    db.commit()

    questions = [
        {
            "qId": q.q_id, "type": q.type, "difficulty": q.difficulty, "score": q.score,
            "stem": q.stem, "options": loads(q.options) or [],
            "kpPath": loads(q.kp_path) or [], "kpId": q.kp_id, "isKey": bool(q.is_key),
            "preKp": loads(q.pre_kp) or [],
            "figure": _figure_of(q),
        }
        for q in picked
    ]
    return ok({
        "sessionId": session_id, "mode": req.mode, "total": count,
        "questions": questions,
    })


@router.get("/sessions/current")
def current_session(
    mode: str = Query("order"),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    course_id: str = Depends(get_current_course_id),
):
    """取当前进行中的练习存档（用于「继续挑战」）；无则返回 null"""
    session = (
        db.query(PracticeSession)
        .filter(PracticeSession.user_id == user.user_id,
                PracticeSession.course_id == course_id,
                PracticeSession.mode == mode,
                PracticeSession.status == "running")
        .order_by(PracticeSession.created_at.desc())
        .first()
    )
    if not session:
        return ok(None)
    q_ids = [x.get("qId") for x in (loads(session.questions_snapshot) or []) if x.get("qId")]
    rows = {q.q_id: q for q in db.query(Question).filter(
        Question.course_id == course_id,
        Question.q_id.in_(q_ids),
    ).all()}
    answered = {r.q_id: r for r in db.query(AnswerRecord).filter(
        AnswerRecord.session_id == session.session_id,
        AnswerRecord.course_id == course_id,
    ).all()}
    questions = []
    for qid in q_ids:
        q = rows.get(qid)
        if not q:
            continue
        ar = answered.get(qid)
        questions.append({
            "qId": q.q_id, "type": q.type, "difficulty": q.difficulty, "score": q.score,
            "stem": q.stem, "options": loads(q.options) or [],
            "kpPath": loads(q.kp_path) or [], "kpId": q.kp_id, "preKp": loads(q.pre_kp) or [],
            "isKey": bool(q.is_key), "figure": _figure_of(q),
            "answered": ar is not None,
            "myAnswer": (ar.my_answer if ar else ""),
            "correct": (bool(ar.is_correct) if ar else None),
        })
    answered_count = sum(1 for x in questions if x["answered"])
    return ok({
        "sessionId": session.session_id, "mode": session.mode,
        "total": len(questions), "answered": answered_count,
        "questions": questions,
    })


@router.get("/sessions/{session_id}/questions")
def get_session_questions(
    session_id: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    course_id: str = Depends(get_current_course_id),
):
    """取题"""
    session = db.query(PracticeSession).filter(
        PracticeSession.session_id == session_id,
        PracticeSession.user_id == user.user_id,
        PracticeSession.course_id == course_id,
    ).first()
    if not session:
        return fail("会话不存在", 404)
    q_ids = [x["qId"] for x in loads(session.questions_snapshot) or []]
    rows = db.query(Question).filter(
        Question.course_id == course_id,
        Question.q_id.in_(q_ids),
    ).all()
    items = [
        {
            "qId": q.q_id, "type": q.type, "difficulty": q.difficulty, "score": q.score,
            "stem": q.stem, "options": loads(q.options) or [],
            "kpPath": loads(q.kp_path) or [], "kpId": q.kp_id, "preKp": loads(q.pre_kp) or [],
            "isKey": bool(q.is_key),
        }
        for q in rows
    ]
    return ok(items)


@router.post("/answers")
def submit_answer(
    req: SubmitAnswerReq,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    course_id: str = Depends(get_current_course_id),
):
    """提交单题作答 —— 即时判分 + 解析"""
    question = db.query(Question).filter(
        Question.q_id == req.qId,
        Question.course_id == course_id,
    ).first()
    if not question:
        return fail("题目不存在", 404)

    # 越权校验：作答必须属于当前登录用户的练习会话
    session = db.query(PracticeSession).filter(
        PracticeSession.session_id == req.sessionId,
        PracticeSession.course_id == course_id,
    ).first()
    if not session:
        return fail("练习会话不存在", 404)
    if session.user_id != user.user_id:
        return fail("无权操作他人练习会话", 403)

    correct = req.answer == question.answer

    # 保存答题记录
    # ⚠️ course_id 必须显式写入：模型里的默认值是早期演示课 "C2026DS001"，
    # 而真实库里只有学生实际加入的课程，靠默认值会直接外键约束失败（提交答案整体 500）。
    record = AnswerRecord(
        session_id=req.sessionId,
        user_id=user.user_id,
        course_id=session.course_id or question.course_id or course_id,
        q_id=req.qId,
        kp_id=question.kp_id,
        my_answer=req.answer,
        correct_answer=question.answer,
        is_correct=1 if correct else 0,
        duration_seconds=req.durationSeconds,
        error_type="" if correct else question.error_type,
    )
    db.add(record)
    # 更新会话 correct/wrong
    if correct:
        session.correct = (session.correct or 0) + 1
    else:
        session.wrong = (session.wrong or 0) + 1
    db.commit()

    # 每次产生新的真实作答后立即重算该生预警，教师端刷新即可看到最新红/黄状态；
    # 检测失败不影响本次答题结果的正常返回。
    try:
        from ..services.alert_detector import detect_alerts
        detect_alerts(db, [user])
    except Exception as e:
        db.rollback()   # 检测失败必须回滚，否则会话毒化导致后续判分/统计查询 500
        print(f"[alert-detect] 作答后刷新跳过（{e}）")

    # 动态统计：该题真实班级正确率、平均用时
    class_rate, avg_sec, _, _ = _calc_question_stats(db, question.q_id, course_id)
    delta = _mastery_delta(correct, question.difficulty, question.score)

    return ok({
        "qId": question.q_id,
        "correct": correct,
        "rightAnswer": question.answer,
        "analysis": question.analysis,
        "kpPath": loads(question.kp_path) or [],
        "classCorrectRate": class_rate,
        "avgSeconds": avg_sec,
        "masteryDelta": delta,
    })


@router.post("/sessions/{session_id}/finish")
def finish_session(
    session_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    course_id: str = Depends(get_current_course_id),
):
    """结束练习，返回练习报告"""
    from ..models.graph import LearningPath
    session = db.query(PracticeSession).filter(
        PracticeSession.session_id == session_id,
        PracticeSession.course_id == course_id,
    ).first()
    if not session:
        return fail("会话不存在", 404)
    # 越权校验：只能结束本人练习会话
    if session.user_id != user.user_id:
        return fail("无权操作他人练习会话", 403)
    session.status = "finished"
    session.finished_at = datetime.utcnow()
    if session.total > 0:
        session.accuracy = round(session.correct / session.total * 100, 1)

    # 答题记录
    records = db.query(AnswerRecord).filter(
        AnswerRecord.session_id == session_id,
        AnswerRecord.user_id == user.user_id,
        AnswerRecord.course_id == course_id,
    ).all()

    # 错题知识点分布（题库无「错误类型」字段，改用真实数据：错题按 kp_id 汇总）
    wrong_by_kp = {}
    for r in records:
        if not r.is_correct and r.kp_id:
            wrong_by_kp[r.kp_id] = wrong_by_kp.get(r.kp_id, 0) + 1
    wrong_kp_names = {}
    if wrong_by_kp:
        wrong_kp_names = dict(db.query(GraphNode.id, GraphNode.name).filter(
            GraphNode.graph_type == "knowledge",
            GraphNode.course_id == course_id,
            GraphNode.id.in_(list(wrong_by_kp.keys())),
        ).all())
    wrong_by_kp_list = [
        {"kpId": k, "name": wrong_kp_names.get(k, k), "count": c}
        for k, c in sorted(wrong_by_kp.items(), key=lambda kv: -kv[1])
    ]

    # 真实用时：所有 answer_records.duration_seconds 求和
    duration_seconds = sum((r.duration_seconds or 0) for r in records)
    # 写回会话字段：此前该字段从未写入、恒为 0，导致学生端「学习时长」漏计练习用时、
    # 练习动态卡片显示墙钟时长。这里用真实练习用时回填，供学生端统计复用（非伪造）。
    session.duration_seconds = duration_seconds
    total_answered = len(records) or 1
    avg_seconds = round(duration_seconds / total_answered, 1)

    # kpChanges：练习涉及的 kp，取当前 mastery；delta 按本次练习该 kp 的答题表现累加
    kp_ids_in_session = list({r.kp_id for r in records if r.kp_id})
    kp_changes = []
    if kp_ids_in_session:
        lps = db.query(LearningPath).filter(
            LearningPath.user_id == user.user_id,
            LearningPath.course_id == course_id,
            LearningPath.kp_id.in_(kp_ids_in_session),
        ).all()
        lp_map = {lp.kp_id: lp for lp in lps}
        for kp_id in kp_ids_in_session:
            lp = lp_map.get(kp_id)
            cur_m = round(lp.mastery or 0) if lp else 0
            # 汇总本次练习中该 kp 的每题变化量
            delta = 0
            for r in records:
                if r.kp_id == kp_id:
                    q = db.query(Question).filter(
                        Question.q_id == r.q_id,
                        Question.course_id == course_id,
                    ).first()
                    if q:
                        delta += _mastery_delta(bool(r.is_correct), q.difficulty, q.score)
            before_m = max(0, min(100, cur_m - delta))
            name = lp.name if lp else kp_id
            kp_changes.append({
                "name": name or kp_id,
                "before": round(before_m),
                "after": cur_m,
                "delta": round(delta, 2),
            })

    # 班级正确率：按本次练习涉及题目的真实 answer_records 计算
    q_ids = [r.q_id for r in records]
    qid_total = db.query(func.count(AnswerRecord.id), func.sum(AnswerRecord.is_correct)).filter(
        AnswerRecord.course_id == course_id,
        AnswerRecord.q_id.in_(q_ids)
    ).first()
    total_ans, correct_ans = qid_total or (0, 0)
    class_acc = round((correct_ans or 0) / (total_ans or 1) * 100, 1)

    # 得分变化：按每题分值累加（答对+score，答错0）
    q_score_map = {q.q_id: q.score for q in db.query(Question).filter(
        Question.course_id == course_id,
        Question.q_id.in_(q_ids),
    ).all()}
    score_gain = 0
    for r in records:
        if r.is_correct:
            score_gain += q_score_map.get(r.q_id, 5)

    # 错题重练：答对的题自动标记为已掌握（进入错题本“已掌握”列表）
    mastered_count = 0
    if session.mode == "wrong":
        correct_qids = {r.q_id for r in records if r.is_correct == 1}
        for qid in correct_qids:
            res = db.query(AnswerRecord).filter(
                AnswerRecord.user_id == user.user_id,
                AnswerRecord.course_id == course_id,
                AnswerRecord.q_id == qid,
                AnswerRecord.is_correct == 0,
            ).update({"mastered": True})
            if res:
                mastered_count += 1

    db.commit()

    return ok({
        "reportId": "PR" + uuid.uuid4().hex[:10],
        "mode": session.mode,
        "total": session.total, "correct": session.correct or 0, "wrong": session.wrong or 0,
        "accuracy": session.accuracy or 0,
        "durationSeconds": duration_seconds,
        "avgSeconds": avg_seconds,
        "classAccuracy": class_acc,
        "scoreGain": round(score_gain, 1),
        "kpChanges": kp_changes,
        "wrongByKp": wrong_by_kp_list,
        "masteredCount": mastered_count,
        "nextSuggestion": "建议先回顾错题对应的知识点，再进行薄弱点强化。",
    })


@router.get("/wrong-book")
def wrong_book(
    kpId: str = Query(None),
    chapter: str = Query(None),
    mastered: str = Query(None),   # 'true' / 'false'
    page: int = Query(1),
    size: int = Query(20),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    course_id: str = Depends(get_current_course_id),
):
    """错题本（按题目聚合 + 按「章节 → 知识点」归纳统计）

    返回 `groups`：当前分类（待攻克/已掌握/全部）下每个章节的错题数与章节内各知识点错题数，
    供前端做「按章节知识点归纳」筛选；`kpId` / `chapter` 只影响列表本身，
    不影响 groups（这样选中某个知识点时章节导航不会跳变）。
    """
    # 从答题记录中取错题
    records = db.query(AnswerRecord).filter(
        AnswerRecord.user_id == user.user_id,
        AnswerRecord.course_id == course_id,
        AnswerRecord.is_correct == 0,
    ).order_by(AnswerRecord.created_at.desc()).all()

    # 按题目聚合；records 已按时间倒序，首条即最近一次作答
    wrong_map = {}
    for r in records:
        if r.q_id not in wrong_map:
            wrong_map[r.q_id] = {
                "wrongCount": 0, "lastTime": r.created_at,
                # 最近一次错题的状态决定该题归属“待攻克/已掌握”
                "mastered": bool(r.mastered),
                "myAnswer": r.my_answer,
            }
        wrong_map[r.q_id]["wrongCount"] += 1
        if r.created_at > wrong_map[r.q_id]["lastTime"]:
            wrong_map[r.q_id]["lastTime"] = r.created_at

    # 状态过滤：'true' 已掌握 / 'false' 待攻克 / 'all'|None 全部
    filter_flag = None
    if mastered in ("true", "false"):
        filter_flag = mastered == "true"

    # 知识点元信息：名称 + 章节（图谱为准，题库 chapter 兜底，最后兜到 kp_id）
    kp_meta = {
        n.id: {"name": n.name, "chapter": n.chapter or "未分章"}
        for n in db.query(GraphNode).filter(
            GraphNode.graph_type == "knowledge", GraphNode.course_id == course_id,
        ).all()
    }

    items = []
    if wrong_map:
        questions = db.query(Question).filter(
            Question.course_id == course_id,
            Question.q_id.in_(list(wrong_map.keys())),
        ).all()
        for q in questions:
            w = wrong_map[q.q_id]
            if filter_flag is not None and w["mastered"] != filter_flag:
                continue
            meta = kp_meta.get(q.kp_id) or {}
            items.append({
                "qId": q.q_id, "stem": q.stem, "myAnswer": w["myAnswer"],
                "answer": q.answer,
                "wrongCount": w["wrongCount"],
                "kp": meta.get("name") or q.kp_id or "未标注",
                "kpId": q.kp_id,
                "kpName": meta.get("name") or q.kp_id or "未标注",
                "chapter": meta.get("chapter") or q.chapter or "未分章",
                "difficulty": q.difficulty,
                "lastTime": fmt_dt(w["lastTime"], "%m-%d %H:%M"),
                "mastered": w["mastered"],
            })

    # ---- 按章节 → 知识点归纳（章按「第N章」排序，知识点按错题数倒序）----
    def _ch_order(ch: str):
        m = re.search(r"第\s*(\d+)\s*[章讲]", ch or "")
        return (0, int(m.group(1)), ch or "") if m else (1, 10**9, ch or "")

    agg = {}
    for it in items:
        g = agg.setdefault(it["chapter"], {"chapter": it["chapter"], "total": 0, "kps": {}})
        g["total"] += 1
        k = g["kps"].setdefault(it["kpId"], {"kpId": it["kpId"], "name": it["kpName"], "count": 0})
        k["count"] += 1
    groups = []
    for ch in sorted(agg.keys(), key=_ch_order):
        g = agg[ch]
        kps = sorted(g["kps"].values(), key=lambda x: (-x["count"], x["name"] or ""))
        groups.append({"chapter": ch, "total": g["total"], "kpCount": len(kps), "kps": kps})

    # 列表筛选：先按知识点，再按章节
    if kpId:
        items = [it for it in items if it["kpId"] == kpId]
    if chapter:
        items = [it for it in items if it["chapter"] == chapter]

    total = len(items)
    start = (page - 1) * size
    payload = list_response(items[start:start + size], total)
    payload["groups"] = groups
    payload["totalWrong"] = len(items)
    return ok(payload)


@router.get("/wrong-book/{q_id}/detail")
def wrong_detail(
    q_id: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    course_id: str = Depends(get_current_course_id),
):
    """错题详情"""
    q = db.query(Question).filter(
        Question.q_id == q_id,
        Question.course_id == course_id,
    ).first()
    if not q:
        return fail("错题不存在或已移除", 404)
    class_rate, avg_sec, wrong_count, total_count = _calc_question_stats(db, q.q_id, course_id)

    # 推荐资源：按知识点所属章节匹配本地资源
    kp_path = loads(q.kp_path) or []
    chapter = kp_path[0] if kp_path else ""
    res_q = db.query(Resource).filter(Resource.course_id == q.course_id)
    if chapter:
        res_q = res_q.filter(Resource.kp == chapter)
    elif q.kp_id:
        res_q = res_q.filter((Resource.kp_id == q.kp_id) |
                              (Resource.title.like(f"%{q.kp_id}%")))
    resources = [
        {
            "resId": r.res_id, "type": r.type, "title": r.title,
            "name": r.title,
            "meta": r.duration or (f"{r.pages} 页" if r.pages else "本地资源"),
            "url": r.url or "",
        }
        for r in res_q.order_by(Resource.type).limit(4).all()
    ]

    return ok({
        "qId": q.q_id, "type": q.type, "difficulty": q.difficulty, "score": q.score,
        "stem": q.stem, "options": loads(q.options) or [],
        "answer": q.answer, "analysis": q.analysis,
        "kpPath": loads(q.kp_path) or [], "kpId": q.kp_id,
        "preKp": loads(q.pre_kp) or [], "isKey": bool(q.is_key),
        "figure": _figure_of(q),
        "classCorrectRate": class_rate, "avgSeconds": avg_sec,
        "wrongCount": wrong_count, "totalCount": total_count,
        "history": [], "similar": [], "resources": resources,
        "tips": "",
    })


@router.delete("/wrong-book/{q_id}")
def remove_wrong(
    q_id: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    course_id: str = Depends(get_current_course_id),
):
    """标记已掌握：把该题的错题记录置为 mastered=True（保留历史，不再移出）"""
    db.query(AnswerRecord).filter(
        AnswerRecord.user_id == user.user_id,
        AnswerRecord.course_id == course_id,
        AnswerRecord.q_id == q_id,
        AnswerRecord.is_correct == 0,
    ).update({"mastered": True})
    db.commit()
    return ok({"qId": q_id, "mastered": True})
