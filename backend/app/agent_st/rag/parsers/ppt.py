from __future__ import annotations

import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from app.agent_st.rag.schema import ParsedUnit


class PptParser:
    """抽取 PPTX 幻灯片文本。旧版 .ppt 需先另存为 .pptx 或 PDF。"""

    source_type = "ppt"

    def can_parse(self, path: Path) -> bool:
        return path.suffix.lower() in {".pptx", ".ppt"}

    def parse(self, path: Path) -> list[ParsedUnit]:
        if path.suffix.lower() == ".ppt":
            raise ValueError("暂不解析二进制 .ppt，请另存为 .pptx 或 PDF 后再入库")
        units: list[ParsedUnit] = []
        with zipfile.ZipFile(path) as zf:
            names = sorted(
                n for n in zf.namelist() if n.startswith("ppt/slides/slide") and n.endswith(".xml")
            )
            for i, name in enumerate(names, start=1):
                root = ET.fromstring(zf.read(name))
                texts = [node.text for node in root.iter() if node.tag.endswith("}t") and node.text]
                text = "\n".join(texts).strip()
                if not text:
                    continue
                units.append(
                    ParsedUnit(
                        text=text,
                        page=i,
                        source_type="ppt",
                        source_id=path.name,
                    )
                )
        if not units:
            raise ValueError(f"PPTX 未抽出文本：{path.name}")
        return units
