"""
智能练习接口：/practice/*
"""
import json, uuid
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
from ..schemas.common import ok, fail, list_response
from ..utils import loads, fmt_dt
from sqlalchemy import func

router = APIRouter(prefix="/api/v1/practice", tags=["智能练习"])


def _expand_kp_ids(db: Session, kp_ids: list[str]) -> set[str]:
    """把细粒度知识点扩展到同章节的其它知识点。

    课后题库（KHD）按“章代表知识点”挂载，细分知识点（如 KP02 时间复杂度）题量很少，
    直接按其 kp_id 组卷往往只有一两道；这里按章节扩到同章其它知识点，凑足同主题题量。
    """
    kp_ids = [k for k in kp_ids if k]
    if not kp_ids:
        return set()
    kps = set(kp_ids)
    rows = db.query(GraphNode).filter(
        GraphNode.graph_type == "knowledge", GraphNode.id.in_(kp_ids)
    ).all()
    chapters = {r.chapter for r in rows if r.chapter}
    if chapters:
        extra = db.query(GraphNode.id).filter(
            GraphNode.graph_type == "knowledge", GraphNode.chapter.in_(chapters)
        ).all()
        kps |= {r[0] for r in extra}
    return kps


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
def _calc_question_stats(db: Session, q_id: str):
    """基于 answer_records 返回班级正确率、平均用时、错误数、总答题数"""
    total, correct, avg_dur = db.query(
        func.count(AnswerRecord.id),
        func.sum(AnswerRecord.is_correct),
        func.avg(AnswerRecord.duration_seconds),
    ).filter(AnswerRecord.q_id == q_id).first()
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
):
    # 题库总题数
    total_qs = db.query(Question).filter(Question.status == "published").count()
    # 当前用户错题数（答题记录中 is_correct=0）
    wrong_count = db.query(AnswerRecord).filter(
        AnswerRecord.user_id == user.user_id,
        AnswerRecord.is_correct == 0,
    ).count()

    base = [
        {"key": "weak", "name": "薄弱点强化", "desc": "系统按掌握率自动组卷，命中薄弱知识点", "icon": "target", "recommend": True},
        {"key": "order", "name": "顺序练习", "desc": "按章节与知识点前后置顺序逐题推进", "icon": "list"},
        {"key": "random", "name": "随机练习", "desc": "在已学范围内随机抽题，检验综合掌握", "icon": "shuffle"},
        {"key": "wrong", "name": "错题重练", "desc": "重做历史错题，验证是否真正掌握", "icon": "refresh"},
    ]
    for m in base:
        key = m["key"]
        cap = {"weak": total_qs, "order": total_qs, "random": total_qs, "wrong": wrong_count}[key]
        m["count"] = min(_BASE_COUNTS[key], cap)
        if cap == 0:
            m["count"] = 0
    return ok(base)


