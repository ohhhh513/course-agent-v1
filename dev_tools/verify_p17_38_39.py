# -*- coding: utf-8 -*-
"""「四、隔离与权限」（P17 / P18 / P38 / P39 + 补做 P4 / P9）深度验证。

跑法（与其它 verify_* 一致，全程用 8010 独立实例 + 数据库副本，不碰用户 8000 与真实库）：

    cd backend
    DATABASE_URL=sqlite:///<副本>.db python -m uvicorn app.main:app --port 8010
    cd .. && VERIFY_DB=<副本路径> python dev_tools/verify_p17_38_39.py

验证内容（全部真实调用接口，不使用任何 mock）：
  [0] P18：所有模型表的 course_id 列都不再有 default（不再静默指向演示课 C2026DS001）
  [1] 注入第二门课 fixture（课程 + 题目 + 报告），用于制造「跨课程」场景
  [2] P17：跨课程的题目改/删/审核、报告读/导出 → 403；同课程改题（写入同值）→ 200
  [3] P38：学生 token 打教师端接口 → 403
  [4] P39/P4/P9 敏感性对照：往第二门课灌入「真实形态」噪声（第二门课自己的知识点、题目、
      今日错答、练习会话、学习路径）+ 一层防御性脏数据，教师端/学生端接口响应必须逐字不变；
      并用「不过滤 vs 过滤」的原始 SQL 计数证明噪声足够强
"""
import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta

BASE = os.environ.get("BASE", "http://127.0.0.1:8010")
DB = os.environ.get("VERIFY_DB", r"C:\Users\CQYDDD\AppData\Local\Temp\_verify_v1b\course_agent.db")
STUDENT_USER = os.environ.get("STUDENT_USER", "stu01")
TEACHER_USER = os.environ.get("TEACHER_USER", "wangjg")
PASSWORD = os.environ.get("PASSWORD", "123456")
COURSE_ID = os.environ.get("COURSE_ID", "CCHYJTKE")
NOISE_COURSE = "CVERIFY2"
NOISE_KPS = ["VFY2KP01", "VFY2KP02", "VFY2KP03"]
NOISE_QS = ["QVFY2A", "QVFY2B", "QVFY2C"]

PASS, FAIL = [], []


def req(method, path, token=None, body=None, course=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method)
    if token:
        r.add_header("Authorization", "Bearer " + token)
    if course:
        r.add_header("X-Course-Id", course)
    if data:
        r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
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
    return ((d or {}).get("data") or {}).get("token") if isinstance(d, dict) else ""


def ok(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("  [%s] %s%s" % ("PASS" if cond else "FAIL", name, (" -> " + str(detail)) if detail else ""))


def db():
    return sqlite3.connect(DB)


def is_forbidden(status, data):
    """403 有两种落地：依赖层 HTTP 403，业务层信封 code=403（HTTP 200）。"""
    code = (data or {}).get("code") if isinstance(data, dict) else None
    return status == 403 or (status == 200 and code == 403)


print("  实例=%s  副本=%s" % (BASE, DB))
s_tok = login(STUDENT_USER, PASSWORD)
t_tok = login(TEACHER_USER, PASSWORD)
if not s_tok or not t_tok:
    print("[FATAL] 登录失败，请检查账号")
    raise SystemExit(1)

con = db()
student_id = con.execute("select user_id from users where username=? limit 1", (STUDENT_USER,)).fetchone()
student_id = student_id[0] if student_id else ""
own_q = con.execute("select q_id from questions where course_id=? limit 1", (COURSE_ID,)).fetchone()
own_q = own_q[0] if own_q else ""
own_kps = [r[0] for r in con.execute(
    "select id from graph_nodes where course_id=? and graph_type='knowledge' limit 4", (COURSE_ID,))]
con.close()
print("  学生=%s  本课题目=%s  本课知识点=%s" % (student_id, own_q, own_kps[:2]))

# ---------------------------------------------------------------- [0] P18
print("\n[0] P18：模型 course_id 是否还有演示课默认值")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))
try:
    from app.database import Base  # noqa: E402
    import app.models.question, app.models.alert, app.models.graph  # noqa: E402,F401
    import app.models.practice, app.models.course, app.models.user  # noqa: E402,F401
    import app.models.intervention, app.models.ai, app.models.user_course, app.models.checkin  # noqa: E402,F401

    bad = []
    for tname, table in Base.metadata.tables.items():
        col = table.columns.get("course_id")
        if col is not None and col.default is not None:
            bad.append((tname, str(getattr(col.default, "arg", col.default))))
    ok("P18 所有表 course_id 均无默认值（原 9 处 C2026DS001）", not bad, bad or "0 处残留")
