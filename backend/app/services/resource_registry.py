"""
自动检测/登记课程资源：把本地 resources/data-structures-1-9/ 幂等同步到数据库。

解决「资源放本地却检测不到，必须手动 import」的痛点。
规则（全部幂等，可每次启动调用）：
1. 删除 url 为空的占位资源（它们点不开，属死数据，如 run_seed 生成的 R101-R112）；
2. 文件夹里有、但库里没有的资源 -> 自动补登记（res_id 取 MAX+1，source='本地资源'），并生成封面；
3. 已登记的资源一律跳过，保留 res_id / views / 学习进度 / 封面；
4. remove_orphans=True 时，删除「本地资源」中文件已不存在的记录（仅在文件夹存在时执行，
   避免资源目录临时缺失导致误删）。
"""
import re
import sqlite3
from pathlib import Path
from typing import Optional, Set

from ..config import settings
from ..media_utils import (
    BASE_DIR,
    COVERS_DIR,
    guess_type,
    mp4_duration,
    pptx_pages,
    pdf_pages,
    parse_title,
    generate_cover,
)

RESOURCES_ROOT = BASE_DIR / "resources" / "data-structures-1-9"
COURSE_ID = "C2026DS001"

CHAPTER_NAMES = {
    1: "第1章 绪论", 2: "第2章 线性表", 3: "第3章 栈和队列",
    4: "第4章 串", 5: "第5章 数组和广义表", 6: "第6章 树和二叉树",
    7: "第7章 图", 8: "第8章 查找", 9: "第9章 排序",
}
CHAPTER_REP = {
    1: "KP01", 2: "KP11", 3: "KP21", 4: "KP401",
    5: "KP501", 6: "KP31", 7: "KP41", 8: "KP61", 9: "KP71",
}
CHAPTER_OF_KP = {
    "KP01": 1, "KP02": 1,
    "KP11": 2, "KP12": 2, "KP13": 2, "KP14": 2,
    "KP21": 3, "KP22": 3, "KP23": 3, "KP24": 3,
    "KP401": 4, "KP402": 4, "KP403": 4, "KP404": 4,
    "KP501": 5, "KP502": 5,
    "KP31": 6, "KP32": 6, "KP33": 6, "KP34": 6, "KP44": 6,
    "KP41": 7, "KP42": 7, "KP43": 7, "KP51": 7, "KP52": 7, "KP53": 7,
    "KP61": 8, "KP62": 8, "KP63": 8, "KP64": 8,
    "KP71": 9, "KP72": 9, "KP73": 9,
}
KP_KEYWORDS = {
    "KP01": ["绪论", "为什么学数据结构", "数据元素", "逻辑结构", "存储结构", "ADT"],
    "KP02": ["复杂度", "时间复杂度", "空间复杂度", "大O", "渐进分析", "算法复杂度"],
    "KP11": ["线性表定义", "线性表", "一元多项式", "有序表合并", "线性表应用"],
    "KP12": ["顺序表", "顺序存储", "插入", "删除", "查找", "溢出", "顺序表VS链表", "顺序表插入删除"],
    "KP13": ["单链表", "头插", "尾插", "遍历", "链式存储", "反转"],
    "KP14": ["双链表", "循环链表", "双向链表"],
    "KP21": ["栈的定义", "栈的实现", "顺序栈", "链栈"],
    "KP22": ["队列", "链队列", "双端队列"],
    "KP23": ["循环队列", "判空", "判满"],
    "KP24": ["栈的应用", "表达式求值", "后缀", "递归", "栈帧", "括号匹配", "数制转换"],
    "KP401": ["串", "模式匹配", "串的定义", "串的存储"],
    "KP402": ["BF", "Brute-Force"],
    "KP403": ["KMP", "next数组"],
    "KP404": ["串的应用"],
    "KP501": ["数组", "矩阵", "压缩", "稀疏矩阵", "三元组", "十字链表"],
    "KP502": ["广义表", "头尾表示"],
    "KP31": ["二叉树基本概念", "树与二叉树", "二叉树性质", "术语"],
    "KP32": ["二叉树遍历", "二叉树递归遍历", "递归遍历", "先序", "中序", "后序", "层次遍历", "重建", "由遍历序列"],
    "KP33": ["线索二叉树", "线索化"],
    "KP34": ["树与森林", "树森林", "转换"],
    "KP44": ["哈夫曼", "哈夫曼树", "哈夫曼编码"],
    "KP41": ["图的定义", "图的术语"],
    "KP42": ["图的存储", "邻接矩阵", "邻接表"],
    "KP43": ["图的遍历", "DFS", "BFS"],
    "KP51": ["最小生成树", "Prim", "Kruskal"],
    "KP52": ["最短路径", "Dijkstra", "Floyd"],
    "KP53": ["拓扑排序", "关键路径"],
    "KP61": ["查找", "查找概念", "ASL", "顺序查找", "折半查找", "分块", "静态与动态查找"],
    "KP62": ["二分查找", "折半"],
    "KP63": ["二叉排序树", "AVL", "平衡树", "AVL树旋转", "B树", "B+树"],
    "KP64": ["哈希表", "哈希", "冲突", "开放定址", "链地址"],
    "KP71": ["插入排序", "交换排序", "冒泡排序", "希尔排序", "八大排序"],
    "KP72": ["快速排序", "partition"],
    "KP73": ["堆排序", "归并排序", "基数排序"],
}


