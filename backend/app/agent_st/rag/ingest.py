from __future__ import annotations

import re
from pathlib import Path

from app.agent_st.rag.chapter_map import map_section, section_prefix
from app.agent_st.rag.embed import active_model_name, embed_texts
from app.agent_st.rag.parsers import get_parser
from app.agent_st.rag.parsers.base import split_text
from app.agent_st.rag.schema import ChunkRecord, ParsedUnit
from app.agent_st.rag.store import ChunkStore

CHAPTER_HINT_RE = re.compile(r"第\s*([1-9])\s*章")
SECTION_HINT_RE = re.compile(r"([1-8]\.[1-5])")


def _infer_section(unit: ParsedUnit, fallback_name: str) -> tuple[int, str]:
    if unit.course_chapter and unit.section:
        return unit.course_chapter, unit.section
    hint = " ".join(filter(None, [unit.section_hint, unit.text[:200], fallback_name]))
    mapped = map_section(hint)
    if mapped["id"]:
        prefix = section_prefix(hint) or hint
        return mapped["id"], unit.section_hint or prefix
    m = SECTION_HINT_RE.search(hint)
    if m:
        mapped = map_section(m.group(1))
        if mapped["id"]:
            return mapped["id"], m.group(1)
    m = CHAPTER_HINT_RE.search(hint)
    if m:
        return int(m.group(1)), f"第{m.group(1)}章"
    return 0, unit.section_hint or fallback_name


def units_to_records(units: list[ParsedUnit], source_name: str) -> list[ChunkRecord]:
    records: list[ChunkRecord] = []
    model = active_model_name()
    seq = 0
    for unit in units:
        chapter, section = _infer_section(unit, source_name)
        pieces = [unit.text] if unit.pre_chunked else split_text(unit.text)
        for piece in pieces:
            seq += 1
            if unit.pre_chunked and unit.question_id is not None:
                prefix = "qstem" if unit.source_type == "question_stem" else "qanal"
                chunk_id = f"{prefix}-{unit.question_id}"
            else:
                chunk_id = f"{unit.source_type}-{source_name}-{seq}"
            records.append(
                ChunkRecord(
                    chunk_id=chunk_id,
                    text=piece,
                    source_type=unit.source_type,
                    source_id=unit.source_id or source_name,
                    course_chapter=chapter,
                    section=section,
                    question_id=unit.question_id,
                    page_or_slide=unit.page,
                    extra=unit.extra,
                    embedding_model=model,
                )
            )
    return records


def ingest_path(path: Path, store: ChunkStore | None = None, replace_source: bool = True) -> dict:
    path = Path(path)
    parser = get_parser(path)
    units = parser.parse(path)
    records = units_to_records(units, path.name)
    if not records:
        return {"ok": False, "error": "未产生切片", "path": str(path)}
    vectors = embed_texts([r.text for r in records])
    for rec, vec in zip(records, vectors):
        rec.embedding = vec
    store = store or ChunkStore()
    if replace_source:
        if path.suffix.lower() == ".json":
            store.delete_source_types(["question_stem", "question_analysis"])
        else:
            store.delete_source(path.name)
    n = store.upsert_many(records)
    types = sorted({r.source_type for r in records})
    return {
        "ok": True,
        "path": str(path),
        "chunks": n,
        "source_types": types,
        "embedding_model": active_model_name(),
    }


def ingest_bank(bank_path: Path | None = None, store: ChunkStore | None = None) -> dict:
    from app.agent_st.agent.config import get_settings

    settings = get_settings()
    return ingest_path(Path(bank_path or settings.bank_path), store=store)


def reembed_stale_chunks(store: ChunkStore | None = None) -> dict:
    """把由旧 embedding 模型生成的切片重新向量化。

    常见于：先用本地哈希向量建库，之后在 .env 里填了 EMBEDDING_API_KEY。
    若不重算，查询向量与库内向量维度不同，cosine 恒为 0，检索永远为空，
    表现为“解析成功但讲解/出题检索不到原文”。
    """
    store = store or ChunkStore()
    model = active_model_name()
    stale = store.stale_chunks(model)
    if not stale:
        return {"ok": True, "reembedded": 0, "embedding_model": model}
    vectors = embed_texts([text for _, text in stale])
    if len(vectors) != len(stale):
        return {
            "ok": False,
            "reembedded": 0,
            "error": f"向量条数不一致：切片 {len(stale)}，向量 {len(vectors)}",
            "embedding_model": model,
        }
    pairs = [(chunk_id, vec) for (chunk_id, _), vec in zip(stale, vectors)]
    n = store.update_embeddings(pairs, model)
    return {"ok": True, "reembedded": n, "embedding_model": model}


def ensure_bank_indexed() -> dict:
    """启动/每轮对话前的自检：先修复 embedding 模型漂移，再按需建库。

    建库/重算都访问外部 embedding 服务，失败不能拖垮服务，
    因此只记录 reembed_error，让服务照常起来。
    题库文件缺失时（导入脚本未运行）直接跳过建库，不报错。
    """
    from app.agent_st.agent.config import get_settings

    store = ChunkStore()
    info: dict = {}
    try:
        result = reembed_stale_chunks(store)
        if result.get("reembedded"):
            info["reembedded"] = result["reembedded"]
            info["embedding_model"] = result.get("embedding_model")
        if not result.get("ok"):
            info["reembed_error"] = result.get("error")
    except Exception as exc:  # noqa: BLE001
        info["reembed_error"] = str(exc)

    if store.count() > 0:
        return {"ok": True, "chunks": store.count(), "skipped": True, **info}
    if not Path(get_settings().bank_path).exists():
        info["bank_missing"] = True
        return {"ok": False, "error": "题库文件不存在，请先运行 import_st_bank.py", **info}
    try:
        return ingest_bank(store=store)
    except Exception as exc:  # noqa: BLE001
        info["ingest_error"] = str(exc)
        return {"ok": False, "error": str(exc), **info}
