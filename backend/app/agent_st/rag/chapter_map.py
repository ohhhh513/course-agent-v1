"""王道小节 → 课程 9 章。规则与 assets/js/chapter-map.js 保持一致。"""

from __future__ import annotations

from typing import Any

CHAPTERS = [
    {"id": 1, "title": "第1章 绪论", "prefixes": ["1."]},
    {"id": 2, "title": "第2章 线性表", "prefixes": ["2."]},
    {"id": 3, "title": "第3章 栈和队列", "prefixes": ["3.1", "3.2", "3.3"]},
    {"id": 4, "title": "第4章 串", "prefixes": ["4."]},
    {"id": 5, "title": "第5章 数组和广义表", "prefixes": ["3.4"]},
    {"id": 6, "title": "第6章 树和二叉树", "prefixes": ["5."]},
    {"id": 7, "title": "第7章 图", "prefixes": ["6."]},
    {"id": 8, "title": "第8章 查找", "prefixes": ["7."]},
    {"id": 9, "title": "第9章 排序", "prefixes": ["8."]},
]

UNCATEGORIZED = {"id": 0, "title": "未分类", "prefixes": []}

ALLOWED_GRAPH_TYPES = frozenset(
    {
        "tree",
        "adjacency_matrix",
        "undirected_graph",
        "directed_graph",
        "weighted_undirected_graph",
        "weighted_directed_graph",
        "aoe_network",
    }
)

DIRECTED_TYPES = frozenset({"directed_graph", "weighted_directed_graph", "aoe_network"})
WEIGHTED_TYPES = frozenset(
    {"weighted_undirected_graph", "weighted_directed_graph", "aoe_network"}
)


def map_section(section: str | None) -> dict:
    text = str(section or "")
    for ch in CHAPTERS:
        for prefix in ch["prefixes"]:
            if text.startswith(prefix):
                return ch
    return UNCATEGORIZED


def section_prefix(section: str | None) -> str:
    text = str(section or "").strip()
    parts = text.split(" ", 1)
    return parts[0] if parts else ""


def figure_mode(question: dict | None) -> str:
    q = question or {}
    if q.get("options_graph"):
        return "option-figures"
    graph = q.get("graph") or {}
    if graph.get("type") == "adjacency_matrix":
        return "matrix"
    if graph:
        return "stem-figure"
    return "text"


def normalize(question: dict) -> dict:
    course = map_section(question.get("chapter"))
    return {
        "id": question.get("id"),
        "section": question.get("chapter"),
        "courseId": course["id"],
        "courseTitle": course["title"],
        "question": question.get("question") or "",
        "options": question.get("options") or {},
        "answer": question.get("answer"),
        "analysis": question.get("analysis") or "",
        "has_image": bool(question.get("has_image")),
        "graph": question.get("graph"),
        "options_graph": question.get("options_graph"),
        "figureMode": figure_mode(question),
    }


def is_allowed_chapter(section: str | None) -> bool:
    return map_section(section)["id"] != 0


def extra_from_question(question: dict) -> dict[str, Any]:
    graph = question.get("graph") or {}
    return {
        "figure_mode": figure_mode(question),
        "graph_type": graph.get("type"),
        "has_image": bool(question.get("has_image")),
        "has_graph": bool(graph),
        "has_options_graph": bool(question.get("options_graph")),
    }
