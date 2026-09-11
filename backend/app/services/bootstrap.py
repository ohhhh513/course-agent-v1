"""启动引导：把 run_seed() 生成的演示库补全为正确库，使其接近基准快照。

在 init_db()+run_seed() 之后调用，依次：
  1) extend_graph_to_nine    图谱从 7 章扩展为 9 章（补 KP401-404 / KP501-502、重排章节、新增前后置）
  2) verify_resources        校验资源记录与磁盘文件的一致性（只报告，不自动处理）
  3) import_questions        从 after_class.json 导入正式题库（KHD 前缀）
  4) ensure_learning_paths   按扩展后的图谱校正学习路径（旧模板残留整体重建）
全部幂等，可每次启动调用。
"""
import json
import sqlite3
from pathlib import Path
from typing import Optional

from ..config import settings
from .resource_registry import verify_resources, open_conn

COURSE_ID = "C2026DS001"


# ---------- 1) 图谱扩展为 9 章（移植自 import_course_resources.py） ----------
_CHAPTER_UPDATE = {
    "第1章": ["KP01", "KP02"],
    "第2章": ["KP11", "KP12", "KP13", "KP14"],
    "第3章": ["KP21", "KP22", "KP23", "KP24"],
    "第6章": ["KP31", "KP32", "KP33", "KP34", "KP44"],
    "第7章": ["KP41", "KP42", "KP43", "KP51", "KP52", "KP53"],
    "第8章": ["KP61", "KP62", "KP63", "KP64"],
    "第9章": ["KP71", "KP72", "KP73"],
}
_NEW_KPS = [
    ("KP401", "串与模式匹配", "第4章", 4, 1),
    ("KP402", "BF 算法", "第4章", 2, 0),
    ("KP403", "KMP 算法与 next 数组", "第4章", 6, 1),
    ("KP404", "串的应用", "第4章", 2, 0),
    ("KP501", "数组与矩阵压缩", "第5章", 4, 1),
    ("KP502", "广义表", "第5章", 2, 1),
]
_NEW_LINKS = [
    ("KP24", "KP401"), ("KP401", "KP402"), ("KP402", "KP403"), ("KP403", "KP404"),
    ("KP404", "KP501"), ("KP12", "KP501"), ("KP501", "KP502"), ("KP502", "KP31"),
    ("KP53", "KP61"), ("KP64", "KP71"),
]


