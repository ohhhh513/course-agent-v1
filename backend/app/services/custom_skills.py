"""课程定制技能：现有 JSON 存储、作者/课程隔离、发布快照和乐观并发控制。"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import json
import re
import uuid

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import case, func

from app.models.course import Course
from app.models.intervention import TeacherClassDashboard
from app.models.user import User
from app.models.user_course import UserCourse

DATA_TYPE = "custom_skill"
SKILL_ID = re.compile(r"^CS[a-f0-9]{32}$")
LIMITS = {"name": 40, "purpose": 300, "steps": 3000, "outputFormat": 1000, "example": 2000}
TRIAL_TOOLS = {"resolve_topic", "retrieve_chunks", "get_question", "explain_metric"}


def _json_column():
    return case((func.json_valid(TeacherClassDashboard.data_json), TeacherClassDashboard.data_json), else_="{}")


def _query(db):
    return db.query(TeacherClassDashboard).filter(
        TeacherClassDashboard.data_type == DATA_TYPE,
        TeacherClassDashboard.class_id.is_(None),
    )


def _read(row):
    try:
        value = json.loads(row.data_json or "{}")
        if (isinstance(value, dict) and value.get("schemaVersion") == 1
                and value.get("id") == row.data_key and SKILL_ID.fullmatch(row.data_key)
                and isinstance(value.get("draft"), dict) and value.get("ownerId") and value.get("courseId")):
            return value
    except (ValueError, TypeError):
        pass
    return None


def _actor(db, user_id, course_id=None, roles=("teacher",)):
    user = db.get(User, user_id)
    if not user or user.role not in roles:
        raise HTTPException(403, "当前账号无权执行此技能操作")
    if course_id:
        member = db.query(UserCourse).filter(UserCourse.user_id == user_id, UserCourse.course_id == course_id).first()
        if not member or not db.get(Course, course_id):
            raise HTTPException(403, "你尚未加入该课程")
        if user.role == "teacher" and member.role_in_course != "teacher":
            raise HTTPException(403, "只有本课程任课教师可以管理定制技能")
    return user


def templates():
    from app.agent_st.agent.chat_skills import SKILLS
    return [{"id": sid, "label": spec["label"]} for sid, spec in SKILLS.items()
            if spec["roles"] == ("student",) and spec["flow"] == "explain"]


def validate_draft(body):
    draft = {}
    for key, limit in LIMITS.items():
        text = body.get(key, "")
        if not isinstance(text, str) or len(text.strip()) > limit:
            raise HTTPException(400, f"{key} 内容无效或超过长度限制")
        draft[key] = text.strip()
    if not all(draft[key] for key in ("name", "purpose", "steps")):
        raise HTTPException(400, "请填写技能名称、用途和处理步骤")
    base = body.get("baseSkillId")
    if base not in {item["id"] for item in templates()}:
        raise HTTPException(400, "请选择一个面向学生的内置基础技能")
    draft["baseSkillId"] = base
    if body.get("builder") is not None:
        from app.schemas.skill_builder import SkillBuilder, TEMPLATE_BASES
        try:
            builder = SkillBuilder.model_validate(body["builder"])
        except ValidationError as error:
            raise HTTPException(400, "模板选项无效，请重新检查填写内容") from error
        if builder.mode == "guided" and TEMPLATE_BASES[builder.templateId] != base:
            raise HTTPException(400, "引导式模板与基础技能不匹配，请重新选择模板")
        draft["builder"] = builder.model_dump()
    return draft


def _find(db, skill_id):
    if not SKILL_ID.fullmatch(str(skill_id)):
        raise HTTPException(404, "定制技能不存在")
    row = _query(db).filter(TeacherClassDashboard.data_key == skill_id).first()
    value = _read(row) if row else None
    if not value:
        raise HTTPException(404, "定制技能不存在或已删除")
    return row, value


def _owned(db, skill_id, user_id, course_id):
    _actor(db, user_id, course_id)
    row, value = _find(db, skill_id)
    if value["courseId"] != course_id or value["ownerId"] != user_id:
        raise HTTPException(404, "当前课程中不存在你可管理的该技能")
    return row, value


def _view(db, value):
    course = db.get(Course, value["courseId"])
    owner = db.get(User, value["ownerId"])
    return {**deepcopy(value), "courseName": course.name if course else "课程已删除",
            "ownerName": owner.name if owner else "账号已删除",
            "publishedVersion": (value.get("published") or {}).get("version", 0)}


def list_teacher(db, user_id, course_id):
    _actor(db, user_id, course_id)
    rows = _query(db).filter(func.json_extract(_json_column(), "$.ownerId") == user_id,
                             func.json_extract(_json_column(), "$.courseId") == course_id).all()
    values = [value for row in rows if (value := _read(row))]
    return {"templates": templates(), "list": [_view(db, value) for value in sorted(values, key=lambda v: v["updatedAt"], reverse=True)]}


def list_admin(db, user_id):
    _actor(db, user_id, roles=("admin",))
    values = [value for row in _query(db).all() if (value := _read(row))]
    return {"list": [_view(db, value) for value in sorted(values, key=lambda v: v["updatedAt"], reverse=True)]}


def create(db, user_id, course_id, body):
    _actor(db, user_id, course_id)
    now = datetime.utcnow().isoformat(timespec="microseconds") + "Z"
    value = {"schemaVersion": 1, "id": "CS" + uuid.uuid4().hex, "ownerId": user_id, "courseId": course_id,
             "draft": validate_draft(body), "published": None, "revision": 1,
             "enabled": False, "blocked": False, "createdAt": now, "updatedAt": now}
    db.add(TeacherClassDashboard(class_id=None, data_type=DATA_TYPE, data_key=value["id"],
                                data_json=json.dumps(value, ensure_ascii=False)))
    db.flush()
    return _view(db, value)


def _revision(value, revision):
    if value["revision"] != revision:
        raise HTTPException(409, "技能已被修改，请重新加载最新版本后再操作")


def _write(db, row, value, revision):
    _revision(value, revision)
    value = deepcopy(value)
    value["revision"] += 1
    value["updatedAt"] = datetime.utcnow().isoformat(timespec="microseconds") + "Z"
    changed = _query(db).filter(TeacherClassDashboard.id == row.id,
                                TeacherClassDashboard.data_json == row.data_json).update({
        TeacherClassDashboard.data_json: json.dumps(value, ensure_ascii=False),
        TeacherClassDashboard.updated_at: datetime.utcnow(),
    }, synchronize_session=False)
    if changed != 1:
        raise HTTPException(409, "技能已被修改，请重新加载最新版本后再操作")
    return _view(db, value)


def save(db, skill_id, user_id, course_id, body, revision):
    row, value = _owned(db, skill_id, user_id, course_id)
    value["draft"] = validate_draft(body)
    return _write(db, row, value, revision)


def publish(db, skill_id, user_id, course_id, revision):
    row, value = _owned(db, skill_id, user_id, course_id)
    if value.get("blocked"):
        raise HTTPException(403, "该技能已被管理员停用，不能重新发布")
    number = (value.get("published") or {}).get("version", 0) + 1
    value["published"] = {**validate_draft(value["draft"]), "version": number}
    value["enabled"] = True
    return _write(db, row, value, revision)


def disable(db, skill_id, user_id, revision, course_id=None, admin=False):
    if admin:
        _actor(db, user_id, roles=("admin",))
        row, value = _find(db, skill_id)
        value["blocked"] = True
    else:
        row, value = _owned(db, skill_id, user_id, course_id)
    value["enabled"] = False
    return _write(db, row, value, revision)


def _author_available(db, value):
    owner = db.get(User, value["ownerId"])
    return bool(owner and owner.role == "teacher" and db.query(UserCourse).filter(
        UserCourse.user_id == owner.user_id, UserCourse.course_id == value["courseId"],
        UserCourse.role_in_course == "teacher").first())


def list_student(db, user_id, course_id):
    _actor(db, user_id, course_id, roles=("student",))
    rows = _query(db).filter(func.json_extract(_json_column(), "$.courseId") == course_id).all()
    result = []
    for row in rows:
        value = _read(row)
        if not value or not value.get("enabled") or value.get("blocked") or not value.get("published") or not _author_available(db, value):
            continue
        published = value["published"]
        result.append({"id": value["id"], "label": published["name"], "desc": published["purpose"],
                       "hint": "已启用「" + published["name"] + "」，输入你的问题", "version": published["version"]})
    return {"list": sorted(result, key=lambda item: (item["label"], item["id"]))}


def resolve(db, skill_id, user_id, course_id, role, *, trial=False, revision=None):
    from app.agent_st.agent.chat_skills import SKILLS
    if trial:
        _, value = _owned(db, skill_id, user_id, course_id)
        if role != "teacher":
            raise HTTPException(403, "只有技能作者可以试用草稿")
        _revision(value, revision)
        draft = value["draft"]
    else:
        _actor(db, user_id, course_id, roles=("student",))
        _, value = _find(db, skill_id)
        if (role != "student" or value["courseId"] != course_id or not value.get("enabled")
                or value.get("blocked") or not value.get("published") or not _author_available(db, value)):
            raise HTTPException(403, "该技能尚未发布、已停用或不属于当前课程")
        draft = value["published"]
    base = SKILLS.get(draft.get("baseSkillId"))
    if not base or base["roles"] != ("student",) or base["flow"] != "explain":
        raise HTTPException(403, "该技能的基础能力已不可用")
    spec = deepcopy(base)
    instructions = {key: content for key, content in draft.items() if key != "builder"}
    spec.update(id=value["id"], label=draft["name"], custom=deepcopy(instructions),
                customActor=user_id, customCourse=course_id, customRevision=value["revision"],
                customVersion=draft.get("version", 0), trial=trial)
    if trial:
        spec["roles"] = ("teacher",)
        spec["tools"] = [name for name in spec["tools"] if name in TRIAL_TOOLS]
        spec["guide"] = False
    return spec


def delete_owned(db, user_id):
    return _query(db).filter(func.json_extract(_json_column(), "$.ownerId") == user_id).delete(synchronize_session=False)
