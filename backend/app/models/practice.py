"""
练习与会话模型
"""
from sqlalchemy import Column, String, Integer, Float, Text, DateTime, ForeignKey
from datetime import datetime
from ..database import Base


class PracticeSession(Base):
    """练习会话"""
    __tablename__ = "practice_sessions"

    session_id = Column(String(32), primary_key=True)          # PS...
    user_id = Column(String(64), ForeignKey("users.user_id"), index=True)
    mode = Column(String(16), default="weak")                  # weak/order/random/wrong
    total = Column(Integer, default=0)
    correct = Column(Integer, default=0)
    wrong = Column(Integer, default=0)
    accuracy = Column(Float, default=0)
    duration_seconds = Column(Integer, default=0)
    status = Column(String(16), default="running")              # running/finished
    created_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)
    questions_snapshot = Column(Text, default="[]")            # JSON 题目快照


class AnswerRecord(Base):
    """答题记录（用于错题本和统计）"""
    __tablename__ = "answer_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(32), ForeignKey("practice_sessions.session_id"), index=True)
    user_id = Column(String(64), ForeignKey("users.user_id"), index=True)
    q_id = Column(String(32), ForeignKey("questions.q_id"), index=True)
    kp_id = Column(String(32), index=True)

    my_answer = Column(String(128), default="")
    correct_answer = Column(String(128), default="")
    is_correct = Column(Integer, default=0)                     # 0/1
    duration_seconds = Column(Integer, default=0)
    error_type = Column(String(32), default="")

    created_at = Column(DateTime, default=datetime.utcnow)
