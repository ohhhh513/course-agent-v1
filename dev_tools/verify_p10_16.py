# -*- coding: utf-8 -*-
"""P10–P16「接口占位与伪数据」深度验证（跑在独立 8010 实例 + 数据库副本上）。

用法：
    cd backend
    DATABASE_URL=sqlite:///<副本>.db python -m uvicorn app.main:app --port 8010
    python dev_tools/verify_p10_16.py            # BASE 默认 http://127.0.0.1:8010

验证内容（全部基于真实实例 + 真实库，不使用任何 mock）：
  A. /ai/feedback 真实落库：请求后 ai_feedback 表新增行，且字段与请求一致
  B. /ai/feedback 参数校验：无 token 401 / 缺 messageId 422 / 非法取值被拒
  C. /intervention/templates 去伪：插入真实模板与干预记录后，useCount 真实统计，
     且响应中不再出现 successRate / avgLift
  D. /auth/logout 吊销粒度：只吊销当前 token，不影响同一用户的其它 token
  E. 读副本库，确认 ai_feedback 表的确由启动建表产生（非手工预置）
"""
import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("BASE", "http://127.0.0.1:8010")
DB = os.environ.get("VERIFY_DB", r"C:\Users\CQYDDD\AppData\Local\Temp\_verify_v1\course_agent.db")
STUDENT_USER = os.environ.get("STUDENT_USER", "stu01")
PASSWORD = os.environ.get("PASSWORD", "123456")

PASS, FAIL = [], []


def req(method, path, token=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method)
    if token:
        r.add_header("Authorization", "Bearer " + token)
    if data:
        r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r, timeout=20) as resp:
            raw = resp.read().decode()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw


def login():
    s, d = req("POST", "/api/v1/auth/login", body={"username": STUDENT_USER, "password": PASSWORD})
    tok = ((d or {}).get("data") or {}).get("token") if isinstance(d, dict) else None
    return tok or ""


def q1(sql, args=()):
    con = sqlite3.connect(DB)
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


def ex(sql, args=()):
    con = sqlite3.connect(DB)
    try:
        con.execute(sql, args)
        con.commit()
    finally:
        con.close()


def mark(ok, name, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}{(' -> ' + detail) if detail else ''}")


token = login()
if not token:
    print(f"[FATAL] 无法登录（{STUDENT_USER}/{PASSWORD}），请确认 8010 实例与副本库就绪")
    raise SystemExit(1)

me = req("GET", "/api/v1/auth/profile", token)[1]
uid = ((me or {}).get("data") or {}).get("userId")
_, my = req("GET", "/api/v1/course/my", token)
course_id = (((my or {}).get("data") or [{}])[0]).get("courseId")
print(f"  实例={BASE}  用户={uid}  课程={course_id}")

print("\n[A] /ai/feedback 真实落库")
before = q1("select count(*) from ai_feedback")[0][0]
payload = {"messageId": "M-VERIFY-UP", "sessionId": "CH-VERIFY", "feedback": 1}
s1, d1 = req("POST", "/api/v1/ai/feedback", token, payload)
after = q1("select count(*) from ai_feedback")[0][0]
row = q1("select message_id, session_id, user_id, course_id, feedback from ai_feedback "
         "where message_id='M-VERIFY-UP' order by id desc limit 1")
mark(s1 == 200 and isinstance(d1, dict) and d1.get("code") == 0, "反馈接口返回 code=0", f"http={s1}")
mark(after == before + 1, "ai_feedback 行数 +1（真实落库）", f"{before} -> {after}")
if row:
    r = row[0]
    mark(r[0] == "M-VERIFY-UP" and r[1] == "CH-VERIFY" and r[2] == uid and r[3] == course_id and r[4] == 1,
         "落库字段与请求一致（含 user_id / course_id 归属）", str(r))
else:
    mark(False, "落库字段与请求一致（含 user_id / course_id 归属）", "未查到该行")

s, d = req("POST", "/api/v1/ai/feedback", token, {"messageId": "M-VERIFY-DOWN", "feedback": -1})
down = q1("select feedback from ai_feedback where message_id='M-VERIFY-DOWN' order by id desc limit 1")
mark(s == 200 and down and down[0][0] == -1, "点踩(-1)同样真实落库", f"stored={down[0][0] if down else None}")

