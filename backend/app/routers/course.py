"""
课程公共接口：/course/*
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..database import get_db
from ..models.course import Course
from ..schemas.common import ok

router = APIRouter(prefix="/api/v1/course", tags=["课程"])


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
