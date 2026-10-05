"""端到端验证：学生端学习驾驶舱 coreMetrics 口径（打真实后端 + 真实 SQLite）。

覆盖 2026-09-29 的改动：
  1. coreMetrics 不再返回 goalAchieveRate（「能力目标达成度」已移除）；
  2. masteryThreshold 下发「掌握率达标线」（=80，全站唯一真源 constants.MASTERY_THRESHOLD），
     并保留 totalKpCount / masteredKpCount / completedKpCount；
  3. /student/dashboard 仍返回真实计算值（completionRate = 已完成/总数，可复算）；
  4. /student/ability/radar 已删除 → 404。

用法：python verify_dashboard_metrics.py [username] [password]
默认账号 stu01 / 123456（本库真实学生号；regression_test.py 里的 student/123456 已不存在）。
"""
import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.getenv("CA_BASE", "http://127.0.0.1:8000")
USERNAME = sys.argv[1] if len(sys.argv) > 1 else "stu01"
PASSWORD = sys.argv[2] if len(sys.argv) > 2 else "123456"

failures = []


def req(method, path, body=None, token=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method,
                               headers={"Content-Type": "application/json"})
    if token:
        r.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ((" | " + detail) if detail else ""))
    if not cond:
        failures.append(name)


print("=" * 72)
print("1) 登录")
print("=" * 72)
st, d = req("POST", "/api/v1/auth/login", {"username": USERNAME, "password": PASSWORD})
check("POST /auth/login -> 200", st == 200, f"status={st} msg={d.get('message')}")
token = (d.get("data") or {}).get("token") or (d.get("data") or {}).get("accessToken")
check("返回 token", bool(token))
if not token:
    print("\n登录失败，终止。")
    raise SystemExit(1)

print()
print("=" * 72)
print("2) GET /student/dashboard  coreMetrics 字段与口径")
print("=" * 72)
st, d = req("GET", "/api/v1/student/dashboard", token=token)
check("GET /student/dashboard -> 200", st == 200, f"status={st}")
m = (d.get("data") or {}).get("coreMetrics") or {}
print("  coreMetrics =", json.dumps(m, ensure_ascii=False))

check("已移除 goalAchieveRate", "goalAchieveRate" not in m)
check("masteryThreshold = 80（全站唯一真源）", m.get("masteryThreshold") == 80,
      f"值={m.get('masteryThreshold')}")
for k in ("completionRate", "masteryRate", "totalKpCount", "masteredKpCount",
          "completedKpCount", "updatedAt"):
    check(f"保留字段 {k}", k in m, f"值={m.get(k)}")

total, done = m.get("totalKpCount"), m.get("completedKpCount")
if isinstance(total, int) and total > 0 and isinstance(done, int):
    expect = round(done / total * 100, 1)
    check("completionRate 可由 completed/total 复算",
          abs(expect - (m.get("completionRate") or 0)) < 0.051,
          f"completed={done} / total={total} → {expect}%，接口 {m.get('completionRate')}%")
    # 这正是此前前端写死「共 46 个」的位置：现在由接口下发真实总数
    check("totalKpCount 为真实值（≠ 旧写死 46）", total != 46,
          f"真实 totalKpCount={total}（前端环形图副标题现取该值）")

check("masteredKpCount ≤ totalKpCount",
      (m.get("masteredKpCount") or 0) <= (total or 0),
      f"{m.get('masteredKpCount')} ≤ {total}")
check("masteryRate 在 0~100",
      isinstance(m.get("masteryRate"), (int, float)) and 0 <= m["masteryRate"] <= 100,
      f"值={m.get('masteryRate')}")

print()
print("=" * 72)
print("3) GET /student/ability/radar 应已删除")
print("=" * 72)
st, d = req("GET", "/api/v1/student/ability/radar", token=token)
check("GET /student/ability/radar -> 404", st == 404, f"status={st}")

print()
print("=" * 72)
print("4) 回归抽样：其它学生端接口未受影响")
print("=" * 72)
for path in ("/api/v1/student/mastery/matrix", "/api/v1/student/growth",
             "/api/v1/student/compare", "/api/v1/study-duration".replace("/api/v1/study-duration", "/api/v1/student/study-duration")):
    st, _ = req("GET", path, token=token)
    check(f"GET {path} -> 200", st == 200, f"status={st}")

print()
print("=" * 72)
print("RESULT: " + ("ALL PASS" if not failures else f"{len(failures)} FAILED -> {failures}"))
print("=" * 72)
raise SystemExit(0 if not failures else 1)
