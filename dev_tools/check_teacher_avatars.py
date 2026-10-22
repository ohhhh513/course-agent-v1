"""教师端头像可见性验收：库副本中上传头像后，教师端接口必须返回同一 avatarUrl。"""
from pathlib import Path
from contextlib import ExitStack, closing
import hashlib
import io
import os
import sqlite3
import sys
import tempfile

REPO = Path(__file__).resolve().parents[1]


def main():
    source = REPO / "backend/app/data/course_agent.db"
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix="teacher-avatar-") as folder, ExitStack() as cleanup:
        target = Path(folder) / "course_agent.db"
        original = sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)
        copied = sqlite3.connect(target)
        original.backup(copied)
        original.close()
        schema = copied.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").fetchall()
        copied.close()
        os.environ.update(DATABASE_URL="sqlite:///" + target.as_posix(), DEBUG="false",
                          JWT_SECRET="teacher-avatar-copy-only", USER_AVATAR_DIR=str(Path(folder) / "avatars"))
        sys.path.insert(0, str(REPO / "backend"))
        from fastapi.testclient import TestClient
        from app.main import app
        from app.database import SessionLocal, engine
        cleanup.callback(engine.dispose)
        from app.middleware.auth import hash_password

        client = TestClient(app)
        cleanup.callback(client.close)
        db = SessionLocal()
        cleanup.callback(db.close)

        teacher = client.post("/api/v1/auth/login", json={"username": "wangjg", "password": "123456"}).json()["data"]
        th = {"Authorization": "Bearer " + teacher["token"]}
        classes = (client.get("/api/v1/auth/profile", headers=th).json()["data"]).get("classes") or []
        course = classes[0]["classId"] if classes else ""

        before = client.get("/api/v1/teacher/students", params={"size": 200}, headers=th).json()["data"]["list"]
        assert before, "教师端应能拿到本课程学生"
        for row in before:
            assert "avatarUrl" in row, "教师端学生列表必须带 avatarUrl 字段"
            assert "signature" in row, "教师端学生列表必须带 signature 字段"
        targets = [r for r in before if r["avatarUrl"] == ""][:2]
        assert targets, "需要至少两名尚未上传头像的学生"
        print(f"PASS 教师端 /students 返回 avatarUrl/signature 字段（{len(before)} 名学生，"
              f"已上传头像 {sum(1 for r in before if r['avatarUrl'])} 名）")

        # 找一名真实学生账号，在库副本里重置密码后用学生身份上传头像，
        # 验证教师端接口立刻返回同一 avatarUrl（管理员端已由 check_user_profiles 覆盖）。
        from app.models.user import User
        from app.middleware.auth import hash_password
        from PIL import Image
        stream = io.BytesIO()
        Image.new("RGBA", (512, 512), (30, 180, 160, 255)).save(stream, "PNG")
        photo = stream.getvalue()

        checked = False
        for row in targets:
            uid = row["userId"]
            stored = db.query(User).filter(User.user_id == uid).one()
            original_password = stored.password
            stored.password = hash_password("AvatarCheck123")
            db.commit()
            try:
                token = None
                for candidate in (stored.username, uid):
                    attempt = client.post("/api/v1/auth/login",
                                          json={"username": candidate, "password": "AvatarCheck123"})
                    if attempt.status_code == 200 and attempt.json().get("code") == 0:
                        token = attempt.json()["data"]["token"]
                        break
                assert token, f"学生 {uid} 应能登录"
                sh = {"Authorization": "Bearer " + token}
                saved = client.put("/api/v1/auth/profile", headers=sh,
                                   data={"signature": "教师端可见性验收", "useDefaultAvatar": "false"},
                                   files={"avatar": ("avatar.png", photo, "image/png")})
                assert saved.status_code == 200 and saved.json()["code"] == 0, saved.text
                avatar_url = saved.json()["data"]["avatarUrl"]
                assert avatar_url, "学生上传后应返回 avatarUrl"

                after = client.get("/api/v1/teacher/students", params={"size": 200}, headers=th).json()["data"]["list"]
                mine = next(r for r in after if r["userId"] == uid)
                assert mine["avatarUrl"] == avatar_url, (
                    f"教师端应看到学生上传的头像：期望 {avatar_url}，实际 {mine['avatarUrl']}")
                assert mine["signature"] == "教师端可见性验收"

                # 图片本身在教师端路径下可访问
                picture = client.get(avatar_url)
                assert picture.status_code == 200 and picture.headers["content-type"].startswith("image/png")

                # 管理员端与教师端必须看到同一个头像（两端一致）
                admin_login = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
                if admin_login.status_code == 200 and admin_login.json().get("code") == 0:
                    ah = {"Authorization": "Bearer " + admin_login.json()["data"]["token"]}
                    rows = client.get("/api/v1/admin/users", params={"size": 500}, headers=ah).json()["data"]["list"]
                    admin_row = next((r for r in rows if r["userId"] == uid), None)
                    if admin_row:
                        assert admin_row["avatarUrl"] == mine["avatarUrl"], "教师端与管理员端头像应一致"

                # 恢复默认，避免污染副本后续断言
                client.put("/api/v1/auth/profile", headers=sh,
                           data={"signature": "", "useDefaultAvatar": "true"})
                cleared = client.get("/api/v1/teacher/students", params={"size": 200}, headers=th).json()["data"]["list"]
                assert next(r for r in cleared if r["userId"] == uid)["avatarUrl"] == "", "恢复默认后教师端也应同步"
                print(f"PASS 学生 {uid} 上传头像后，教师端 /students 同步返回同一 avatarUrl，"
                      f"图片可访问，与管理员端一致；恢复默认后同步清空")
                checked = True
                break
            finally:
                db.expire_all()
                restore = db.query(User).filter(User.user_id == uid).one()
                restore.password = original_password
                db.commit()

        assert checked, "未能完成学生上传 → 教师端可见的端到端校验"
        if course:
            analysis = client.get("/api/v1/analysis/errors", params={"classId": course}, headers=th)
            if analysis.status_code == 200 and analysis.json().get("code") == 0:
                individual = analysis.json()["data"].get("commonVsIndividual", {}).get("individual", [])
                for item in individual:
                    assert "avatarUrl" in item, "归因分析 individual 必须带 avatarUrl 字段"
                print(f"PASS 教师端 /analysis 的 individual 每项带 avatarUrl（{len(individual)} 条）")

        db.close()
        with closing(sqlite3.connect(target)) as connection:
            assert connection.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").fetchall() == schema
        assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash, "真实库被改动"
        print("PASS 数据库结构不变、真实库 SHA256 未变")
    print("全部通过")


if __name__ == "__main__":
    main()