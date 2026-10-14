"""`resource_progress` 的规范读取与去重。

历史坑：`resource_progress` 表**没有 (user_id, res_id) 唯一约束**，而写入是「先查后插」。
学生在播放器里可能同时触发多次上报（就绪时 `save(true)` + `timeupdate` + `pause`/`seeked`），
两个请求都查不到记录就会各自插入一行，同一资源留下多行。后果：
  - 列表/卡片把行装进 `{res_id: row}` 字典，后一行覆盖前一行 → 可能只显示 0%；
  - 知识点掌握率取到 0 那一行 → 资源完成率被低估；
  - 驾驶舱最近动态里同一资源出现两条。
统一约定：**读用 `progress_map()`**（同一资源只取最优行），**写用 `consolidate()`**（合并成一行）。
"""
from datetime import datetime
from typing import Dict, Iterable, List, Optional

from sqlalchemy.orm import Session

from ..models.course import ResourceProgress

_EPOCH = datetime.min


def row_key(row: ResourceProgress):
    """同一资源的取优排序键：先比进度、再比记录点，最后比更新时间。"""
    return ((row.progress or 0), (row.position or 0), row.updated_at or _EPOCH)


def progress_map(
    db: Session,
    user_id: str,
    res_ids: Optional[Iterable[str]] = None,
) -> Dict[str, ResourceProgress]:
    """{res_id: 最优行}；同一资源存在重复行时只保留数据最优的那行。"""
    q = db.query(ResourceProgress).filter(ResourceProgress.user_id == user_id)
    if res_ids is not None:
        ids: List[str] = [r for r in res_ids if r]
        if not ids:
            return {}
        q = q.filter(ResourceProgress.res_id.in_(ids))
    out: Dict[str, ResourceProgress] = {}
    for row in q.all():
        cur = out.get(row.res_id)
        if cur is None or row_key(row) > row_key(cur):
            out[row.res_id] = row
    return out


def consolidate(db: Session, user_id: str, res_id: str) -> Optional[ResourceProgress]:
    """把 (user_id, res_id) 的重复行合并为一行（进度/记录点取最大），返回保留的行。

    没有记录时返回 None，由调用方新建（保持原有「不存在则创建」语义）。
    """
    rows = (
        db.query(ResourceProgress)
        .filter(
            ResourceProgress.user_id == user_id,
            ResourceProgress.res_id == res_id,
        )
        .order_by(ResourceProgress.id.asc())
        .all()
    )
    if not rows:
        return None
    keep = max(rows, key=row_key)
    progress = max((r.progress or 0) for r in rows)
    position = max((r.position or 0) for r in rows)
    updated = max((r.updated_at or _EPOCH) for r in rows)
    for r in rows:
        if r is not keep:
            db.delete(r)
    keep.progress = progress
    keep.position = position
    if updated != _EPOCH:
        keep.updated_at = updated
    db.flush()
    return keep
