"""
课程标签服务：列表/按名创建/覆盖式挂载资源与题目
"""
import uuid
from sqlalchemy.orm import Session

from ..models.tag import Tag, ResourceTagLink, QuestionTagLink


def _gen_tag_id(db: Session) -> str:
    while True:
        tid = "T" + uuid.uuid4().hex[:8].upper()
        if not db.query(Tag).filter(Tag.tag_id == tid).first():
            return tid


def list_tags(db: Session, course_id: str) -> list[dict]:
    rows = (
        db.query(Tag)
        .filter(Tag.course_id == course_id)
        .order_by(Tag.name.asc())
        .all()
    )
    return [{"tagId": t.tag_id, "name": t.name} for t in rows]


def ensure_tag(db: Session, course_id: str, name: str) -> Tag | None:
    """按名获取或创建课程标签；空名返回 None"""
    name = (name or "").strip()
    if not name:
        return None
    row = db.query(Tag).filter(Tag.course_id == course_id, Tag.name == name).first()
    if row:
        return row
    row = Tag(tag_id=_gen_tag_id(db), course_id=course_id, name=name)
    db.add(row)
    db.flush()
    return row


def _clean_tag_ids(db: Session, course_id: str, tag_ids: list | None) -> list[str]:
    """过滤并校验标签均属当前课程；非法 id 静默丢弃（调用方可先 ensure）"""
    ids: list[str] = []
    seen = set()
    for raw in (tag_ids or []):
        tid = str(raw or "").strip()
        if not tid or tid in seen:
            continue
        seen.add(tid)
        ok = db.query(Tag).filter(Tag.tag_id == tid, Tag.course_id == course_id).first()
        if ok:
            ids.append(tid)
    return ids


def get_resource_tags(db: Session, res_id: str) -> list[dict]:
    rows = (
        db.query(Tag)
        .join(ResourceTagLink, ResourceTagLink.tag_id == Tag.tag_id)
        .filter(ResourceTagLink.res_id == res_id)
        .order_by(Tag.name.asc())
        .all()
    )
    return [{"tagId": t.tag_id, "name": t.name} for t in rows]


def get_question_tags(db: Session, q_id: str) -> list[dict]:
    rows = (
        db.query(Tag)
        .join(QuestionTagLink, QuestionTagLink.tag_id == Tag.tag_id)
        .filter(QuestionTagLink.q_id == q_id)
        .order_by(Tag.name.asc())
        .all()
    )
    return [{"tagId": t.tag_id, "name": t.name} for t in rows]


def set_resource_tags(db: Session, res_id: str, tag_ids: list | None) -> list[str]:
    ids = _clean_tag_ids(db, _course_of_resource(db, res_id) or "", tag_ids) if res_id else []
    # 若 course 未知则仍按传入过滤（需 course 时由调用方先校验）
    db.query(ResourceTagLink).filter(ResourceTagLink.res_id == res_id).delete(synchronize_session=False)
    for tid in ids:
        db.add(ResourceTagLink(res_id=res_id, tag_id=tid))
    return ids


def set_question_tags(db: Session, q_id: str, tag_ids: list | None, course_id: str | None = None) -> list[str]:
    if course_id is None:
        course_id = _course_of_question(db, q_id) or ""
    ids = _clean_tag_ids(db, course_id, tag_ids)
    db.query(QuestionTagLink).filter(QuestionTagLink.q_id == q_id).delete(synchronize_session=False)
    for tid in ids:
        db.add(QuestionTagLink(q_id=q_id, tag_id=tid))
    return ids


def set_resource_tags_in_course(db: Session, res_id: str, course_id: str, tag_ids: list | None) -> list[str]:
    ids = _clean_tag_ids(db, course_id, tag_ids)
    db.query(ResourceTagLink).filter(ResourceTagLink.res_id == res_id).delete(synchronize_session=False)
    for tid in ids:
        db.add(ResourceTagLink(res_id=res_id, tag_id=tid))
    return ids


def ensure_tags_by_ids_or_names(
    db: Session, course_id: str, tag_ids=None, names=None
) -> list[str]:
    """返回可挂载的 tag_id 列表：先校验 id，再按名 ensure"""
    ids = _clean_tag_ids(db, course_id, tag_ids)
    for n in (names or []):
        t = ensure_tag(db, course_id, str(n or ""))
        if t and t.tag_id not in ids:
            ids.append(t.tag_id)
    return ids


def delete_tag(db: Session, course_id: str, tag_id: str) -> bool:
    row = db.query(Tag).filter(Tag.tag_id == tag_id, Tag.course_id == course_id).first()
    if not row:
        return False
    db.query(ResourceTagLink).filter(ResourceTagLink.tag_id == tag_id).delete(synchronize_session=False)
    db.query(QuestionTagLink).filter(QuestionTagLink.tag_id == tag_id).delete(synchronize_session=False)
    db.delete(row)
    return True


def _course_of_resource(db: Session, res_id: str) -> str | None:
    from ..models.course import Resource
    r = db.query(Resource.course_id).filter(Resource.res_id == res_id).first()
    return r[0] if r else None


def _course_of_question(db: Session, q_id: str) -> str | None:
    from ..models.question import Question
    r = db.query(Question.course_id).filter(Question.q_id == q_id).first()
    return r[0] if r else None