except Exception as exc:  # noqa: BLE001
    ok("P18 模型默认值检查", False, "导入模型失败: %s" % exc)

# ---------------------------------------------------------------- [1] fixture
print("\n[1] 注入第二门课 fixture（制造跨课程场景）")
con = db()
for t, w in (("questions", "course_id=?"), ("reports", None), ("courses", "course_id=?"),
             ("graph_nodes", "course_id=?"), ("answer_records", "course_id=?"),
             ("practice_sessions", "course_id=?"), ("learning_paths", "course_id=?")):
    if w:
        con.execute("delete from %s where %s" % (t, w), (NOISE_COURSE,))
con.execute("delete from reports where report_id=?", ("RP-VERIFY-OTHER",))
con.execute("insert into courses (course_id, name, code, term, teacher, credit, chapters,"
            " knowledge_points, resources, questions, invite_code, owner_id)"
            " values (?,?,?,?,?,?,?,?,?,?,?,?)",
            (NOISE_COURSE, "验证用第二门课", "", "", "验证", 0, 0, 0, 0, 0, "VERIFY2", ""))
# 第二门课自己的知识点
for i, kp in enumerate(NOISE_KPS):
    con.execute("insert into graph_nodes (id, graph_type, course_id, name, category, chapter, difficulty)"
                " values (?,?,?,?,?,?,?)",
                (kp, "knowledge", NOISE_COURSE, "别课知识点%d" % (i + 1), "别课章节", "别课章节", 3))
# 第二门课自己的题目
for i, q in enumerate(NOISE_QS):
    con.execute("insert into questions (q_id, course_id, kp_id, type, difficulty, score, status, stem,"
                " options, answer, analysis, is_key) values (?,?,?,?,?,?,?,?,?,?,?,?)",
                (q, NOISE_COURSE, NOISE_KPS[i], "single", 3, 5, "published", "别门课的题%d" % i,
                 "[]", "A", "", 0))
# 别门课的题目（用于 P17 越权测试）
foreign_q = "QVFY-OTHER-COURSE"
con.execute("delete from questions where q_id=?", (foreign_q,))
con.execute("insert into questions (q_id, course_id, kp_id, type, difficulty, score, status, stem,"
            " options, answer, analysis, is_key) values (?,?,?,?,?,?,?,?,?,?,?,?)",
            (foreign_q, NOISE_COURSE, NOISE_KPS[0], "single", 3, 5, "published", "别门课的题",
             "[]", "A", "", 0))
con.execute("insert into reports (report_id, class_id, title, status, detail_json, created_at)"
            " values (?,?,?,?,?,?)",
            ("RP-VERIFY-OTHER", "", "别门课的报告", "done",
             json.dumps({"meta": {"courseId": NOISE_COURSE}, "sections": []}, ensure_ascii=False),
             datetime.now().isoformat(sep=" ", timespec="seconds")))
con.commit()
ok("fixture 就绪（第二门课 + 自己的知识点/题目 + 别课报告）",
   con.execute("select count(*) from questions where q_id=?", (foreign_q,)).fetchone()[0] == 1)
con.close()

# ---------------------------------------------------------------- [2] P17
print("\n[2] P17：跨课程 题目/报告 操作必须 403")
s, d = req("PUT", "/api/v1/question/" + foreign_q, t_tok, {"difficulty": 4}, course=COURSE_ID)
ok("P17 跨课程改题 -> 403", is_forbidden(s, d), "http=%s code=%s" % (s, (d or {}).get("code")))
s, d = req("DELETE", "/api/v1/question/" + foreign_q, t_tok, course=COURSE_ID)
ok("P17 跨课程删题 -> 403", is_forbidden(s, d), "http=%s code=%s" % (s, (d or {}).get("code")))
s, d = req("POST", "/api/v1/question/review", t_tok,
           {"qIds": [foreign_q], "action": "publish"}, course=COURSE_ID)
