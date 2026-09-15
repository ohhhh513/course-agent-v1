"""
课程公共接口：/course/*
"""
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ..database import get_db
from ..middleware.auth import get_current_user
from ..models.course import Course
from ..models.user import User
from ..models.user_course import UserCourse
from ..schemas.common import ok, fail

router = APIRouter(prefix="/api/v1/course", tags=["课程"])


# 注意：/my 必须注册在 /{course_id} 之前，否则会被通配路由捕获
@router.get("/my")
def my_courses(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """当前用户的课程列表（教师/学生通用，基于 user_courses 成员关系）"""
    rows = (
        db.query(UserCourse, Course)
        .join(Course, Course.course_id == UserCourse.course_id)
        .filter(UserCourse.user_id == user.user_id)
        .order_by(UserCourse.joined_at.asc())
        .all()
    )
    return ok([
        {
            "courseId": c.course_id,
            "name": c.name,
            "term": c.term,
            "teacher": c.teacher,
            "role": uc.role_in_course,
            # 邀请码仅对课程教师可见（管理用途：展示给学生扫码/输码加入）
            **({"inviteCode": c.invite_code} if uc.role_in_course == "teacher" else {}),
        }
        for uc, c in rows
    ])


class JoinBody(BaseModel):
    inviteCode: str


@router.post("/join")
def join_course(body: JoinBody, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """凭邀请码加入课程（学生/教师通用，课程内角色随账号身份）"""
    code = (body.inviteCode or "").strip().upper()
    if not code:
        return fail("请输入邀请码", 400)
    course = db.query(Course).filter(Course.invite_code == code).first()
    if not course:
        return fail("邀请码无效", 404)
    exists = db.query(UserCourse).filter(
        UserCourse.user_id == user.user_id,
        UserCourse.course_id == course.course_id,
    ).first()
    if exists:
        return ok({"courseId": course.course_id, "name": course.name, "alreadyJoined": True})
    db.add(UserCourse(
        user_id=user.user_id, course_id=course.course_id,
        role_in_course=user.role, joined_at=datetime.utcnow(),
    ))
    db.commit()
    # 入课即生成该生的个人学习路径（否则学生看新课时路径为空，
    # dashboard 会回落显示默认课程的 KP —— 跨课程同名 KP 撞名的根源之一）
    if user.role == "student":
        from ..services.learning_path import sync_user
        sync_user(db, user.user_id, course.course_id)
        db.commit()
    return ok({"courseId": course.course_id, "name": course.name, "alreadyJoined": False})


@router.get("/{course_id}")
def get_course(course_id: str = "C2026DS001", db: Session = Depends(get_db)):
    course = db.query(Course).filter(Course.course_id == course_id).first()
    if not course:
        course = db.query(Course).first()
    if not course:
        return ok(None)
    return ok({
        "courseId": course.course_id,
        "name": course.name,
        "code": course.code,
        "term": course.term,
        "teacher": course.teacher,
        "credit": course.credit,
        "chapters": course.chapters,
        "knowledgePoints": course.knowledge_points,
        "resources": course.resources,
        "questions": course.questions,
    })
