"""公共 FastAPI 依赖。

课程上下文（多课程重构 · Step 5 起含成员校验）：
- 从请求头 ``X-Course-Id`` 读取当前课程，未携带时回退 ``DEFAULT_COURSE_ID``
  （请求缺省——前端 api.js 默认会带头；这不是旧库兼容）；
- **校验当前用户与该课程的归属关系**（user_courses 表），未加入则 403；
  归属的建立入口：教师建课（POST /teacher/courses）、凭邀请码入课
  （POST /course/join）、seed 初始灌入。
- 数据库结构完全由 models/ 定义（面向删库重建），本依赖不做任何旧库兼容。
"""
from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from .database import get_db
from .media_utils import DEFAULT_COURSE_ID
from .middleware.auth import get_current_user
from .models.user_course import UserCourse


async def get_current_course_id(
    x_course_id: str = Header(default="", alias="X-Course-Id"),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
) -> str:
    """当前请求的课程上下文（含成员校验）"""
    course_id = (x_course_id or "").strip() or DEFAULT_COURSE_ID
    member = db.query(UserCourse).filter(
        UserCourse.user_id == user.user_id,
        UserCourse.course_id == course_id,
    ).first()
    if not member:
        raise HTTPException(status_code=403, detail=f"你尚未加入课程 {course_id}")
    return course_id
