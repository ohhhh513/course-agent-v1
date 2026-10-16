"""个人中心验收：真实库只读备份，资料、密码与头像均在临时副本中操作。"""
from pathlib import Path
from contextlib import ExitStack, closing
import argparse
import hashlib
import io
import os
import sqlite3
import sys
import tempfile

REPO = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve", action="store_true")
    args = parser.parse_args()
    source = REPO / "backend/app/data/course_agent.db"
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix="user-profiles-") as folder, ExitStack() as cleanup:
        target = Path(folder) / "course_agent.db"
        original = sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)
        copied = sqlite3.connect(target)
        original.backup(copied)
        original.close()
        schema = copied.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").fetchall()
        copied.close()
        os.environ.update(DATABASE_URL="sqlite:///" + target.as_posix(), DEBUG="false", JWT_SECRET="profile-check-copy-only-secret", USER_AVATAR_DIR=str(Path(folder) / "avatars"))
        sys.path.insert(0, str(REPO / "backend"))
        from PIL import Image, PngImagePlugin
        from fastapi.testclient import TestClient
        from app.main import app
        from app.database import SessionLocal, engine
        cleanup.callback(engine.dispose)
        from app.models.user import User
        from app.models.intervention import TeacherClassDashboard
        from app.middleware.auth import hash_password, verify_password
        from app.services.user_profiles import DATA_TYPE, normalize_avatar, save_profile, delete_profile

        client = TestClient(app)  # 不触发启动建表；副本结构必须前后完全相同。
        cleanup.callback(client.close)
        db = SessionLocal()
        cleanup.callback(db.close)
        for uid, role in (("PROFILE_STU", "student"), ("PROFILE_TEACHER", "teacher"), ("PROFILE_ADMIN", "admin")):
            db.add(User(user_id=uid, username=uid, password=hash_password("Start123"), role=role, name="头像验收" + role, avatar_char="验"))
        db.commit()

        def login(username, password="Start123"):
            response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
            assert response.status_code == 200 and response.json()["code"] == 0, response.text
            return response.json()["data"]

        sessions = {uid: login(uid) for uid in ("PROFILE_STU", "PROFILE_TEACHER", "PROFILE_ADMIN")}
        headers = {uid: {"Authorization": "Bearer " + session["token"]} for uid, session in sessions.items()}

        def get(uid):
            response = client.get("/api/v1/auth/profile", headers=headers[uid])
            assert response.status_code == 200 and response.json()["code"] == 0, response.text
            return response.json()["data"]

        info = PngImagePlugin.PngInfo()
        info.add_text("Comment", "must be removed")
        stream = io.BytesIO()
        Image.new("RGBA", (512, 512), (20, 170, 150, 180)).save(stream, "PNG", pnginfo=info)
        photo = stream.getvalue()

        def save(uid, signature="测试签名", image=None, default=False, expected=200, **extra):
            files = {"avatar": ("avatar.png", image, "image/png")} if image is not None else None
            response = client.put("/api/v1/auth/profile", headers=headers[uid],
                                  data={"signature": signature, "useDefaultAvatar": str(default).lower(), **extra}, files=files)
            assert response.status_code == expected, response.text
            return response.json().get("data") if expected == 200 else response

        for uid in sessions:
            user = get(uid)
            assert user["avatarUrl"] == "" and user["signature"] == ""
            updated = save(uid, signature="个性签名 <script> 不应执行 " + uid, image=photo)
            assert updated["userId"] == uid and updated["avatarUrl"].endswith(".png")
            assert get(uid)["signature"] == updated["signature"]
            assert login(uid)["user"]["avatarUrl"] == updated["avatarUrl"]
            response = client.get(updated["avatarUrl"])
            assert response.status_code == 200 and response.headers["content-type"].startswith("image/png")
            with Image.open(io.BytesIO(response.content)) as avatar:
                assert avatar.size == (512, 512) and "Comment" not in avatar.info
            assert "password" not in updated and "token" not in updated
        print("PASS 三端资料保存/重新读取/重新登录、规范512×512头像、去除源图片元数据与签名持久化")

        student = get("PROFILE_STU")
        old_url = student["avatarUrl"]
        updated = save("PROFILE_STU", signature="只改签名")
        assert updated["avatarUrl"] == old_url
        files_before = {p.name for p in (Path(folder) / "avatars").iterdir()}
        save("PROFILE_STU", image=b"<svg></svg>", expected=400)
        rectangle = io.BytesIO()
        Image.new("RGB", (512, 256)).save(rectangle, "PNG")
        save("PROFILE_STU", image=rectangle.getvalue(), expected=400)
        save("PROFILE_STU", image=b"x" * (5 * 1024 * 1024 + 1), expected=400)
        save("PROFILE_STU", image=photo, default=True, expected=400)
        save("PROFILE_STU", signature="长" * 121, expected=422)
        assert {p.name for p in (Path(folder) / "avatars").iterdir()} == files_before
        assert get("PROFILE_STU")["signature"] == "只改签名"
        replacement = save("PROFILE_STU", image=photo)["avatarUrl"]
        assert replacement != old_url and client.get(old_url).status_code == 404
        assert not (Path(folder) / "avatars" / old_url.rsplit("/", 1)[-1]).exists()
        default = save("PROFILE_STU", signature="默认头像", default=True)
        assert default["avatarUrl"] == "" and default["avatarChar"] == "验"
        assert client.get(replacement).status_code == 404
        old_teacher = get("PROFILE_TEACHER")
        files_before = {p.name for p in (Path(folder) / "avatars").iterdir()}
        commit = db.commit
        def fail_commit():
            raise RuntimeError("模拟资料提交失败")
        db.commit = fail_commit
        try:
            save_profile(db, db.query(User).filter(User.user_id == "PROFILE_TEACHER").one(), "不能保存", normalize_avatar(photo, "avatar.png"), False)
            raise AssertionError("应拒绝失败的提交")
        except RuntimeError:
            pass
        finally:
            db.commit = commit
        assert get("PROFILE_TEACHER") == old_teacher
        assert {p.name for p in (Path(folder) / "avatars").iterdir()} == files_before
        delete_profile(db, "PROFILE_TEACHER")
        db.rollback()
        assert client.get(old_teacher["avatarUrl"]).status_code == 200
        print("PASS 图片实际格式/比例/体积、签名上限、非法请求不落盘、仅改签名保留头像、替换与恢复默认清理")

        other_before = get("PROFILE_TEACHER")
        save("PROFILE_STU", signature="只能修改本人", userId="PROFILE_TEACHER")
        assert get("PROFILE_TEACHER") == other_before
        assert client.put("/api/v1/auth/profile", data={"signature": "匿名"}).status_code == 401
        assert client.post("/api/v1/auth/change-password", json={"currentPassword": "Start123", "password": "Changed123"}).status_code == 401
        assert client.get("/api/v1/auth/avatars/invalid.png").status_code == 404

        for uid in sessions:
            for payload, status in (({"currentPassword": "wrong", "password": "Changed123"}, 400),
                                    ({"password": "Changed123"}, 422),
                                    ({"currentPassword": "Start123", "password": "Start123"}, 400),
                                    ({"currentPassword": "Start123", "password": "汉" * 25}, 400)):
                response = client.post("/api/v1/auth/change-password", headers=headers[uid], json=payload)
                assert response.status_code == status, response.text
            legacy = client.post("/api/v1/auth/reset-password", headers=headers[uid], json={"username": uid, "password": "Bypass123"})
            assert legacy.status_code == 400
            response = client.post("/api/v1/auth/change-password", headers=headers[uid], json={"currentPassword": "Start123", "password": "Changed123"})
            assert response.status_code == 200 and response.json()["code"] == 0
            wrong = client.post("/api/v1/auth/login", json={"username": uid, "password": "Start123"}).json()
            assert wrong["code"] == 401
            assert login(uid, "Changed123")["user"]["signature"] == get(uid)["signature"]
        rows = client.get("/api/v1/admin/users", headers=headers["PROFILE_ADMIN"]).json()["data"]["list"]
        for uid in ("PROFILE_STU", "PROFILE_TEACHER"):
            row = next(row for row in rows if row["userId"] == uid)
            assert row["signature"] == get(uid)["signature"] and row["avatarUrl"] == get(uid)["avatarUrl"]
            assert "password" not in row
        print("PASS 本人权限/匿名拒绝、当前密码必填和校验、旧接口防绕过、新旧密码登录、管理员资料同步且不返回密码")

        real_teacher = login("wangjg", "123456")
        response = client.get("/api/v1/auth/profile", headers={"Authorization": "Bearer " + real_teacher["token"]})
        assert response.status_code == 200 and "classes" in response.json()["data"]
        for uid in sessions:
            assert db.query(TeacherClassDashboard).filter(TeacherClassDashboard.data_type == DATA_TYPE, TeacherClassDashboard.data_key == uid).count() == 1
        db.expire_all()
        for uid in sessions:
            stored = db.query(User).filter(User.user_id == uid).one()
            assert verify_password("Changed123", stored.password) and stored.password != "Changed123"
        deleted_url = save("PROFILE_STU", image=photo)["avatarUrl"]
        response = client.request("DELETE", "/api/v1/admin/users/PROFILE_STU", headers=headers["PROFILE_ADMIN"], json={"confirmUsername": "PROFILE_STU"})
        assert response.status_code == 200 and response.json()["code"] == 0, response.text
        assert db.query(TeacherClassDashboard).filter(TeacherClassDashboard.data_type == DATA_TYPE, TeacherClassDashboard.data_key == "PROFILE_STU").count() == 0
        assert client.get(deleted_url).status_code == 404
        assert not (Path(folder) / "avatars" / deleted_url.rsplit("/", 1)[-1]).exists()
        db.close()
        with closing(sqlite3.connect(target)) as connection:
            assert connection.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").fetchall() == schema
        assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
        print("PASS 教师账号兼容、资料记录无重复、密码哈希、删号资料清理、数据库结构不变及真实库哈希未变")
        if args.serve:
            import uvicorn
            print("库副本预览 http://127.0.0.1:8016；PROFILE_TEACHER / Changed123，PROFILE_ADMIN / Changed123")
            uvicorn.run(app, host="127.0.0.1", port=8016, lifespan="off")


if __name__ == "__main__":
    main()
