from __future__ import annotations

import re

from app.agent_st.rag import structure
from app.agent_st.rag.bank import existing_q_ids
from app.agent_st.rag.figures import ALLOWED_GRAPH_TYPES, WEIGHTED_TYPES

# q_id 不是模型的输出字段（保存时由系统分配），因此不在必填项里；
# 但一旦给出了值，就必须是规范的形态。主库真实题号形如
# `QD44D2820`（Q + 8 位十六进制，前缀后含字母）、`AI3F8A21E7`，
# 所以前缀之后允许字母数字混合 —— 只写 \d 会误杀主库题号。
# 知识点是「kp_id / kp_ids 二选一」（缺 kp_id 时取 kp_ids 首个），也不进必填项。
REQUIRED_FIELDS = ("chapter_id", "question", "options", "answer", "analysis", "has_image")
OPTION_KEYS = ("A", "B", "C", "D")
Q_ID_RE = re.compile(r"^[A-Za-z]{1,4}[0-9A-Za-z]{3,12}$")


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


def validate_question(
    payload: dict,
    course_id: str = "",
    used_q_ids: set[str] | None = None,
) -> dict:
    """题目结构校验。

    结构与题号一律按**主库规范**校验：
      - `q_id` 为字符串题号，需在本课程内唯一；
      - `chapter_id` / `kp_id` 必须是该课程图谱里真实存在的节点
        （不再用「王道小节前缀能否映射到 9 章」这种文本推断）。
    """
    errors: list[str] = []
    if not isinstance(payload, dict):
        return {"ok": False, "errors": ["题目必须是 JSON 对象"]}
    for field in REQUIRED_FIELDS:
        if field not in payload:
            errors.append(f"缺少必填字段 {field}")
    if errors:
        return {"ok": False, "errors": errors}

    q_id = str(payload.get("q_id") or "").strip()
    if q_id and not Q_ID_RE.match(q_id):
        errors.append(
            f"题号 {q_id!r} 格式不合法：应为「字母前缀 + 字母数字」，如 QD44D2820 / AI3F8A21E7"
            "（q_id 通常无需你提供，系统会在保存时分配）"
        )
    used = used_q_ids if used_q_ids is not None else (existing_q_ids(course_id) if course_id else set())
    if q_id and q_id in used:
        errors.append(f"题号 {q_id} 与现有题库冲突")

    # 知识点：与主库口径一致 —— kp_id 是主 KP，kp_ids 是完整列表（可多项）。
    # 允许只给其中一种；同时给出时必须包含主 KP。
    chapter_id = str(payload.get("chapter_id") or "").strip()
    kp_id = str(payload.get("kp_id") or "").strip()
    kp_ids = [str(x).strip() for x in (payload.get("kp_ids") or []) if str(x).strip()] \
        if isinstance(payload.get("kp_ids"), list) else []
    if kp_id:
        if kp_id not in kp_ids:
            kp_ids.insert(0, kp_id)
    elif kp_ids:
        kp_id = kp_ids[0]

    if course_id:
        valid = structure.valid_kp_ids(course_id)
        if not kp_id:
            errors.append("kp_id 不能为空（或提供 kp_ids 列表）")
        elif kp_id not in valid:
            errors.append(f"kp_id {kp_id!r} 不属于本课程图谱")
        for kp in kp_ids:
            if kp not in valid:
                errors.append(f"kp_ids 中的 {kp!r} 不属于本课程图谱")
        if not chapter_id:
            errors.append("chapter_id 不能为空")
        elif not structure.chapter_name_by_id(course_id, chapter_id):
            errors.append(f"chapter_id {chapter_id!r} 不属于本课程图谱")
        # 主 KP 与章必须自洽；其余 KP 只要求属于本课程（多 KP 可以跨章，如「二叉树和图的区别」）
        if kp_id and chapter_id:
            info = structure.kp_info(course_id, kp_id)
            if info and info["chapter_id"] and info["chapter_id"] != chapter_id:
                errors.append(
                    f"知识点 {kp_id} 属于 {info['chapter_id']}，与 chapter_id {chapter_id} 不一致"
                )
    else:
        if not kp_id:
            errors.append("kp_id 不能为空（或提供 kp_ids 列表）")
        if not chapter_id:
            errors.append("chapter_id 不能为空")

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

    return {"ok": not errors, "errors": errors, "q_id": q_id,
            "chapter_id": chapter_id, "kp_id": kp_id, "kp_ids": kp_ids}
