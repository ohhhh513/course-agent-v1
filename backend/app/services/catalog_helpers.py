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


def question_kp_ids(q) -> list[str]:
    ids = parse_kp_ids(getattr(q, "kp_ids", None))
    primary = (getattr(q, "kp_id", "") or "").strip()
    if primary and primary not in ids:
        ids.insert(0, primary)
    return ids
