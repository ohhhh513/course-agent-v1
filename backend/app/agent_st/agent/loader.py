from __future__ import annotations

from pathlib import Path

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
            "没有工具结果时禁止编造定义、题号或 graph 结构。",
        ]
    )