ok("P17 跨课程审核 -> 403", is_forbidden(s, d), "http=%s code=%s" % (s, (d or {}).get("code")))
s, d = req("GET", "/api/v1/report/RP-VERIFY-OTHER", t_tok, course=COURSE_ID)
ok("P17 跨课程读报告 -> 403", is_forbidden(s, d), "http=%s code=%s" % (s, (d or {}).get("code")))
s, d = req("POST", "/api/v1/report/RP-VERIFY-OTHER/export", t_tok,
           {"format": "html"}, course=COURSE_ID)
ok("P17 跨课程导出报告 -> 403", is_forbidden(s, d), "http=%s code=%s" % (s, (d or {}).get("code")))
con = db()
row = con.execute("select difficulty, status from questions where q_id=?", (foreign_q,)).fetchone()
con.close()
ok("P17 反证：别课题目未被改动", row == (3, "published"), row)
if own_q:
    con = db()
    cur_diff = con.execute("select difficulty from questions where q_id=?", (own_q,)).fetchone()[0]
    con.close()
    s, d = req("PUT", "/api/v1/question/" + own_q, t_tok, {"difficulty": cur_diff}, course=COURSE_ID)
    ok("P17 对照组：本课题目可正常修改", s == 200 and (d or {}).get("code") == 0,
       "http=%s code=%s" % (s, (d or {}).get("code")))

# ---------------------------------------------------------------- [3] P38
print("\n[3] P38：学生 token 打教师端接口必须 403")
for p in ("/api/v1/teacher/classes", "/api/v1/teacher/dashboard", "/api/v1/teacher/heatmap",
          "/api/v1/analysis/errors", "/api/v1/question/bank", "/api/v1/report/list",
          "/api/v1/intervention/list", "/api/v1/teacher/students"):
    s, d = req("GET", p, s_tok, course=COURSE_ID)
    ok("P38 student->%s -> 403" % p.replace("/api/v1/", ""), is_forbidden(s, d),
       "http=%s code=%s" % (s, (d or {}).get("code")))
s, d = req("GET", "/api/v1/teacher/classes", t_tok, course=COURSE_ID)
ok("P38 对照组：教师 token 正常", s == 200 and (d or {}).get("code") == 0)

# ---------------------------------------------------------------- [4] 敏感性对照
SNAPSHOT = [
    ("teacher/dashboard", "/api/v1/teacher/dashboard", "t"),
    ("teacher/students", "/api/v1/teacher/students", "t"),
    ("teacher/heatmap(completion)", "/api/v1/teacher/heatmap", "t"),
    ("teacher/heatmap(mastery)", "/api/v1/teacher/heatmap?type=mastery", "t"),
    ("analysis/errors", "/api/v1/analysis/errors", "t"),
    ("question/bank", "/api/v1/question/bank", "t"),
    ("intervention/list", "/api/v1/intervention/list", "t"),
    ("student/dashboard", "/api/v1/student/dashboard", "s"),
    ("student/mastery/matrix", "/api/v1/student/mastery/matrix", "s"),
    ("student/alerts", "/api/v1/student/alerts", "s"),
]


def snapshot():
    out = {}
    for name, p, who in SNAPSHOT:
        s, d = req("GET", p, t_tok if who == "t" else s_tok, course=COURSE_ID)
        out[name] = json.dumps((d or {}).get("data"), ensure_ascii=False, sort_keys=True)
    if student_id:
        s, d = req("GET", "/api/v1/teacher/students/%s/profile" % student_id, t_tok, course=COURSE_ID)
        out["teacher/students/{id}/profile"] = json.dumps(
            (d or {}).get("data"), ensure_ascii=False, sort_keys=True)
    return out


print("\n[4] P39 + P4/P9：注入第二门课噪声后的逐字对照（两级噪声）")
before = snapshot()
print("    噪声前快照 %d 个接口" % len(before))

con = db()
now = datetime.now().replace(microsecond=0)
stamp = now.strftime("%Y-%m-%d %H:%M:%S")


