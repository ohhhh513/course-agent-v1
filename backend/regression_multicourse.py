"""
多课程回归测试（多课程重构 Step 8 固化）。

前置：后端已在 127.0.0.1:8010 运行。
覆盖：建课 → 成员隔离(403) → 邀请码入课 → 切课数据隔离 → 清理测试课程。
运行：python regression_multicourse.py [端口，默认 8010]
"""
import json
import sqlite3
import sys
import urllib.request
import urllib.error
from pathlib import Path

PORT = sys.argv[1] if len(sys.argv) > 1 else "8010"
B = f"http://127.0.0.1:{PORT}"
DB = Path(__file__).resolve().parent / "app" / "data" / "course_agent.db"

results = []


def req(method, path, token=None, body=None, headers=None):
    url = B + path
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    if token:
        r.add_header("Authorization", "Bearer " + token)
    if data:
        r.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        r.add_header(k, v)
    try:
        with urllib.request.urlopen(r, timeout=15) as resp:
            raw = resp.read().decode()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw


def check(name, status, data, want_http=200, want_code=0):
    got = (data or {}).get("code") if isinstance(data, dict) else None
    ok = (status == want_http and got == want_code)
    results.append((name, ok, status, got))
    print(f"  {'✅' if ok else '❌'} {name} (http={status} code={got})")


def login(u, p):
    s, d = req("POST", "/api/v1/auth/login", body={"username": u, "password": p})
    return (d.get("data") or {}).get("token", "") if d else ""


def hdr(tok, course=None):
    h = {}
    if course:
        h["X-Course-Id"] = course
    return h


def cleanup_course(course_id):
    """测试自清理：删课程与成员关系（多课程重构后尚无删除课程接口）"""
    con = sqlite3.connect(str(DB))
    con.execute("DELETE FROM user_courses WHERE course_id=?", (course_id,))
    con.execute("DELETE FROM courses WHERE course_id=?", (course_id,))
    con.commit()
    con.close()


def main():
    t = login("teacher", "123456")
    s = login("student", "123456")
    if not t or not s:
        print("❌ 登录失败，请确认服务已启动")
        sys.exit(1)

    print("== 1) 教师建课 ==")
    st, d = req("POST", "/api/v1/teacher/courses", t, {"name": "__回归测试课程__", "term": "test"})
    check("教师建课", st, d)
    cid = (d.get("data") or {}).get("courseId", "")
    inv = (d.get("data") or {}).get("inviteCode", "")

    print("== 2) 课程隔离 ==")
    st, d = req("GET", "/api/v1/teacher/resources", t, headers=hdr(t, cid))
    check("教师访问新课资源(空)", st, d)
    st, d = req("GET", "/api/v1/student/resources", s, headers=hdr(t, cid))
    check("学生未加入访问新课 → 403", st, d, want_http=403, want_code=None)
    results[-1] = ("学生未加入访问新课 → 403", st == 403, st, "-")

    print("== 3) 邀请码入课 ==")
    st, d = req("POST", "/api/v1/course/join", s, {"inviteCode": inv})
    check("学生凭码入课", st, d)
    st, d = req("GET", "/api/v1/student/resources", s, headers=hdr(t, cid))
    check("入课后访问新课", st, d)
    st, d = req("GET", "/api/v1/course/my", s)
    names = [c["courseId"] for c in (d.get("data") or [])]
    results.append(("my/courses 含新课", cid in names, 200, "-"))
    print(f"  {'✅' if cid in names else '❌'} my/courses 含新课")

    print("== 4) 未加入课程 403（图谱/练习/AI）==")
    st, _ = req("GET", "/api/v1/graph", s, headers=hdr(s, "C2026FAKE"))
    results.append(("图谱未加入 403", st == 403, st, "-"))
    print(f"  {'✅' if st == 403 else '❌'} 图谱未加入 403 (http={st})")
    st, _ = req("POST", "/api/v1/practice/sessions", s, {"mode": "weak"}, headers=hdr(s, "C2026FAKE"))
    results.append(("练习未加入 403", st == 403, st, "-"))
    print(f"  {'✅' if st == 403 else '❌'} 练习未加入 403 (http={st})")
    st, _ = req("GET", "/api/v1/ai/sessions", s, headers=hdr(s, "C2026FAKE"))
    results.append(("AI会话未加入 403", st == 403, st, "-"))
    print(f"  {'✅' if st == 403 else '❌'} AI会话未加入 403 (http={st})")

    print("== 5) 回归：默认课程不受影响 ==")
    st, d = req("GET", "/api/v1/student/resources", s)
    check("默认课程资源列表", st, d)
    st, d = req("GET", "/api/v1/graph?courseId=ignored", s)
    check("图谱接口(头优先)", st, d)

    print("== 6) 清理测试课程 ==")
    cleanup_course(cid)
    print(f"  已清理 {cid}")

    failed = [r for r in results if not r[1]]
    print(f"\n==== 多课程回归：{len(results) - len(failed)}/{len(results)} 通过 ====")
    for name, ok, st, got in failed:
        print(f"  ❌ {name} (http={st})")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
