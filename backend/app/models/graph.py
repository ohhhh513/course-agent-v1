"""
三大图谱模型：知识图谱 / 问题图谱 / 目标图谱
"""
from sqlalchemy import Column, String, Integer, Float, Boolean, Text, DateTime, ForeignKey
from datetime import datetime
from ..database import Base


class GraphNode(Base):
    """图谱节点"""
    __tablename__ = "graph_nodes"

    id = Column(String(32), primary_key=True)         # KP01 / PB1 / G0
    graph_type = Column(String(16), primary_key=True)  # knowledge / problem / goal（联合主键）
    course_id = Column(String(32), ForeignKey("courses.course_id"), default="C2026DS001", index=True)

    name = Column(String(128), nullable=False)
    category = Column(Integer, default=0)              # categories 下标

    # 知识图谱特有
    chapter = Column(String(32), default="")
    mastery = Column(Float, default=0)                 # 0~100
    difficulty = Column(Integer, default=2)            # 1~5
    is_key = Column(Boolean, default=False)
    hours = Column(Integer, default=0)

    # 问题图谱特有
    level = Column(Integer, default=0)
    related_kp = Column(Integer, default=0)
    error_rate = Column(Float, default=0)

    # 目标图谱特有
    achieve = Column(Float, default=0)
    weight = Column(Integer, default=0)

    # 错题簇特有
    count = Column(Integer, default=0)


class GraphLink(Base):
    """图谱边"""
    __tablename__ = "graph_links"

    id = Column(Integer, primary_key=True, autoincrement=True)
    graph_type = Column(String(16), index=True)
    course_id = Column(String(32), ForeignKey("courses.course_id"), default="C2026DS001", index=True)
    source = Column(String(32), nullable=False, index=True)
    target = Column(String(32), nullable=False, index=True)
    relation = Column(String(16), nullable=False)  # pre/advance/parallel/split/map/error/support


class KpDetail(Base):
    """知识点详情"""
    __tablename__ = "kp_details"

    kp_id = Column(String(32), primary_key=True)
    course_id = Column(String(32), ForeignKey("courses.course_id"), default="C2026DS001", index=True)

    name = Column(String(128), nullable=False)
    chapter = Column(String(32), default="")
    difficulty = Column(Integer, default=2)
    is_key = Column(Boolean, default=False)
    hours = Column(Integer, default=0)
    summary = Column(Text, default="")

    completion_rate = Column(Float, default=0)
    mastery_rate = Column(Float, default=0)
    class_avg_mastery = Column(Float, default=0)

    # JSON 字段存结构化子对象
    pre_kp = Column(Text, default="[]")         # JSON
    post_kp = Column(Text, default="[]")        # JSON
    resources = Column(Text, default="[]")      # JSON
    related_problems = Column(Text, default="[]")
    question_count = Column(Integer, default=0)
    wrong_count = Column(Integer, default=0)


class LearningPath(Base):
    """推荐学习路径 — 每个学生独立"""
    __tablename__ = "learning_paths"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), ForeignKey("users.user_id"), index=True)
    course_id = Column(String(32), ForeignKey("courses.course_id"), default="C2026DS001", index=True)
    step = Column(Integer, default=0)
    kp_id = Column(String(32), index=True)
    name = Column(String(128))
    chapter = Column(String(32), default="")
    status = Column(String(16), default="todo")    # done/doing/todo/warn
    hours = Column(Integer, default=0)
    mastery = Column(Float, default=0)
    res_count = Column(Integer, default=0)
    progress = Column(Float, default=0)
    locked = Column(Integer, default=0)           # 0/1
    lock_reason = Column(String(256), default="")
    mastered_at = Column(DateTime, nullable=True)    # 何时掌握
    last_practiced_at = Column(DateTime, nullable=True)  # 最近练习时间
