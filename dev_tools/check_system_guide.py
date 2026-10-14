"""系统操作目录与三端导航自检：仅静态文件和内存，不访问真实数据库。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))

from app.agent_st.agent.context import ToolContext
from app.agent_st.agent.registry import TOOLS, execute, openai_tools
from app.agent_st.agent.loader import build_system_prompt, load_flow, load_persona
from app.agent_st.agent.system_guide import allowed_views, catalogue, features_for_role, lookup_guide
from app.agent_st.agent.tools import analytics  # noqa: F401


def main() -> int:
    failures = []
    def check(ok, label):
        if not ok:
            failures.append(label)
            print("[FAIL]", label)

    count = 0
    for role in ("student", "teacher", "admin"):
        records = features_for_role(role)
        count += len(records)
        html = (REPO / f"{role}.html").read_text(encoding="utf-8")
        nav = set(re.findall(r'data-view="([^"]+)"', html))
        check(set(allowed_views(role)) == nav, f"{role} 页面目录与实际侧栏一致")
        chat_file = {"student": "chat.js", "teacher": "chat.js", "admin": "assistant.js"}[role]
        chat = (REPO / f"assets/js/{role}/views/{chat_file}").read_text(encoding="utf-8")
        views_match = re.search(r"const VIEWS = \[(.*?)\]", chat, re.S)
        views = set(re.findall(r"'([^']+)'", views_match.group(1))) if views_match else set()
        check(views == nav, f"{role} 前端跳转白名单与目录一致")
        for item in records:
            text = (REPO / item["source"]).read_text(encoding="utf-8")
            for anchor in item["anchors"]:
                check(anchor in text, f"{role}:{item['id']} 代码锚点 {anchor}")
            check(item["view"] in nav, f"{item['id']} 的目标页面属于当前角色")
            result = lookup_guide(role, feature_id=item["id"])
            check(result.get("found") and result["features"][0]["steps"] == item["steps"], f"{item['id']} 可精确查询")
        flow_id = "admin_ops" if role == "admin" else "explain"
        ctx = ToolContext(store=None, flow_id=flow_id, extra={"role": role})
        offered = {item["function"]["name"] for item in openai_tools(flow_id, load_flow(flow_id)["tools"], role)}
        check({"get_system_guide", "suggest_action"} <= offered, f"{role} 模型可用操作手册与导航")
        for view in nav:
            result = execute("suggest_action", {"kind": "navigate", "label": "打开页面", "view": view}, ctx)
            check(result.get("ok") and result["queued"] == {"kind": "navigate", "label": "打开页面", "view": view},
                  f"{role}/{view} 导航沿用原事件字段")
        for view in {"users", "structure", "practice", "graph-edit", "assistant", "ai", "chat"} - nav:
            before = len(ctx.turn.get("actions", []))
            result = execute("suggest_action", {"kind": "navigate", "label": "打开页面", "view": view}, ctx)
            check("error" in result and len(ctx.turn.get("actions", [])) == before, f"{role} 拒绝跨角色导航 {view}")
        if role != "student":
            result = execute("suggest_action", {"kind": "practice", "label": "去练习", "kp_id": "KP001"}, ctx)
            check("error" in result, f"{role} 拒绝学生练习入口")
        result = execute("get_system_guide", {"feature_id": "teacher.structure.chapter.edit"}, ctx)
        check(bool(result.get("found")) == (role == "teacher"), f"{role} 编辑章节手册权限")
        flow = load_flow(flow_id)
        prompt = build_system_prompt(load_persona(flow["persona"]), flow, {"role": role})
        check("系统操作目录" in prompt and "system_guide" in prompt, f"{role} 提示词含操作目录")
        if role != "teacher":
            check("teacher.structure.chapter.edit" not in prompt.split("当前登录角色可用的系统操作目录")[-1], f"{role} 目录没有教师操作")

    for name in ("get_system_guide", "suggest_action"):
        check(TOOLS[name].approval is None, f"{name} 不新增业务写操作")
    unknown = ToolContext(store=None, flow_id="explain", extra={})
    check("error" in execute("get_system_guide", {"query": "编辑课程"}, unknown), "身份缺失不能查操作目录")
    for role, question, expected in [
        ("teacher", "在哪里修改章节名称", "teacher.structure.chapter.edit"),
        ("teacher", "知识图谱如何连线", "teacher.graph.link"),
        ("admin", "如何重置密码", "admin.users.edit"),
        ("student", "双击图片放大预览", "chat.image"),
    ]:
        result = lookup_guide(role, query=question)
        check(expected in {item["id"] for item in result.get("features", [])}, f"完整问题查找：{question}")
    from app.agent_st.agent.runtime import _explain_out_of_scope
    ctx = ToolContext(store=None, flow_id="explain", extra={"role": "teacher"})
    execute("get_system_guide", {"feature_id": "teacher.structure.chapter.edit"}, ctx)
    check(not _explain_out_of_scope(ctx, "章节怎么编辑"), "成功查询操作目录不误判课程越界")
    print(f"检查目录：{len(catalogue()['roles'])} 个角色，{sum(len(allowed_views(r)) for r in catalogue()['roles'])} 个页面，{count} 条角色操作记录")
    print(f"结果：{len(failures)} 项失败" if failures else "结果：全部通过")
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
