"""班级治理端到端自检：只读备份真实库，写入仅发生在临时副本，不改变表结构。"""
from contextlib import ExitStack, closing, redirect_stderr
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory(prefix="admin-class-check-") as folder, ExitStack() as cleanup:
        work = Path(folder)
        with closing(sqlite3.connect((ROOT / "backend/app/data/course_agent.db").as_uri() + "?mode=ro", uri=True)) as source:
            with closing(sqlite3.connect(work / "copy.db")) as target:
                source.backup(target)
                schema = target.execute("SELECT type,name,sql FROM sqlite_master ORDER BY type,name").fetchall()
        os.environ.update(DATABASE_URL="sqlite:///" + (work / "copy.db").as_posix(), DEBUG="false",
                          JWT_SECRET="class-check-copy-only-secret", AGENT_DATA_DIR=str(work / "st"),
                          RAG_DB_PATH=str(work / "rag.db"), USER_AVATAR_DIR=str(work / "avatars"))
        sys.path.insert(0, str(ROOT / "backend"))
        from fastapi.testclient import TestClient
        from app.main import app
        from app.database import SessionLocal, engine
        from app.middleware.auth import hash_password
        from app.models.user import ClassInfo, TeacherClass, User
        from app.models.user_course import UserCourse
        from app.models.course import Course, Resource, ResourceProgress
        from app.models.graph import LearningPath
        from app.models.question import Question
        from app.models.practice import AnswerRecord, PracticeSession
        from app.models.ai import ChatMessage, ChatSession
        from app.models.alert import Alert
        from app.models.intervention import Intervention, Report, TeacherClassDashboard
        from app.services import account_import
        cleanup.callback(engine.dispose)
        client = TestClient(app, raise_server_exceptions=False)
        cleanup.callback(client.close)
        db = SessionLocal()
        cleanup.callback(db.close)
        db.add(User(user_id="CLASS_CHECK_ADMIN", username="class_check_admin", name="班级验收管理员",
                    role="admin", password=hash_password("Check123")))
        db.commit()

        def login(username, role="student"):
            response = client.post("/api/v1/auth/login", json={"username": username, "password": "Check123", "role": role})
            assert response.json()["code"] == 0, response.text
            return {"Authorization": "Bearer " + response.json()["data"]["token"]}

        headers = login("class_check_admin", "admin")

        def request(method, path, *, ok=True, **kwargs):
            response = client.request(method, "/api/v1" + path, headers=headers, **kwargs)
            if ok:
                assert response.status_code == 200 and response.json()["code"] == 0, response.text
                return response.json()["data"]
            return response

        def create_user(name, *, role="student", class_name=""):
            return request("POST", "/admin/users", json={"username": "class_check_" + name, "name": name,
                           "role": role, "password": "Check123", "className": class_name})["userId"]

        a = request("POST", "/admin/classes", json={"name": "验收 A 班"})
        b = request("POST", "/admin/classes", json={"name": "验收 B 班"})
        aid, bid = a["classId"], b["classId"]
        assert request("POST", "/admin/classes", ok=False, json={"name": "验收A班"}).status_code == 409
        teacher_id = create_user("teacher", role="teacher")
        keep_id = create_user("keep", class_name=b["name"])
        move_id = create_user("move", class_name=b["name"])
        teachers = login("class_check_teacher", "teacher")
        students = login("class_check_keep")
        # 兼容历史数据：只有 users.class_name、尚未登记 classes 的班级也可治理，GET 不写库。
        db.add(User(user_id="CLASS_CHECK_LEGACY", username="class_check_legacy", role="student",
                    name="历史学生", class_name="历史 C 班", password=hash_password("Check123")))
        db.commit()
        class_count = db.query(ClassInfo).count()
        catalog = request("GET", "/admin/classes")["list"]
        legacy = next(row for row in catalog if row["name"] == "历史 C 班")
        assert legacy["studentCount"] == 1 and db.query(ClassInfo).count() == class_count
        legacy_preview = request("GET", f"/admin/classes/{legacy['classId']}/delete-preview")
        request("DELETE", f"/admin/classes/{legacy['classId']}", json={"revision": legacy_preview["revision"]})
        db.expire_all()
        assert db.get(User, "CLASS_CHECK_LEGACY") is None
        print("[ok] 历史未登记班级可读可删，列表及预览不写库")
        for user_headers in (teachers, students):
            for method, path, body in (("GET", "/admin/classes", None),
                                      ("POST", "/admin/classes", {"name": "不应创建"}),
                                      ("GET", f"/admin/classes/{aid}/students", None),
                                      ("POST", f"/admin/classes/{aid}/students", {"userIds": [keep_id]}),
                                      ("GET", f"/admin/classes/{aid}/delete-preview", None),
                                      ("DELETE", f"/admin/classes/{aid}", {"revision": "0" * 64})):
                response = client.request(method, "/api/v1" + path, headers=user_headers, json=body)
                assert response.status_code == 403, (path, response.text)
        print("[ok] 新建、重名校验、师生角色闸门")

        content = "用户名,姓名,密码,班级,学号\nclass_check_one,学生甲,Check123,文件其他班,001\nclass_check_two,学生乙,Check123,文件其他班,002\nclass_check_keep,重复,Check123,文件其他班,003\n".encode("utf-8-sig")
        payload = {"role": "student", "classId": aid}
        files = {"file": ("students.csv", content, "text/csv")}
        preview = request("POST", "/admin/users/import/preview", data=payload, files=files)
        assert preview["valid"] == 2 and preview["dup"] == 1
        assert all(row["className"] == a["name"] for row in preview["rows"])
        assert request("GET", f"/admin/classes/{aid}/students")["studentCount"] == 0
        imported = request("POST", "/admin/users/import/commit", data=payload, files=files)
        assert imported["created"] == 2 and imported["skipped"] == 1
        assert db.get(User, keep_id).class_name == b["name"]
        request("POST", f"/admin/classes/{aid}/students", json={"userIds": [move_id]})
        assert request("GET", f"/admin/classes/{bid}/students")["studentCount"] == 1
        users = request("GET", f"/admin/classes/{aid}/students")["list"]
        ids = [user["userId"] for user in users]
        first_id = next(user["userId"] for user in users if user["username"] == "class_check_one")
        deleted_headers = login("class_check_one")
        print("[ok] 导入预览只读、指定班级、重复不覆盖、已有学生转班")

        course_id = "CLASS_CHECK_COURSE"
        db.expire_all()
        db.add(Course(course_id=course_id, name="班级清理验收课程", owner_id=teacher_id, teacher="teacher"))
        db.flush()
        for uid in ids + [keep_id, teacher_id]:
            db.add(UserCourse(course_id=course_id, user_id=uid, role_in_course="teacher" if uid == teacher_id else "student"))
        db.add(TeacherClass(teacher_user_id=teacher_id, class_id=aid, class_name=a["name"], student_count=3))
        db.add(Question(q_id="CLASS_CHECK_Q", course_id=course_id, stem="保留课程题目", kp_id="CLASS_CHECK_KP"))
        db.add(Resource(res_id="CLASS_CHECK_RES", course_id=course_id, title="保留课程资源", type="doc"))
        db.add(Intervention(iv_id="CLASS_CHECK_IV", class_id=aid, title="班级干预"))
        db.flush()
        for index, uid in enumerate(ids):
            sid = f"CLASS_CHECK_PS{index}"
            csid = f"CLASS_CHECK_CHAT{index}"
            db.add(PracticeSession(session_id=sid, user_id=uid, course_id=course_id))
            db.add(ChatSession(session_id=csid, user_id=uid, course_id=course_id))
            db.flush()
            db.add(AnswerRecord(session_id=sid, user_id=uid, course_id=course_id, q_id="CLASS_CHECK_Q", kp_id="CLASS_CHECK_KP"))
            db.add(ResourceProgress(user_id=uid, res_id="CLASS_CHECK_RES", progress=50))
            db.add(LearningPath(user_id=uid, course_id=course_id, kp_id="CLASS_CHECK_KP"))
            db.add(ChatMessage(session_id=csid, role="me", content="验收问题"))
            db.add(Alert(alert_id=f"CLASS_CHECK_AL{index}", user_id=uid, course_id=course_id, class_id=aid))
            db.add(Report(report_id=f"CLASS_CHECK_R{index}", class_id=aid,
                          detail_json=json.dumps({"meta": {"scope": "self", "courseId": course_id, "userId": uid}})))
            for data_type, field in (("exam_attempt", "userId"), ("ai_daily_analysis", "studentId")):
                db.add(TeacherClassDashboard(data_type=data_type, class_id=None, data_key=f"class-check-{index}-{field}",
                                             data_json=json.dumps({field: uid, "courseId": course_id})))
        db.add(TeacherClassDashboard(data_type="dashboard", class_id=aid, data_json="{}"))
        db.add(TeacherClassDashboard(data_type="exam_paper", class_id=None, data_key="CLASS_CHECK_PAPER",
                                     data_json=json.dumps({"courseId": course_id, "userId": teacher_id})))
        db.commit()
        th = {**teachers, "X-Course-Id": course_id}
        def teacher_students():
            response = client.get("/api/v1/teacher/students?size=100", headers=th)
            assert response.json()["code"] == 0, response.text
            return {user["userId"] for user in response.json()["data"]["list"]}
        assert first_id in teacher_students()
        response = request("POST", f"/admin/classes/{aid}/students/batch-delete", ok=False, json={"userIds": [first_id, keep_id]})
        assert response.status_code == 400
        result = request("POST", f"/admin/classes/{aid}/students/batch-delete", json={"userIds": [first_id]})
        assert result["deletedStudents"] == 1 and first_id not in teacher_students()
        assert client.get("/api/v1/auth/profile", headers=deleted_headers).status_code == 401
        db.expire_all()
        assert db.query(TeacherClassDashboard).filter(TeacherClassDashboard.data_json.contains(first_id)).count() == 0
        assert db.query(Report).filter(Report.detail_json.contains(first_id)).count() == 0
        print("[ok] 单个/批量学生删除、跨班拒绝、个人快照清理、旧令牌失效、教师不可见")

        old_preview = request("GET", f"/admin/classes/{aid}/delete-preview")
        extra_id = create_user("newcomer", class_name=a["name"])
        assert request("DELETE", f"/admin/classes/{aid}", ok=False, json={"revision": old_preview["revision"]}).status_code == 409
        fresh = request("GET", f"/admin/classes/{aid}/delete-preview")
        original_delete = account_import.delete_user_cascade
        calls = []
        def fail_second(db, user, **kwargs):
            calls.append(user.user_id)
            if len(calls) == 2:
                raise RuntimeError("验收注入失败，仅限临时副本")
            return original_delete(db, user, **kwargs)
        with redirect_stderr(io.StringIO()), patch.object(account_import, "delete_user_cascade", side_effect=fail_second):
            failed = request("DELETE", f"/admin/classes/{aid}", ok=False, json={"revision": fresh["revision"]})
            assert failed.status_code == 500 or failed.json().get("code") == 500
        assert request("GET", f"/admin/classes/{aid}/students")["studentCount"] == fresh["studentCount"]
        print("[ok] 过期确认拒绝、删除中途失败整体回滚")
        result = request("DELETE", f"/admin/classes/{aid}", json={"revision": fresh["revision"]})
        assert result["deletedStudents"] == fresh["studentCount"]
        assert request("GET", f"/admin/classes/{aid}/students", ok=False).status_code == 404
        assert request("POST", "/admin/users/import/commit", ok=False, data=payload, files=files).status_code == 404
        assert teacher_students() == {keep_id}
        for uid in [*ids, extra_id]:
            response = client.get(f"/api/v1/teacher/students/{uid}/profile", headers=th)
            assert response.json()["code"] == 404, response.text
        assert client.get("/api/v1/teacher/classes", headers=teachers).json()["data"] == []
        db.expire_all()
        assert db.get(User, keep_id) is not None
        assert db.get(Course, course_id) is not None
        assert db.get(Resource, "CLASS_CHECK_RES") is not None
        assert db.get(Question, "CLASS_CHECK_Q") is not None
        assert db.query(TeacherClassDashboard).filter(TeacherClassDashboard.data_key == "CLASS_CHECK_PAPER").count() == 1
        assert db.get(ClassInfo, bid) is not None
        with closing(sqlite3.connect(work / "copy.db")) as copied:
            assert copied.execute("PRAGMA foreign_key_check").fetchall() == []
            assert copied.execute("SELECT type,name,sql FROM sqlite_master ORDER BY type,name").fetchall() == schema
        print("[ok] 删班清理全部学生、班级关联与教师展示；保留其他班级、课程、资源和题库；结构无变化")
        print("全部通过；业务写入仅在数据库副本。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
