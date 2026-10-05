"""学生学情指标（统一口径）。

quiz_accuracy_by_kp：每个知识点的「答题正确率」—— 按题去重，每道题只取最近一次作答。

一道题可能挂多个知识点（`questions.kp_id` 是主 KP，`questions.kp_ids` 是完整标签列表），
做错这道题意味着**它对所有挂载的知识点都负一份责任**，所以正确率按权重累加：

    主 KP 权重 = 1.0；其它标签 KP 权重 = SECONDARY_KP_WEIGHT（默认 0.3）
    正确率(KP) = Σ(权重 × 该题最近一次是否答对) / Σ(权重)

而"做过几道题"（返回值第二个元素，供预警门槛 ENGAGE_MIN 判定）**包含次要命中**：
一道题只要挂了这个知识点（主或次），就为该点计 1 道题 —— 这样"顺带考到的子知识点"
既会拉低它的正确率，也能让它进入预警判定，不会出现"薄弱点看得见、预警判不到"的口径分裂。
（权重只影响正确率数值大小：主命中证据更重，次要命中证据更轻。）

传 secondary_weight=0.0 只把**正确率**退回"只算主 KP"的旧口径（便于对账/回退）；
「不同题数」与权重无关（它记录的是"这道题考到了该点"这一事实），始终包含次要命中。
返回 {kp_id: (加权正确率%, 含次要命中的不同题数)}。掌握率 / 预警 / 靶向薄弱点都基于它。
"""
import json
from collections import defaultdict

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models.practice import AnswerRecord

# 次要知识点权重（主 KP 固定 1.0）：一道题挂在别的知识点标签上时，对该点正确率的贡献。
# 0.3 = 影响温和：既承认"这道题确实考到了这个子知识点"，又不让次要命中盖过主命中的证据。
SECONDARY_KP_WEIGHT = 0.3


def _kp_tags(raw) -> list[str]:
    """questions.kp_ids（JSON 数组字符串）→ 标签列表。"""
    try:
        data = json.loads(raw or "[]")
    except (TypeError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return [str(x).strip() for x in data if str(x or "").strip()]


def quiz_accuracy_by_kp(
    db: Session,
    user_id: str,
    secondary_weight: float = SECONDARY_KP_WEIGHT,
    course_id: str | None = None,
) -> dict:
    """每知识点：(加权答题正确率%, 含次要命中的不同题数)。按题去重、取最近一次作答。

    course_id 给定时**只统计该课程下的作答记录**（默认 None = 保持历史口径：该生全部课程）。
    传了它就不再依赖「KP id 全局唯一」来间接隔离课程（清单 P43）。
    """
    from ..models.question import Question

    # 每题只取最近一次作答（按 q_id 去重，不按 kp 分组：题目归属后来被改过时也不会重复计数）
    latest_q = db.query(
        func.max(AnswerRecord.id).label("last_id"),
    ).filter(
        AnswerRecord.user_id == user_id,
        AnswerRecord.kp_id.isnot(None),
    )
    if course_id:
        latest_q = latest_q.filter(AnswerRecord.course_id == course_id)
    latest = latest_q.group_by(AnswerRecord.q_id).subquery()
    rows = db.query(
        AnswerRecord.q_id, AnswerRecord.kp_id, AnswerRecord.is_correct,
    ).join(latest, AnswerRecord.id == latest.c.last_id).all()
    if not rows:
        return {}

    # 题目当前的标签（主 KP + kp_ids）；题目已被删除时退回答题记录里的 kp_id
    qids = [r[0] for r in rows if r[0]]
    primary_map: dict[str, str] = {}
    tags_map: dict[str, list[str]] = {}
    if qids:
        for qid, kp_id, kp_ids in db.query(
                Question.q_id, Question.kp_id, Question.kp_ids).filter(
                Question.q_id.in_(qids)).all():
            primary_map[qid] = (kp_id or "").strip()
            tags_map[qid] = _kp_tags(kp_ids)

    num: dict[str, float] = defaultdict(float)   # 加权答对数
    den: dict[str, float] = defaultdict(float)   # 加权作答数
    hits: dict[str, int] = defaultdict(int)      # 该点上的不同题数（主命中 ∪ 次要命中）
    for qid, rec_kp, ok in rows:
        primary = primary_map.get(qid) or (rec_kp or "").strip()
        if not primary:
            continue
        related = [primary]
        for tag in tags_map.get(qid, []):
            if tag and tag != primary and tag not in related:
                related.append(tag)
        for kp in related:
            w = 1.0 if kp == primary else float(secondary_weight)
            hits[kp] += 1                 # 只要挂了这个点就算"做过 1 道题"
            if w <= 0:
                continue                  # secondary_weight=0 → 退回只算主 KP
            den[kp] += w
            if ok:
                num[kp] += w

    out = {}
    for kp, total_w in den.items():
        if total_w:
            out[kp] = (round(num[kp] / total_w * 100, 1), hits.get(kp, 0))
    return out


def weak_kp_ids(
    db: Session,
    user_id: str,
    course_id: str | None,
    candidates,
    limit: int | None = None,
) -> list[str]:
    """从 candidates 里挑出「薄弱知识点」，按「有未处理预警优先 → 正确率升序」排序。

    门槛与预警完全一致（同一组常量 `ENGAGE_MIN` / `YELLOW_BELOW`）：某知识点上做过
    ≥ ENGAGE_MIN 道不同题、且加权正确率 < YELLOW_BELOW，才算薄弱点。

    有未处理红/黄预警的点**优先占位**：否则会出现「预警页提示某知识点有问题、
    薄弱点清单里却找不到它」的两套说法（清单 P47）。学习驾驶舱与「薄弱点强化」
    卡片题量都走这一个入口，保证两边口径不再漂移。
    """
    from .alert_detector import ALERT_TYPE, ENGAGE_MIN, YELLOW_BELOW
    from ..models.alert import Alert

    acc = quiz_accuracy_by_kp(db, user_id, course_id=course_id)
    aq = db.query(Alert.kp_id).filter(
        Alert.user_id == user_id,
        Alert.type == ALERT_TYPE,
        Alert.level.in_(("red", "yellow")),
        Alert.status.notin_(("closed", "ignored")),
    )
    if course_id:
        aq = aq.filter(Alert.course_id == course_id)
    alert_kps = {kp for (kp,) in aq.all() if kp}

    rows = []
    for kp in candidates:
        q = acc.get(kp)
        if q and q[1] >= ENGAGE_MIN and q[0] < YELLOW_BELOW:
            rows.append((0 if kp in alert_kps else 1, q[0], kp))
    rows.sort()
    ids = [kp for _urgent, _rate, kp in rows]
    return ids[:limit] if limit else ids
