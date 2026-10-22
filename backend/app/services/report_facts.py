"""报告事实清单：只读取当前课程，区分期间活动与当前快照，不生成分析正文。"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func, or_

from app.models.alert import Alert
from app.models.course import Course, Resource, ResourceProgress
from app.models.graph import GraphNode, LearningPath
from app.models.intervention import TeacherClassDashboard
from app.models.practice import AnswerRecord
from app.models.question import Question
from app.models.user import User
from app.models.user_course import UserCourse
from app.services.catalog_helpers import (
    not_share_type, question_kp_ids, resource_kp_ids, student_visible_source,
)
from app.services.resource_progress import row_key
from app.services.scoring import SECONDARY_KP_WEIGHT

SHANGHAI = timezone(timedelta(hours=8))
PASS_LINE = 60


def _json(raw):
    try:
        value = json.loads(raw or "{}")
        return value if isinstance(value, dict) else {}
    except (TypeError, ValueError):
        return {}


def _chapter_key(value):
    text = str(value or "").strip()
    match = re.search(r"第\s*([0-9一二三四五六七八九十百零]+)\s*章", text)
    return f"第{match[1]}章" if match else text


def _utc(value):
    if not value:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


@dataclass(frozen=True)
class ReportScope:
    course_id: str
    chapters: tuple[str, ...] = ()
    kp_ids: tuple[str, ...] = ()
    start: date | None = None
    end: date | None = None

    def during(self, timestamp):
        value = _utc(timestamp)
        if value is None:
            return not (self.start or self.end)
        local_day = value.astimezone(SHANGHAI).date()
        return (not self.start or local_day >= self.start) and (not self.end or local_day <= self.end)

    def includes(self, chapter, kps):
        return (not self.chapters or _chapter_key(chapter) in self.chapters) and (
            not self.kp_ids or bool(set(kps) & set(self.kp_ids)))


def make_scope(course_id, *, chapters=None, chapter=None, kp_ids=None, start_date="", end_date=""):
    today = datetime.now(SHANGHAI).date()
    try:
        start = date.fromisoformat(start_date) if start_date else None
        end = date.fromisoformat(end_date) if end_date else None
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, "报告日期必须为 YYYY-MM-DD") from exc
    if start and end and start > end:
        raise HTTPException(400, "开始日期不能晚于结束日期")
    if any(day and day > today for day in (start, end)):
        raise HTTPException(400, "报告不能选择未来日期")
    if chapters is None:
        chapters = re.split(r"[、,，]", chapter or "")
    normalized = tuple(dict.fromkeys(_chapter_key(x) for x in chapters if str(x or "").strip()))
    if "全课程" in normalized:
        normalized = ()
    return ReportScope(course_id, normalized, tuple(dict.fromkeys(kp_ids or [])), start, end)


def collect_report_facts(db, user, scope: ReportScope, *, personal=False):
    """返回不含原始问句的事实；教师只获得课程总体汇总。全程只读。"""
    now = datetime.now(SHANGHAI)
    course = db.query(Course).filter(Course.course_id == scope.course_id).first()
    if not course:
        raise HTTPException(404, "课程不存在")
    course_name = course.name or "当前课程"
    members = db.query(UserCourse.user_id).join(User, User.user_id == UserCourse.user_id).filter(
        UserCourse.course_id == scope.course_id,
        UserCourse.role_in_course == "student", User.role == "student",
    )
    if personal:
        members = members.filter(UserCourse.user_id == user.user_id)
    user_ids = {uid for (uid,) in members.all()}
    catalog = db.query(GraphNode).filter(
        GraphNode.course_id == scope.course_id, GraphNode.graph_type == "knowledge",
    ).all()
    chapter_rows = db.query(GraphNode).filter(
        GraphNode.course_id == scope.course_id, GraphNode.graph_type == "chapter",
    ).all()
    chapter_names = {n.id: n.name for n in chapter_rows}
    known_chapters = {_chapter_key(n.chapter) for n in catalog if n.chapter}
    known_chapters.update(_chapter_key(n.name) for n in chapter_rows)
    if set(scope.chapters) - known_chapters:
        raise HTTPException(400, "所选章节不属于当前课程，请重新选择")
    if set(scope.kp_ids) - {n.id for n in catalog}:
        raise HTTPException(400, "所选知识点不属于当前课程，请重新选择")
    selected_nodes = {n.id: n for n in catalog if scope.includes(n.chapter, [n.id])}

    def label(kp_id):
        node = selected_nodes.get(kp_id)
        return f"{node.name}（{node.chapter}）" if node and node.chapter else (node.name if node else "未关联知识点")

    def hits(chapter, kps, chapter_id=""):
        chapter = chapter or chapter_names.get(chapter_id, "")
        if scope.chapters and not chapter:
            chapter = next((selected_nodes[k].chapter for k in kps if k in selected_nodes), "")
        return scope.includes(chapter, kps)

    facts = []

    def add(key, category, text):
        facts.append({"id": key, "category": category, "text": text})

    period = f"{scope.start.isoformat() if scope.start else '有记录起'} 至 {scope.end.isoformat() if scope.end else now.date().isoformat()}"
    add("scope", "overview", f"《{course_name}》；范围：{'、'.join(scope.chapters) or '全课程'}；期间：{period}（北京时间）；覆盖学生 {len(user_ids)} 人。")
    add("snapshot", "learning", f"学习路径、资源进度和综合掌握率为 {now.strftime('%Y-%m-%d %H:%M')} 的当前快照，不能还原期间起止时的进度或计算历史进步。")
    add("method", "overview", "正确率按统计期间每位学生每题的最近一次作答计算，练习和试卷答题合并去重；答错次数另按实际作答次数计算，不能相互替代。")

    lps = db.query(LearningPath).filter(
        LearningPath.course_id == scope.course_id, LearningPath.user_id.in_(members),
    ).order_by(LearningPath.id).all()
    lp_map = {(row.user_id, row.kp_id): row for row in lps if row.kp_id in selected_nodes}
    done = sum(row.status == "done" for row in lp_map.values())
    expected = len(selected_nodes) * len(user_ids)
    add("path", "learning", f"范围内知识点 {len(selected_nodes)} 个；应有学生与知识点组合 {expected} 个，已有学习路径 {len(lp_map)} 个，标记完成 {done} 个；" +
        (f"当前完成率 {round(done / expected * 100, 1)}%。" if expected else "暂无可计算的完成率。"))

    resources = db.query(Resource).filter(
        Resource.course_id == scope.course_id, student_visible_source(Resource.source), not_share_type(Resource.type),
    ).all()
    resources = {r.res_id: r for r in resources if hits(r.chapter, resource_kp_ids(r), r.chapter_id)}
    progresses = db.query(ResourceProgress).join(Resource, Resource.res_id == ResourceProgress.res_id).filter(
        Resource.course_id == scope.course_id, ResourceProgress.user_id.in_(members),
    ).all()
    progress = {}
    for row in progresses:
        if row.res_id not in resources:
            continue
        key = (row.user_id, row.res_id)
        if key not in progress or row_key(row) > row_key(progress[key]):
            progress[key] = row
    res_expected = len(resources) * len(user_ids)
    finished = sum((row.progress or 0) >= 100 for row in progress.values())
    average = round(sum(row.progress or 0 for row in progress.values()) / res_expected, 1) if res_expected else None
    add("resources", "learning", f"范围内可学资源 {len(resources)} 个，学生与资源组合 {res_expected} 个，已学完 {finished} 个组合；" +
        (f"当前平均资源完成率 {average}%。" if average is not None else "暂无可计算的资源完成率。") + "资源最远观看位置不等于实际学习时长，现有资源时长日志不分课程，不纳入课程时长。")

    questions = {q.q_id: q for q in db.query(Question).filter(Question.course_id == scope.course_id).all()}
    answers = db.query(AnswerRecord).outerjoin(Question, Question.q_id == AnswerRecord.q_id).filter(
        AnswerRecord.course_id == scope.course_id, AnswerRecord.user_id.in_(members),
        or_(Question.course_id == scope.course_id, Question.q_id.is_(None)),
    ).order_by(AnswerRecord.id).all()
    related_by_q = {}
    selected_answers = []
    for answer in answers:
        question = questions.get(answer.q_id)
        kps = question_kp_ids(question) if question else ([answer.kp_id] if answer.kp_id else [])
        chapter = question.chapter if question else ""
        chapter_id = question.chapter_id if question else ""
        if hits(chapter, kps, chapter_id):
            selected_answers.append(answer)
            related_by_q[answer.q_id] = kps
    latest_now, latest_period = {}, {}
    period_answers = []
    for row in selected_answers:
        key = (row.user_id, row.q_id)
        latest_now[key] = row
        if scope.during(row.created_at):
            latest_period[key] = row
            period_answers.append(row)
    correct = sum(bool(row.is_correct) for row in latest_period.values())
    answer_students = {row.user_id for row in period_answers}
    add("practice", "practice", f"期间作答学生 {len(answer_students)}/{len(user_ids)} 人；实际提交 {len(period_answers)} 次，答错 {sum(not row.is_correct for row in period_answers)} 次；按学生每题最近作答去重后 {len(latest_period)} 题，答对 {correct} 题；" +
        (f"正确率 {round(correct / len(latest_period) * 100, 1)}%。" if latest_period else "没有作答，正确率未知。"))
    practice_seconds = sum(max(0, row.duration_seconds or 0) for row in period_answers)
    active_dates = {_utc(row.created_at).astimezone(SHANGHAI).date() for row in period_answers if row.created_at}
    add("effort", "learning", f"期间有练习记录的自然日 {len(active_dates)} 天，累计作答用时 {practice_seconds} 秒；这只是作答用时，不能当作总学习时长；登录签到不分课程，不用于推断本课程连续学习天数。")

    wrong_counts = Counter((row.user_id, row.q_id) for row in period_answers if not row.is_correct)
    recovered = sum(key in latest_period and bool(latest_period[key].is_correct) for key in wrong_counts)
    repeated = sum(count >= 2 for count in wrong_counts.values())
    outstanding = sum(not row.is_correct and not row.mastered for row in latest_period.values())
    add("wrong", "practice", f"期间曾答错的学生与题目组合 {len(wrong_counts)} 个，其中 {repeated} 个组合答错至少两次，{recovered} 个组合在期间最近作答已答对，{outstanding} 个组合最近仍答错且未标记掌握。")
    error_types = Counter(row.error_type.strip() for row in period_answers if not row.is_correct and
                          row.error_type and row.error_type.strip() not in ("未分类", "题目类型"))
    add("errors", "practice", "已有错误分类：" + ("；".join(f"{name} {count} 次" for name, count in error_types.most_common(5)) if error_types else "暂无可靠分类，不能凭作答结果推断粗心、态度、动机或心理原因。"))

    def accuracy_maps(latest):
        numerator, denominator, counts = defaultdict(float), defaultdict(float), Counter()
        for (uid, qid), row in latest.items():
            kps = related_by_q.get(qid, [])
            for index, kp in enumerate(kps):
                if kp not in selected_nodes:
                    continue
                weight = 1.0 if index == 0 else SECONDARY_KP_WEIGHT
                key = (uid, kp)
                denominator[key] += weight
                numerator[key] += weight if row.is_correct else 0
                counts[key] += 1
        return {key: round(numerator[key] / weight * 100, 1) for key, weight in denominator.items()}, counts

    quiz_now, _ = accuracy_maps(latest_now)
    quiz_period, kp_counts = accuracy_maps(latest_period)
    by_kp_resource = defaultdict(list)
    for resource in resources.values():
        for kp in resource_kp_ids(resource):
            if kp in selected_nodes:
                by_kp_resource[kp].append(resource.res_id)
    mastery = defaultdict(list)
    for uid in user_ids:
        for kp in selected_nodes:
            res_ids = by_kp_resource.get(kp, [])
            values = [(progress[(uid, rid)].progress or 0) if (uid, rid) in progress else 0 for rid in res_ids]
            if (uid, kp) in quiz_now or any((uid, rid) in progress for rid in res_ids):
                mastery[kp].append(max(quiz_now.get((uid, kp), 0), sum(values) / len(values) if values else 0))
    averages = {kp: round(sum(values) / len(values), 1) for kp, values in mastery.items() if values}
    add("mastery", "mastery", f"当前综合掌握率取各学生资源完成率与加权答题正确率中的较高值，主知识点权重 1，关联标签权重 {SECONDARY_KP_WEIGHT}；达标线 {PASS_LINE}%。各点均值只含有作答或资源进度记录的学生，不代表全体；资源看完不等于已能独立解题，没有学习证据的点记为未知。")
    by_kp_period = defaultdict(list)
    for (uid, kp), accuracy in quiz_period.items():
        by_kp_period[kp].append((accuracy, kp_counts[(uid, kp)]))
    weak_order = sorted(selected_nodes, key=lambda kp: (averages.get(kp, 101), selected_nodes[kp].name))
    # 模型输入限制为最需关注的点和少量优势点；总量与截断范围明确记录。
    strong_order = sorted(averages, key=lambda kp: -averages[kp])[:3]
    chosen = list(dict.fromkeys(weak_order[:8] + strong_order))
    for index, kp in enumerate(chosen):
        sample = by_kp_period.get(kp, [])
        text = f"{label(kp)}：当前综合掌握率均值 {averages[kp]}%" if kp in averages else f"{label(kp)}：当前掌握率未知"
        text += f"（当前有证据的学生 {len(mastery.get(kp, []))} 人）"
        text += f"；期间有该点答题证据的学生 {len(sample)} 人，学生与不同题目组合 {sum(n for _, n in sample)} 个"
        if sample:
            text += f"，学生加权正确率均值 {round(sum(acc for acc, _ in sample) / len(sample), 1)}%"
        add(f"kp{index}", "mastery", text + "。")
    add("kpCoverage", "mastery", f"所选范围共 {len(selected_nodes)} 个知识点，当前可计算综合掌握率 {len(averages)} 个，达标 {sum(v >= PASS_LINE for v in averages.values())} 个，低于达标线 {sum(v < PASS_LINE for v in averages.values())} 个；明细最多展示薄弱端 8 个与优势端 3 个，其余未逐项分析。")

    dated = [row for row in period_answers if row.created_at]
    ordered_days = sorted({_utc(row.created_at).astimezone(SHANGHAI).date() for row in dated})
    if len(ordered_days) >= 2:
        middle = ordered_days[len(ordered_days) // 2]
        groups = [[], []]
        for row in dated:
            groups[int(_utc(row.created_at).astimezone(SHANGHAI).date() >= middle)].append(row)
        add("trend", "practice", "期间前后段实际提交正确率（不去重，题目难度可能不同，不能据此证明能力提高或下降）：" + "；".join(
            f"{name} {len(rows)} 次，{round(sum(bool(r.is_correct) for r in rows) / len(rows) * 100, 1)}%"
            for name, rows in zip(("前段", "后段"), groups)))
    else:
        add("trend", "practice", "有日期的作答不足两个自然日，暂不能比较前后变化。")

    alerts = db.query(Alert).filter(
        Alert.course_id == scope.course_id, Alert.user_id.in_(members),
        Alert.level.in_(("red", "yellow")), Alert.status.notin_(("ignored", "closed")),
    ).all()
    alerts = [row for row in alerts if scope.during(row.created_at) and (
        not (scope.chapters or scope.kp_ids) or row.kp_id in selected_nodes)]
    levels = Counter(row.level for row in alerts)
    add("alerts", "dialogue", f"期间产生且当前未忽略、未关闭的红色预警 {levels['red']} 条、黄色预警 {levels['yellow']} 条，涉及学生 {len({r.user_id for r in alerts})} 人；" +
        ("涉及知识点：" + "、".join(dict.fromkeys(label(r.kp_id) for r in alerts))[:400] if alerts else "未查到符合范围的预警，不代表没有薄弱点。"))

    summary_rows = db.query(TeacherClassDashboard).filter(
        TeacherClassDashboard.data_type == "ai_daily_analysis",
        func.json_extract(TeacherClassDashboard.data_json, "$.courseId") == scope.course_id,
        func.json_extract(TeacherClassDashboard.data_json, "$.studentId").in_(members),
    ).order_by(TeacherClassDashboard.updated_at, TeacherClassDashboard.id).all()
    days = {}
    for row in summary_rows:
        payload = _json(row.data_json)
        if payload.get("courseId") != scope.course_id or payload.get("studentId") not in user_ids:
            continue
        for day in payload.get("daily") or []:
            try:
                day_date = date.fromisoformat(str(day.get("date", "")))
            except (AttributeError, ValueError):
                continue
            if (not scope.start or day_date >= scope.start) and (not scope.end or day_date <= scope.end):
                days[(payload["studentId"], day_date)] = day
    topic_counts, topic_concerns, topic_methods = Counter(), defaultdict(set), defaultdict(set)
    total_questions, analyzed_questions = 0, 0
    latest_scan = ""
    for day in days.values():
        total_questions += int(day.get("questionCount") or 0)
        analyzed_questions += int(day.get("analyzedQuestionCount") or 0)
        latest_scan = max(latest_scan, str(day.get("updatedAt") or day.get("generatedAt") or ""))
        for topic in day.get("topics") or []:
            kp = str(topic.get("kpId") or "")
            if kp not in selected_nodes:
                continue
            topic_counts[kp] += int(topic.get("questionCount") or 0)
            if personal and topic.get("likelyDoubt"):
                topic_concerns[kp].add(str(topic["likelyDoubt"])[:150])
            topic_methods[kp].add(str(day.get("topicStatus") or "未知"))
    add("aiCoverage", "dialogue", f"已保存 AI 互动摘要覆盖 {len(days)} 个学生与日期组合，范围内摘要记录提问 {total_questions} 次、已分析 {analyzed_questions} 次；" +
        (f"最近摘要更新时间 {latest_scan}。" if latest_scan else "尚无可用摘要。") +
        "摘要最多保留最近 30 天，按每 5 分钟增量更新，不保证覆盖全部问答；没有摘要不等于未提问；只使用归纳结果，不读取原始问句。" +
        ("章节筛选时，上述摘要覆盖量仍为期间课程级总量，下面的知识点提问次数才是所选章节范围。" if scope.chapters or scope.kp_ids else ""))
    for index, (kp, count) in enumerate(topic_counts.most_common(8)):
        concern = "；归纳疑惑：" + "；".join(sorted(topic_concerns[kp])[:2]) if personal and topic_concerns[kp] else ""
        add(f"ai{index}", "dialogue", f"{label(kp)}：摘要中的提问次数 {count} 次；摘要生成依据 {','.join(sorted(topic_methods[kp]))}，course_terms 表示课程词匹配而非模型推断{concern}；提问只能说明关注或疑惑，不能直接认定不会。")

    attempt_rows = db.query(TeacherClassDashboard).filter(
        TeacherClassDashboard.data_type == "exam_attempt",
        func.json_extract(TeacherClassDashboard.data_json, "$.courseId") == scope.course_id,
        func.json_extract(TeacherClassDashboard.data_json, "$.userId").in_(members),
        func.json_extract(TeacherClassDashboard.data_json, "$.status") == "finished",
    ).order_by(TeacherClassDashboard.id.desc()).all()
    attempts = {}
    for row in attempt_rows:
        attempt = _json(row.data_json)
        result = attempt.get("result")
        if not isinstance(result, dict) or not scope.during(attempt.get("finishedAt")):
            continue
        key = (attempt.get("userId"), attempt.get("paperId"))
        previous = attempts.get(key)
        if previous is None or str(attempt.get("finishedAt") or "") > str(previous.get("finishedAt") or ""):
            attempts[key] = attempt
    exam_groups = defaultdict(list)
    for attempt in attempts.values():
        result = attempt["result"]
        items = result.get("items") or []
        selected = [item for item in items if hits(item.get("chapter"), item.get("kpIds") or [])]
        if (scope.chapters or scope.kp_ids) and not selected:
            continue
        partial = bool(scope.chapters or scope.kp_ids)
        score = sum(float(item.get("earnedScore") or 0) for item in selected) if partial else float(result.get("score") or 0)
        total = sum(float(item.get("score") or 0) for item in selected) if partial else float(result.get("totalScore") or 0)
        if total > 0:
            exam_groups[(attempt.get("paperId"), attempt.get("title") or "未命名试卷")].append((score, total))
    add("examCoverage", "practice", f"期间按学生每份试卷最近一次已结算记录，符合范围的试卷 {len(exam_groups)} 份，提交 {sum(len(v) for v in exam_groups.values())} 人次；" +
        ("仅统计所选章节或知识点题目的得分，不将整卷分数当作章节成绩。" if scope.chapters or scope.kp_ids else "不同满分试卷分别展示，不直接平均原始分数。"))
    for index, ((_paper_id, title), results) in enumerate(list(exam_groups.items())[:5]):
        percents = [score / total * 100 for score, total in results]
        score_text = (f"得分 {results[0][0]:g}/{results[0][1]:g}，" if personal and len(results) == 1 else "")
        add(f"exam{index}", "practice", f"《{title}》：{len(results)} 人次，{score_text}平均得分率 {round(sum(percents) / len(percents), 1)}%，最高得分率 {round(max(percents), 1)}%，最低得分率 {round(min(percents), 1)}%；明细仅展示最近提交涉及的最多 5 份试卷。")

    priority = set(weak_order[:3])
    suggested_resources = sorted(resources.values(), key=lambda r: (not bool(set(resource_kp_ids(r)) & priority), r.res_id))
    for index, resource in enumerate(suggested_resources[:8]):
        kind = {"doc": "教材文献", "ppt": "课件", "video": "教学视频", "quiz": "练习"}.get(resource.type, "学习资源")
        names = [selected_nodes[k].name for k in resource_kp_ids(resource) if k in selected_nodes]
        add(f"resource{index}", "plan", f"可用{kind}《{resource.title}》，章节 {resource.chapter or chapter_names.get(resource.chapter_id) or '未分章'}，关联知识点 {'、'.join(names) or '未关联'}；入口：课程图谱导航或学习资源中心。")
    add("actions", "plan", "可用入口：课程图谱导航、学习资源中心、智能练习中的薄弱强化、错题本、试卷测验作答详情、智能助手。学生已完成试卷只可查看详情，不建议重新测验同卷。计划需先补概念再用不同题验证；每项写清优先级、行动、依据和验收方式，不虚构截止日期或课程要求。")
    meta = {
        "scope": "self" if personal else "course", "courseId": scope.course_id, "courseName": course_name,
        "className": course_name, "chapter": "、".join(scope.chapters) or "全课程",
        "kpIds": list(scope.kp_ids), "startDate": scope.start.isoformat() if scope.start else "",
        "endDate": scope.end.isoformat() if scope.end else "", "period": period,
        "studentCount": len(user_ids), "generator": user.name or user.username,
        "generatedAt": now.strftime("%Y-%m-%d %H:%M"), "dataAsOf": now.isoformat(timespec="seconds"),
        "generationMethod": "ai", "reportVersion": 2,
    }
    if personal:
        meta.update(userId=user.user_id, studentNo=user.student_no or "")
    return {"facts": facts, "meta": meta}
