"""
课程与资源模型
"""
from datetime import datetime
from sqlalchemy import Column, String, Integer, Text, Float, ForeignKey, DateTime, UniqueConstraint
from ..database import Base


class Course(Base):
    __tablename__ = "courses"

    course_id = Column(String(32), primary_key=True)       # C2026DS001
    name = Column(String(128), nullable=False)             # 数据结构与算法
    code = Column(String(32), default="")                   # CS20301
    term = Column(String(64), default="")                   # 2026 春季学期
    teacher = Column(String(64), default="")
    credit = Column(Integer, default=0)
    chapters = Column(Integer, default=0)
    knowledge_points = Column(Integer, default=0)
    resources = Column(Integer, default=0)
    questions = Column(Integer, default=0)


class ResourceProgress(Base):
    """学生对单个资源的学习进度（视频为秒 / 文档为页）"""
    __tablename__ = "resource_progress"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), ForeignKey("users.user_id"), index=True, nullable=False)
    res_id = Column(String(32), ForeignKey("resources.res_id"), index=True, nullable=False)
    progress = Column(Integer, default=0)      # 0~100 百分比
    position = Column(Integer, default=0)    # 视频：秒；文档：页码
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ResourceStudyLog(Base):
    """每日资源观看时长累计（视频观看秒数），用于驾驶舱「今日已学」叠加资源时长"""
    __tablename__ = "resource_study_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), ForeignKey("users.user_id"), index=True, nullable=False)
    day = Column(String(16), index=True, nullable=False)        # YYYY-MM-DD
    watch_seconds = Column(Integer, default=0)                  # 当日累计观看秒数

    __table_args__ = (
        UniqueConstraint("user_id", "day", name="uq_studylog_user_day"),
    )


class Resource(Base):
    """学习资源：video / ppt / doc / quiz"""
    __tablename__ = "resources"

    res_id = Column(String(32), primary_key=True)
    course_id = Column(String(32), ForeignKey("courses.course_id"), default="C2026DS001", index=True)
    title = Column(String(256), nullable=False)
    type = Column(String(16), nullable=False)  # video / ppt / doc / quiz
    kp = Column(String(64), default="")         # 关联知识点名
    kp_id = Column(String(32), default="", index=True)
    category = Column(String(32), default="knowledge", index=True)  # knowledge=绑定知识点, other=课外/教材/章节级

    # 资源特定属性
    duration = Column(String(16), default="")    # video 时长 22:10
    pages = Column(Integer, default=0)           # ppt/doc 页数
    count = Column(Integer, default=0)           # quiz 题数

    source = Column(String(128), default="")     # 来源
    views = Column(Integer, default=0)
    url = Column(String(512), default="")        # 资源访问路径 /assets/resources/...
