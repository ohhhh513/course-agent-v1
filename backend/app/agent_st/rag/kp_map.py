"""知识点 ↔ 王道小节、例题 id 解析。"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Iterable

# backend/app/agent_st/rag/kp_map.py → backend/kp_section_mapping.json
MAPPING_PATH = Path(__file__).resolve().parents[3] / "kp_section_mapping.json"

_KHD_RE = re.compile(r"^(?:KHD)?0*(\d+)$", re.I)


@lru_cache(maxsize=1)
def load_kp_section_map() -> dict[str, list[str]]:
    """KP id → 王道小节前缀列表。"""
    inverted: dict[str, list[str]] = {}
    if not MAPPING_PATH.exists():
        return inverted
    raw = json.loads(MAPPING_PATH.read_text(encoding="utf-8"))
    for section, kp_ids in raw.items():
        if str(section).startswith("_") or not isinstance(kp_ids, list):
            continue
        prefix = str(section).strip()
        for kp_id in kp_ids:
            key = str(kp_id)
            inverted.setdefault(key, [])
            if prefix not in inverted[key]:
                inverted[key].append(prefix)
    return inverted


def sections_for_kp_ids(kp_ids: Iterable[str] | None) -> list[str]:
    mapping = load_kp_section_map()
    seen: list[str] = []
    for kp_id in kp_ids or []:
        for prefix in mapping.get(str(kp_id), []):
            if prefix not in seen:
                seen.append(prefix)
    return seen


@lru_cache(maxsize=1)
def _section_to_kps() -> dict[str, list[str]]:
    """王道小节前缀 → KP id 列表（kp_section_mapping.json 正向）。"""
    out: dict[str, list[str]] = {}
    if not MAPPING_PATH.exists():
        return out
    raw = json.loads(MAPPING_PATH.read_text(encoding="utf-8"))
    for section, kp_ids in raw.items():
        if str(section).startswith("_") or not isinstance(kp_ids, list):
            continue
        out[str(section).strip()] = [str(k) for k in kp_ids]
    return out


def kps_for_section(prefix: str) -> list[str]:
    return _section_to_kps().get(str(prefix or "").strip(), [])


def parse_example_question_id(raw) -> int | None:
    """支持 12 / '12' / 'KHD012'。"""
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw if raw > 0 else None
    text = str(raw).strip()
    if not text:
        return None
    if text.isdigit():
        value = int(text)
        return value if value > 0 else None
    match = _KHD_RE.match(text)
    if match:
        value = int(match.group(1))
        return value if value > 0 else None
    return None


def parse_example_question_ids(raw_ids: Iterable | None) -> list[int]:
    out: list[int] = []
    for item in raw_ids or []:
        qid = parse_example_question_id(item)
        if qid is not None and qid not in out:
            out.append(qid)
    return out
