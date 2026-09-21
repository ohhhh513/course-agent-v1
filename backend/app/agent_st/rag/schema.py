from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

SOURCE_TYPES = (
    "question_stem",
    "question_analysis",
    "textbook",
    "ppt",
    "transcript",
)


@dataclass
class ParsedUnit:
    """解析器的原始产出。结构归属（章/知识点）不在此处推断 ——

    资源类切片由调用方从 `resources` 表继承，题库类切片由 `questions` 表带出。
    """
    text: str
    page: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)
    pre_chunked: bool = False
    source_type: str = "textbook"
    source_id: str = ""


@dataclass
class ChunkRecord:
    chunk_id: str
    text: str
    source_type: str
    source_id: str
    # 课程隔离：切片必须显式归属某门课，禁止默认值兜底
    course_id: str = ""
    # 课程结构归属（主库规范）：章 CH01-09 / 知识点 KP001-026，来自 graph_nodes
    # kp_id 为主知识点（单值），kp_ids 为全部知识点（JSON 数组）——与
    # resources / questions 两表的字段语义保持一致
    chapter_id: str = ""
    kp_id: str = ""
    kp_ids: list[str] = field(default_factory=list)
    # 题库切片的来源题号（主库 questions.q_id），资源类切片为空
    q_id: str = ""
    page_or_slide: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)
    embedding: list[float] | None = None
    embedding_model: str = ""

    def to_hit(self, score: float) -> dict[str, Any]:
        snippet = self.text if len(self.text) <= 400 else self.text[:400] + "…"
        return {
            "chunk_id": self.chunk_id,
            "text": snippet,
            "source_type": self.source_type,
            "source_id": self.source_id,
            "course_id": self.course_id,
            "chapter_id": self.chapter_id,
            "kp_id": self.kp_id,
            "kp_ids": list(self.kp_ids or []),
            "q_id": self.q_id,
            "page_or_slide": self.page_or_slide,
            "score": round(score, 4),
            "extra": self.extra,
        }

    def meta_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("embedding", None)
        return data
