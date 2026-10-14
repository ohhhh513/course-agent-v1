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
from ..models.course import Course, Resource
# 学情类工具（tools/analytics.py）需要：预警、答题记录、学习路径、选课关系
from ..models.alert import Alert, Message
from ..models.practice import AnswerRecord
from ..models.graph import LearningPath
from ..models.user_course import UserCourse
# 教师视角工具（tools/teacher_analytics.py）需要学生姓名 / 学号
from ..models.user import User
# 平台治理工具（tools/admin_ops.py）需要学情报告归档
from ..models.intervention import Report

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
    "Resource",
    "Alert",
    "Message",
    "AnswerRecord",
    "LearningPath",
    "UserCourse",
    "User",
    "Report",
]
