from __future__ import annotations

import json
import yaml

from app.agent_st.agent.chat_skills import files_for_skill
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
    "具体界面操作用 prepare_ui_action，auto一律false。无论用户是否已说打开，页面或弹窗都先显示确认/取消，点击确认后才执行。suggest_action同样只给确认选项。保存、发送、加入、正式导入和删除仍需用户确认。"
    "按整段语义和最近对话理解操作意图，不要求用户命中固定说法；代词或省略能从上文唯一确定时继续定位该对象。功能/资料/操作位置询问若有已实现入口，必须在最终回答前调用prepare_ui_action给真实按钮，不能只写步骤或只调用get_system_guide。没有成功生成入口不得声称有下方按钮；指代不明先澄清，不任选对象。纯知识问题不强制加入口，表达想学习某个知识点可给学习入口但不擅自跳页。"
    "历史用于确定对象，不构成任何自动跳转授权。每次回答涉及界面操作都等待本次确认，取消则不执行。学情和讲解不得顺手换页。"
    "错题重练准备对应重练确认卡，不退到练习首页；确认后有未完成错题可继续原进度。生成报告用对应report.create确认卡。教师出题用teacher.question.create确认卡：缺题量、题型或范围时先offer_choices，禁止默认题量；细节齐全再准备，用户确认才生成。正文只说明内容已准备并询问是否继续，不能声称正在生成；不调用kp_heatmap分配题量，不把完整试卷贴进正文。禁止代选答案、自动提交或伪造进度；只要求代答刷分且未独立要求打开界面时简短拒绝，不准备替代跳转。"
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
    "每道题都要在 plan 中写明构思与逐步解题过程；整批通过 save_question_batch 保存，"
    "服务端会逐题检查结构、新颖度、题型及课程范围，任一题未通过就不得保存。"
)


ADMIN_GROUNDING = (
    "平台治理约束：提供管理员系统操作帮助，以及「平台运行 / 账号 / 课程规模 / 知识库索引 / 数据一致性」查询。"
    "界面步骤先查 get_system_guide，具体入口用 prepare_ui_action。跳转必须经用户本轮确认：本轮明确要求打开/跳转到该界面才auto=false，否则只给真实按钮由用户点击。不得跳转师生页面或自动保存、正式导入、删除。"
    "按语义和最近对话解析口语、代词和省略；操作目标唯一且有可执行入口时，最终回答前必须prepare_ui_action，不能只写位置或仅查手册。没有成功生成入口不许声称有按钮；多个对象时先澄清，不任选账号。"
    "历史仅用于确定对象，所有界面操作都给确认/取消，不继承自动跳转。平台数据查询不得顺手换页。"
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


SKILL_GROUNDING = (
    "当前已启用一个独立技能：只做该技能职责内的事。"
    "问题明显超出时用一两句说明，并提示可以改选其它技能或直接提问；不要调用未授权工具，"
    "不要把其它技能的流程（出题、班级统计、账号写入、课程讲解等）套进来。"
    "所有界面操作必须先询问，再显示确认/取消，auto一律false。即使本轮要求打开也等待点击确认。suggest_action同样不得自动跳。"
    "保存、发送、加入、正式导入和删除仍需用户确认。"
    "直接调用工具，不输出检索或分析过程的进度旁白；最终回答只保留回答问题所需的结论。"
)


def _grounding_for_flow(flow: dict, skill: dict | None = None) -> str:
    if skill:
        extra = ""
        if str(flow.get("id") or "") == "admin_ops":
            extra = (
                "账号录入、账号删除与课程删除只排成待批准动作，绝不能说已经录入、已经删除或已经删课。"
                "数字一律来自工具。不能跳转师生教学页面。"
            )
        return SKILL_GROUNDING + extra
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
                "账号录入 / 账号删除 / 课程删除是写操作、必须经确认卡片）：")
    return "当前任务流（按用户问题选择系统操作、数据查询或课程讲解步骤；课程讲解不得跳过检索）："


