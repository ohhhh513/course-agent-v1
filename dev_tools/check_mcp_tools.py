"""MCP 导出端到端自检：**真实 MCP 客户端** ↔ 真实的 `mcp_server` 子进程（stdio）。

做什么
1. 把演示库复制到临时目录（绝不写真实库），用 `--db` 指给 server；
2. 用官方 mcp 客户端 `stdio_client` 真实拉起 server 子进程，走完 initialize 握手；
3. 断言工具清单 = 「该 flow 白名单 ∩ 该角色可用」且**不含写工具**；
4. 断言越权调用（学生会话里调教师工具）返回 `isError`；
5. 断言真取数：`class_overview` / `my_alerts` 的返回与库内 SQL 逐项一致；
6. 断言作用域校验：用户不存在 / 不是课程成员 / 课程不存在 → 启动失败（退出码 2 + 可读报错）。

用法（**必须用装了 mcp 的解释器**，例如本项目验收用的隔离 venv）：

    <venv>\\Scripts\\python.exe dev_tools/check_mcp_tools.py
    <venv>\\Scripts\\python.exe dev_tools/check_mcp_tools.py --python <venv>\\Scripts\\python.exe

返回值：0 = 全部通过；1 = 有失败项。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BACKEND = REPO / "backend"
sys.path.insert(0, str(BACKEND))

COURSE = "CCHYJTKE"
TEACHER = "wangjg"
STUDENT = "stu08"          # 换有预警的学生：stu01 在演示库里预警为 0，断言会退化成 0 == 0
NON_MEMBER = "admin"          # 演示库里 admin 不在 CCHYJTKE 的成员表里
WRITE_TOOL = "save_question_draft"

FAILS: list[str] = []


def check(cond: bool, label: str) -> None:
    print(("  [ok] " if cond else "  [FAIL] ") + label)
    if not cond:
        FAILS.append(label)


# =============================================================================
# 期望值：从注册表推导（与 mcp_server 的过滤规则同源，用于交叉校验）
# =============================================================================
def expected_tools(flow_id: str, role: str) -> set:
    from app.agent_st.agent import registry
    from app.agent_st.agent.tools import (analytics, bank, draft, plan, rag,  # noqa: F401
                                          teacher_analytics, topic, validate)
    return {s.name for s in registry.TOOLS.values()
            if flow_id in s.flows and role in s.roles and s.approval is None}


def teacher_only(flow_id: str) -> set:
    from app.agent_st.agent import registry
    return {s.name for s in registry.TOOLS.values()
            if flow_id in s.flows and "student" not in s.roles}


def copy_db(work: Path) -> Path:
    src = REPO / "backend" / "app" / "data" / "course_agent.db"
    if not src.exists():
        print(f"[!] 找不到演示库 {src}；本副本的 data/*.db 被 .gitignore 排除，"
              "请先从队友那里要一份放到 backend/app/data/course_agent.db")
        raise SystemExit(2)
    dst = work / "course_agent.db"
    shutil.copy2(src, dst)
    return dst


def server_params(python: str, db: Path, user: str, flow: str):
    from mcp import StdioServerParameters
    return StdioServerParameters(
        command=python,
        args=["-m", "app.agent_st.mcp_server",
              "--user", user, "--course", COURSE, "--flow", flow,
              "--db", "sqlite:///" + db.as_posix()],
        cwd=str(BACKEND),
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )


async def mcp_session(python: str, db: Path, user: str, flow: str):
    """起一个 server 子进程并完成握手，返回 (session, tools_result)。"""
    from mcp import ClientSession, stdio_client
    params = server_params(python, db, user, flow)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            return session, listed


def tool_names(listed) -> list[str]:
    return sorted(t.name for t in listed.tools)


# =============================================================================
# 主流程
# =============================================================================
async def run_checks(python: str, db: Path) -> None:
    print("1) 教师 · explain 流")
    from mcp import ClientSession, stdio_client
    async with stdio_client(server_params(python, db, TEACHER, "explain")) as (r, w):
        async with ClientSession(r, w) as sess:
            await sess.initialize()
            listed = await sess.list_tools()
            names = set(tool_names(listed))
            exp = expected_tools("explain", "teacher")
            t_only = teacher_only("explain")
            check(names == exp, f"清单 = 注册表推导（{len(names)} 个）：{sorted(names)}")
            check(t_only <= names, f"教师看得到全部教师专用工具：{sorted(t_only)}")
            check(WRITE_TOOL not in names, f"写工具 {WRITE_TOOL} **不暴露**给 MCP")
            check(all(t.annotations and t.annotations.readOnlyHint for t in listed.tools),
                  "所有工具都标了 readOnlyHint")

            print("2) 教师会话里**真取数**（与库内 SQL 交叉验证）")
            res = await sess.call_tool("class_overview", {})
            check(not res.isError, "class_overview 调用成功")
            data = json.loads(res.content[0].text)
            sql = sqlite3.connect(db)
            sql_students = sql.execute(
                "select count(*) from user_courses where course_id=? and role_in_course='student'",
                (COURSE,)).fetchone()[0]
            sql_red = sql.execute(
                "select count(*) from alerts where course_id=? and status!='ignored' and level='red'",
                (COURSE,)).fetchone()[0]
            sql_yellow = sql.execute(
                "select count(*) from alerts where course_id=? and status!='ignored' and level='yellow'",
                (COURSE,)).fetchone()[0]
            sql.close()
            check(data["studentCount"] == sql_students,
                  f"studentCount={data['studentCount']} == SQL {sql_students}")
            check(data["alerts"]["red"] == sql_red and data["alerts"]["yellow"] == sql_yellow,
                  f"预警红/黄={data['alerts']['red']}/{data['alerts']['yellow']}"
                  f" == SQL {sql_red}/{sql_yellow}")
            check(not res.structuredContent is None,
                  "带结构化输出（structuredContent）—— MCP 客户端可直接读对象")

            print("3) 教师会话读取单个学生画像（隐私边界内的合法调用）")
            prof = await sess.call_tool("student_profile", {"student_id": "2026010101"})
            check(not prof.isError and "studentId" in prof.content[0].text,
                  "教师调 student_profile 返回真实学生画像")
            bad = await sess.call_tool("student_profile", {"student_id": "2026999999"})
            check(bad.isError or "不在当前课程" in bad.content[0].text,
                  f"课程外的学生 id 被拒或明确说明：{bad.content[0].text[:52]}")

    print("4) 学生 · explain 流")
    async with stdio_client(server_params(python, db, STUDENT, "explain")) as (r, w):
        async with ClientSession(r, w) as sess:
            await sess.initialize()
            listed = await sess.list_tools()
            names = set(tool_names(listed))
            exp = expected_tools("explain", "student")
            t_only = teacher_only("explain")
            check(names == exp, f"清单 = 注册表推导（{len(names)} 个）：{sorted(names)}")
            check(not (t_only & names), f"学生**看不到**教师专用工具（{sorted(t_only)}）")
            check(WRITE_TOOL not in names, "写工具不在学生清单里")

            res = await sess.call_tool("class_alerts", {"limit": 5})
            check(res.isError, "学生硬调 class_alerts → isError（角色层拦住）")
            check("无权" in res.content[0].text or "不可用" in res.content[0].text,
                  f"拒绝原因可读：{res.content[0].text[:60]}")

            res = await sess.call_tool("my_alerts", {})
            check(not res.isError, "学生调 my_alerts 成功")
            data = json.loads(res.content[0].text)
            sql = sqlite3.connect(db)
            uid = sql.execute("select user_id from users where username=?", (STUDENT,)).fetchone()[0]
            # 口径 = 工具本身：my_alerts 取该生在该课程下的**全部**预警行（不做 status/level 过滤），
            # 与教师端 class_alerts（过滤 ignored 只留红黄）不同 —— 断言按工具真实语义写。
            n = sql.execute("select count(*) from alerts where user_id=? and course_id=?",
                            (uid, COURSE)).fetchone()[0]
            sql.close()
            check(n > 0, f"该生确实有预警（避免 0 == 0 的空断言）：{n} 条")
            check(data.get("count") == n, f"my_alerts count={data.get('count')} == SQL 该生全部预警 {n}")
            check(data.get("items") and data["items"][0].get("alertId"),
                  "items 里有真实 alertId（不是占位数据）")

    print("5) 出题流：只读工具照常，写工具仍然不出现")
    async with stdio_client(server_params(python, db, TEACHER, "generate_items")) as (r, w):
        async with ClientSession(r, w) as sess:
            await sess.initialize()
            names = set(tool_names(await sess.list_tools()))
            exp = expected_tools("generate_items", "teacher")
            check(names == exp, f"教师出题流清单 = 注册表推导（{len(names)} 个）：{sorted(names)}")
            check(WRITE_TOOL not in names,
                  f"出题流里 {WRITE_TOOL} 也不暴露（MCP 侧无法完成确认）")

    async with stdio_client(server_params(python, db, STUDENT, "generate_items")) as (r, w):
        async with ClientSession(r, w) as sess:
            await sess.initialize()
            names = set(tool_names(await sess.list_tools()))
            check(names == expected_tools("generate_items", "student"),
                  f"学生出题流只剩共享只读工具：{sorted(names)}")


def run_scope_failure_checks(python: str, db: Path) -> None:
    """作用域校验失败必须**拒绝启动**（退出码 2 + 可读中文报错），不能静默兜底。"""
    print("6) 作用域校验失败 → 拒绝启动")
    cases = [
        ("用户不存在", ["--user", "nobody"]),
        ("不是课程成员", ["--user", NON_MEMBER]),
        ("课程不存在", ["--user", STUDENT, "--course", "CNOPE"]),
    ]
    for label, extra in cases:
        cmd = [python, "-m", "app.agent_st.mcp_server",
               "--course", COURSE, "--db", "sqlite:///" + db.as_posix(), "--list", *extra]
        # --course 可能在 extra 里被覆盖，统一去掉重复项
        if "--course" in extra:
            cmd = [python, "-m", "app.agent_st.mcp_server",
                   "--db", "sqlite:///" + db.as_posix(), "--list", *extra]
        proc = subprocess.run(cmd, cwd=str(BACKEND), capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=120)
        err = (proc.stderr or "").strip().splitlines()
        msg = err[-1] if err else ""
        check(proc.returncode == 2 and "启动失败" in msg,
              f"{label} → 退出码 {proc.returncode}：{msg[:76]}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--python", default=sys.executable,
                    help="用哪个解释器拉起 server 子进程（需装了 mcp；默认当前解释器）")
    args = ap.parse_args()

    try:
        import mcp  # noqa: F401
    except ImportError:
        print("[!] 当前解释器没有 mcp —— 本脚本要用装了 mcp 的解释器运行")
        print("    例：<venv>\\Scripts\\python.exe dev_tools/check_mcp_tools.py")
        return 2

    work = Path(tempfile.mkdtemp(prefix="mcp-check-"))
    db = copy_db(work)
    print(f"[i] 库副本：{db}\n")
    try:
        asyncio.run(run_checks(args.python, db))
        run_scope_failure_checks(args.python, db)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    print()
    if FAILS:
        print(f"结果：{len(FAILS)} 项失败")
        for f in FAILS:
            print("  -", f)
        return 1
    print("结果：全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
