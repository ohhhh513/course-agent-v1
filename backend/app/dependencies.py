"""公共 FastAPI 依赖。

课程上下文：
- 优先读请求头 ``X-Course-Id``；
- 未携带时：取当前用户 ``user_courses`` 中的第一门课（教师优先 owner 课）；
- 用户一门课都没有 → 400「尚未创建或加入课程」，**绝不回退**到演示课 C2026DS001；
- 携带了课号但未加入 → 403。
"""
from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from .database import get_db
from .middleware.auth import get_current_user
from .models.user_course import UserCourse


async def get_current_course_id(
    x_course_id: str = Header(default="", alias="X-Course-Id"),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
) -> str:
    """当前请求的课程上下文（含成员校验）。无课时明确报错，不默认演示课。"""
    course_id = (x_course_id or "").strip()
    if course_id:
        member = db.query(UserCourse).filter(
            UserCourse.user_id == user.user_id,
            UserCourse.course_id == course_id,
        ).first()
        if not member:
            raise HTTPException(status_code=403, detail=f"你尚未加入课程 {course_id}")
        return course_id

    # 未带 X-Course-Id：取用户已有课程（教师课优先）
    rows = (
        db.query(UserCourse)
        .filter(UserCourse.user_id == user.user_id)
        .order_by(
            (UserCourse.role_in_course == "teacher").desc(),
            UserCourse.joined_at.asc(),
        )
        .all()
    )
    if not rows:
        raise HTTPException(status_code=400, detail="尚未创建或加入课程，请先建课或凭邀请码加入")
    return rows[0].course_id
