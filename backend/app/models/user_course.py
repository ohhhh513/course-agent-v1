"""用户-课程关联表：多课程数据地基。

教师「授课」与学生「选课」共用一张关联表（role_in_course 区分），
这是课程隔离的归属依据：任何业务数据按 course_id 过滤前，先由本表
确认"当前用户与该课程的关系"。

历史说明：在本表出现之前，"学生属于哪门课"是隐式假设（全站单课程
C2026DS001 硬编码），多课程能力因此无法成立。
"""
from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint

from ..database import Base


class UserCourse(Base):
    __tablename__ = "user_courses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), nullable=False, index=True)      # → users.user_id
    course_id = Column(String(32), nullable=False, index=True)    # → courses.course_id
    role_in_course = Column(String(16), nullable=False, default="student")  # teacher / student
    joined_at = Column(DateTime)

    __table_args__ = (UniqueConstraint("user_id", "course_id", name="uq_user_course"),)

    def to_dict(self):
        return {
            "courseId": self.course_id,
            "roleInCourse": self.role_in_course,
            "joinedAt": self.joined_at.isoformat(sep=" ", timespec="seconds") if self.joined_at else "",
        }
