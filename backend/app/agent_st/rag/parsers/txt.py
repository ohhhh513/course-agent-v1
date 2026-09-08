from __future__ import annotations

from pathlib import Path

from app.agent_st.rag.schema import ParsedUnit


class TxtParser:
    source_type = "textbook"

    def can_parse(self, path: Path) -> bool:
        return path.suffix.lower() in {".txt", ".md"}

    def parse(self, path: Path) -> list[ParsedUnit]:
        text = path.read_text(encoding="utf-8")
        return [
            ParsedUnit(
                text=text,
                source_type="transcript" if "transcript" in path.name.lower() else "textbook",
                source_id=path.name,
            )
        ]
