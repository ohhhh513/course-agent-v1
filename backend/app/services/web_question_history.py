"""教师近期联网题卡：复用消息 JSON，按用户/课程隔离，比较原题而非卡片 UUID。"""
from __future__ import annotations

from datetime import datetime, timedelta
from functools import lru_cache
import hashlib
import json
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy.exc import SQLAlchemyError

from app.config import settings
from app.database import SessionLocal
from app.models.ai import ChatMessage, ChatSession
from app.services.teacher_web_search import SearchFailure
from app.services.web_pdf import local_image
from app.services.web_question_text import canonical


_NUMBER = re.compile(r"^(?:[（(]\d+[）)](?=[A-Za-z\u4e00-\u9fff])|\d+[.、](?!\d)|第\d+题[:：.]?|例题?\d+[:：.]?)")
_FIGURE = re.compile(r"(?:图|[Ff]ig(?:ure)?\.?)[\s]*\d+(?:[-.]\d+)*")


def normalized(text: str, *, strip_number=True) -> str:
    value = canonical(text)[0]
    if strip_number:
        value = _NUMBER.sub("", value, count=1)
    value = _FIGURE.sub("图", value)
    value = re.sub(r"(?<![A-Za-z0-9_])_+(?![A-Za-z0-9_])|[（(][）)]", "〔空〕", value)
    return value.rstrip(".?")


def source_url(value: str) -> str:
    try:
        parts = urlsplit(value)
        query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                 if not k.lower().startswith("utm_") and k.lower() not in ("fbclid", "gclid")]
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, urlencode(sorted(query)), ""))
    except (TypeError, ValueError):
        return ""


@lru_cache(maxsize=256)
def _pixel_hash(path: str, modified: int, size: int) -> str:
    from PIL import Image
    try:
        with Image.open(path) as original:
            image = original.convert("RGB")
            try:
                return hashlib.sha256(str(image.size).encode() + image.tobytes()).hexdigest()
            finally:
                image.close()
    except (OSError, ValueError):
        return ""


def image_keys(question):
    keys = set()
    for item in question.get("images", []):
        url = item.get("url", "")
        if not url:
            continue
        keys.add("url:" + source_url(url))
        # 只读取服务端生成的本地 PDF 图片；比较不额外抓取外部图片。
        if local_image(url):
            path = settings.FRONTEND_DIR / url.lstrip("/")
            try:
                stat = path.stat()
                digest = _pixel_hash(str(path), stat.st_mtime_ns, stat.st_size)
                if digest:
                    keys.add("pixels:" + digest)
            except OSError:
                pass
    return keys


def profile(question):
    options = tuple(sorted(normalized(re.sub(r"^[A-H][.、)）]", "", canonical(item["text"])[0]), strip_number=False) for item in question.get("options", [])))
    return {"question": question, "stem": normalized(question["stem"]), "options": options,
            "source": source_url(question.get("sourceUrl", "")), "page": question.get("sourcePage"),
            "images": image_keys(question),
            "figures": tuple(_FIGURE.findall(canonical(question["stem"])[0])),
            "illustrated": bool(question.get("images") or question.get("requiresImage"))}


def same_profiles(left, right):
    same_source = bool(left["source"] and left["source"] == right["source"])
    same_page = bool(left["page"] and left["page"] == right["page"])
    # 同一份 PDF 的单题裁图可识别模型截取了不同长度题干的情况；整页预览不能套用。
    shared_pixels = {key for key in left["images"] & right["images"] if key.startswith("pixels:")}
    if same_source and same_page and left["question"].get("viewKind") == right["question"].get("viewKind") == "question_crop" and shared_pixels:
        return True
    if left["stem"] != right["stem"] or left["options"] != right["options"]:
        return False
    if not left["illustrated"] and not right["illustrated"]:
        return True
    if left["images"] & right["images"]:
        return True
    # 旧 PDF 卡片未存裁图坐标，使用同来源、同页、同图号承接；不同配图不只凭短题干合并。
    known_different_crops = (left["question"].get("viewKind") == right["question"].get("viewKind") == "question_crop"
                             and any(key.startswith("pixels:") for key in left["images"])
                             and any(key.startswith("pixels:") for key in right["images"]))
    return bool(not known_different_crops and same_source and same_page and left["figures"] and left["figures"] == right["figures"])


def same_question(left, right):
    return same_profiles(profile(left), profile(right))


def valid_question(value):
    if not isinstance(value, dict) or not isinstance(value.get("stem"), str) or not 4 <= len(value["stem"]) <= 6000:
        return False
    for field in ("options", "images"):
        entries = value.get(field, [])
        if not isinstance(entries, list) or len(entries) > (8 if field == "options" else 4):
            return False
        key = "text" if field == "options" else "url"
        if any(not isinstance(item, dict) or not isinstance(item.get(key), str) for item in entries):
            return False
    return isinstance(value.get("sourceUrl", ""), str)


