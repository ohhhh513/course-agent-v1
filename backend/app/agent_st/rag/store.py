from __future__ import annotations

import json
import sqlite3
import struct
from pathlib import Path

from app.agent_st.agent.config import get_settings
from app.agent_st.rag.schema import ChunkRecord

# 建表列定义 ----------
# 两条硬约束（都来自踩过的坑）：
#   1) course_id NOT NULL 且**不给默认值** —— 历史 DEFAULT 'C2026DS001' 会把
#      漏传课程的写入静默挂到演示课下，是跨课程串数据的根因。
#   2) chapter_id / kp_id 用主库规范的结构 id（CH01-09 / KP001-026），
#      不再用「章序号 + 王道小节」——那套已整体废除（docs/主库数据规范.md）。
_COLUMNS = """
    chunk_id TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_id TEXT NOT NULL,
    course_id TEXT NOT NULL,
    chapter_id TEXT NOT NULL DEFAULT '',
    kp_id TEXT NOT NULL DEFAULT '',
    kp_ids TEXT NOT NULL DEFAULT '[]',
    q_id TEXT NOT NULL DEFAULT '',
    page_or_slide INTEGER,
    extra_json TEXT,
    embedding BLOB,
    embedding_model TEXT
"""

_TABLE_SQL = f"CREATE TABLE IF NOT EXISTS chunks ({_COLUMNS})"

