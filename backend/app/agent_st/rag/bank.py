"""题库访问：唯一数据源是主库 `questions` 表。

历史说明：原实现读 `st_bank/after_class.json`（v1.0 遗留的题目文件），
与主库正式题库双轨并行，导致「防抄黑名单不覆盖已发布 AI 题」「题号体系互不相识」
等问题。现已整体改为读主库 —— 题目的章/知识点/题号天然是规范值。

身份标识统一用 **`q_id` 字符串**（如 `QD44D2820` / `AI3F8A21E7`），
与前端题库列表、发布链路完全一致；不再有 90001 起的整数题号。
"""
from __future__ import annotations

import json
import re
import uuid

from app.agent_st import persistence
from app.agent_st.rag import figures, structure

# AI 题号：与「导入题库」的 `Q`+8hex 用**不同前缀**，一眼可辨是 AI 生成的题。
AI_HEX_LEN = 8
AI_QID_RE = re.compile(r"^AI[0-9A-F]{8}$")
_AI_MAX_RETRY = 20

_LOWER_HEX = "0123456789abcdef"


def _opt_map(raw: str | None) -> dict[str, str]:
    """questions.options [{"key","text","right"}] → {"A": "..."}"""
    try:
        rows = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return {}
    if not isinstance(rows, list):
        return {}
    return {str(r.get("key")): str(r.get("text") or "") for r in rows if isinstance(r, dict)}


def _figure(raw: str | None) -> tuple[dict | None, dict | None]:
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return None, None
    if not isinstance(data, dict):
        return None, None
    return data.get("graph"), data.get("options_graph")


def _kp_list(row) -> list[str]:
    """题目的知识点列表：主 KP（kp_id）+ 挂载列表（kp_ids JSON），去重保序。

    与主库口径一致：`kp_id` 是主 KP（供组卷/掌握度统计），`kp_ids` 是完整列表。
    """
    out: list[str] = []
    primary = str(getattr(row, "kp_id", "") or "").strip()
    if primary:
        out.append(primary)
    try:
        raw = json.loads(getattr(row, "kp_ids", "") or "[]")
    except json.JSONDecodeError:
        raw = []
    if isinstance(raw, list):
        for kp in raw:
            kp = str(kp or "").strip()
            if kp and kp not in out:
                out.append(kp)
    return out


def kp_ids_of_row(row) -> list[str]:
    """公开入口：题目行 → 知识点列表（主 KP + `kp_ids`），供切片归属继承使用。"""
    return _kp_list(row)


def to_agent_question(row) -> dict:
    """DB 行 → agent 内部题目结构。字段名与出题/讲解提示词保持一致。"""
    graph, options_graph = _figure(row.figure_json)
    kp_ids = _kp_list(row)
    data = {
        "q_id": row.q_id,
        "chapter_id": row.chapter_id or "",
        "chapter": row.chapter or "",
        "kp_id": row.kp_id or "",
        "kp_ids": kp_ids,
        "kp_name": "",
        "kp_names": [],
        "type": row.type or "single",
        "difficulty": row.difficulty if row.difficulty is not None else 3,
        "score": row.score,
        "question": row.stem or "",
        "options": _opt_map(row.options),
        "answer": row.answer or "",
        "analysis": row.analysis or "",
        "has_image": bool(row.has_image),
        "graph": graph,
        "options_graph": options_graph,
        "figure_mode": figures.figure_mode({"graph": graph, "options_graph": options_graph,
                                            "has_image": bool(row.has_image)}),
    }
    return data


def _query(course_id: str, *, status: str = "published"):
    Question = persistence.Question
    db = persistence.SessionLocal()
    try:
        return (
            db.query(Question)
            .filter(Question.course_id == course_id, Question.status == status)
            .order_by(Question.q_id)
            .all()
        )
    finally:
        db.close()


def _with_kp_names(course_id: str, data: dict) -> dict:
    """补知识点名称：主 KP 填 kp_name，完整列表填 kp_names。"""
    names = {kp["id"]: kp["name"] for kp in structure.list_kps(course_id)}
    kps = [str(x) for x in (data.get("kp_ids") or []) if str(x).strip()]
    if data.get("kp_id") and data["kp_id"] not in kps:
        kps.insert(0, data["kp_id"])
    if kps:
        data["kp_ids"] = kps
        data["kp_names"] = [names.get(k, "") for k in kps]
    if not data.get("kp_name") and data.get("kp_id"):
        data["kp_name"] = names.get(data["kp_id"], "")
    return data


