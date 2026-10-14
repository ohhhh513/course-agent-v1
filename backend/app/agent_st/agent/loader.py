from __future__ import annotations

import yaml

from app.agent_st.agent.config import AGENT_DIR
from app.agent_st.agent.system_guide import feature_index


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
    "讲解约束：先区分系统操作、学情查询与课程讲解。系统操作先查 get_system_guide 并给出准确的面板和按钮步骤，"
    "具体界面操作用 prepare_ui_action：询问auto=false给按钮，明确指令auto=true打开并回填；保存、发送、加入、正式导入和删除仍需用户确认。"
    "按整段语义和最近对话理解操作意图，不要求用户命中固定说法；代词或省略能从上文唯一确定时继续定位该对象。功能/资料/操作位置询问若有已实现入口，必须在最终回答前调用prepare_ui_action给真实按钮，不能只写步骤或只调用get_system_guide。没有成功生成入口不得声称有下方按钮；指代不明先澄清，不任选对象。纯知识问题不强制加入口，表达想学习某个知识点可给学习入口但不擅自跳页。"
    "auto只依据本轮意图：历史用于确定对象，不继承历史的自动跳转指令。即使上一轮说我要编辑，本轮问那在哪改也必须auto=false，只给按钮；本轮明确要求打开或继续执行才auto=true。"
    "明确做错题必须打开错题重练，不得只跳到练习首页或错题本；有未完成错题会直接继续原进度。明确生成学情报告用当前角色report.create入口，让前端实际生成并打开详情。禁止代选答案、自动提交练习或伪造学习进度。用户只要求代答刷分而未独立要求打开界面时，只简短拒绝，不调用任何界面准备或导航工具，不擅自打开替代页面。"
    "学情数据用对应角色查询工具；只有课程知识讲解必须先检索，并以命中的原文为依据。正文使用题目或知识点名称说明，默认不附题号或 KP 编号；"
    "只有用户明确询问编号，或需要靠编号区分对象时，才给出工具实际返回的编号。来源编号由系统的 citations 事件单独展示。"
    "直接调用工具，不输出检索或分析过程的进度旁白；最终回答只保留回答问题所需的结论与说明。"
    "回答数量以用户的问题范围为准，排名默认最多列三项；列完即止，不追加总结、建议或邀请。"
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
    "平台治理约束：提供管理员系统操作帮助，以及「平台运行 / 账号 / 课程规模 / 知识库索引 / 数据一致性」查询。"
    "界面步骤先查 get_system_guide，具体入口用 prepare_ui_action：询问给按钮，明确指令自动打开和回填；不得跳转师生页面或自动保存、正式导入、删除。"
    "按语义和最近对话解析口语、代词和省略；操作目标唯一且有可执行入口时，最终回答前必须prepare_ui_action，不能只写位置或仅查手册。没有成功生成入口不许声称有按钮；多个对象时先澄清，不任选账号。"
    "auto只依据本轮意图，历史仅用于确定对象；上一轮要修改而本轮问哪里改，auto=false，不继承自动跳转。"
    "数据一律来自工具调用（system_overview / account_overview / course_overview / kb_status / data_check），"
    "数字一律来自工具，禁止凭印象、估算或按经验作答；工具没给到的数字就不要说。"
    "工具返回的 basis 是给你自己对齐用的，**默认不写进回答**；只有管理员问起统计方式时才用一句话说明。"
    "直接调用工具，不输出查询过程的进度旁白；最终回答只保留管理员所问维度与必要说明。"
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
    return "当前任务流（按用户问题选择系统操作、数据查询或课程讲解步骤；课程讲解不得跳过检索）："


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
    if str(flow.get("id") or "") in ("explain", "admin_ops"):
        index = feature_index(str(ctx.get("role") or ""))
        if index:
            parts.append(index)
        from .ui_actions import action_index
        parts.append(action_index(str(ctx.get("role") or "")))
    parts.append("当前页面上下文：" + str(ctx))
    parts.append(_grounding_for_flow(flow))
    return "\n\n".join(parts)
