import json, os, urllib.request, urllib.error

# 默认打本机 8000；独立实例验证时用 BASE=http://127.0.0.1:8010 覆盖
B = os.environ.get("BASE", "http://127.0.0.1:8000")
# 真实账号（2026-09-29 校正：库中已无演示号 student/teacher，原脚本按提示账号登录必然失败）
STUDENT_USER = os.environ.get("STUDENT_USER", "stu01")
TEACHER_USER = os.environ.get("TEACHER_USER", "wangjg")
PASSWORD = os.environ.get("PASSWORD", "123456")
# 写入类用例（反馈落库）默认执行；在真实库上可设 SKIP_WRITE=1 跳过
SKIP_WRITE = os.environ.get("SKIP_WRITE", "") == "1"


def req(method, path, token=None, body=None):
    url = B + path
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    if token:
        r.add_header("Authorization", "Bearer " + token)
    if data:
        r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            raw = resp.read().decode()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw


def login(u, p):
    s, d = req("POST", "/api/v1/auth/login", body={"username": u, "password": p})
    if not isinstance(d, dict):
        return ""
    return ((d.get("data") or {}).get("token")) or ""


results = []


def check(name, status, data, want_http=200, want_code=0):
    got = (data or {}).get("code") if isinstance(data, dict) else None
    ok = (status == want_http and got == want_code)
    results.append((name, ok, status, got))


def check_sec(name, status, want_http=401):
    results.append((name, status == want_http, status, "(no envelope code)"))


def check_forbidden(name, status, data):
    """越权：项目里 403 有两种落地方式 —— 依赖层 raise HTTPException(403)（HTTP 403），
    业务层 return fail(...,403)（HTTP 200 + 信封 code=403）。两者都算通过。"""
    code = (data or {}).get("code") if isinstance(data, dict) else None
    ok = (status == 403) or (status == 200 and code == 403)
    results.append((name, ok, status, code if code is not None else "http-403"))


def check_gone(name, status):
    """已下线端点：HTTP 应为 404（路由不存在），或 405（路径只剩 PUT/DELETE 等其它方法，
    即被 `/question/{qId}` 这类单段动态路由占用、POST 不再被允许）——两者都证明该端点已不存在。

    2026-09-29「接口占位与伪数据」清理后下列端点已从后端删除，
    这里改为断言「确实不存在」，避免日后被误加回来。
    """
    results.append((name, status in (404, 405), status, "expected 404/405"))


s_tok = login(STUDENT_USER, PASSWORD)
t_tok = login(TEACHER_USER, PASSWORD)
if not s_tok or not t_tok:
    print(f"[FATAL] 登录失败：student({STUDENT_USER})={bool(s_tok)} teacher({TEACHER_USER})={bool(t_tok)}")
    print("        请用 STUDENT_USER / TEACHER_USER / PASSWORD 环境变量指定当前库中的真实账号。")
    raise SystemExit(1)

# ---- 动态发现当前库中的真实 course_id / class_id / student_id ----
_, _my = req("GET", "/api/v1/course/my", t_tok)
_my_list = (_my or {}).get("data") or []
course_id = (_my_list[0].get("courseId") if _my_list else "") or ""

_, _cls = req("GET", "/api/v1/teacher/classes", t_tok)
_cls_list = (_cls or {}).get("data") or []
class_id = (_cls_list[0].get("classId") if _cls_list else "") or ""

_, _stu = req("GET", f"/api/v1/teacher/students?classId={class_id}", t_tok)
_d = (_stu or {}).get("data")
_stu_list = (_d.get("list") if isinstance(_d, dict) else _d) or []
student_id = (_stu_list[0].get("userId") if _stu_list else "") or ""

_, qbank = req("GET", "/api/v1/question/bank", t_tok)
q_id = ((qbank.get("data") or {}).get("list") or [{}])[0].get("qId") if qbank else None
_, graph = req("GET", "/api/v1/graph", s_tok)
kp_id = ((graph.get("data") or {}).get("nodes") or [{}])[0].get("id") if graph else None

print(f"  发现 course={course_id!r} class={class_id!r} student={student_id!r}")

