"""学情类只读工具（P1）+ 界面动作建议。

设计原则
--------
- **数据只从服务端注入的身份取**：学生 / 课程都来自 `ctx.user_id` 与
  `ctx.extra['courseId']`，工具签名里**没有** user_id / course_id 参数，
  模型无法指定别人的数据（越权在参数层面就不成立）。
- **数值复用业务函数**：正确率逐题拆解走 `services.scoring.kp_accuracy_detail`
  （与页面、预警同一套口径），工具本身不做统计。
- **只读**：这三个工具都不写库；唯一的"动作"是 `suggest_action`，
  它只把建议塞进 `ctx.turn['actions']`，由前端渲染成按钮、用户点击才生效。
"""
from __future__ import annotations

from app.agent_st.agent.context import ToolContext
from app.agent_st.agent.registry import tool
from app.agent_st import persistence
from app.utils import fmt_dt

# 前端允许的界面白名单（与 assets/js/student/views/chat.js 的 AgentBridge 一致）
_VIEWS = ("dashboard", "graph", "resource", "practice", "mastery", "alerts", "ai")
_MODES = ("weak", "order", "random", "wrong")

# 口径字典：内容取自各接口的真实实现（改口径时这里必须同步改）
_METRICS: dict[str, dict] = {
    "知识点完成率": {
        "formula": "status 为 done 的知识点数 ÷ 课程知识点总数 × 100%",
        "detail": "done 的判定：资源完成率达到 100%，或者该点有答题记录且答题正确率 ≥ 80%。"
                  "所以它是「学完了多少个知识点」，不是「资源看了百分之多少」。",
        "where": "学生端 → 学习驾驶舱 / 我的学情；教师端 → 教学驾驶舱的班级均值",
    },
    "知识点学习完成率": {
        "formula": "对每个知识点取 max(资源完成率, 答题正确率)，再对全部知识点求平均",
        "detail": "它是平均掌握率，不是比率；名字里带「完成」容易误解。",
        "where": "学生端 → 学习驾驶舱（环形图）/ 我的学情",
    },
    "能力目标达成度": {
        "formula": "掌握率 ≥ 60% 的知识点数 ÷ 知识点总数 × 100%",
        "detail": "实际就是达标知识点占比，与「目标图谱」无关（目标图谱尚未实现）。"
                  "页面上曾写「基线 80%」，但代码里的阈值是 60%。",
        "where": "学生端 → 学习驾驶舱（环形图）/ 我的学情",
    },
    "答题正确率": {
        "formula": "Σ(权重 × 该题最近一次是否答对) ÷ Σ(权重) × 100%",
        "detail": "按题去重、每道题只取最近一次作答；主知识点权重 1.0，"
                  "同一道题挂到的其它知识点（kp_ids 标签）各 0.3。"
                  "重做同一道题是替换该题的最近一次，不会累加。",
        "where": "学生端 → 我的学情 / 预警与提醒；教师端 → 学情监测看板",
    },
    "资源完成率": {
        "formula": "该知识点主挂载资源的 progress 平均值",
        "detail": "视频 = 播放位置 ÷ 时长；PPT/PDF = 页码 ÷ 总页数（页码由前端记录/学生填写）。"
                  "进度只增不减，填到最后一页即永久 100%。",
        "where": "学生端 → 学习资源中心 / 我的学情",
    },
    "预警规则": {
        "formula": "同一知识点至少作答 2 道不同题才计入；正确率 < 50% 记红、< 60% 记黄",
        "detail": "正确率回到 ≥ 60% 时预警自动解除；教师点「忽略」的预警不会被自动重新激活。"
                  "标签命中的知识点（自己没有题、只被别的题挂标签）同样会出预警，"
                  "并可以用该知识点的靶向练习消除。",
        "where": "学生端 → 预警与提醒；教师端 → 学情监测看板 → 异常预警列表",
    },
    "学习时长": {
        "formula": "当天练习用时 + 当天视频观看秒数",
        "detail": "PDF/PPT 的阅读时长暂不计入。",
        "where": "学生端 → 学习驾驶舱 → 今日累计学习时长",
    },
}


def _course_id(ctx: ToolContext) -> str:
    return str((ctx.extra or {}).get("courseId") or ctx.store.course_id or "").strip()


