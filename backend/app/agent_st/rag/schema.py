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
    text: str
    section_hint: str = ""
    page: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)
    pre_chunked: bool = False
    source_type: str = "textbook"
    source_id: str = ""
    question_id: int | None = None
    course_chapter: int | None = None
    section: str = ""


@dataclass
class ChunkRecord:
    chunk_id: str
    text: str
    source_type: str
    source_id: str
    course_chapter: int
    section: str
    question_id: int | None = None
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
            "course_chapter": self.course_chapter,
            "section": self.section,
            "question_id": self.question_id,
            "page_or_slide": self.page_or_slide,
            "score": round(score, 4),
            "extra": self.extra,
        }

    def meta_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("embedding", None)
        return data
