"""试卷作答只读聚合；按课程学生的最近一次已结算快照统计。"""
from __future__ import annotations

import json
from collections import OrderedDict

from sqlalchemy import func

from app.models.graph import GraphNode
from app.models.intervention import TeacherClassDashboard
from app.models.user import User
from app.models.user_course import UserCourse
from app.services.blank_questions import grade_submission, load_specs, student_parts


def course_students(db, course_id):
    return db.query(User).join(UserCourse, UserCourse.user_id == User.user_id).filter(
        UserCourse.course_id == course_id, UserCourse.role_in_course == "student",
        User.role == "student",
    ).order_by(User.student_no, User.user_id).all()


def latest_submissions(db, course_id, paper_id):
    rows = db.query(TeacherClassDashboard).join(
        User, User.user_id == func.json_extract(TeacherClassDashboard.data_json, "$.userId"),
    ).join(UserCourse, UserCourse.user_id == User.user_id).filter(
        User.role == "student", UserCourse.course_id == course_id, UserCourse.role_in_course == "student",
        TeacherClassDashboard.data_type == "exam_attempt",
        func.json_extract(TeacherClassDashboard.data_json, "$.courseId") == course_id,
        func.json_extract(TeacherClassDashboard.data_json, "$.paperId") == paper_id,
        func.json_extract(TeacherClassDashboard.data_json, "$.status") == "finished",
    ).order_by(func.json_extract(TeacherClassDashboard.data_json, "$.finishedAt").desc(),
               TeacherClassDashboard.updated_at.desc(), TeacherClassDashboard.id.desc()).all()
    latest = {}
    for row in rows:
        value = json.loads(row.data_json)
        if isinstance(value.get("result"), dict):
            latest.setdefault(value.get("userId"), value)
    return latest


def rank_class(students, submissions, class_name):
    members = [student for student in students if (student.class_name or "") == class_name]
    if not class_name:
        return {"className": "", "classSize": len(members), "testedCount": 0, "list": [],
                "message": "学生尚未设置班级，暂时无法计算班级排名"}
    tested, pending = [], []
    for student in members:
        attempt = submissions.get(student.user_id)
        result = attempt["result"] if attempt else None
        entry = {"userId": student.user_id, "name": student.name, "studentNo": student.student_no or "",
                 "status": "finished" if result else "pending", "rank": None,
                 "score": result.get("score", 0) if result else None,
                 "totalScore": result.get("totalScore", 0) if result else None,
                 "durationSeconds": result.get("durationSeconds", 0) if result else None}
        (tested if result else pending).append(entry)
    tested.sort(key=lambda item: (-float(item["score"] or 0), int(item["durationSeconds"] or 0)))
    previous, rank = None, None
    for index, entry in enumerate(tested, 1):
        key = (entry["score"], entry["durationSeconds"])
        if key != previous:
            rank = index
        entry["rank"] = rank
        previous = key
    return {"className": class_name, "classSize": len(members), "testedCount": len(tested),
            "list": tested + pending}


def student_summary(student, submissions):
    attempt = submissions.get(student.user_id)
    return {"userId": student.user_id, "name": student.name, "studentNo": student.student_no or "",
            "className": student.class_name or "", "status": "finished" if attempt else "pending"}


def _question_key(item):
    question = item.get("question") or {}
    # 章节显示名不参与区分；实际题干、选项、答案或分值改变时按独立快照统计。
    snapshot = {key: value for key, value in question.items() if key != "chapterName"}
    return json.dumps({"id": item.get("id"), "score": float(item.get("score", 0) or 0), "question": snapshot},
                      sort_keys=True, ensure_ascii=False)


def paper_statistics(db, course_id, paper, students, submissions):
    names = {node.id: node.name for node in db.query(GraphNode).filter(GraphNode.course_id == course_id).all()}
    groups = OrderedDict()

    def group_for(item, index, historical=False):
        key = _question_key(item)
        if key not in groups:
            question = item.get("question") or {}
            blank = question.get("type") == "blank"
            answer = str(question.get("answer") or "").upper()
            options = [] if blank else [{"key": option.get("key", ""), "text": option.get("text", ""),
                                        "right": str(option.get("key", "")).upper() in answer, "count": 0}
                                       for option in question.get("options") or []]
            specs = load_specs(question.get("stem", ""), question.get("options"), question.get("answer", "")) if blank else []
            groups[key] = {"number": index + 1, "itemId": item.get("id", ""), "historical": historical,
                           "type": question.get("type", "single"), "stem": question.get("stem", ""),
                           "score": item.get("score", 0), "chapter": question.get("chapterName") or names.get(question.get("chapterId"), "未分章"),
                           "kpNames": [names.get(kp, kp) for kp in question.get("kpIds") or []],
                           "answer": question.get("answer", ""), "analysis": question.get("analysis", ""),
                           "figure": question.get("figureJson"), "options": options, "respondentCount": 0,
                           "correctCount": 0, "unansweredCount": 0,
                           "blanks": [{"index": spec["blank"], "accept": spec["accept"], "correctCount": 0,
                                       "wrongCount": 0, "unansweredCount": 0} for spec in specs]}
        return groups[key]

    for index, item in enumerate(paper.get("items") or []):
        group_for(item, index)
    for attempt in submissions.values():
        results = {item.get("itemId"): item for item in attempt["result"].get("items") or []}
        for index, item in enumerate(attempt.get("items") or []):
            group = group_for(item, index, True)
            result = results.get(item.get("id"))
            if result is None:
                continue
            group["respondentCount"] += 1
            group["correctCount"] += bool(result.get("correct"))
            raw = str(result.get("myAnswer") or "")
            if group["type"] == "blank":
                parts = student_parts(raw, len(group["blanks"]))
                question = item["question"]
                graded = grade_submission(question.get("stem", ""), question.get("options"), question.get("answer", ""), raw)
                group["unansweredCount"] += not any(parts)
                for counts, part, grade in zip(group["blanks"], parts, graded["results"]):
                    counts["correctCount"] += bool(grade["correct"])
                    counts["wrongCount"] += bool(part) and not grade["correct"]
                    counts["unansweredCount"] += not bool(part)
            else:
                selected = set(raw.strip().upper())
                group["unansweredCount"] += not bool(raw.strip())
                for option in group["options"]:
                    option["count"] += option["key"].upper() in selected
    scores = [float(attempt["result"].get("score", 0) or 0) for attempt in submissions.values()]
    return {"paperId": paper["paperId"], "title": paper.get("title", ""), "totalScore": paper.get("totalScore", 0),
            "summary": {"submittedCount": len(scores), "averageScore": round(sum(scores) / len(scores), 1) if scores else None,
                        "highestScore": max(scores) if scores else None, "lowestScore": min(scores) if scores else None},
            "students": [student_summary(student, submissions) for student in students],
            "classes": sorted({student.class_name for student in students if student.class_name}),
            "questions": list(groups.values())}