def load_recent_questions(user_id: str, course_id: str) -> list[dict]:
    if not user_id or not course_id:
        raise SearchFailure("近期题目读取缺少用户或课程上下文，请重新选择课程。")
    try:
        with SessionLocal() as db:
            rows = (db.query(ChatMessage.tool_log).join(ChatSession, ChatSession.session_id == ChatMessage.session_id)
                    .filter(ChatSession.user_id == user_id, ChatSession.course_id == course_id,
                            ChatMessage.role == "ai", ChatMessage.created_at >= datetime.utcnow() - timedelta(days=30),
                            ChatMessage.tool_log.contains('"web_question"'))
                    .order_by(ChatMessage.id.desc()).limit(200).all())
    except SQLAlchemyError:
        raise SearchFailure("近期题目记录暂时无法读取，请稍后重试；本轮尚未完成去重。") from None
    questions = []
    for (raw,) in rows:
        try:
            entries = json.loads(raw or "[]")
        except (TypeError, ValueError):
            continue
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if isinstance(entry, dict) and entry.get("kind") == "web_question" and valid_question(entry.get("question")):
                questions.append(entry["question"])
    return questions


def repeat_requested(message: str) -> bool:
    """只在明确引用/重看原题时放行；“换一道/再找一道”仍默认新题。"""
    if re.search(r"(?:换|另外|不同|别的).{0,8}(?:题|一道)|再(?:找|来|搜|给)(?:给我|帮我|我|找){0,2}(?:一道|一个|一题|个)|不要重复|不重复|新题", message):
        return False
    reference = r"(?:上(?:一(?:道|个)?|道)|刚才(?:那道|的)?|之前(?:那道|的)?|原来(?:那道|的)?|这(?:一)?道|此|同一(?:道)?|原)题"
    return bool(re.search(r"(?:重看|再(?:给我)?看|再找|再来|重新(?:显示|展示|打开)|重复(?:显示|展示|一下)?).{0,12}(?:题|原图)|"
                          + reference + r".{0,16}(?:讲解|解释|解析|答案|重看|再看|显示|展示)|"
                          r"(?:讲解|解释|解析|重看|再看|显示|展示).{0,12}" + reference + r"|同一(?:道)?题", message))


class QuestionHistory:
    def __init__(self, questions, allow_repeat=False, enabled=True):
        self.questions = list(questions)
        self.profiles = [profile(q) for q in questions]
        self.allow_repeat = allow_repeat
        self.enabled = enabled
        self.current_profiles = []

    def duplicate(self, question):
        if not self.enabled:
            return None
        current = profile(question)
        return next((prior["question"] for prior in self.profiles if same_profiles(current, prior)), None)

    def duplicate_in_turn(self, question):
        current = profile(question)
        return any(same_profiles(current, prior) for prior in self.current_profiles)

    def remember(self, question):
        self.questions.insert(0, question)
        current = profile(question)
        self.profiles.insert(0, current)
        self.current_profiles.append(current)

    def summaries(self, limit=12):
        result, used = [], set()
        for prior in self.profiles:
            key = (prior["stem"], prior["options"])
            if key in used:
                continue
            used.add(key)
            question = prior["question"]
            result.append({"title": str(question.get("title") or "已用题")[:80], "stem": question["stem"][:500],
                           "sourceUrl": question.get("sourceUrl", ""), "sourcePage": question.get("sourcePage")})
            if len(result) >= limit:
                break
        return result

    def segment_seen(self, segment, page, source):
        if not self.enabled or self.allow_repeat:
            return False
        text = normalized(segment["text"])
        raw = canonical(segment["text"])[0]
        images = None
        for prior in self.profiles:
            if prior["source"] != source_url(source) or prior["page"] != page["pageNumber"]:
                continue
            if prior["stem"] in text and all(option in text for option in prior["options"]):
                if not prior["illustrated"]:
                    return True
                if images is None:
                    images = image_keys({"images": [{"url": segment["imageUrl"]}]})
                if prior["images"] & images:
                    return True
                known_different = (prior["question"].get("viewKind") == segment.get("viewKind") == "question_crop" and any(k.startswith("pixels:") for k in prior["images"])
                                   and any(k.startswith("pixels:") for k in images))
                if not known_different and prior["figures"] and all(figure in raw for figure in prior["figures"]):
                    return True
        return False


def current_history(ctx):
    key = "web_question_history"
    with ctx.turn_lock:
        if key not in ctx.turn:
            enabled = settings.TEACHER_WEB_QUESTION_DEDUP_ENABLED
            ctx.turn[key] = QuestionHistory(load_recent_questions(ctx.user_id, ctx.store.course_id) if enabled else [],
                                           allow_repeat=repeat_requested(str(ctx.extra.get("message") or "")), enabled=enabled)
        return ctx.turn[key]
