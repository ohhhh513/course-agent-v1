"""课程退绑 → 删除 链路冒烟（跑在库副本上，绝不碰真库）。

复现并验证本次修复的死锁：
    教师自己建课（课程里只有他一个成员）
      → 管理端删不掉（负责人无法移出、也无法设为「无负责人」）
      → 修复后：软退绑负责人 → 课程进入「待指派负责人」→ 可直接删除

顺带验证批量退绑（管理端「当前成员」多选）。
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_DB = REPO / "backend" / "app" / "data" / "course_agent.db"


def main() -> int:
    if not DEFAULT_DB.exists():
        raise SystemExit(f"找不到数据库：{DEFAULT_DB}")
    work = tempfile.mkdtemp(prefix="course-unbind-")
    copy = Path(work) / "course_agent.db"
    shutil.copy2(DEFAULT_DB, copy)
    os.environ["DATABASE_URL"] = "sqlite:///" + copy.as_posix()
    os.environ["JWT_SECRET"] = "unbind-check-fixed-secret"
    sys.path.insert(0, str(REPO / "backend"))

    from fastapi.testclient import TestClient          # noqa: E402
    from app.main import app                            # noqa: E402

    fails: list[str] = []

    def check(cond: bool, label: str) -> None:
        print(("  [ok] " if cond else "  [FAIL] ") + label)
        if not cond:
            fails.append(label)

    def is_ok(resp) -> bool:
        """统一判断业务成功。信封约定 code=0 为成功（ok()），400/403 等为失败码。"""
        try:
            return resp.json().get("code") == 0
        except Exception:
            return False

    def biz(resp):
        try:
            return resp.json().get("code")
        except Exception:
            return None

    with TestClient(app) as client:
        def login(username: str, password: str, role: str = "admin") -> str:
            r = client.post("/api/v1/auth/login",
                            json={"username": username, "password": password, "role": role})
            body = r.json()
            return (body.get("data") or {}).get("token") or ""

        admin = login("admin", "admin")
        if not admin:
            print("  [FAIL] 管理员登录失败（试 admin/admin）")
            return 1
        H = {"Authorization": f"Bearer {admin}"}

        print("数据库副本 :", copy)
        print("1) 造一门「只有老师、没有学生和教材」的空课（复现死锁前提）")

        # 找一位已有教师
        r = client.get("/api/v1/admin/courses", headers=H).json()
        courses = (r.get("data") or {}).get("list") or []
        teacher_id = None
        for c in courses:
            if c.get("ownerId"):
                teacher_id = c["ownerId"]
                break
        if not teacher_id:
            # 从账号列表里取一位教师
            r = client.get("/api/v1/admin/users?role=teacher", headers=H).json()
            us = (r.get("data") or {}).get("list") or []
            if us:
                teacher_id = us[0]["userId"]
        check(bool(teacher_id), f"找到可用的教师 userId={teacher_id}")
        if not teacher_id:
            return 1

        r = client.post("/api/v1/admin/courses", headers=H, json={
            "name": "退绑冒烟课_教师自建", "term": "2026秋",
            "code": "SMOKE01", "classNo": "", "teacherUserId": teacher_id,
        }).json()
        cid = (r.get("data") or {}).get("courseId")
        check(bool(cid), f"建课成功 courseId={cid}（期望非空）")
        if not cid:
            return 1

        print("2) 课里只有教师一个成员 —— 这正是删不掉的那门课")
        m = client.get(f"/api/v1/admin/courses/{cid}/members", headers=H).json()
        md = m.get("data") or {}
        members = md.get("list") or []
        check(len(members) == 1, f"成员数={len(members)}（期望 1，只有老师）")
        check(md.get("ownerBound") is True, f"ownerBound={md.get('ownerBound')}（期望 True，负责人还在位）")
        owner_row = next((x for x in members if x.get("isOwner")), None)
        check(owner_row is not None, "负责人行存在")
        owner_id = owner_row["userId"] if owner_row else ""

        print("3) 修复点：负责人现在可以退绑（以前这里直接 400 拒绝）")
        resp = client.delete(f"/api/v1/admin/courses/{cid}/members/{owner_id}", headers=H)
        check(is_ok(resp), f"退绑负责人 → code={biz(resp)}（期望 0 · 以前是 400）")
        check((resp.json().get("data") or {}).get("removed") == 1, "removed=1")

        m = client.get(f"/api/v1/admin/courses/{cid}/members", headers=H).json()
        md = m.get("data") or {}
        check(len(md.get("list") or []) == 0, "退绑后成员为空")
        check(md.get("ownerBound") is False, f"ownerBound={md.get('ownerBound')}（期望 False · 待指派负责人）")
        check(bool(md.get("ownerId")), f"ownerId 仍保留={md.get('ownerId')}（软退绑：不改 courses.owner_id）")

        print("4) 退绑后可以直接删课了（死锁解开）")
        resp = client.delete(f"/api/v1/admin/courses/{cid}", headers=H)
        check(is_ok(resp), f"删除课程 → code={biz(resp)}（期望 0）")

        print("5) 批量退绑（管理端「当前成员」多选一次移出多个）")
        r = client.post("/api/v1/admin/courses", headers=H, json={
            "name": "退绑冒烟课_批量", "term": "2026秋",
            "code": "SMOKE02", "classNo": "", "teacherUserId": teacher_id,
        }).json()
        cid2 = (r.get("data") or {}).get("courseId")
        check(bool(cid2), f"建课成功 courseId={cid2}")
        if cid2:
            # 造一个「负责人 + 3 名学生」的真实多成员课程。
            # 学生入课走 bind-classes（按班级），这里直接挑库里已有班级的学生，
            # 用 roster/commit 太重，改走 services 层的等价公开入口 bind_users。
            from app.models.user import User as _User          # noqa: E402
            from app.services.course_admin import _get_course as _gc, bind_users  # noqa: E402
            from app.database import SessionLocal                # noqa: E402

            with SessionLocal() as sdb:
                students = sdb.query(_User).filter(_User.role == "student").limit(3).all()
                if students:
                    c2 = _gc(sdb, cid2)
                    res = bind_users(sdb, c2, students)
                    sdb.commit()
                    check(res["bound"] == len(students),
                          f"绑定 {len(students)} 名学生（bound={res['bound']}）")
                    sids = [u.user_id for u in students]
                else:
                    sids = []

            m = client.get(f"/api/v1/admin/courses/{cid2}/members", headers=H).json()
            md2 = m.get("data") or {}
            all_members = md2.get("list") or []
            check(len(all_members) >= 2, f"成员数={len(all_members)}（期望 ≥2，含负责人与学生）")

            # 空列表必须被拒
            resp = client.post(f"/api/v1/admin/courses/{cid2}/unbind-members", headers=H,
                               json={"userIds": []})
            check(biz(resp) == 400, f"空列表批量退绑 → code={biz(resp)}（期望 400 · 请先勾选）")

            # 一次勾选多人（含负责人）全部移出
            targets = [x["userId"] for x in all_members][:3]
            resp = client.post(f"/api/v1/admin/courses/{cid2}/unbind-members", headers=H,
                               json={"userIds": targets})
            check(is_ok(resp), f"批量退绑 {len(targets)} 人 → code={biz(resp)}（期望 0）")
            data = resp.json().get("data") or {}
            check(data.get("removed") == len(targets),
                  f"removed={data.get('removed')}（期望 {len(targets)}）")

            m = client.get(f"/api/v1/admin/courses/{cid2}/members", headers=H).json()
            left = {x["userId"] for x in (m.get("data") or {}).get("list") or []}
            check(not (left & set(targets)),
                  f"勾选的 {len(targets)} 人已全部移出（剩余成员 {len(left)} 人）")

            # 不存在的账号必须报错，且不能顺带把别人移掉
            resp = client.post(f"/api/v1/admin/courses/{cid2}/unbind-members", headers=H,
                               json={"userIds": ["__NO_SUCH_USER__"]})
            check(biz(resp) == 400, f"不存在的账号 → code={biz(resp)}（期望 400）")

            client.delete(f"/api/v1/admin/courses/{cid2}", headers=H)

    print()
    if fails:
        print(f"结果：{len(fails)} 项未通过")
        for f in fails:
            print("  - " + f)
        return 1
    print("结果：全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())