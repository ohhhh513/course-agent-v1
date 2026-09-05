import json, urllib.request, urllib.error

B = "http://127.0.0.1:8000"

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
    return d.get("data", {}).get("token", "") if d else ""

results = []
def check(name, status, data, want_http=200, want_code=0):
    got = (data or {}).get("code") if isinstance(data, dict) else None
    ok = (status == want_http and got == want_code)
    results.append((name, ok, status, got))

def check_sec(name, status, want_http=401):
    ok = (status == want_http)
    results.append((name, ok, status, "(no envelope code)"))

s_tok = login("student", "123456")
t_tok = login("teacher", "123456")

# discover a real q_id + kp_id for deeper checks
_, qbank = req("GET", "/api/v1/question/bank?classId=CL2301", t_tok)
q_id = (qbank.get("data") or {}).get("list", [{}])[0].get("qId") if qbank else None
_, graph = req("GET", "/api/v1/graph", s_tok)
kp_id = ((graph.get("data") or {}).get("nodes", [{}])[0].get("id")) if graph else None
_, courses = req("GET", "/api/v1/course/list", s_tok) if False else (None, None)
# course list path is /api/v1/course/{course_id} only; use a fixed id
course_id = "C001"

# --- student endpoints (expect code=0) ---
check("student/dashboard", *req("GET", "/api/v1/student/dashboard", s_tok))
check("student/ability/radar", *req("GET", "/api/v1/student/ability/radar", s_tok))
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
check("course/{id}", *req("GET", f"/api/v1/course/{course_id}", s_tok))

# --- teacher endpoints (expect code=0) ---
check("teacher/classes (NEW)", *req("GET", "/api/v1/teacher/classes", t_tok))
check("teacher/dashboard", *req("GET", "/api/v1/teacher/dashboard?classId=CL2301", t_tok))
check("teacher/students", *req("GET", "/api/v1/teacher/students?classId=CL2301", t_tok))
check("teacher/heatmap", *req("GET", "/api/v1/teacher/heatmap?classId=CL2301", t_tok))
check("teacher/alerts", *req("GET", "/api/v1/teacher/alerts?classId=CL2301", t_tok))
check("teacher/messages (POST send)", *req("POST", "/api/v1/teacher/messages", t_tok, {"userId": "S20260317", "content": "回归测试消息"}))
check("question/gen/config", *req("GET", "/api/v1/question/gen/config?classId=CL2301", t_tok))
check("question/bank", *req("GET", "/api/v1/question/bank?classId=CL2301", t_tok))
check("question/gen (classCorrectRate)", *req("POST", "/api/v1/question/gen", t_tok, {"count": 1, "difficulty": 3}))
check("report/list", *req("GET", "/api/v1/report/list?classId=CL2301", t_tok))
check("analysis/errors", *req("GET", "/api/v1/analysis/errors?classId=CL2301", t_tok))
check("analysis/causes", *req("GET", "/api/v1/analysis/causes?classId=CL2301", t_tok))
check("analysis/weak-chain", *req("GET", "/api/v1/analysis/weak-chain?classId=CL2301", t_tok))
check("intervention/list", *req("GET", "/api/v1/intervention/list?classId=CL2301", t_tok))

# deeper: wrong-book detail + graph/kp if ids present
if q_id:
    check("practice/wrong-book/{q}/detail", *req("GET", f"/api/v1/practice/wrong-book/{q_id}/detail", s_tok))
if kp_id:
    check("graph/kp/{kp}", *req("GET", f"/api/v1/graph/kp/{kp_id}", s_tok))

# --- security: no token -> 401 (HTTP level) ---
check_sec("teacher/classes NO token -> 401", req("GET", "/api/v1/teacher/classes")[0])
check_sec("student/dashboard NO token -> 401", req("GET", "/api/v1/student/dashboard")[0])
check_sec("reset-password NO token -> 401", req("POST", "/api/v1/auth/reset-password", body={"username":"x","oldPassword":"y","newPassword":"z"})[0])

print(f"{'ALL PASS' if all(r[1] for r in results) else 'SOME FAIL'}  total={len(results)} passed={sum(r[1] for r in results)}")
for name, ok, status, got in results:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name} -> http={status} code={got}")
