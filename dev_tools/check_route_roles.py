"""路由角色闸门验收（真实 FastAPI + 真实登录 + 库副本）。

用法（backend/.venv 的解释器）：

    python dev_tools/check_route_roles.py

做什么：
1. 把演示库复制到临时目录（绝不写真实库）；
2. 用 TestClient 拉起真实应用（含启动事件：建表、确保 admin、预警检测）；
3. 分别用 学生 / 教师 / 管理员 token 请求教师端前缀、/agent/ingest/* 与公开前缀，
   断言「教师端前缀与入库端点：学生 403、教师 200、管理员不被角色闸门拦」
   且「学生端前缀与 /agent/status 不受影响」。

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

        def detail(r):
            if not r.headers.get("content-type", "").startswith("application/json"):
                return ""
            return str(r.json().get("detail", ""))

        def call(method: str, path: str, token: str, json=None):
            kw = {"headers": {"Authorization": f"Bearer {token}", "X-Course-Id": COURSE}}
            if json is not None:
                kw["json"] = json
            return client.request(method, path, **kw)

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

        print("2) /agent/ingest/*：入库运维端点（同一套角色闸门，逐个端点显式挂）")
        s = call("GET", "/api/v1/agent/ingest/stats", student)
        t = call("GET", "/api/v1/agent/ingest/stats", teacher)
        a = call("GET", "/api/v1/agent/ingest/stats", admin)
        s_detail = str(s.json().get("detail", "")) if s.headers.get("content-type", "").startswith("application/json") else ""
        check(s.status_code == 403 and "无权访问该接口" in s_detail,
              f"学生 /agent/ingest/stats → {s.status_code} {s_detail[:24]}（期望 403 角色闸门）")
        check(t.status_code == 200, f"教师 /agent/ingest/stats → {t.status_code}（期望 200）")
        a_detail = str(a.json().get("detail", "")) if a.headers.get("content-type", "").startswith("application/json") else ""
        check(a.status_code != 403 or "无权访问该接口" not in a_detail,
              f"管理员 /agent/ingest/stats → {a.status_code} {a_detail[:24]}（不得被角色闸门拦截）")

        print("3) /agent/status 与学生端/公共前缀不受影响")
        student_side = [
            ("GET", "/api/v1/agent/status"),
            ("GET", "/api/v1/student/dashboard"),
            ("GET", "/api/v1/course/my"),
        ]
        for method, path in student_side:
            s = call(method, path, student)
            check(s.status_code == 200, f"学生 {path} → {s.status_code}（期望 200）")

        print("4) 未登录仍是 401（不是 403）")
        r = client.get("/api/v1/teacher/classes", headers={"X-Course-Id": COURSE})
        check(r.status_code == 401, f"匿名 /teacher/classes → {r.status_code}（期望 401）")
        r2 = client.get("/api/v1/agent/ingest/stats", headers={"X-Course-Id": COURSE})
        check(r2.status_code == 401, f"匿名 /agent/ingest/stats → {r2.status_code}（期望 401）")

        print("5) /admin/agent/*：仅管理员可用（教师/学生 403，匿名 401）")
        admin_agent_endpoints = [
            ("GET", "/api/v1/admin/agent/sessions"),
            ("POST", "/api/v1/admin/agent/chat/stream"),
            ("POST", "/api/v1/admin/agent/chat/stop"),
            ("GET", "/api/v1/admin/agent/sessions/CHNOPE/messages"),
            ("DELETE", "/api/v1/admin/agent/sessions/CHNOPE"),
        ]
        for method, path in admin_agent_endpoints:
            a = call(method, path, admin, json={"sessionId": "new", "question": "x"} if method == "POST" else None)
            t = call(method, path, teacher, json={"sessionId": "new", "question": "x"} if method == "POST" else None)
            s = call(method, path, student, json={"sessionId": "new", "question": "x"} if method == "POST" else None)
            td = detail(t); sd = detail(s)
            check(t.status_code == 403 and "无权访问" in td,
                  f"教师 {path} → {t.status_code} {td[:24]}（期望 403 角色闸门）")
            check(s.status_code == 403 and "无权访问" in sd,
                  f"学生 {path} → {s.status_code} {sd[:24]}（期望 403 角色闸门）")
            # 管理员：角色闸门放行（进入 SSE 流或正常返回，不为 403/401）
            if method == "GET" and "messages" in path or method == "DELETE":
                # 这些是带具体 session 的端点：管理员因 session 不存在应 404，但不应是 403/401
                check(a.status_code not in (403, 401),
                      f"管理员 {path} → {a.status_code}（角色闸门放行，期望非 403/401）")
            elif method == "GET":
                check(a.status_code == 200, f"管理员 {path} → {a.status_code}（期望 200）")
            else:  # POST chat/stream：进入 SSE 流（200），不消费 body
                check(a.status_code == 200, f"管理员 {path} → {a.status_code}（期望 200，进入 SSE）")
        # 5b) 上传附件的 multipart 形态（管理员智能助手 · 附到当前问题）：
        #     管理员放行且真正进入 SSE（含 meta）；教师/学生仍在角色闸门 403；不支持的类型 400。
        a_att = client.post("/api/v1/admin/agent/chat/stream",
                            files={"files": ("notes.txt", "平台数据说明：学生 10 名，教师 1 名。".encode("utf-8"), "text/plain")},
                            data={"sessionId": "new", "question": "这个附件说了什么？"},
                            headers={"Authorization": f"Bearer {admin}", "X-Course-Id": COURSE})
        check(a_att.status_code == 200 and "event: meta" in a_att.text,
              f"管理员 multipart 附件提问 → {a_att.status_code}（期望 200 且 SSE 含 meta）")
        t_att = client.post("/api/v1/admin/agent/chat/stream",
                            files={"files": ("notes.txt", b"x", "text/plain")},
                            data={"sessionId": "new", "question": "x"},
                            headers={"Authorization": f"Bearer {teacher}", "X-Course-Id": COURSE})
        s_att = client.post("/api/v1/admin/agent/chat/stream",
                            files={"files": ("notes.txt", b"x", "text/plain")},
                            data={"sessionId": "new", "question": "x"},
                            headers={"Authorization": f"Bearer {student}", "X-Course-Id": COURSE})
        check(t_att.status_code == 403, f"教师 multipart 附件提问 → {t_att.status_code}（期望 403）")
        check(s_att.status_code == 403, f"学生 multipart 附件提问 → {s_att.status_code}（期望 403）")
        a_bad = client.post("/api/v1/admin/agent/chat/stream",
                            files={"files": ("old.doc", b"xx", "application/msword")},
                            data={"sessionId": "new", "question": "x"},
                            headers={"Authorization": f"Bearer {admin}", "X-Course-Id": COURSE})
        check(a_bad.status_code == 400 and "不支持的文件类型" in a_bad.text,
              f"管理员上传 .doc 附件 → {a_bad.status_code}（期望 400 · 不支持的类型）")
        # 5c) 治理写操作的审批端点（P2c 平台级）：教师/学生 403；管理员放行到归属校验（不存在 → 403+「不存在」）
        for path in ("/api/v1/admin/agent/actions/ACNOPE/approve",
                     "/api/v1/admin/agent/actions/ACNOPE/reject"):
            t_a = call("POST", path, teacher)
            s_a = call("POST", path, student)
            a_a = call("POST", path, admin)
            check(t_a.status_code == 403 and "无权访问" in detail(t_a),
                  f"教师 {path} → {t_a.status_code} {detail(t_a)[:20]}（期望 403 角色闸门）")
            check(s_a.status_code == 403 and "无权访问" in detail(s_a),
                  f"学生 {path} → {s_a.status_code} {detail(s_a)[:20]}（期望 403 角色闸门）")
            check(a_a.status_code == 403 and "不存在" in detail(a_a),
                  f"管理员 {path} → {a_a.status_code} {detail(a_a)[:22]}（期望 403 · 动作不存在，非角色闸门）")
        r4 = client.post("/api/v1/admin/agent/actions/ACNOPE/approve", headers={"X-Course-Id": COURSE})
        check(r4.status_code == 401, f"匿名 POST /admin/agent/actions/ACNOPE/approve → {r4.status_code}（期望 401）")
        # 匿名访问管理员智能体
        r3 = client.post("/api/v1/admin/agent/chat/stream",
                         headers={"X-Course-Id": COURSE},
                         json={"sessionId": "new", "question": "x"})
        check(r3.status_code == 401, f"匿名 POST /admin/agent/chat/stream → {r3.status_code}（期望 401）")

        print("5d) 停止生成与批量删除（新端点三档）")
        # 答疑侧停止：学生/教师可用（own session）；匿名 401；非本会话 404
        for token, who in ((student, "学生"), (teacher, "教师")):
            r_new = call("POST", "/api/v1/ai/chat/stop", token, json={"sessionId": "new"})
            check(r_new.status_code == 200, f"{who} POST /ai/chat/stop（sessionId=new）→ {r_new.status_code}（期望 200）")
        r_anon = client.post("/api/v1/ai/chat/stop", headers={"X-Course-Id": COURSE},
                             json={"sessionId": "new"})
        check(r_anon.status_code == 401, f"匿名 POST /ai/chat/stop → {r_anon.status_code}（期望 401）")
        r_other = call("POST", "/api/v1/ai/chat/stop", student, json={"sessionId": "CHNOPE123"})
        # 本项目约定：fail() 走「HTTP 200 + 信封 code」，不是真 404
        check(r_other.status_code == 200 and r_other.json().get("code") == 404,
              f"学生停止别人的/不存在的会话 → HTTP {r_other.status_code} code={r_other.json().get('code')}（期望 200/404 信封）")
        # 答疑附件（multipart 形态）：匿名 401；师生进流 200
        # （接口对师生开放，三端界面均已渲染上传按钮：学生「AI 智能答疑」/教师「智能答疑」/管理端「智能助手」）
        att = {"files": ("a.txt", b"hello", "text/plain")}
        r_att_anon = client.post("/api/v1/ai/chat/stream", files=att,
                                 data={"sessionId": "new", "question": "附件测试"},
                                 headers={"X-Course-Id": COURSE})
        check(r_att_anon.status_code == 401,
              f"匿名 multipart /ai/chat/stream → {r_att_anon.status_code}（期望 401）")
        for token, who in ((teacher, "教师"), (student, "学生")):
            r_att = client.post("/api/v1/ai/chat/stream", files=att,
                                data={"sessionId": "new", "question": "附件测试"},
                                headers={"Authorization": f"Bearer {token}", "X-Course-Id": COURSE})
            check(r_att.status_code == 200,
                  f"{who} multipart /ai/chat/stream → {r_att.status_code}（期望 200，进入 SSE）")
        # 治理侧停止（在 5) 的三档里已覆盖）；批量删除：三档 + 空列表 400 信封
        for token, who, expect in ((teacher, "教师", 403), (student, "学生", 403)):
            r_bd = call("POST", "/api/v1/admin/users/batch-delete", token, json={"userIds": ["Sx"]})
            check(r_bd.status_code == expect and "无权访问" in detail(r_bd),
                  f"{who} POST /admin/users/batch-delete → {r_bd.status_code}（期望 403 角色闸门）")
        r_bd_anon = client.post("/api/v1/admin/users/batch-delete", headers={"X-Course-Id": COURSE},
                                json={"userIds": ["Sx"]})
        check(r_bd_anon.status_code == 401, f"匿名 POST /admin/users/batch-delete → {r_bd_anon.status_code}（期望 401）")
        r_bd_empty = call("POST", "/api/v1/admin/users/batch-delete", admin, json={"userIds": []})
        check(r_bd_empty.status_code == 200 and r_bd_empty.json().get("code") == 400,
              f"管理员批量删除空列表 → HTTP {r_bd_empty.status_code} code={r_bd_empty.json().get('code')}（期望 200/400 信封）")

        print("6) /admin/users/import/*：批量导入（仅管理员，教师/学生 403，匿名 401）")
        # 在内存里造一个合法的 xlsx（2 行学生），用于预览校验
        from io import BytesIO
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.append(["用户名", "姓名", "密码", "班级", "学号"])
        ws.append(["imp_a", "导入甲", "123456", "计算机2301班", "2301001"])
        ws.append(["imp_b", "导入乙", "123456", "计算机2301班", "2301002"])
        xlsx_bytes = BytesIO()
        wb.save(xlsx_bytes)
        xlsx_bytes = xlsx_bytes.getvalue()

        def call_multipart(path: str, token: str, files: dict, data: dict):
            return client.post(path, files=files, data=data,
                               headers={"Authorization": f"Bearer {token}", "X-Course-Id": COURSE})

        xfiles = {"file": ("students.xlsx", xlsx_bytes,
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
        # 6a) 模板下载（GET）
        t_tpl = client.get("/api/v1/admin/users/import/template?role=student&format=xlsx",
                           headers={"Authorization": f"Bearer {teacher}", "X-Course-Id": COURSE})
        s_tpl = client.get("/api/v1/admin/users/import/template?role=student&format=xlsx",
                           headers={"Authorization": f"Bearer {student}", "X-Course-Id": COURSE})
        a_tpl = client.get("/api/v1/admin/users/import/template?role=student&format=xlsx",
                           headers={"Authorization": f"Bearer {admin}", "X-Course-Id": COURSE})
        check(t_tpl.status_code == 403, f"教师 GET /admin/users/import/template → {t_tpl.status_code}（期望 403）")
        check(s_tpl.status_code == 403, f"学生 GET /admin/users/import/template → {s_tpl.status_code}（期望 403）")
        check(a_tpl.status_code == 200, f"管理员 GET /admin/users/import/template → {a_tpl.status_code}（期望 200）")
        # 6b) 预览（POST multipart，只读不写库）
        t_pv = call_multipart("/api/v1/admin/users/import/preview", teacher, xfiles, {"role": "student"})
        s_pv = call_multipart("/api/v1/admin/users/import/preview", student, xfiles, {"role": "student"})
        a_pv = call_multipart("/api/v1/admin/users/import/preview", admin, xfiles, {"role": "student"})
        td = detail(t_pv); sd = detail(s_pv)
        check(t_pv.status_code == 403 and "无权访问" in td,
              f"教师 POST /admin/users/import/preview → {t_pv.status_code} {td[:24]}（期望 403）")
        check(s_pv.status_code == 403 and "无权访问" in sd,
              f"学生 POST /admin/users/import/preview → {s_pv.status_code} {sd[:24]}（期望 403）")
        a_pv_body = a_pv.json().get("data", {}) if a_pv.headers.get("content-type", "").startswith("application/json") else {}
        check(a_pv.status_code == 200 and a_pv_body.get("total") == 2 and a_pv_body.get("valid") == 2,
              f"管理员 POST /admin/users/import/preview → {a_pv.status_code} total={a_pv_body.get('total')} valid={a_pv_body.get('valid')}（期望 200/2/2）")
        # 6c) 匿名预览 401
        r4 = client.post("/api/v1/admin/users/import/preview", files=xfiles, data={"role": "student"},
                         headers={"X-Course-Id": COURSE})
        check(r4.status_code == 401, f"匿名 POST /admin/users/import/preview → {r4.status_code}（期望 401）")

    print()
    if fails:
        print(f"结果：{len(fails)} 项失败")
        return 1
    print("结果：全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
