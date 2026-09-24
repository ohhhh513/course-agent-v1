"""学生学情指标（统一口径）。

quiz_accuracy_by_kp：每个知识点的「答题正确率」—— 按题去重，每道题只取最近一次作答。
返回 {kp_id: (正确率%, 不同题目数)}。掌握率 / 预警 / 靶向薄弱点 都基于它，保证口径一致。
"""
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models.practice import AnswerRecord


def quiz_accuracy_by_kp(db: Session, user_id: str) -> dict:
    """每知识点：(答题正确率, 不同题目数)。按题去重、取最近一次作答。"""
    latest = db.query(
        AnswerRecord.kp_id.label("kp"),
        func.max(AnswerRecord.id).label("last_id"),   # id 自增 → 最大即最近
    ).filter(
        AnswerRecord.user_id == user_id,
        AnswerRecord.kp_id.isnot(None),
    ).group_by(AnswerRecord.kp_id, AnswerRecord.q_id).subquery()
    rows = db.query(
        latest.c.kp,
        func.count(AnswerRecord.id),          # 不同题目数
        func.sum(AnswerRecord.is_correct),    # 最近一次答对的题数
    ).join(AnswerRecord, AnswerRecord.id == latest.c.last_id).group_by(latest.c.kp).all()
    out = {}
    for kp, total, correct in rows:
        if kp and total:
            out[kp] = (round((correct or 0) / total * 100, 1), total)
    return out
