"""填空题：题干空位、可接受答案与判分。

不新增表或列。标准答案放在 questions.options（JSON 文本），
questions.answer 只存不超过 64 字的展示摘要，以适配现有字符串列。
学生端组卷不返回 options 里的答案。
"""
from __future__ import annotations

import json
import re

# 与学生端、教师端使用同一组空位记号：连续下划线，或一对空括号。
BLANK_MARK = re.compile(r"_{2,}|＿{2,}|（\s*）|\(\s*\)")
_SEGMENT = re.compile(r"[;；]")
_ALTERNATIVE = re.compile(r"[|｜]")
_FULLWIDTH = str.maketrans(
    "０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ",
    "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz",
)

MAX_BLANKS = 8
MAX_ALTERNATIVES = 8
MAX_ITEM_LEN = 200
STORED_ANSWER_LEN = 64
RECORD_ANSWER_LEN = 128


def is_blank_type(value) -> bool:
    return str(value or "").strip().lower() in {"blank", "填空", "填空题"}


def marker_count(stem: str) -> int:
    return len(BLANK_MARK.findall(stem or ""))


def normalize_blank(text: str) -> str:
    """判分用：去空白、全角字母数字转半角、英文不区分大小写。"""
    folded = str(text or "").replace("\u3000", " ").translate(_FULLWIDTH)
    return re.sub(r"\s+", "", folded).casefold()


def clip(text: str, limit: int) -> str:
    text = text or ""
    return text if len(text) <= limit else text[:limit]


def _alternatives(text: str) -> list[str]:
    return [part.strip() for part in _ALTERNATIVE.split(str(text or "")) if part.strip()]


def _specs_from_options(options, count: int):
    if not isinstance(options, list) or len(options) != count:
        return None
    specs = []
    for index, item in enumerate(options):
        if not isinstance(item, dict) or "accept" not in item:
            return None
        raw = item.get("accept")
        if isinstance(raw, str):
            raw = _alternatives(raw)
        if not isinstance(raw, list):
            return None
        accept = []
        for value in raw:
            text = str(value if value is not None else "").strip()
            if text:
                accept.append(text)
        if not accept or len(accept) > MAX_ALTERNATIVES or any(len(text) > MAX_ITEM_LEN for text in accept):
            return None
        specs.append({"blank": index + 1, "accept": accept})
    return specs


def _specs_from_answer(answer: str, count: int) -> list[dict]:
    text = str(answer or "").strip()
    if count <= 1:
        parts = [text]
    else:
        parts = [part.strip() for part in _SEGMENT.split(text)]
        if len(parts) != count:
            raise ValueError(f"题干有 {count} 个空，答案要用中文或英文分号分成 {count} 段")
    specs = []
    for index, part in enumerate(parts):
        accept = _alternatives(part)
        if not accept:
            raise ValueError(f"第 {index + 1} 空没有答案")
        if len(accept) > MAX_ALTERNATIVES or any(len(item) > MAX_ITEM_LEN for item in accept):
            raise ValueError(f"第 {index + 1} 空的答案过长，或可接受写法超过 {MAX_ALTERNATIVES} 个")
        specs.append({"blank": index + 1, "accept": accept})
    return specs


def pack_blank(stem: str, answer: str = "", options=None) -> dict:
    """整理成可入库的填空题。options 已是 accept 结构时优先使用，以保留多个可接受答案。"""
    count = marker_count(stem)
    if count == 0:
        count = 1
    if count > MAX_BLANKS:
        raise ValueError(f"一道题最多 {MAX_BLANKS} 个空")
    specs = _specs_from_options(options, count) or _specs_from_answer(answer, count)
    display = "；".join("|".join(item["accept"]) for item in specs)
    canonical = "；".join(item["accept"][0] for item in specs)
    return {
        "options": specs,
        "display": display,
        "canonical": canonical,
        "stored_answer": clip(canonical, STORED_ANSWER_LEN),
        "count": count,
    }


def load_specs(stem: str, options, answer: str = "") -> list[dict]:
    """读取已入库的填空题。结构损坏时退回 answer 列，仍无法解析则抛出 ValueError。"""
    parsed = options
    if isinstance(options, str):
        try:
            parsed = json.loads(options) if options else []
        except json.JSONDecodeError:
            parsed = []
    count = marker_count(stem) or 1
    specs = _specs_from_options(parsed, count)
    if specs:
        return specs
    return _specs_from_answer(answer, count)


def canonical_text(specs: list[dict]) -> str:
    return "；".join(item["accept"][0] for item in specs)


def student_parts(raw: str, count: int) -> list[str]:
    text = str(raw or "").strip()
    if text.startswith("["):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = None
        if isinstance(data, list):
            values = [str(item if item is not None else "") for item in data]
            if len(values) < count:
                values.extend([""] * (count - len(values)))
            return [item.strip() for item in values[:count]]
    if count <= 1:
        return [text]
    parts = [part.strip() for part in _SEGMENT.split(text)]
    if len(parts) == count:
        return parts
    return [text] + [""] * (count - 1)


def grade_submission(stem: str, options, stored_answer: str, submitted: str) -> dict:
    specs = load_specs(stem, options, stored_answer)
    parts = student_parts(submitted, len(specs))
    results = []
    correct = True
    for spec, given in zip(specs, parts):
        accepted = {normalize_blank(item) for item in spec["accept"]}
        matched = bool(given) and normalize_blank(given) in accepted
        correct = correct and matched
        results.append({
            "index": spec["blank"],
            "correct": matched,
            "expect": " / ".join(spec["accept"]),
        })
    return {
        "correct": correct,
        "results": results,
        "display": canonical_text(specs),
        "student_text": "；".join(parts),
    }


def student_view(question_type: str, stem: str, options, answer: str) -> dict:
    """学生可见字段。填空题不返回可接受答案。"""
    parsed = options
    if isinstance(options, str):
        try:
            parsed = json.loads(options) if options else []
        except json.JSONDecodeError:
            parsed = []
    if not isinstance(parsed, list):
        parsed = []
    if not is_blank_type(question_type):
        return {"blank": False, "type": question_type or "single", "options": parsed, "blanks": [], "answer": answer or ""}
    try:
        specs = load_specs(stem or "", parsed, answer or "")
    except ValueError:
        specs = []
    return {
        "blank": True,
        "type": "blank",
        "options": [],
        "blanks": [{"index": item["blank"]} for item in specs] or [{"index": 1}],
        "answer": canonical_text(specs) if specs else (answer or ""),
    }
