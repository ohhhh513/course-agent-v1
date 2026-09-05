"""
工具函数：JSON 列序列化/反序列化、通用查询等
"""
import json
from sqlalchemy.orm import Session


def dumps(obj) -> str:
    if obj is None:
        return "null"
    return json.dumps(obj, ensure_ascii=False)


def loads(text: str):
    if not text:
        return None
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None


def to_user_dict(user) -> dict:
    """User ORM → 前端期望的 User dict"""
    data = {
        "userId": user.user_id,
        "name": user.name,
        "role": user.role,
        "avatarChar": user.avatar_char or user.name[0] if user.name else "",
        "avatarColor": user.avatar_color or "",
    }
    if user.role == "student":
        data.setdefault("no", user.student_no)
        data.setdefault("className", user.class_name)
    elif user.role == "teacher":
        data.setdefault("title", user.title)
        data.setdefault("dept", user.dept)
        # 教师班级列表从 TeacherClass 关联
        data.setdefault("classes", [])
    return data
