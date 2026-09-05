"""
三大图谱接口：/graph/*
所有动态数值（mastery / achieve / error_rate / count）均从用户真实学习记录计算，
不使用 graph_nodes 中 seed 写死的静态 mock 值。
"""
import json
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_, func
from ..database import get_db
from ..models.graph import GraphNode, GraphLink, KpDetail, LearningPath
from ..models.practice import AnswerRecord
from ..models.question import Question
from ..models.course import Resource, ResourceProgress
from ..models.user import User
from ..middleware.auth import get_current_user, get_current_user_optional
from ..schemas.common import ok

router = APIRouter(prefix="/api/v1/graph", tags=["图谱"])


# 课程目标 → 下属知识点映射（课程结构元数据，用于从真实记录聚合目标达成度）
GOAL_KP_MAP = {
    "G0": ["KP01", "KP02", "KP11", "KP12", "KP13", "KP14", "KP21", "KP22", "KP23", "KP24",
           "KP31", "KP32", "KP33", "KP34", "KP44", "KP41", "KP42", "KP43", "KP51", "KP52", "KP53",
           "KP61", "KP62", "KP63", "KP64", "KP71", "KP72", "KP73"],
    "G1": ["KP11", "KP12", "KP13", "KP14", "KP21", "KP22", "KP23", "KP24"],
    "G1-1": ["KP11", "KP12", "KP13", "KP14"],
    "G1-2": ["KP21", "KP22", "KP23", "KP24"],
    "G2": ["KP31", "KP32", "KP33", "KP34", "KP44"],
    "G2-1": ["KP31", "KP32"],
    "G2-2": ["KP44"],
    "G2-3": ["KP34"],
    "G3": ["KP41", "KP42", "KP43", "KP51", "KP52", "KP53"],
    "G3-1": ["KP41", "KP42"],
    "G3-2": ["KP43"],
    "G3-3": ["KP51", "KP52", "KP53"],
    "G4": ["KP01", "KP02"],
    "G4-1": ["KP01", "KP02"],
}


# 节点分类配色（与前端 mock 一致）
CATEGORY_COLORS = {
    "knowledge": [
        {"name": "已掌握", "color": "#22c55e"},
        {"name": "学习中", "color": "#6366f1"},
        {"name": "待加强", "color": "#f59e0b"},
        {"name": "未开始", "color": "#64748b"},
        {"name": "薄弱预警", "color": "#ef4444"},
    ],
    "problem": [
        {"name": "驱动问题", "color": "#8b5cf6"},
        {"name": "子问题", "color": "#38bdf8"},
        {"name": "关联知识点", "color": "#6366f1"},
        {"name": "高频错题簇", "color": "#ef4444"},
    ],
    "goal": [
        {"name": "课程总目标", "color": "#8b5cf6"},
        {"name": "单元目标", "color": "#06b6d4"},
        {"name": "知识点目标", "color": "#6366f1"},
    ],
}


