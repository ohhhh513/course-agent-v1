"""统一的预警检测服务。

按真实学习数据生成 / 刷新 / 关闭 Alert：
正确率 = 该知识点下「每道题最近一次作答」的对错（按题去重，避免重复作答 / 补救练习拉偏）：
- 学生达到预警条件 → 生成 Alert（level / type / class_id / trigger / detail_json，status=open）；
- 条件恢复（掌握率回到达标线以上）→ 把该生仍为 open 的告警统一置为 closed；
- 不覆盖教师已处理的告警：status 为 reviewed / ignored 的记录一律不重建、不改写。

分级（掌握率，达标线 60%）：
  - mastery < 50  → red   / mastery_low（预警）
  - 50 ≤ mastery < 60 → yellow / mastery_low（需关注）
  - mastery ≥ 60 → 正常（不生成告警；若有 open 则关闭）

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

COURSE_ID = "C2026DS001"
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
    """为给定学生（默认全体学生）检测并同步告警。返回 {created, updated, reopened, closed}。"""
    if users is None:
        users = db.query(User).filter(User.role == "student").all()
    cmap = _class_id_map(db)
    created = updated = reopened = closed = 0

    for u in users:
        # 该生每个知识点的「答题正确率」——统一口径（services/scoring：按题去重取最近一次）
        from .scoring import quiz_accuracy_by_kp
        acc_map = {kp: acc for kp, (acc, n) in quiz_accuracy_by_kp(db, u.user_id).items()
                   if n >= ENGAGE_MIN}
        if not acc_map:
            continue

        kp_names = dict(db.query(GraphNode.id, GraphNode.name).filter(
            GraphNode.graph_type == "knowledge", GraphNode.id.in_(list(acc_map.keys())),
        ).all())
        existing = {a.kp_id: a for a in db.query(Alert).filter(
            Alert.user_id == u.user_id, Alert.type == ALERT_TYPE,
        ).all()}

        for kp, mastery in acc_map.items():
            name = kp_names.get(kp, kp)
            level = _level_of(mastery)
            row = existing.get(kp)

            if level:
                title = f"「{name}」掌握率偏低"
                desc = f"当前作答正确率 {mastery:.0f}%，低于课程达标线 {YELLOW_BELOW}%。"
                detail = json.dumps(
                    {"current": mastery, "threshold": YELLOW_BELOW, "redBelow": RED_BELOW},
                    ensure_ascii=False,
                )
                sugs = _suggestions(db, kp, name)
                if row is None:
                    db.add(Alert(
                        alert_id="AL" + uuid.uuid4().hex[:10], course_id=COURSE_ID,
                        user_id=u.user_id, class_id=cmap.get(u.class_name, ""),
                        level=level, type=ALERT_TYPE, title=title, desc=desc,
                        trigger=TRIGGER, kp_id=kp, kp_name=name,
                        detail_json=detail, suggestions_json=sugs, status="open",
                    ))
                    created += 1
                elif row.status == "open":
                    row.level, row.title, row.desc, row.trigger, row.detail_json, row.suggestions_json = level, title, desc, TRIGGER, detail, sugs
                    updated += 1
                elif row.status == "closed":
                    # 恢复后又重新触达 → 重新打开（刷新内容）
                    row.level, row.title, row.desc, row.trigger, row.detail_json, row.suggestions_json, row.status = level, title, desc, TRIGGER, detail, sugs, "open"
                    reopened += 1
                # reviewed / ignored → 尊重教师处理，不动
            else:
                # 恢复：等级置为 green（已解除）并关闭（含历史遗留的 closed 记录）
                # reviewed / ignored → 尊重教师处理，不改
                if row is not None and row.status in ("open", "read", "closed"):
                    was_open = row.status == "open"
                    row.level = "green"
                    row.status = "closed"
                    row.desc = "作答正确率已回升至达标线以上，预警解除。"
                    row.trigger = TRIGGER
                    row.suggestions_json = "[]"
                    if was_open:
                        closed += 1

    db.commit()
    return {"created": created, "updated": updated, "reopened": reopened, "closed": closed}
