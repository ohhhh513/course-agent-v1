"""
学生端接口：/student/*
所有数据从事务表（learning_paths, answer_records, practice_sessions, alerts）动态计算，
不读取任何预置 JSON 快照。每个用户看到的都是自己的真实学习数据。
"""
import json
from datetime import date, datetime, timedelta, timezone
from collections import defaultdict
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import func, desc
from sqlalchemy.orm import Session
from ..database import get_db
from ..models.course import Resource, ResourceProgress, ResourceStudyLog
from ..models.alert import Alert, Message
from ..models.user import User, ClassInfo
from ..models.graph import GraphNode, LearningPath
from ..models.practice import AnswerRecord, PracticeSession
from ..models.checkin import StudyCheckin
from ..middleware.auth import get_current_user
from ..schemas.common import ok, fail, list_response
from ..utils import loads, fmt_dt

router = APIRouter(prefix="/api/v1/student", tags=["学生端"])

# 东八区（中国），无夏令时；数据库存的是 UTC，展示前统一转成本地时间
_CN_TZ = timezone(timedelta(hours=8))

# 学期打卡热力图的锚点：第 1 周从学期开学那一周的周一算起（列 = 周，行 = 周一…周日），
# 与「成长轨迹」用同一口径；想改学期长度只改这里。
SEMESTER_START = date(2026, 8, 31)   # 2026 秋季学期第 1 周周一
SEMESTER_WEEKS = 18                  # 学期周数


def _to_local(dt: datetime | None) -> datetime | None:
    """把库中 naive UTC 时间转成东八区 naive 本地时间。"""
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_CN_TZ).replace(tzinfo=None)


def _duration_to_seconds(s: str) -> int:
    """'22:10' / '01:02:30' → 秒数；无法解析返回 0"""
    if not s:
        return 0
    try:
        parts = [int(x) for x in str(s).split(":")]
    except ValueError:
        return 0
    if not parts:
        return 0
    parts = parts[::-1]
    mult = [1, 60, 3600]
    return sum(parts[i] * mult[i] for i in range(min(len(parts), 3)))


def _resolve_class_id(db: Session, user: User) -> str:
    if user.class_name:
        row = db.query(ClassInfo.class_id).filter(ClassInfo.name == user.class_name).first()
        if row:
            return row[0]
    return "CL2301"


# =============================================================================
# 学生驾驶舱 — 全动态计算
# =============================================================================

