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
    course_chapter: int | None = None,
    section_prefix: str | None = None,
    source_types: list[str] | None = None,
    top_k: int = 6,
    store: ChunkStore | None = None,
) -> list[dict]:
    store = store or ChunkStore()
    records = store.load_filtered(course_chapter, section_prefix, source_types)
    if not records:
        return []
    query_vec = embed_texts([query])[0]
    ranked: list[tuple[float, ChunkRecord]] = []
    for rec in records:
        k_score = keyword_score(query, rec.text + " " + rec.section)
        # 维度不一致时向量分恒为 0，此时退化为纯关键词打分，而不是把总分压低到
        # 0.45 倍、让本该命中的切片落到阈值以下。
        if dims_compatible(query_vec, rec.embedding):
            score = 0.55 * cosine(query_vec, rec.embedding) + 0.45 * k_score
        else:
            score = k_score
        ranked.append((score, rec))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [rec.to_hit(score) for score, rec in ranked[: max(1, top_k)]]
