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

# 题库 JSON 入库时按来源类型整体替换（同一课程内的题库是「全量快照」语义）
BANK_SOURCE_TYPES = ["question_stem", "question_analysis"]


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


def units_to_records(
    units: list[ParsedUnit],
    source_name: str,
    course_id: str,
    source_key: str | None = None,
) -> list[ChunkRecord]:
    """切片记录化。

    - course_id 必填，并写进 chunk_id 前缀 —— chunk_id 是主键，若不带课程维度，
      两门课导入同一份题库会因 `qstem-1` 撞车而互相 INSERT OR REPLACE 覆盖。
    - source_key 是切片的来源标识，默认取文件名；资源类上传应传
      `{res_id}/{文件名}`，避免同名文件互相覆盖（课程内隔离）。
    """
    if not course_id:
        raise ValueError("units_to_records 必须指定 course_id")
    key = source_key or source_name
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
                chunk_id = f"{course_id}:{prefix}-{unit.question_id}"
            else:
                chunk_id = f"{course_id}:{unit.source_type}-{key}-{seq}"
            records.append(
                ChunkRecord(
                    chunk_id=chunk_id,
                    text=piece,
                    source_type=unit.source_type,
                    source_id=key,
                    course_chapter=chapter,
                    section=section,
                    course_id=course_id,
                    question_id=unit.question_id,
                    page_or_slide=unit.page,
                    extra=unit.extra,
                    embedding_model=model,
                )
            )
    return records


def ingest_path(
    path: Path,
    course_id: str,
    store: ChunkStore | None = None,
    replace_source: bool = True,
    source_key: str | None = None,
) -> dict:
    """把一个文件切片入某门课的库。

    题库 JSON 走「按来源类型整体替换该课程的题库切片」，
    其它文件走「按 source_key 替换」。
    """
    if not course_id:
        raise ValueError("ingest_path 必须指定 course_id")
    path = Path(path)
    key = source_key or path.name
    parser = get_parser(path)
    units = parser.parse(path)
    records = units_to_records(units, path.name, course_id=course_id, source_key=key)
    if not records:
        return {"ok": False, "error": "未产生切片", "path": str(path), "course_id": course_id}
    vectors = embed_texts([r.text for r in records])
    for rec, vec in zip(records, vectors):
        rec.embedding = vec
    store = store or ChunkStore()
    if replace_source:
        if path.suffix.lower() == ".json":
            store.delete_source_types(BANK_SOURCE_TYPES, course_id=course_id)
        else:
            store.delete_source(key, course_id=course_id)
    n = store.upsert_many(records)
    types = sorted({r.source_type for r in records})
    return {
        "ok": True,
        "path": str(path),
        "course_id": course_id,
        "source_key": key,
        "chunks": n,
        "source_types": types,
        "embedding_model": active_model_name(),
    }


def ingest_bank(
    course_id: str,
    bank_path: Path | None = None,
    store: ChunkStore | None = None,
) -> dict:
    """把课后题库 JSON 入到指定课程。course_id 必填。"""
    from app.agent_st.agent.config import get_settings

    if not course_id:
        raise ValueError("ingest_bank 必须指定 course_id")
    settings = get_settings()
    return ingest_path(
        Path(bank_path or settings.bank_path),
        course_id=course_id,
        store=store,
        source_key="__st_bank__",
    )


def reembed_stale_chunks(
    store: ChunkStore | None = None, course_id: str | None = None
) -> dict:
    """把由旧 embedding 模型生成的切片重新向量化。

    常见于：先用本地哈希向量建库，之后在 .env 里填了 EMBEDDING_API_KEY。
    若不重算，查询向量与库内向量维度不同，cosine 恒为 0，检索永远为空，
    表现为“解析成功但讲解/出题检索不到原文”。

    course_id 为 None 时处理全库（向量模型是全库统一的，跨课程重算无害）。
    """
    store = store or ChunkStore()
    model = active_model_name()
    stale = store.stale_chunks(model, course_id=course_id)
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


def ensure_bank_indexed(course_id: str | None = None) -> dict:
    """每轮对话前的自检。

    两件事分开处理：
    1) **向量漂移自愈**（全库、幂等、与课程无关）——切换 embedding 模型后把
       旧维度向量重算，否则检索永远命中不到。
    2) **按需建库**——只有在配置里显式声明了「题库归属课程」
       （settings.ST_BANK_COURSE_ID）且与本次请求课程一致时才自动入库。
       多课程下不能再按「这门课没切片就灌题库」兜底：那会把数据结构题库
       灌进任何新课程。没有声明归属就交给 `/agent/ingest/bank`（教师）
       或 `run_st_ingest.py`（运维）显式触发。
    """
    from app.agent_st.agent.config import get_settings

    store = ChunkStore()
    info: dict = {"course_id": course_id or ""}
    try:
        result = reembed_stale_chunks(store)
        if result.get("reembedded"):
            info["reembedded"] = result["reembedded"]
            info["embedding_model"] = result.get("embedding_model")
        if not result.get("ok"):
            info["reembed_error"] = result.get("error")
    except Exception as exc:  # noqa: BLE001  重算失败不能拖垮服务
        info["reembed_error"] = str(exc)

    if not course_id:
        info["skipped_no_course"] = True
        return {"ok": True, "chunks": store.count(), "skipped": True, **info}

    if store.count(course_id) > 0:
        return {"ok": True, "chunks": store.count(course_id), "skipped": True, **info}

    if get_settings().bank_course_id != course_id:
        info["skipped_unbound_bank"] = True
        return {"ok": True, "chunks": 0, "skipped": True, **info}

    bank_path = Path(get_settings().bank_path)
    if not bank_path.exists():
        info["bank_missing"] = True
        return {"ok": False, "error": "题库文件不存在，请先运行 import_st_bank.py", **info}
    try:
        return ingest_bank(course_id, store=store)
    except Exception as exc:  # noqa: BLE001
        info["ingest_error"] = str(exc)
        return {"ok": False, "error": str(exc), **info}
