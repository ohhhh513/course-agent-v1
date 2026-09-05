"""
预警与消息模型
"""
from sqlalchemy import Column, String, Integer, Text, DateTime, ForeignKey
from datetime import datetime
from ..database import Base


class Alert(Base):
    """预警"""
    __tablename__ = "alerts"

    alert_id = Column(String(32), primary_key=True)
    course_id = Column(String(32), ForeignKey("courses.course_id"), default="C2026DS001", index=True)
    user_id = Column(String(64), ForeignKey("users.user_id"), index=True)                 # 学生 ID
    class_id = Column(String(32), ForeignKey("classes.class_id"), index=True)

    level = Column(String(16), default="yellow")               # red/yellow/green
    type = Column(String(32), default="")                       # mastery_low/progress_lag/error_cluster

    title = Column(String(256), default="")
    desc = Column(Text, default="")
    trigger = Column(Text, default="")                          # 触发规则描述
    kp_id = Column(String(32), default="", index=True)
    kp_name = Column(String(64), default="")

    detail_json = Column(Text, default="{}")                    # JSON 详情
    suggestions_json = Column(Text, default="[]")               # JSON 建议

    status = Column(String(16), default="open")                # open/reviewed/ignored/read
    note = Column(Text, default="")                             # 教师复核备注

    created_at = Column(DateTime, default=datetime.utcnow)
    reviewed_at = Column(DateTime, nullable=True)


class Message(Base):
    """私信 / 系统通知"""
    __tablename__ = "messages"

    msg_id = Column(String(32), primary_key=True)
    user_id = Column(String(64), ForeignKey("users.user_id"), index=True)                   # 接收方
    from_user = Column(String(64), default="system")
    from_name = Column(String(64), default="系统")
    title = Column(String(256), default="")
    content = Column(Text, default="")
    read = Column(Integer, default=0)                           # 0/1
    created_at = Column(DateTime, default=datetime.utcnow)
