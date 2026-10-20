"""课程学情摘要：每五分钟增量整理学生智能答疑，不保存原始问句。"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.database import SessionLocal
from app.models.ai import ChatMessage, ChatSession
from app.models.course import Course
from app.models.graph import GraphNode, LearningPath
from app.models.intervention import TeacherClassDashboard
from app.models.practice import AnswerRecord
from app.models.user import User
from app.models.user_course import UserCourse

logger = logging.getLogger(__name__)

DATA_TYPE = "ai_daily_analysis"
RUN_DATA_TYPE = "ai_daily_run"
RETENTION_DAYS = 30
BACKFILL_DAYS = 7
MAX_QUESTIONS_PER_BATCH = 40
SHANGHAI = ZoneInfo("Asia/Shanghai")

_scheduler = None


def _key(*parts: str) -> str:
    value = "|".join(str(part or "") for part in parts)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]


def _student_key(course_id: str, user_id: str) -> str:
    return _key("student", course_id, user_id)


def _run_key(course_id: str, day: date) -> str:
    return _key("run", course_id, day.isoformat())


def _utc_day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=SHANGHAI)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=SHANGHAI)
    return (
        start.astimezone(timezone.utc).replace(tzinfo=None),
        end.astimezone(timezone.utc).replace(tzinfo=None),
    )


def _loads_dict(raw: str | None) -> dict:
    try:
        value = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _read_student_days(db, course_id: str, user_id: str) -> list[dict]:
    rows = db.query(TeacherClassDashboard).filter(
        TeacherClassDashboard.data_type == DATA_TYPE,
        TeacherClassDashboard.class_id.is_(None),
        TeacherClassDashboard.data_key == _student_key(course_id, user_id),
    ).order_by(TeacherClassDashboard.id.desc()).all()
    by_date: dict[str, dict] = {}
    for row in rows:
        value = _loads_dict(row.data_json)
        if value.get("courseId") != course_id or value.get("studentId") != user_id:
            continue
        for item in value.get("daily") or []:
            if isinstance(item, dict) and item.get("date"):
                by_date[str(item["date"])] = item
    return [by_date[key] for key in sorted(by_date)]


def _student_day(db, course_id: str, user_id: str, day: date) -> dict | None:
    target = day.isoformat()
    return next((item for item in _read_student_days(db, course_id, user_id)
                 if item.get("date") == target), None)


def _save_student_day(db, course_id: str, user_id: str, snapshot: dict) -> None:
    key = _student_key(course_id, user_id)
    rows = db.query(TeacherClassDashboard).filter(
        TeacherClassDashboard.data_type == DATA_TYPE,
        TeacherClassDashboard.class_id.is_(None),
        TeacherClassDashboard.data_key == key,
    ).order_by(TeacherClassDashboard.id.asc()).all()
    by_date: dict[str, dict] = {}
    valid_rows = []
    for row in rows:
        value = _loads_dict(row.data_json)
        if value.get("courseId") != course_id or value.get("studentId") != user_id:
            continue
        valid_rows.append(row)
        for item in value.get("daily") or []:
            if isinstance(item, dict) and item.get("date"):
                by_date[str(item["date"])] = item

    by_date[snapshot["date"]] = snapshot
    cutoff = (date.fromisoformat(snapshot["date"]) - timedelta(days=RETENTION_DAYS - 1)).isoformat()
    retained = [by_date[key] for key in sorted(by_date) if key >= cutoff]
    payload = json.dumps({
        "version": 1,
        "courseId": course_id,
        "studentId": user_id,
        "daily": retained,
    }, ensure_ascii=False)
    row = valid_rows[0] if valid_rows else None
    if row is None:
        row = TeacherClassDashboard(
            class_id=None,
            data_type=DATA_TYPE,
            data_key=key,
            data_json=payload,
        )
        db.add(row)
    else:
        row.data_json = payload
        row.updated_at = datetime.utcnow()
        for duplicate in valid_rows[1:]:
            db.delete(duplicate)
    db.commit()


def _save_run(db, course_id: str, day: date, payload: dict) -> None:
    key = _run_key(course_id, day)
    rows = db.query(TeacherClassDashboard).filter(
        TeacherClassDashboard.data_type == RUN_DATA_TYPE,
        TeacherClassDashboard.class_id.is_(None),
        TeacherClassDashboard.data_key == key,
    ).order_by(TeacherClassDashboard.id.asc()).all()
    data_json = json.dumps(payload, ensure_ascii=False)
    if rows:
        rows[0].data_json = data_json
        rows[0].updated_at = datetime.utcnow()
        for duplicate in rows[1:]:
            db.delete(duplicate)
    else:
        db.add(TeacherClassDashboard(
            class_id=None,
            data_type=RUN_DATA_TYPE,
            data_key=key,
            data_json=data_json,
        ))
    db.commit()


def _prune_student_summaries(db, cutoff: str) -> None:
    """删除保留期外的逐日摘要，避免不再活跃学生的历史摘要长期残留。"""
    rows = db.query(TeacherClassDashboard).filter(
        TeacherClassDashboard.data_type == DATA_TYPE,
        TeacherClassDashboard.class_id.is_(None),
    ).all()
    for row in rows:
        payload = _loads_dict(row.data_json)
        daily = payload.get("daily")
        if not isinstance(daily, list):
            continue
        retained = [
            item for item in daily
            if isinstance(item, dict) and str(item.get("date") or "") >= cutoff
        ]
        if len(retained) == len(daily):
            continue
        if not retained:
            db.delete(row)
            continue
        payload["daily"] = retained
        row.data_json = json.dumps(payload, ensure_ascii=False)
        row.updated_at = datetime.utcnow()


def _course_catalog(db, course_id: str) -> list[dict]:
    rows = db.query(GraphNode.id, GraphNode.name, GraphNode.chapter).filter(
        GraphNode.course_id == course_id,
        GraphNode.graph_type == "knowledge",
    ).order_by(GraphNode.chapter, GraphNode.id).all()
    return [{"kpId": row.id, "name": row.name or row.id, "chapter": row.chapter or ""} for row in rows]


def _practice_for_day(db, course_id: str, user_id: str, day: date, catalog: list[dict]) -> dict:
    start, end = _utc_day_bounds(day)
    rows = db.query(AnswerRecord.kp_id, AnswerRecord.is_correct).filter(
        AnswerRecord.course_id == course_id,
        AnswerRecord.user_id == user_id,
        AnswerRecord.created_at >= start,
        AnswerRecord.created_at < end,
    ).all()
    correct = sum(1 for _kp, is_correct in rows if bool(is_correct))
    wrong_by_kp = Counter((kp or "").strip() for kp, is_correct in rows if not bool(is_correct))
    names = {item["kpId"]: item["name"] for item in catalog}
    chapters = {item["kpId"]: item["chapter"] for item in catalog}
    total = len(rows)
    wrong = total - correct
    return {
        "answerCount": total,
        "correctCount": correct,
        "wrongCount": wrong,
        "accuracy": round(correct / total * 100, 1) if total else None,
        "wrongByKp": [
            {"kpId": kp, "kpName": names.get(kp, kp or "未关联知识点"),
             "chapter": chapters.get(kp, ""), "wrongCount": count}
            for kp, count in wrong_by_kp.most_common(8)
        ],
    }


def _learning_for_day(db, course_id: str, user_id: str) -> dict:
    rows = db.query(LearningPath.status, LearningPath.mastery).filter(
        LearningPath.course_id == course_id,
        LearningPath.user_id == user_id,
    ).all()
    total = len(rows)
    done = sum(1 for status, _mastery in rows if status == "done")
    mastery_values = [float(mastery) for _status, mastery in rows if mastery is not None and float(mastery) > 0]
    return {
        "pathSteps": total,
        "completedSteps": done,
        "completionPercent": round(done / total * 100, 1) if total else None,
        "averageMastery": round(sum(mastery_values) / len(mastery_values), 1) if mastery_values else None,
    }


def _question_query(db, course_id: str, user_id: str, day: date):
    start, end = _utc_day_bounds(day)
    return db.query(ChatMessage.id, ChatMessage.content).join(
        ChatSession, ChatSession.session_id == ChatMessage.session_id,
    ).join(User, User.user_id == ChatSession.user_id).join(
        UserCourse, UserCourse.user_id == ChatSession.user_id,
    ).filter(
        ChatSession.course_id == course_id,
        ChatSession.user_id == user_id,
        ChatSession.flow_id == "explain",
        User.role == "student",
        UserCourse.course_id == course_id,
        ChatMessage.role == "me",
        ChatMessage.created_at >= start,
        ChatMessage.created_at < end,
    )


def _get_questions(db, course_id: str, user_id: str, day: date) -> tuple[list[tuple[int, str]], int, int]:
    """读取某日历史问题；返回最多 40 条样本、有效问题数和当天最大消息 ID。"""
    rows = _question_query(db, course_id, user_id, day).order_by(
        ChatMessage.created_at.asc(), ChatMessage.id.asc(),
    ).all()
    valid = [(int(message_id), str(content or "").strip())
             for message_id, content in rows if len(str(content or "").strip()) >= 2]
    last_message_id = max((int(message_id) for message_id, _content in rows), default=0)
    return valid[-MAX_QUESTIONS_PER_BATCH:], len(valid), last_message_id


def _get_new_questions(
    db, course_id: str, user_id: str, day: date, after_message_id: int,
) -> tuple[list[tuple[int, str]], int, int, bool]:
    """读取游标之后的新问题；每轮最多分析 40 条并按消息 ID 推进游标。"""
    rows = _question_query(db, course_id, user_id, day).filter(
        ChatMessage.id > max(0, int(after_message_id or 0)),
    ).order_by(ChatMessage.id.asc()).limit(200).all()
    if not rows:
        return [], 0, int(after_message_id or 0), False

    valid = [(int(message_id), str(content or "").strip())
             for message_id, content in rows if len(str(content or "").strip()) >= 2]
    selected = valid[:MAX_QUESTIONS_PER_BATCH]
    if len(valid) > MAX_QUESTIONS_PER_BATCH:
        # 留下尚未分析的有效问题，下一轮从该 ID 之后继续处理。
        watermark = selected[-1][0]
    else:
        watermark = int(rows[-1][0])
    return selected, len(selected), watermark, True


def _parse_json_object(content: str) -> dict:
    text = (content or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        return {}
    try:
        value = json.loads(text[start:end + 1])
    except (ValueError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


def _confidence(question_count: int, wrong_count: int) -> str:
    if question_count >= 3 and wrong_count >= 2:
        return "较强"
    if question_count >= 2 or wrong_count >= 2:
        return "一般"
    return "有限"


def _normalise_topics(
    raw_topics,
    question_count: int,
    catalog: list[dict],
    practice: dict,
    source_texts: list[str] | None = None,
) -> list[dict]:
    catalog_by_id = {item["kpId"]: item for item in catalog}
    wrong_by_id = {item["kpId"]: int(item["wrongCount"]) for item in practice.get("wrongByKp") or []}
    topics = []
    seen = set()
    for raw in raw_topics if isinstance(raw_topics, list) else []:
        if not isinstance(raw, dict):
            continue
        kp_id = str(raw.get("kpId") or "").strip()
        course_kp = catalog_by_id.get(kp_id)
        if not course_kp or kp_id in seen:
            continue
        indexes = raw.get("questionIndexes") or []
        indexes = [i for i in indexes if isinstance(i, int) and 1 <= i <= question_count]
        if not indexes:
            continue
        seen.add(kp_id)
        q_count = len(set(indexes))
        wrong_count = wrong_by_id.get(kp_id, 0)
        concern = str(raw.get("likelyDoubt") or "").strip()
        concern = re.sub(r"[\r\n\t\"'“”‘’`]+", " ", concern)
        concern = re.sub(r"\s+", " ", concern)[:100]
        normalized_concern = re.sub(r"[\W_]+", "", concern).lower()
        repeats_source = any(
            len(normalized_source := re.sub(r"[\W_]+", "", source or "").lower()) >= 12
            and normalized_concern
            and (normalized_source in normalized_concern or normalized_concern in normalized_source)
            for source in (source_texts or [])
        )
        if repeats_source:
            concern = "已按知识点归纳；摘要不复述学生原始问句"
        if not concern:
            concern = "该知识点出现相关提问，单凭提问不能判断为掌握薄弱"
        topics.append({
            "kpId": kp_id,
            "kpName": course_kp["name"],
            "chapter": course_kp["chapter"],
            "questionCount": q_count,
            "wrongAnswerCount": wrong_count,
            "likelyDoubt": concern,
            "confidence": _confidence(q_count, wrong_count),
        })
    return sorted(topics, key=lambda item: (
        -(item["questionCount"] + item["wrongAnswerCount"]), item["kpName"],
    ))[:8]


def _llm_topics(course_id: str, texts: list[str], catalog: list[dict], practice: dict) -> list[dict] | None:
    if not texts or not catalog:
        return []
    try:
        from app.agent_st.agent.llm import chat_available, complete

        if not chat_available():
            return None
        messages = [
            {
                "role": "system",
                "content": (
                    "你是课程学情分析器。只分析输入中当天的学生课程问答和当天练习数据。"
                    "请把问题映射到给定课程知识点；questionIndexes 必须引用输入问题编号。"
                    "likelyDoubt 用简短、概括性的中文描述学生可能需要进一步澄清的概念，"
                    "不得引用、复述或输出原始问句，不得根据单次提问断言学生薄弱。"
                    "只有存在清晰依据时才输出该知识点；没有可靠映射就省略。"
                    "严格只返回 JSON：{\"topics\":[{\"kpId\":\"目录中的知识点 id\","
                    "\"questionIndexes\":[1],\"likelyDoubt\":\"概括性疑惑\"}]}。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps({
                    "catalog": catalog,
                    "questions": [
                        {"index": index, "text": text[:900]}
                        for index, text in enumerate(texts, 1)
                    ],
                    "sameDayWrongAnswers": practice.get("wrongByKp") or [],
                }, ensure_ascii=False),
            },
        ]
        response = complete(messages, None)
        parsed = _parse_json_object(response.get("content") or "")
        if not isinstance(parsed.get("topics"), list):
            return None
        return _normalise_topics(
            parsed.get("topics"), len(texts), catalog, practice, source_texts=texts,
        )
    except Exception as exc:
        logger.warning("incremental student AI analysis unavailable (%s)", type(exc).__name__)
        return None


def _rule_topics(course_id: str, texts: list[str], catalog: list[dict], practice: dict) -> list[dict]:
    from app.agent_st.rag.topic import match_terms

    matched: dict[str, list[int]] = defaultdict(list)
    for index, text in enumerate(texts, 1):
        for hit in match_terms(course_id, text):
            matched[str(hit.get("kp_id") or "")].append(index)
    raw = []
    wrong_by_id = {item["kpId"]: int(item["wrongCount"]) for item in practice.get("wrongByKp") or []}
    for kp_id, indexes in matched.items():
        wrong_count = wrong_by_id.get(kp_id, 0)
        if len(indexes) >= 2 and wrong_count:
            concern = "同一知识点多次提问，且当天有答错记录，建议核实相关概念或解题步骤"
        elif len(indexes) >= 2:
            concern = "同一知识点多次提问，可能仍有概念或步骤需要澄清"
        elif wrong_count:
            concern = "有相关提问且当天出现答错记录，建议结合后续练习确认理解情况"
        else:
            concern = "出现相关提问；单次提问不足以判断为薄弱点"
        raw.append({"kpId": kp_id, "questionIndexes": indexes, "likelyDoubt": concern})
    return _normalise_topics(raw, len(texts), catalog, practice, source_texts=texts)


def _course_student_ids(db, course_id: str) -> list[str]:
    rows = db.query(UserCourse.user_id).join(
        User, User.user_id == UserCourse.user_id,
    ).filter(
        UserCourse.course_id == course_id,
        User.role == "student",
    ).all()
    return list(dict.fromkeys(row[0] for row in rows if row[0]))


def _course_day_has_questions(db, course_id: str, user_id: str, day: date) -> bool:
    start, end = _utc_day_bounds(day)
    return bool(db.query(ChatMessage.id).join(
        ChatSession, ChatSession.session_id == ChatMessage.session_id,
    ).filter(
        ChatSession.course_id == course_id,
        ChatSession.user_id == user_id,
        ChatSession.flow_id == "explain",
        ChatMessage.role == "me",
        ChatMessage.created_at >= start,
        ChatMessage.created_at < end,
    ).first())


def _course_day_marker(db, course_id: str, day: date) -> dict:
    row = db.query(TeacherClassDashboard).filter(
        TeacherClassDashboard.data_type == RUN_DATA_TYPE,
        TeacherClassDashboard.class_id.is_(None),
        TeacherClassDashboard.data_key == _run_key(course_id, day),
    ).order_by(TeacherClassDashboard.id.desc()).first()
    value = _loads_dict(row.data_json) if row else {}
    if value.get("courseId") != course_id or value.get("date") != day.isoformat():
        return {}
    return value


def _merge_topics(previous_topics: list[dict], new_topics: list[dict], practice: dict) -> list[dict]:
    """把本轮新增问题的主题合入当天摘要，并刷新课程内答错次数。"""
    wrong_by_id = {
        str(item.get("kpId") or ""): int(item.get("wrongCount") or 0)
        for item in practice.get("wrongByKp") or []
        if isinstance(item, dict)
    }
    merged: dict[str, dict] = {}
    for source in previous_topics if isinstance(previous_topics, list) else []:
        if not isinstance(source, dict):
            continue
        kp_id = str(source.get("kpId") or "").strip()
        if not kp_id:
            continue
        topic = dict(source)
        topic["questionCount"] = max(0, int(topic.get("questionCount") or 0))
        topic["wrongAnswerCount"] = wrong_by_id.get(kp_id, 0)
        topic["confidence"] = _confidence(topic["questionCount"], topic["wrongAnswerCount"])
        merged[kp_id] = topic

    generic_prefixes = ("该知识点出现相关提问", "出现相关提问")
    for source in new_topics if isinstance(new_topics, list) else []:
        if not isinstance(source, dict):
            continue
        kp_id = str(source.get("kpId") or "").strip()
        if not kp_id:
            continue
        existing = merged.get(kp_id)
        question_count = max(0, int(source.get("questionCount") or 0))
        incoming_doubt = str(source.get("likelyDoubt") or "").strip()
        if existing:
            total_questions = int(existing.get("questionCount") or 0) + question_count
            previous_doubt = str(existing.get("likelyDoubt") or "").strip()
            is_generic = any(incoming_doubt.startswith(prefix) for prefix in generic_prefixes)
            existing.update({
                "questionCount": total_questions,
                "wrongAnswerCount": wrong_by_id.get(kp_id, 0),
                "likelyDoubt": previous_doubt if is_generic and previous_doubt else incoming_doubt or previous_doubt,
                "confidence": _confidence(total_questions, wrong_by_id.get(kp_id, 0)),
            })
            if source.get("kpName"):
                existing["kpName"] = source["kpName"]
            if source.get("chapter"):
                existing["chapter"] = source["chapter"]
        else:
            topic = dict(source)
            topic["questionCount"] = question_count
            topic["wrongAnswerCount"] = wrong_by_id.get(kp_id, 0)
            topic["confidence"] = _confidence(question_count, topic["wrongAnswerCount"])
            merged[kp_id] = topic

    return sorted(merged.values(), key=lambda item: (
        -(int(item.get("questionCount") or 0) + int(item.get("wrongAnswerCount") or 0)),
        str(item.get("kpName") or ""),
    ))[:8]


def _analyse_student_day(db, course_id: str, user_id: str, day: date, catalog: list[dict]) -> dict | None:
    question_rows, question_count, last_message_id = _get_questions(db, course_id, user_id, day)
    if not question_count and not last_message_id:
        return None
    practice = _practice_for_day(db, course_id, user_id, day, catalog)
    learning = _learning_for_day(db, course_id, user_id)
    sampled = [text for _message_id, text in question_rows]
    db.rollback()  # release the read transaction before the model request
    topics = []
    status = "no_questions"
    if sampled:
        topics = _llm_topics(course_id, sampled, catalog, practice)
        status = "model"
        if topics is None:
            topics = _rule_topics(course_id, sampled, catalog, practice)
            status = "course_terms"
    generated_at = datetime.now(SHANGHAI).isoformat(timespec="seconds")
    return {
        "date": day.isoformat(),
        "generatedAt": generated_at,
        "updatedAt": generated_at,
        "lastMessageId": last_message_id,
        "questionCount": question_count,
        "analyzedQuestionCount": len(sampled),
        "topicStatus": status,
        "topics": topics,
        "practice": practice,
        "learning": learning,
    }


def _incremental_student_day(
    db, course_id: str, user_id: str, day: date, catalog: list[dict],
) -> tuple[dict | None, int, bool]:
    """只分析游标之后的新问题；没有新问句时不调用模型。"""
    previous = _student_day(db, course_id, user_id, day)
    if previous is not None and "lastMessageId" not in previous:
        # 旧版摘要没有消息游标，仅在升级后的第一次扫描重建一次，之后转为增量。
        snapshot = _analyse_student_day(db, course_id, user_id, day, catalog)
        return snapshot, 0, snapshot is not None

    cursor = int((previous or {}).get("lastMessageId") or 0)
    question_rows, new_question_count, last_message_id, consumed_rows = _get_new_questions(
        db, course_id, user_id, day, cursor,
    )
    if previous is None and not consumed_rows:
        return None, 0, False

    practice = _practice_for_day(db, course_id, user_id, day, catalog)
    learning = _learning_for_day(db, course_id, user_id)
    new_topics = []
    topic_status = (previous or {}).get("topicStatus") or "no_questions"
    sampled = [text for _message_id, text in question_rows]
    if sampled:
        db.rollback()  # release the read transaction before the model request
        new_topics = _llm_topics(course_id, sampled, catalog, practice)
        topic_status = "model"
        if new_topics is None:
            new_topics = _rule_topics(course_id, sampled, catalog, practice)
            topic_status = "course_terms"

    topics = _merge_topics((previous or {}).get("topics") or [], new_topics or [], practice)
    now = datetime.now(SHANGHAI).isoformat(timespec="seconds")
    snapshot = {
        "date": day.isoformat(),
        "generatedAt": now if sampled or previous is None else (previous.get("generatedAt") or now),
        "updatedAt": now,
        "lastMessageId": max(cursor, last_message_id),
        "questionCount": int((previous or {}).get("questionCount") or 0) + new_question_count,
        "analyzedQuestionCount": int((previous or {}).get("analyzedQuestionCount") or 0) + len(sampled),
        "topicStatus": topic_status,
        "topics": topics,
        "practice": practice,
        "learning": learning,
    }
    changed = (
        previous is None
        or consumed_rows
        or practice != previous.get("practice")
        or learning != previous.get("learning")
    )
    return snapshot, new_question_count, changed


def analyze_day(day: date | None = None, only_missing: bool = False) -> dict:
    """增量分析今天的新问答；历史日期仅用于缺失摘要补算。"""
    today = datetime.now(SHANGHAI).date()
    target_day = day or today
    incremental = target_day == today and not only_missing
    db = SessionLocal()
    totals = {"courses": 0, "students": 0, "questions": 0, "failed": 0}
    try:
        course_ids = [row[0] for row in db.query(Course.course_id).all() if row[0]]
        totals["courses"] = len(course_ids)
        for course_id in course_ids:
            marker = _course_day_marker(db, course_id, target_day)
            if only_missing and marker.get("status") == "complete":
                continue
            members = _course_student_ids(db, course_id)
            catalog = _course_catalog(db, course_id)
            course_questions = 0
            new_course_questions = 0
            analysed_students = 0
            failed_students = 0
            for user_id in members:
                previous = _student_day(db, course_id, user_id, target_day)
                if only_missing and previous:
                    analysed_students += 1
                    course_questions += int(previous.get("questionCount") or 0)
                    continue
                try:
                    if incremental:
                        snapshot, new_questions, changed = _incremental_student_day(
                            db, course_id, user_id, target_day, catalog,
                        )
                    else:
                        if not _course_day_has_questions(db, course_id, user_id, target_day):
                            continue
                        snapshot = _analyse_student_day(db, course_id, user_id, target_day, catalog)
                        new_questions = int((snapshot or {}).get("questionCount") or 0)
                        changed = snapshot is not None
                    if snapshot:
                        if changed:
                            _save_student_day(db, course_id, user_id, snapshot)
                        analysed_students += 1
                        course_questions += snapshot["questionCount"]
                        new_course_questions += new_questions
                        if changed:
                            totals["students"] += 1
                            totals["questions"] += new_questions
                except Exception as exc:
                    db.rollback()
                    failed_students += 1
                    totals["failed"] += 1
                    logger.warning("incremental analysis failed for course (%s)", type(exc).__name__)
            _save_run(db, course_id, target_day, {
                "version": 1,
                "courseId": course_id,
                "date": target_day.isoformat(),
                "processedAt": datetime.now(SHANGHAI).isoformat(timespec="seconds"),
                "status": "partial" if failed_students else "complete",
                "studentCount": len(members),
                "analyzedStudents": analysed_students,
                "questionCount": course_questions,
                "newQuestionCount": new_course_questions,
                "failedStudents": failed_students,
            })
        retention_anchor = max(target_day, datetime.now(SHANGHAI).date())
        run_cutoff = (retention_anchor - timedelta(days=RETENTION_DAYS - 1)).isoformat()
        _prune_student_summaries(db, run_cutoff)
        for row in db.query(TeacherClassDashboard).filter(
            TeacherClassDashboard.data_type == RUN_DATA_TYPE,
            TeacherClassDashboard.class_id.is_(None),
        ).all():
            if str(_loads_dict(row.data_json).get("date") or "") < run_cutoff:
                db.delete(row)
        db.commit()
        logger.info("incremental student learning analysis finished: %s", totals)
        return totals
    finally:
        db.close()


def backfill_recent_days() -> None:
    today = datetime.now(SHANGHAI).date()
    for offset in range(BACKFILL_DAYS, 0, -1):
        analyze_day(today - timedelta(days=offset), only_missing=True)


def recent_ai_summary(db, course_id: str, user_id: str, days: int = 7) -> dict:
    """供教师 student_profile 使用；只返回主题和归纳，不返回原始问句。"""
    try:
        window = max(1, min(int(days or 7), 30))
    except (TypeError, ValueError):
        window = 7
    today = datetime.now(SHANGHAI).date()
    start_day = today - timedelta(days=window - 1)
    student_days = [item for item in _read_student_days(db, course_id, user_id)
                    if start_day.isoformat() <= str(item.get("date") or "") <= today.isoformat()]
    by_kp: dict[str, dict] = {}
    daily = []
    for item in student_days:
        daily.append({
            "date": item.get("date"),
            "questionCount": int(item.get("questionCount") or 0),
            "analyzedQuestionCount": int(item.get("analyzedQuestionCount") or 0),
            "practice": item.get("practice") or {},
        })
        for topic in item.get("topics") or []:
            if not isinstance(topic, dict):
                continue
            kp_id = str(topic.get("kpId") or "")
            if not kp_id:
                continue
            row = by_kp.setdefault(kp_id, {
                "kpId": kp_id,
                "kpName": topic.get("kpName") or kp_id,
                "chapter": topic.get("chapter") or "",
                "questionCount": 0,
                "wrongAnswerCount": 0,
                "likelyDoubt": "",
                "confidence": "有限",
                "lastAsked": "",
                "_concerns": Counter(),
            })
            row["questionCount"] += int(topic.get("questionCount") or 0)
            row["wrongAnswerCount"] += int(topic.get("wrongAnswerCount") or 0)
            concern = str(topic.get("likelyDoubt") or "").strip()
            if concern:
                row["_concerns"][concern] += 1
            row["lastAsked"] = max(row["lastAsked"], str(item.get("date") or ""))
            confidence = str(topic.get("confidence") or "有限")
            confidence_rank = {"有限": 0, "一般": 1, "较强": 2}
            if confidence_rank.get(confidence, 0) > confidence_rank.get(row["confidence"], 0):
                row["confidence"] = confidence
    topics = []
    for row in by_kp.values():
        concerns = row.pop("_concerns")
        row["likelyDoubt"] = concerns.most_common(1)[0][0] if concerns else ""
        topics.append(row)
    topics.sort(key=lambda item: (
        -(item["questionCount"] + item["wrongAnswerCount"]), item["kpName"],
    ))

    run_days = []
    latest_scan_at = ""
    for offset in range(window):
        day = start_day + timedelta(days=offset)
        run = _course_day_marker(db, course_id, day)
        if run:
            processed_at = str(run.get("processedAt") or "")
            run_days.append({
                "date": day.isoformat(),
                "status": run.get("status") or "complete",
                "processedAt": processed_at,
            })
            latest_scan_at = max(latest_scan_at, processed_at)
    analyzed_through = max((item["date"] for item in run_days), default="")
    question_count = sum(int(item.get("questionCount") or 0) for item in daily)
    return {
        "days": window,
        "fromDate": start_day.isoformat(),
        "throughDate": analyzed_through,
        "latestScanAt": latest_scan_at,
        "scheduledRuns": run_days,
        "questionCount": question_count,
        "analyzedQuestionCount": sum(int(item.get("analyzedQuestionCount") or 0) for item in daily),
        "topics": topics[:8],
        "dailyActivity": daily,
        "basis": (
            "后台每五分钟增量扫描当前课程新增的学生智能答疑，并更新当天摘要；没有新问答时不会重复调用模型。"
            "只返回课程知识点、章节及归纳疑惑，原始问句不会写入分析摘要或返回教师。"
            "分析日期以 throughDate 为准，最近一次扫描时间以 latestScanAt 为准。"
        ),
    }


def start_scheduler() -> bool:
    """启动每五分钟增量分析和启动时的历史摘要补算任务。"""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        return True
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.interval import IntervalTrigger
        from apscheduler.triggers.date import DateTrigger
    except ImportError:
        logger.error("APScheduler is missing; install backend/requirements.txt to enable five-minute analysis")
        return False

    scheduler = BackgroundScheduler(timezone=SHANGHAI, daemon=True)
    scheduler.add_job(
        analyze_day,
        IntervalTrigger(minutes=5, timezone=SHANGHAI),
        id="incremental_student_learning_analysis",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60,
    )
    scheduler.add_job(
        backfill_recent_days,
        DateTrigger(run_date=datetime.now(SHANGHAI) + timedelta(seconds=15)),
        id="backfill_recent_student_learning_analysis",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.start()
    _scheduler = scheduler
    logger.info("incremental student learning analysis scheduled every 5 minutes (Asia/Shanghai)")
    return True


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
    _scheduler = None