@tool(
    name="explain_metric",
    description=(
        "解释本系统某个学情指标的计算口径（完成率 / 掌握率 / 达标率 / 答题正确率 / "
        "资源完成率 / 预警规则 / 学习时长）。用户问「这个百分比怎么算的」「为什么我完成率"
        "是 0 但学情里有数」这类问题时调用，不要自己推测口径。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "metric": {"type": "string",
                       "description": "指标名，例如 知识点完成率 / 能力目标达成度 / 答题正确率 / 预警规则"},
        },
        "required": ["metric"],
    },
    flows=("explain",),
)
def explain_metric(ctx: ToolContext, metric: str = ""):
    key = (metric or "").strip()
    hit = _METRICS.get(key)
    if hit is None:                       # 容错：按关键词挑一个最接近的
        for name in _METRICS:
            if name and name in key:
                key, hit = name, _METRICS[name]
                break
    if hit is None:
        for name in _METRICS:
            if key and (key in name):
                key, hit = name, _METRICS[name]
                break
    if hit is None:
        return {"known": False, "supported": list(_METRICS),
                "hint": "请用上面可用的指标名再问一次"}
    return {"known": True, "metric": key, **hit}


@tool(
    name="my_alerts",
    description=(
        "读取**当前登录用户**在本课程的预警清单（学生看自己的；教师端不适用）。"
        "返回每条预警的等级、知识点、状态、触发说明。"
        "用户问「我有哪些预警」「为什么提示我某某知识点有问题」时调用。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "level": {"type": "string", "enum": ["all", "red", "yellow"],
                      "description": "只看某一等级；默认 all"},
        },
    },
    flows=("explain",),
)
def my_alerts(ctx: ToolContext, level: str = "all"):
    uid, course_id = ctx.user_id, _course_id(ctx)
    if not uid:
        return {"error": "当前会话没有用户身份，无法读取预警"}
    if not course_id:
        return {"error": "当前会话没有课程上下文，无法读取预警"}
    db = persistence.SessionLocal()
    try:
        q = db.query(persistence.Alert).filter(
            persistence.Alert.user_id == uid,
            persistence.Alert.course_id == course_id,
        )
        if (level or "all") != "all":
            q = q.filter(persistence.Alert.level == level)
        rows = q.order_by(persistence.Alert.created_at.desc()).all()
        return {
            "count": len(rows),
            "items": [{
                "alertId": r.alert_id, "level": r.level, "status": r.status,
                "kpId": r.kp_id, "kpName": r.kp_name,
                "desc": r.desc, "createdAt": fmt_dt(r.created_at),
            } for r in rows],
        }
    finally:
        db.close()


@tool(
    name="breakdown",
    description=(
        "把**当前登录用户**在某个知识点上的答题正确率逐题拆开：每道题的权重"
        "（主命中 1.0 / 标签命中 0.3）、最近一次对错、对正确率的贡献。"
        "用于回答「为什么这个知识点正确率是 X%」「正确答案率要练哪几道题」。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "kp_id": {"type": "string", "description": "知识点 id，如 KP018"},
        },
        "required": ["kp_id"],
    },
    flows=("explain",),
)
def breakdown(ctx: ToolContext, kp_id: str = ""):
    from app.services.scoring import kp_accuracy_detail

    uid, course_id = ctx.user_id, _course_id(ctx)
    kp = (kp_id or "").strip()
    if not uid or not course_id:
        return {"error": "缺少用户或课程上下文"}
    if not kp:
        return {"error": "请给出知识点 id（如 KP018）"}
    db = persistence.SessionLocal()
    try:
        node = db.query(persistence.GraphNode).filter(
            persistence.GraphNode.id == kp,
            persistence.GraphNode.graph_type == "knowledge",
            persistence.GraphNode.course_id == course_id,
        ).first()
        if not node:
            return {"error": f"知识点 {kp} 不属于当前课程"}
        detail = kp_accuracy_detail(db, uid, kp)
        detail["kpName"] = node.name
        detail["chapter"] = node.chapter or ""
        detail["isKey"] = bool(node.is_key)
        # 前置/后继（来自知识图谱编排保存的关系）：用于解释"为什么建议先补它"
        detail["relations"] = _relations(db, course_id, kp)
        detail["note"] = ("正确率 = Σ(权重×最近一次是否答对) ÷ Σ(权重)；"
                          "主命中权重 1.0、标签命中 0.3；重做同一道题是替换而不是累加。")
        return detail
    finally:
        db.close()


def _relations(db, course_id: str, kp_id: str) -> dict:
    """某知识点的前置/后继（名字），供"先补哪个"的解释使用。"""
    kd = db.query(persistence.KpDetail).filter(
        persistence.KpDetail.kp_id == kp_id,
        persistence.KpDetail.course_id == course_id,
    ).first()
    import json as _json

    def _names(ids):
        ids = [str(x) for x in (ids or []) if str(x).strip()]
        if not ids:
            return []
        rows = db.query(persistence.GraphNode.id, persistence.GraphNode.name).filter(
            persistence.GraphNode.id.in_(ids),
            persistence.GraphNode.course_id == course_id,
        ).all()
        m = {i: n for i, n in rows}
        return [{"kpId": i, "name": m.get(i, i)} for i in ids]

    if not kd:
        return {"pre": [], "post": []}
    try:
        pre_ids = _json.loads(kd.pre_kp or "[]")
    except Exception:
        pre_ids = []
    try:
        post_ids = _json.loads(kd.post_kp or "[]")
    except Exception:
        post_ids = []
    return {"pre": _names(pre_ids), "post": _names(post_ids)}


