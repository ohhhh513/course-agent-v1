"""
persistence —— agent_st 对正式数据库模型的统一访问点。
集中导入避免循环依赖，也方便测试时替换。
"""
from sqlalchemy.orm import sessionmaker

from ..database import SessionLocal, engine  # noqa: F401
from ..models.ai import ChatSession, ChatMessage
from ..models.agent_st import STQuestionDraft
from ..models.graph import GraphNode, GraphLink, KpDetail
from ..models.question import Question
from ..models.course import Course
# 学情类工具（tools/analytics.py）需要：预警、答题记录、学习路径、选课关系
from ..models.alert import Alert
from ..models.practice import AnswerRecord
from ..models.graph import LearningPath
from ..models.user_course import UserCourse

__all__ = [
    "SessionLocal",
    "engine",
    "ChatSession",
    "ChatMessage",
    "STQuestionDraft",
    "GraphNode",
    "GraphLink",
    "KpDetail",
    "Question",
    "Course",
    "Alert",
    "AnswerRecord",
    "LearningPath",
    "UserCourse",
]
