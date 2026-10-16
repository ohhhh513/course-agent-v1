"""归因分析课程隔离验收：共享学生、多课程与异常归属夹具仅写数据库副本。"""
from contextlib import ExitStack, closing
from datetime import datetime, timedelta
import hashlib
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import SimpleNamespace


def main():
    repo = Path(__file__).resolve().parents[1]
    source = repo / "backend/app/data/course_agent.db"
    original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix="analysis-course-") as folder, ExitStack() as cleanup:
        target = Path(folder) / "course_agent.db"
        with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as src, closing(sqlite3.connect(target)) as dst:
            src.backup(dst)
            schema = dst.execute("SELECT type,name,sql FROM sqlite_master ORDER BY type,name").fetchall()
        os.environ.update(DATABASE_URL="sqlite:///" + target.as_posix(), JWT_SECRET="analysis-course-test", DEBUG="false",
                          RAG_DB_PATH=str(Path(folder) / "rag.db"), AGENT_DATA_DIR=str(Path(folder) / "agent"))
        sys.path.insert(0, str(repo / "backend"))
        from fastapi.testclient import TestClient
        from app.main import app
        from app.database import SessionLocal, engine
        from app.middleware.auth import create_jwt
        from app.models.course import Course
        from app.models.graph import GraphNode, LearningPath
        from app.models.practice import AnswerRecord, PracticeSession
        from app.models.question import Question
        from app.models.user import User
        from app.models.user_course import UserCourse
        from app.routers.teacher import _analysis_option_stats
        cleanup.callback(engine.dispose)
        client = TestClient(app)
        cleanup.callback(client.close)
        db = SessionLocal()
        cleanup.callback(db.close)
        teacher = db.query(User).filter(User.username == "wangjg").one()
        login = client.post("/api/v1/auth/login", json={"username": "wangjg", "password": "123456", "role": "teacher"}).json()
        assert login["code"] == 0
        teacher_token = login["data"]["token"]
        for uid in ("AN_S1", "AN_S2", "AN_OUT"):
            db.add(User(user_id=uid, username=uid.lower(), name=uid, role="student", class_name="同一个班", password="unused"))
        db.flush()
        for course in ("AN_A", "AN_B", "AN_EMPTY", "AN_DENIED"):
            db.add(Course(course_id=course, name=course, owner_id=teacher.user_id))
        db.flush()
        for course in ("AN_A", "AN_B", "AN_EMPTY"):
            db.add(UserCourse(user_id=teacher.user_id, course_id=course, role_in_course="teacher"))
            for uid in ("AN_S1", "AN_S2"):
                db.add(UserCourse(user_id=uid, course_id=course, role_in_course="student"))
        db.add(UserCourse(user_id="AN_OUT", course_id="AN_B", role_in_course="student"))
        for course, count, mastery, status in (("AN_A", 3, 90, "done"), ("AN_B", 10, 1, "doing")):
            for index in range(count):
                kp = f"{course}_KP{index}"
                db.add(GraphNode(id=kp, graph_type="knowledge", course_id=course, name=kp, chapter=f"{course}章节"))
                for uid in ("AN_S1", "AN_S2"):
                    db.add(LearningPath(user_id=uid, course_id=course, kp_id=kp, name=kp,
                                        chapter=f"{course}章节", status=status, mastery=mastery))
                db.add(Question(q_id=f"{course}_Q{index}", course_id=course, kp_id=kp, stem=f"{course}独立题目{index}",
                                chapter=f"{course}章节", status="published", type="single", answer="A",
                                options='[{"key":"A","text":"正确"},{"key":"B","text":"错误"}]'))
            for uid in ("AN_S1", "AN_S2", "AN_OUT"):
                db.add(PracticeSession(session_id=f"{course}_{uid}", user_id=uid, course_id=course, mode="order"))
        db.commit()

        def answer(course, uid, qid, correct, error_type, days=0):
            db.add(AnswerRecord(session_id=f"{course}_{uid}", user_id=uid, course_id=course,
                                q_id=qid, kp_id=qid.replace("_Q", "_KP"), is_correct=correct,
                                my_answer="A" if correct else "B",
                                error_type=error_type, created_at=datetime.utcnow() - timedelta(days=days)))

        answer("AN_A", "AN_S1", "AN_A_Q0", 0, "A错因")
        answer("AN_A", "AN_S1", "AN_A_Q0", 0, "A错因", 10)
        answer("AN_A", "AN_S1", "AN_A_Q1", 1, "A正确记录")
        answer("AN_A", "AN_S2", "AN_A_Q0", 1, "A正确记录")
        for uid in ("AN_S1", "AN_S2"):
            for _ in range(12):
                answer("AN_B", uid, "AN_B_Q0", 0, "B错因")
        answer("AN_A", "AN_S1", "AN_B_Q0", 0, "题目归属不符")
        for _ in range(20):
            answer("AN_A", "AN_OUT", "AN_A_Q0", 0, "非课程成员")
        db.commit()
        before_records = db.query(AnswerRecord).count()
        before_paths = db.query(LearningPath).count()

        def call(endpoint="errors", course="AN_A", params=None, token=teacher_token, expected=200):
            response = client.get("/api/v1/analysis/" + endpoint, params=params,
                                  headers={"Authorization": "Bearer " + token, "X-Course-Id": course})
            assert response.status_code == expected, (endpoint, course, response.status_code, response.text)
            if expected == 200:
                assert response.json()["code"] == 0, response.text
                return response.json()["data"]

        a = call()
        assert [(q["qId"], q["count"]) for q in a["topWrongQuestions"]] == [("AN_A_Q0", 2)], a["topWrongQuestions"]
        assert a["topWrongQuestions"][0]["wrongRate"] == 66.7
        assert a["topWrongQuestions"][0]["respondentCount"] == 2
        assert a["topWrongQuestions"][0]["optionStats"] == [{"key": "A", "count": 1, "percent": 50}, {"key": "B", "count": 1, "percent": 50}]
        assert a["commonVsIndividual"] == {"common": [], "individual": []}, a["commonVsIndividual"]
        assert all(not node["kpId"] or node["kpId"].startswith("AN_A_") for node in a["weakChain"].values() if isinstance(node, dict))
        b = call(course="AN_B")
        assert [(q["qId"], q["count"]) for q in b["topWrongQuestions"]] == [("AN_B_Q0", 24)]
        assert b["topWrongQuestions"][0]["respondentCount"] == 2
        assert b["topWrongQuestions"][0]["optionStats"] == [{"key": "A", "count": 0, "percent": 0}, {"key": "B", "count": 2, "percent": 100}]
        assert b["commonVsIndividual"]["common"][0]["kpId"] == "AN_B_KP0"
        assert {item["userId"] for item in b["commonVsIndividual"]["individual"]} == {"AN_S1", "AN_S2"}
        assert call() == a, "A→B→A 后应恢复A自己的数据"
        for course, expected_kp, count in (("AN_A", "AN_A_KP0", 2), ("AN_B", "AN_B_KP0", 24)):
            chain = call("weak-chain", course)
            assert chain["root"] == {"kpId": expected_kp, "wrongCount": count}
            categories = call("causes", course)["categories"]
            assert all(item["name"].startswith(course[-1]) for item in categories), categories
            assert sum(item["count"] for item in categories) == (4 if course == "AN_A" else 24)
        assert call(params={"chapter": "不存在的章节"})["topWrongQuestions"] == []
        assert call(params={"chapter": "AN_B章节"})["topWrongQuestions"] == []
        assert call(params={"chapter": "AN_A章节"})["topWrongQuestions"] == a["topWrongQuestions"]
        assert call(params={"kpId": "AN_B_KP0"})["topWrongQuestions"] == []
        assert call("weak-chain", params={"kpId": "AN_B_KP0"}) is None
        assert call(params={"timeRange": "7d"})["topWrongQuestions"][0]["count"] == 1
        empty = call(course="AN_EMPTY")
        assert empty["topWrongQuestions"] == [] and empty["commonVsIndividual"] == {"common": [], "individual": []}
        assert call("weak-chain", "AN_EMPTY") is None
        assert call("causes", "AN_EMPTY")["categories"] == []
        for endpoint in ("errors", "weak-chain", "causes"):
            call(endpoint, token=create_jwt("AN_S1", "student"), expected=403)
            call(endpoint, token="", expected=401)
            call(endpoint, "AN_DENIED", expected=403)
        choices = '[{"key":"A","text":"A"},{"key":"B","text":"B"},{"key":"C","text":"C"}]'
        question = Question(type="multi", answer="AC", options=choices)
        selected = _analysis_option_stats(question, {1: SimpleNamespace(my_answer="AABC"), 2: SimpleNamespace(my_answer="C"), 3: SimpleNamespace(my_answer="a,c")})
        assert selected == {"respondentCount": 3, "optionStats": [{"key": "A", "count": 2, "percent": 66.7}, {"key": "B", "count": 1, "percent": 33.3}, {"key": "C", "count": 3, "percent": 100}]}
        assert all(item["count"] == 0 and item["percent"] == 0 for item in _analysis_option_stats(question, {})["optionStats"])
        question.type = "judge"
        assert _analysis_option_stats(question, {1: SimpleNamespace(my_answer="A"), 2: SimpleNamespace(my_answer="B")})["optionStats"][1]["percent"] == 50
        question.type = "blank"
        assert _analysis_option_stats(question, {1: SimpleNamespace(my_answer="答案")}) == {"respondentCount": 1, "optionStats": []}
        answer("AN_A", "AN_S1", "AN_A_Q0", 1, "A正确记录")
        db.commit()
        before_records += 1
        updated = call()["topWrongQuestions"][0]
        assert updated["count"] == 2 and updated["respondentCount"] == 2, "累计错题次数不改，人数按学生去重"
        assert updated["optionStats"] == [{"key": "A", "count": 2, "percent": 100}, {"key": "B", "count": 0, "percent": 0}], "新作答应替换该学生旧选择"
        assert db.query(AnswerRecord).count() == before_records and db.query(LearningPath).count() == before_paths
        with closing(sqlite3.connect(target)) as copied:
            assert copied.execute("SELECT type,name,sql FROM sqlite_master ORDER BY type,name").fetchall() == schema
        assert hashlib.sha256(source.read_bytes()).hexdigest() == original_hash
        print("PASS 真实教师登录；同一批学生跨三课的错题Top5、错误率、共性/个性、弱链与错因隔离；异常题目归属、非成员、空课程、章节/KP/时间筛选、角色权限、只读及真实库/表结构未改")
        print("PASS 各选项人数/百分比、同一学生去重与零选择、多选独立统计/重复字母去重/百分比取一位小数、零分母、判断及填空兼容")


if __name__ == "__main__":
    main()
