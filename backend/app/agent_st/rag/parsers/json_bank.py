from __future__ import annotations

import json
from pathlib import Path

from app.agent_st.rag.chapter_map import extra_from_question, map_section
from app.agent_st.rag.schema import ParsedUnit


class JsonBankParser:
    source_type = "question_stem"

    def can_parse(self, path: Path) -> bool:
        return path.suffix.lower() == ".json"

    def parse(self, path: Path) -> list[ParsedUnit]:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError("题库 JSON 必须是题目对象数组")
        units: list[ParsedUnit] = []
        for item in data:
            if not isinstance(item, dict) or item.get("id") is None:
                continue
            qid = int(item["id"])
            section = str(item.get("chapter") or "")
            course = map_section(section)
            extra = extra_from_question(item)
            options = item.get("options") or {}
            opt_text = "\n".join(f"{k}. {options.get(k, '')}" for k in ("A", "B", "C", "D"))
            stem = "\n".join(
                [
                    f"章节：{section}",
                    f"题干：{item.get('question') or ''}",
                    "选项：",
                    opt_text,
                ]
            )
            units.append(
                ParsedUnit(
                    text=stem,
                    section_hint=section,
                    pre_chunked=True,
                    source_type="question_stem",
                    source_id=str(qid),
                    question_id=qid,
                    course_chapter=course["id"],
                    section=section,
                    extra=extra,
                )
            )
            analysis = str(item.get("analysis") or "").strip() or "（本题暂无解析）"
            units.append(
                ParsedUnit(
                    text=f"章节：{section}\n解析：{analysis}",
                    section_hint=section,
                    pre_chunked=True,
                    source_type="question_analysis",
                    source_id=str(qid),
                    question_id=qid,
                    course_chapter=course["id"],
                    section=section,
                    extra=extra,
                )
            )
        return units
