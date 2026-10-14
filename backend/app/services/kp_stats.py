"""知识点维度的学情统计（全部真实表计算，无兜底/模拟）。

口径说明（与学生端既有实现严格一致，集中在此避免多入口漂移）：
- 掌握度：max(答题正确率[按题去重], 资源学习完成率) —— 同 graph.py 原 _mastery_for_user。
- 完成度：learning_paths（status=done → 100，否则取 progress）。
- 学习时长：Σ resource_progress.position（仅 video，秒；同资源多行取最大，
  与 routers/student.py::resource_stats 的 watchMinutes 同源，此处按知识点收窄）
  + Σ answer_records.duration_seconds（该知识点的练习作答时长）。
"""
from collections import defaultdict

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models.course import Resource, ResourceProgress
from ..models.graph import LearningPath
from ..models.practice import AnswerRecord
from ..models.user_course import UserCourse


def mastery_by_kp(db: Session, user_id: str) -> dict:
    """某用户各知识点的综合掌握率（答题正确率与资源完成率取较优）。"""
    if not user_id:
        return {}
    from .resource_progress import progress_map
    from .scoring import quiz_accuracy_by_kp

    res_rows = db.query(Resource.kp_id, Resource.res_id).filter(Resource.kp_id.isnot(None)).all()
    prog = {rid: (row.progress or 0) for rid, row in progress_map(db, user_id).items()}
    kp_res = defaultdict(list)
    for kp_id, res_id in res_rows:
        kp_res[kp_id].append(prog.get(res_id, 0))
    by_res = {k: round(sum(v) / len(v), 1) for k, v in kp_res.items() if v}
    by_quiz = {kp: acc for kp, (acc, _n) in quiz_accuracy_by_kp(db, user_id).items()}
    return {kp: max(by_res.get(kp, 0), by_quiz.get(kp, 0)) for kp in set(by_res) | set(by_quiz)}


def course_student_ids(db: Session, course_id: str):
    """课程内学生 user_id 列表（真实成员关系在 user_courses，班级维已废弃）。"""
    return [u for (u,) in db.query(UserCourse.user_id).filter(
        UserCourse.course_id == course_id,
        UserCourse.role_in_course == "student",
    ).all()]


def best_position_sum(db: Session, user_id: str, res_ids) -> int:
    """某用户在一组资源上的最佳观看位置合计（秒）；同资源多行取最大，避免重复计数。"""
    ids = [r for r in (res_ids or []) if r]
    if not user_id or not ids:
        return 0
    best = {}
    for res_id, pos in db.query(ResourceProgress.res_id, ResourceProgress.position).filter(
        ResourceProgress.user_id == user_id,
        ResourceProgress.res_id.in_(ids),
    ).all():
        best[res_id] = max(best.get(res_id, 0), int(pos or 0))
    return int(sum(best.values()))


def kp_study_seconds(db: Session, user_id: str, kp_id: str, video_res_ids) -> int:
    """个人在该知识点上的学习时长（秒）= 视频最佳观看位置 + 该 KP 作答时长。"""
    if not user_id:
        return 0
    sec = best_position_sum(db, user_id, video_res_ids)
    ans = db.query(func.coalesce(func.sum(AnswerRecord.duration_seconds), 0)).filter(
        AnswerRecord.user_id == user_id, AnswerRecord.kp_id == kp_id,
    ).scalar() or 0
    return int(sec) + int(ans)


def kp_course_stats(db: Session, course_id: str, kp_id: str, video_res_ids) -> dict:
    """课程维度该知识点的学情均值（分母 = 课程内全部学生）。

    courseStudiedCount：在该知识点上有记录（完成度或时长 > 0）的学生数，供前端注明分母。
    """
    uids = course_student_ids(db, course_id)
    n = len(uids)
    if not n:
        return {
            "courseStudentCount": 0, "courseStudiedCount": 0,
            "courseAvgCompletion": 0.0, "courseAvgMastery": 0.0, "courseAvgMinutes": 0.0,
        }

    # 完成度（learning_paths）
    comp = {}
    for uid, status, prog in db.query(
        LearningPath.user_id, LearningPath.status, LearningPath.progress,
    ).filter(
        LearningPath.course_id == course_id,
        LearningPath.kp_id == kp_id,
        LearningPath.user_id.in_(uids),
    ).all():
        comp[uid] = 100.0 if status == "done" else float(prog or 0)

    # 学习时长（秒）：视频最佳位置 + 该 KP 作答时长
    secs = {}
    ids = [r for r in (video_res_ids or []) if r]
    if ids:
        best = {}
        for uid, res_id, pos in db.query(
            ResourceProgress.user_id, ResourceProgress.res_id, ResourceProgress.position,
        ).filter(
            ResourceProgress.user_id.in_(uids),
            ResourceProgress.res_id.in_(ids),
        ).all():
            key = (uid, res_id)
            best[key] = max(best.get(key, 0), int(pos or 0))
        for (uid, _rid), pos in best.items():
            secs[uid] = secs.get(uid, 0) + pos
    for uid, dur in db.query(
        AnswerRecord.user_id, func.coalesce(func.sum(AnswerRecord.duration_seconds), 0),
    ).filter(
        AnswerRecord.user_id.in_(uids), AnswerRecord.kp_id == kp_id,
    ).group_by(AnswerRecord.user_id).all():
        secs[uid] = secs.get(uid, 0) + int(dur or 0)

    # 掌握度（与个人展示同口径）
    mastery = {}
    for u in uids:
        try:
            mastery[u] = float(mastery_by_kp(db, u).get(kp_id, 0) or 0)
        except Exception:
            mastery[u] = 0.0

    studied = sum(1 for u in uids if comp.get(u, 0) > 0 or secs.get(u, 0) > 0)
    return {
        "courseStudentCount": n,
        "courseStudiedCount": studied,
        "courseAvgCompletion": round(sum(comp.get(u, 0) for u in uids) / n, 1),
        "courseAvgMastery": round(sum(mastery.get(u, 0) for u in uids) / n, 1),
        "courseAvgMinutes": round(sum(secs.get(u, 0) for u in uids) / n / 60, 1),
    }
