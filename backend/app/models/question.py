"""
题库/习题模型
"""
from sqlalchemy import Column, String, Integer, Float, Text, ForeignKey
from ..database import Base


class Question(Base):
    """题库题目（含 AI 生成题和题库）"""
    __tablename__ = "questions"

    q_id = Column(String(32), primary_key=True)               # Q1024
    course_id = Column(String(32), ForeignKey("courses.course_id"), default="C2026DS001", index=True)
    kp_id = Column(String(32), default="", index=True)

    type = Column(String(16), default="single")               # single/multi/judge/blank/code
    difficulty = Column(Integer, default=3)                    # 1~5
    score = Column(Integer, default=5)
    status = Column(String(16), default="published")          # pending/approved/published/archived

    stem = Column(Text, nullable=False)                        # 题干
    options = Column(Text, default="[]")                       # JSON 选项
    answer = Column(String(64), default="")
    analysis = Column(Text, default="")

    kp_path = Column(Text, default="[]")                       # JSON 知识点路径
    pre_kp = Column(Text, default="[]")
    post_kp = Column(Text, default="[]")
    is_key = Column(Integer, default=0)                        # 0/1

    class_correct_rate = Column(Float, default=50)
    avg_seconds = Column(Integer, default=60)
    error_type = Column(String(32), default="")                # 概念混淆/公式记忆错误...

    # AI 生成题溯源
    source_ref_file = Column(String(32), default="")
    source_ref_locator = Column(String(32), default="")
