"""学生个人学情报告（自助生成）—— 全部数字从真实业务表计算，不做估算、不留兜底。

与教师端班级报告（`routers/intervention.py::generate_report`）的关系：

- 统计范围 = **当前登录学生本人**，只读自己的记录，不涉及同班同学；
- 掌握率 / 正确率一律复用 `services` 里已有口径（`kp_stats.mastery_by_kp`、
  `scoring.overall_accuracy`、`scoring.quiz_accuracy_by_kp`），**不在这里另起一套**；
- 归属写进 `detail_json.meta`（`scope="self"` / `userId` / `courseId`）——
  `reports` 表只有 `class_id`（真实数据里恒为 NULL），本阶段不动表结构，
  列表与详情靠 meta 过滤（口径问题见 `待修复清单.md` P45）。

**刻意不做筛选**：教师端报告页的「章节 / 日期」选择器只写进 meta、并不参与计算
（既有行为，见 `routers/intervention.py`），所以本报告不复制这套会误导人的参数，
直接给「截至当前」的课程全量学情快照。
"""
from collections import defaultdict
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models.alert import Alert
from ..models.checkin import StudyCheckin
from ..models.course import Course, Resource
from ..models.graph import GraphNode, LearningPath
from ..models.practice import AnswerRecord
from ..utils import fmt_dur
from .kp_stats import best_position_sum, mastery_by_kp
from .resource_progress import progress_map
from .scoring import overall_accuracy, quiz_accuracy_by_kp

# 达标线：与「能力目标达成度」同一个 60% 阈值（见 student_dashboard 的注释）
PASS_LINE = 60.0

# 预警的有效口径：与教师端工具 class_alerts 保持一致（忽略教师已忽略的）
_ACTIVE_ALERT_LEVELS = ("red", "yellow")
_LEVEL_TEXT = {"red": "红色", "yellow": "黄色"}


def _kp_names(db: Session, course_id: str) -> dict:
    """知识点 id → 名称（只取课程内的知识图谱节点）。"""
    rows = db.query(GraphNode.id, GraphNode.name).filter(
        GraphNode.graph_type == "knowledge",
        GraphNode.course_id == course_id,
    ).all()
    return {nid: (name or nid) for nid, name in rows}


def _study_days(db: Session, user_id: str) -> int:
    """累计学习天数 = 有作答记录或登录打卡的不同日期数。"""
    days = {d[0] for d in db.query(func.date(AnswerRecord.created_at)).filter(
        AnswerRecord.user_id == user_id).distinct().all() if d[0]}
    days |= {d[0] for d in db.query(StudyCheckin.day).filter(
        StudyCheckin.user_id == user_id).all() if d[0]}
    return len(days)


def _total_study_seconds(db: Session, user_id: str, course_id: str) -> int:
    """累计学习时长（秒）= 视频最佳观看位置合计 + 练习作答时长合计。

    与 `kp_stats.kp_study_seconds` 同一口径，只是把范围从「某个知识点」放大到「整门课」。
    """
    from .catalog_helpers import student_visible_source
    video_ids = [rid for (rid,) in db.query(Resource.res_id).filter(
        Resource.course_id == course_id, Resource.type == "video",
        student_visible_source(Resource.source)).all()]
    watched = best_position_sum(db, user_id, video_ids)
    practiced = db.query(func.coalesce(func.sum(AnswerRecord.duration_seconds), 0)).filter(
        AnswerRecord.user_id == user_id,
        AnswerRecord.course_id == course_id,
    ).scalar() or 0
    return int(watched) + int(practiced)


