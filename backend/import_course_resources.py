"""
将课程资源（位于项目内的 assets/resources/data-structures-1-9/）导入系统，
并把知识图谱扩展为 9 章结构（匹配严蔚敏《数据结构》体系），同时完成资源挂靠。

执行: cd backend && python3.12 import_course_resources.py
说明: SOURCE_DIR / TARGET_DIR 均相对项目根目录解析，不再写死本机绝对路径。
"""
import os
import re
import sys
import sqlite3
import shutil
from pathlib import Path

# 将 backend 目录加入路径，以便导入 media_utils
BACKEND_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(BACKEND_DIR))

from app.media_utils import (
    BASE_DIR, COVERS_DIR, guess_type, mp4_duration,
    pptx_pages, pdf_pages, parse_title, generate_cover,
)

DB_PATH = BACKEND_DIR / "app" / "data" / "course_agent.db"
# 相对项目根目录（course-agent）解析，避免依赖本机绝对路径
SOURCE_DIR = BASE_DIR / "assets" / "resources" / "data-structures-1-9"
TARGET_DIR = BASE_DIR / "assets" / "resources" / "data-structures-1-9"
COURSE_ID = "C2026DS001"

# 9 章名称（与清单一致）
CHAPTER_NAMES = {
    1: "第1章 绪论",
    2: "第2章 线性表",
    3: "第3章 栈和队列",
    4: "第4章 串",
    5: "第5章 数组和广义表",
    6: "第6章 树和二叉树",
    7: "第7章 图",
    8: "第8章 查找",
    9: "第9章 排序",
}

# 每章代表知识点（无关键词命中时兜底）
CHAPTER_REP = {
    1: "KP01", 2: "KP11", 3: "KP21", 4: "KP401",
    5: "KP501", 6: "KP31", 7: "KP41", 8: "KP61", 9: "KP71",
}

# 知识点所属章节（用于限定匹配范围，杜绝跨章误挂）
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

# 知识点关键词映射（用于把资源标题匹配到最合适知识点）
KP_KEYWORDS = {
    # 第1章 绪论
    "KP01": ["绪论", "为什么学数据结构", "数据元素", "逻辑结构", "存储结构", "ADT"],
    "KP02": ["复杂度", "时间复杂度", "空间复杂度", "大O", "渐进分析", "算法复杂度"],
    # 第2章 线性表
    "KP11": ["线性表定义", "线性表", "一元多项式", "有序表合并", "线性表应用"],
    "KP12": ["顺序表", "顺序存储", "插入", "删除", "查找", "溢出", "顺序表VS链表", "顺序表插入删除"],
    "KP13": ["单链表", "头插", "尾插", "遍历", "链式存储", "反转"],
    "KP14": ["双链表", "循环链表", "双向链表"],
    # 第3章 栈和队列
    "KP21": ["栈的定义", "栈的实现", "顺序栈", "链栈"],
    "KP22": ["队列", "链队列", "双端队列"],
    "KP23": ["循环队列", "判空", "判满"],
    "KP24": ["栈的应用", "表达式求值", "后缀", "递归", "栈帧", "括号匹配", "数制转换"],
    # 第4章 串（新增）
    "KP401": ["串", "模式匹配", "串的定义", "串的存储"],
    "KP402": ["BF", "Brute-Force"],
    "KP403": ["KMP", "next数组"],
    "KP404": ["串的应用"],
    # 第5章 数组和广义表（新增）
    "KP501": ["数组", "矩阵", "压缩", "稀疏矩阵", "三元组", "十字链表"],
    "KP502": ["广义表", "头尾表示"],
    # 第6章 树和二叉树
    "KP31": ["二叉树基本概念", "树与二叉树", "二叉树性质", "术语"],
    "KP32": ["二叉树遍历", "二叉树递归遍历", "递归遍历", "先序", "中序", "后序", "层次遍历", "重建", "由遍历序列"],
    "KP33": ["线索二叉树", "线索化"],
    "KP34": ["树与森林", "树森林", "转换"],
    "KP44": ["哈夫曼", "哈夫曼树", "哈夫曼编码"],
    # 第7章 图
    "KP41": ["图的定义", "图的术语"],
    "KP42": ["图的存储", "邻接矩阵", "邻接表"],
    "KP43": ["图的遍历", "DFS", "BFS"],
    "KP51": ["最小生成树", "Prim", "Kruskal"],
    "KP52": ["最短路径", "Dijkstra", "Floyd"],
    "KP53": ["拓扑排序", "关键路径"],
    # 第8章 查找
    "KP61": ["查找", "查找概念", "ASL", "顺序查找", "折半查找", "分块", "静态与动态查找"],
    "KP62": ["二分查找", "折半"],
    "KP63": ["二叉排序树", "AVL", "平衡树", "AVL树旋转", "B树", "B+树"],
    "KP64": ["哈希表", "哈希", "冲突", "开放定址", "链地址"],
    # 第9章 排序
    "KP71": ["插入排序", "交换排序", "冒泡排序", "希尔排序", "八大排序"],
    "KP72": ["快速排序", "partition"],
    "KP73": ["堆排序", "归并排序", "基数排序"],
}