# --- student endpoints (expect code=0) ---
check("student/dashboard", *req("GET", "/api/v1/student/dashboard", s_tok))
check("student/alerts", *req("GET", "/api/v1/student/alerts", s_tok))
check("student/compare", *req("GET", "/api/v1/student/compare", s_tok))
check("student/growth", *req("GET", "/api/v1/student/growth", s_tok))
check("student/mastery/matrix", *req("GET", "/api/v1/student/mastery/matrix", s_tok))
check("student/messages", *req("GET", "/api/v1/student/messages", s_tok))
check("student/resources", *req("GET", "/api/v1/student/resources", s_tok))
check("auth/profile", *req("GET", "/api/v1/auth/profile", s_tok))
check("practice/wrong-book", *req("GET", "/api/v1/practice/wrong-book?page=1&size=10", s_tok))
check("graph", *req("GET", "/api/v1/graph", s_tok))
check("graph/path", *req("GET", "/api/v1/graph/path", s_tok))
check("course/my", *req("GET", "/api/v1/course/my", s_tok))
if course_id:
    check("course/{id}", *req("GET", f"/api/v1/course/{course_id}", s_tok))

# --- teacher endpoints (expect code=0) ---
check("teacher/classes", *req("GET", "/api/v1/teacher/classes", t_tok))
check("teacher/dashboard", *req("GET", f"/api/v1/teacher/dashboard?classId={class_id}", t_tok))
check("teacher/students", *req("GET", f"/api/v1/teacher/students?classId={class_id}", t_tok))
check("teacher/heatmap", *req("GET", f"/api/v1/teacher/heatmap?classId={class_id}", t_tok))
check("teacher/alerts", *req("GET", f"/api/v1/teacher/alerts?classId={class_id}", t_tok))
if student_id:
    check("teacher/messages (POST send)", *req("POST", "/api/v1/teacher/messages", t_tok, {"userId": student_id, "content": "回归测试消息"}))
check("question/gen/config", *req("GET", "/api/v1/question/gen/config", t_tok))
check("question/bank", *req("GET", "/api/v1/question/bank", t_tok))
check("question/drafts", *req("GET", "/api/v1/question/drafts", t_tok))
check("agent/status", *req("GET", "/api/v1/agent/status", t_tok))


def check_gen_sse():
    """question/gen 为 SSE 流式出题：校验响应为 text/event-stream 且首个 event 行可读。

    注意：该端点要求「至少一个知识点或一道例题」，否则返回 400 信封而非 SSE。
    """
    body = json.dumps({"count": 1, "difficulty": 3, "kpIds": [kp_id] if kp_id else []}).encode()
    r = urllib.request.Request(
        B + "/api/v1/question/gen", data=body, method="POST",
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + t_tok},
    )
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            ctype = resp.headers.get("Content-Type", "")
            first = ""
            for _ in range(20):  # 跳过空行 / sse ping 注释，直到首个 event 行
                line = resp.readline().decode("utf-8", "ignore")
                if line.startswith("event:"):
                    first = line.strip()
                    break
            ok = "text/event-stream" in ctype and first.startswith("event:")
            return ok, f"ctype={ctype.split(';')[0]} first={first[:40]!r}"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


_gen_ok, _gen_detail = check_gen_sse()
print(f"  [{'PASS' if _gen_ok else 'FAIL'}] question/gen (SSE streaming) -> {_gen_detail}")
results.append(("question/gen (SSE streaming)", _gen_ok, 200, "text/event-stream"))

check("report/list", *req("GET", f"/api/v1/report/list?classId={class_id}", t_tok))
check("analysis/errors", *req("GET", f"/api/v1/analysis/errors?classId={class_id}", t_tok))
check("intervention/list", *req("GET", f"/api/v1/intervention/list?classId={class_id}", t_tok))
check("intervention/templates", *req("GET", "/api/v1/intervention/templates", t_tok))

# deeper: wrong-book detail + graph/kp if ids present
if q_id:
    check("practice/wrong-book/{q}/detail", *req("GET", f"/api/v1/practice/wrong-book/{q_id}/detail", s_tok))
if kp_id:
    check("graph/kp/{kp}", *req("GET", f"/api/v1/graph/kp/{kp_id}", s_tok))

# --- 2026-09-29「接口占位与伪数据」：已删除端点必须 404 ---
check_gone("student/ability/radar GONE -> 404", req("GET", "/api/v1/student/ability/radar", s_tok)[0])
check_gone("analysis/causes GONE -> 404", req("GET", f"/api/v1/analysis/causes?classId={class_id}", t_tok)[0])
check_gone("analysis/weak-chain GONE -> 404", req("GET", f"/api/v1/analysis/weak-chain?classId={class_id}", t_tok)[0])
check_gone("question/materials GONE -> 404", req("POST", "/api/v1/question/materials", t_tok, {"name": "x.pdf"})[0])
check_gone("question/packs GONE -> 404", req("POST", "/api/v1/question/packs", t_tok, {"kpIds": [], "count": 6})[0])
check_gone("question/gen/stream GONE -> 404", req("POST", "/api/v1/question/gen/stream", t_tok, {"count": 1})[0])
check_gone("ai/suggest-questions GONE -> 404", req("GET", "/api/v1/ai/suggest-questions", s_tok)[0])
check_gone("intervention/{id}/effect GONE -> 404", req("GET", "/api/v1/intervention/IV_TEST/effect", t_tok)[0])

