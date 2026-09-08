"""出题「较大变动」校验：禁止数值微扰克隆，允许同考点的新实例。"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

from app.agent_st.rag.chapter_map import DIRECTED_TYPES

STEM_CLONE_RATIO = 0.85
STEM_FRESH_RATIO = 0.65
EDGE_CLONE_JACCARD = 0.8
EDGE_FRESH_JACCARD = 0.6
MAX_MICRO_WEIGHT_CHANGES = 2
MIN_FRESH_WEIGHT_CHANGES = 3
NODE_FRESH_DELTA = 2

_NUM_RE = re.compile(r"\d+(?:\.\d+)?")
_SPACE_RE = re.compile(r"\s+")

# 更长的标记必须排在前面，避免「最短路径」被「路径」吞掉。
ASK_MARKERS = (
    "第一条边",
    "最后一条边",
    "次短路径",
    "最短路径",
    "关键路径",
    "拓扑序列",
    "拓扑排序",
    "总权值",
    "权值和",
    "next数组",
    "next 数组",
    "最小生成树",
    "最大生成树",
    "时间复杂度",
    "空间复杂度",
    "比较次数",
    "第几次",
    "先序",
    "中序",
    "后序",
    "层序",
    "入度",
    "出度",
    "kruskal",
    "prim",
    "dijkstra",
    "floyd",
    "kmp",
    "最大",
    "最小",
    "高度",
    "深度",
)


def normalize_stem(text: str) -> str:
    lowered = str(text or "").lower()
    lowered = _NUM_RE.sub("#", lowered)
    lowered = _SPACE_RE.sub("", lowered)
    lowered = lowered.replace("，", ",").replace("、", ",")
    return lowered


def asked_markers(text: str) -> frozenset[str]:
    lowered = str(text or "").lower()
    found: list[str] = []
    rest = lowered
    for marker in ASK_MARKERS:
        key = marker.lower()
        if key in rest:
            found.append(marker)
            rest = rest.replace(key, " ")
    return frozenset(found)


def stem_similarity(a: str, b: str) -> float:
    na, nb = normalize_stem(a), normalize_stem(b)
    if not na and not nb:
        return 1.0
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


def same_asked_target(a: str, b: str) -> bool:
    ma, mb = asked_markers(a), asked_markers(b)
    if not ma and not mb:
        return True
    return ma == mb


def question_fingerprint(payload: dict) -> str:
    stem = normalize_stem(str(payload.get("question") or ""))
    graph = payload.get("graph") if isinstance(payload.get("graph"), dict) else {}
    edges = []
    for edge in graph.get("edges") or []:
        if not isinstance(edge, dict):
            continue
        edges.append(f"{edge.get('from')}-{edge.get('to')}:{edge.get('weight')}")
    matrix = graph.get("matrix")
    extra = ""
    if isinstance(matrix, list):
        extra = str(matrix)
    return stem + "|" + ",".join(sorted(edges)) + "|" + extra


def _edge_key(edge: dict, directed: bool) -> tuple:
    frm, to = str(edge.get("from")), str(edge.get("to"))
    if directed:
        return (frm, to)
    return tuple(sorted((frm, to)))


def _edges_from_graph(graph: dict) -> list[dict]:
    gtype = graph.get("type")
    if gtype == "adjacency_matrix":
        nodes = [str(n) for n in graph.get("nodes") or []]
        matrix = graph.get("matrix") or []
        directed = True
        edges = []
        for i, row in enumerate(matrix):
            if not isinstance(row, list):
                continue
            for j, val in enumerate(row):
                if i >= len(nodes) or j >= len(nodes):
                    continue
                try:
                    weight = float(val)
                except (TypeError, ValueError):
                    continue
                if abs(weight) < 1e-12:
                    continue
                if not directed and j <= i:
                    continue
                edges.append({"from": nodes[i], "to": nodes[j], "weight": weight})
        return edges
    return [e for e in (graph.get("edges") or []) if isinstance(e, dict)]


def _graph_view(graph: dict | None) -> dict | None:
    if not isinstance(graph, dict) or not graph:
        return None
    gtype = graph.get("type")
    nodes = [str(n) for n in graph.get("nodes") or []]
    directed = gtype in DIRECTED_TYPES or gtype == "adjacency_matrix"
    edges = _edges_from_graph(graph)
    edge_set = set()
    weight_map: dict[tuple, float] = {}
    for edge in edges:
        key = _edge_key(edge, directed)
        edge_set.add(key)
        weight = edge.get("weight")
        if isinstance(weight, (int, float)):
            weight_map[key] = float(weight)
    return {
        "type": gtype,
        "n": len(nodes),
        "m": len(edges),
        "edge_set": edge_set,
        "weight_map": weight_map,
    }


def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    union = a | b
    if not union:
        return 1.0
    return len(a & b) / len(union)


def _weight_changes(va: dict, vb: dict) -> tuple[int, bool]:
    shared = va["edge_set"] & vb["edge_set"]
    diffs: list[float] = []
    for key in shared:
        wa = va["weight_map"].get(key)
        wb = vb["weight_map"].get(key)
        if wa is None or wb is None:
            continue
        diffs.append(wb - wa)
    changed = sum(1 for d in diffs if abs(d) > 1e-9)
    translated = (
        len(diffs) >= 3
        and changed == len(diffs)
        and len({round(d, 6) for d in diffs}) == 1
    )
    return changed, translated


def _graph_compare(candidate: dict | None, source: dict | None) -> dict | None:
    va, vb = _graph_view(candidate), _graph_view(source)
    if va is None and vb is None:
        return None
    if va is None or vb is None:
        n = (va or vb)["n"]
        return {
            "same_type": False,
            "same_size": False,
            "jaccard": 0.0,
            "node_diff": max(n, NODE_FRESH_DELTA),
            "weight_changes": 0,
            "translated": False,
            "meaningful_weight_changes": 0,
        }
    changed, translated = _weight_changes(va, vb)
    meaningful = 0 if translated else changed
    return {
        "same_type": va["type"] == vb["type"],
        "same_size": va["n"] == vb["n"] and va["m"] == vb["m"],
        "jaccard": _jaccard(va["edge_set"], vb["edge_set"]),
        "node_diff": abs(va["n"] - vb["n"]),
        "weight_changes": changed,
        "translated": translated,
        "meaningful_weight_changes": meaningful,
    }


def _ref_stem(ref: dict) -> str:
    return str(ref.get("question") or ref.get("stem") or "")


def _ref_graph(ref: dict) -> dict | None:
    if isinstance(ref.get("graph"), dict):
        return ref.get("graph")
    raw = ref.get("raw") if isinstance(ref.get("raw"), dict) else {}
    if isinstance(raw.get("graph"), dict):
        return raw.get("graph")
    return None


def _ref_id(ref: dict) -> str:
    return str(ref.get("id") or ref.get("question_id") or "?")


def compare_against_ref(candidate: dict, ref: dict) -> dict:
    cand_stem = str(candidate.get("question") or "")
    ref_stem = _ref_stem(ref)
    ratio = stem_similarity(cand_stem, ref_stem)
    same_target = same_asked_target(cand_stem, ref_stem)
    graph = _graph_compare(candidate.get("graph"), _ref_graph(ref))

    sufficient = (not same_target) or ratio < STEM_FRESH_RATIO
    if graph is not None:
        sufficient = sufficient or (
            graph["jaccard"] < EDGE_FRESH_JACCARD
            or graph["node_diff"] >= NODE_FRESH_DELTA
            or graph["meaningful_weight_changes"] >= MIN_FRESH_WEIGHT_CHANGES
        )

    trivial = ratio >= STEM_CLONE_RATIO and same_target
    if graph is not None:
        trivial = trivial and graph["same_type"] and graph["same_size"]
        trivial = trivial and graph["jaccard"] >= EDGE_CLONE_JACCARD
        trivial = trivial and (
            graph["weight_changes"] <= MAX_MICRO_WEIGHT_CHANGES or graph["translated"]
        )
    else:
        trivial = trivial  # 纯文本：题干几乎一样且提问目标相同即偷懒

    ref_id = _ref_id(ref)
    if sufficient:
        return {
            "sufficient": True,
            "trivial": False,
            "ok": True,
            "ref_id": ref_id,
            "stem_ratio": round(ratio, 4),
            "same_target": same_target,
            "graph": graph,
            "reason": "",
        }
    if trivial:
        reason = f"相对题 {ref_id} 仅做了数值/标签微扰，提问目标与实例几乎未变"
    else:
        reason = f"相对题 {ref_id} 变动不足：请换提问目标，或换一个实质不同的实例（不要只改一两个数）"
    return {
        "sufficient": False,
        "trivial": trivial,
        "ok": False,
        "ref_id": ref_id,
        "stem_ratio": round(ratio, 4),
        "same_target": same_target,
        "graph": graph,
        "reason": reason,
    }


def check_novelty(candidate: dict, references: list[dict] | None = None) -> dict:
    refs = [r for r in (references or []) if isinstance(r, dict)]
    fingerprint = question_fingerprint(candidate)
    if not refs:
        return {
            "ok": True,
            "errors": [],
            "note": "无对照例题，仅做自洽检查",
            "details": [],
            "fingerprint": fingerprint,
        }
    details = [compare_against_ref(candidate, ref) for ref in refs]
    errors = [d["reason"] for d in details if not d["ok"] and d.get("reason")]
    return {
        "ok": not errors,
        "errors": errors,
        "note": None if errors else "相对对照题已满足较大变动",
        "details": details,
        "fingerprint": fingerprint,
    }
