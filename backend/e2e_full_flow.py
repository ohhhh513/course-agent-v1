"""
全链路真实流程 E2E v2 —— 零注入版。

规则（用户约定）：除创建两个账号（系统暂无注册接口，直接写 users 表）外，
一切业务数据**只通过真实后端 API 产生**；资源与题目从本地真实数据中选取。

链路：T300001 建课 → 建章/建KP/设前置 → 上传真实资源(挂KP) → 从真实题库选题导入
  → S300001 凭码入课 → 切课看资源 → 做练习(判分/报告) → AI 答疑
  → 三重隔离验证（账号间/课程间/未加入 403）。
测试数据**保留不清理**（真实流程产物）。

执行: cd backend && python e2e_full_flow.py [端口默认8010]
"""
import json
import sqlite3
import sys
import urllib.request
import urllib.error
from pathlib import Path

B = f"http://127.0.0.1:{sys.argv[1] if len(sys.argv) > 1 else '8010'}"
BACKEND = Path(__file__).resolve().parent
DB = BACKEND / "app" / "data" / "course_agent.db"
sys.path.insert(0, str(BACKEND))

# 本机回环请求不走系统代理
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

results = []


def ok(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(f"  {'✅' if cond else '❌'} {name}" + (f"  [{detail}]" if detail else ""))


def req(method, path, token=None, body=None, headers=None, raw_body=None, content_type=None):
    url = B + path
    data = raw_body if raw_body is not None else (json.dumps(body).encode() if body is not None else None)
    r = urllib.request.Request(url, data=data, method=method)
    if token:
        r.add_header("Authorization", "Bearer " + token)
    if data is not None and not content_type and raw_body is None:
        content_type = "application/json"
    if data is not None and content_type:
        r.add_header("Content-Type", content_type)
    for k, v in (headers or {}).items():
        r.add_header(k, v)
    try:
        with _opener.open(r, timeout=90) as resp:
            return resp.status, json.loads(resp.read().decode() or "null")
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw


def login(u, p):
    s, d = req("POST", "/api/v1/auth/login", body={"username": u, "password": p})
    return (d.get("data") or {}).get("token", "")


def ensure_account(user_id, username, role):
    """系统暂无注册接口 —— 管理员开账号（本次唯一允许的库写入）"""
    con = sqlite3.connect(str(DB))
    if con.execute("SELECT 1 FROM users WHERE user_id=?", (user_id,)).fetchone():
        con.close()
        return "existed"
    from app.middleware.auth import hash_password
    con.execute(
        "INSERT INTO users (user_id, username, password, name, role, avatar_char) VALUES (?,?,?,?,?,?)",
        (user_id, username, hash_password("123456"),
         "王测试" if role == "teacher" else "李测试", role, "王" if role == "teacher" else "李"),
    )
    con.commit()
    con.close()
    return "created"


def pick_real_assets():
    """从本地真实资源中选取 2 个测试文件（一个视频 + 一个文档）"""
    root = BACKEND.parent / "resources" / "C2026DS001"

    def pick(exts, limit):
        fs = [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in exts
              and p.stat().st_size < limit]
        return sorted(fs, key=lambda p: p.stat().st_size)[:1]

    picked = pick((".mp4",), 20 * 1024 * 1024) + pick((".pdf", ".pptx", ".md", ".txt"), 2 * 1024 * 1024)
    return picked[:2]


def pick_real_questions(n=2):
    """从当前真实题库中读取 n 题用于导入新课程（只读）"""
    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute(
        "SELECT type, difficulty, score, stem, options, answer, analysis, kp_path "
        "FROM questions WHERE status='published' AND type='single' AND kp_id<>'' "
        "ORDER BY q_id LIMIT ?", (n,))]
    con.close()
    out = []
    for r in rows:
        r["options"] = json.loads(r["options"]) if r["options"] else []
        r["kp_path"] = json.loads(r["kp_path"]) if r["kp_path"] else []
        out.append(r)
    return out