@router.get("")
def get_graph(
    courseId: str = Query("C2026DS001"),
    type: str = Query("knowledge"),
    userId: str = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_optional),
):
    """查询图谱数据 — 动态数值从用户真实学习记录计算"""
    uid = user.user_id if user else (userId or None)

    nodes = db.query(GraphNode).filter(
        and_(GraphNode.graph_type == type, GraphNode.course_id == courseId)
    ).all()

    links = db.query(GraphLink).filter(
        and_(GraphLink.graph_type == type, GraphLink.course_id == courseId)
    ).all()

    # ---------- 预计算：每个 knowledge 节点的真实掌握率 ----------
    # 同时融合答题正确率与资源学习进度
    kp_mastery = _mastery_for_user(uid, db) if uid else {}

    # ---------- 预计算：每个 knowledge 节点的错误统计（供 problem 图谱用） ----------
    kp_error = {}
    if uid:
        err_rows = db.query(
            AnswerRecord.kp_id,
            func.count(AnswerRecord.id),
            func.sum(AnswerRecord.is_correct),
        ).filter(
            AnswerRecord.user_id == uid,
            AnswerRecord.kp_id.isnot(None),
            AnswerRecord.is_correct == 0,
        ).group_by(AnswerRecord.kp_id).all()
        for kp_id, total_wrong, _ in err_rows:
            kp_error[kp_id] = total_wrong or 0

    # ---------- problem 图谱：构建节点到关联 knowledge 的映射 ----------
    problem_links = []
    if type == "problem":
        problem_links = db.query(GraphLink).filter(
            and_(GraphLink.graph_type == "problem", GraphLink.course_id == courseId)
        ).all()

    def _goal_achieve(goal_id: str) -> float:
        """目标达成度 = 下属知识点真实掌握率的加权平均"""
        kp_ids = GOAL_KP_MAP.get(goal_id, [])
        if not kp_ids:
            return 0
        values = [kp_mastery.get(kp_id, 0) for kp_id in kp_ids]
        return round(sum(values) / len(values), 1)

    def _problem_descendants(problem_id: str) -> set:
        """找到问题节点下属所有 map/error 关联的 knowledge 节点"""
        related = set()
        # 直接边 source=problem_id -> target=kp
        for l in problem_links:
            if l.source == problem_id and l.relation in ("map", "error"):
                related.add(l.target)
        # 递归子问题
        for l in problem_links:
            if l.source == problem_id and l.relation == "split":
                related |= _problem_descendants(l.target)
        return related

    def node_to_dict(n: GraphNode) -> dict:
        d = {
            "id": n.id,
            "name": n.name,
            "category": n.category,
        }
        # 知识图谱字段：mastery 从真实记录计算
        if type == "knowledge":
            d.update({
                "chapter": n.chapter,
                "mastery": kp_mastery.get(n.id, 0),
                "difficulty": n.difficulty,
                "isKey": bool(n.is_key),
                "hours": n.hours,
            })
        # 问题图谱字段：errorRate / count 从下属 knowledge 聚合
        elif type == "problem":
            related_kps = _problem_descendants(n.id)
            if related_kps and uid:
                total_err = sum(kp_error.get(kp, 0) for kp in related_kps)
                avg_mastery = sum(kp_mastery.get(kp, 0) for kp in related_kps) / len(related_kps)
                error_rate = round(100 - avg_mastery, 1)
            else:
                total_err = 0
                error_rate = 0
            d.update({
                "level": n.level,
                "relatedKp": n.related_kp,
                "errorRate": error_rate,
            })
            d["count"] = total_err
        # 目标图谱字段：achieve 从下属 knowledge 聚合
        elif type == "goal":
            d.update({
                "achieve": _goal_achieve(n.id),
                "weight": n.weight,
            })
        return d

    return ok({
        "graphType": type,
        "categories": CATEGORY_COLORS.get(type, CATEGORY_COLORS["knowledge"]),
        "nodes": [node_to_dict(n) for n in nodes],
        "links": [
            {"source": l.source, "target": l.target, "relation": l.relation}
            for l in links
        ],
    })


