from __future__ import annotations

from app.agent_st.rag.bank import existing_ids
from app.agent_st.rag.chapter_map import ALLOWED_GRAPH_TYPES, WEIGHTED_TYPES, is_allowed_chapter, map_section

REQUIRED_FIELDS = ("id", "chapter", "question", "options", "answer", "analysis", "has_image")
OPTION_KEYS = ("A", "B", "C", "D")


def _as_str_nodes(nodes) -> list[str]:
    return [str(n) for n in (nodes or [])]


def _has_cycle(nodes: list[str], edges: list[dict]) -> bool:
    graph = {n: [] for n in nodes}
    for edge in edges:
        frm, to = str(edge.get("from")), str(edge.get("to"))
        if frm in graph:
            graph[frm].append(to)
    state = {n: 0 for n in nodes}

    def dfs(node: str) -> bool:
        state[node] = 1
        for nxt in graph.get(node, []):
            if nxt not in state:
                continue
            if state[nxt] == 1:
                return True
            if state[nxt] == 0 and dfs(nxt):
                return True
        state[node] = 2
        return False

    return any(state[n] == 0 and dfs(n) for n in nodes)


def validate_graph(graph: dict, label: str = "graph") -> list[str]:
    errors: list[str] = []
    gtype = graph.get("type")
    if gtype not in ALLOWED_GRAPH_TYPES:
        errors.append(f"{label}.type 必须是闭集之一，当前={gtype!r}")
        return errors
    nodes = _as_str_nodes(graph.get("nodes"))
    if not nodes:
        errors.append(f"{label}.nodes 不能为空")
        return errors
    node_set = set(nodes)
    if gtype == "adjacency_matrix":
        matrix = graph.get("matrix")
        if not isinstance(matrix, list) or len(matrix) != len(nodes):
            errors.append(f"{label}.matrix 必须是与 nodes 等长的方阵")
            return errors
        for i, row in enumerate(matrix):
            if not isinstance(row, list) or len(row) != len(nodes):
                errors.append(f"{label}.matrix[{i}] 长度必须为 {len(nodes)}")
        return errors

    edges = graph.get("edges") or []
    if not isinstance(edges, list):
        errors.append(f"{label}.edges 必须是数组")
        return errors
    if gtype == "tree":
        root = str(graph.get("root") or "")
        if root not in node_set:
            errors.append(f"{label}.root 必须出现在 nodes 中")
        seen_side: set[tuple[str, str]] = set()
        for edge in edges:
            frm, to = str(edge.get("from")), str(edge.get("to"))
            pos = edge.get("position")
            if frm not in node_set or to not in node_set:
                errors.append(f"{label} 边 {frm}->{to} 的端点必须在 nodes 中")
            if pos not in {"left", "right"}:
                errors.append(f"{label} 树边必须有 position=left/right")
            key = (frm, pos)
            if pos in {"left", "right"} and key in seen_side:
                errors.append(f"{label} 结点 {frm} 的 {pos} 侧重复")
            seen_side.add(key)
        return errors

    for edge in edges:
        frm, to = str(edge.get("from")), str(edge.get("to"))
        if frm not in node_set or to not in node_set:
            errors.append(f"{label} 边 {frm}->{to} 的端点必须在 nodes 中")
        if gtype in WEIGHTED_TYPES and not isinstance(edge.get("weight"), (int, float)):
            errors.append(f"{label} 有权边 {frm}->{to} 缺少数字 weight")
        if gtype == "aoe_network":
            activity = edge.get("activity")
            if not activity or "=" in str(activity) or "/" in str(activity):
                errors.append(f"{label} AOE 边需要短 activity，且不要含 = 或 /")
    if gtype == "aoe_network" and _has_cycle(nodes, edges):
        errors.append(f"{label} AOE 网必须是 DAG，当前存在环")
    return errors


def validate_question(payload: dict, used_ids: set[int] | None = None) -> dict:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return {"ok": False, "errors": ["题目必须是 JSON 对象"]}
    for field in REQUIRED_FIELDS:
        if field not in payload:
            errors.append(f"缺少必填字段 {field}")
    if errors:
        return {"ok": False, "errors": errors}

    try:
        qid = int(payload["id"])
    except (TypeError, ValueError):
        qid = None
        errors.append("id 必须是正整数")
    if qid is not None and qid <= 0:
        errors.append("id 必须是正整数")
    used = used_ids if used_ids is not None else existing_ids()
    if qid in used:
        errors.append(f"id {qid} 与现有题库冲突")

    chapter = payload.get("chapter")
    if not is_allowed_chapter(chapter):
        errors.append(f"chapter 前缀无法映射到课程 9 章：{chapter!r}")
    else:
        payload["_course"] = map_section(chapter)

    if not str(payload.get("question") or "").strip():
        errors.append("question 不能为空")

    options = payload.get("options")
    if not isinstance(options, dict):
        errors.append("options 必须是对象，键为 A/B/C/D")
    else:
        for key in OPTION_KEYS:
            if key not in options or not isinstance(options[key], str):
                errors.append(f"options.{key} 必须是字符串")

    answer = payload.get("answer")
    if answer not in OPTION_KEYS:
        errors.append("answer 只能是 A/B/C/D")

    if not isinstance(payload.get("analysis"), str):
        errors.append("analysis 必须是字符串（没有则用空串）")

    if not isinstance(payload.get("has_image"), bool):
        errors.append("has_image 必须是布尔值")

    graph = payload.get("graph")
    options_graph = payload.get("options_graph")
    if graph:
        if not payload.get("has_image"):
            errors.append("存在 graph 时 has_image 必须为 true")
        if not isinstance(graph, dict):
            errors.append("graph 必须是对象")
        else:
            errors.extend(validate_graph(graph, "graph"))
    if options_graph:
        if not payload.get("has_image"):
            errors.append("存在 options_graph 时 has_image 必须为 true")
        if not isinstance(options_graph, dict) or set(options_graph.keys()) != set(OPTION_KEYS):
            errors.append("options_graph 键必须恰好为 A/B/C/D")
        else:
            for key in OPTION_KEYS:
                if not isinstance(options_graph[key], dict):
                    errors.append(f"options_graph.{key} 必须是图对象")
                else:
                    errors.extend(validate_graph(options_graph[key], f"options_graph.{key}"))

    return {"ok": not errors, "errors": errors, "id": qid, "chapter": chapter}


def next_question_id(extra_ids: set[int] | None = None) -> int:
    used = existing_ids() | (extra_ids or set())
    candidate = 90001
    while candidate in used:
        candidate += 1
    return candidate
