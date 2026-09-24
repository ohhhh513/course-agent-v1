from __future__ import annotations

import json
from pathlib import Path

from app.agent_st.rag import bank as banks
from app.agent_st.rag.embed import active_model_name, embed_texts
from app.agent_st.rag.parsers import get_parser
from app.agent_st.rag.parsers.base import split_text
from app.agent_st.rag.schema import ChunkRecord, ParsedUnit
from app.agent_st.rag.store import ChunkStore

BANK_SOURCE_TYPES = ["question_stem", "question_analysis"]
QUESTION_BANK_SOURCE_KEY = "__questions__"


def units_to_records(
    units: list[ParsedUnit],
    source_name: str,
    course_id: str,
    source_key: str | None = None,
    chapter_id: str = "",
    kp_ids: list[str] | None = None,
    q_id: str = "",
) -> list[ChunkRecord]:
    """切片记录化。

    - course_id 必填，并写进 chunk_id 前缀 —— chunk_id 是主键，若不带课程维度，
      两门课导入同一份题库会因主键撞车而互相 INSERT OR REPLACE 覆盖。
    - source_key 是切片的来源标识：资源类为 `{res_id}/{文件名}`（避免同名文件
      互相覆盖），题库类为 `__questions__`。
    - **结构归属由调用方给定**（资源继承 `resources` 表、题库继承 `questions` 表），
      本函数不做任何文本推断 —— 旧的「王道小节」推断已整体废除。
    """
    if not course_id:
        raise ValueError("units_to_records 必须指定 course_id")
    key = source_key or source_name
    kps = [str(k) for k in (kp_ids or []) if str(k).strip()]
    records: list[ChunkRecord] = []
    model = active_model_name()
    seq = 0
    for unit in units:
        pieces = [unit.text] if unit.pre_chunked else split_text(unit.text)
        for piece in pieces:
            seq += 1
            if unit.pre_chunked and q_id:
                prefix = "qstem" if unit.source_type == "question_stem" else "qanal"
                chunk_id = f"{course_id}:{prefix}-{q_id}"
            else:
                chunk_id = f"{course_id}:{unit.source_type}-{key}-{seq}"
            records.append(
                ChunkRecord(
                    chunk_id=chunk_id,
                    text=piece,
                    source_type=unit.source_type,
                    source_id=key,
                    course_id=course_id,
                    chapter_id=chapter_id or "",
                    kp_id=kps[0] if kps else "",
                    kp_ids=kps,
                    q_id=q_id or "",
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
    chapter_id: str = "",
    kp_ids: list[str] | None = None,
) -> dict:
    """把一个**资源文件**切片入某门课的库。

    chapter_id / kp_ids 应由调用方从 `resources` 表继承后传入；
    留空表示该文件尚未归入任何章/知识点（仍可被整课检索到）。
    """
    if not course_id:
        raise ValueError("ingest_path 必须指定 course_id")
    path = Path(path)
    key = source_key or path.name
    parser = get_parser(path)
    units = parser.parse(path)
    records = units_to_records(
        units, path.name, course_id=course_id, source_key=key,
        chapter_id=chapter_id, kp_ids=kp_ids,
    )
    if not records:
        return {"ok": False, "error": "未产生切片", "path": str(path), "course_id": course_id}
    vectors = embed_texts([r.text for r in records])
    for rec, vec in zip(records, vectors):
        rec.embedding = vec
    store = store or ChunkStore()
    if replace_source:
        store.delete_source(key, course_id=course_id)
    n = store.upsert_many(records)
    types = sorted({r.source_type for r in records})
    return {
        "ok": True,
        "path": str(path),
        "course_id": course_id,
        "source_key": key,
        "chapter_id": chapter_id,
        "kp_ids": list(kp_ids or []),
        "chunks": n,
        "source_types": types,
        "embedding_model": active_model_name(),
    }


# ----------------------------------------------------------------------
# 题库切片：唯一来源是主库 questions 表
# ----------------------------------------------------------------------
def _options_text(raw: str | None) -> str:
    """questions.options 是 [{"key":"A","text":..,"right":..}]，转成可检索的 A. xxx"""
    try:
        rows = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return ""
    if not isinstance(rows, list):
        return ""
    return "\n".join(f"{o.get('key')}. {o.get('text') or ''}" for o in rows if isinstance(o, dict))


def _question_units(
    stem: str, options_text: str, analysis: str, chapter_name: str, kp_name: str
) -> list[ParsedUnit]:
    head = ""
    if chapter_name:
        head += f"章节：{chapter_name}\n"
    if kp_name:
        head += f"知识点：{kp_name}\n"
    stem_body = f"{head}题干：{stem}"
    if options_text:
        stem_body += f"\n选项：\n{options_text}"
    return [
        ParsedUnit(text=stem_body, pre_chunked=True, source_type="question_stem",
                   source_id=QUESTION_BANK_SOURCE_KEY),
        ParsedUnit(text=f"{head}解析：{analysis or '（本题暂无解析）'}", pre_chunked=True,
                   source_type="question_analysis", source_id=QUESTION_BANK_SOURCE_KEY),
    ]


def ingest_question_bank(course_id: str, store: ChunkStore | None = None) -> dict:
    """把**主库 questions 表**里该课程的已发布题目切成检索切片。

    这是题库切片进入 rag.db 的唯一通道（原先读 after_class.json，已废除）。
    题目的章/知识点直接取 `questions.chapter_id` / `questions.kp_id`，
    因此切片天然带规范结构，不需要任何文本推断。
    """
    from app.agent_st import persistence
    from app.agent_st.rag import structure

    if not course_id:
        raise ValueError("ingest_question_bank 必须指定 course_id")

    Question = persistence.Question
    db = persistence.SessionLocal()
    try:
        rows = (
            db.query(Question)
            .filter(Question.course_id == course_id, Question.status == "published")
            .order_by(Question.q_id)
            .all()
        )
        questions = [
            {
                "q_id": r.q_id,
                "stem": r.stem or "",
                "options": r.options,
                "analysis": r.analysis or "",
                "chapter_id": r.chapter_id or "",
                "chapter": r.chapter or "",
                "kp_id": r.kp_id or "",
                # 多 KP：kp_id 是主 KP，kp_ids 是完整列表（切片要把两者都带上，
                # 否则挂多 KP 的题在按非主 KP 检索时会漏）
                "kp_ids": banks.kp_ids_of_row(r),
            }
            for r in rows
        ]
    finally:
        db.close()

    if not questions:
        return {"ok": True, "course_id": course_id, "questions": 0, "chunks": 0,
                "note": "该课程 questions 表无已发布题目，未产生切片"}

    kp_names = {kp["id"]: kp["name"] for kp in structure.list_kps(course_id)}
    records: list[ChunkRecord] = []
    for q in questions:
        units = _question_units(
            q["stem"], _options_text(q["options"]), q["analysis"],
            q["chapter"], kp_names.get(q["kp_id"], ""),
        )
        records.extend(
            units_to_records(
                units, QUESTION_BANK_SOURCE_KEY, course_id=course_id,
                source_key=QUESTION_BANK_SOURCE_KEY,
                chapter_id=q["chapter_id"],
                kp_ids=q["kp_ids"] or None,
                q_id=q["q_id"],
            )
        )

    vectors = embed_texts([r.text for r in records])
    for rec, vec in zip(records, vectors):
        rec.embedding = vec

    store = store or ChunkStore()
    store.delete_source_types(BANK_SOURCE_TYPES, course_id=course_id)
    n = store.upsert_many(records)
    return {
        "ok": True,
        "course_id": course_id,
        "questions": len(questions),
        "chunks": n,
        "embedding_model": active_model_name(),
    }


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

    1) **向量漂移自愈**（全库、幂等、与课程无关）。
    2) **按需建题库索引** —— 该课程在 rag.db 里一条切片都没有时才建。
       数据源是主库 questions 表，切片只覆盖本课程自己的题，
       因此不再需要「题库文件归属哪门课」这类配置。
    """
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

    try:
        return {**ingest_question_bank(course_id, store=store), **info}
    except Exception as exc:  # noqa: BLE001
        info["ingest_error"] = str(exc)
        return {"ok": False, "error": str(exc), **info}
