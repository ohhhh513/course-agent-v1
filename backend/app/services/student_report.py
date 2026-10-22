"""学生个人 AI 学情报告入口；与教师报告共享事实口径和结构校验。"""
from sqlalchemy.orm import Session

from .ai_learning_report import build_learning_report
from .report_facts import PASS_LINE


def build_student_report(db: Session, user, course_id: str) -> dict:
    """只分析当前学生、当前课程，保留现有报告详情与归档结构。"""
    return build_learning_report(db, user, course_id, personal=True)


__all__ = ["build_student_report", "PASS_LINE"]
