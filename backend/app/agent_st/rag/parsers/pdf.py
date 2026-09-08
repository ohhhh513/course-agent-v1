from __future__ import annotations

from pathlib import Path

from app.agent_st.rag.schema import ParsedUnit


class PdfParser:
    source_type = "textbook"

    def can_parse(self, path: Path) -> bool:
        return path.suffix.lower() == ".pdf"

    def parse(self, path: Path) -> list[ParsedUnit]:
        try:
            from pypdf import PdfReader
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("解析 PDF 需要安装 pypdf") from exc
        reader = PdfReader(str(path))
        units: list[ParsedUnit] = []
        for i, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            if not text:
                continue
            units.append(
                ParsedUnit(
                    text=text,
                    page=i,
                    source_type="textbook",
                    source_id=path.name,
                )
            )
        if not units:
            raise ValueError(f"PDF 未抽出文本：{path.name}")
        return units
