"""路由角色闸门验收（真实 FastAPI + 真实登录 + 库副本）。

用法（backend/.venv 的解释器）：

    python dev_tools/check_route_roles.py

做什么：
1. 把演示库复制到临时目录（绝不写真实库）；
2. 用 TestClient 拉起真实应用（含启动事件：建表、确保 admin、预警检测）；
3. 分别用 学生 / 教师 / 管理员 token 请求教师端前缀与公开前缀，
   断言「教师端前缀：学生 403、教师/管理员 200」且「学生端前缀不受影响」。

返回值：0 = 全部通过；1 = 有失败项。
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_DB = REPO / "backend" / "app" / "data" / "course_agent.db"
COURSE = "CCHYJTKE"


def main() -> int:
    if not DEFAULT_DB.exists():
        raise SystemExit(f"找不到数据库：{DEFAULT_DB}")
    work = tempfile.mkdtemp(prefix="route-role-")
    copy = Path(work) / "course_agent.db"
    shutil.copy2(DEFAULT_DB, copy)
    os.environ["DATABASE_URL"] = "sqlite:///" + copy.as_posix()
    os.environ["JWT_SECRET"] = "role-check-fixed-secret"
    sys.path.insert(0, str(REPO / "backend"))

    from fastapi.testclient import TestClient          # noqa: E402
    from app.main import app                            # noqa: E402

    fails: list[str] = []

    def check(cond: bool, label: str) -> None:
        print(("  [ok] " if cond else "  [FAIL] ") + label)
        if not cond:
            fails.append(label)

    with TestClient(app) as client:
        def login(username: str, password: str) -> str:
            r = client.post("/api/v1/auth/login",
                            json={"username": username, "password": password, "role": "student"})
            body = r.json()
            token = (body.get("data") or {}).get("token") or ""
            if not token:
                raise SystemExit(f"登录失败 {username}: {r.status_code} {body}")
            return token

        def call(method: str, path: str, token: str):
            return client.request(method, path, headers={
                "Authorization": f"Bearer {token}", "X-Course-Id": COURSE,
            })

        student = login("stu01", "123456")
        teacher = login("wangjg", "123456")
        admin = login("admin", "admin")
        print(f"数据库副本 : {copy}")
        print("1) 教师端前缀：学生必须 403，教师/管理员 200")

        teacher_only = [
            ("GET", "/api/v1/teacher/classes", None),
            ("GET", "/api/v1/analysis/errors", None),
            ("GET", "/api/v1/question/bank", None),
            ("GET", "/api/v1/intervention/list", None),
            ("GET", "/api/v1/report/list", None),
        ]
        for method, path, _ in teacher_only:
            s = call(method, path, student)
            t = call(method, path, teacher)
            a = call(method, path, admin)
            s_detail = str(s.json().get("detail", "")) if s.headers.get("content-type", "").startswith("application/json") else ""
            check(s.status_code == 403 and "无权访问该接口" in s_detail,
                  f"学生 {path} → {s.status_code} {s_detail[:24]}（期望 403 角色闸门）")
            check(t.status_code != 403, f"教师 {path} → {t.status_code}（期望非 403）")
            # 管理员可能因为「不是该课程成员」被 403（预存在行为，与本闸门无关），
            # 但绝不能再被角色闸门拦下。
            a_detail = str(a.json().get("detail", "")) if a.headers.get("content-type", "").startswith("application/json") else ""
            check(a.status_code != 403 or "无权访问该接口" not in a_detail,
                  f"管理员 {path} → {a.status_code} {a_detail[:24]}（不得被角色闸门拦截）")

        print("2) 学生端/公共前缀不受影响")
        student_side = [
            ("GET", "/api/v1/student/dashboard"),
            ("GET", "/api/v1/course/my"),
        ]
        for method, path in student_side:
            s = call(method, path, student)
            check(s.status_code == 200, f"学生 {path} → {s.status_code}（期望 200）")

        print("3) 未登录仍是 401（不是 403）")
        r = client.get("/api/v1/teacher/classes", headers={"X-Course-Id": COURSE})
        check(r.status_code == 401, f"匿名 /teacher/classes → {r.status_code}（期望 401）")

    print()
    if fails:
        print(f"结果：{len(fails)} 项失败")
        return 1
    print("结果：全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
