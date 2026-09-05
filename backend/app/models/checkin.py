"""
学习打卡（登录即打卡）模型
记录学生每日登录 / 学习签到日期，用于连续天数与累计天数的统计。
主键为 (user_id, day)，保证同一天多次登录只计一次。
"""
from sqlalchemy import Column, Integer, String, Date, DateTime, ForeignKey
from datetime import datetime
from ..database import Base


class StudyCheckin(Base):
    __tablename__ = "study_checkins"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), ForeignKey("users.user_id"), index=True, nullable=False)
    day = Column(Date, nullable=False, index=True)            # 学习 / 登录日期
    kind = Column(String(16), default="login")                # login / study
    created_at = Column(DateTime, default=datetime.utcnow)
