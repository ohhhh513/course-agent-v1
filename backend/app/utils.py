"""
工具函数：JSON 列序列化/反序列化、通用查询等
"""
import json
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session


# 东八区（中国），无夏令时；数据库存的是 UTC，展示前转本地
_CN_TZ = timezone(timedelta(hours=8))


def to_local(dt):
    """把库中的 naive UTC 时间转成东八区 naive 本地时间。"""
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_CN_TZ).replace(tzinfo=None)


def fmt_dt(dt, fmt: str = "%Y-%m-%d %H:%M") -> str:
    """把 UTC 时间格式化为东八区本地时间字符串。"""
    if dt is None:
        return ""
    return to_local(dt).strftime(fmt)


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
