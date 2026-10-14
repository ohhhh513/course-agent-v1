"""图规格：闭集常量与判定工具（与课程结构无关的纯函数）。

历史说明：本模块的内容原在 `rag/chapter_map.py` 中，该文件还承载「王道小节 →
课程 9 章」的文本推断。课程结构已全量改为「章(CH01-09) + 知识点(KP001-026)」
（见 docs/主库数据规范.md），文本推断整体废除，只把与结构无关的图规格部分迁到这里。
"""
from __future__ import annotations

from typing import Any

# 允许的图类型闭集（出题校验与前端 DsFigure 渲染共同依赖）
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


def figure_mode(question: dict | None) -> str:
    """题目用哪种方式呈现图形 —— 决定前端渲染分支与出题时的图型约束。"""
    q = question or {}
    if q.get("options_graph"):
        return "option-figures"
    graph = q.get("graph") or {}
    if graph.get("type") == "adjacency_matrix":
        return "matrix"
    if graph:
        return "stem-figure"
    return "text"


def extra_from_question(question: dict | None) -> dict[str, Any]:
    """从题目里抽出用于切片检索加权的图形特征。"""
    q = question or {}
    graph = q.get("graph") or {}
    return {
        "figure_mode": figure_mode(q),
        "graph_type": graph.get("type"),
        "has_image": bool(q.get("has_image")),
        "has_graph": bool(graph),
        "has_options_graph": bool(q.get("options_graph")),
    }


def is_allowed_graph_type(gtype: str | None) -> bool:
    return gtype in ALLOWED_GRAPH_TYPES
