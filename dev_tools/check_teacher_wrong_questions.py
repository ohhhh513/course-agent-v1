"""教师待办错题详情验收：仅在数据库副本中构造数据并调用真实接口。"""
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]


def main():
    real = ROOT / "backend/app/data/course_agent.db"
    original = sha256(real.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix="teacher-wrong-", ignore_cleanup_errors=True) as tmp:
        copy = Path(tmp) / "copy.db"
        shutil.copy2(real, copy)
        os.environ.update(DATABASE_URL="sqlite:///" + copy.as_posix(),
                          AGENT_DATA_DIR=str(Path(tmp) / "agent"), JWT_SECRET="teacher-wrong-check", DEBUG="false")
        sys.path.insert(0, str(ROOT / "backend"))
        from fastapi.testclient import TestClient
        from app.main import app
        from app.database import SessionLocal, engine
        from app.middleware.auth import create_jwt
        from app.models.user import User
        from app.models.course import Course
        from app.models.user_course import UserCourse
        from app.models.graph import GraphNode
        from app.models.question import Question
        from app.models.practice import AnswerRecord, PracticeSession
        from app.models.alert import Alert

        suffix = uuid4().hex[:8]
        course, other_course = "WQC_" + suffix, "WQO_" + suffix
        student, outsider, empty = [prefix + suffix for prefix in ("WQS_", "WQU_", "WQE_")]
        kp_ids = [f"WQK_{suffix}_{i}" for i in range(7)]
        q_ids = [f"WQQ_{suffix}_{i}" for i in range(15)]
        session = "WQP_" + suffix
        with SessionLocal() as db:
            teacher = db.query(User).filter(User.username == "wangjg").one()
            teacher_id = teacher.user_id
            for cid in (course, other_course):
                db.add(Course(course_id=cid, name="错题详情验收课程" if cid == course else "错题详情隔离课程", owner_id=teacher_id))
                db.add(UserCourse(user_id=teacher_id, course_id=cid, role_in_course="teacher"))
            db.flush()
            for uid in (student, outsider, empty):
                db.add(User(user_id=uid, username=uid, name="错题验收学生", password="unused", role="student"))
            db.flush()
            for uid, cid in ((student, course), (student, other_course), (empty, course), (outsider, other_course)):
                db.add(UserCourse(user_id=uid, course_id=cid, role_in_course="student"))
            for i, kid in enumerate(kp_ids):
                db.add(GraphNode(id=kid, graph_type="knowledge", course_id=course, name=f"测试知识点 {i}"))
            db.add(PracticeSession(session_id=session, user_id=student, course_id=course))
            db.flush()
            expected_tags = {}
            for i, qid in enumerate(q_ids):
                tags = [kp_ids[i % 7]]
                if i == 0:
                    tags.append(kp_ids[1])
                if i == 13:
                    tags = []
                expected_tags[qid] = tags or ["__unassigned__"]
                blank = i == 14
                db.add(Question(q_id=qid, course_id=course, stem="填入 __" if blank else f"题干 {i}",
                                kp_id=tags[0] if tags else "", kp_ids=json.dumps(tags), chapter="第一章",
                                type="blank" if blank else "single", answer="答案" if blank else "A",
                                options=json.dumps([{"blank": 1, "accept": ["答案", "等价答案"]}] if blank else
                                                   [{"key": "A", "text": "正确选项"}, {"key": "B", "text": "错误选项"}]),
                                analysis="测试解析", figure_json=json.dumps({"imageUrl": "/test.png"}) if i == 0 else None))
            other_qid = "WQX_" + suffix
            db.add(Question(q_id=other_qid, course_id=other_course, stem="其他课程题目", kp_id=kp_ids[0]))
            db.flush()

            def answer(qid, correct=False, cid=course, uid=student):
                db.add(AnswerRecord(session_id=session, user_id=uid, course_id=cid, q_id=qid,
                                    kp_id=kp_ids[0], is_correct=int(correct),
                                    my_answer="A" if correct else "B", correct_answer="A"))
                db.flush()

            for qid in q_ids:
                answer(qid)
            answer(q_ids[0])
            answer(q_ids[0], True)
            answer(other_qid, cid=other_course)
            answer(other_qid)  # 记录与题目课程不匹配，不能泄漏另一课程题目。
            answer(q_ids[1], cid=other_course)
            answer(q_ids[1], uid=outsider)
            db.add(Alert(alert_id="WQA_" + suffix, user_id=student, course_id=course,
                         kp_id=kp_ids[0], level="red", type="mastery_low", title="正确率偏低"))
            db.commit()

        client = TestClient(app)
        try:
            login = client.post("/api/v1/auth/login", json={"username": "wangjg", "password": "123456"})
            token = login.json()["data"]["token"]
            headers = {"Authorization": "Bearer " + token, "X-Course-Id": course}
            path = f"/api/v1/teacher/students/{student}/wrong-questions"
            with SessionLocal() as db:
                before = (db.query(AnswerRecord).count(), db.query(Alert).count(), db.query(Question).count())

            def read(params=None):
                response = client.get(path, params=params, headers=headers)
                assert response.status_code == 200, response.text
                return response.json()["data"]

            data = read({"size": 50})
            assert data["total"] == 15 and len(data["list"]) == 15
            assert len(data["knowledgePoints"]) == 8, "全部知识点不应截断为 Top 5"
            first = data["list"][0]
            assert first["qId"] == q_ids[0] and first["wrongCount"] == 2 and first["latestCorrect"]
            assert first["myAnswer"] == "B" and first["latestAnswer"] == "A"
            assert first["analysis"] == "测试解析" and first["options"][0]["right"]
            assert first["chapter"] == "第一章" and first["figureJson"]["imageUrl"] == "/test.png"
            assert "等价答案" in next(q for q in data["list"] if q["type"] == "blank")["answer"]
            print("PASS 全部知识点、完整题目、配图、填空答案、累计错误和最近已答对状态")
            for selected in ({kp_ids[0]}, {kp_ids[0], kp_ids[1]}, {"__unassigned__"}):
                result = read({"kpIds": ",".join(selected), "size": 50})
                expected = {qid for qid, tags in expected_tags.items() if selected.intersection(tags)}
                actual = [q["qId"] for q in result["list"]]
                assert set(actual) == expected and len(actual) == len(set(actual))
                assert len(result["knowledgePoints"]) == 8
            assert read({"kpIds": "nonexistent"})["total"] == 0
            paged = [read({"page": p, "size": 5}) for p in (1, 2, 3)]
            assert {q["qId"] for result in paged for q in result["list"]} == set(q_ids)
            assert read({"page": 99, "size": 5})["page"] == 3
            assert client.get(path, params={"page": 0}, headers=headers).status_code == 422
            assert client.get(path, params={"size": 51}, headers=headers).status_code == 422
            print("PASS 单选/多选并集与去重、未标注知识点、空结果、分页与参数校验")
            assert client.get(path).status_code == 401
            student_headers = {"Authorization": "Bearer " + create_jwt(student, "student"), "X-Course-Id": course}
            assert client.get(path, headers=student_headers).status_code == 403
            assert client.get(path.replace(student, outsider), headers=headers).status_code == 404
            assert client.get(path.replace(student, empty), headers=headers).json()["data"]["total"] == 0
            other_headers = dict(headers, **{"X-Course-Id": other_course})
            other_data = client.get(path, headers=other_headers).json()["data"]
            assert {q["qId"] for q in other_data["list"]} == {other_qid}
            dashboard = client.get("/api/v1/teacher/dashboard", headers=headers).json()["data"]
            todo = next(t for t in dashboard["todos"] if t["id"] == "TD_ALERT_WQA_" + suffix)
            assert todo["action"] == "查看详情" and todo["userId"] == student and todo["kpId"] == kp_ids[0]
            with SessionLocal() as db:
                after = (db.query(AnswerRecord).count(), db.query(Alert).count(), db.query(Question).count())
            assert before == after, "查看详情不能写入学情和错题数据"
            print("PASS 教师登录、未登录401、学生403、课程成员404、跨课程隔离及待办入口；详情只读")
        finally:
            client.close()
            engine.dispose()
        if "--serve" in sys.argv:
            import uvicorn
            print("浏览器验收：库副本服务 http://127.0.0.1:8015 ，教师 wangjg/123456，选择错题详情验收课程", flush=True)
            uvicorn.run(app, host="127.0.0.1", port=8015, lifespan="off", use_colors=False)
    assert sha256(real.read_bytes()).hexdigest() == original, "真实数据库被修改"
    print("PASS 真实数据库哈希未变化，全部写入仅发生于临时副本")


if __name__ == "__main__":
    main()