def backup_db():
    bak = DB_PATH.with_suffix(f".db.bak.{__import__('datetime').datetime.now().strftime('%Y%m%d_%H%M%S')}")
    shutil.copy2(DB_PATH, bak)
    print(f"[backup] 数据库已备份到 {bak.name}")


def ensure_dirs():
    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    COVERS_DIR.mkdir(parents=True, exist_ok=True)


def delete_existing_local_resources(cur, con):
    """删除旧的 source='本地资源' 资源、文件、封面、学习进度"""
    cur.execute("SELECT res_id, url FROM resources WHERE source='本地资源'")
    rows = cur.fetchall()
    if not rows:
        print("[clean] 没有旧本地资源需要清理")
        return

    for res_id, url in rows:
        # 删文件
        if url:
            p = BASE_DIR / url.lstrip("/")
            try:
                if p.exists():
                    p.unlink()
                d = p.parent
                if d.exists() and not any(d.iterdir()):
                    d.rmdir()
            except Exception as e:
                print(f"  删文件失败 {res_id}: {e}")
        # 删封面
        c = COVERS_DIR / f"{res_id}.jpg"
        try:
            if c.exists():
                c.unlink()
        except Exception as e:
            print(f"  删封面失败 {res_id}: {e}")

    res_ids = [r[0] for r in rows]
    # 级联删除学习进度
    cur.execute(
        f"DELETE FROM resource_progress WHERE res_id IN ({','.join('?'*len(res_ids))})",
        res_ids,
    )
    cur.execute(
        f"DELETE FROM resources WHERE res_id IN ({','.join('?'*len(res_ids))})",
        res_ids,
    )
    con.commit()
    print(f"[clean] 已清理旧本地资源 {len(rows)} 条及其进度、文件、封面")


