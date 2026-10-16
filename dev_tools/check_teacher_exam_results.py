"""教师试卷作答统计端到端验收；真实教师登录，写入仅限数据库副本。"""
from contextlib import ExitStack, closing
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from sqlalchemy import func


def main():
    repo = Path(__file__).resolve().parents[1]
    source = repo / "backend/app/data/course_agent.db"
    original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix="teacher-exam-results-") as folder, ExitStack() as cleanup:
        target = Path(folder) / "course_agent.db"
        with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as src, closing(sqlite3.connect(target)) as dst:
            src.backup(dst)
            original_schema = dst.execute("SELECT type,name,sql FROM sqlite_master ORDER BY type,name").fetchall()
        os.environ.update(DATABASE_URL="sqlite:///" + target.as_posix(), JWT_SECRET="teacher-exam-results-test", DEBUG="false")
        sys.path.insert(0, str(repo / "backend"))
        from fastapi.testclient import TestClient
        from app.main import app
        from app.database import SessionLocal, engine
        from app.middleware.auth import create_jwt
        from app.models.course import Course
        from app.models.graph import GraphNode
        from app.models.intervention import TeacherClassDashboard
        from app.models.practice import AnswerRecord
        from app.models.user import User
        from app.models.user_course import UserCourse
        cleanup.callback(engine.dispose)
        client = TestClient(app)
        cleanup.callback(client.close)
        db = SessionLocal()
        cleanup.callback(db.close)
        teacher = db.query(User).filter(User.username == "wangjg").one()
        login = client.post("/api/v1/auth/login", json={"username": "wangjg", "password": "123456", "role": "teacher"}).json()
        assert login["code"] == 0
        token = login["data"]["token"]
        for index in range(1, 8):
            db.add(User(user_id=f"RES_A{index}", username=f"res_a{index}", name=f"A学生{index}", student_no=f"00{index}",
                        class_name="统计A班", role="student", password="unused"))
        for uid, role, class_name in (("RES_B1", "student", "统计B班"), ("RES_OUT", "student", "统计A班"),
                                       ("RES_OTHER_TEACHER", "teacher", "")):
            db.add(User(user_id=uid, username=uid.lower(), name=uid, class_name=class_name, role=role, password="unused"))
        db.flush()
        db.add_all([Course(course_id="RES_C1", name="成绩统计课程", owner_id=teacher.user_id),
                    Course(course_id="RES_C2", name="隔离课程", owner_id=teacher.user_id)])
        db.flush()
        for uid in [teacher.user_id, "RES_OTHER_TEACHER"] + [f"RES_A{i}" for i in range(1, 8)] + ["RES_B1"]:
            db.add(UserCourse(user_id=uid, course_id="RES_C1", role_in_course="teacher" if uid in (teacher.user_id, "RES_OTHER_TEACHER") else "student"))
        db.add_all([UserCourse(user_id=teacher.user_id, course_id="RES_C2", role_in_course="teacher"),
                    UserCourse(user_id="RES_OUT", course_id="RES_C2", role_in_course="student"),
                    GraphNode(id="RES_CH", graph_type="chapter", course_id="RES_C1", name="统计章节"),
                    GraphNode(id="RES_KP", graph_type="knowledge", course_id="RES_C1", name="统计知识点")])
        db.commit()

        def call(path, method="GET", body=None, *, auth=token, course="RES_C1", expected=200):
            response = client.request(method, "/api/v1" + path, json=body,
                                      headers={"Authorization": "Bearer " + auth, "X-Course-Id": course})
            assert response.status_code == expected, (path, response.status_code, response.text)
            if expected == 200:
                assert response.json()["code"] == 0, response.text
                return response.json()["data"]

        question = {"type": "single", "stem": "单选统计", "chapterId": "RES_CH", "kpIds": ["RES_KP"],
                    "options": [{"key": "A", "text": "正确"}, {"key": "B", "text": "错误"}], "answer": "A", "analysis": "解析"}
        variants = [deepcopy(question) for _ in range(4)]
        variants[1].update(type="multi", stem="多选统计", options=[{"key": key, "text": key} for key in "ABC"], answer="AC")
        variants[2].update(type="judge", stem="判断统计", answer="B")
        variants[3].update(type="blank", stem="队列遵循____", options=[{"accept": ["先进先出", "FIFO"]}], answer="先进先出")
        paper = call("/teacher/exams", "POST", {"title": "教师作答统计验收", "publish": True,
                    "items": [{"id": f"res-item-{i}", "question": q} for i, q in enumerate(variants)]})
        base = "/teacher/exams/" + paper["paperId"]
        empty = call(base + "/results")
        assert empty["summary"] == {"submittedCount": 0, "averageScore": None, "highestScore": None, "lowestScore": None}
        assert len(empty["students"]) == 8 and len(empty["questions"]) == 4
        for uid, answers in (("RES_A1", ["A", "AB", "B", '["FIFO"]']),
                             ("RES_A2", ["B", "AC", "A", '[]']), ("RES_B1", ["A", "AC", "B", '["先进先出"]'])):
            student_token = create_jwt(uid, "student")
            started = call("/practice/exams/" + paper["paperId"] + "/attempts", "POST", auth=student_token)
            for item, answer in zip(started["questions"], answers):
                call("/practice/exams/attempts/" + started["attemptId"] + "/answers", "PUT",
                     {"itemId": item["itemId"], "answer": answer, "durationSeconds": 12}, auth=student_token)
            call("/practice/exams/attempts/" + started["attemptId"] + "/finish", "POST", auth=student_token)
        stats = call(base + "/results")
        assert stats["summary"] == {"submittedCount": 3, "averageScore": 66.7, "highestScore": 100, "lowestScore": 25}, stats["summary"]
        single, multi, judge, blank = stats["questions"]
        assert [o["count"] for o in single["options"]] == [2, 1]
        assert [o["right"] for o in single["options"]] == [True, False]
        assert [o["count"] for o in multi["options"]] == [3, 1, 2]
        assert [o["right"] for o in multi["options"]] == [True, False, True]
        assert [o["count"] for o in judge["options"]] == [1, 2]
        assert blank["blanks"][0]["correctCount"] == 2 and blank["blanks"][0]["unansweredCount"] == 1
        assert blank["unansweredCount"] == 1
        ranking = call(base + "/ranking?className=" + "统计A班")
        assert ranking["classSize"] == 7 and ranking["testedCount"] == 2
        assert ranking["list"][0]["userId"] == "RES_A1" and ranking["list"][-1]["status"] == "pending"
        assert all("items" not in entry for entry in ranking["list"])
        student_result = call(base + "/students/RES_A1/result")
        assert student_result["score"] == 75 and student_result["ranking"]["rank"] == 1 and student_result["ranking"]["classSize"] == 7
        assert len(student_result["items"]) == 4 and student_result["durationSeconds"] >= 0
        own_rank = call("/practice/exams/" + paper["paperId"] + "/ranking", auth=create_jwt("RES_A1", "student"))
        assert (own_rank["rank"], own_rank["classSize"]) == (student_result["ranking"]["rank"], student_result["ranking"]["classSize"])
        pending = call(base + "/students/RES_A7/result")
        assert pending["student"]["status"] == "pending" and pending["score"] is None and pending["items"] == []
        assert call(base + "/ranking?className=" + "统计B班")["classSize"] == 1
        for suffix in ("/results", "/ranking", "/students/RES_A1/result"):
            call(base + suffix, auth=create_jwt("RES_A1", "student"), expected=403)
            call(base + suffix, auth=create_jwt("RES_OTHER_TEACHER", "teacher"), expected=404)
            call(base + suffix, course="RES_C2", expected=404)
            call(base + suffix, auth="", expected=401)
        call(base + "/students/RES_OUT/result", expected=404)
        call(base + "/ranking?className=outside", expected=404)
        draft = call("/teacher/exams", "POST", {})
        call("/teacher/exams/" + draft["paperId"] + "/results", expected=409)

        db.expire_all()
        row = db.query(TeacherClassDashboard).filter(TeacherClassDashboard.data_type == "exam_attempt",
               func.json_extract(TeacherClassDashboard.data_json, "$.userId") == "RES_A1").one()
        old = json.loads(row.data_json)
        old.update(attemptId="EA_RES_OLD", finishedAt="2000-01-01T00:00:00+00:00")
        old["result"]["score"] = 100
        db.add(TeacherClassDashboard(data_type="exam_attempt", data_key="EA_RES_OLD", data_json=json.dumps(old)))
        db.commit()
        assert call(base + "/results")["summary"] == stats["summary"], "旧重测不能重复计人或替换新成绩"
        modified = deepcopy(paper)
        modified["items"][0]["question"]["stem"] = "修改后的单选题"
        call(base, "PUT", modified)
        revised = call(base + "/results")
        assert len(revised["questions"]) == 5
        assert revised["questions"][0]["respondentCount"] == 0
        assert any(q["historical"] and q["stem"] == "单选统计" and q["respondentCount"] == 3 for q in revised["questions"])
        before_records = db.query(AnswerRecord).count()
        before_rows = db.query(TeacherClassDashboard).count()
        call(base + "/results"); call(base + "/ranking"); call(base + "/students/RES_A1/result")
        assert db.query(AnswerRecord).count() == before_records and db.query(TeacherClassDashboard).count() == before_rows
        with closing(sqlite3.connect(target)) as copied:
            assert copied.execute("SELECT type,name,sql FROM sqlite_master ORDER BY type,name").fetchall() == original_schema
        assert hashlib.sha256(source.read_bytes()).hexdigest() == original_hash
        print("PASS 教师真实登录、零提交、四类题统计、多选人数、未答、最近提交去重、历史快照、学生详情、同班排名一致、未测验末尾、权限/课程/学生隔离、只读与数据库结构/真实库哈希检查")


if __name__ == "__main__":
    main()
