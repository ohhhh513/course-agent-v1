"""教师创建与试用、学生使用、管理员停用课程技能。"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session
from typing import Literal

from app.database import get_db
from app.dependencies import get_current_course_id, require_admin, require_role
from app.schemas.common import ok
from app.schemas.skill_builder import SkillBuilder
from app.services import custom_skills as service

student_router = APIRouter(prefix="/api/v1/skills", tags=["课程技能"])
teacher_router = APIRouter(prefix="/api/v1/teacher/skills", tags=["教师定制技能"], dependencies=[Depends(require_role("teacher"))])
admin_router = APIRouter(prefix="/api/v1/admin/skills", tags=["管理员技能治理"], dependencies=[Depends(require_admin)])


class Draft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=40)
    baseSkillId: str
    purpose: str = Field(min_length=1, max_length=300)
    steps: str = Field(min_length=1, max_length=3000)
    outputFormat: str = Field(default="", max_length=1000)
    example: str = Field(default="", max_length=2000)
    builder: SkillBuilder | None = None


class Revision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)


class UpdateDraft(Draft):
    revision: int = Field(ge=1)


class TrialMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["user", "assistant"]
    content: str = Field(max_length=8000)


class Trial(Revision):
    question: str = Field(min_length=1, max_length=2000)
    history: list[TrialMessage] = Field(default_factory=list, max_length=10)


def commit(db, task):
    try:
        result = task()
        db.commit()
        return ok(result)
    except Exception:
        db.rollback()
        raise


@student_router.get("")
def student_list(db: Session = Depends(get_db), user=Depends(require_role("student")), course_id=Depends(get_current_course_id)):
    return ok(service.list_student(db, user.user_id, course_id))


@teacher_router.get("")
def teacher_list(db: Session = Depends(get_db), user=Depends(require_role("teacher")), course_id=Depends(get_current_course_id)):
    return ok(service.list_teacher(db, user.user_id, course_id))


@teacher_router.post("")
def create(body: Draft, db: Session = Depends(get_db), user=Depends(require_role("teacher")), course_id=Depends(get_current_course_id)):
    return commit(db, lambda: service.create(db, user.user_id, course_id, body.model_dump()))


@teacher_router.put("/{skill_id}")
def save(skill_id: str, body: UpdateDraft, db: Session = Depends(get_db), user=Depends(require_role("teacher")), course_id=Depends(get_current_course_id)):
    return commit(db, lambda: service.save(db, skill_id, user.user_id, course_id, body.model_dump(exclude={"revision"}), body.revision))


@teacher_router.post("/{skill_id}/publish")
def publish(skill_id: str, body: Revision, db: Session = Depends(get_db), user=Depends(require_role("teacher")), course_id=Depends(get_current_course_id)):
    return commit(db, lambda: service.publish(db, skill_id, user.user_id, course_id, body.revision))


@teacher_router.post("/{skill_id}/disable")
def disable(skill_id: str, body: Revision, db: Session = Depends(get_db), user=Depends(require_role("teacher")), course_id=Depends(get_current_course_id)):
    return commit(db, lambda: service.disable(db, skill_id, user.user_id, body.revision, course_id))


@teacher_router.post("/{skill_id}/trial")
def trial(skill_id: str, body: Trial, db: Session = Depends(get_db), user=Depends(require_role("teacher")), course_id=Depends(get_current_course_id)):
    from app.services.skill_trial import run_trial
    spec = service.resolve(db, skill_id, user.user_id, course_id, "teacher", trial=True, revision=body.revision)
    if not body.question.strip():
        raise HTTPException(400, "请先输入测试问题")
    return ok(run_trial(spec, user.user_id, course_id, body.question.strip(), [message.model_dump() for message in body.history]))


@admin_router.get("")
def admin_list(db: Session = Depends(get_db), user=Depends(require_admin)):
    return ok(service.list_admin(db, user.user_id))


@admin_router.post("/{skill_id}/disable")
def admin_disable(skill_id: str, body: Revision, db: Session = Depends(get_db), user=Depends(require_admin)):
    return commit(db, lambda: service.disable(db, skill_id, user.user_id, body.revision, admin=True))
