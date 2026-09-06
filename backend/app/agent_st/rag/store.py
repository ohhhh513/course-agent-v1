from __future__ import annotations

import json
import sqlite3
import struct
from pathlib import Path

from app.agent_st.agent.config import get_settings
from app.agent_st.rag.schema import ChunkRecord

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_id TEXT NOT NULL,
    course_chapter INTEGER NOT NULL,
    section TEXT NOT NULL,
    question_id INTEGER,
    page_or_slide INTEGER,
    extra_json TEXT,
    embedding BLOB,
    embedding_model TEXT
);
CREATE INDEX IF NOT EXISTS idx_chunks_chapter ON chunks(course_chapter);
CREATE INDEX IF NOT EXISTS idx_chunks_section ON chunks(section);
CREATE INDEX IF NOT EXISTS idx_chunks_source ON chunks(source_type);
CREATE INDEX IF NOT EXISTS idx_chunks_qid ON chunks(question_id);
"""


def _pack(vec: list[float] | None) -> bytes | None:
    if not vec:
        return None
    return struct.pack(f"{len(vec)}f", *vec)


def _unpack(blob: bytes | None) -> list[float] | None:
    if not blob:
        return None
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))


class ChunkStore:
    def __init__(self, path: Path | None = None):
        settings = get_settings()
        self.path = Path(path or settings.rag_db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.executescript(CREATE_SQL)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def count(self) -> int:
        with self._conn() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM chunks").fetchone()
            return int(row["n"] if row else 0)

    def delete_source(self, source_id: str) -> int:
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM chunks WHERE source_id = ?", (source_id,))
            conn.commit()
            return cur.rowcount

    def delete_source_types(self, source_types: list[str]) -> int:
        if not source_types:
            return 0
        placeholders = ",".join("?" * len(source_types))
        with self._conn() as conn:
            cur = conn.execute(
                f"DELETE FROM chunks WHERE source_type IN ({placeholders})",
                source_types,
            )
            conn.commit()
            return cur.rowcount

    def upsert_many(self, records: list[ChunkRecord]) -> int:
        rows = [
            (
                r.chunk_id,
                r.text,
                r.source_type,
                r.source_id,
                r.course_chapter,
                r.section,
                r.question_id,
                r.page_or_slide,
                json.dumps(r.extra or {}, ensure_ascii=False),
                _pack(r.embedding),
                r.embedding_model,
            )
            for r in records
        ]
        with self._conn() as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO chunks (
                    chunk_id, text, source_type, source_id, course_chapter, section,
                    question_id, page_or_slide, extra_json, embedding, embedding_model
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            conn.commit()
        return len(rows)

    def load_filtered(
        self,
        course_chapter: int | None = None,
        section_prefix: str | None = None,
        source_types: list[str] | None = None,
    ) -> list[ChunkRecord]:
        clauses = ["1=1"]
        args: list = []
        if course_chapter:
            clauses.append("course_chapter = ?")
            args.append(course_chapter)
        if section_prefix:
            clauses.append("section LIKE ?")
            args.append(f"{section_prefix}%")
        if source_types:
            placeholders = ",".join("?" * len(source_types))
            clauses.append(f"source_type IN ({placeholders})")
            args.extend(source_types)
        sql = f"SELECT * FROM chunks WHERE {' AND '.join(clauses)}"
        with self._conn() as conn:
            rows = conn.execute(sql, args).fetchall()
        return [self._to_record(row) for row in rows]

    def embedding_model_counts(self) -> dict[str, int]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT COALESCE(embedding_model, '') AS model, COUNT(*) AS n "
                "FROM chunks GROUP BY model"
            ).fetchall()
        return {row["model"]: int(row["n"]) for row in rows}

    def stale_chunks(self, model: str) -> list[tuple[str, str]]:
        """返回向量缺失或由其它 embedding 模型生成的切片 (chunk_id, text)。

        切换 embedding 供应商/模型后，旧向量维度不同，cosine 恒为 0，
        检索会退化成“永远检索不到”。这里把它们挑出来重算。
        """
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT chunk_id, text FROM chunks "
                "WHERE embedding IS NULL OR COALESCE(embedding_model, '') <> ? "
                "ORDER BY chunk_id",
                (model,),
            ).fetchall()
        return [(row["chunk_id"], row["text"]) for row in rows]

    def update_embeddings(self, pairs: list[tuple[str, list[float]]], model: str) -> int:
        if not pairs:
            return 0
        rows = [(_pack(vec), model, chunk_id) for chunk_id, vec in pairs]
        with self._conn() as conn:
            conn.executemany(
                "UPDATE chunks SET embedding = ?, embedding_model = ? WHERE chunk_id = ?",
                rows,
            )
            conn.commit()
        return len(rows)

    def _to_record(self, row: sqlite3.Row) -> ChunkRecord:
        extra = json.loads(row["extra_json"] or "{}")
        return ChunkRecord(
            chunk_id=row["chunk_id"],
            text=row["text"],
            source_type=row["source_type"],
            source_id=row["source_id"],
            course_chapter=row["course_chapter"],
            section=row["section"],
            question_id=row["question_id"],
            page_or_slide=row["page_or_slide"],
            extra=extra,
            embedding=_unpack(row["embedding"]),
            embedding_model=row["embedding_model"] or "",
        )
