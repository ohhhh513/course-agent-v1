"""三端对话技能目录：选中后只加载对应提示词与工具，未选则走原任务流。

技能不改库表、不改任务流 id。flow 的 tools 仍是超集；技能白名单必须是该流工具的子集。
角色校验在服务端完成，模型不能指定 skill_id。
"""
from __future__ import annotations

from typing import Any

GUIDE_TOOLS: tuple[str, ...] = (
    "get_system_guide",
    "prepare_ui_action",
    "suggest_action",
    "offer_choices",
)


def _spec(
    *,
    label: str,
    roles: tuple[str, ...],
    flow: str,
    file: str,
    tools: tuple[str, ...],
    guide: bool = True,
) -> dict[str, Any]:
    merged = list(dict.fromkeys((*(GUIDE_TOOLS if guide else ()), *tools)))
    return {
        "label": label,
        "roles": roles,
        "flow": flow,
        "file": file,
        "guide": guide,
        "tools": merged,
    }


# id 与前端 composer 菜单一致。
SKILLS: dict[str, dict[str, Any]] = {
    "course_qa": _spec(
        label="课程答疑",
        roles=("student",),
        flow="explain",
        file="student_course_qa.md",
        tools=("resolve_topic", "retrieve_chunks", "get_question", "breakdown"),
    ),
    "wrong_review": _spec(
        label="错题复盘",
        roles=("student",),
        flow="explain",
        file="student_wrong_review.md",
        tools=("resolve_topic", "retrieve_chunks", "get_question", "my_last_attempt"),
    ),
    "mastery": _spec(
        label="学情诊断",
        roles=("student",),
        flow="explain",
        file="student_mastery.md",
        tools=("explain_metric", "my_alerts", "breakdown", "weak_ranking", "resolve_topic"),
    ),
    "practice": _spec(
        label="练习教练",
        roles=("student",),
        flow="explain",
        file="student_practice.md",
        tools=("weak_ranking", "my_alerts", "breakdown", "resolve_topic"),
    ),
    "resource": _spec(
        label="资源导航",
        roles=("student",),
        flow="explain",
        file="student_resource.md",
        tools=("resolve_topic",),
    ),
    "class": _spec(
        label="班级学情",
        roles=("teacher",),
        flow="explain",
        file="teacher_class.md",
        tools=("class_overview", "class_alerts", "kp_heatmap"),
    ),
    "student_track": _spec(
        label="个体追踪",
        roles=("teacher",),
        flow="explain",
        file="teacher_student_track.md",
        tools=("student_profile", "class_alerts"),
    ),
    "wrong_analysis": _spec(
        label="错题归因",
        roles=("teacher",),
        flow="explain",
        file="teacher_wrong_analysis.md",
        tools=("hot_wrong_questions", "kp_heatmap", "class_question_hotspots", "resolve_topic"),
    ),
    "question": _spec(
        label="备课出题",
        roles=("teacher",),
        flow="explain",
        file="teacher_question.md",
        tools=("resolve_topic",),
    ),
    "web_research": _spec(
        label="联网备课",
        roles=("teacher",),
        flow="explain",
        file="teacher_web_research.md",
        tools=("search_web", "read_web_page", "prepare_web_question", "resolve_topic", "retrieve_chunks", "get_question"),
    ),
    "report": _spec(
        label="学情报告",
        roles=("teacher",),
        flow="explain",
        file="teacher_report.md",
        tools=("class_overview",),
    ),
    "accounts": _spec(
        label="账号治理",
        roles=("admin",),
        flow="admin_ops",
        file="admin_accounts.md",
        tools=(
            "account_overview",
            "preview_account_import",
            "import_accounts",
            "preview_account_delete",
            "delete_accounts",
            # 删课程与删账号同属「治理写入」，管理员在账号治理里点名删课也走得通
            "preview_course_delete",
            "delete_course",
        ),
    ),
    "courses": _spec(
        label="课程核查",
        roles=("admin",),
        flow="admin_ops",
        file="admin_courses.md",
        tools=("course_overview", "data_check",
              "preview_course_delete", "delete_course"),
    ),
    "kb": _spec(
        label="知识库体检",
        roles=("admin",),
        flow="admin_ops",
        file="admin_kb.md",
        tools=("kb_status", "data_check"),
    ),
    "runtime": _spec(
        label="平台运行",
        roles=("admin",),
        flow="admin_ops",
        file="admin_runtime.md",
        tools=("system_overview", "kb_status", "data_check"),
    ),
}


def files_for_skill(spec: dict[str, Any]) -> list[str]:
    names = [str(spec.get("file") or "")]
    if spec.get("guide"):
        names.append("system_guide.md")
    return [n for n in names if n]


def resolve_chat_skill(flow_id: str, role: str, skill_id: str | None, *, user_id="", course_id="", trial=False, revision=None) -> tuple[dict[str, Any] | None, str]:
    """返回 (技能规格, 错误文案)。未选技能时规格为 None、错误为空。"""
    sid = str(skill_id or "").strip()
    if not sid:
        return None, ""
    spec = SKILLS.get(sid)
    if spec is None and sid.startswith("CS"):
        from fastapi import HTTPException
        from app.database import SessionLocal
        from app.services.custom_skills import resolve
        try:
            with SessionLocal() as db:
                spec = resolve(db, sid, user_id, course_id, role, trial=trial, revision=revision)
        except HTTPException as error:
            return None, str(error.detail)
    if spec is None:
        return None, "未知技能"
    labeled = spec["label"]
    if spec["flow"] != flow_id:
        return None, f"当前任务流不能使用技能「{labeled}」"
    if role and role not in spec["roles"]:
        return None, f"当前角色不能使用技能「{labeled}」"
    resolved = dict(spec)
    resolved["id"] = sid
    return resolved, ""


def skills_for_role(role: str) -> list[str]:
    return [sid for sid, spec in SKILLS.items() if role in spec["roles"]]


def bind_skill(flow: dict, extra: dict, *, user_id="", course_id="") -> tuple[dict[str, Any] | None, list[str], str]:
    """按本轮 extra['skillId'] 收窄工具。未选技能则返回任务流原白名单。"""
    flow_id = str(flow.get("id") or "")
    role = str(extra.get("role") or "").strip()
    sid = str(extra.get("skillId") or "").strip()
    course_id = course_id or str(extra.get("courseId") or "")
    # 该字段只由服务端运行层写入，SDK 的预检和工作线程复用同一轮快照。
    snapshot = extra.get("_customSkillSnapshot")
    if (isinstance(snapshot, dict) and snapshot.get("id") == sid
            and snapshot.get("customActor") == user_id and snapshot.get("customCourse") == course_id
            and snapshot.get("flow") == flow_id and role in snapshot.get("roles", ())):
        skill, err = dict(snapshot), ""
    else:
        skill, err = resolve_chat_skill(flow_id, role, sid, user_id=user_id, course_id=course_id,
                                        trial=bool(extra.get("_skillTrial")), revision=extra.get("_skillTrialRevision"))
    flow_tools = list(flow.get("tools") or [])
    if err:
        extra.pop("skillTools", None)
        return None, flow_tools, err
    if not skill:
        extra.pop("skillTools", None)
        extra.pop("skillId", None)
        return None, flow_tools, ""
    if skill.get("custom"):
        extra["_customSkillSnapshot"] = dict(skill)
    allowed = [name for name in skill["tools"] if name in set(flow_tools)]
    extra["skillId"] = skill["id"]
    extra["skillTools"] = allowed
    extra["skillLabel"] = skill["label"]
    return skill, allowed, ""
