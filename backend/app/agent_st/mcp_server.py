"""把 `registry` 里的工具挂成 MCP server（stdio），给 Claude Desktop / Cursor 等 MCP 客户端用。

**安全模型：本地进程信任 + 显式作用域**

MCP 客户端没有本系统的 JWT，所以作用域（哪个用户、哪门课、哪条任务流）**在启动参数里固化**：

    python -m app.agent_st.mcp_server --user wangjg --course CCHYJTKE
    python -m app.agent_st.mcp_server --user wangjg --course CCHYJTKE --flow generate_items

- 启动时查库校验「用户存在」**且**「是本课程成员」——与 HTTP 层 `get_current_course_id`
  的成员校验同源；校验不过直接退出并打印可读原因。
- 工具的签名里**没有** `course_id` / `user_id`（课程从服务端注入），
  所以客户端与模型都无法切换作用域。
- 不校验密码：能把这段配置写进 MCP 客户端的人，本来就能读 `backend/app/.env` 与数据库文件。
  要更严的隔离就别用本机 stdio，改走 HTTP + 一次性令牌（本阶段未做）。

**工具可见性 = 该 flow 的白名单 ∩ 该角色可用的工具**（与 `/ai` 答疑同一套过滤）。

**写工具（带 `approval`）不暴露**：MCP 客户端没有确认卡片，也没有 `/agent/actions/{id}/approve`
那个确认入口，暴露出来只会排出一条**永远批不了**的 pending。要放开就给它挂审批 UI 之后再说。

⚠️ **本模块里所有 `app.*` 都是惰性导入**：`app.config.settings` 在导入时就会固化
`DATABASE_URL`，而 `--db` 需要在导入之前生效，所以不能把 `app.*` 放在模块顶层。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, TextContent, Tool, ToolAnnotations

SERVER_NAME = "course-agent"
SUPPORTED_FLOWS = ("explain", "generate_items")


def _registry():
    """惰性导入注册表并确保工具已注册（import 即注册，逐个显式列出，不靠 tools/__init__ 副作用）。"""
    from app.agent_st.agent import registry
    from app.agent_st.agent.tools import (analytics, bank, draft, plan, rag,  # noqa: F401
                                          teacher_analytics, topic, validate, ui_actions)
    return registry


# =============================================================================
# 作用域解析（启动时一次性完成，之后不可变）
# =============================================================================
class ScopeError(RuntimeError):
    """作用域校验失败 —— 直接退出，不带任何默认值兜底。"""


def resolve_scope(user: str, course: str, flow: str) -> dict:
    """把 `--user/--course/--flow` 解析成固化的作用域；任一环节不成立就抛 ScopeError。"""
    if flow not in SUPPORTED_FLOWS:
        raise ScopeError(f"不支持的任务流 {flow!r}；可选：{', '.join(SUPPORTED_FLOWS)}")

    from app.database import SessionLocal
    from app.models.course import Course
    from app.models.user import User
    from app.models.user_course import UserCourse

    db = SessionLocal()
    try:
        # 先按 username 找，找不到再按 user_id 找 —— MCP 配置里写哪个都行
        row = db.query(User).filter((User.username == user) | (User.user_id == user)).first()
        if row is None:
            raise ScopeError(f"用户 {user!r} 不存在")
        course_row = db.query(Course).filter(Course.course_id == course).first()
        if course_row is None:
            raise ScopeError(f"课程 {course!r} 不存在")

        member = db.query(UserCourse).filter(
            UserCourse.user_id == row.user_id,
            UserCourse.course_id == course,
        ).first()
        if member is None:
            raise ScopeError(
                f"用户 {row.username}（{row.user_id}）不是课程 {course} 的成员；"
                "请先让该用户加入这门课（MCP 的作用域必须落在真实成员关系上）"
            )

        return {
            "user_id": row.user_id,
            "username": row.username,
            "name": row.name or row.username,
            "role": (row.role or "").strip(),
            "course_id": course,
            "course_name": (course_row.name or "").strip() or course,
            "flow_id": flow,
            "role_in_course": member.role_in_course or "",
        }
    finally:
        db.close()


# =============================================================================
# 工具可见性
# =============================================================================
def visible_tools(flow_id: str, role: str) -> list:
    """该 flow 内、该角色可用、且**非写操作**的工具（按名字排序，输出稳定）。"""
    registry = _registry()
    out = [
        spec for spec in registry.TOOLS.values()
        if flow_id in spec.flows
        and (not role or role in spec.roles)
        and spec.approval is None            # 写工具不暴露：MCP 侧无法完成确认
    ]
    return sorted(out, key=lambda s: s.name)


def as_mcp_tools(scope: dict) -> list[Tool]:
    return [
        Tool(
            name=spec.name,
            description=spec.description,
            inputSchema=spec.parameters,
            annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False),
        )
        for spec in visible_tools(scope["flow_id"], scope["role"])
    ]


def run_tool(scope: dict, name: str, args: dict):
    """执行一个工具：作用域全部来自启动参数，客户端只能给业务参数。"""
    allowed = {spec.name for spec in visible_tools(scope["flow_id"], scope["role"])}
    if name not in allowed:
        return None, (f"工具 {name} 在当前作用域不可用"
                      f"（用户 {scope['username']} · 角色 {scope['role']} · 流 {scope['flow_id']}）")

    from app.agent_st.agent.context import ToolContext
    from app.agent_st.agent.store import AgentStore

    store = AgentStore(user_id=scope["user_id"], course_id=scope["course_id"])
    ctx = ToolContext(
        store=store,
        flow_id=scope["flow_id"],
        extra={"courseId": scope["course_id"], "role": scope["role"]},
        user_id=scope["user_id"],
    )
    return _registry().execute(name, args or {}, ctx), None


# =============================================================================
# MCP server
# =============================================================================
def build_server(scope: dict) -> Server:
    server = Server(SERVER_NAME)
    tools = as_mcp_tools(scope)
    by_name = {t.name: t for t in tools}

    @server.list_tools()
    async def _list_tools() -> list[Tool]:
        return tools

    # ⚠️ 低层 Server 的约定（见 mcp/server/lowlevel/server.py 的 call_tool 装饰器）：
    #   - 成功要返回「内容块列表」（或 (内容块列表, 结构化 dict)），**不能直接返回 CallToolResult**，
    #     否则 SDK 会把它当可迭代对象拆成 (字段名, 值) 元组 → 20 条 pydantic 校验错误；
    #   - 失败要**抛异常**，SDK 会包成 isError=True 的 CallToolResult（异常文本原样透给客户端）。
    @server.call_tool()
    async def _call_tool(name: str, arguments: dict | None):
        if name not in by_name:
            raise ValueError(f"未知或不可用的工具：{name}")

        # registry.execute 是同步的（查库 / 向量检索）→ 丢线程池，别阻塞事件循环
        result, err = await asyncio.to_thread(run_tool, scope, name, arguments or {})
        if err:
            raise ValueError(err)
        # 工具自身用 {"error": ...} 表达失败 → 抬成 MCP 错误，别让客户端以为调用成功
        if isinstance(result, dict) and set(result) == {"error"}:
            raise ValueError(str(result["error"]))

        if isinstance(result, str):
            return [TextContent(type="text", text=result)]

        text = json.dumps(result, ensure_ascii=False, default=str)
        if isinstance(result, dict):
            try:
                json.dumps(result)          # SDK 内部用严格 dumps 生成 structuredContent
            except (TypeError, ValueError):
                return [TextContent(type="text", text=text)]
            return [TextContent(type="text", text=text)], result
        return [TextContent(type="text", text=text)]

    return server


async def serve(scope: dict) -> None:
    server = build_server(scope)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


# =============================================================================
# CLI
# =============================================================================
def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="python -m app.agent_st.mcp_server",
        description="把 course-agent 的工具挂成 MCP server（stdio）；作用域由 --user/--course/--flow 固化。",
    )
    p.add_argument("--user", required=True, help="系统里的用户名或 user_id（必须是该课程成员）")
    p.add_argument("--course", required=True, help="课程 ID，例如 CCHYJTKE")
    p.add_argument("--flow", default="explain", choices=list(SUPPORTED_FLOWS),
                   help="暴露哪条任务流的工具（默认 explain）")
    p.add_argument("--db", default="", help="可选：覆盖 DATABASE_URL（验收时指向库副本）")
    p.add_argument("--list", action="store_true", help="只打印作用域与工具清单后退出（不开 MCP 会话）")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    # 必须在任何 app.* 导入之前生效（settings 在导入时固化 DATABASE_URL）
    if args.db:
        os.environ["DATABASE_URL"] = args.db

    try:
        scope = resolve_scope(args.user, args.course, args.flow)
    except ScopeError as exc:
        print(f"[mcp] 启动失败：{exc}", file=sys.stderr)
        return 2

    tools = visible_tools(scope["flow_id"], scope["role"])
    print(f"[mcp] {SERVER_NAME} 作用域：{scope['name']}（{scope['username']}）"
          f" · 角色 {scope['role']} · 课程 {scope['course_name']}（{scope['course_id']}）"
          f" · 流 {scope['flow_id']}", file=sys.stderr)
    print(f"[mcp] 可用工具 {len(tools)} 个：{', '.join(t.name for t in tools)}", file=sys.stderr)

    if args.list:
        print(json.dumps({"scope": scope, "tools": [t.name for t in tools]},
                         ensure_ascii=False, indent=2))
        return 0

    try:
        asyncio.run(serve(scope))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
