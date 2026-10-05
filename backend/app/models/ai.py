"""
AI 会话模型
"""
from sqlalchemy import Column, String, Integer, Text, DateTime, ForeignKey
from datetime import datetime
from ..database import Base


class ChatSession(Base):
    """AI 答疑会话"""
    __tablename__ = "chat_sessions"

    session_id = Column(String(32), primary_key=True)          # CH...
    user_id = Column(String(64), ForeignKey("users.user_id"), index=True)
    # 课程隔离：由写入方（AgentStore / 业务路由）显式提供。
    # 这里**不给默认值** —— 历史默认值 'C2026DS001' 会让漏传课程的写入
    # 静默落到演示课，而列表查询按真实课程过滤，于是会话「写了但查不到」。
    course_id = Column(String(32), ForeignKey("courses.course_id"), index=True)
    title = Column(String(256), default="")
    kp_name = Column(String(64), default="")
    flow_id = Column(String(16), default="explain")            # explain / generate_items
    rounds = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ChatMessage(Base):
    """会话消息"""
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(32), ForeignKey("chat_sessions.session_id"), index=True)
    role = Column(String(16))                                    # ai / me
    method = Column(String(16), default="")                      # 教学法
    content = Column(Text, default="")
    citations = Column(Text, default="[]")                       # JSON
    tool_log = Column(Text, default="[]")                        # JSON 工具调用日志（agent_st）
    draft_id = Column(String(32), default="")                    # 关联的出题草稿（如有）
    time_str = Column(String(32), default="")                    # 14:21
    created_at = Column(DateTime, default=datetime.utcnow)


class AiFeedback(Base):
    """AI 回答的点赞/点踩反馈（真实落库，供知识库与回答质量迭代使用）。"""
    __tablename__ = "ai_feedback"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # 回答标识：流式回答取 SSE meta 的 messageId（MSG…），
    # 历史消息取接口下发的稳定 id（M+chat_messages 行号）。仅作关联标识，不做外键。
    message_id = Column(String(64), index=True)
    session_id = Column(String(32), index=True)
    user_id = Column(String(64), ForeignKey("users.user_id"), index=True)
    # 课程隔离：由写入方显式提供（get_current_course_id，含成员校验），不给默认值
    course_id = Column(String(32), ForeignKey("courses.course_id"), index=True)
    feedback = Column(Integer, default=1)                        # 1=点赞 -1=点踩
    created_at = Column(DateTime, default=datetime.utcnow)