def get_question(course_id: str, q_id: str, include_answer: bool = True) -> dict | None:
    """按题号读题。课程隔离：跨课程的题号一律视为不存在。"""
    if not course_id or not q_id:
        return None
    Question = persistence.Question
    db = persistence.SessionLocal()
    try:
        row = (
            db.query(Question)
            .filter(Question.course_id == course_id, Question.q_id == str(q_id))
            .first()
        )
        if row is None:
            return None
        data = _with_kp_names(course_id, to_agent_question(row))
    finally:
        db.close()
    if not include_answer:
        data.pop("answer", None)
        data.pop("analysis", None)
    return data


def existing_q_ids(course_id: str) -> set[str]:
    """该课程已发布题号集合（用于出题时防重、防抄黑名单）"""
    if not course_id:
        return set()
    return {row.q_id for row in _query(course_id)}


def search_similar(
    course_id: str,
    chapter_id: str | None = None,
    kp_id: str | None = None,
    kp_ids: list[str] | None = None,
    figure: str | None = None,
    graph_type: str | None = None,
    exclude_q_id: str | None = None,
    limit: int = 3,
    include_answer: bool = False,
) -> list[dict]:
    """同章/同知识点的题库题 —— 出题时用做**防抄黑名单**与灵感对照。

    改读主库后，教师已发布的 AI 题同样在册（原先只扫 JSON，属于盲区）。
    知识点按**成员匹配**：题目挂着多个 KP 时，命中其中任一个都算（并集），
    否则挂多 KP 的题会被漏掉、防抄名单出现缺口。
    """
    if not course_id:
        return []
    want = [str(x).strip() for x in (kp_ids or []) if str(x).strip()]
    if kp_id and str(kp_id).strip() and str(kp_id).strip() not in want:
        want.insert(0, str(kp_id).strip())
    kp_names = {kp["id"]: kp["name"] for kp in structure.list_kps(course_id)}
    hits: list[dict] = []
    for row in _query(course_id):
        if exclude_q_id and row.q_id == str(exclude_q_id):
            continue
        if chapter_id and (row.chapter_id or "") != chapter_id:
            continue
        if want and not (set(want) & set(_kp_list(row))):
            continue
        data = _with_kp_names(course_id, to_agent_question(row))
        data["kp_name"] = kp_names.get(data["kp_id"], "")
        if figure and data["figure_mode"] != figure:
            continue
        gtype = (data.get("graph") or {}).get("type")
        if graph_type and gtype != graph_type:
            continue
        if not include_answer:
            data.pop("answer", None)
            data.pop("analysis", None)
        hits.append(data)
        if len(hits) >= limit:
            break
    return hits


def _taken_ai_q_ids(reserved: set[str] | None = None) -> set[str]:
    """已被占用的 AI 题号 = 正式题库里的 AI 号 ∪ `reserved`（草稿已分配的号）。"""
    Question = persistence.Question
    db = persistence.SessionLocal()
    try:
        rows = db.query(Question.q_id).filter(Question.q_id.like("AI%")).all()
    finally:
        db.close()
    taken = {str(r[0]) for r in rows}
    taken |= {str(x) for x in (reserved or set()) if str(x).upper().startswith("AI")}
    return taken


def next_ai_q_id(course_id: str = "", reserved: set[str] | None = None) -> str:
    """分配一个 AI 题号：`AI` + 8 位随机十六进制（如 `AI3F8A21E7`）。

    **为什么不再自增序号**：`q_id` 是 `questions` 主键、必须全局唯一，自增就得扫全库
    `LIKE 'AI%'`，于是「第二门出题的课程第一道题」会拿到 `AI002`（号段被别的课程吃掉），
    而且号段越大扫描越慢。随机 hex 不需要扫描，且与导入题库的 `Q`+8hex **前缀不同**，
    一眼可辨是 AI 生成的题。

    **随机 hex 单独不保证不撞**（16^8 ≈ 4.3e9；按 1 万道题估算，出现一次碰撞的概率约 1%），
    因此必须配合唯一性检查：撞了就换一个。`reserved` 让「已分配但未发布」的草稿号
    也进入检查范围，避免同一批次两道题拿到同一个号。
    """
    taken = _taken_ai_q_ids(reserved)
    for _ in range(_AI_MAX_RETRY):
        candidate = "AI" + uuid.uuid4().hex[:AI_HEX_LEN].upper()
        if candidate not in taken:
            return candidate
    # 理论上到不了这里；真到了就加长，保证不会返回已知占用的号
    return "AI" + uuid.uuid4().hex[: AI_HEX_LEN + 4].upper()