def update_graph_structure(cur, con):
    """把知识图谱从 7 章扩展为 9 章，并新增第4、5章知识点"""
    # 更新现有知识点章节号
    chapter_updates = {
        "第1章": ["KP01", "KP02"],
        "第2章": ["KP11", "KP12", "KP13", "KP14"],
        "第3章": ["KP21", "KP22", "KP23", "KP24"],
        "第6章": ["KP31", "KP32", "KP33", "KP34", "KP44"],
        "第7章": ["KP41", "KP42", "KP43", "KP51", "KP52", "KP53"],
        "第8章": ["KP61", "KP62", "KP63", "KP64"],
        "第9章": ["KP71", "KP72", "KP73"],
    }
    for chapter, ids in chapter_updates.items():
        cur.execute(
            f"UPDATE graph_nodes SET chapter=? WHERE graph_type='knowledge' AND id IN ({','.join('?'*len(ids))})",
            (chapter, *ids),
        )
        # 同步 kp_details（虽然现有只有一条，但保持一致）
        cur.execute(
            f"UPDATE kp_details SET chapter=? WHERE kp_id IN ({','.join('?'*len(ids))})",
            (chapter, *ids),
        )

    # 新增知识点（核心节点设为重难点，便于在图谱重难点清单中展示）
    new_kps = [
        ("KP401", "串与模式匹配", "第4章", 4, 1),
        ("KP402", "BF 算法", "第4章", 2, 0),
        ("KP403", "KMP 算法与 next 数组", "第4章", 6, 1),
        ("KP404", "串的应用", "第4章", 2, 0),
        ("KP501", "数组与矩阵压缩", "第5章", 4, 1),
        ("KP502", "广义表", "第5章", 2, 1),
    ]
    for kid, name, chapter, hours, is_key in new_kps:
        cur.execute("""
            INSERT OR IGNORE INTO graph_nodes (id, graph_type, course_id, name, chapter, hours, difficulty, category, is_key)
            VALUES (?, 'knowledge', ?, ?, ?, ?, 3, 0, ?)
        """, (kid, COURSE_ID, name, chapter, hours, is_key))
        cur.execute("""
            INSERT OR IGNORE INTO kp_details (kp_id, course_id, name, chapter, hours, summary)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (kid, COURSE_ID, name, chapter, hours, f"关于 {name} 的详细说明"))

    con.commit()
    print("[graph] 知识点章节已更新为 9 章结构，新增 6 个知识点")


def update_graph_links(cur, con):
    """新增第4、5章前后置关系，并把新桥接到第6章"""
    links = [
        ("knowledge", "KP24", "KP401", "pre"),   # 栈的应用 -> 串
        ("knowledge", "KP401", "KP402", "pre"),
        ("knowledge", "KP402", "KP403", "pre"),
        ("knowledge", "KP403", "KP404", "pre"),
        ("knowledge", "KP404", "KP501", "pre"),  # 串 -> 数组和广义表
        ("knowledge", "KP12", "KP501", "pre"),   # 顺序表 -> 数组
        ("knowledge", "KP501", "KP502", "pre"),
        ("knowledge", "KP502", "KP31", "pre"),   # 广义表 -> 树和二叉树
        ("knowledge", "KP53", "KP61", "pre"),    # 图 -> 查找
        ("knowledge", "KP64", "KP71", "pre"),    # 哈希表 -> 排序
    ]
    for graph_type, src, tgt, rel in links:
        cur.execute("""
            INSERT OR IGNORE INTO graph_links (graph_type, course_id, source, target, relation)
            VALUES (?, ?, ?, ?, ?)
        """, (graph_type, COURSE_ID, src, tgt, rel))
    con.commit()
    print(f"[graph] 已新增 {len(links)} 条前后置关系")


def clear_learning_paths(cur, con):
    cur.execute("DELETE FROM learning_paths")
    con.commit()
    print("[path] 已清空学习路径缓存，下次访问将按新 9 章结构重新生成")


def update_course_meta(cur, con):
    cur.execute("SELECT COUNT(*) FROM graph_nodes WHERE graph_type='knowledge'")
    total_kp = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM resources")
    total_res = cur.fetchone()[0]
    cur.execute("""
        UPDATE courses
        SET chapters=9, knowledge_points=?, resources=?
        WHERE course_id=?
    """, (total_kp, total_res, COURSE_ID))
    con.commit()
    print(f"[course] 课程元信息已更新：章节=9，知识点={total_kp}，资源={total_res}")


def next_res_id(cur):
    row = cur.execute("SELECT MAX(res_id) FROM resources WHERE res_id LIKE 'R%'").fetchone()
    if not row or not row[0]:
        return "R001"
    n = int(row[0][1:]) + 1
    return f"R{n:03d}"


def extract_chapter(filename: str) -> int:
    m = re.search(r"Ch(\d{2})", filename)
    return int(m.group(1)) if m else 0


def decide_kp_id(title: str, chapter: int) -> str:
    """
    根据标题关键词匹配知识点。
    限制：只在同章节知识点内匹配，杜绝跨章误挂（如把"二叉树遍历"挂到单链表）。
    权重 = 命中关键词长度之和，优先长关键词（如 "二叉树遍历" > "遍历"）。
    无命中则返回章节代表知识点。
    """
    title = title.lower()
    best_kp = None
    best_score = 0
    for kp_id, keywords in KP_KEYWORDS.items():
        if CHAPTER_OF_KP.get(kp_id) != chapter:
            continue
        score = sum(len(kw) for kw in keywords if kw.lower() in title)
        if score > best_score:
            best_score = score
            best_kp = kp_id
    if best_kp and best_score > 0:
        return best_kp
    return CHAPTER_REP.get(chapter, "")


def parse_duration_or_pages(path: Path, rtype: str):
    if rtype == "video":
        return mp4_duration(path), 0
    elif rtype == "ppt":
        return "", pptx_pages(path)
    elif rtype == "doc":
        return "", pdf_pages(path)
    return "", 0


def import_resources(cur, con):
    """扫描 SOURCE_DIR，复制文件，创建 Resource 记录"""
    # 收集所有目标文件
    files = sorted([p for p in SOURCE_DIR.rglob("*") if p.is_file()])
    if not files:
        print(f"[error] 未在 {SOURCE_DIR} 找到资源文件")
        return 0

    created = 0
    for src in files:
        filename = src.name
        rtype, _ = guess_type(filename)
        if not rtype:
            print(f"  跳过未知类型: {filename}")
            continue

        chapter = extract_chapter(filename)
        if chapter == 0 or chapter not in CHAPTER_NAMES:
            print(f"  跳过无法识别章节的文件: {filename}")
            continue

        title = parse_title(filename)
        # 教材文献 PDF 标题特殊处理：保留完整章节名
        if filename.startswith("DOC_"):
            title = f"数据结构第{chapter}章"

        # 决定挂载知识点
        # 教材文献按「章节级兜底」处理（kp_id 为空，kp 为章节名），让所有知识点抽屉都显示教材
        if filename.startswith("DOC_"):
            kp_id = ""
        else:
            kp_id = decide_kp_id(title, chapter)

        chapter_name = CHAPTER_NAMES[chapter]

        # 复制文件到目标目录，保持子目录结构
        rel = src.relative_to(SOURCE_DIR)
        dest = TARGET_DIR / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)

        # URL 使用正斜杠
        url = "/assets/resources/data-structures-1-9/" + "/".join(rel.parts)

        # 解析时长/页数
        duration, pages = parse_duration_or_pages(dest, rtype)

        res_id = next_res_id(cur)

        cur.execute("""
            INSERT INTO resources
            (res_id, course_id, title, type, kp, kp_id, category, duration, pages, count, source, views, url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, '本地资源', 0, ?)
        """, (res_id, COURSE_ID, title, rtype, chapter_name, kp_id, "other", duration, pages, url))

        # 生成封面
        generate_cover(res_id, title, rtype)

        created += 1
        print(f"  {res_id} {rtype:5} {chapter_name} {kp_id or '(章节级)':8} {title[:40]}")

    con.commit()
    print(f"[import] 成功导入 {created} 个资源")
    return created


def update_course_resource_count(cur, con):
    cur.execute("SELECT COUNT(*) FROM resources")
    total = cur.fetchone()[0]
    cur.execute("UPDATE courses SET resources=? WHERE course_id=?", (total, COURSE_ID))
    con.commit()
    print(f"[course] 课程资源总数已更新为 {total}")


def print_summary(cur):
    print("\n=== 导入后知识点挂载统计 ===")
    cur.execute("""
        SELECT r.kp_id, g.name, COUNT(*)
        FROM resources r LEFT JOIN graph_nodes g ON r.kp_id = g.id AND g.graph_type='knowledge'
        WHERE r.kp_id != ''
        GROUP BY r.kp_id ORDER BY r.kp_id
    """)
    for row in cur.fetchall():
        print(f"  {row[0]} {row[1]}: {row[2]} 条")

    print("\n=== 各章节资源分布 ===")
    cur.execute("""
        SELECT SUBSTR(kp, 1, 3) as ch, type, COUNT(*) FROM resources
        WHERE source='本地资源' GROUP BY ch, type ORDER BY ch, type
    """)
    for row in cur.fetchall():
        print(f"  {row[0]} {row[1]:5}: {row[2]} 条")


def main():
    print("=" * 60)
    print("开始导入 数据结构1-9 课程资源")
    print("=" * 60)

    backup_db()
    ensure_dirs()

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    try:
        delete_existing_local_resources(cur, con)
        update_graph_structure(cur, con)
        update_graph_links(cur, con)
        clear_learning_paths(cur, con)
        update_course_meta(cur, con)
        import_resources(cur, con)
        update_course_resource_count(cur, con)
        print_summary(cur)
        print("\nDONE ✅")
    except Exception as e:
        con.rollback()
        print(f"\n[ERROR] 导入失败，已回滚: {e}")
        raise
    finally:
        con.close()


if __name__ == "__main__":
    main()
