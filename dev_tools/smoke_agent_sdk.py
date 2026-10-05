"""Agent 对话冒烟测试：同一句话分别跑 legacy / sdk 两条运行层，打印事件流对照。

用法（用 backend/.venv 的解释器跑，它装了 openai + openai-agents）：

    # 默认在数据库副本上跑，不会写真实库
    python dev_tools/smoke_agent_sdk.py --runtime sdk   --user stu07 --question "我现在有哪些预警？"
    python dev_tools/smoke_agent_sdk.py --runtime legacy --user stu07 --question "我现在有哪些预警？"

    # 想直接跑当前库，加 --db backend/app/data/course_agent.db

它会打印：事件序列（session/text/tool_start/tool_end/citations/done）、
工具调用明细、最终回答文本，用来确认两条路径行为一致。
"""
from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BACKEND = REPO / "backend"
DEFAULT_DB = BACKEND / "app" / "data" / "course_agent.db"


def parse_args():
    ap = argparse.ArgumentParser(description="Agent 对话冒烟测试")
    ap.add_argument("--runtime", choices=["legacy", "sdk"], default="sdk")
    ap.add_argument("--user", default="stu07", help="学生用户名（演示库：stu01-stu10）")
    ap.add_argument("--course", default="", help="课程 id，留空取该用户第一门课")
    ap.add_argument("--flow", default="explain", help="explain / generate_items")
    ap.add_argument("--question", default="我现在有哪些预警？分别是什么知识点？")
    ap.add_argument("--db", default="", help="指定数据库；留空则在副本上跑")
    return ap.parse_args()


def prepare_db(args) -> str:
    """默认复制一份库到临时目录再跑，避免冒烟测试污染真实数据。"""
    if args.db:
        return str(Path(args.db).resolve())
    if not DEFAULT_DB.exists():
        raise SystemExit(f"找不到数据库：{DEFAULT_DB}")
    work = tempfile.mkdtemp(prefix="agent-smoke-")
    copy = Path(work) / "course_agent.db"
    shutil.copy2(DEFAULT_DB, copy)
    return str(copy)


def main():
    args = parse_args()
    db_path = prepare_db(args)
    os.environ["DATABASE_URL"] = "sqlite:///" + db_path.replace("\\", "/")
    os.environ["AGENT_RUNTIME"] = args.runtime          # 必须在 import app.* 之前
    sys.path.insert(0, str(BACKEND))

    from app.database import SessionLocal                    # noqa: E402
    from app.models.user import User                         # noqa: E402
    from app.models.user_course import UserCourse            # noqa: E402
    from app.agent_st.agent import runtime, sdk_runner       # noqa: E402

    db = SessionLocal()
    user = db.query(User).filter(User.username == args.user).first()
    if not user:
        raise SystemExit(f"演示库里没有用户 {args.user}")
    course_id = args.course or (
        db.query(UserCourse.course_id)
        .filter(UserCourse.user_id == user.user_id)
        .order_by(UserCourse.id)
        .first() or [""]
    )[0]

    print(f"运行层      : {args.runtime}"
          f"（sdk 可用={sdk_runner.available()}，未装 openai-agents 或没配 key 时自动回退 legacy）")
    print(f"数据库      : {db_path}")
    print(f"用户/课程   : {user.name}({user.user_id}) / {course_id}")
    print(f"问题        : {args.question}")
    print("-" * 72)

    text_parts, tools, citations, done = [], [], [], None
    for ev in runtime.run_turn(
        message=args.question, flow_id=args.flow, context={}, store=None,
        user_id=user.user_id, course_id=course_id,
    ):
        kind = ev.get("type")
        if kind == "text":
            text_parts.append(ev.get("delta") or "")
        elif kind == "tool_start":
            tools.append(("start", ev.get("name"), ev.get("args")))
        elif kind == "tool_end":
            tools.append(("end", ev.get("name"), None))
        elif kind == "citations":
            citations = ev.get("items") or []
        elif kind == "done":
            done = ev
        elif kind == "error":
            print(f"[error] {ev.get('message')}")
        print(f"  event: {kind}" + (f"  {ev.get('name') or ''}" if kind.startswith("tool") else ""))

    print("-" * 72)
    print(f"工具调用    : {tools}")
    print(f"引用条数    : {len(citations)}")
    print(f"done        : {done}")
    print(f"回答文本    : {((''.join(text_parts)) or '')[:400]}")
    db.close()


if __name__ == "__main__":
    main()
