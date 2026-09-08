"""
将课后题库（after_class.json）幂等导入正式 questions 表。

- 来源：backend/app/data/st/st_bank/after_class.json（首次运行自动从原型目录复制）
- q_id 前缀 KHD（课后题库），如 KHD001
- 章节映射：王道小节前缀 → 课程 9 章（与 rag/chapter_map.py 一致），kp 取各章代表知识点
- 图题（graph/options_graph/has_image）整体打包进 figure_json，渲染由前端 DsFigure 完成
- 幂等：按 q_id upsert，可重复执行

执行: cd backend && python3.11 import_st_bank.py
"""
import json
import re
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(BACKEND_DIR))

from app.database import SessionLocal, init_db
from app.models.question import Question

# 相对定位：backend/app/data/st/st_bank/after_class.json
ST_BANK_DIR = BACKEND_DIR / "app" / "data" / "st" / "st_bank"
BANK_PATH = ST_BANK_DIR / "after_class.json"
PROTOTYPE_BANK = BACKEND_DIR.parent / "tmp_ST_problem_model" / "after_class.json"

COURSE_ID = "C2026DS001"

# 王道小节前缀 → 课程章（与 agent_st/rag/chapter_map.py 严格一致）
CHAPTERS = [
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


def map_chapter(section: str):
    """返回 (章号, 章名, 代表 kp_id, 默认难度)；未匹配返回 None"""
    text = str(section or "")
    for num, title, prefixes, kp, diff in CHAPTERS:
        for p in prefixes:
            if text.startswith(p):
                return num, title, kp, diff
    return None


MAPPING_PATH = BACKEND_DIR / "kp_section_mapping.json"


def load_section_kp_mapping() -> dict:
    """加载人工维护的 王道小节前缀 → KP id 列表 映射（backend/kp_section_mapping.json）"""
    if not MAPPING_PATH.exists():
        return {}
    try:
        raw = json.loads(MAPPING_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[warn] 映射文件读取失败，全部使用章级代表知识点：{exc}")
        return {}
    return {str(k): v for k, v in raw.items()
            if not k.startswith("_") and isinstance(v, list) and v}


def section_prefix_of(chapter: str) -> str:
    return str(chapter or "").split(" ")[0]


def ensure_bank_file() -> Path:
    ST_BANK_DIR.mkdir(parents=True, exist_ok=True)
    if not BANK_PATH.exists():
        if not PROTOTYPE_BANK.exists():
            raise SystemExit(f"[error] 找不到题库文件：{PROTOTYPE_BANK}")
        BANK_PATH.write_text(PROTOTYPE_BANK.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"[copy] 已从原型目录复制题库 -> {BANK_PATH.relative_to(BACKEND_DIR.parent)}")
    return BANK_PATH


def main():
    bank_path = ensure_bank_file()
    raw = json.loads(bank_path.read_text(encoding="utf-8"))
    items = [x for x in raw if isinstance(x, dict) and x.get("id") is not None]
    print(f"[bank] 共 {len(items)} 道课后题")

    init_db()  # 确保 figure_json/has_image 列已迁移
    db = SessionLocal()

    # 细粒度知识点映射：小节前缀 → KP 列表；KP 名称取自知识图谱（用于 kp_path）
    section_kp = load_section_kp_mapping()
    kp_names = {}
    if section_kp:
        from app.models.graph import GraphNode
        need = {k for kps in section_kp.values() for k in kps} | {c[3] for c in CHAPTERS}
        for kp_id, name in db.query(GraphNode.id, GraphNode.name).filter(
                GraphNode.graph_type == "knowledge", GraphNode.id.in_(need)).all():
            kp_names[kp_id] = name
        missing = need - set(kp_names)
        if missing:
            print(f"[warn] 映射中的 KP 在图谱中不存在：{sorted(missing)}（相关小节将回退章级代表知识点）")

    created = updated = skipped = 0
    try:
        for item in items:
            try:
                qid_num = int(item["id"])
            except (TypeError, ValueError):
                skipped += 1
                continue
            mapped = map_chapter(item.get("chapter"))
            if not mapped:
                skipped += 1
                print(f"  跳过无法识别章节的题 #{qid_num}: {item.get('chapter')}")
                continue
            _, title, chapter_kp, diff = mapped
            prefix = section_prefix_of(item.get("chapter"))
            # 细粒度映射优先；未维护的小节回退章级代表知识点
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
                course_id=COURSE_ID,
                kp_id=kp,
                type="single",
                difficulty=diff,
                score=5,
                status="published",
                stem=item.get("question") or "",
                options=json.dumps(options, ensure_ascii=False),
                answer=str(item.get("answer") or ""),
                analysis=item.get("analysis") or "",
                kp_path=json.dumps([title] + [kp_names[k] for k in kps], ensure_ascii=False),
                pre_kp="[]",
                post_kp="[]",
                is_key=0,
                source_ref_file="after_class.json",
                source_ref_locator="课后题库",
                figure_json=figure_json,
                has_image=has_image,
            )

            row = db.query(Question).filter(Question.q_id == q_id).first()
            if row:
                for k, v in values.items():
                    setattr(row, k, v)
                updated += 1
            else:
                db.add(Question(q_id=q_id, **values))
                created += 1
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    print(f"[done] 新增 {created} 条，更新 {updated} 条，跳过 {skipped} 条")


if __name__ == "__main__":
    main()