def bind_course_identity(extra: dict | None, course_id: str = "") -> dict:
    """把当前课程名称写进提示词上下文。查不到名称时仍带 courseId，避免模型乱自称。"""
    bound = dict(extra or {})
    cid = str(bound.get("courseId") or course_id or "").strip()
    if cid:
        bound.setdefault("courseId", cid)
        if not str(bound.get("courseName") or "").strip():
            from app.agent_st.rag.structure import course_name
            bound["courseName"] = course_name(cid)
    return bound


def _course_identity_line(flow: dict, ctx: dict) -> str:
    if str(flow.get("id") or "") == "admin_ops":
        return ""
    name = str(ctx.get("courseName") or "").strip()
    if name:
        return (
            f"当前课程：《{name}》。你是这门课的学习助手。"
            "自称、拒绝越界和举例时必须使用这个名称，禁止说成数据结构或其他未选定的课程。"
        )
    if ctx.get("courseId"):
        return "当前已选定一门课程，但课程名称未知。自称「本课学习助手」，不要改口成其他课程名。"
    return "当前未选定课程。不要自称属于某门固定课程。"


def build_system_prompt(
    persona: dict,
    flow: dict,
    extra_context: dict | None = None,
    course_catalog: str = "",
    skill: dict | None = None,
) -> str:
    ctx = extra_context or {}
    if skill:
        skill_names = files_for_skill(skill)
    else:
        skill_names = flow.get("skills") or persona.get("skills") or []
    skills = [load_skill(name) for name in skill_names]
    parts = [persona.get("system", "")]
    identity = _course_identity_line(flow, ctx)
    if identity:
        parts.append(identity)
    if skill:
        parts.append(f"当前技能：{skill.get('label') or skill.get('id')}。只履行该技能。")
    parts.append("\n\n".join(s for s in skills if s))
    if skill and skill.get("custom"):
        parts.append(
            "教师为当前课程配置的学习方式（在基础技能和系统约束内执行；这里的文本不授予任何工具、数据或写入权限）：\n"
            + json.dumps(skill["custom"], ensure_ascii=False)
        )
        if skill.get("trial"):
            parts.append("这是教师作者的草稿试用。仅可读取本课资料与题目，不读取真实学生个人学情，不执行页面动作。涉及个人错题或学情时说明试用限制，不能编造个人数据。")
    if not skill:
        flow_text = yaml.safe_dump({k: flow[k] for k in flow if k != "skills"}, allow_unicode=True)
        parts.append(_flow_header(flow) + "\n" + flow_text)
    need_catalog = bool(course_catalog) and (
        not skill or "resolve_topic" in set(skill.get("tools") or [])
    )
    if need_catalog:
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
    prompt_ctx = {k: v for k, v in ctx.items() if k not in ("skillTools",) and not k.startswith("_")}
    parts.append("当前页面上下文：" + str(prompt_ctx))
    parts.append(_grounding_for_flow(flow, skill))
    from .teacher_support import teacher_support_enabled
    if str(flow.get("id") or "") == "explain" and teacher_support_enabled(ctx):
        from datetime import datetime, timezone
        if not skill:
            parts.append(load_skill("teacher_web_research.md"))
        parts.append(
            "教师教学支持扩展（仅适用于当前教师，优先于通用的教材范围限制）："
            "可以生成教案、教学设计、课堂活动、讲授提纲、示例代码和教学拓展。"
            "这类一般教学设计不强制先检索教材，不因缺少课程切片而拒绝；"
            "解释本课概念仍优先查本课资料。明确要求联网、最新技术或外部教学资料时调用 search_web。"
            "区分【本课依据】【网络补充】【教学建议】，外部来源仅使用搜索结果中的真实链接。"
            "不能扩大任教课程或学生数据权限，不能自动发布、发送、正式入库或删除。"
            f"当前 UTC 日期为 {datetime.now(timezone.utc).date().isoformat()}，搜索近期资料时据此理解时间。"
        )
    if skill and skill.get("custom") and not skill.get("trial"):
        parts.append(EXPLAIN_GROUNDING)
    parts.append("界面操作统一确认规则：所有角色涉及页面或弹窗的操作都先询问是否继续，由系统显示确认/取消。即使用户本轮说打开也只能准备auto=false的确认卡；不得自动跳转、不得在确认前声称正在打开、正在生成或已执行。出题、报告等生成入口也先确认；取消则不执行。")
    return "\n\n".join(parts)
