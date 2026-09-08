from __future__ import annotations

import yaml

from app.agent_st.agent.config import AGENT_DIR


def load_yaml(rel: str) -> dict:
    path = AGENT_DIR / rel
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_persona(name: str = "course_tutor") -> dict:
    return load_yaml(f"personas/{name}.yaml")


def load_skill(name: str) -> str:
    path = AGENT_DIR / "skills" / name
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def load_flow(flow_id: str) -> dict:
    aliases = {"qa": "explain", "tutoring": "explain"}
    flow_id = aliases.get(flow_id, flow_id)
    return load_yaml(f"flows/{flow_id}.yaml")


EXPLAIN_GROUNDING = (
    "讲解约束：必须先检索。命中的原文必须引用 [题号] 或 [小节]。"
    "原文不足时可以用课程常识补充，但必须用【补充】显式标注「非课程原文」，"
    "且不得伪造题号或小节。"
)

GENERATE_GROUNDING = (
    "出题约束：必须按任务流调用工具，不要跳过构思与校验。"
    "题面与 graph 不得把题库原题做数值/标签微扰动后当作新题。"
    "没有工具结果时禁止编造 graph 结构或字段名。"
    "保存前必须 submit_item_plan（含解题过程）、validate_question、check_novelty 均通过。"
)


def _grounding_for_flow(flow: dict) -> str:
    flow_id = str(flow.get("id") or "")
    if flow_id == "generate_items":
        return GENERATE_GROUNDING
    return EXPLAIN_GROUNDING


def build_system_prompt(persona: dict, flow: dict, extra_context: dict | None = None) -> str:
    skill_names = flow.get("skills") or persona.get("skills") or []
    skills = [load_skill(name) for name in skill_names]
    flow_text = yaml.safe_dump({k: flow[k] for k in flow if k != "skills"}, allow_unicode=True)
    ctx = extra_context or {}
    return "\n\n".join(
        [
            persona.get("system", ""),
            "\n\n".join(s for s in skills if s),
            "当前任务流（必须按步骤调用工具，不要跳过检索）：\n" + flow_text,
            "当前页面上下文：" + str(ctx),
            _grounding_for_flow(flow),
        ]
    )
