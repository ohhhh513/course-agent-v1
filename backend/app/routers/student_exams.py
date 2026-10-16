"""学生端已发布试卷测验；尝试与标准答题记录复用现有数据库表。"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_course_id, require_student
from app.middleware.auth import get_current_user
from app.models.graph import GraphNode
from app.models.intervention import TeacherClassDashboard
from app.models.practice import AnswerRecord, PracticeSession
from app.models.question import Question
from app.models.user import User
from app.models.user_course import UserCourse
from app.schemas.common import ok
from app.services.blank_questions import clip, grade_submission, is_blank_type, student_view
from app.services.exam_papers import DATA_TYPE as PAPER_DATA_TYPE

ATTEMPT_DATA_TYPE = "exam_attempt"

router = APIRouter(
    prefix="/api/v1/practice/exams",
    tags=["学生试卷测验"],
    dependencies=[Depends(require_student)],
)


class SaveExamAnswer(BaseModel):
    itemId: str = Field(min_length=1, max_length=64)
    answer: str = Field(default="", max_length=10000)
    durationSeconds: int = Field(default=0, ge=0, le=86400)


def _data(row: TeacherClassDashboard) -> dict:
    try:
        value = json.loads(row.data_json or "{}")
        return value if isinstance(value, dict) else {}
    except (TypeError, ValueError):
        return {}


def _paper_rows(db: Session, course_id: str):
    return db.query(TeacherClassDashboard).filter(
        TeacherClassDashboard.data_type == PAPER_DATA_TYPE,
        func.json_extract(TeacherClassDashboard.data_json, "$.courseId") == course_id,
        func.json_extract(TeacherClassDashboard.data_json, "$.status") == "published",
    ).order_by(TeacherClassDashboard.updated_at.desc()).all()


def _attempt_rows(db: Session, user_id: str, course_id: str):
    return db.query(TeacherClassDashboard).filter(
        TeacherClassDashboard.data_type == ATTEMPT_DATA_TYPE,
        func.json_extract(TeacherClassDashboard.data_json, "$.userId") == user_id,
        func.json_extract(TeacherClassDashboard.data_json, "$.courseId") == course_id,
    ).order_by(func.json_extract(TeacherClassDashboard.data_json, "$.finishedAt").desc(),
               TeacherClassDashboard.updated_at.desc(), TeacherClassDashboard.id.desc()).all()


def _kp_names(db: Session, course_id: str) -> dict[str, str]:
    return dict(db.query(GraphNode.id, GraphNode.name).filter(
        GraphNode.course_id == course_id,
        GraphNode.graph_type == "knowledge",
    ).all())


def _paper_kps(paper: dict, names: dict[str, str]) -> list[dict]:
    seen, result = set(), []
    for item in paper.get("items", []):
        question = item.get("question") or {}
        for kp_id in question.get("kpIds") or []:
            kp_id = str(kp_id or "")
            if kp_id and kp_id not in seen:
                seen.add(kp_id)
                result.append({"kpId": kp_id, "name": names.get(kp_id, kp_id)})
    return result


def _paper_attempt_summary(rows: list[TeacherClassDashboard], paper_id: str) -> dict:
    matching = [_data(row) for row in rows if _data(row).get("paperId") == paper_id]
    if not matching:
        return {"attemptCount": 0, "lastScore": None, "lastAccuracy": None,
                "lastAttemptAt": "", "lastAttemptId": "", "inProgress": False}
    finished = [attempt for attempt in matching if attempt.get("status") == "finished"]
    running = next((attempt for attempt in matching if attempt.get("status") == "running"), None)
    latest = finished[0] if finished else {}
    result = latest.get("result") or {}
    return {
        "attemptCount": len(finished),
        "lastScore": result.get("score"),
        "lastAccuracy": result.get("accuracy"),
        "lastAttemptAt": latest.get("finishedAt") or "",
        "inProgress": running is not None,
        "attemptId": running.get("attemptId", "") if running else "",
        "lastAttemptId": latest.get("attemptId", ""),
    }


def _class_ranking(db: Session, user: User, course_id: str, paper_id: str) -> dict:
    """仅排名当前课程同班学生，历史重测取最近一次已完成记录。"""
    class_name = (user.class_name or "").strip()
    empty = {"className": class_name, "classSize": 0, "testedCount": 0, "rank": None, "list": []}
    if not class_name:
        return {**empty, "message": "尚未设置班级，暂时无法查看班级排名"}
    students = db.query(User).join(UserCourse, UserCourse.user_id == User.user_id).filter(
        User.role == "student", User.class_name == user.class_name,
        UserCourse.course_id == course_id, UserCourse.role_in_course == "student",
    ).order_by(User.student_no, User.user_id).all()
    if not students:
        return empty
    # 使用子查询限定学生归属，避免大班级生成过多 IN 参数。
    members = db.query(UserCourse.user_id).join(User, User.user_id == UserCourse.user_id).filter(
        User.role == "student", User.class_name == user.class_name,
        UserCourse.course_id == course_id, UserCourse.role_in_course == "student",
    )
    attempts = db.query(TeacherClassDashboard).filter(
        TeacherClassDashboard.data_type == ATTEMPT_DATA_TYPE,
        func.json_extract(TeacherClassDashboard.data_json, "$.courseId") == course_id,
        func.json_extract(TeacherClassDashboard.data_json, "$.paperId") == paper_id,
        func.json_extract(TeacherClassDashboard.data_json, "$.status") == "finished",
        func.json_extract(TeacherClassDashboard.data_json, "$.userId").in_(members),
    ).order_by(func.json_extract(TeacherClassDashboard.data_json, "$.finishedAt").desc(),
               TeacherClassDashboard.updated_at.desc(), TeacherClassDashboard.id.desc()).all()
    latest = {}
    for row in attempts:
        attempt = _data(row)
        if isinstance(attempt.get("result"), dict):
            latest.setdefault(attempt.get("userId"), attempt["result"])
    tested, pending = [], []
    for student in students:
        result = latest.get(student.user_id)
        entry = {"name": student.name, "studentNo": student.student_no or "",
                 "isMe": student.user_id == user.user_id, "rank": None,
                 "status": "finished" if result else "pending", "score": None,
                 "totalScore": None, "durationSeconds": None}
        if result:
            entry.update(score=result.get("score", 0), totalScore=result.get("totalScore", 0),
                         durationSeconds=result.get("durationSeconds", 0))
            tested.append(entry)
        else:
            pending.append(entry)
    tested.sort(key=lambda item: (-float(item["score"] or 0), int(item["durationSeconds"] or 0)))
    previous, rank = None, None
    for index, entry in enumerate(tested, 1):
        key = (entry["score"], entry["durationSeconds"])
        if key != previous:
            rank = index
        entry["rank"] = rank
        previous = key
    entries = tested + pending
    mine = next((entry for entry in entries if entry["isMe"]), {})
    return {"className": class_name, "classSize": len(students), "testedCount": len(tested),
            "rank": mine.get("rank"), "list": entries}


def _result_response(db: Session, user: User, course_id: str, attempt: dict) -> dict:
    ranking = _class_ranking(db, user, course_id, attempt.get("paperId", ""))
    return {**attempt["result"], "attemptId": attempt.get("attemptId", ""),
            "ranking": {key: value for key, value in ranking.items() if key != "list"}}


def _list_item(db: Session, course_id: str, paper: dict,
               attempts: list[TeacherClassDashboard], names: dict[str, str]) -> dict:
    summary = _paper_attempt_summary(attempts, paper.get("paperId", ""))
    return {
        "paperId": paper.get("paperId", ""),
        "title": paper.get("title") or "未命名试卷",
        "totalScore": paper.get("totalScore", 100),
        "questionCount": len(paper.get("items") or []),
        "knowledgePoints": _paper_kps(paper, names),
        "revision": paper.get("revision", 0),
        **summary,
    }


def _student_item(item: dict, kp_names: dict[str, str]) -> dict:
    question = item.get("question") or {}
    shown = student_view(
        question.get("type", "single"), question.get("stem", ""),
        question.get("options") or [], question.get("answer", ""),
    )
    # student_view 对选择题会附带 answer 和选项 right 标记；交卷前必须全部剥离。
    options = [{"key": o.get("key", ""), "text": o.get("text", "")}
               for o in shown.get("options", []) if isinstance(o, dict)]
    kp_ids = list(dict.fromkeys(str(x) for x in question.get("kpIds") or [] if str(x)))
    kp_path = ([question.get("chapterName")] if question.get("chapterName") else []) + [
        kp_names.get(kp_id, kp_id) for kp_id in kp_ids
    ]
    return {
        "itemId": item.get("id", ""),
        "qId": item.get("sourceQId", ""),
        "score": item.get("score", 0),
        "type": shown.get("type", question.get("type", "single")),
        "stem": question.get("stem", ""),
        "options": options,
        "blanks": shown.get("blanks", []),
        "kpIds": kp_ids,
        "kpNames": [kp_names.get(kp_id, kp_id) for kp_id in kp_ids],
        "kpPath": kp_path,
        "chapter": question.get("chapterName") or "未分章",
        "difficulty": question.get("difficulty", 3),
        "figure": question.get("figureJson"),
    }


def _attempt_response(attempt: dict, kp_names: dict[str, str]) -> dict:
    elapsed = max(0, int((datetime.now(timezone.utc) - datetime.fromisoformat(
        attempt["startedAt"].replace("Z", "+00:00")).astimezone(timezone.utc)).total_seconds()))
    questions = [_student_item(item, kp_names) for item in attempt.get("items", [])]
    saved_answers = attempt.get("answers") or {}
    answers = {key: value.get("answer", "") for key, value in saved_answers.items()}
    durations = {key: max(0, int(value.get("durationSeconds", 0) or 0))
                 for key, value in saved_answers.items()}
    return {
        "attemptId": attempt.get("attemptId", ""),
        "sessionId": attempt.get("sessionId", ""),
        "paperId": attempt.get("paperId", ""),
        "title": attempt.get("title", ""),
        "totalScore": attempt.get("totalScore", 0),
        "startedAt": attempt.get("startedAt", ""),
        "elapsedSeconds": elapsed,
        "status": attempt.get("status", "running"),
        "questions": questions,
        "answers": answers,
        "durations": durations,
    }


def _owned_attempt(db: Session, attempt_id: str, user: User, course_id: str):
    row = db.query(TeacherClassDashboard).filter(
        TeacherClassDashboard.data_type == ATTEMPT_DATA_TYPE,
        TeacherClassDashboard.data_key == attempt_id,
        func.json_extract(TeacherClassDashboard.data_json, "$.userId") == user.user_id,
        func.json_extract(TeacherClassDashboard.data_json, "$.courseId") == course_id,
    ).first()
    if not row:
        raise HTTPException(404, "试卷测验记录不存在或已切换课程")
    return row, _data(row)


def _grade(question: dict, answer: str) -> tuple[bool, str, list]:
    q_type = question.get("type", "single")
    if is_blank_type(q_type):
        graded = grade_submission(
            question.get("stem", ""), question.get("options") or [],
            question.get("answer", ""), answer,
        )
        return bool(graded["correct"]), graded["display"], graded["results"]
    correct_answer = re_normalize_answer(question.get("answer", ""), q_type)
    mine = re_normalize_answer(answer, q_type)
    return mine == correct_answer, correct_answer, []


def re_normalize_answer(value: str, q_type: str) -> str:
    text = str(value or "").strip().upper()
    if q_type == "multi":
        return "".join(sorted(set(ch for ch in text if ch in "ABCDEFGH")))
    return text


@router.get("")
def list_published_exams(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    course_id: str = Depends(get_current_course_id),
):
    attempts = _attempt_rows(db, user.user_id, course_id)
    names = _kp_names(db, course_id)
    papers = [_data(row) for row in _paper_rows(db, course_id)]
    items = [_list_item(db, course_id, paper, attempts, names) for paper in papers
             if paper.get("paperId")]
    return ok({"list": items, "total": len(items)})


@router.get("/attempts/{attempt_id}")
def read_exam_result(
    attempt_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    course_id: str = Depends(get_current_course_id),
):
    _, attempt = _owned_attempt(db, attempt_id, user, course_id)
    if attempt.get("status") != "finished" or not isinstance(attempt.get("result"), dict):
        raise HTTPException(409, "测验尚未结算，暂时无法查看作答详情")
    return ok(_result_response(db, user, course_id, attempt))


@router.get("/{paper_id}/ranking")
def read_exam_ranking(
    paper_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    course_id: str = Depends(get_current_course_id),
):
    paper = db.query(TeacherClassDashboard.id).filter(
        TeacherClassDashboard.data_type == PAPER_DATA_TYPE,
        TeacherClassDashboard.data_key == paper_id,
        func.json_extract(TeacherClassDashboard.data_json, "$.courseId") == course_id,
        func.json_extract(TeacherClassDashboard.data_json, "$.status") == "published",
    ).first()
    if not paper:
        raise HTTPException(404, "已发布试卷不存在或不属于当前课程")
    return ok(_class_ranking(db, user, course_id, paper_id))


@router.post("/{paper_id}/attempts")
def start_exam_attempt(
    paper_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    course_id: str = Depends(get_current_course_id),
):
    paper_row = db.query(TeacherClassDashboard).filter(
        TeacherClassDashboard.data_type == PAPER_DATA_TYPE,
        TeacherClassDashboard.data_key == paper_id,
        func.json_extract(TeacherClassDashboard.data_json, "$.courseId") == course_id,
        func.json_extract(TeacherClassDashboard.data_json, "$.status") == "published",
    ).first()
    if not paper_row:
        raise HTTPException(404, "已发布试卷不存在或不属于当前课程")
    paper = _data(paper_row)

    previous_rows = _attempt_rows(db, user.user_id, course_id)
    if any(_data(row).get("paperId") == paper_id and _data(row).get("status") == "finished"
           for row in previous_rows):
        raise HTTPException(409, "此试卷已完成，请查看作答详情，不支持重新测验")
    running_rows = [row for row in previous_rows
                    if (lambda d: d.get("paperId") == paper_id and d.get("status") == "running")(_data(row))]
    if running_rows:
        return ok(_attempt_response(_data(running_rows[0]), _kp_names(db, course_id)))

    normalized_items = []
    for item in paper.get("items", []):
        question = item.get("question") or {}
        qid = str(item.get("sourceQId") or "")
        if not qid or not db.query(Question.q_id).filter(
                Question.q_id == qid, Question.course_id == course_id).first():
            raise HTTPException(409, "试卷有题目尚未进入题库，请联系教师重新发布")
        chapter = db.query(GraphNode).filter(
            GraphNode.id == question.get("chapterId"), GraphNode.graph_type == "chapter",
            GraphNode.course_id == course_id,
        ).first() if question.get("chapterId") else None
        question_snapshot = dict(question)
        question_snapshot["chapterName"] = chapter.name if chapter else ""
        normalized_items.append({
            "id": item.get("id", ""), "sourceQId": qid,
            "score": item.get("score", 0), "question": question_snapshot,
        })
    if not normalized_items:
        raise HTTPException(400, "试卷没有可测验的题目")

    attempt_id = "EA" + uuid.uuid4().hex[:24]
    session_id = "PS" + uuid.uuid4().hex[:30]
    now = datetime.now(timezone.utc).isoformat()
    attempt = {
        "attemptId": attempt_id,
        "sessionId": session_id,
        "userId": user.user_id,
        "courseId": course_id,
        "paperId": paper_id,
        "paperRevision": paper.get("revision", 0),
        "title": paper.get("title") or "未命名试卷",
        "totalScore": paper.get("totalScore", 100),
        "status": "running",
        "startedAt": now,
        "finishedAt": "",
        "items": normalized_items,
        "answers": {},
        "result": None,
    }
    snapshot = [{"qId": item["sourceQId"], "type": item["question"].get("type", "single"),
                 "stem": item["question"].get("stem", "")} for item in normalized_items]
    db.add(PracticeSession(
        session_id=session_id, user_id=user.user_id, course_id=course_id,
        mode="exam", total=len(normalized_items), correct=0, wrong=0,
        accuracy=0, duration_seconds=0, status="running",
        questions_snapshot=json.dumps(snapshot, ensure_ascii=False),
    ))
    db.add(TeacherClassDashboard(
        class_id=None, data_type=ATTEMPT_DATA_TYPE,
        data_key=attempt_id, data_json=json.dumps(attempt, ensure_ascii=False),
    ))
    db.commit()
    return ok(_attempt_response(attempt, _kp_names(db, course_id)))


@router.put("/attempts/{attempt_id}/answers")
def save_exam_answer(
    attempt_id: str,
    req: SaveExamAnswer,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    course_id: str = Depends(get_current_course_id),
):
    row, attempt = _owned_attempt(db, attempt_id, user, course_id)
    if attempt.get("status") != "running":
        raise HTTPException(409, "试卷已经结算，不能再修改答案")
    item = next((it for it in attempt.get("items", []) if it.get("id") == req.itemId), None)
    if not item:
        raise HTTPException(404, "题目不属于本次试卷")
    answers = attempt.setdefault("answers", {})
    previous = answers.get(req.itemId) or {}
    answers[req.itemId] = {
        "answer": req.answer,
        "durationSeconds": max(int(previous.get("durationSeconds", 0)), req.durationSeconds),
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }
    encoded = json.dumps(attempt, ensure_ascii=False, allow_nan=False)
    changed = db.query(TeacherClassDashboard).filter(
        TeacherClassDashboard.id == row.id,
        TeacherClassDashboard.data_json == row.data_json,
    ).update({TeacherClassDashboard.data_json: encoded,
              TeacherClassDashboard.updated_at: datetime.utcnow()}, synchronize_session=False)
    if changed != 1:
        db.rollback()
        raise HTTPException(409, "答案已在其它窗口更新，请重新载入试卷")
    db.commit()
    return ok({"itemId": req.itemId, "saved": True})


def _build_result(db: Session, user: User, course_id: str, attempt: dict) -> dict:
    answers = attempt.get("answers") or {}
    result_items, records, correct_count = [], [], 0
    duration_seconds = 0
    for item in attempt.get("items", []):
        qid = item["sourceQId"]
        question = item["question"]
        answer_data = answers.get(item.get("id"), {}) or {}
        mine = str(answer_data.get("answer", ""))
        duration = max(0, int(answer_data.get("durationSeconds", 0) or 0))
        duration_seconds += duration
        correct, right_answer, blank_results = _grade(question, mine)
        qrow = db.query(Question).filter(
            Question.q_id == qid, Question.course_id == course_id,
        ).first()
        if not qrow:
            raise HTTPException(409, "试卷题目已从题库移除，无法保存答题记录")
        if correct:
            correct_count += 1
        records.append(AnswerRecord(
            session_id=attempt["sessionId"], user_id=user.user_id,
            course_id=course_id, q_id=qid, kp_id=qrow.kp_id or "",
            my_answer=clip(mine, 128), correct_answer=clip(right_answer, 128),
            is_correct=1 if correct else 0, duration_seconds=duration,
            error_type="" if correct else (qrow.error_type or ""),
        ))
        result_items.append({
            "itemId": item.get("id", ""), "qId": qid,
            "type": question.get("type", "single"), "stem": question.get("stem", ""),
            "options": question.get("options") or [], "myAnswer": mine,
            "correctAnswer": right_answer, "correct": correct,
            "score": float(item.get("score", 0) or 0),
            "earnedScore": float(item.get("score", 0) or 0) if correct else 0,
            "analysis": question.get("analysis", ""),
            "chapter": question.get("chapterName") or "未分章",
            "kpIds": question.get("kpIds") or [],
            "difficulty": question.get("difficulty", 3),
            "figure": question.get("figureJson"),
            "blankResults": blank_results,
        })
    total = len(result_items)
    score = round(sum(item["earnedScore"] for item in result_items), 1)
    accuracy = round(correct_count / total * 100, 1) if total else 0
    session = db.query(PracticeSession).filter(
        PracticeSession.session_id == attempt["sessionId"],
        PracticeSession.user_id == user.user_id,
        PracticeSession.course_id == course_id,
    ).first()
    if not session:
        raise HTTPException(409, "试卷测验会话不存在，无法保存答题记录")

    now = datetime.now(timezone.utc).isoformat()
    elapsed = max(0, int((datetime.now(timezone.utc) - datetime.fromisoformat(
        attempt["startedAt"].replace("Z", "+00:00")).astimezone(timezone.utc)).total_seconds()))
    mastered_count = 0
    for result in result_items:
        if result["correct"]:
            changed = db.query(AnswerRecord).filter(
                AnswerRecord.user_id == user.user_id,
                AnswerRecord.course_id == course_id,
                AnswerRecord.q_id == result["qId"],
                AnswerRecord.is_correct == 0,
                AnswerRecord.mastered.is_(False),
            ).update({"mastered": True}, synchronize_session=False)
            mastered_count += int(changed > 0)
    db.add_all(records)
    session.correct = correct_count
    session.wrong = total - correct_count
    session.accuracy = accuracy
    session.duration_seconds = elapsed or duration_seconds
    session.status = "finished"
    session.finished_at = datetime.utcnow()
    return {
        "paperId": attempt.get("paperId", ""), "title": attempt.get("title", ""),
        "totalScore": attempt.get("totalScore", 0), "score": score,
        "correct": correct_count, "wrong": total - correct_count,
        "total": total, "accuracy": accuracy,
        "durationSeconds": elapsed or duration_seconds,
        "masteredCount": mastered_count,
        "finishedAt": now, "items": result_items,
    }


@router.post("/attempts/{attempt_id}/finish")
def finish_exam_attempt(
    attempt_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    course_id: str = Depends(get_current_course_id),
):
    row, attempt = _owned_attempt(db, attempt_id, user, course_id)
    if attempt.get("status") == "finished" and attempt.get("result"):
        return ok(_result_response(db, user, course_id, attempt))
    if attempt.get("status") != "running":
        raise HTTPException(409, "试卷测验状态不正确")
    result = _build_result(db, user, course_id, attempt)
    attempt["status"] = "finished"
    attempt["finishedAt"] = result["finishedAt"]
    attempt["result"] = result
    encoded = json.dumps(attempt, ensure_ascii=False, allow_nan=False)
    changed = db.query(TeacherClassDashboard).filter(
        TeacherClassDashboard.id == row.id,
        TeacherClassDashboard.data_json == row.data_json,
    ).update({TeacherClassDashboard.data_json: encoded,
              TeacherClassDashboard.updated_at: datetime.utcnow()}, synchronize_session=False)
    if changed != 1:
        db.rollback()
        raise HTTPException(409, "试卷状态已更新，请重新打开记录")
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    try:
        from app.services.alert_detector import detect_alerts
        detect_alerts(db, [user])
    except Exception as exc:  # 答题结果已经提交，预警刷新失败不能撤销成绩。
        db.rollback()
        print(f"[alert-detect] 试卷交卷后刷新跳过（{exc}）")
    return ok(_result_response(db, user, course_id, attempt))