# --- 2026-09-30「四、隔离与权限」P38：学生 token 调教师端接口必须 403 ---
for _p in ("/api/v1/teacher/classes", "/api/v1/teacher/dashboard",
           "/api/v1/analysis/errors", "/api/v1/question/bank",
           "/api/v1/report/list", "/api/v1/intervention/list"):
    _s, _d = req("GET", _p, s_tok)
    check_forbidden("P38 student->" + _p.replace("/api/v1/", ""), _s, _d)

# --- P17 归属校验：不存在的题目走新校验路径应 404（而不是 500/静默成功） ---
check("P17 question PUT unknown -> 404",
      *req("PUT", "/api/v1/question/Q-NOT-EXIST-REGRESSION", t_tok, {"difficulty": 3}), want_code=404)
check("P17 question DELETE unknown -> 404",
      *req("DELETE", "/api/v1/question/Q-NOT-EXIST-REGRESSION", t_tok), want_code=404)


# --- P10③ /ai/feedback：真实落库（写入类，SKIP_WRITE=1 可跳过） ---
def check_feedback():
    if SKIP_WRITE:
        return True, "skipped(SKIP_WRITE=1)"
    s1, d1 = req("POST", "/api/v1/ai/feedback", s_tok,
                 {"messageId": "M-REGRESSION-CHECK", "sessionId": "CH-REGRESSION", "feedback": 1})
    ok1 = (s1 == 200 and isinstance(d1, dict) and d1.get("code") == 0)
    # 缺 messageId 必须 422（修复前前端正是漏传该字段，实际操作必然失败）
    s2, _ = req("POST", "/api/v1/ai/feedback", s_tok, {"feedback": 1})
    # 非法取值必须被拒（信封 code != 0）
    s3, d3 = req("POST", "/api/v1/ai/feedback", s_tok, {"messageId": "M-REGRESSION-CHECK", "feedback": 9})
    ok3 = (s3 == 200 and isinstance(d3, dict) and d3.get("code") != 0)
    # 点踩（-1）也必须被接受
    s4, d4 = req("POST", "/api/v1/ai/feedback", s_tok,
                 {"messageId": "M-REGRESSION-CHECK-DOWN", "feedback": -1})
    ok4 = (s4 == 200 and isinstance(d4, dict) and d4.get("code") == 0)
    return (ok1 and s2 == 422 and ok3 and ok4), \
        f"up={s1} noMessageId={s2}(want 422) badValue={s3}/code={(d3 or {}).get('code')} down={s4}"


_fb_ok, _fb_detail = check_feedback()
print(f"  [{'PASS' if _fb_ok else 'FAIL'}] ai/feedback (real persist) -> {_fb_detail}")
results.append(("ai/feedback (real persist)", _fb_ok, 200, "code=0"))


# --- P14 /auth/logout：吊销后旧 token 必须 401 ---
def check_logout_revokes():
    tok = login(STUDENT_USER, PASSWORD)
    if not tok:
        return False, "无法登录取得 token"
    s1, d1 = req("POST", "/api/v1/auth/logout", tok)
    ok1 = (s1 == 200 and isinstance(d1, dict) and d1.get("code") == 0)
    s2, _ = req("GET", "/api/v1/student/dashboard", tok)
    return (ok1 and s2 == 401), f"logout={s1} reuse_old_token={s2}(want 401)"


_lo_ok, _lo_detail = check_logout_revokes()
print(f"  [{'PASS' if _lo_ok else 'FAIL'}] auth/logout (revoke token) -> {_lo_detail}")
results.append(("auth/logout (revoke token)", _lo_ok, 200, "reuse->401"))

check_sec("auth/logout NO token -> 401", req("POST", "/api/v1/auth/logout")[0])

# --- security: no token -> 401 (HTTP level) ---
check_sec("teacher/classes NO token -> 401", req("GET", "/api/v1/teacher/classes")[0])
check_sec("student/dashboard NO token -> 401", req("GET", "/api/v1/student/dashboard")[0])
check_sec("reset-password NO token -> 401", req("POST", "/api/v1/auth/reset-password", body={"username": "x", "oldPassword": "y", "newPassword": "z"})[0])

print(f"{'ALL PASS' if all(r[1] for r in results) else 'SOME FAIL'}  total={len(results)} passed={sum(r[1] for r in results)}")
for name, ok, status, got in results:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name} -> http={status} code={got}")