@router.get("/kp/{kp_id}")
def kp_detail(
    kp_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_optional),
):
    """知识点详情 — 动态数值从学习记录/题库/资源表实时计算"""
    uid = user.user_id if user else None

    # 课程结构信息优先读取 KpDetail；缺失则从 GraphNode 兜底
    kp = db.query(KpDetail).filter(KpDetail.kp_id == kp_id).first()
    node = db.query(GraphNode).filter(
        GraphNode.id == kp_id, GraphNode.graph_type == "knowledge"
    ).first()
    if not kp and not node:
        return ok({})

    def _parse(t, default=None):
        if not t: return default or []
        try: return json.loads(t)
        except: return default or []

    # ---------- 真实数值计算 ----------
    # 个人掌握率
    personal_mastery = 0
    if uid:
        ans = db.query(
            func.count(AnswerRecord.id),
            func.sum(AnswerRecord.is_correct),
        ).filter(
            AnswerRecord.user_id == uid,
            AnswerRecord.kp_id == kp_id,
        ).first()
        total, correct = ans or (0, 0)
        if total:
            personal_mastery = round((correct or 0) / total * 100, 1)
        else:
            lp = db.query(LearningPath.mastery).filter(
            LearningPath.user_id == uid,
            LearningPath.kp_id == kp_id,
        ).first()
        if lp and lp[0] is not None:
            personal_mastery = round(lp[0], 1)

    # 个人掌握率：融合答题正确率与资源进度
    if uid:
        personal_mastery = _mastery_for_user(uid, db).get(kp_id, personal_mastery)

    # 班级平均掌握率
    class_avg = 0
    class_rows = db.query(
        AnswerRecord.user_id,
        func.sum(AnswerRecord.is_correct),
        func.count(AnswerRecord.id),
    ).filter(
        AnswerRecord.kp_id == kp_id,
    ).group_by(AnswerRecord.user_id).all()
    if class_rows:
        user_rates = [(c or 0) / t * 100 for _, c, t in class_rows if t]
        class_avg = round(sum(user_rates) / len(user_rates), 1) if user_rates else 0

    # 完成率：从学习路径状态计算
    completion_rate = 0
    if uid:
        lp = db.query(LearningPath.status, LearningPath.progress).filter(
            LearningPath.user_id == uid,
            LearningPath.kp_id == kp_id,
        ).first()
        if lp:
            completion_rate = 100 if lp[0] == "done" else round(lp[1] or 0, 1)

    # 题库题数 + 个人错题数
    question_count = db.query(Question).filter(
        Question.kp_id == kp_id,
        Question.status == "published",
    ).count()
    wrong_count = 0
    if uid:
        wrong_count = db.query(AnswerRecord).filter(
            AnswerRecord.user_id == uid,
            AnswerRecord.kp_id == kp_id,
            AnswerRecord.is_correct == 0,
        ).count()

    # 挂载资源：精确匹配 kp_id + 同章节且未绑定具体 kp 的兜底资源
    resources = []
    if node or kp:
        chapter = (kp.chapter if kp else None) or (node.chapter if node else "")
        prog_map = {
            p.res_id: p for p in db.query(ResourceProgress).filter(
                ResourceProgress.user_id == user.user_id
            ).all()
        } if user else {}
        if chapter:
            rows = db.query(Resource).filter(
                (Resource.kp_id == kp_id) |
                ((Resource.kp_id == "") & Resource.kp.like(f"{chapter}%"))
            ).all()
        else:
            rows = db.query(Resource).filter(Resource.kp_id == kp_id).all()
        resources = [
            {
                "resId": r.res_id, "type": r.type, "title": r.title,
                "duration": r.duration, "pages": r.pages,
                "progress": prog_map[r.res_id].progress if r.res_id in prog_map else 0,
                "url": r.url or "",
            }
            for r in rows
        ]

    # ---------- 组装返回 ----------
    if kp:
        return ok({
            "kpId": kp.kp_id, "name": kp.name, "chapter": kp.chapter,
            "difficulty": kp.difficulty, "isKey": bool(kp.is_key), "hours": kp.hours,
            "summary": kp.summary,
            "completionRate": completion_rate,
            "masteryRate": personal_mastery,
            "classAvgMastery": class_avg,
            "pre": _parse(kp.pre_kp, []),
            "post": _parse(kp.post_kp, []),
            "resources": resources or _parse(kp.resources, []),
            "questionCount": question_count,
            "wrongCount": wrong_count,
            "relatedProblems": _parse(kp.related_problems, []),
        })

    # GraphNode 兜底
    return ok({
        "kpId": kp_id, "name": node.name, "chapter": node.chapter,
        "difficulty": node.difficulty, "isKey": bool(node.is_key), "hours": node.hours,
        "summary": f"关于 {node.name} 的详细说明",
        "completionRate": completion_rate,
        "masteryRate": personal_mastery,
        "classAvgMastery": class_avg,
        "pre": [], "post": [],
        "resources": resources,
        "questionCount": question_count,
        "wrongCount": wrong_count,
        "relatedProblems": [],
    })


def _mastery_from_records(user_id: str, db: Session):
    """从 answer_records 计算每个知识点的真实掌握率。"""
    ans_rows = db.query(
        AnswerRecord.kp_id,
        func.count(AnswerRecord.id),
        func.sum(AnswerRecord.is_correct),
    ).filter(
        AnswerRecord.user_id == user_id,
        AnswerRecord.kp_id.isnot(None),
    ).group_by(AnswerRecord.kp_id).all()
    return {
        kp_id: round((correct or 0) / total * 100, 1)
        for kp_id, total, correct in ans_rows if total
    }


def _resource_mastery(user_id: str, db: Session):
    """按知识点聚合用户所有挂载资源的平均进度。未开始资源按 0 计。"""
    from collections import defaultdict
    res_rows = db.query(
        Resource.kp_id,
        Resource.res_id,
    ).filter(Resource.kp_id.isnot(None)).all()
    prog_rows = db.query(
        ResourceProgress.res_id,
        ResourceProgress.progress,
    ).filter(ResourceProgress.user_id == user_id).all()
    prog_map = {r.res_id: r.progress or 0 for r in prog_rows}
    kp_res = defaultdict(list)
    for kp_id, res_id in res_rows:
        kp_res[kp_id].append(prog_map.get(res_id, 0))
    return {
        kp_id: round(sum(vals) / len(vals), 1)
        for kp_id, vals in kp_res.items() if vals
    }


def _mastery_for_user(user_id: str, db: Session):
    """按知识点聚合用户的资源学习完成率（平均值）。

    TODO: 题库导入后恢复为「答题正确率 ∪ 资源进度取大」的综合掌握率。
    当前阶段题库尚未导入，若继续使用答题记录会导致「掌握率」与资源学习
    进度脱钩，因此临时改为仅按课程资源完成情况计算，数值即「学习完成率」。
    """
    return _resource_mastery(user_id, db)


def _quiz_mastery_for_user(user_id: str, db: Session):
    """按知识点聚合用户的答题正确率（题库导入后使用）。

    当前题库尚未导入，因此该接口自然返回空或全 0；后续只需保证
    answer_records 有数据即可自动生效，无需修改此处逻辑。
    """
    return _mastery_from_records(user_id, db)