def extend_graph_to_nine(conn: sqlite3.Connection, verbose: bool = True) -> None:
    cur = conn.cursor()
    for chapter, ids in _CHAPTER_UPDATE.items():
        ph = ",".join("?" * len(ids))
        cur.execute(
            f"UPDATE graph_nodes SET chapter=? WHERE graph_type='knowledge' AND id IN ({ph})",
            (chapter, *ids),
        )
        cur.execute(
            f"UPDATE kp_details SET chapter=? WHERE kp_id IN ({ph})",
            (chapter, *ids),
        )
    for kid, name, chapter, hours, is_key in _NEW_KPS:
        cur.execute(
            """INSERT OR IGNORE INTO graph_nodes
               (id, graph_type, course_id, name, chapter, hours, difficulty, category, is_key)
               VALUES (?, 'knowledge', ?, ?, ?, ?, 3, 0, ?)""",
            (kid, COURSE_ID, name, chapter, hours, is_key),
        )
        cur.execute(
            """INSERT OR IGNORE INTO kp_details (kp_id, course_id, name, chapter, hours, summary)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (kid, COURSE_ID, name, chapter, hours, f"关于 {name} 的详细说明"),
        )
    for src, tgt in _NEW_LINKS:
        cur.execute(
            """INSERT OR IGNORE INTO graph_links (graph_type, course_id, source, target, relation)
               VALUES ('knowledge', ?, ?, ?, 'pre')""",
            (COURSE_ID, src, tgt),
        )
    conn.commit()
    if verbose:
        print("[bootstrap] 图谱已扩展为 9 章")


# ---------- 2) 题库导入（移植自 import_st_bank.py） ----------
_CHAPTERS = [
    (1, "第1章 绪论", ["1."], "KP01", 2),
    (2, "第2章 线性表", ["2."], "KP11", 3),
    (3, "第3章 栈和队列", ["3.1", "3.2", "3.3"], "KP21", 3),
    (4, "第4章 串", ["4."], "KP401", 4),
    (5, "第5章 数组和广义表", ["3.4"], "KP501", 3),
    (6, "第6章 树和二叉树", ["5."], "KP31", 4),
    (7, "第7章 图", ["6."], "KP41", 4),
    (8, "第8章 查找", ["7."], "KP61", 4),
    (9, "第9章 排序", ["8."], "KP71", 4),
]


def _map_chapter(section: str):
    text = str(section or "")
    for num, title, prefixes, kp, diff in _CHAPTERS:
        for p in prefixes:
            if text.startswith(p):
                return num, title, kp, diff
    return None


def _bank_path() -> Path:
    return settings.BASE_DIR / "data" / "st" / "st_bank" / "after_class.json"


def _ai_samples_path() -> Path:
    return settings.BASE_DIR / "data" / "st" / "st_bank" / "ai_samples.json"


def import_questions(verbose: bool = True) -> int:
    bank = _bank_path()
    if not bank.exists():
        if verbose:
            print(f"[bootstrap] 题库文件不存在，跳过: {bank}")
        return 0
    raw = json.loads(bank.read_text(encoding="utf-8"))
    items = [x for x in raw if isinstance(x, dict) and x.get("id") is not None]

    from ..database import SessionLocal, init_db
    from ..models.question import Question
    from ..models.graph import GraphNode
    init_db()
    db = SessionLocal()
    created = updated = skipped = 0
    try:
        section_kp: dict = {}
        mapping = settings.BASE_DIR.parent / "kp_section_mapping.json"
        if mapping.exists():
            try:
                m = json.loads(mapping.read_text(encoding="utf-8"))
                section_kp = {str(k): v for k, v in m.items()
                              if not k.startswith("_") and isinstance(v, list) and v}
            except Exception:
                section_kp = {}
        need = {k for kps in section_kp.values() for k in kps} | {c[3] for c in _CHAPTERS}
        kp_names = dict(db.query(GraphNode.id, GraphNode.name).filter(
            GraphNode.graph_type == "knowledge", GraphNode.id.in_(need)).all())

        for item in items:
            try:
                qid_num = int(item["id"])
            except (TypeError, ValueError):
                skipped += 1
                continue
            mapped = _map_chapter(item.get("chapter"))
            if not mapped:
                skipped += 1
                continue
            _, title, chapter_kp, diff = mapped
            prefix = str(item.get("chapter") or "").split(" ")[0]
            kps = [k for k in section_kp.get(prefix, []) if k in kp_names] or [chapter_kp]
            kp = kps[0]
            q_id = f"KHD{qid_num:03d}"
            options_src = item.get("options") or {}
            options = [
                {"key": k, "text": options_src.get(k, ""), "right": item.get("answer") == k}
                for k in ("A", "B", "C", "D")
            ]
            figure = {}
            if item.get("graph"):
                figure["graph"] = item.get("graph")
            if item.get("options_graph"):
                figure["options_graph"] = item.get("options_graph")
            has_image = bool(item.get("has_image"))
            if figure:
                figure["has_image"] = has_image
                figure_json = json.dumps(figure, ensure_ascii=False)
            else:
                figure_json = None
            values = dict(
                course_id=COURSE_ID, kp_id=kp, type="single", difficulty=diff,
                score=5, status="published", stem=item.get("question") or "",
                options=json.dumps(options, ensure_ascii=False),
                answer=str(item.get("answer") or ""), analysis=item.get("analysis") or "",
                kp_path=json.dumps([title] + [kp_names[k] for k in kps], ensure_ascii=False),
                pre_kp="[]", post_kp="[]", is_key=0,
                source_ref_file="after_class.json", source_ref_locator="课后题库",
                figure_json=figure_json, has_image=has_image,
            )
            row = db.query(Question).filter(Question.q_id == q_id).first()
            if row:
                for k, v in values.items():
                    setattr(row, k, v)
                updated += 1
            else:
                db.add(Question(q_id=q_id, **values))
                created += 1

        # 额外：AI 生成样例题（如 AI001，来自 ai_samples.json，已含完整字段）
        ai_bank = _ai_samples_path()
        if ai_bank.exists():
            for a in json.loads(ai_bank.read_text(encoding="utf-8")):
                fields = (
                    "q_id", "course_id", "kp_id", "type", "difficulty", "score", "status",
                    "stem", "options", "answer", "analysis", "kp_path", "pre_kp", "post_kp",
                    "is_key", "class_correct_rate", "avg_seconds", "error_type",
                    "source_ref_file", "source_ref_locator", "figure_json", "has_image",
                )
                values = {k: a[k] for k in fields if k in a}
                q_id = a.get("q_id")
                if not q_id:
                    continue
                row = db.query(Question).filter(Question.q_id == q_id).first()
                if row:
                    for k, v in values.items():
                        setattr(row, k, v)
                    updated += 1
                else:
                    db.add(Question(**values))
                    created += 1
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    if verbose:
        print(f"[bootstrap] 题库：新增 {created}，更新 {updated}，跳过 {skipped}")
    return created + updated


def ensure_learning_paths(verbose: bool = True) -> dict:
    """按扩展后的图谱校正学习路径（幂等）。

    必须放在 extend_graph_to_nine 之后：学习路径完全由 graph_nodes 派生，
    图谱还是 7 章时生成出来的就是缺串/数组/排序的旧路径（历史上正是这么踩的坑）。
    知识点集合与图谱不一致（旧模板残留、图谱扩章后未同步）→ 整体重建；
    一致则不动，保留 mastered_at 等既有信息。
    """
    from ..database import SessionLocal, init_db
    from ..models.user import User
    from .learning_path import sync_user

    init_db()
    db = SessionLocal()
    stats = {"created": 0, "rebuilt": 0, "ok": 0}
    try:
        students = db.query(User).filter(User.role == "student").all()
        for u in students:
            action = sync_user(db, u.user_id, COURSE_ID)
            stats[action] = stats.get(action, 0) + 1
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    if verbose:
        print(f"[bootstrap] 学习路径：新建 {stats['created']} 人，重建 {stats['rebuilt']} 人，"
              f"已一致 {stats['ok']} 人")
    return stats


def bootstrap(conn: Optional[sqlite3.Connection] = None, verbose: bool = True) -> None:
    own = conn is None
    conn = conn or open_conn()
    try:
        extend_graph_to_nine(conn, verbose=verbose)
        verify_resources(conn, verbose=verbose)
        import_questions(verbose=verbose)
        ensure_learning_paths(verbose=verbose)
    finally:
        if own:
            conn.close()