def multipart_upload(token, course_id, file_path, title, kp_id, kp_name):
    boundary = "----E2EBoundaryReal"
    data = file_path.read_bytes()
    parts = [
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{file_path.name}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode(),
        data,
        f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="title"\r\n\r\n{title}\r\n'.encode(),
        f'--{boundary}\r\nContent-Disposition: form-data; name="kp"\r\n\r\n{kp_name}\r\n'.encode(),
        f'--{boundary}\r\nContent-Disposition: form-data; name="kp_id"\r\n\r\n{kp_id}\r\n'.encode(),
        f'--{boundary}\r\nContent-Disposition: form-data; name="category"\r\n\r\nknowledge\r\n'.encode(),
        f'--{boundary}--\r\n'.encode(),
    ]
    return req("POST", "/api/v1/teacher/resources/upload", token,
               raw_body=b"".join(parts),
               content_type=f"multipart/form-data; boundary={boundary}",
               headers={"X-Course-Id": course_id})


def main():
    print("== 0. 创建账号（唯一允许的库操作） ==")
    r1 = ensure_account("T300001", "t_real_flow", "teacher")
    r2 = ensure_account("S300001", "s_real_flow", "student")
    ok("教师/学生账号就绪", True, f"T300001:{r1} / S300001:{r2}")

    tt = login("t_real_flow", "123456")
    st = login("s_real_flow", "123456")
    ok("两账号登录真实后端", bool(tt) and bool(st))

    print("== A. 教师建课 ==")
    s, d = req("POST", "/api/v1/teacher/courses", tt, {"name": "真实流程演示课", "term": "2026 秋季"})
    cid = (d.get("data") or {}).get("courseId", "")
    inv = (d.get("data") or {}).get("inviteCode", "")
    ok("教师建课（空课）", s == 200 and bool(cid and inv), f"课程={cid} 邀请码={inv}")

    print("== B. 搭建课程结构 ==")
    s, d = req("POST", "/api/v1/teacher/structure/chapters", tt,
               {"name": "第1章 绪论与基础"}, headers={"X-Course-Id": cid})
    ch = (d.get("data") or {}).get("id", "")
    ok("新建章节", s == 200 and bool(ch), ch)
    kp_ids = {}
    for nm in ("什么是数据结构", "算法与复杂度"):
        s, d = req("POST", "/api/v1/teacher/structure/kps", tt,
                   {"name": nm, "chapterId": ch, "hours": 2}, headers={"X-Course-Id": cid})
        kp_ids[nm] = (d.get("data") or {}).get("id", "")
    ok("新建知识点×2", all(kp_ids.values()), str(kp_ids))
    s, d = req("PUT", f"/api/v1/teacher/structure/kps/{kp_ids['算法与复杂度']}/relations", tt,
               {"preKpIds": [kp_ids["什么是数据结构"]]}, headers={"X-Course-Id": cid})
    ok("图谱手动编辑：设置前置关系", s == 200)

    print("== C. 上传真实资源（从本地真实数据选取） ==")
    assets = pick_real_assets()
    ok("本地真实文件选取×2", len(assets) == 2, "、".join(p.name for p in assets))
    uploaded = []
    for i, f in enumerate(assets):
        kp_id = kp_ids["什么是数据结构"] if i == 0 else kp_ids["算法与复杂度"]
        kp_name = "什么是数据结构" if i == 0 else "算法与复杂度"
        s, d = multipart_upload(tt, cid, f, f"真实资源·{f.name}", kp_id, kp_name)
        rid = ((d.get("data") or {}).get("resId") or "")
        uploaded.append(rid)
        on_disk = (BACKEND.parent / "resources" / cid / rid).exists()
        ok(f"上传资源{i + 1}（落盘按课程隔离）", s == 200 and bool(rid) and on_disk,
           f"{rid} → resources/{cid}/{rid}/")

    print("== D. 从真实题库选题导入新课程 ==")
    real_qs = pick_real_questions(2)
    ok("从当前真实题库选取题目×2", len(real_qs) == 2)
    for i, q in enumerate(real_qs):
        q["kp_id"] = kp_ids["什么是数据结构"] if i == 0 else kp_ids["算法与复杂度"]
        q["status"] = "published"
    s, d = req("POST", "/api/v1/question/import", tt, {"questions": real_qs}, headers={"X-Course-Id": cid})
    ok("题目通过导入接口进入新课（API，非注入）", s == 200)
    s, d = req("GET", "/api/v1/question/bank", tt, headers={"X-Course-Id": cid})
    ok("新课题库=2（课程间隔离）", (d.get("data") or {}).get("total") == 2)

    print("== E. 学生入课与全功能 ==")
    s, d = req("POST", "/api/v1/course/join", st, {"inviteCode": inv})
    ok("学生凭邀请码入课", s == 200)
    s, d = req("GET", "/api/v1/student/resources", st, headers={"X-Course-Id": cid})
    ok("学生看新课资源=2", (d.get("data") or {}).get("total") == 2)
    s, d = req("GET", "/api/v1/graph", st, headers={"X-Course-Id": cid})
    dd = d.get("data")
    g_nodes = dd.get("nodes") if isinstance(dd, dict) else None
    ok("学生端图谱含新建知识点", bool(g_nodes) and len(g_nodes) >= 2, f"节点数={len(g_nodes) if g_nodes else 0}")

    print("== F. 学生练习（真实判分链路） ==")
    s, d = req("POST", "/api/v1/practice/sessions", st,
               {"mode": "order", "kpIds": [kp_ids["什么是数据结构"], kp_ids["算法与复杂度"]], "count": 5},
               headers={"X-Course-Id": cid})
    sid = (d.get("data") or {}).get("sessionId", "")
    ok("创建练习会话", s == 200 and bool(sid), sid)
    s, d = req("GET", f"/api/v1/practice/sessions/{sid}/questions", st, headers={"X-Course-Id": cid})
    dd = d.get("data")
    q_list = dd if isinstance(dd, list) else ((dd or {}).get("list") or [])
    ok("练习出题（新课题目）", s == 200 and len(q_list) >= 1, f"{len(q_list)} 题")
    if q_list:
        q0 = q_list[0]
        qid0 = q0.get("qId") or q0.get("id")
        ans0 = q0.get("answer") or ""
        s, d = req("POST", "/api/v1/practice/answers", st,
                   {"sessionId": sid, "qId": qid0, "answer": ans0 or "A", "durationSeconds": 45},
                   headers={"X-Course-Id": cid})
        ok("提交作答（即时判分）", s == 200, f"答对={(d.get('data') or {}).get('correct')}")
        s, d = req("POST", f"/api/v1/practice/sessions/{sid}/finish", st, headers={"X-Course-Id": cid})
        ok("结束练习出报告", s == 200)
        s, d = req("GET", "/api/v1/student/dashboard", st, headers={"X-Course-Id": cid})
        ov = ((d.get("data") or {}).get("overview") or {})
        ok("学情联动（进度/当前节点）", d.get("code") == 0,
           f"进度={ov.get('courseProgress')}% 节点={ov.get('currentNode')}")

    print("== G. AI 答疑（真实 LLM 链路） ==")
    s, d = req("POST", "/api/v1/ai/chat", st,
               {"question": "用一句话说明什么是算法的时间复杂度？", "courseId": cid},
               headers={"X-Course-Id": cid})
    content = ""
    if isinstance(d, dict):
        data = d.get("data") or {}
        content = data.get("content") or data.get("answer") or ""
        if not content and isinstance(data.get("messages"), list) and data["messages"]:
            content = data["messages"][-1].get("content", "")
    ok("AI 答疑返回真实内容", s == 200 and bool(content),
       f"http={s} resp={json.dumps(d, ensure_ascii=False)[:300] if isinstance(d, (dict, list)) else d}")

    print("== H. 三重隔离验证 ==")
    st1, _ = req("GET", "/api/v1/teacher/resources", tt)
    ok("新教师访问默认课 → 403（未加入）", st1 == 403)
    st2, _ = req("GET", "/api/v1/teacher/resources", login("teacher", "123456"),
                 headers={"X-Course-Id": cid})
    ok("种子教师访问新课 → 403（账号间隔离）", st2 == 403)
    st3, _ = req("GET", "/api/v1/student/resources", login("student", "123456"),
                 headers={"X-Course-Id": cid})
    ok("种子学生访问新课 → 403（未加入）", st3 == 403)

    failed = [n for n, c in results if not c]
    print(f"\n==== 真实流程 E2E：{len(results) - len(failed)}/{len(results)} 通过 ====")
    print(f"保留产物：课程 {cid}（2 资源 / 2 题 / 2 KP / 1 学生）——真实流程产生的数据")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
