"""统一的预警检测服务。

按真实学习数据生成 / 刷新 / 删除 Alert：
正确率 = 该知识点下「每道题最近一次作答」的对错（按题去重，避免重复作答 / 补救练习拉偏）：
- 学生达到预警条件 → 生成 Alert（level / type / class_id / trigger / detail_json，status=open）；
- 条件恢复（掌握率回到预警线以上）→ 直接删除对应的自动预警记录；
- 教师确认只表示已复核，系统仍按最新学习数据刷新红黄等级并自动解除；
- 教师忽略的告警固定按 green / ignored 处理，不再被检测服务重新激活。

分级（掌握率，预警线；注意「预警线」与 app/constants.py 的掌握率「达标线」是两个概念，
本模块既不引用也不跟随达标线变动）：
  - mastery < RED_BELOW    → red   / mastery_low（预警）
  - RED_BELOW ≤ mastery < YELLOW_BELOW → yellow / mastery_low（需关注）
  - mastery ≥ YELLOW_BELOW → 正常（不生成告警；若有有效预警则删除）

「已学」门槛：该知识点至少作答过 ENGAGE_MIN 道【不同】题，避免对未开始/证据不足的知识点误报。
"""
import json
import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models.alert import Alert
from ..models.user import User, ClassInfo
from ..models.course import Course, Resource  # noqa: F401  确保 courses 表已注册
from ..models.graph import GraphNode
from ..models.practice import AnswerRecord

# 课程归属不再写死：早期这里固定用演示课 "C2026DS001"，真实库里没有该课程，
# 建预警时外键约束直接失败（异常被调用方吞掉，表现为预警表永远为空）。
# 现在按被预警知识点自己的 GraphNode.course_id 写入。
ALERT_TYPE = "mastery_low"
RED_BELOW = 50       # 掌握率 < 50 → 预警
YELLOW_BELOW = 60    # 50~60 → 需关注
ENGAGE_MIN = 2       # 至少作答过 2 道【不同】题才计入（按题去重后）

# 触发规则文案：由上面的阈值常量拼出来，避免改了阈值却漏改文案
# （历史 mock 数据里正文阈值与规则号互相打架，就是手写两份导致的）
TRIGGER = (
    f"知识点作答正确率 < {RED_BELOW}% 触发预警"
    f"（{RED_BELOW}%–{YELLOW_BELOW}% 为需关注，≥{YELLOW_BELOW}% 达标）；"
    f"按题去重取最近一次作答，至少作答 {ENGAGE_MIN} 道不同题才计入"
)


def _class_id_map(db: Session) -> dict:
    return {c.name: c.class_id for c in db.query(ClassInfo).all()}


def _level_of(mastery: float):
    if mastery < RED_BELOW:
        return "red"
    if mastery < YELLOW_BELOW:
        return "yellow"
    return None


def _suggestions(db: Session, kp_id: str, kp_name: str) -> str:
    """该知识点的补救建议：只给靶向练习（目标是把做题正确率刷上来，不推荐资源）。"""
    return json.dumps(
        [{"type": "practice", "text": f"完成 5 道「{kp_name}」靶向练习", "kpId": kp_id}],
        ensure_ascii=False,
    )


