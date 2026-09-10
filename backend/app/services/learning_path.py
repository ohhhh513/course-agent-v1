"""学习路径（learning_paths）的生成与校正。

学习路径是「图谱 + 资源」的派生数据，唯一事实来源是 graph_nodes，所以生成逻辑
只留这一份，供三处共用：
  - routers/graph.py     GET /graph/path      首次访问时按需生成
  - routers/student.py   资源进度上报          补齐单个知识点
  - services/bootstrap.py 启动引导            图谱扩展到 9 章后校正全量路径

历史坑：seed_data 曾用手写模板（mock_data.KP_STEPS_TEMPLATE）灌 25 条 6 章路径，
与图谱（34 个知识点 9 章）不一致，章名还写成「第3章 栈与队列」，和资源的
「第3章 栈和队列」差一个字，导致资源中心按章筛选为空。改为完全由图谱派生后，
章名、章号、知识点集合永远和资源/学情一致。
"""
from typing import Callable, Dict, List, Optional, Tuple

from sqlalchemy import and_
from sqlalchemy.orm import Session

from ..models.course import Resource
from ..models.graph import GraphNode, LearningPath

DEFAULT_COURSE_ID = "C2026DS001"

# state_of(kp_id) -> (mastery, status)；不传则一律 (0.0, "todo")，
# 由后续访问 /graph/path 时用真实答题/资源数据刷新。
StateFn = Callable[[str], Tuple[float, str]]


def graph_nodes(db: Session, course_id: str = DEFAULT_COURSE_ID) -> List[GraphNode]:
    """按「章节 → 知识点 ID」排序取全部知识节点（与前端展示顺序一致）。"""
    return db.query(GraphNode).filter(
        and_(GraphNode.graph_type == "knowledge", GraphNode.course_id == course_id)
    ).order_by(GraphNode.chapter.asc(), GraphNode.id.asc()).all()


def resource_count_map(db: Session, course_id: str = DEFAULT_COURSE_ID) -> Dict[str, int]:
    """每个知识点实际挂载的资源数。"""
    rows = db.query(Resource.kp_id).filter(
        and_(Resource.course_id == course_id, Resource.kp_id.isnot(None))
    ).all()
    counts: Dict[str, int] = {}
    for (kp_id,) in rows:
        if kp_id:
            counts[kp_id] = counts.get(kp_id, 0) + 1
    return counts


def make_row(
    user_id: str,
    course_id: str,
    step: int,
    node: GraphNode,
    res_count: int,
    state: Tuple[float, str],
) -> LearningPath:
    mastery, status = state
    return LearningPath(
        user_id=user_id,
        course_id=course_id,
        step=step,
        kp_id=node.id,
        name=node.name,
        chapter=node.chapter,
        status=status,
        hours=node.hours or 1,
        mastery=mastery,
        res_count=res_count,
        progress=mastery,
        locked=0,
        lock_reason="",
    )


def build_rows(
    db: Session,
    user_id: str,
    course_id: str = DEFAULT_COURSE_ID,
    state_of: Optional[StateFn] = None,
) -> List[LearningPath]:
    """按图谱生成该学生的完整学习路径（不写库，返回待 add 的行）。"""
    counts = resource_count_map(db, course_id)
    rows: List[LearningPath] = []
    for step, node in enumerate(graph_nodes(db, course_id), start=1):
        state = state_of(node.id) if state_of else (0.0, "todo")
        rows.append(make_row(user_id, course_id, step, node, counts.get(node.id, 0), state))
    return rows


def sync_user(
    db: Session,
    user_id: str,
    course_id: str = DEFAULT_COURSE_ID,
    state_of: Optional[StateFn] = None,
) -> str:
    """保证该学生的学习路径与当前图谱一致，返回 'ok' / 'created' / 'rebuilt'。

    - 没有记录 → 生成；
    - 知识点集合与图谱不一致（历史模板残留、图谱扩章后未同步）→ 整体重建；
    - 一致 → 不动（保留 mastered_at 等既有信息）。
    """
    nodes = graph_nodes(db, course_id)
    if not nodes:
        return "ok"

    existing = db.query(LearningPath).filter(
        LearningPath.user_id == user_id,
        LearningPath.course_id == course_id,
    ).all()

    if existing:
        if {r.kp_id for r in existing} == {n.id for n in nodes}:
            return "ok"
        for row in existing:
            db.delete(row)
        db.flush()
        action = "rebuilt"
    else:
        action = "created"

    for row in build_rows(db, user_id, course_id, state_of):
        db.add(row)
    return action
