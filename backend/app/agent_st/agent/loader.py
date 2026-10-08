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
    "讲解约束：必须先检索。命中的原文必须引用 [题号 q_id] 或 [知识点 KP0xx]。"
    "原文不足时可以用课程常识补充，但必须用【补充】显式标注「非课程原文」，"
    "且不得伪造题号或知识点。"
    "定位一律把用户原话整句交给 resolve_topic，禁止拆成单字或自己判断知识点 id ——"
    "本课知识点是成词的（「树形查找」与「查找」是两个不同知识点）。"
)

GENERATE_GROUNDING = (
    "出题约束：必须按任务流调用工具，不要跳过构思与校验。"
    "题面与 graph 不得把题库原题做数值/标签微扰动后当作新题。"
    "没有工具结果时禁止编造 graph 结构或字段名。"
    "chapter_id / kp_ids 必须取自 resolve_topic 的结果，不要自造 id；"
    "定位用整词，不要拆词。"
    "禁止输出 q_id 字段或自编题号，题号由系统在保存时分配。"
    "保存前必须 submit_item_plan（含解题过程）、validate_question、check_novelty 均通过。"
)


ADMIN_GROUNDING = (
    "平台治理约束：主要回答与「平台运行 / 账号 / 课程规模 / 知识库索引 / 数据一致性」有关的问题，"
    "数据一律来自工具调用（system_overview / account_overview / course_overview / kb_status / data_check），"
    "数字一律来自工具，禁止凭印象、估算或按经验作答；工具没给到的数字就不要说。"
    "工具返回的 basis 是给你自己对齐用的，**默认不写进回答**；只有管理员问起统计方式时才用一句话说明。"
    "本流的写操作**只有两种**：账号录入（import_accounts）与账号删除（delete_accounts）——"
    "它们会先排成「待批准」动作，管理员在确认卡片上点「确认执行」后才真正生效，"
    "因此**绝不能说已经录入 / 已经删除 / 已经修改**，必须提示管理员去点确认卡片。"
    "其余写操作（重建索引、改课程内容、发通知等）本助手确实做不到：如实说明，并指出对应的管理页面入口。"
    "课程不存在、数据为空等情况如实说明，不要编造。"
)


def _grounding_for_flow(flow: dict) -> str:
    flow_id = str(flow.get("id") or "")
    if flow_id == "generate_items":
        return GENERATE_GROUNDING
    if flow_id == "admin_ops":
        return ADMIN_GROUNDING
    return EXPLAIN_GROUNDING


def _flow_header(flow: dict) -> str:
    """「当前任务流」那句的措辞：按流区分，避免把检索约束套到不检索的流上。"""
    if str(flow.get("id") or "") == "admin_ops":
        return ("当前任务流（必须按步骤调用工具；本流不做教材检索，"
                "账号录入 / 账号删除是写操作、必须经确认卡片）：")
    return "当前任务流（必须按步骤调用工具，不要跳过检索）："


def build_system_prompt(
    persona: dict,
    flow: dict,
    extra_context: dict | None = None,
    course_catalog: str = "",
) -> str:
    skill_names = flow.get("skills") or persona.get("skills") or []
    skills = [load_skill(name) for name in skill_names]
    flow_text = yaml.safe_dump({k: flow[k] for k in flow if k != "skills"}, allow_unicode=True)
    ctx = extra_context or {}
    parts = [
        persona.get("system", ""),
        "\n\n".join(s for s in skills if s),
        _flow_header(flow) + "\n" + flow_text,
    ]
    if course_catalog:
        parts.append(
            "本课程「章 + 知识点」清单（术语以这些名称为准；"
            "用户提到的说法若与某个知识点名称一致，就定位到它，不要臆造其它知识点）：\n"
            + course_catalog
        )
    parts.append("当前页面上下文：" + str(ctx))
    parts.append(_grounding_for_flow(flow))
    return "\n\n".join(parts)