@tool(
    name="weak_ranking",
    description=(
        "按**统一口径**列出当前用户在本课程里「最该先补」的知识点排序（含理由），"
        "用于回答「应该先完成哪一个」「先补哪个知识点」。"
        "口径：只统计命中 ≥2 道不同题（与预警门槛一致）且正确率 < 60% 的知识点；"
        "排序 = 正确率升序 → 前置知识点个数多的优先（基础点先补）→ 章节靠前。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "description": "返回前几个，默认 3"},
        },
    },
    flows=("explain",),
)
def weak_ranking(ctx: ToolContext, limit: int = 3):
    from app.services.alert_detector import ENGAGE_MIN
    from app.services.scoring import quiz_accuracy_by_kp

    uid, course_id = ctx.user_id, _course_id(ctx)
    if not uid or not course_id:
        return {"error": "缺少用户或课程上下文"}
    db = persistence.SessionLocal()
    try:
        acc = quiz_accuracy_by_kp(db, uid)
        nodes = db.query(persistence.GraphNode).filter(
            persistence.GraphNode.graph_type == "knowledge",
            persistence.GraphNode.course_id == course_id,
        ).all()
        rows = []
        for node in nodes:
            hit = acc.get(node.id)
            if not hit:
                continue
            rate, hits = hit
            if hits < ENGAGE_MIN or rate >= 60:
                continue
            rel = _relations(db, course_id, node.id)
            rows.append({
                "kpId": node.id, "name": node.name, "chapter": node.chapter or "",
                "rate": rate, "hits": hits, "isKey": bool(node.is_key),
                "pre": [x["name"] for x in rel["pre"]],
                "post": [x["name"] for x in rel["post"]],
            })
        rows.sort(key=lambda r: (r["rate"], -len(r["pre"]), r["chapter"], r["kpId"]))
        top = rows[: max(1, int(limit or 3))]
        for i, r in enumerate(top, 1):
            reasons = [f"正确率仅 {r['rate']}%（{r['hits']} 道题）"]
            if r["pre"]:
                reasons.append(f"且它是「{'、'.join(r['pre'])}」的前置")
            if r["post"]:
                reasons.append(f"补上后能支撑 {len(r['post'])} 个后续知识点")
            r["rank"] = i
            r["reason"] = "；".join(reasons)
        return {
            "totalWeak": len(rows),
            "basis": "命中 ≥2 道不同题且正确率 <60%；按正确率升序、基础点（被更多点依赖）优先",
            "ranking": top,
        }
    finally:
        db.close()


@tool(
    name="suggest_action",
    description=(
        "在回答末尾给用户一个**可点击的界面动作按钮**（不直接执行任何操作）。"
        "当你的结论指向某个页面或某组练习时调用，例如「建议去练某知识点的靶向练习」"
        "「去我的学情看矩阵」。kind=navigate 只是跳页面；kind=practice 会在学生端"
        "预置该知识点的靶向练习并跳到练习页（仍由用户自己点击开始）。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": ["navigate", "practice"]},
            "label": {"type": "string", "description": "按钮文案，例如「去练 KP018 靶向练习」"},
            "view": {"type": "string", "enum": list(_VIEWS),
                     "description": "kind=navigate 时的目标页面"},
            "kp_id": {"type": "string", "description": "kind=practice 时的知识点 id"},
            "mode": {"type": "string", "enum": list(_MODES),
                     "description": "练习模式，默认 weak（靶向练习）"},
        },
        "required": ["kind", "label"],
    },
    flows=("explain",),
)
def suggest_action(ctx: ToolContext, kind: str = "", label: str = "", view: str = "",
                   kp_id: str = "", mode: str = "weak"):
    kind = (kind or "").strip()
    label = (label or "").strip()
    if kind not in ("navigate", "practice"):
        return {"error": "kind 只能是 navigate 或 practice"}
    if not label:
        return {"error": "label 不能为空"}
    action = {"kind": kind, "label": label}
    if kind == "navigate":
        if view not in _VIEWS:
            return {"error": f"view 不在允许范围内：{list(_VIEWS)}"}
        action["view"] = view
    else:
        if not kp_id:
            return {"error": "kind=practice 时必须给出 kp_id"}
        action["kpId"] = kp_id
        action["mode"] = mode if mode in _MODES else "weak"
    ctx.turn.setdefault("actions", []).append(action)
    return {"ok": True, "queued": action,
            "note": "已加入建议动作，前端会在回答下方渲染按钮，用户点击后才生效"}
