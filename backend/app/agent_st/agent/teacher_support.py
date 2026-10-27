"""教师教学扩展的范围判断；不影响学生、管理员或定制技能草稿试用。"""
from __future__ import annotations

import re


TEACHING_REQUEST = re.compile(
    r"备课|教案|教学|课堂|授课|讲授|讲课|课外拓展|课程拓展|拓展阅读|"
    r"示例代码|代码示例|教学案例|教学示例|技术文档|官方文档|实验设计|课程设计"
)


def teacher_support_enabled(extra: dict) -> bool:
    return (extra.get("role") == "teacher"
            and not extra.get("_skillTrial")
            and not extra.get("_customSkillSnapshot")
            and str(extra.get("skillId") or "") in ("", "web_research"))


def is_teaching_request(message: str) -> bool:
    return bool(TEACHING_REQUEST.search(str(message or "")))
