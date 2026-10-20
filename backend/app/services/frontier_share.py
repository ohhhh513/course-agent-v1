"""前沿分享：复用 resources + resource_progress，不加表不加列。

type=share 的资源不进入课程资源中心。发布日期写在现有 duration 列（YYYY-MM-DD）。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from ..models.course import Resource, ResourceProgress
from ..models.user import User
from ..models.user_course import UserCourse
from .catalog_helpers import SHARE_TYPE
from .resource_progress import consolidate, progress_map

_CN_TZ = timezone(timedelta(hours=8))


def china_today() -> str:
    return datetime.now(_CN_TZ).strftime("%Y-%m-%d")


def _fmt_read_at(dt) -> str:
    if not dt:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_CN_TZ).strftime("%Y-%m-%d %H:%M")


def _next_res_id(db: Session) -> str:
    last = db.query(Resource.res_id).filter(Resource.res_id.like("R%")).order_by(Resource.res_id.desc()).first()
    n = int(last[0][1:]) + 1 if last else 1
    while db.query(Resource.res_id).filter(Resource.res_id == f"R{n:03d}").first():
        n += 1
    return f"R{n:03d}"


def _clean_url(url: str) -> str:
    text = (url or "").strip()
    parsed = urlparse(text)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("请填写以 http 或 https 开头的文章 / 公众号链接")
    if len(text) > 512:
        raise ValueError("链接过长")
    return text


def _share_query(db: Session, course_id: str):
    return db.query(Resource).filter(Resource.course_id == course_id, Resource.type == SHARE_TYPE)


def serialize(row: Resource, *, read: bool = False, read_count: int = 0, student_count: int = 0) -> dict:
    return {
        "shareId": row.res_id,
        "title": row.title,
        "source": row.source or "教师推荐",
        "url": row.url or "",
        "publishedOn": row.duration or "",
        "views": row.views or 0,
        "read": bool(read),
        "readCount": read_count,
        "studentCount": student_count,
    }


def _student_ids(db: Session, course_id: str) -> list[str]:
    rows = (
        db.query(User.user_id)
        .join(UserCourse, UserCourse.user_id == User.user_id)
        .filter(UserCourse.course_id == course_id, User.role == "student")
        .all()
    )
    return [uid for (uid,) in rows]


def list_for_student(db: Session, course_id: str, user_id: str, limit: int = 3) -> dict:
    rows = _share_query(db, course_id).all()
    rows.sort(key=lambda r: ((r.duration or ""), r.res_id), reverse=True)
    today = china_today()
    today_rows = [r for r in rows if r.duration == today]
    chosen = (today_rows or rows)[: max(1, min(limit, 6))]
    read_map = progress_map(db, user_id, [r.res_id for r in chosen])
    return {
        "today": today,
        "label": "今日更新" if today_rows else "近期更新",
        "list": [serialize(r, read=(read_map.get(r.res_id) and read_map[r.res_id].progress >= 100)) for r in chosen],
    }


def list_for_teacher(db: Session, course_id: str) -> dict:
    rows = _share_query(db, course_id).all()
    rows.sort(key=lambda r: ((r.duration or ""), r.res_id), reverse=True)
    student_ids = _student_ids(db, course_id)
    student_count = len(student_ids)
    items = []
    for r in rows:
        read_count = 0
        if student_ids:
            read_count = (
                db.query(ResourceProgress.user_id)
                .filter(
                    ResourceProgress.res_id == r.res_id,
                    ResourceProgress.user_id.in_(student_ids),
                    ResourceProgress.progress >= 100,
                )
                .distinct()
                .count()
            )
        items.append(serialize(r, read_count=read_count, student_count=student_count))
    return {"today": china_today(), "studentCount": student_count, "list": items}


def create_share(db: Session, course_id: str, title: str, source: str, url: str) -> dict:
    title = (title or "").strip()
    source = (source or "").strip()
    if not title:
        raise ValueError("请填写文章标题")
    if len(title) > 256:
        raise ValueError("标题过长")
    if len(source) > 128:
        raise ValueError("来源过长")
    row = Resource(
        res_id=_next_res_id(db),
        course_id=course_id,
        title=title,
        type=SHARE_TYPE,
        category="other",
        source=source,
        url=_clean_url(url),
        duration=china_today(),
        views=0,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return serialize(row)


def update_share(db: Session, course_id: str, share_id: str, title: str, source: str, url: str) -> dict:
    row = _share_query(db, course_id).filter(Resource.res_id == share_id).first()
    if not row:
        raise LookupError("分享不存在")
    title = (title or "").strip()
    source = (source or "").strip()
    if not title:
        raise ValueError("请填写文章标题")
    row.title = title
    row.source = source
    row.url = _clean_url(url)
    db.commit()
    db.refresh(row)
    return serialize(row)


def delete_share(db: Session, course_id: str, share_id: str) -> None:
    row = _share_query(db, course_id).filter(Resource.res_id == share_id).first()
    if not row:
        raise LookupError("分享不存在")
    db.query(ResourceProgress).filter(ResourceProgress.res_id == share_id).delete(synchronize_session=False)
    db.delete(row)
    db.commit()


def mark_read(db: Session, course_id: str, user_id: str, share_id: str) -> dict:
    row = _share_query(db, course_id).filter(Resource.res_id == share_id).first()
    if not row:
        raise LookupError("分享不存在")
    existing = progress_map(db, user_id, [share_id]).get(share_id)
    first = not existing or (existing.progress or 0) < 100
    progress = consolidate(db, user_id, share_id)
    if progress is None:
        progress = ResourceProgress(user_id=user_id, res_id=share_id)
        db.add(progress)
    progress.progress = 100
    progress.position = 1
    if first:
        row.views = (row.views or 0) + 1
    db.commit()
    return serialize(row, read=True)


def readers_of(db: Session, course_id: str, share_id: str) -> dict:
    row = _share_query(db, course_id).filter(Resource.res_id == share_id).first()
    if not row:
        raise LookupError("分享不存在")
    students = (
        db.query(User)
        .join(UserCourse, UserCourse.user_id == User.user_id)
        .filter(UserCourse.course_id == course_id, User.role == "student")
        .order_by(User.student_no, User.name)
        .all()
    )
    read_map = {}
    if students:
        for p in (
            db.query(ResourceProgress)
            .filter(
                ResourceProgress.res_id == share_id,
                ResourceProgress.user_id.in_([s.user_id for s in students]),
                ResourceProgress.progress >= 100,
            )
            .all()
        ):
            prev = read_map.get(p.user_id)
            if not prev or (p.updated_at and (not prev.updated_at or p.updated_at > prev.updated_at)):
                read_map[p.user_id] = p
    read, unread = [], []
    for s in students:
        item = {
            "userId": s.user_id,
            "name": s.name,
            "studentNo": s.student_no or "",
        }
        rec = read_map.get(s.user_id)
        if rec:
            item["readAt"] = _fmt_read_at(rec.updated_at)
            read.append(item)
        else:
            unread.append(item)
    return {
        "share": serialize(row, read_count=len(read), student_count=len(students)),
        "read": read,
        "unread": unread,
    }
