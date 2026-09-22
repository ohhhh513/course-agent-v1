"""章节目录与 KP 标签公共辅助"""
import json
from sqlalchemy.orm import Session


def parse_kp_ids(raw) -> list[str]:
    if raw is None or raw == "":
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            raw = [x.strip() for x in raw.split(",") if x.strip()]
    if not isinstance(raw, list):
        return []
    out, seen = [], set()
    for x in raw:
        s = str(x or "").strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def kp_name_map(db: Session, course_id: str | None = None) -> dict:
    from ..models.graph import GraphNode
    q = db.query(GraphNode).filter(GraphNode.graph_type == "knowledge")
    if course_id:
        q = q.filter(GraphNode.course_id == course_id)
    return {n.id: n.name for n in q.all()}


def resolve_kp_labels(db: Session, kp_ids: list[str], name_map: dict | None = None) -> list[dict]:
    if name_map is None:
        name_map = kp_name_map(db)
    return [{"kpId": i, "name": name_map.get(i, i)} for i in kp_ids]


def resource_kp_ids(r) -> list[str]:
    ids = parse_kp_ids(getattr(r, "kp_ids", None))
    primary = (getattr(r, "kp_id", "") or "").strip()
    if primary and primary not in ids:
        ids.insert(0, primary)
    return ids


def resource_hits_kp(r, kp_id: str | None) -> bool:
    """资源是否与某知识点相关：主挂载点 kp_id 或 kp_ids 多标签任一命中。

    必须与「学习路径 N 个资源」的统计口径（learning_path.resource_count_map）
    保持同源，否则会出现「左侧标记 6 个资源、点进去只有 4 个」——
    被别的知识点主挂载、只在 kp_ids 里带上本知识点的资源会被过滤掉。
    """
    if not kp_id:
        return False
    return kp_id in resource_kp_ids(r)


def filter_resources_by_kp(rows, kp_id: str | None) -> list:
    """按知识点过滤资源列表（主挂载 + 多标签，去重后每资源只出现一次）。"""
    if not kp_id:
        return list(rows)
    return [r for r in rows if resource_hits_kp(r, kp_id)]


def question_kp_ids(q) -> list[str]:
    ids = parse_kp_ids(getattr(q, "kp_ids", None))
    primary = (getattr(q, "kp_id", "") or "").strip()
    if primary and primary not in ids:
        ids.insert(0, primary)
    return ids
