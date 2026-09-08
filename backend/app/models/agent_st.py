"""
智能体（agent_st）模型：智能出题草稿
草稿仅按 user_id 归属个人会话历史，绝不自动写入 questions 正式题库。
"""
from sqlalchemy import Column, String, Text, DateTime
from datetime import datetime
from ..database import Base


class STQuestionDraft(Base):
    """AI 生成题目草稿（教师个人）"""
    __tablename__ = "st_question_drafts"

    draft_id = Column(String(32), primary_key=True)            # QD...
    user_id = Column(String(64), index=True)                   # 生成者
    batch_id = Column(String(32), default="", index=True)      # 一次生成批次
    payload_json = Column(Text, default="{}")                  # 原型题 JSON（含 graph/options_graph/has_image）
    status = Column(String(16), default="draft")               # draft / invalid
    errors_json = Column(Text, default="[]")                   # 校验错误 JSON
    created_at = Column(DateTime, default=datetime.utcnow)