def _status_from_mastery(mastery: float) -> str:
    """仅用于资源/学习完成率的进度状态（供内部非展示用途）。"""
    if mastery >= 80:
        return "done"
    if mastery >= 50:
        return "doing"
    if mastery > 0:
        return "warn"
    return "todo"


def _status_from_quiz_mastery(quiz_mastery: float, learning_mastery: float, has_quiz: bool) -> str:
    """学习路径节点展示状态：以习题掌握率为主，资源进度为辅。

    - 资源学习完成率达到 100% 视为「已完成」（进度条绿色）。
    - 已答题（has_quiz=True）：
        >=80%  已完成
        >=50%  学习中
        <50%   待加强（含 0%，即全错）
    - 未答题：按资源学习进度判断是否有在学
        >0%    学习中
        =0%    未开始
    """
    if learning_mastery >= 100:
        return "done"
    if has_quiz:
        if quiz_mastery >= 80:
            return "done"
        if quiz_mastery >= 50:
            return "doing"
        return "warn"
    if learning_mastery > 0:
        return "doing"
    return "todo"


def _ensure_learning_path(user_id: str, course_id: str, db: Session):
    """如果当前课程没有学习路径，则从 graph_nodes 自动生成并持久化。"""
    existing = db.query(LearningPath).filter(
        LearningPath.user_id == user_id,
        LearningPath.course_id == course_id,
    ).first()
    if existing:
        return

    mastery_map = _mastery_for_user(user_id, db)
    quiz_map = _quiz_mastery_for_user(user_id, db)

    # 按章节、知识点 ID 排序取所有知识节点
    nodes = db.query(GraphNode).filter(
        and_(GraphNode.graph_type == "knowledge", GraphNode.course_id == course_id)
    ).order_by(GraphNode.chapter.asc(), GraphNode.id.asc()).all()

    # 按知识点精确统计挂载资源数（实际资源数与标记一致）
    resources = db.query(Resource).filter(
        and_(Resource.course_id == course_id, Resource.kp_id.isnot(None))
    ).all()
    res_count_by_kp = {}
    for r in resources:
        if r.kp_id:
            res_count_by_kp[r.kp_id] = res_count_by_kp.get(r.kp_id, 0) + 1

    # 按章节知识点顺序建立章节 → 节点列表
    chapter_nodes = {}
    for n in nodes:
        chapter_nodes.setdefault(n.chapter, []).append(n)

    step = 0
    has_quiz = set(quiz_map.keys())
    for chapter, c_nodes in chapter_nodes.items():
        for node in c_nodes:
            step += 1
            mastery = mastery_map.get(node.id, 0.0)
            quiz = quiz_map.get(node.id, 0.0)
            status = _status_from_quiz_mastery(quiz, mastery, node.id in has_quiz)
            lp = LearningPath(
                user_id=user_id,
                course_id=course_id,
                step=step,
                kp_id=node.id,
                name=node.name,
                chapter=node.chapter,
                status=status,
                hours=node.hours or 1,
                mastery=mastery,
                res_count=res_count_by_kp.get(node.id, 0),
                progress=mastery,
                locked=0,
                lock_reason="",
            )
            db.add(lp)
    db.commit()


@router.get("/path")
def learning_path(
    courseId: str = Query("C2026DS001"),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """当前用户的推荐学习路径（专属进度 + 掌握率）"""
    _ensure_learning_path(user.user_id, courseId, db)
    rows = db.query(LearningPath).filter(
        LearningPath.user_id == user.user_id,
        LearningPath.course_id == courseId,
    ).order_by(LearningPath.step.asc()).all()

    # 同步刷新：资源进度/答题记录变化后，已有 LP 的 mastery/status 可能已过时
    mastery_map = _mastery_for_user(user.user_id, db)
    quiz_map = _quiz_mastery_for_user(user.user_id, db)
    has_quiz = set(quiz_map.keys())
    for r in rows:
        m = mastery_map.get(r.kp_id, 0)
        q = quiz_map.get(r.kp_id, 0)
        status = _status_from_quiz_mastery(q, m, r.kp_id in has_quiz)
        if r.mastery != m or r.progress != m or r.status != status:
            r.mastery = m
            r.progress = m
            r.status = status
    db.commit()

    return ok([
        {
            "step": r.step, "kpId": r.kp_id, "name": r.name, "chapter": r.chapter,
            "status": r.status, "hours": r.hours, "mastery": r.mastery,
            "resCount": r.res_count,
            "progress": r.progress,
            "quizMastery": quiz_map.get(r.kp_id, 0),
            "quizAnswered": r.kp_id in has_quiz,
            "locked": bool(r.locked), "lockReason": r.lock_reason,
        }
        for r in rows
    ])
