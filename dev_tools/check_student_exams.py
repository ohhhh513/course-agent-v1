"""学生试卷测验端到端验收；先只读复制数据库，测试写入只发生在临时副本。"""
from pathlib import Path
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
    with tempfile.TemporaryDirectory(prefix="student-exams-") as folder:
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
        from app.database import SessionLocal
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
        db.add_all([
            User(user_id="ST_EXAM_CHECK", username="st_exam_check", name="试卷学生", role="student", password=hash_password("x")),
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
        for question, answer in zip(started["questions"], ("B", "A")):
            saved = call("PUT", f"/attempts/{attempt_id}/answers", body={
                "itemId": question["itemId"], "answer": answer, "durationSeconds": 12,
            })
            assert saved["saved"] is True
        first = call("POST", f"/attempts/{attempt_id}/finish")
        assert (first["score"], first["correct"], first["wrong"], first["accuracy"]) == (50, 1, 1, 50)
        assert call("POST", f"/attempts/{attempt_id}/finish") == first, "重复结算须幂等"

        db = SessionLocal()
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

        resumed = call("POST", "/EP_ST_EXAM_P1/attempts")
        assert resumed["attemptId"] != attempt_id and resumed["status"] == "running"
        for question in resumed["questions"]:
            call("PUT", f"/attempts/{resumed['attemptId']}/answers", body={
                "itemId": question["itemId"], "answer": "A", "durationSeconds": 20,
            })
        second = call("POST", f"/attempts/{resumed['attemptId']}/finish")
        assert (second["score"], second["accuracy"], second["correct"], second["wrong"]) == (100, 100, 2, 0)
        listed = call("GET", "")
        summary = listed["list"][0]
        assert summary["attemptCount"] == 2 and summary["lastScore"] == 100 and summary["lastAccuracy"] == 100
        wrong = client.get("/api/v1/practice/wrong-book?mastered=false", headers={
            "Authorization": "Bearer " + student, "X-Course-Id": "ST_EXAM_C1"})
        assert wrong.status_code == 200 and all(item["qId"] != "EX_ST_EXAM_Q1" for item in wrong.json()["data"]["list"])
        db = SessionLocal()
        assert overall_accuracy(db, "ST_EXAM_CHECK")["accuracy"] == 100
        assert db.query(AnswerRecord).filter(AnswerRecord.user_id == "ST_EXAM_CHECK").count() == 4
        db.close()

        client.close()
        from app.database import engine
        engine.dispose()
        print("PASS: 已发布/草稿与课程隔离、题目答案脱敏、作答自动保存、计时记录、交卷判分、普通答题统计、错题本掌握同步、重测成绩及幂等结算")


if __name__ == "__main__":
    main()