def build_student_report(db: Session, user, course_id: str) -> dict:
    """按当前学生真实数据拼一份报告：{title, sections, meta}。"""
    uid = user.user_id
    now = datetime.now()
    student_name = getattr(user, "name", "") or uid
    student_no = getattr(user, "student_no", "") or ""

    course_row = db.query(Course).filter(Course.course_id == course_id).first()
    course_name = (course_row.name if course_row and course_row.name else "").strip() or f"课程 {course_id}"
    kp_name = _kp_names(db, course_id)

    # ---------- 基础数据（全部真实查询） ----------
    lp_rows = db.query(LearningPath).filter(
        LearningPath.user_id == uid,
        LearningPath.course_id == course_id,
    ).all()
    total_kp = len(lp_rows)
    done_kp = [r for r in lp_rows if r.status == "done"]
    completion = round(len(done_kp) / total_kp * 100, 1) if total_kp else 0.0

    mastery_map = mastery_by_kp(db, uid)
    mastery_vals = [mastery_map[r.kp_id] for r in lp_rows if r.kp_id in mastery_map]
    mastery_avg = round(sum(mastery_vals) / len(mastery_vals), 1) if mastery_vals else 0.0

    from .catalog_helpers import student_visible_source, not_share_type
    resources = db.query(Resource).filter(
        Resource.course_id == course_id,
        student_visible_source(Resource.source),
        not_share_type(Resource.type),
    ).all()
    pmap = progress_map(db, uid, [r.res_id for r in resources])
    res_progress = [((pmap.get(r.res_id).progress if pmap.get(r.res_id) else 0) or 0) for r in resources]
    res_avg = round(sum(res_progress) / len(resources), 1) if resources else 0.0
    res_done = sum(1 for p in res_progress if p >= 100)

    quiz = overall_accuracy(db, uid)
    quiz_by_kp = quiz_accuracy_by_kp(db, uid)
    seconds = _total_study_seconds(db, uid, course_id)
    study_days = _study_days(db, uid)

    alert_rows = db.query(Alert).filter(
        Alert.course_id == course_id,
        Alert.user_id == uid,
        Alert.status != "ignored",
        Alert.level.in_(_ACTIVE_ALERT_LEVELS),
    ).all()
    alert_by_level = defaultdict(int)
    for a in alert_rows:
        alert_by_level[a.level] += 1

    # 错题按知识点聚合（题目归属取作答记录里的 kp_id，与练习页一致）
    wrong_by_kp = defaultdict(int)
    for kp_id, n in db.query(AnswerRecord.kp_id, func.count(AnswerRecord.id)).filter(
        AnswerRecord.user_id == uid,
        AnswerRecord.course_id == course_id,
        AnswerRecord.is_correct.is_(False),
        AnswerRecord.kp_id.isnot(None),
    ).group_by(AnswerRecord.kp_id).all():
        if kp_id:
            wrong_by_kp[kp_id] += int(n)

    # ---------- 一、学习概况 ----------
    overview = [f"{student_name}（学号 {student_no}）在《{course_name}》的学习记录。" if student_no
                else f"{student_name}在《{course_name}》的学习记录。"]
    overview_bullets = [
        f"知识点完成率：{completion}%（{len(done_kp)}/{total_kp} 个知识点）" if total_kp
        else "知识点完成率：暂无学习路径记录",
        f"平均掌握率：{mastery_avg}%（各知识点综合掌握率均值，达标线 {PASS_LINE:g}%）" if mastery_vals
        else "平均掌握率：暂无掌握率记录",
        f"资源完成率：{res_avg}%（{res_done}/{len(resources)} 个资源已学完）",
        (f"练习作答：{quiz['answered']} 题，正确率 {quiz['accuracy']}%"
         if quiz["accuracy"] is not None else "练习作答：暂无作答记录"),
        f"累计学习时长：{fmt_dur(seconds)}",
        f"累计学习天数：{study_days} 天",
    ]

    # ---------- 二、知识点掌握情况 ----------
    ranked = sorted(mastery_map.items(), key=lambda kv: kv[1])
    weak = [(k, v) for k, v in ranked if v < PASS_LINE]
    strong = [(k, v) for k, v in ranked if v >= PASS_LINE][::-1]
    mastery_para = [f"课程内共 {total_kp} 个知识点，其中 {len(weak)} 个掌握率低于 {PASS_LINE:g}%。"
                    if total_kp else "当前课程暂无学习路径记录。"]
    mastery_bullets = []
    if weak:
        mastery_bullets.append("待加强（掌握率由低到高）：" + "；".join(
            f"「{kp_name.get(k, k)}」{v}%" for k, v in weak[:3]))
    if strong:
        mastery_bullets.append("已掌握（掌握率由高到低）：" + "；".join(
            f"「{kp_name.get(k, k)}」{v}%" for k, v in strong[:3]))
    if not mastery_bullets:
        mastery_bullets.append("暂无掌握率记录，建议先从资源学习与练习开始。")

    # ---------- 三、练习与错题 ----------
    wrong_total = sum(wrong_by_kp.values())
    practice_para = [
        (f"按题去重、每道题取最近一次作答：共作答 {quiz['answered']} 题，答错 {quiz['answered'] - quiz['correct']} 题，"
         f"正确率 {quiz['accuracy']}%。" if quiz["answered"] else "暂无练习作答记录。")
    ]
    practice_bullets = []
    if wrong_by_kp:
        top_wrong = sorted(wrong_by_kp.items(), key=lambda kv: -kv[1])[:3]
        practice_bullets.append("错题最集中的知识点：" + "；".join(
            f"「{kp_name.get(k, k)}」{n} 次" for k, n in top_wrong))
    if quiz_by_kp:
        lowest = sorted(((k, acc) for k, (acc, _n) in quiz_by_kp.items()), key=lambda kv: kv[1])[:3]
        practice_bullets.append("答题正确率最低的知识点：" + "；".join(
            f"「{kp_name.get(k, k)}」{acc}%" for k, acc in lowest))

    # ---------- 四、学习预警 ----------
    alert_para = [
        (f"当前有 {len(alert_rows)} 条未处理预警（红色 {alert_by_level.get('red', 0)} 条，"
         f"黄色 {alert_by_level.get('yellow', 0)} 条）。" if alert_rows else "当前没有未处理的学习预警。")
    ]
    if alert_rows:
        alert_rows.sort(key=lambda a: (a.level != "red", a.created_at or datetime.min))
        alert_para_bullets = [
            f"[{_LEVEL_TEXT.get(a.level, a.level)}] {a.kp_name or kp_name.get(a.kp_id, a.kp_id or '')}"
            f"{('·' + a.title) if a.title else ''}"
            for a in alert_rows[:5]
        ]
    else:
        alert_para_bullets = []

    # ---------- 五、学习建议（全部由上面的真实数字推导，不编造） ----------
    advice = []
    if weak:
        k, v = weak[0]
        advice.append(f"优先补强「{kp_name.get(k, k)}」（掌握率 {v}%）：建议从「智能练习」的靶向练习入手，"
                      "先做该知识点的薄弱强化。")
    if alert_rows:
        first = alert_rows[0]
        advice.append(f"存在未处理预警：{first.kp_name or kp_name.get(first.kp_id, first.kp_id or '')}"
                      f"{('·' + first.title) if first.title else ''}，建议尽快完成对应练习。")
    if total_kp and len(done_kp) < total_kp:
        advice.append(f"仍有 {total_kp - len(done_kp)} 个知识点未完成，建议按「课程图谱导航」的路径顺序推进。")
    if strong:
        k, v = strong[0]
        advice.append(f"「{kp_name.get(k, k)}」掌握率已达 {v}%，可尝试综合题巩固。")
    if not advice:
        advice.append("暂无足够的学习记录用于给出建议，建议先完成资源学习与一次练习。")

    sections = [
        {"title": "一、学习概况", "paragraphs": overview, "bullets": overview_bullets},
        {"title": "二、知识点掌握情况", "paragraphs": mastery_para, "bullets": mastery_bullets},
        {"title": "三、练习与错题", "paragraphs": practice_para, "bullets": practice_bullets},
        {"title": "四、学习预警", "paragraphs": alert_para, "bullets": alert_para_bullets},
        {"title": "五、学习建议", "paragraphs": [], "bullets": advice},
    ]

    title = f"{student_name} · 个人学情报告 {now.strftime('%Y-%m-%d')}"
    return {
        "title": title,
        "sections": sections,
        "meta": {
            "scope": "self",                 # 与教师班组报告区分（教师端列表据此排除）
            "userId": uid,
            "studentNo": student_no,
            "courseId": course_id,
            "courseName": course_name,
            "studentCount": 1,               # 兼容前端详情模板的人数位
            "className": course_name,
            "generator": student_name,       # 自助生成 → 生成者就是本人
            "generatedAt": now.strftime("%Y-%m-%d %H:%M"),
        },
    }


__all__ = ["build_student_report", "PASS_LINE"]
