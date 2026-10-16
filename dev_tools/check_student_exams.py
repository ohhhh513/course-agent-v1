"""学生试卷测验端到端验收；先只读复制数据库，测试写入只发生在临时副本。"""
from pathlib import Path
from contextlib import ExitStack
import hashlib
import json
import os
import sqlite3
import sys
import tempfile

REPO = Path(__file__).resolve().parents[1]


def main():
    source = REPO / "backend/app/data/course_agent.db"
    if not source.is_file():
        raise SystemExit("缺少 backend/app/data/course_agent.db；请按 AGENTS.md 将演示数据库放到该路径后重试。")
    original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix="student-exams-") as folder, ExitStack() as cleanup:
        target = Path(folder) / "course_agent.db"
        src = sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)
        dst = sqlite3.connect(target)
        try:
            src.backup(dst)
        finally:
            src.close()
            dst.close()
        os.environ["DATABASE_URL"] = "sqlite:///" + target.as_posix()
        os.environ["JWT_SECRET"] = "student-exam-check-temporary-secret"
        os.environ["DEBUG"] = "0"
        sys.path.insert(0, str(REPO / "backend"))

        from fastapi.testclient import TestClient
        from app.main import app
        from app.database import SessionLocal, engine
        cleanup.callback(engine.dispose)
        from app.models.course import Course
        from app.models.graph import GraphNode
        from app.models.intervention import TeacherClassDashboard
        from app.models.practice import AnswerRecord, PracticeSession
        from app.models.question import Question
        from app.models.user import User
        from app.models.user_course import UserCourse
        from app.middleware.auth import create_jwt, hash_password
        from app.routers.student_exams import _grade
        from app.services.scoring import overall_accuracy

        assert _grade({"type": "multi", "answer": "BA"}, "AB")[0], "多选答案顺序不应影响判分"

        db = SessionLocal()
        cleanup.callback(db.close)
        db.add_all([
            User(user_id="ST_EXAM_CHECK", username="st_exam_check", name="试卷学生", role="student", class_name="试卷测试班", password=hash_password("x")),
            User(user_id="TE_EXAM_CHECK", username="te_exam_check", name="试卷教师", role="teacher", password=hash_password("x")),
        ])
        db.flush()
        db.add_all([
            Course(course_id="ST_EXAM_C1", name="试卷测验课程", owner_id="TE_EXAM_CHECK"),
            Course(course_id="ST_EXAM_C2", name="另一门测验课程", owner_id="TE_EXAM_CHECK"),
            UserCourse(user_id="ST_EXAM_CHECK", course_id="ST_EXAM_C1", role_in_course="student"),
            UserCourse(user_id="ST_EXAM_CHECK", course_id="ST_EXAM_C2", role_in_course="student"),
            UserCourse(user_id="TE_EXAM_CHECK", course_id="ST_EXAM_C1", role_in_course="teacher"),
            GraphNode(id="ST_EXAM_CH", graph_type="chapter", course_id="ST_EXAM_C1", name="试卷测验章节"),
            GraphNode(id="ST_EXAM_KP", graph_type="knowledge", course_id="ST_EXAM_C1", name="试卷知识点", chapter="试卷测验章节"),
        ])
        db.add_all([
            Question(q_id="EX_ST_EXAM_Q1", course_id="ST_EXAM_C1", chapter_id="ST_EXAM_CH", chapter="试卷测验章节",
                     kp_id="ST_EXAM_KP", kp_ids='["ST_EXAM_KP"]', type="single", status="published",
                     stem="发布的新题一", options='[{"key":"A","text":"正确项","right":true},{"key":"B","text":"错误项","right":false}]',
                     answer="A", analysis="第一题解析", source_ref_file="exam_paper"),
            Question(q_id="EX_ST_EXAM_Q2", course_id="ST_EXAM_C1", chapter_id="ST_EXAM_CH", chapter="试卷测验章节",
                     kp_id="ST_EXAM_KP", kp_ids='["ST_EXAM_KP"]', type="single", status="published",
                     stem="发布的新题二", options='[{"key":"A","text":"正确项","right":true},{"key":"B","text":"错误项","right":false}]',
                     answer="A", analysis="第二题解析", source_ref_file="exam_paper"),
        ])
        items = []
        for index, qid in enumerate(("EX_ST_EXAM_Q1", "EX_ST_EXAM_Q2"), 1):
            items.append({
                "id": f"exam-item-{index}", "sourceQId": qid, "sourceOrigin": "exam", "score": 50,
                "question": {"stem": f"发布的新题{index}", "type": "single", "difficulty": 3,
                             "chapterId": "ST_EXAM_CH", "kpIds": ["ST_EXAM_KP"],
                             "options": [{"key": "A", "text": "正确项", "right": True},
                                         {"key": "B", "text": "错误项", "right": False}],
                             "answer": "A", "analysis": f"第{index}题解析", "figureJson": None},
            })

        def paper(paper_id, course_id, status="published"):
            payload = {"paperId": paper_id, "title": "数据结构阶段测验" if course_id == "ST_EXAM_C1" else "隔离课程试卷",
                       "courseId": course_id, "userId": "TE_EXAM_CHECK", "status": status,
                       "revision": 1, "totalScore": 100, "items": items if course_id == "ST_EXAM_C1" else []}
            db.add(TeacherClassDashboard(data_type="exam_paper", data_key=paper_id,
                                         data_json=json.dumps(payload, ensure_ascii=False)))

        paper("EP_ST_EXAM_P1", "ST_EXAM_C1")
        paper("EP_ST_EXAM_DRAFT", "ST_EXAM_C1", "draft")
        paper("EP_ST_EXAM_P2", "ST_EXAM_C2")
        db.commit()
        db.close()

        client = TestClient(app)
        cleanup.callback(client.close)
        student = create_jwt("ST_EXAM_CHECK", "student")
        teacher = create_jwt("TE_EXAM_CHECK", "teacher")

        def call(method, path, *, token=student, course="ST_EXAM_C1", expected=200, body=None):
            response = client.request(method, "/api/v1/practice/exams" + path, json=body,
                                      headers={"Authorization": "Bearer " + token, "X-Course-Id": course})
            assert response.status_code == expected, (method, path, response.status_code, response.text)
            if expected == 200:
                payload = response.json()
                assert payload.get("code") == 0, payload
                return payload["data"]
            return response

        listed = call("GET", "")
        assert [p["paperId"] for p in listed["list"]] == ["EP_ST_EXAM_P1"]
        assert listed["list"][0]["knowledgePoints"] == [{"kpId": "ST_EXAM_KP", "name": "试卷知识点"}]
        assert call("GET", "", course="ST_EXAM_C2")["list"][0]["paperId"] == "EP_ST_EXAM_P2"
        call("GET", "", token=teacher, expected=403)

        started = call("POST", "/EP_ST_EXAM_P1/attempts")
        assert started["status"] == "running" and started["totalScore"] == 100
        assert len(started["questions"]) == 2
        assert all("answer" not in q for q in started["questions"])
        assert all("right" not in option for q in started["questions"] for option in q["options"])
        attempt_id = started["attemptId"]
        assert call("POST", "/EP_ST_EXAM_P1/attempts")["attemptId"] == attempt_id, "未完成测验仍可继续"
        call("GET", f"/attempts/{attempt_id}", expected=409)
        db = SessionLocal()
        cleanup.callback(db.close)
        db.add(PracticeSession(session_id="PS_EXAM_OLD_WRONG", user_id="ST_EXAM_CHECK", course_id="ST_EXAM_C1",
                               mode="order", status="finished"))
        db.flush()
        db.add(AnswerRecord(session_id="PS_EXAM_OLD_WRONG", user_id="ST_EXAM_CHECK", course_id="ST_EXAM_C1",
                            q_id="EX_ST_EXAM_Q2", kp_id="ST_EXAM_KP", is_correct=0, mastered=False,
                            my_answer="B", correct_answer="A"))
        db.commit()
        db.close()
        for question, answer in zip(started["questions"], ("B", "A")):
            saved = call("PUT", f"/attempts/{attempt_id}/answers", body={
                "itemId": question["itemId"], "answer": answer, "durationSeconds": 12,
            })
            assert saved["saved"] is True
        first = call("POST", f"/attempts/{attempt_id}/finish")
        assert (first["score"], first["correct"], first["wrong"], first["accuracy"]) == (50, 1, 1, 50)
        assert first["masteredCount"] == 1, "试卷答对仍须同步移出已有错题"
        assert call("POST", f"/attempts/{attempt_id}/finish") == first, "重复结算须幂等"

        db = SessionLocal()
        cleanup.callback(db.close)
        assert db.query(PracticeSession).filter(PracticeSession.session_id == started["sessionId"],
                                                PracticeSession.mode == "exam", PracticeSession.status == "finished").count() == 1
        records = db.query(AnswerRecord).filter(AnswerRecord.session_id == started["sessionId"]).all()
        assert len(records) == 2 and all(r.q_id.startswith("EX_ST_EXAM_Q") for r in records)
        assert overall_accuracy(db, "ST_EXAM_CHECK")["accuracy"] == 50
        db.close()
        wrong = client.get("/api/v1/practice/wrong-book?mastered=false", headers={
            "Authorization": "Bearer " + student, "X-Course-Id": "ST_EXAM_C1"})
        assert wrong.status_code == 200 and wrong.json()["code"] == 0
        assert any(item["qId"] == "EX_ST_EXAM_Q1" for item in wrong.json()["data"]["list"])
        assert all(item["qId"] != "EX_ST_EXAM_Q2" for item in wrong.json()["data"]["list"])

        assert call("GET", f"/attempts/{attempt_id}") == first
        call("GET", f"/attempts/{attempt_id}", token=teacher, expected=403)
        call("GET", f"/attempts/{attempt_id}", course="ST_EXAM_C2", expected=404)
        call("POST", "/EP_ST_EXAM_P1/attempts", expected=409)
        summary = call("GET", "")["list"][0]
        assert summary["lastAttemptId"] == attempt_id and summary["attemptCount"] == 1 and summary["lastScore"] == 50
        db = SessionLocal()
        cleanup.callback(db.close)
        assert overall_accuracy(db, "ST_EXAM_CHECK")["accuracy"] == 50
        assert db.query(AnswerRecord).filter(AnswerRecord.user_id == "ST_EXAM_CHECK").count() == 3

        # 榜单夹具仅写临时副本；包括并列、低分、未测验、异班和未选课学生。
        fixture_students = [("TOP1", "试卷测试班", True), ("TOP2", "试卷测试班", True),
                            ("TIE", "试卷测试班", True), ("LOW", "试卷测试班", True),
                            ("PENDING", "试卷测试班", True), ("OTHERCLASS", "其他班级", True),
                            ("NONMEMBER", "试卷测试班", False), ("NOCLASS", "", True)]
        for uid, class_name, joined in fixture_students:
            db.add(User(user_id=uid, username="exam_" + uid.lower(), name=uid, role="student",
                        class_name=class_name, password="unused"))
            if joined:
                db.add(UserCourse(user_id=uid, course_id="ST_EXAM_C1", role_in_course="student"))

        def finished(uid, suffix, score, duration, finished_at="2026-10-16T12:00:00+00:00", course="ST_EXAM_C1"):
            payload = {"attemptId": "EA_CHECK_" + suffix, "userId": uid, "courseId": course,
                       "paperId": "EP_ST_EXAM_P1", "status": "finished", "finishedAt": finished_at,
                       "result": {"score": score, "durationSeconds": duration, "totalScore": 100}}
            db.add(TeacherClassDashboard(data_type="exam_attempt", data_key=payload["attemptId"],
                                         data_json=json.dumps(payload)))

        duration = first["durationSeconds"]
        finished("TOP1", "top1", 100, 10)
        finished("TOP2", "top2", 100, 10)
        finished("TIE", "tie", 50, duration)
        finished("LOW", "low", 50, duration + 20)
        finished("OTHERCLASS", "otherclass", 100, 1)
        finished("NONMEMBER", "nonmember", 100, 1)
        # 兼容原有历史重测；较旧的高分不能替换最近成绩，即使其数据库更新时间更晚。
        finished("ST_EXAM_CHECK", "old", 100, 1, "2000-01-01T00:00:00+00:00")
        # 同一个试卷标识但课程不一致的记录也不能进入当前榜单。
        finished("LOW", "wrongcourse", 100, 1, "2099-01-01T00:00:00+00:00", "ST_EXAM_C2")
        db.commit()
        before_records = db.query(AnswerRecord).count()
        before_attempts = db.query(TeacherClassDashboard).filter(TeacherClassDashboard.data_type == "exam_attempt").count()
        db.close()

        ranking = call("GET", "/EP_ST_EXAM_P1/ranking")
        assert ranking["classSize"] == 6 and ranking["testedCount"] == 5 and ranking["rank"] == 3, ranking
        assert [entry["rank"] for entry in ranking["list"]] == [1, 1, 3, 3, 5, None]
        assert ranking["list"][-1]["name"] == "PENDING" and ranking["list"][-1]["status"] == "pending"
        assert all("items" not in entry and "answers" not in entry for entry in ranking["list"])
        assert {entry["name"] for entry in ranking["list"]}.isdisjoint({"OTHERCLASS", "NONMEMBER", "NOCLASS"})
        details = call("GET", f"/attempts/{attempt_id}")
        assert details["ranking"]["rank"] == 3 and details["ranking"]["classSize"] == 6
        assert details["items"] == first["items"] and details["score"] == 50
        summary = call("GET", "")["list"][0]
        assert summary["lastAttemptId"] == attempt_id and summary["lastScore"] == 50 and summary["attemptCount"] == 2
        call("GET", f"/attempts/{attempt_id}", token=create_jwt("TIE", "student"), expected=404)
        call("GET", "/EP_ST_EXAM_DRAFT/ranking", expected=404)
        call("GET", "/EP_ST_EXAM_P1/ranking", course="ST_EXAM_C2", expected=404)
        call("GET", "/EP_ST_EXAM_P1/ranking", token=teacher, expected=403)
        call("GET", "/EP_ST_EXAM_P1/ranking", token="", expected=401)
        unassigned = call("GET", "/EP_ST_EXAM_P1/ranking", token=create_jwt("NOCLASS", "student"))
        assert unassigned["list"] == [] and unassigned["rank"] is None and unassigned["message"]
        db = SessionLocal()
        cleanup.callback(db.close)
        assert db.query(AnswerRecord).count() == before_records, "读取详情/排名不得写答题记录"
        assert db.query(TeacherClassDashboard).filter(TeacherClassDashboard.data_type == "exam_attempt").count() == before_attempts
        db.close()

        client.close()
        engine.dispose()
        assert hashlib.sha256(source.read_bytes()).hexdigest() == original_hash, "真实数据库不能被验证修改"
        print("PASS: 课程与本人权限、答案脱敏、自动保存、交卷判分、普通统计与错题本、幂等结算、禁止重测、历史详情、最近成绩、同班榜单与并列、未测验置尾、无班级说明及只读检查")


if __name__ == "__main__":
    main()