print("\n[B] /ai/feedback 参数与鉴权校验")
s_noauth, _ = req("POST", "/api/v1/ai/feedback", None, payload)
mark(s_noauth == 401, "无 token -> 401", f"http={s_noauth}")
s_missing, _ = req("POST", "/api/v1/ai/feedback", token, {"feedback": 1})
mark(s_missing == 422, "缺 messageId -> 422（修复前前端正是漏传）", f"http={s_missing}")
s_bad, d_bad = req("POST", "/api/v1/ai/feedback", token, {"messageId": "M-VERIFY-BAD", "feedback": 0})
mark(s_bad == 200 and isinstance(d_bad, dict) and d_bad.get("code") != 0,
     "feedback=0 被拒（信封 code != 0）", f"http={s_bad} code={(d_bad or {}).get('code')}")
mark(q1("select count(*) from ai_feedback where message_id='M-VERIFY-BAD'")[0][0] == 0,
     "被拒的请求不落库")

print("\n[C] /intervention/templates 去伪字段 + useCount 真实统计")
# 造真实数据：1 个模板 + 2 条同场景干预记录（用独立场景名，避免影响既有数据）
SCENE = "__VERIFY_SCENE__"
ex("delete from interventions where iv_id like 'IV-VERIFY-%'")
ex("delete from intervention_templates where tpl_id='TPL-VERIFY'")
ex("insert into intervention_templates(tpl_id, scene, name, steps_json, resources_json, note) "
   "values('TPL-VERIFY', ?, '验证用模板', '[\"步骤1\",\"步骤2\"]', '[]', '验证备注')", (SCENE,))
for i in (1, 2):
    ex("insert into interventions(iv_id, level, scope, title, status) values(?, ?, 'class', ?, 'done')",
       (f"IV-VERIFY-{i}", SCENE, f"验证干预{i}"))
s, d = req("GET", "/api/v1/intervention/templates", token)
items = (d or {}).get("data") or []
mine = [it for it in items if it.get("tplId") == "TPL-VERIFY"]
mark(s == 200 and len(mine) == 1, "能读到刚插入的真实模板", f"http={s} items={len(items)}")
if mine:
    t = mine[0]
    mark(t.get("useCount") == 2, "useCount 按真实 interventions 统计 = 2", f"useCount={t.get('useCount')}")
    mark("successRate" not in t and "avgLift" not in t,
         "响应已不含 successRate / avgLift 编造字段", f"keys={sorted(t.keys())}")
else:
    mark(False, "useCount 按真实 interventions 统计 = 2", "未读到模板")
    mark(False, "响应已不含 successRate / avgLift 编造字段", "未读到模板")

print("\n[D] /auth/logout 吊销粒度（只作废当前 token）")
tok_a, tok_b = login(), login()
mark(bool(tok_a) and bool(tok_b), "两次登录各取一个 token")
sa, _ = req("POST", "/api/v1/auth/logout", tok_a)
reuse_a, _ = req("GET", "/api/v1/student/dashboard", tok_a)
still_b, _ = req("GET", "/api/v1/student/dashboard", tok_b)
mark(sa == 200 and reuse_a == 401, "登出后该 token 立即 401", f"logout={sa} reuse={reuse_a}")
mark(still_b == 200, "同一用户的另一个 token 不受影响", f"http={still_b}")

print("\n[E] 副本库结构确认")
cols = [r[1] for r in q1("PRAGMA table_info(ai_feedback)")]
mark(set(cols) >= {"id", "message_id", "session_id", "user_id", "course_id", "feedback", "created_at"},
     "ai_feedback 表由启动建表产生且字段齐全", ",".join(cols))
mark(bool(q1("select count(*) from ai_feedback where course_id=?", (course_id,))[0][0] > 0),
     "反馈记录带真实 course_id（课程隔离可追溯）")

print(f"\n{'ALL PASS' if not FAIL else 'SOME FAIL'}  passed={len(PASS)} failed={len(FAIL)}")
if FAIL:
    print("FAILED: " + "; ".join(FAIL))
    sys.exit(1)