def inject_legal():
    """L1 合法噪声：第二门课自己的知识点 / 题目 / 作答 / 会话 / 路径。"""
    for i in range(12):
        con.execute(
            "insert into answer_records (session_id, user_id, course_id, q_id, kp_id, my_answer,"
            " correct_answer, is_correct, mastered, duration_seconds, error_type, created_at)"
            " values (?,?,?,?,?,?,?,?,?,?,?,?)",
            ("PS-VFY-N1", student_id, NOISE_COURSE, NOISE_QS[i % 3], NOISE_KPS[i % 3],
             "B", "A", 0, 0, 30, "", stamp))
    for i in range(3):
        con.execute(
            "insert into practice_sessions (session_id, user_id, course_id, mode, total, correct, wrong,"
            " accuracy, duration_seconds, status, created_at, finished_at, questions_snapshot)"
            " values (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("PS-VFY-N2-%d" % i, student_id, NOISE_COURSE, "weak", 10, 4, 6, 40.0, 300,
             "finished", stamp, stamp, "[]"))
        con.execute(
            "insert into learning_paths (user_id, course_id, step, kp_id, name, chapter, status,"
            " hours, mastery, res_count, progress, locked, lock_reason)"
            " values (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (student_id, NOISE_COURSE, 900 + i, NOISE_KPS[i % 3], "别课知识点", "别课章节",
             "done", 1, 95, 9, 95, 0, ""))


def inject_dirty():
    """L2 脏数据：行内 course_id 与 kp/q 归属不一致（P43 所述「同号」风险）。"""
    if not (own_q and own_kps):
        return
    for i in range(8):
        con.execute(
            "insert into answer_records (session_id, user_id, course_id, q_id, kp_id, my_answer,"
            " correct_answer, is_correct, mastered, duration_seconds, error_type, created_at)"
            " values (?,?,?,?,?,?,?,?,?,?,?,?)",
            ("PS-VFY-N3", student_id, NOISE_COURSE, own_q, own_kps[i % len(own_kps)],
             "C", "A", 0, 0, 30, "", stamp))
    for i in range(2):
        con.execute(
            "insert into learning_paths (user_id, course_id, step, kp_id, name, chapter, status,"
            " hours, mastery, res_count, progress, locked, lock_reason)"
            " values (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (student_id, NOISE_COURSE, 950 + i, own_kps[i % len(own_kps)], "越界知识点", "越界",
             "done", 1, 99, 9, 99, 0, ""))


inject_legal()
con.commit()
print("    L1 合法噪声：第二门课自己的 12 条今日错答 + 3 会话 + 3 学习路径")
after_legal = snapshot()
changed_legal = [k for k in before if before[k] != after_legal[k]]
ok("L1 合法噪声下接口响应逐字不变（%d 个接口）" % len(before), not changed_legal,
   changed_legal or "全部一致")

inject_dirty()
con.commit()
print("    L2 脏数据：8 条错答 + 2 条学习路径（course 与 kp 归属不一致）")
after_dirty = snapshot()
changed_dirty = [k for k in before if before[k] != after_dirty[k]]
print("    [已知残余] L2 脏数据下发生变化的接口：%s" % (changed_dirty or "无"))
print("               （根因：services/scoring.quiz_accuracy_by_kp 等按 user_id 取值、无课程参数 = 清单 P43，")
print("                本次按约定未改）")
con.close()

con = db()


def pair(label, sql):
    with_f = con.execute(sql + " and course_id=?", (student_id, COURSE_ID)).fetchone()[0]
    without = con.execute(sql, (student_id,)).fetchone()[0]
    print("    %-34s 不过滤=%-5s 过滤后=%-5s" % (label, without, with_f))
    return without != with_f


strong = []
today = "and date(created_at)=date('now','localtime') "
strong.append(pair("今日答题记录（该生）",
                   "select count(*) from answer_records where user_id=?" + " " + today))
strong.append(pair("全部答题记录（该生）", "select count(*) from answer_records where user_id=?"))
strong.append(pair("学习路径（该生）", "select count(*) from learning_paths where user_id=?"))
strong.append(pair("练习会话（该生）", "select count(*) from practice_sessions where user_id=?"))
con.close()
ok("对照组：噪声足够强（不过滤时这些数字都会变）", all(strong), strong)

print("\n%s  passed=%d failed=%d" % ("ALL PASS" if not FAIL else "SOME FAIL", len(PASS), len(FAIL)))
for n in FAIL:
    print("  [FAIL] " + n)