_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_chunks_course ON chunks(course_id);
CREATE INDEX IF NOT EXISTS idx_chunks_chapter ON chunks(chapter_id);
CREATE INDEX IF NOT EXISTS idx_chunks_kp ON chunks(kp_id);
CREATE INDEX IF NOT EXISTS idx_chunks_source ON chunks(source_type);
CREATE INDEX IF NOT EXISTS idx_chunks_qid ON chunks(q_id);
"""

_COLUMN_ORDER = (
    "chunk_id", "text", "source_type", "source_id", "course_id",
    "chapter_id", "kp_id", "kp_ids", "q_id", "page_or_slide",
    "extra_json", "embedding", "embedding_model",
)


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
    """rag.db 的读写入口。所有业务方法都以 course_id 为第一等公民。"""

    def __init__(self, path: Path | None = None):
        settings = get_settings()
        self.path = Path(path or settings.rag_db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            self._ensure_schema(conn)

    # ------------------------------------------------------------------
    # 结构
    # ------------------------------------------------------------------
    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        """建表 / 结构变更自动重建。

        切片是**可再生的派生数据**（由 resources / questions 重新切出来即可），
        因此列定义不匹配时直接重建空表，而不是写迁移兼容代码。
        """
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='chunks'"
        ).fetchone()
        if row is not None:
            existing = {r[1] for r in conn.execute("PRAGMA table_info(chunks)").fetchall()}
            if existing != set(_COLUMN_ORDER):
                conn.execute("DROP TABLE chunks")
                conn.commit()
        conn.execute(_TABLE_SQL)
        conn.executescript(_INDEX_SQL)
        conn.commit()

    # ------------------------------------------------------------------
    # 读
    # ------------------------------------------------------------------
    def count(self, course_id: str | None = None) -> int:
        with self._conn() as conn:
            if course_id:
                row = conn.execute(
                    "SELECT COUNT(*) AS n FROM chunks WHERE course_id = ?", (course_id,)
                ).fetchone()
            else:
                row = conn.execute("SELECT COUNT(*) AS n FROM chunks").fetchone()
            return int(row["n"] if row else 0)

    def course_counts(self) -> dict[str, int]:
        """各课程的切片数（含空串等未归属值，供运维对账）"""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT course_id, COUNT(*) AS n FROM chunks GROUP BY course_id ORDER BY course_id"
            ).fetchall()
        return {row["course_id"]: int(row["n"]) for row in rows}

    def source_counts(self, course_id: str) -> dict[str, int]:
        """某课程下各 source_id 的切片数"""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT source_id, COUNT(*) AS n FROM chunks WHERE course_id = ? "
                "GROUP BY source_id ORDER BY n DESC, source_id",
                (course_id,),
            ).fetchall()
        return {row["source_id"]: int(row["n"]) for row in rows}

    def kp_coverage(self, course_id: str) -> dict[str, int]:
        """某课程各知识点的切片数（对齐主库规范的结构视图）"""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT kp_id, COUNT(*) AS n FROM chunks "
                "WHERE course_id = ? AND kp_id <> '' GROUP BY kp_id ORDER BY kp_id",
                (course_id,),
            ).fetchall()
        return {row["kp_id"]: int(row["n"]) for row in rows}

    def load_filtered(
        self,
        course_id: str,
        chapter_id: str | None = None,
        kp_ids: list[str] | None = None,
        source_types: list[str] | None = None,
    ) -> list[ChunkRecord]:
        """按课程取切片。course_id 必填 —— 缺失时返回空集（fail-closed），

        不做「不过滤全库混搜」的兜底：那正是跨课程串数据的根源。

        `kp_ids` 支持**多个知识点**，语义为「命中任一」（并集）。每条候选 KP
        都按当前主 KP（`kp_id`）或挂载列表（`kp_ids` JSON 元素）匹配，
        所以挂了多 KP 的课件（如 `["KP024","KP023"]`）在任一 KP 下都能被查到。
        列表内的具体值全部走参数绑定，不做字符串拼接。
        """
        if not course_id:
            return []
        clauses = ["course_id = ?"]
        args: list = [course_id]
        if chapter_id:
            clauses.append("chapter_id = ?")
            args.append(chapter_id)
        want = [str(k).strip() for k in (kp_ids or []) if str(k).strip()]
        if want:
            parts = []
            for kp in want:
                parts.append("(kp_id = ? OR kp_ids LIKE ?)")
                args.extend([kp, f'%"{kp}"%'])
            clauses.append("(" + " OR ".join(parts) + ")")
        if source_types:
            placeholders = ",".join("?" * len(source_types))
            clauses.append(f"source_type IN ({placeholders})")
            args.extend(source_types)
        sql = f"SELECT * FROM chunks WHERE {' AND '.join(clauses)}"
        with self._conn() as conn:
            rows = conn.execute(sql, args).fetchall()
        return [self._to_record(row) for row in rows]

    def embedding_model_counts(self, course_id: str | None = None) -> dict[str, int]:
        sql = "SELECT COALESCE(embedding_model, '') AS model, COUNT(*) AS n FROM chunks"
        args: list = []
        if course_id:
            sql += " WHERE course_id = ?"
            args.append(course_id)
        sql += " GROUP BY model"
        with self._conn() as conn:
            rows = conn.execute(sql, args).fetchall()
        return {row["model"]: int(row["n"]) for row in rows}

    def stale_chunks(self, model: str, course_id: str | None = None) -> list[tuple[str, str]]:
        """返回向量缺失或由其它 embedding 模型生成的切片 (chunk_id, text)。

        切换 embedding 供应商/模型后，旧向量维度不同，cosine 恒为 0，
        检索会退化成“永远检索不到”。这里把它们挑出来重算。
        """
        sql = (
            "SELECT chunk_id, text FROM chunks "
            "WHERE (embedding IS NULL OR COALESCE(embedding_model, '') <> ?)"
        )
        args: list = [model]
        if course_id:
            sql += " AND course_id = ?"
            args.append(course_id)
        sql += " ORDER BY chunk_id"
        with self._conn() as conn:
            rows = conn.execute(sql, args).fetchall()
        return [(row["chunk_id"], row["text"]) for row in rows]

    # ------------------------------------------------------------------
    # 写
    # ------------------------------------------------------------------
    def upsert_many(self, records: list[ChunkRecord]) -> int:
        missing = [r.chunk_id for r in records if not r.course_id]
        if missing:
            raise ValueError(f"切片缺少 course_id，拒绝写入：{missing[:3]}")
        rows = [
            (
                r.chunk_id,
                r.text,
                r.source_type,
                r.source_id,
                r.course_id,
                r.chapter_id or "",
                r.kp_id or "",
                json.dumps(list(r.kp_ids or []), ensure_ascii=False),
                r.q_id or "",
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
                    chunk_id, text, source_type, source_id, course_id,
                    chapter_id, kp_id, kp_ids, q_id, page_or_slide,
                    extra_json, embedding, embedding_model
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            conn.commit()
        return len(rows)

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

    # ------------------------------------------------------------------
    # 删（全部要求显式课程，杜绝跨课程误删）
    # ------------------------------------------------------------------
    def delete_source(self, source_id: str, course_id: str) -> int:
        if not course_id:
            raise ValueError("delete_source 必须指定 course_id")
        with self._conn() as conn:
            cur = conn.execute(
                "DELETE FROM chunks WHERE source_id = ? AND course_id = ?",
                (source_id, course_id),
            )
            conn.commit()
            return cur.rowcount

    def delete_source_prefix(self, prefix: str, course_id: str) -> int:
        """按 source_id 前缀删除某课程的切片。

        资源删除用：source_id 规范为 `{res_id}/{文件名}`，因此用
        `{res_id}/` 作前缀可一次清掉该资源下所有文件（含多文件、改名）的切片，
        且不会波及其它资源或其它课程。
        """
        if not prefix:
            raise ValueError("delete_source_prefix 必须指定非空前缀")
        if not course_id:
            raise ValueError("delete_source_prefix 必须指定 course_id")
        with self._conn() as conn:
            cur = conn.execute(
                "DELETE FROM chunks WHERE source_id LIKE ? AND course_id = ?",
                (f"{prefix}%", course_id),
            )
            conn.commit()
            return cur.rowcount

    def delete_source_types(self, source_types: list[str], course_id: str) -> int:
        """删除某课程下指定来源类型的切片（旧实现无课程条件，会清掉所有课程）"""
        if not source_types:
            return 0
        if not course_id:
            raise ValueError("delete_source_types 必须指定 course_id")
        placeholders = ",".join("?" * len(source_types))
        with self._conn() as conn:
            cur = conn.execute(
                f"DELETE FROM chunks WHERE source_type IN ({placeholders}) AND course_id = ?",
                [*source_types, course_id],
            )
            conn.commit()
            return cur.rowcount

    def delete_course(self, course_id: str) -> int:
        """清空某课程的全部切片（课程删除 / 数据纠偏用）"""
        if not course_id:
            raise ValueError("delete_course 必须指定非空 course_id")
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM chunks WHERE course_id = ?", (course_id,))
            conn.commit()
            return cur.rowcount

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------
    def _to_record(self, row: sqlite3.Row) -> ChunkRecord:
        extra = json.loads(row["extra_json"] or "{}")
        try:
            kp_ids = json.loads(row["kp_ids"] or "[]")
        except json.JSONDecodeError:
            kp_ids = []
        return ChunkRecord(
            chunk_id=row["chunk_id"],
            text=row["text"],
            source_type=row["source_type"],
            source_id=row["source_id"],
            course_id=row["course_id"],
            chapter_id=row["chapter_id"] or "",
            kp_id=row["kp_id"] or "",
            kp_ids=kp_ids if isinstance(kp_ids, list) else [],
            q_id=row["q_id"] or "",
            page_or_slide=row["page_or_slide"],
            extra=extra,
            embedding=_unpack(row["embedding"]),
            embedding_model=row["embedding_model"] or "",
        )
