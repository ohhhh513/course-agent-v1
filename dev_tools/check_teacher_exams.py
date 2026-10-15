"""教师试卷端到端验收；通过 SQLite backup 只读取真实库，所有写入均在临时副本。"""
from pathlib import Path
import copy
import json
import os
import sqlite3
import sys
import tempfile

REPO = Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory(prefix="teacher-exams-") as folder:
        source = REPO / "backend/app/data/course_agent.db"
        target = Path(folder) / "course_agent.db"
        src = sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)
        dst = sqlite3.connect(target)
        try:
            src.backup(dst)
        finally:
            src.close()
            dst.close()
        os.environ["DATABASE_URL"] = "sqlite:///" + target.as_posix()
        os.environ["JWT_SECRET"] = "exam-check-temporary-secret"
        os.environ["DEBUG"] = "0"
        sys.path.insert(0, str(REPO / "backend"))
        from fastapi.testclient import TestClient
        from app.main import app
        from app.database import SessionLocal
        from app.models.course import Course
        from app.models.user import User
        from app.models.user_course import UserCourse
        from app.models.graph import GraphNode
        from app.models.question import Question
        from app.models.agent_st import STQuestionDraft
        from app.middleware.auth import create_jwt, hash_password
        from app.services.exam_papers import distribute_scores

        client = TestClient(app)
        login = client.post("/api/v1/auth/login", json={"username": "wangjg", "password": "123456", "role": "teacher"}).json()
        assert login.get("code") == 0, login
        teacher_token = login["data"]["token"]
        db = SessionLocal()
        teacher = db.query(User).filter(User.username == "wangjg").one()
        for uid, role in (("EXAM_CHECK_OTHER", "teacher"), ("EXAM_CHECK_STU", "student")):
            db.add(User(user_id=uid, username=uid, name=uid, role=role, password=hash_password("123456")))
        db.add(Course(course_id="EXAM_CHECK_C", name="试卷验收课程", owner_id=teacher.user_id))
        db.add(Course(course_id="EXAM_CHECK_C2", name="另一验收课程", owner_id=teacher.user_id))
        db.commit()
        for uid, role in ((teacher.user_id, "teacher"), ("EXAM_CHECK_OTHER", "teacher"), ("EXAM_CHECK_STU", "student")):
            for cid in ("EXAM_CHECK_C", "EXAM_CHECK_C2"):
                db.add(UserCourse(user_id=uid, course_id=cid, role_in_course=role))
        db.add(GraphNode(id="EXAM_CHECK_CH", graph_type="chapter", course_id="EXAM_CHECK_C", name="验收章节"))
        db.add(GraphNode(id="EXAM_CHECK_CH2", graph_type="chapter", course_id="EXAM_CHECK_C", name="第二章验收"))
        db.add(GraphNode(id="EXAM_CHECK_KP", graph_type="knowledge", course_id="EXAM_CHECK_C", name="验收知识点", chapter="验收章节"))
        db.add(GraphNode(id="EXAM_CHECK_KP2", graph_type="knowledge", course_id="EXAM_CHECK_C", name="组合筛选知识点", chapter="第二章验收"))
        db.add(Question(q_id="EXAM_CHECK_Q", course_id="EXAM_CHECK_C", type="single", status="published",
                        stem="题库快照题", chapter_id="EXAM_CHECK_CH", kp_id="EXAM_CHECK_KP",
                        options='[{"key":"A","text":"一"},{"key":"B","text":"二"}]', answer="A"))
        db.add(Question(q_id="EXAM_CHECK_Q2", course_id="EXAM_CHECK_C", type="single", status="published",
                        stem="组合筛选题", chapter_id="EXAM_CHECK_CH2", chapter="第二章验收",
                        kp_id="EXAM_CHECK_KP2", kp_ids='["EXAM_CHECK_KP"]',
                        options='[{"key":"A","text":"一"},{"key":"B","text":"二"}]', answer="A"))
        db.commit()
        counts = (db.query(Question).count(), db.query(STQuestionDraft).count())

        def bank(params):
            response = client.get("/api/v1/question/bank", params=params,
                                  headers={"Authorization": "Bearer " + teacher_token, "X-Course-Id": "EXAM_CHECK_C"})
            assert response.status_code == 200, response.text
            assert response.json()["code"] == 0, response.text
            return response.json()["data"]

        assert [q["qId"] for q in bank({"status": "published", "chapterId": "EXAM_CHECK_CH2"})["list"]] == ["EXAM_CHECK_Q2"]
        assert {q["qId"] for q in bank({"status": "published", "knowledgeId": "EXAM_CHECK_KP"})["list"]} == {"EXAM_CHECK_Q", "EXAM_CHECK_Q2"}
        assert [q["qId"] for q in bank({"status": "published", "chapterId": "EXAM_CHECK_CH2", "knowledgeId": "EXAM_CHECK_KP"})["list"]] == ["EXAM_CHECK_Q2"]
        assert [q["qId"] for q in bank({"status": "published", "keyword": "第二章验收"})["list"]] == ["EXAM_CHECK_Q2"]
        assert bank({"status": "published", "chapterId": "EXAM_CHECK_CH", "knowledgeId": "EXAM_CHECK_KP2"})["total"] == 0

        multi = {"status": "published", "knowledgeIds": "EXAM_CHECK_KP,EXAM_CHECK_KP2"}
        combined = bank(multi)
        assert {q["qId"] for q in combined["list"]} == {"EXAM_CHECK_Q", "EXAM_CHECK_Q2"}
        assert combined["total"] == 2  # 同时命中主知识点与多标签的题目不重复。
        assert [q["qId"] for q in bank({**multi, "chapterId": "EXAM_CHECK_CH2", "type": "single", "keyword": "组合"})["list"]] == ["EXAM_CHECK_Q2"]
        pages = [bank({**multi, "page": page, "size": 1}) for page in (1, 2)]
        assert all(result["total"] == 2 and len(result["list"]) == 1 for result in pages)
        assert {q["qId"] for result in pages for q in result["list"]} == {"EXAM_CHECK_Q", "EXAM_CHECK_Q2"}
        assert bank({"knowledgeIds": "not-a-kp,not-another-kp"})["total"] == 0
        print("PASS: 题库知识点多选并集、去重、组合筛选与分页，兼容单选")

        def call(method, path="", body=None, *, token=teacher_token, course="EXAM_CHECK_C", expected=200):
            response = client.request(method, "/api/v1/teacher/exams" + path, json=body,
                                      headers={"Authorization": "Bearer " + token, "X-Course-Id": course})
            assert response.status_code == expected, (method, path, response.status_code, response.text)
            if expected == 200:
                assert response.json()["code"] == 0, response.text
                return response.json()["data"]

        question = {"stem": "新题仅属于试卷", "type": "single", "difficulty": 3,
                    "chapterId": "EXAM_CHECK_CH", "kpIds": ["EXAM_CHECK_KP"],
                    "options": [{"key": "A", "text": "一"}, {"key": "B", "text": "二"}], "answer": "A"}
        bank_question = {**question, "stem": "题库快照题",
                         "options": [{"key": "A", "text": "一"}, {"key": "B", "text": "二"}]}
        body = {"title": "验收试卷", "totalScore": 100, "scoreMode": "auto",
                "items": [{"id": f"item{i}", "question": copy.deepcopy(question)} for i in range(3)]}
        body["items"][0]["sourceQId"] = "EXAM_CHECK_Q"
        body["items"][0]["question"] = copy.deepcopy(bank_question)
        paper = call("POST", body=body)
        pid = "/" + paper["paperId"]
        assert paper["status"] == "draft" and [q["score"] for q in paper["items"]] == [33, 33, 34]
        assert db.query(Question).count() == counts[0], "保存草稿不能把自出题写入正式题库"
        assert call("GET", pid)["items"][1]["question"]["stem"] == question["stem"]
        assert any(p["paperId"] == paper["paperId"] for p in call("GET")["list"])
        assert distribute_scores(1, 3) == [0.3, 0.3, 0.4]
        assert distribute_scores(100.1, 3) == [33.3, 33.4, 33.4]
        for n in range(1, 201):
            scores = distribute_scores(100, n)
            assert sum(round(s * 10) for s in scores) == 1000
        # 权限、教师隔离、课程隔离。
        student = create_jwt("EXAM_CHECK_STU", "student")
        other = create_jwt("EXAM_CHECK_OTHER", "teacher")
        for method, path, payload in (("GET", "", None), ("GET", pid, None), ("POST", "", body),
                                       ("PUT", pid, body), ("POST", pid + "/publish", {"revision": 1})):
            call(method, path, payload, token=student, expected=403)
        assert call("GET", token=other)["list"] == []
        call("GET", pid, token=other, expected=404)
        call("POST", pid + "/publish", {"revision": 1}, token=other, expected=404)
        call("GET", pid, course="EXAM_CHECK_C2", expected=404)
        call("POST", body=body, course="EXAM_CHECK_C2", expected=400)
        bad = copy.deepcopy(body)
        bad.update(scoreMode="manual", publish=True)
        for item in bad["items"]:
            item["score"] = 30
        call("POST", body=bad, expected=400)
        for item in bad["items"]:
            item["score"] = 40
        call("POST", body=bad, expected=400)
        bad["items"][0]["score"] = 33.33
        call("POST", body=bad, expected=400)
        for i, score in enumerate((33.3, 33.3, 33.4)):
            bad["items"][i]["score"] = score
        published_bad = call("POST", body=bad)
        assert published_bad["status"] == "published"
        db.rollback()
        assert db.query(Question).count() == counts[0] + 2, (counts[0], db.query(Question).count())
        for item in published_bad["items"][1:]:
            saved = db.query(Question).filter(Question.q_id == item["sourceQId"]).one()
            assert saved.status == "published" and saved.source_ref_file == "exam_paper"
            assert item["sourceOrigin"] == "exam"
        imported_ids = {item["sourceQId"] for item in published_bad["items"][1:]}
        assert imported_ids <= {q["qId"] for q in bank({"status": "published"})["list"]}
        # 四种题型及结构图/选项图完整保存，填空题保留多个可接受答案。
        variants = [copy.deepcopy(question) for _ in range(4)]
        variants[1].update(type="multi", answer="AB")
        variants[2].update(type="judge", options=[{"key": "A", "text": "正确"}, {"key": "B", "text": "错误"}], answer="B")
        variants[3].update(type="blank", stem="队列遵循____原则", options=[{"accept": ["先进先出", "FIFO"]}], answer="先进先出")
        graph = {"type": "tree", "root": "A", "nodes": ["A"], "edges": []}
        variants[0]["figureJson"] = {"graph": graph, "options_graph": {"A": graph}}
        mixed = call("POST", body={"title": "四种题型", "publish": True,
                                   "items": [{"id": f"mixed{i}", "question": q} for i, q in enumerate(variants)]})
        db.rollback()
        assert db.query(Question).count() == counts[0] + 6
        mixed = call("GET", "/" + mixed["paperId"])
        assert [i["question"]["type"] for i in mixed["items"]] == ["single", "multi", "judge", "blank"]
        assert mixed["items"][0]["question"]["figureJson"]["options_graph"]["A"] == graph
        assert mixed["items"][3]["question"]["options"][0]["accept"] == ["先进先出", "FIFO"]
        invalid_question = copy.deepcopy(body)
        invalid_question["publish"] = True
        invalid_question["items"][1]["question"]["answer"] = "C"
        call("POST", body=invalid_question, expected=400)
        # 空草稿可保存，但不能发布；保存草稿和发布均不入题库/单题草稿箱。
        empty = call("POST", body={})
        assert not empty["ready"]
        call("POST", "/" + empty["paperId"] + "/publish", {"revision": 1}, expected=400)
        call("PUT", pid, {**body, "revision": 0}, expected=409)
        # 原题删除后仍能打开、发布已保存的试卷快照。
        db.query(Question).filter(Question.q_id == "EXAM_CHECK_Q").delete()
        db.commit()
        paper = call("POST", pid + "/publish", {"revision": 1})
        assert paper["status"] == "published" and paper["revision"] == 2
        assert paper["items"][0]["sourceQId"] != "EXAM_CHECK_Q"
        assert paper["items"][0]["sourceOrigin"] == "exam"
        db.rollback()
        assert db.query(Question).count() == counts[0] + 8
        assert all(db.query(Question).filter(Question.q_id == item["sourceQId"],
                                             Question.status == "published").first()
                   for item in paper["items"])
        renamed = call("PUT", pid, {**paper, "title": "已发布试卷修改", "revision": 2})
        assert renamed["status"] == "published" and renamed["revision"] == 3
        call("PUT", pid, {**paper, "revision": 2}, expected=409)
        call("PUT", pid, {**renamed, "items": [], "revision": 3}, expected=400)
        db.rollback()
        db.expire_all()
        assert (db.query(Question).count(), db.query(STQuestionDraft).count()) == (counts[0] + 8, counts[1])
        db.close()
        client.close()
        from app.database import engine
        engine.dispose()
        print("PASS: 章节/知识点组合筛选与章节关键词搜索、教师登录、草稿持久化、均分/小数/超欠分校验、列表/编辑发布、权限隔离、快照；草稿题不入题库，正式发布后新题入正式题库")


if __name__ == "__main__":
    main()
