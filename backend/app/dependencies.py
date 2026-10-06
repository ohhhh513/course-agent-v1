"""公共 FastAPI 依赖。

课程上下文：
- 优先读请求头 ``X-Course-Id``；
- 未携带时：取当前用户 ``user_courses`` 中的第一门课（教师优先 owner 课）；
- 用户一门课都没有 → 400「尚未创建或加入课程」，**绝不回退**到演示课 C2026DS001；
- 携带了课号但未加入 → 403。

角色依赖（P2 角色基建）：
- ``require_teacher``：教师或管理员可用；挂在教师端路由上（/teacher、/analysis、
  /question、/intervention、/report）。学生 token 访问这些前缀一律 403。
- ``require_admin``：仅管理员。
两个依赖都基于 JWT 里的用户角色（``users.role``），与请求体、查询参数无关，
模型/前端都无法伪造。
"""
from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from .database import get_db
from .middleware.auth import get_current_user
from .models.user_course import UserCourse

ROLE_TEACHER = "teacher"
ROLE_STUDENT = "student"
ROLE_ADMIN = "admin"


def require_role(*roles: str):
    """生成一个「必须属于指定角色」的 FastAPI 依赖。

    例：``Depends(require_role("teacher", "admin"))``。
    未登录仍是 401（由 get_current_user 抛出），角色不符是 403。
    """
    allowed = tuple(r for r in roles if r)

    async def _dep(user=Depends(get_current_user)):
        role = (getattr(user, "role", "") or "").strip()
        if role not in allowed:
            raise HTTPException(
                status_code=403,
                detail=f"当前账号角色（{role or '未知'}）无权访问该接口",
            )
        return user

    return _dep


# 常用角色依赖（在 APIRouter(dependencies=[Depends(...)]) 里挂）
require_teacher = require_role(ROLE_TEACHER, ROLE_ADMIN)
require_student = require_role(ROLE_STUDENT, ROLE_ADMIN)
require_admin = require_role(ROLE_ADMIN)


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
