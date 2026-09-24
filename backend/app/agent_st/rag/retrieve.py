from __future__ import annotations

import re

from app.agent_st.rag.embed import cosine, dims_compatible, embed_texts
from app.agent_st.rag.schema import ChunkRecord
from app.agent_st.rag.store import ChunkStore

TERM_RE = re.compile(r"[A-Za-z][A-Za-z0-9_+]*|[\u4e00-\u9fff]{2,}")


def _terms(query: str) -> list[str]:
    return [t for t in TERM_RE.findall(query or "") if t]


def keyword_score(query: str, text: str) -> float:
    q = (query or "").strip()
    body = text or ""
    if not q or not body:
        return 0.0
    score = 0.0
    if q in body:
        score += 0.55
    hits = 0
    terms = _terms(q)
    for term in terms:
        if term in body:
            hits += 1
    if terms:
        score += 0.45 * (hits / len(terms))
    return min(1.0, score)


def retrieve_chunks(
    query: str,
    course_id: str | None = None,
    chapter_id: str | None = None,
    kp_id: str | None = None,
    kp_ids: list[str] | None = None,
    source_types: list[str] | None = None,
    top_k: int = 6,
    store: ChunkStore | None = None,
) -> list[dict]:
    """按课程 + 章/知识点检索切片。

    结构过滤用主库规范的 `chapter_id`(CH01-09) / `kp_id`(KP001-026)，
    不再用「章序号 + 王道小节」。

    知识点可以是**多个**：`kp_ids` 非空时按「命中任一」过滤（并集），
    与主库多 KP 语义一致（`kp_id` 是主 KP，`kp_ids` 是完整列表）。
    切片侧用成员匹配，所以挂了多 KP 的课件不会被漏掉。

    course_id 缺失时**直接返回空集**（fail-closed）——不再退化为「不过滤 =
    全库混搜」，那是跨课程串数据的根因。调用方（agent 工具）负责从
    ctx.extra['courseId'] 取课程；取不到应被视为上层漏传，而非降级检索。
    """
    if not course_id:
        return []
    want_kps = [str(x).strip() for x in (kp_ids or []) if str(x).strip()]
    if kp_id and str(kp_id).strip() and str(kp_id).strip() not in want_kps:
        want_kps.insert(0, str(kp_id).strip())
    store = store or ChunkStore()
    records = store.load_filtered(
        course_id=course_id,
        chapter_id=chapter_id,
        kp_ids=want_kps or None,
        source_types=source_types,
    )
    if not records:
        return []
    query_vec = embed_texts([query])[0]
    ranked: list[tuple[float, ChunkRecord]] = []
    for rec in records:
        k_score = keyword_score(query, rec.text)
        # 维度不一致时向量分恒为 0，此时退化为纯关键词打分，而不是把总分压低到
        # 0.45 倍、让本该命中的切片落到阈值以下。
        if dims_compatible(query_vec, rec.embedding):
            score = 0.55 * cosine(query_vec, rec.embedding) + 0.45 * k_score
        else:
            score = k_score
        ranked.append((score, rec))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [rec.to_hit(score) for score, rec in ranked[: max(1, top_k)]]
