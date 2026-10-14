"""课程结构查询：章（CH01-09）与知识点（KP001-026）。

唯一数据源是主库 `graph_nodes`（见 docs/主库数据规范.md）：
  - 章   ：graph_type='chapter'，id=CH0x，name=第N章 xxx
  - 知识点：graph_type='knowledge'，id=KP0xx，**chapter 列存的是章名**（不是 id）

本模块替代了原先的「王道小节」文本推断：不再从章节字符串猜归属，
而是直接以主库的结构 id 为准。查询不缓存 —— 教师随时可能改图谱，
SQLite 本地查询成本极低，正确性优先。
"""
from __future__ import annotations

from app.agent_st import persistence


def _rows(course_id: str, graph_type: str) -> list[dict]:
    GraphNode = persistence.GraphNode
    db = persistence.SessionLocal()
    try:
        q = db.query(GraphNode).filter(
            GraphNode.course_id == course_id,
            GraphNode.graph_type == graph_type,
        )
        rows = q.all()
        return [
            {
                "id": r.id,
                "name": r.name or "",
                "chapter": r.chapter or "",
                "difficulty": r.difficulty,
                "is_key": bool(r.is_key),
                "pos_x": r.pos_x,
                "pos_y": r.pos_y,
            }
            for r in rows
        ]
    finally:
        db.close()


def course_name(course_id: str) -> str:
    """课程名（用于提示词与文案；查不到时返回空串）"""
    Course = persistence.Course
    db = persistence.SessionLocal()
    try:
        row = db.query(Course).filter(Course.course_id == course_id).first()
        return (row.name or "") if row else ""
    finally:
        db.close()


def list_chapters(course_id: str) -> list[dict]:
    """该课程的章列表，按 id 排序（CH01 → CH09）"""
    rows = _rows(course_id, "chapter")
    return sorted(rows, key=lambda r: r["id"])


def list_kps(course_id: str) -> list[dict]:
    """该课程的知识点列表，按 (章名, id) 排序"""
    rows = _rows(course_id, "knowledge")
    return sorted(rows, key=lambda r: (r["chapter"], r["id"]))


def chapter_name_by_id(course_id: str, chapter_id: str) -> str:
    for ch in list_chapters(course_id):
        if ch["id"] == chapter_id:
            return ch["name"]
    return ""


def chapter_id_by_name(course_id: str, chapter_name: str) -> str:
    """章名 → 章 id。知识点表只存章名，需要 id 时走这里。"""
    target = str(chapter_name or "").strip()
    for ch in list_chapters(course_id):
        if ch["name"] == target:
            return ch["id"]
    return ""


def kp_info(course_id: str, kp_id: str) -> dict | None:
    """知识点 → {kp_id, kp_name, chapter_id, chapter_name}"""
    target = str(kp_id or "").strip()
    if not target:
        return None
    for kp in list_kps(course_id):
        if kp["id"] == target:
            return {
                "kp_id": kp["id"],
                "kp_name": kp["name"],
                "chapter_name": kp["chapter"],
                "chapter_id": chapter_id_by_name(course_id, kp["chapter"]),
            }
    return None


def kp_name(course_id: str, kp_id: str) -> str:
    info = kp_info(course_id, kp_id)
    return info["kp_name"] if info else ""


def valid_kp_ids(course_id: str) -> set[str]:
    """该课程图谱里真实存在的知识点 id 集合（用于出题发布时校验归属）"""
    return {kp["id"] for kp in list_kps(course_id)}


def kp_ids_of_chapter(course_id: str, chapter_id: str) -> list[str]:
    ch_name = chapter_name_by_id(course_id, chapter_id)
    if not ch_name:
        return []
    return [kp["id"] for kp in list_kps(course_id) if kp["chapter"] == ch_name]


def kp_catalog_text(course_id: str) -> str:
    """本课程「章 + 知识点」清单，用于注入 system prompt。

    目的是让模型看到的术语**来自数据库**（换课程自动换），
    而不是把某门课的知识点名称写死在提示词里。
    """
    if not course_id:
        return ""
    lines: list[str] = []
    for ch in list_chapters(course_id):
        kps = [kp for kp in list_kps(course_id) if kp["chapter"] == ch["name"]]
        if not kps:
            continue
        lines.append(
            f"{ch['id']} {ch['name']}：" + "、".join(f"{kp['name']}({kp['id']})" for kp in kps)
        )
    return "\n".join(lines)
