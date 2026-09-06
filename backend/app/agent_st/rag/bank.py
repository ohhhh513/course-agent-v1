from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from app.agent_st.agent.config import get_settings
from app.agent_st.rag.chapter_map import figure_mode, map_section, normalize


@lru_cache(maxsize=4)
def load_questions(path: str | None = None) -> list[dict]:
    settings = get_settings()
    target = Path(path or settings.bank_path)
    if not target.exists():
        # 题库文件尚未就位（导入脚本未运行）：返回空库而不是崩溃，讲解/出题会提示未检索到原文
        return []
    raw = json.loads(target.read_text(encoding="utf-8"))
    return [item for item in raw if isinstance(item, dict) and item.get("id") is not None]


def get_question(question_id: int, include_answer: bool = True) -> dict | None:
    for item in load_questions():
        if int(item["id"]) == int(question_id):
            data = normalize(item)
            data["raw"] = {
                "chapter": item.get("chapter"),
                "has_image": bool(item.get("has_image")),
                "graph": item.get("graph"),
                "options_graph": item.get("options_graph"),
            }
            if not include_answer:
                data = dict(data)
                data.pop("answer", None)
                data.pop("analysis", None)
            return data
    return None


def existing_ids() -> set[int]:
    return {int(item["id"]) for item in load_questions()}


def search_similar(
    course_chapter: int | None = None,
    section_prefix: str | None = None,
    figure: str | None = None,
    graph_type: str | None = None,
    exclude_id: int | None = None,
    limit: int = 3,
    include_answer: bool = False,
) -> list[dict]:
    hits: list[dict] = []
    for item in load_questions():
        qid = int(item["id"])
        if exclude_id is not None and qid == int(exclude_id):
            continue
        course = map_section(item.get("chapter"))
        if course_chapter and course["id"] != int(course_chapter):
            continue
        section = str(item.get("chapter") or "")
        if section_prefix and not section.startswith(section_prefix):
            continue
        mode = figure_mode(item)
        if figure and mode != figure:
            continue
        gtype = (item.get("graph") or {}).get("type")
        if graph_type and gtype != graph_type:
            continue
        payload = {
            "id": qid,
            "chapter": item.get("chapter"),
            "question": item.get("question"),
            "options": item.get("options"),
            "has_image": bool(item.get("has_image")),
            "figure_mode": mode,
            "graph": item.get("graph"),
            "options_graph": item.get("options_graph"),
        }
        if include_answer:
            payload["answer"] = item.get("answer")
            payload["analysis"] = item.get("analysis")
        hits.append(payload)
        if len(hits) >= limit:
            break
    return hits