def detect_alerts(db: Session, users=None) -> dict:
    """为给定学生（默认全体学生）检测并同步告警。返回 {created, updated, deleted}。"""
    if users is None:
        users = db.query(User).filter(User.role == "student").all()
    cmap = _class_id_map(db)
    created = updated = deleted = 0

    # 清理旧逻辑遗留的自动解除记录；恢复后的预警不再保留在列表中。
    for closed_row in db.query(Alert).filter(Alert.status == "closed").all():
        db.delete(closed_row)
        deleted += 1

    # 兼容合并前已经存在的“ignored 但仍为 red/yellow”历史记录。
    # ignored 的统一业务含义是教师判定正常，因此先归一为绿色。
    for ignored_row in db.query(Alert).filter(
        Alert.status == "ignored", Alert.level != "green",
    ).all():
        ignored_row.level = "green"
        ignored_row.suggestions_json = "[]"
        updated += 1

    from .scoring import quiz_accuracy_by_kp
    from ..models.question import Question

    for u in users:
        # 该生需要评估的课程 = 「有作答记录的课程」∪「现有预警所在的课程」。
        # 后者保证「答题记录被清空 / 题目被下架」时仍会走到该课程，把失去依据的旧预警清掉（P44）。
        ans_courses = {c for (c,) in db.query(AnswerRecord.course_id).filter(
            AnswerRecord.user_id == u.user_id,
            AnswerRecord.course_id.isnot(None),
        ).distinct().all() if c}
        alert_courses = {c for (c,) in db.query(Alert.course_id).filter(
            Alert.user_id == u.user_id, Alert.type == ALERT_TYPE,
        ).distinct().all() if c}

        for course_id in ans_courses | alert_courses:
            # 统一口径的「答题正确率」表（按题去重取最近一次），**限定在本课程内**
            acc_map = quiz_accuracy_by_kp(db, u.user_id, course_id=course_id)

            # P48：本课程里「以它为主 KP」的题量。为 0 说明该点只靠 kp_ids 标签命中，
            # 分母天生就小（全课仅 2 道标签题 → 错 1 道就到 50%），门槛相应提到 ≥3 道不同题。
            primary_q_count = {kp: n for kp, n in db.query(
                Question.kp_id, func.count(Question.q_id),
            ).filter(
                Question.course_id == course_id,
                Question.kp_id.isnot(None),
            ).group_by(Question.kp_id).all()}

            kp_rows = db.query(GraphNode.id, GraphNode.name).filter(
                GraphNode.graph_type == "knowledge",
                GraphNode.course_id == course_id,
            ).all()
            kp_names = {i: n for i, n in kp_rows}
            existing = {a.kp_id: a for a in db.query(Alert).filter(
                Alert.user_id == u.user_id,
                Alert.course_id == course_id,
                Alert.type == ALERT_TYPE,
            ).all()}

            # P44：「现有预警 ∪ 本次证据」并集遍历 —— 只遍历证据会漏掉「证据已消失」的旧预警，
            # 那条预警既不会更新也不会删除，学生端会一直挂着一条谁也消不掉的红点。
            for kp in set(acc_map) | set(existing):
                rate, hits = acc_map.get(kp) or (None, 0)
                threshold = ENGAGE_MIN if primary_q_count.get(kp, 0) > 0 else ENGAGE_MIN + 1
                row = existing.get(kp)

                if rate is None or hits < threshold or kp not in kp_names:
                    # 证据不足（题目被删 / 标签被改 / 记录被清）→ 预警失去依据，删除。
                    # ignored 是教师主动判定过的历史记录，继续保留。
                    if row is not None and row.status != "ignored":
                        db.delete(row)
                        deleted += 1
                    continue

                name = kp_names.get(kp, kp)
                level = _level_of(rate)
                if level:
                    title = f"「{name}」掌握率偏低"
                    desc = f"当前作答正确率 {rate:.0f}%，低于课程达标线 {YELLOW_BELOW}%。"
                    detail = json.dumps(
                        {"current": rate, "threshold": YELLOW_BELOW, "redBelow": RED_BELOW},
                        ensure_ascii=False,
                    )
                    sugs = _suggestions(db, kp, name)
                    # 课程归属取自本次评估的课程（知识点已确认属于该课程）。
                    # ⚠️ 历史上这里写死演示课 "C2026DS001"，而真实库里没有这门课，
                    # 建预警会直接外键失败（异常被上层吞掉 → 学生端/教师端预警永远是空的）。
                    if row is None:
                        db.add(Alert(
                            alert_id="AL" + uuid.uuid4().hex[:10], course_id=course_id,
                            user_id=u.user_id, class_id=cmap.get(u.class_name) or None,
                            level=level, type=ALERT_TYPE, title=title, desc=desc,
                            trigger=TRIGGER, kp_id=kp, kp_name=name,
                            detail_json=detail, suggestions_json=sugs, status="open",
                        ))
                        created += 1
                    elif row.status in ("open", "read", "reviewed"):
                        row.level, row.title, row.desc, row.trigger, row.detail_json, row.suggestions_json = level, title, desc, TRIGGER, detail, sugs
                        updated += 1
                    # ignored → 教师已判定无需处理，保持 green / ignored，不重新激活
                else:
                    # 恢复：直接删除自动预警；确认过或已读的记录也一并移除。
                    # ignored 是教师主动处理的历史记录，继续保留。
                    if row is not None and row.status != "ignored":
                        db.delete(row)
                        deleted += 1

    db.commit()
    return {"created": created, "updated": updated, "deleted": deleted}