@router.get("/dashboard")
def student_dashboard(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """学习驾驶舱 — 所有指标从用户的 transaction 表动态计算"""
    uid = user.user_id
    today = date.today()

    # 统一预警检测：刷新该生告警（达标→生成/刷新；恢复→关闭；不覆盖教师已处理）
    try:
        from ..services.alert_detector import detect_alerts
        detect_alerts(db, [user])
    except Exception as e:
        print(f"[alert-detect] 跳过（{e}）")

    # 综合掌握率（答题正确率 ∪ 资源完成率）→ 资源中心展示用
    from ..routers.graph import _mastery_for_user
    from ..services.scoring import quiz_accuracy_by_kp
    mastery_map = _mastery_for_user(uid, db)
    acc_by_kp = quiz_accuracy_by_kp(db, uid)   # {kp: (答题正确率, 不同题目数)} —— 靶向/薄弱点用

    # --- learning_path（用户专属）---
    lp_rows = db.query(LearningPath).filter(LearningPath.user_id == uid).order_by(LearningPath.step).all()
    lp_total = len(lp_rows)
    lp_done = [r for r in lp_rows if r.status == "done"]
    lp_doing = [r for r in lp_rows if r.status == "doing"]
    lp_warn = [r for r in lp_rows if r.status == "warn"]
    lp_todo = [r for r in lp_rows if r.status == "todo"]
    course_progress = round(len(lp_done) / lp_total * 100, 1) if lp_total else 0

    # 当前学习节点：doing 里的第一个，或 mastery 最高的 todo
    current_node = None
    if lp_doing:
        n = lp_doing[0]
        current_node = {"kpId": n.kp_id, "name": n.name}
    elif lp_rows:
        # 进度最高的那个
        best = max(lp_rows, key=lambda r: r.progress or 0)
        current_node = {"kpId": best.kp_id, "name": best.name}
    else:
        # 无学习记录时，默认推荐课程第一个知识点，避免前端空指针
        first = db.query(GraphNode).filter(
            GraphNode.graph_type == "knowledge",
            GraphNode.course_id == "C2026DS001",
        ).order_by(GraphNode.id).first()
        if first:
            current_node = {"kpId": first.id, "name": first.name}
        else:
            current_node = {"kpId": "", "name": "暂无"}

    # 知识点掌握率：全部知识点的平均综合掌握率（答题正确率 ∪ 资源完成率）
    mastery_rate = round(sum(mastery_map.get(r.kp_id, 0) for r in lp_rows) / lp_total, 1) if lp_total else 0

    # --- 今日学习时长：practice_sessions 的 duration_seconds + 资源观看秒数 ---
    today_start = datetime.combine(today, datetime.min.time())
    today_ps = db.query(PracticeSession).filter(
        PracticeSession.user_id == uid,
        PracticeSession.finished_at >= today_start,
    ).all()
    today_seconds = sum(p.duration_seconds or 0 for p in today_ps)
    # 叠加资源（视频）今日观看秒数
    today_watch = db.query(
        func.coalesce(func.sum(ResourceStudyLog.watch_seconds), 0)
    ).filter(
        ResourceStudyLog.user_id == uid,
        ResourceStudyLog.day == today.isoformat(),
    ).scalar() or 0
    today_seconds += int(today_watch)
    today_minutes = today_seconds // 60

    # --- streakDays：answer_records 日期去重后算连续天数（从今天往前数）---
    ans_dates = db.query(func.date(AnswerRecord.created_at)).filter(
        AnswerRecord.user_id == uid,
    ).distinct().all()
    ans_date_set = {datetime.strptime(d[0], "%Y-%m-%d").date() for d in ans_dates if d[0]}

    # 合并「登录打卡」日期：登录即计为学习日，与答题记录共同决定连续/累计天数
    checkin_dates = db.query(StudyCheckin.day).filter(StudyCheckin.user_id == uid).all()
    checkin_set = {d[0] for d in checkin_dates if d[0]}
    study_date_set = ans_date_set | checkin_set

    streak_days = 0
    cur = today
    while cur in study_date_set:
        streak_days += 1
        cur -= timedelta(days=1)

    # maxStreakDays：从所有 date 找最长连续
    max_streak = _calc_max_streak(study_date_set)

    # totalStudyDays：所有有记录的日期数
    total_study_days = len(study_date_set)

    # --- weakPoints：mastery < 60 的 learning_path + trend(本周 vs 上周) ---
    # 先算本周/上周 answer_records 中每 kp 的正确数和总数
    week_start = today - timedelta(days=today.weekday())   # 本周一
    last_week_start = week_start - timedelta(days=7)       # 上周一
    last_week_end = week_start                             # 上周日(不含)

    cur_week_rows = db.query(
        AnswerRecord.kp_id, func.count(AnswerRecord.id), func.sum(AnswerRecord.is_correct)
    ).filter(
        AnswerRecord.user_id == uid,
        func.date(AnswerRecord.created_at) >= week_start,
    ).group_by(AnswerRecord.kp_id).all()
    cur_week_stats = {row[0]: (row[1], row[2] or 0) for row in cur_week_rows}

    last_week_rows = db.query(
        AnswerRecord.kp_id, func.count(AnswerRecord.id), func.sum(AnswerRecord.is_correct)
    ).filter(
        AnswerRecord.user_id == uid,
        func.date(AnswerRecord.created_at) >= last_week_start,
        func.date(AnswerRecord.created_at) < last_week_end,
    ).group_by(AnswerRecord.kp_id).all()
    last_week_stats = {row[0]: (row[1], row[2] or 0) for row in last_week_rows}

    def _trend_pp(kp_id):
        c = cur_week_stats.get(kp_id)
        l = last_week_stats.get(kp_id)
        if c and l and c[0] > 0 and l[0] > 0:
            cur_pct = c[1] / c[0] * 100
            last_pct = l[1] / l[0] * 100
            return round(cur_pct - last_pct)
        return 0

    weak_points = []
    for r in lp_rows:
        q = acc_by_kp.get(r.kp_id)
        # 薄弱点 = 有作答记录、且【答题正确率】< 60（靶向练习盯的是做题，不看资源进度）
        if q and q[0] < 60:
            level = "danger" if q[0] < 40 else "warn"
            weak_points.append({
                "kpId": r.kp_id, "name": r.name,
                "accuracyRate": round(q[0]),
                "masteryRate": round(mastery_map.get(r.kp_id, 0)),
                "chapter": r.chapter,
                "errorCount": db.query(AnswerRecord).filter(
                    AnswerRecord.user_id == uid, AnswerRecord.kp_id == r.kp_id,
                    AnswerRecord.is_correct == 0,
                ).count(),
                "level": level,
                "trend": _trend_pp(r.kp_id),
            })
    weak_points.sort(key=lambda x: x["accuracyRate"])
    weak_points = weak_points[:5]

    # --- alerts 相关（open + read 都算需要关注，closed 排除）---
    all_alerts = db.query(Alert).filter(Alert.user_id == uid, Alert.status != "closed").all()
    open_alerts = [a for a in all_alerts if a.status == "open"]
    open_red = [a for a in open_alerts if a.level == "red"]
    open_yellow = [a for a in open_alerts if a.level == "yellow"]
    need_attention = sum(1 for a in all_alerts if a.level in ("red", "yellow"))

    # --- todos：doing 的 kp + 最紧急的 alert ---
    todos = []
    for n in lp_doing[:2]:
        todos.append({
            "id": f"TD_LP_{n.kp_id}", "type": "recommend", "level": "brand",
            "title": f"继续学习：{n.name}", "desc": f"当前进度 {n.progress or 0:.0f}%",
            "action": "继续学习", "target": "learn", "kpId": n.kp_id,
        })
    for a in open_alerts[:2]:
        lv = "danger" if a.level == "red" else "warn"
        todos.append({
            "id": f"TD_ALERT_{a.alert_id}", "type": "alert", "level": lv,
            "title": a.title[:30], "desc": a.desc[:40] if a.desc else "",
            "action": "去处理", "target": "alerts",
        })

    # 进行中的练习「存档」→ 待办「继续挑战」（检查会话历史；同一模式最多一条，需有作答进度）
    _mode_cn = {"weak": "薄弱点强化", "order": "顺序练习", "random": "随机练习", "wrong": "错题重练"}
    _ps_todos, _seen_modes = [], set()
    for ps in db.query(PracticeSession).filter(
        PracticeSession.user_id == uid,
        PracticeSession.status == "running",
    ).order_by(desc(PracticeSession.created_at)).all():
        if ps.mode in _seen_modes:
            continue
        _seen_modes.add(ps.mode)
        answered = db.query(func.count(AnswerRecord.id)).filter(
            AnswerRecord.session_id == ps.session_id).scalar() or 0
        if 0 < answered < (ps.total or 0):
            _ps_todos.append({
                "id": f"TD_PS_{ps.session_id}", "type": "practice", "level": "brand",
                "title": f"继续练习：{_mode_cn.get(ps.mode, ps.mode)}",
                "desc": f"已完成 {answered}/{ps.total} 题，点击继续挑战",
                "action": "继续挑战", "target": "practice", "sessionId": ps.session_id,
                "mode": ps.mode,
            })
    todos = _ps_todos + todos

    if not todos:
        node_name = current_node.get("name") if current_node else "课程学习"
        todos.append({
            "id": "TD_START", "type": "recommend", "level": "brand",
            "title": f"开始学习：{node_name}",
            "desc": "你还没有学习记录，点击前往课程图谱开始第一节",
            "action": "去学习", "target": "graph",
        })

    # --- recentActivities：以「练习会话」为单位展示（不再逐题刷「完成 KPxx 相关题目」）---
    # mode 用中文，时间取完成时间（未完成取创建时间），按时间倒序
    MODE_CN = {"weak": "薄弱点强化", "order": "顺序练习", "random": "随机练习", "wrong": "错题重练"}
    recent = []
    ps_rows = (
        db.query(PracticeSession)
        .filter(PracticeSession.user_id == uid)
        .order_by(desc(func.coalesce(PracticeSession.finished_at, PracticeSession.created_at)))
        .limit(50)
        .all()
    )
    for ps in ps_rows:
        ts = ps.finished_at or ps.created_at
        dur = ps.duration_seconds or 0
        if not dur and ps.finished_at and ps.created_at:
            dur = int((ps.finished_at - ps.created_at).total_seconds())
        mins = dur // 60 if dur else 0
        acc = ps.accuracy if ps.accuracy else (round(ps.correct / ps.total * 100) if ps.total else 0)
        recent.append({
            "id": f"A_PS_{ps.session_id}", "type": "practice",
            "title": MODE_CN.get(ps.mode, f"{ps.mode}练习"),
            "meta": f"{ps.correct}/{ps.total} 正确" + (f" · {mins}分钟" if mins else ""),
            "time": _fmt_time(ts),
            "time_sort": ts,
            "level": "ok" if acc >= 70 else "warn",
        })
    recent.sort(key=lambda x: x.get("time_sort", datetime.min), reverse=True)
    recent = recent[:50]

    # --- streakHistoryStart + streakHistory：学期内的「周 × 日」热力图 ---
    # 起点固定为学期第 1 周周一（不再从今天倒推 52 周），列 = 周、行 = 周一…周日，
    # 覆盖到学期末；若学期已结束则延伸到今天所在周，保证当前打卡不会被切掉。
    # 每天有答题记录则为 1 否则 0。
    WEEKS = max(SEMESTER_WEEKS, (today - SEMESTER_START).days // 7 + 1)
    DAYS = WEEKS * 7
    streak_start = SEMESTER_START
    # 构建日期→值的集合（streak 用 answer_records，练习活跃用 practice_sessions 也行，这里统一用 answer_records）
    streak_history = []
    for i in range(DAYS):
        d = streak_start + timedelta(days=i)
        streak_history.append(1 if d in study_date_set else 0)
    today_index = (today - streak_start).days   # 今天在网格中的下标；不在区间内时越界（前端按越界处理）

    # --- suggestedQuestions：从薄弱点自动生成 AI 推荐问题 ---
    suggested_questions = []
    for wp in weak_points[:4]:
        suggested_questions.append(f"请帮我讲解「{wp['name']}」，我在这个知识点上掌握率较低")
    if not suggested_questions:
        suggested_questions = ["请帮我梳理数据结构课程的知识体系", "如何高效准备期末考试？", "推荐一些经典的算法练习"]

    # --- 能力目标达成度：达标知识点数（完成率>=60%）/ 总知识点数 ---
    goal_achieve_rate = round(
        sum(1 for r in lp_rows if mastery_map.get(r.kp_id, 0) >= 60) / lp_total * 100, 1
    ) if lp_total else 0

    # 用户名：取 user.name 或 user.username 的 "下午好，XXX" 形式
    display_name = user.name or user.username or "同学"

    return ok({
        "userName": display_name,
        "overview": {
            "courseProgress": course_progress,
            "currentNode": current_node,
            "streakDays": streak_days,
            "currentStreak": streak_days,
            "maxStreak": max_streak,
            "totalDays": total_study_days,
            "todayStudyMinutes": today_minutes,
            "needAttention": need_attention,
            "status": "danger" if open_red else ("warn" if need_attention else "ok"),
            "streakHistoryStart": streak_start.strftime("%Y-%m-%d"),
            "streakHistory": streak_history,
            "streakWeeks": WEEKS,
            "streakTodayIndex": today_index,
            "semesterLabel": f"{streak_start.year}-{streak_start.year + 1}",
        },
        "coreMetrics": {
            "completionRate": course_progress,
            "masteryRate": mastery_rate,
            "goalAchieveRate": round(goal_achieve_rate, 1),
            "totalKpCount": lp_total,
        "masteredKpCount": sum(1 for r in lp_rows if mastery_map.get(r.kp_id, 0) >= 60),
            "completedKpCount": len(lp_done),
            "updatedAt": datetime.now().strftime("%Y-%m-%d %H:%M"),
        },
        "todos": todos,
        "weakPoints": weak_points,
        "needAttention": need_attention,
        "recentActivities": recent,
        "suggestedQuestions": suggested_questions,
    })


def _calc_max_streak(date_set: set) -> int:
    if not date_set:
        return 0
    sorted_dates = sorted(date_set)
    max_s = cur_s = 1
    for i in range(1, len(sorted_dates)):
        if (sorted_dates[i] - sorted_dates[i-1]).days == 1:
            cur_s += 1
            max_s = max(max_s, cur_s)
        else:
            cur_s = 1
    return max_s


def _fmt_time(dt: datetime) -> str:
    if not dt:
        return ""
    local = _to_local(dt)
    now = datetime.now(_CN_TZ).replace(tzinfo=None)
    today = now.date()
    d = local.date()
    if d == today:
        return f"今天 {local.strftime('%H:%M')}"
    elif d == today - timedelta(days=1):
        return f"昨天 {local.strftime('%H:%M')}"
    elif (today - d).days < 7:
        return f"{(today - d).days} 天前"
    else:
        return local.strftime("%m-%d %H:%M")


# =============================================================================
# 资源中心
# =============================================================================

@router.get("/resources")
def student_resources(
    type: str = Query("all"),
    kpId: str = Query(None),
    category: str = Query(None),
    keyword: str = Query(None),
    page: int = Query(1),
    size: int = Query(20),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(Resource)
    if type and type != "all":
        q = q.filter(Resource.type == type)
    if kpId:
        q = q.filter(Resource.kp_id == kpId)
    if category:
        q = q.filter(Resource.category == category)
    if keyword:
        like = f"%{keyword}%"
        q = q.filter(Resource.title.like(like) | Resource.kp.like(like) | Resource.source.like(like))
    all_items = q.all()
    total = len(all_items)
    start = (page - 1) * size
    end = start + size
    page_items = all_items[start:end]

    # 用户真实学习进度（视频秒 / 文档页 → 百分比）
    prog_map = {
        p.res_id: p for p in db.query(ResourceProgress).filter(
            ResourceProgress.user_id == user.user_id,
            ResourceProgress.res_id.in_([r.res_id for r in page_items]),
        ).all()
    }

    items = [
        {
            "resId": r.res_id, "type": r.type, "title": r.title,
            "kpId": r.kp_id, "kp": r.kp, "category": r.category,
            "source": r.source, "views": r.views,
            "progress": prog_map[r.res_id].progress if r.res_id in prog_map else 0,
            "position": prog_map[r.res_id].position if r.res_id in prog_map else 0,
            "duration": r.duration, "pages": r.pages, "count": r.count,
            "url": r.url or "",
        }
        for r in page_items
    ]
    return ok(list_response(items, total))


@router.get("/resources/{res_id}/progress")
def get_resource_progress(res_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """获取某个资源的真实学习进度（视频：秒；文档：页码/百分比）"""
    p = db.query(ResourceProgress).filter(
        ResourceProgress.user_id == user.user_id,
        ResourceProgress.res_id == res_id,
    ).first()
    r = db.query(Resource).filter(Resource.res_id == res_id).first()
    if not r:
        return fail("资源不存在", 404)
    dur_sec = _duration_to_seconds(r.duration) if r.duration else 0
    total_pages = r.pages or 0
    if p:
        # 百分比兜底：若 progress 为 0 但 position 有值，则用 position 估算
        progress = p.progress
        if not progress and dur_sec and r.type == "video":
            progress = min(100, int(round(p.position / dur_sec * 100))) if dur_sec else 0
        if not progress and total_pages and r.type in ("ppt", "doc"):
            progress = min(100, int(round(p.position / total_pages * 100))) if total_pages else 0
        return ok({
            "resId": res_id, "type": r.type,
            "progress": progress, "position": p.position,
            "durationSec": dur_sec, "totalPages": total_pages,
        })
    return ok({
        "resId": res_id, "type": r.type,
        "progress": 0, "position": 0,
        "durationSec": dur_sec, "totalPages": total_pages,
    })


@router.post("/resources/{res_id}/progress")
def save_resource_progress(
    res_id: str,
    body: dict,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """保存学习进度：body = {progress: 0~100, position: 秒/页码}"""
    r = db.query(Resource).filter(Resource.res_id == res_id).first()
    if not r:
        return fail("资源不存在", 404)
    progress = int(body.get("progress", 0) or 0)
    position = int(body.get("position", 0) or 0)
    progress = max(0, min(100, progress))
    position = max(0, position)

    # 视频：用秒计算百分比更准
    if r.type == "video" and not progress:
        dur_sec = _duration_to_seconds(r.duration) if r.duration else 0
        if dur_sec:
            progress = min(100, int(round(position / dur_sec * 100)))
    # 文档：用页码计算百分比
    if r.type in ("ppt", "doc") and not progress and r.pages:
        progress = min(100, int(round(position / r.pages * 100)))

    p = db.query(ResourceProgress).filter(
        ResourceProgress.user_id == user.user_id,
        ResourceProgress.res_id == res_id,
    ).first()
    prev_progress = p.progress if p else 0
    prev_position = p.position if p else 0
    if not p:
        p = ResourceProgress(user_id=user.user_id, res_id=res_id)
        db.add(p)
    # 进度/位置不回退：已达到的更高进度（尤其已 100%）始终保留，
    # 重复观看、回拖进度条或中途暂停都不会把已完成资源重置为未完成。
    p.progress = max(prev_progress or 0, progress)
    p.position = max(prev_position or 0, position)
    p.updated_at = datetime.utcnow()

    # 视频：把本次「前进的秒数」累计进今日观看时长（后退/拖动不计）
    if r.type == "video":
        delta = max(0, position - prev_position)
        _add_watch_seconds(db, user.user_id, date.today(), delta)

    # 同步刷新该资源所属知识点在学习路径中的掌握率与状态
    # 先 flush，确保上方写入的 ResourceProgress 对掌握率计算可见（避免读到旧值）
    db.flush()
    if r.kp_id:
        _sync_lp_from_resource_progress(db, user.user_id, r.kp_id)

    db.commit()
    return ok({"resId": res_id, "progress": progress, "position": position})


def _sync_lp_from_resource_progress(db: Session, user_id: str, kp_id: str):
    """根据用户在某知识点下所有资源的真实进度，刷新 learning_paths 的 mastery/status。

    当学生看视频/文档后，左侧学习路径和学情矩阵应同步变化，而不是一直显示“未开始”。
    注意：展示状态以习题掌握率为主，资源进度仅作为“正在学习”的兜底判断。
    """
    from ..routers.graph import (
        _mastery_for_user,
        _quiz_mastery_for_user,
        _status_from_quiz_mastery,
    )

    # 计算该知识点当前学习完成率（资源进度）与习题掌握率（答题记录）
    mastery_map = _mastery_for_user(user_id, db)
    quiz_map = _quiz_mastery_for_user(user_id, db)
    has_quiz = set(quiz_map.keys())
    mastery = mastery_map.get(kp_id, 0)
    quiz = quiz_map.get(kp_id, 0)
    status = _status_from_quiz_mastery(quiz, mastery, kp_id in has_quiz)

    lp = db.query(LearningPath).filter(
        LearningPath.user_id == user_id,
        LearningPath.kp_id == kp_id,
    ).first()
    if lp:
        lp.mastery = mastery
        lp.progress = mastery
        lp.status = status
        return

    # 知识点尚无 LP 记录时，自动创建一条（字段构造与 _ensure_learning_path 共用同一份）
    node = db.query(GraphNode).filter(
        GraphNode.id == kp_id, GraphNode.graph_type == "knowledge"
    ).first()
    if not node:
        return
    from ..services.learning_path import make_row
    max_step = db.query(func.max(LearningPath.step)).filter(
        LearningPath.user_id == user_id,
        LearningPath.course_id == node.course_id,
    ).scalar() or 0
    res_count = db.query(Resource).filter(Resource.kp_id == kp_id).count()
    db.add(make_row(
        user_id=user_id,
        course_id=node.course_id or "C2026DS001",
        step=max_step + 1,
        node=node,
        res_count=res_count,
        state=(mastery, status),
    ))


def _add_watch_seconds(db: Session, uid: str, day: date, delta: int):
    """把 delta 秒累计到 user 当日 resource_study_log（不存在则新建）"""
    if delta <= 0:
        return
    row = db.query(ResourceStudyLog).filter(
        ResourceStudyLog.user_id == uid,
        ResourceStudyLog.day == day.isoformat(),
    ).first()
    if not row:
        row = ResourceStudyLog(user_id=uid, day=day.isoformat(), watch_seconds=0)
        db.add(row)
        db.flush()
    row.watch_seconds += delta


@router.post("/resources/{res_id}/view")
def resource_view(res_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """记录一次资源查看，返回最新观看次数"""
    r = db.query(Resource).filter(Resource.res_id == res_id).first()
    if not r:
        return fail("资源不存在", 404)
    r.views = (r.views or 0) + 1
    db.commit()
    return ok({"resId": r.res_id, "views": r.views})


@router.get("/resource-stats")
def resource_stats(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """学习资源进度统计 — 从 ResourceProgress 聚合"""
    uid = user.user_id
    resources = db.query(Resource).all()
    res_map = {r.res_id: r for r in resources}
    progress_rows = db.query(ResourceProgress).filter(ResourceProgress.user_id == uid).all()
    progress_map = {p.res_id: p for p in progress_rows}

    total = len(resources)
    started = 0
    completed = 0
    total_progress = 0
    watch_seconds = 0
    read_pages = 0

    for r in resources:
        p = progress_map.get(r.res_id)
        prog = p.progress if p else 0
        total_progress += prog
        if prog > 0:
            started += 1
        if prog >= 100:
            completed += 1
        pos = p.position if p else 0
        if r.type == "video":
            watch_seconds += pos
        elif r.type in ("doc", "ppt"):
            read_pages += pos

    recent = []
    studied = [p for p in progress_rows if p.progress > 0]
    studied.sort(key=lambda x: x.updated_at or datetime.min, reverse=True)
    for p in studied[:5]:
        r = res_map.get(p.res_id)
        if not r:
            continue
        recent.append({
            "resId": r.res_id,
            "title": r.title,
            "type": r.type,
            "progress": p.progress,
            "position": p.position,
            "updatedAt": p.updated_at.isoformat() if p.updated_at else None,
        })

    return ok({
        "total": total,
        "started": started,
        "completed": completed,
        "avgProgress": round(total_progress / total, 1) if total else 0.0,
        "watchMinutes": round(watch_seconds / 60, 1),
        "readPages": read_pages,
        "recent": recent,
    })


# =============================================================================
# 掌握矩阵 — 从真实 GraphNode + 用户专属 learning_paths 动态计算
# 注意：章节与知识点完全由 GraphNode 派生，不再使用硬编码列表，
#       避免与知识图谱/学习路径章节结构漂移导致学情缺章、漏知识点。
# =============================================================================


@router.get("/mastery/matrix")
def mastery_matrix(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """知识点掌握矩阵 — 从用户专属 learning_paths 动态计算"""
    uid = user.user_id
    lp_map = {lp.kp_id: lp for lp in db.query(LearningPath).filter(LearningPath.user_id == uid).all()}
    gn_map = {gn.id: gn for gn in db.query(GraphNode).filter(GraphNode.graph_type == "knowledge").all()}
    wrong_counts = dict(db.query(
        AnswerRecord.kp_id, func.count(AnswerRecord.id)
    ).filter(
        AnswerRecord.user_id == uid, AnswerRecord.is_correct == 0
    ).group_by(AnswerRecord.kp_id).all())
    total_counts = dict(db.query(
        AnswerRecord.kp_id, func.count(AnswerRecord.id)
    ).filter(AnswerRecord.user_id == uid).group_by(AnswerRecord.kp_id).all())

    # 按真实 GraphNode 章节动态分组（章节顺序按数字排序，与知识图谱/学习路径一致）
    def _ch_num(ch):
        digits = "".join(filter(str.isdigit, ch or ""))
        return int(digits) if digits else 999

    by_chapter = {}
    for gn in gn_map.values():
        by_chapter.setdefault(gn.chapter, []).append(gn)
    for ch in by_chapter:
        by_chapter[ch].sort(key=lambda g: g.id)

    # 实时掌握率（答题正确率 + 资源进度），直接由权威数据源计算，
    # 不依赖可能滞后的 learning_paths.mastery，保证学情矩阵与资源进度永远同步。
    from ..routers.graph import _mastery_for_user, _mastery_from_records
    mastery_map = _mastery_for_user(uid, db)
    quiz_mastery_map = _mastery_from_records(uid, db)

    result = []
    for chapter_name in sorted(by_chapter, key=_ch_num):
        items = []
        for gn in by_chapter[chapter_name]:
            kp_id = gn.id
            lp = lp_map.get(kp_id)
            m = mastery_map.get(kp_id, 0)
            qm = quiz_mastery_map.get(kp_id, 0)
            comp = 100 if m >= 80 else round(m)
            if m >= 85:
                level = "excellent"
            elif m >= 70:
                level = "good"
            elif m >= 50:
                level = "fair"
            elif m > 0:
                level = "weak"
            else:
                level = "none"
            items.append({
                "kpId": kp_id, "name": (lp.name if lp else None) or gn.name,
                "completion": comp, "mastery": round(m),
                "quizMastery": round(qm),
                "level": level,
                "questions": total_counts.get(kp_id, 0),
                "correct": total_counts.get(kp_id, 0) - wrong_counts.get(kp_id, 0),
                "isKey": gn.is_key or False,
            })
        chapter_completion = round(sum(i["completion"] for i in items) / len(items), 1) if items else 0
        chapter_mastery = round(sum(i["mastery"] for i in items) / len(items), 1) if items else 0
        chapter_quiz_mastery = round(sum(i["quizMastery"] for i in items) / len(items), 1) if items else 0
        result.append({
            "chapter": chapter_name,
            "completionRate": chapter_completion,
            "masteryRate": chapter_mastery,
            "quizMasteryRate": chapter_quiz_mastery,
            "items": items,
        })
    return ok(result)


# =============================================================================
# 能力雷达图 — 从 goal 图谱 + learning_paths 动态计算
# =============================================================================

# goal → 维度映射
_GOAL_DIMENSIONS = {
    "G1": ("线性结构运用", ["KP11", "KP12", "KP13", "KP14", "KP21", "KP22", "KP23", "KP24"]),
    "G2": ("树形结构构建", ["KP31", "KP32", "KP33", "KP34", "KP44"]),
    "G3": ("图结构与算法", ["KP41", "KP42", "KP43", "KP51", "KP52", "KP53"]),
    "G4": ("复杂度分析", ["KP01", "KP02"]),
    "G5": ("算法设计与实现", ["KP01", "KP13", "KP24", "KP32", "KP43", "KP51", "KP52"]),
    "G6": ("工程问题建模", ["KP52", "KP44", "KP21"]),
}


@router.get("/ability/radar")
def ability_radar(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """能力目标达成度 — 从 learning_paths 动态计算 6 个维度"""
    uid = user.user_id
    lp_map = {lp.kp_id: lp for lp in db.query(LearningPath).filter(LearningPath.user_id == uid).all()}

    dim_names = [name for name, _ in _GOAL_DIMENSIONS.values()]
    my_data = []
    for dim_name, kp_ids in _GOAL_DIMENSIONS.values():
        scores = [lp_map[kp].mastery for kp in kp_ids if kp in lp_map and lp_map[kp].mastery and lp_map[kp].mastery > 0]
        my_data.append(round(sum(scores) / len(scores), 1) if scores else 0)

    # 班级平均：按真实同学 learning_paths 掌握率逐维度聚合（无数据则为 0，而非伪造）
    stu = db.query(User).filter(User.user_id == uid).first()
    class_name = stu.class_name if stu else None
    class_ids = [c.user_id for c in db.query(User).filter(
        User.role == "student", User.class_name == class_name).all()] if class_name else []
    class_lps = db.query(LearningPath).filter(LearningPath.user_id.in_(class_ids)).all() if class_ids else []
    class_avg_data = []
    for dim_name, kp_ids in _GOAL_DIMENSIONS.values():
        all_scores = [lp.mastery for lp in class_lps
                      if lp.kp_id in kp_ids and lp.mastery and lp.mastery > 0]
        class_avg_data.append(round(sum(all_scores) / len(all_scores), 1) if all_scores else 0)

    return ok({
        "categories": dim_names,
        "indicators": [
            {"name": n, "max": 100} for n in dim_names
        ],
        "series": [
            {"name": "我的达成度", "data": my_data},
            {"name": "班级平均", "data": class_avg_data},
            {"name": "目标基线", "data": [80, 80, 80, 80, 75, 75]},
        ],
    })


# =============================================================================
# 成长轨迹 — 从 answer_records 按周聚合
# =============================================================================

@router.get("/growth")
def growth(
    dimension: str = Query("week"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """成长轨迹 — 按周从 answer_records 聚合生成曲线"""
    uid = user.user_id
    today = date.today()

    # 取过去 8 周的 answer_records
    eight_weeks_ago = today - timedelta(weeks=8)
    recs = db.query(AnswerRecord).filter(
        AnswerRecord.user_id == uid,
        func.date(AnswerRecord.created_at) >= eight_weeks_ago,
    ).all()

    # 按 ISO 周分组
    week_data = defaultdict(lambda: {"correct": 0, "total": 0, "kps": set()})
    for r in recs:
        if not r.created_at:
            continue
        iso_year, iso_week, _ = r.created_at.isocalendar()
        key = f"{iso_year}-W{iso_week:02d}"
        week_data[key]["total"] += 1
        if r.is_correct:
            week_data[key]["correct"] += 1
        if r.kp_id:
            week_data[key]["kps"].add(r.kp_id)

    # 有序周：以“当前周周一(8/31)”为第1周起点，往后排（第1周→第8周，时间前进）
    first_monday = today - timedelta(days=today.isoweekday() - 1)
    weeks = []
    for i in range(0, 8):
        monday = first_monday + timedelta(weeks=i)
        iso_year, iso_week, _ = monday.isocalendar()
        key = f"{iso_year}-W{iso_week:02d}"
        w = week_data.get(key, {"correct": 0, "total": 0, "kps": set()})
        weeks.append({
            "label": f"第{i+1}周·{monday.strftime('%m/%d')}",
            "correct": w["correct"], "total": w["total"],
            "kp_count": len(w["kps"]),
        })

    # 累计完成率：已掌握知识点占比。
    # 原实现依赖 learning_paths.mastered_at，但该字段只有 seed 会写（seed 不再生成
    # 学习路径后恒为 NULL），故改为按真实掌握率统计；分母也不再写死 28（图谱已是 34 个）。
    total_kp = db.query(GraphNode).filter(
        GraphNode.graph_type == "knowledge",
    ).count() or 1
    mastered_kps = db.query(LearningPath).filter(
        LearningPath.user_id == uid,
        LearningPath.mastery >= 80,
    ).count()
    mastered_ratio = round(min(mastered_kps, total_kp) / total_kp * 100, 1)

    completion_series = []
    mastery_series = []
    for w in weeks:
        completion_series.append(mastered_ratio)
        if w["total"] > 0:
            mastery_series.append(round(w["correct"] / w["total"] * 100, 1))
        else:
            mastery_series.append(0)

    return ok({
        "dimension": dimension,
        "xAxis": [w["label"] for w in weeks],
        "series": [
            {"name": "知识点完成率", "data": completion_series, "color": "#6366f1"},
            {"name": "掌握率(本周)", "data": mastery_series, "color": "#22c55e"},
        ],
        "milestones": [],
    })


# =============================================================================
# 班级对比 — 全班级 learning_paths 排名
# =============================================================================

@router.get("/compare")
def compare(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """与班级对比 — 动态排名"""
    uid = user.user_id
    class_id = _resolve_class_id(db, user)

    # 同班所有学生
    students = db.query(User).filter(User.role == "student", User.class_name == user.class_name).all()
    student_uids = [s.user_id for s in students]

    # 为每个学生算两个核心指标
    my_lp = db.query(LearningPath).filter(LearningPath.user_id == uid).all()
    my_done = sum(1 for r in my_lp if r.status == "done")
    my_mastery = round(sum(r.mastery or 0 for r in my_lp if r.mastery and r.mastery > 0) /
                       max(len([r for r in my_lp if r.mastery and r.mastery > 0]), 1), 1)

    all_stats = []
    for suid in student_uids:
        lps = db.query(LearningPath).filter(LearningPath.user_id == suid).all()
        done = sum(1 for r in lps if r.status == "done")
        actives = [r for r in lps if r.mastery and r.mastery > 0]
        avg_m = round(sum(r.mastery for r in actives) / len(actives), 1) if actives else 0
        all_stats.append((suid, done, avg_m))

    all_stats.sort(key=lambda x: x[1], reverse=True)
    my_rank = next((i+1 for i, s in enumerate(all_stats) if s[0] == uid), len(all_stats))

    # 班级平均
    class_avg_completion = round(sum(s[1] for s in all_stats) / len(all_stats), 1) if all_stats else 0
    class_avg_mastery = round(sum(s[2] for s in all_stats) / len(all_stats), 1) if all_stats else 0
    class_best_completion = max((s[1] for s in all_stats), default=0)
    class_best_mastery = max((s[2] for s in all_stats), default=0)

    return ok({
        "myRank": my_rank,
        "totalStudents": len(all_stats),
        "percentile": round((1 - my_rank / max(len(all_stats), 1)) * 100, 0),
        "items": [
            {"metric": "完成的知识点数", "mine": my_done, "classAvg": class_avg_completion,
             "classBest": class_best_completion, "diff": round(my_done - class_avg_completion, 1)},
            {"metric": "平均掌握率", "mine": my_mastery, "classAvg": class_avg_mastery,
             "classBest": class_best_mastery, "diff": round(my_mastery - class_avg_mastery, 1)},
        ],
    })


# =============================================================================
# 预警（已有）
# =============================================================================

@router.get("/alerts")
def student_alerts(
    level: str = Query("all"),
    status: str = Query("all"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    base_q = db.query(Alert).filter(Alert.user_id == user.user_id)
    stats = {
        "red": base_q.filter(Alert.level == "red").count(),
        "yellow": base_q.filter(Alert.level == "yellow").count(),
        "green": base_q.filter(Alert.level == "green").count(),
    }
    open_stats = {
        "red": base_q.filter(Alert.level == "red", Alert.status == "open").count(),
        "yellow": base_q.filter(Alert.level == "yellow", Alert.status == "open").count(),
    }
    q = base_q
    if level and level != "all":
        q = q.filter(Alert.level == level)
    if status and status != "all":
        q = q.filter(Alert.status == status)
    rows = q.order_by(Alert.created_at.desc()).all()

    def alert_to_dict(a: Alert) -> dict:
        return {
            "alertId": a.alert_id, "level": a.level, "type": a.type,
            "title": a.title, "desc": a.desc, "trigger": a.trigger,
            "kpId": a.kp_id, "kp": a.kp_name,
            "detail": loads(a.detail_json) or {},
            "suggestions": loads(a.suggestions_json) or [],
            "createdAt": fmt_dt(a.created_at),
            "status": a.status,
        }

    data = list_response([alert_to_dict(a) for a in rows], len(rows))
    data["stats"] = stats
    data["openStats"] = open_stats
    return ok(data)


@router.put("/alerts/{alert_id}/read")
def read_alert(
    alert_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    alert = db.query(Alert).filter(Alert.alert_id == alert_id).first()
    if not alert:
        return fail("预警不存在", 404)
    # 越权校验：只能标记本人预警为已读
    if alert.user_id != user.user_id:
        return fail("无权操作该预警", 403)
    alert.status = "read"
    db.commit()
    return ok({"alertId": alert_id, "read": True})


# =============================================================================
# 教师私信
# =============================================================================

@router.get("/messages")
def student_messages(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rows = db.query(Message).filter(Message.user_id == user.user_id).order_by(Message.created_at.desc()).all()
    items = [
        {
            "msgId": m.msg_id, "from": m.from_user, "fromName": m.from_name,
            "title": m.title, "content": m.content,
            "time": fmt_dt(m.created_at),
            "read": bool(m.read),
        }
        for m in rows
    ]
    return ok(list_response(items, len(items)))


@router.put("/messages/{msg_id}/read")
def read_message(
    msg_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """标记一条私信/通知为已读"""
    m = db.query(Message).filter(Message.msg_id == msg_id, Message.user_id == user.user_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="消息不存在")
    m.read = 1
    db.commit()
    return ok({"msgId": msg_id, "read": True})