@router.post("/sessions")
def create_session(
    req: CreateSessionReq,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """创建练习会话（组卷）"""
    q = db.query(Question).filter(Question.status == "published")
    if req.qIds:
        # 重做指定题目（错题本“重做本题”）
        q = q.filter(Question.q_id.in_(req.qIds))
    elif req.kpIds:
        expanded = _expand_kp_ids(db, req.kpIds)
        if expanded:
            q = q.filter(Question.kp_id.in_(expanded))
        else:
            print(f"[practice] 未识别 kpIds={req.kpIds}，回退为全库", flush=True)
    elif req.mode == "wrong":
        # 错题重练：只抽该用户错过的题
        wrong_q_ids = [r[0] for r in db.query(AnswerRecord.q_id).filter(
            AnswerRecord.user_id == user.user_id,
            AnswerRecord.is_correct == 0,
        ).distinct().all()]
        if wrong_q_ids:
            q = q.filter(Question.q_id.in_(wrong_q_ids))
    if req.difficulty:
        q = q.filter(Question.difficulty == req.difficulty)
    # 简单随机抽样（真实环境按 mode 智能组卷）
    import random
    all_qs = q.all()
    count = min(req.count, len(all_qs))
    picked = random.sample(all_qs, count) if all_qs else []

    # 同一模式只保留一个进行中「存档」：新开练习时，把旧的 running 会话标记为 abandoned
    db.query(PracticeSession).filter(
        PracticeSession.user_id == user.user_id,
        PracticeSession.mode == req.mode,
        PracticeSession.status == "running",
    ).update({"status": "abandoned"})

    session_id = "PS" + uuid.uuid4().hex[:10]
    session = PracticeSession(
        session_id=session_id,
        user_id=user.user_id,
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
):
    """取当前进行中的练习存档（用于「继续挑战」）；无则返回 null"""
    session = (
        db.query(PracticeSession)
        .filter(PracticeSession.user_id == user.user_id,
                PracticeSession.mode == mode,
                PracticeSession.status == "running")
        .order_by(PracticeSession.created_at.desc())
        .first()
    )
    if not session:
        return ok(None)
    q_ids = [x.get("qId") for x in (loads(session.questions_snapshot) or []) if x.get("qId")]
    rows = {q.q_id: q for q in db.query(Question).filter(Question.q_id.in_(q_ids)).all()}
    answered = {r.q_id: r for r in db.query(AnswerRecord).filter(
        AnswerRecord.session_id == session.session_id).all()}
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
):
    """取题"""
    session = db.query(PracticeSession).filter(PracticeSession.session_id == session_id).first()
    if not session:
        return fail("会话不存在", 404)
    q_ids = [x["qId"] for x in loads(session.questions_snapshot) or []]
    rows = db.query(Question).filter(Question.q_id.in_(q_ids)).all()
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
):
    """提交单题作答 —— 即时判分 + 解析"""
    question = db.query(Question).filter(Question.q_id == req.qId).first()
    if not question:
        return fail("题目不存在", 404)

    # 越权校验：作答必须属于当前登录用户的练习会话
    session = db.query(PracticeSession).filter(PracticeSession.session_id == req.sessionId).first()
    if not session:
        return fail("练习会话不存在", 404)
    if session.user_id != user.user_id:
        return fail("无权操作他人练习会话", 403)

    correct = req.answer == question.answer

    # 保存答题记录
    record = AnswerRecord(
        session_id=req.sessionId,
        user_id=user.user_id,
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
    session = db.query(PracticeSession).filter(PracticeSession.session_id == req.sessionId).first()
    if session:
        if correct:
            session.correct = (session.correct or 0) + 1
        else:
            session.wrong = (session.wrong or 0) + 1
    db.commit()

    # 动态统计：该题真实班级正确率、平均用时
    class_rate, avg_sec, _, _ = _calc_question_stats(db, question.q_id)
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
):
    """结束练习，返回练习报告"""
    from ..models.graph import LearningPath
    session = db.query(PracticeSession).filter(PracticeSession.session_id == session_id).first()
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
    records = db.query(AnswerRecord).filter(AnswerRecord.session_id == session_id).all()

    # 错题知识点分布（题库无「错误类型」字段，改用真实数据：错题按 kp_id 汇总）
    wrong_by_kp = {}
    for r in records:
        if not r.is_correct and r.kp_id:
            wrong_by_kp[r.kp_id] = wrong_by_kp.get(r.kp_id, 0) + 1
    wrong_kp_names = {}
    if wrong_by_kp:
        wrong_kp_names = dict(db.query(GraphNode.id, GraphNode.name).filter(
            GraphNode.graph_type == "knowledge",
            GraphNode.id.in_(list(wrong_by_kp.keys())),
        ).all())
    wrong_by_kp_list = [
        {"kpId": k, "name": wrong_kp_names.get(k, k), "count": c}
        for k, c in sorted(wrong_by_kp.items(), key=lambda kv: -kv[1])
    ]

    # 真实用时：所有 answer_records.duration_seconds 求和
    duration_seconds = sum((r.duration_seconds or 0) for r in records)
    total_answered = len(records) or 1
    avg_seconds = round(duration_seconds / total_answered, 1)

    # kpChanges：练习涉及的 kp，取当前 mastery；delta 按本次练习该 kp 的答题表现累加
    kp_ids_in_session = list({r.kp_id for r in records if r.kp_id})
    kp_changes = []
    if kp_ids_in_session:
        lps = db.query(LearningPath).filter(
            LearningPath.user_id == user.user_id,
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
                    q = db.query(Question).filter(Question.q_id == r.q_id).first()
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
        AnswerRecord.q_id.in_(q_ids)
    ).first()
    total_ans, correct_ans = qid_total or (0, 0)
    class_acc = round((correct_ans or 0) / (total_ans or 1) * 100, 1)

    # 得分变化：按每题分值累加（答对+score，答错0）
    q_score_map = {q.q_id: q.score for q in db.query(Question).filter(Question.q_id.in_(q_ids)).all()}
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
    mastered: str = Query(None),   # 'true' / 'false'
    page: int = Query(1),
    size: int = Query(20),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """错题本"""
    # 从答题记录中取错题
    q = db.query(AnswerRecord).filter(
        AnswerRecord.user_id == user.user_id,
        AnswerRecord.is_correct == 0,
    )
    if kpId:
        q = q.filter(AnswerRecord.kp_id == kpId)
    records = q.order_by(AnswerRecord.created_at.desc()).all()

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

    if wrong_map:
        q_ids = list(wrong_map.keys())
        questions = db.query(Question).filter(Question.q_id.in_(q_ids)).all()
        items = []
        for q in questions:
            w = wrong_map[q.q_id]
            if filter_flag is not None and w["mastered"] != filter_flag:
                continue
            items.append({
                "qId": q.q_id, "stem": q.stem, "myAnswer": w["myAnswer"],
                "answer": q.answer,
                "wrongCount": w["wrongCount"],
                "kp": q.kp_id, "kpId": q.kp_id,
                "difficulty": q.difficulty,
                "lastTime": fmt_dt(w["lastTime"], "%m-%d %H:%M"),
                "mastered": w["mastered"],
            })
    else:
        items = []

    total = len(items)
    start = (page - 1) * size
    return ok(list_response(items[start:start + size], total))


@router.get("/wrong-book/{q_id}/detail")
def wrong_detail(
    q_id: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """错题详情"""
    q = db.query(Question).filter(Question.q_id == q_id).first()
    if not q:
        return fail("错题不存在或已移除", 404)
    class_rate, avg_sec, wrong_count, total_count = _calc_question_stats(db, q.q_id)

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
):
    """标记已掌握：把该题的错题记录置为 mastered=True（保留历史，不再移出）"""
    db.query(AnswerRecord).filter(
        AnswerRecord.user_id == user.user_id,
        AnswerRecord.q_id == q_id,
        AnswerRecord.is_correct == 0,
    ).update({"mastered": True})
    db.commit()
    return ok({"qId": q_id, "mastered": True})