def _db_path() -> Path:
    url = settings.DATABASE_URL
    if url.startswith("sqlite:///"):
        return Path(url[len("sqlite:///"):])
    return settings.BASE_DIR / "data" / "course_agent.db"


def open_conn() -> sqlite3.Connection:
    return sqlite3.connect(str(_db_path()))


def _extract_chapter(filename: str) -> int:
    m = re.search(r"Ch(\d{2})", filename)
    return int(m.group(1)) if m else 0


def _decide_kp_id(title: str, chapter: int) -> str:
    t = title.lower()
    best_kp, best_score = "", 0
    for kp, kws in KP_KEYWORDS.items():
        if CHAPTER_OF_KP.get(kp) != chapter:
            continue
        score = sum(len(kw) for kw in kws if kw.lower() in t)
        if score > best_score:
            best_score, best_kp = score, kp
    return best_kp if best_kp and best_score > 0 else CHAPTER_REP.get(chapter, "")


def _resource_url(rel: Path) -> str:
    return "/assets/resources/data-structures-1-9/" + "/".join(rel.parts)


def _next_res_id(cur: sqlite3.Cursor) -> str:
    row = cur.execute("SELECT MAX(res_id) FROM resources WHERE res_id LIKE 'R%'").fetchone()
    if not row or not row[0]:
        return "R001"
    return f"R{int(str(row[0])[1:]) + 1:03d}"


def _params(path: Path, rtype: str):
    if rtype == "video":
        return mp4_duration(path), 0
    if rtype == "ppt":
        return "", pptx_pages(path)
    if rtype == "doc":
        return "", pdf_pages(path)
    return "", 0


def sync_resources_from_folder(
    conn: sqlite3.Connection,
    source_dir: Optional[Path] = None,
    *,
    remove_orphans: bool = True,
    verbose: bool = True,
) -> int:
    """幂等同步：补录新增资源；可选删除已失效记录。返回新增资源数。"""
    root = (source_dir or RESOURCES_ROOT).resolve()
    if not root.is_dir():
        if verbose:
            print(f"[resource-sync] 资源目录不存在，跳过: {root}")
        return 0

    cur = conn.cursor()

    dead = cur.execute("SELECT COUNT(*) FROM resources WHERE url IS NULL OR url=''").fetchone()[0]
    if dead:
        cur.execute("DELETE FROM resources WHERE url IS NULL OR url=''")
        if verbose:
            print(f"[resource-sync] 清理 {dead} 条 url 为空的占位资源")

    existing: Set[str] = {
        r[0] for r in cur.execute("SELECT url FROM resources WHERE url IS NOT NULL AND url<>''")
    }

    added = 0
    # 与基准快照一致的 id 顺序：先视频、再课件PPT、再教材（避免按路径字母序导致 R001=PPT 的错位）
    for sub in ("videos", "slides", "textbooks"):
        subdir = root / sub
        if not subdir.is_dir():
            continue
        for src in sorted(p for p in subdir.iterdir() if p.is_file()):
            rtype, _ = guess_type(src.name)
            if not rtype:
                continue
            chapter = _extract_chapter(src.name)
            if chapter == 0 or chapter not in CHAPTER_NAMES:
                continue
            rel = src.relative_to(root)
            url = _resource_url(rel)
            if url in existing:
                continue
            title = parse_title(src.name)
            if src.name.startswith("DOC_"):
                title = f"数据结构第{chapter}章"
            kp_id = "" if src.name.startswith("DOC_") else _decide_kp_id(title, chapter)
            category = "knowledge" if kp_id else "other"
            duration, pages = _params(src, rtype)
            res_id = _next_res_id(cur)
            cur.execute(
                """INSERT INTO resources
                   (res_id, course_id, title, type, kp, kp_id, category,
                    duration, pages, count, source, views, url)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, '本地资源', 0, ?)""",
                (res_id, COURSE_ID, title, rtype, CHAPTER_NAMES[chapter], kp_id,
                 category, duration, pages, url),
            )
            generate_cover(res_id, title, rtype)
            existing.add(url)
            added += 1
            if verbose:
                print(f"  [resource-sync] +{res_id} {rtype:5} {CHAPTER_NAMES[chapter]} "
                      f"{kp_id or '(章节级)':8} {title[:36]}")

    if remove_orphans:
        prefix = "/assets/resources/data-structures-1-9/"
        for res_id, url in cur.execute(
            "SELECT res_id, url FROM resources WHERE source='本地资源' AND url LIKE ?",
            (prefix + "%",),
        ).fetchall():
            if not (root / url.replace(prefix, "", 1)).exists():
                cur.execute("DELETE FROM resources WHERE res_id=?", (res_id,))
                cover = COVERS_DIR / f"{res_id}.jpg"
                if cover.exists():
                    cover.unlink()
                if verbose:
                    print(f"  [resource-sync] -{res_id} 文件已移除，删除登记")

    conn.commit()
    if verbose:
        print(f"[resource-sync] 新增 {added} 个资源")
    return added
