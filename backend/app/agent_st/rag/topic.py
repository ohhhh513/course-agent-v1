from __future__ import annotations

import re

from app.agent_st.rag.bank import get_question
from app.agent_st.rag.chapter_map import CHAPTERS, map_section, section_prefix

# 更长的关键词必须排在前面。
TOPIC_KEYWORDS: list[tuple[str, tuple[int, str]]] = [
    ("next数组", (4, "4.2")),
    ("模式匹配", (4, "4.2")),
    ("BF算法", (4, "4.2")),
    ("KMP", (4, "4.2")),
    ("最小生成树", (7, "6.4")),
    ("最短路径", (7, "6.4")),
    ("拓扑排序", (7, "6.4")),
    ("关键路径", (7, "6.4")),
    ("Dijkstra", (7, "6.4")),
    ("Floyd", (7, "6.4")),
    ("Kruskal", (7, "6.4")),
    ("Prim", (7, "6.4")),
    ("AOE", (7, "6.4")),
    ("AOV", (7, "6.4")),
    ("邻接矩阵", (7, "6.2")),
    ("邻接表", (7, "6.2")),
    ("深度优先", (7, "6.3")),
    ("广度优先", (7, "6.3")),
    ("DFS", (7, "6.3")),
    ("BFS", (7, "6.3")),
    ("线索二叉树", (6, "5.3")),
    ("哈夫曼", (6, "5.5")),
    ("霍夫曼", (6, "5.5")),
    ("Huffman", (6, "5.5")),
    ("二叉排序树", (8, "7.3")),
    ("平衡二叉树", (8, "7.3")),
    ("折半查找", (8, "7.2")),
    ("二分查找", (8, "7.2")),
    ("顺序查找", (8, "7.2")),
    ("B+树", (8, "7.4")),
    ("B树", (8, "7.4")),
    ("散列表", (8, "7.5")),
    ("哈希", (8, "7.5")),
    ("开放定址", (8, "7.5")),
    ("循环队列", (3, "3.2")),
    ("括号匹配", (3, "3.3")),
    ("表达式", (3, "3.3")),
    ("稀疏矩阵", (5, "3.4")),
    ("广义表", (5, "3.4")),
    ("单链表", (2, "2.3")),
    ("双链表", (2, "2.3")),
    ("顺序表", (2, "2.2")),
    ("时间复杂度", (1, "1.2")),
    ("逻辑结构", (1, "1.1")),
    ("存储结构", (1, "1.1")),
    ("插入排序", (9, "8.2")),
    ("希尔排序", (9, "8.2")),
    ("快速排序", (9, "8.3")),
    ("冒泡排序", (9, "8.3")),
    ("堆排序", (9, "8.4")),
    ("选择排序", (9, "8.4")),
    ("归并排序", (9, "8.5")),
    ("基数排序", (9, "8.5")),
    ("AVL", (8, "7.3")),
    ("BST", (8, "7.3")),
    ("二叉树", (6, "5.2")),
    ("线性表", (2, "2.2")),
    ("队列", (3, "3.2")),
    ("链表", (2, "2.3")),
    ("数组", (5, "3.4")),
    ("森林", (6, "5.4")),
    ("排序", (9, "8.2")),
    ("查找", (8, "7.2")),
    ("算法", (1, "1.2")),
    ("栈", (3, "3.1")),
    ("串", (4, "4.2")),
    ("图", (7, "6.1")),
    ("树", (6, "5.1")),
]

QUESTION_ID_RE = re.compile(r"(?:题\s*#?\s*|题号\s*|#|id\s*[=:]\s*)(\d{1,4})", re.I)
SECTION_RE = re.compile(r"\b([1-8]\.[1-5])\b")
COURSE_CHAPTER_RE = re.compile(r"第\s*([1-9])\s*章")


def resolve_topic(
    text: str = "",
    chapter: str | None = None,
    question_id: int | None = None,
) -> dict:
    query = str(text or "").strip()
    result = {
        "course_chapter": None,
        "course_title": None,
        "section": None,
        "section_prefix": None,
        "question_id": None,
        "uncertain": True,
        "matched_by": None,
        "query": query,
    }

    qid = question_id
    if qid is None:
        m = QUESTION_ID_RE.search(query)
        if m:
            qid = int(m.group(1))
    if qid is not None:
        item = get_question(qid, include_answer=False)
        if item:
            course = map_section(item["section"])
            result.update(
                {
                    "course_chapter": course["id"],
                    "course_title": course["title"],
                    "section": item["section"],
                    "section_prefix": section_prefix(item["section"]),
                    "question_id": qid,
                    "uncertain": False,
                    "matched_by": "question_id",
                }
            )
            return result

    hint = chapter or ""
    if hint:
        course = map_section(hint)
        if course["id"]:
            result.update(
                {
                    "course_chapter": course["id"],
                    "course_title": course["title"],
                    "section": hint,
                    "section_prefix": section_prefix(hint),
                    "uncertain": False,
                    "matched_by": "context_chapter",
                }
            )
            return result

    m = SECTION_RE.search(query)
    if m:
        course = map_section(m.group(1))
        if course["id"]:
            result.update(
                {
                    "course_chapter": course["id"],
                    "course_title": course["title"],
                    "section": m.group(1),
                    "section_prefix": m.group(1),
                    "uncertain": False,
                    "matched_by": "section_code",
                }
            )
            return result

    m = COURSE_CHAPTER_RE.search(query)
    if m:
        cid = int(m.group(1))
        ch = next((c for c in CHAPTERS if c["id"] == cid), None)
        if ch:
            result.update(
                {
                    "course_chapter": cid,
                    "course_title": ch["title"],
                    "uncertain": False,
                    "matched_by": "course_chapter",
                }
            )
            return result

    for key, (cid, prefix) in TOPIC_KEYWORDS:
        if key.lower() in query.lower():
            ch = next(c for c in CHAPTERS if c["id"] == cid)
            result.update(
                {
                    "course_chapter": cid,
                    "course_title": ch["title"],
                    "section": prefix,
                    "section_prefix": prefix,
                    "uncertain": False,
                    "matched_by": f"keyword:{key}",
                }
            )
            return result

    result["suggestions"] = [f"{c['id']}:{c['title']}" for c in CHAPTERS]
    return result
