"""
工具函数：JSON 列序列化/反序列化、时间与通用查询等
"""
import json
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session


# 数据库现有 DateTime 字段保存的是无时区 UTC 时间（datetime.utcnow()）。
# 这里统一在接口展示和中国本地日期统计时转换，避免直接把 UTC 当作北京时间。
CHINA_TZ = ZoneInfo("Asia/Shanghai")
UTC = timezone.utc


def utc_now_naive() -> datetime:
    """返回与现有数据库字段兼容的 UTC 无时区时间。"""
    return datetime.now(UTC).replace(tzinfo=None)


def china_now() -> datetime:
    """返回带 Asia/Shanghai 时区信息的当前时间。"""
    return datetime.now(CHINA_TZ)


def as_china_time(value: datetime | None) -> datetime | None:
    """将数据库中的 UTC 时间转换为中国时间。

    SQLite 读取的 DateTime 通常是无时区 datetime；按项目既有约定将其视为 UTC。
    """
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(CHINA_TZ)


def format_china_time(value: datetime | None, fmt: str) -> str:
    """按中国时区格式化时间，供接口返回给前端。"""
    local = as_china_time(value)
    return local.strftime(fmt) if local else ""


def china_day_bounds_utc(day: date | None = None) -> tuple[datetime, datetime]:
    """返回中国某自然日对应的 UTC 无时区起止时间，供数据库筛选使用。"""
    day = day or china_now().date()
    start_local = datetime.combine(day, time.min, tzinfo=CHINA_TZ)
    end_local = datetime.combine(day, time.max, tzinfo=CHINA_TZ)
    return (
        start_local.astimezone(UTC).replace(tzinfo=None),
        end_local.astimezone(UTC).replace(tzinfo=None),
    )


def china_date_to_utc_start(day: date) -> datetime:
    """返回中国某自然日零点对应的 UTC 无时区时间。"""
    return china_day_bounds_utc(day)[0]


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
