from __future__ import annotations

from pathlib import Path
from typing import Protocol

from app.agent_st.rag.schema import ParsedUnit


class Parser(Protocol):
    source_type: str

    def can_parse(self, path: Path) -> bool: ...

    def parse(self, path: Path) -> list[ParsedUnit]: ...


def split_text(text: str, min_size: int = 400, max_size: int = 800, overlap: int = 80) -> list[str]:
    raw = (text or "").strip()
    if not raw:
        return []
    if len(raw) <= max_size:
        return [raw]
    blocks: list[str] = []
    start = 0
    n = len(raw)
    while start < n:
        end = min(start + max_size, n)
        if end < n:
            window = raw[start:end]
            cut = max(window.rfind("\n"), window.rfind("。"), window.rfind("；"))
            if cut >= min_size // 2:
                end = start + cut + 1
        chunk = raw[start:end].strip()
        if chunk:
            blocks.append(chunk)
        if end >= n:
            break
        start = max(end - overlap, start + 1)
    return blocks
