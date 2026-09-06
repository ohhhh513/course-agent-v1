"""
AI 智能答疑接口：/ai/*

智能解析（RAG 讲解 Agent，源自 tmp_ST_problem_model 集成）：
    1. /ai/chat        → 聚合完整回答（信封 {code,message,data}）
    2. /ai/chat/stream → SSE 真实流式输出（event: meta/tool_start/tool_end/content/citations/done）
会话历史复用 chat_sessions / chat_messages（flow_id='explain'）。
"""
import json, uuid
from fastapi import APIRouter, Depends, Body, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from ..database import get_db, SessionLocal
from ..models.ai import ChatSession, ChatMessage
from ..models.intervention import TeacherClassDashboard
from ..middleware.auth import get_current_user
from ..schemas.common import ok
from ..utils import loads
from ..agent_st.agent.runtime import run_turn
from ..agent_st.persistence import ChatMessage as STChatMessage

router = APIRouter(prefix="/api/v1/ai", tags=["AI 智能答疑"])


class ChatReq(BaseModel):
    sessionId: Optional[str] = None
    question: str
    method: str = "guided"
    kpId: Optional[str] = None
    courseId: str = "C2026DS001"


class FeedbackReq(BaseModel):
    messageId: str
    feedback: int = 1   # 1=点赞 -1=点踩


# ========= 路由实现 =========
@router.get("/methods")
def ai_methods(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    return ok([
        {"key": "lecture", "name": "讲授法", "desc": "系统讲解概念与原理，结构清晰", "icon": "book"},
        {"key": "guided", "name": "引导式", "desc": "不直接给答案，层层提问引导思考", "icon": "compass"},
        {"key": "case", "name": "案例式", "desc": "结合实际工程案例说明", "icon": "briefcase"},
        {"key": "heuristic", "name": "启发式", "desc": "从反例与矛盾中启发理解", "icon": "bulb"},
        {"key": "fun", "name": "趣味式", "desc": "类比与故事化表达，降低认知门槛", "icon": "smile"},
    ])


@router.get("/sessions")
def ai_sessions(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    rows = db.query(ChatSession).filter(ChatSession.user_id == user.user_id).order_by(ChatSession.updated_at.desc()).all()
    items = [
        {
            "sessionId": s.session_id, "title": s.title,
            "time": s.updated_at.strftime("%m-%d %H:%M") if s.updated_at else "",
            "rounds": s.rounds, "kp": s.kp_name,
        }
        for s in rows
    ]
    # 不再兜底返回他人的 chat_history —— 新用户无会话则返回空
    return ok({"total": len(items), "list": items})


@router.get("/sessions/{session_id}/messages")
def ai_session_messages(
    session_id: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    rows = db.query(ChatMessage).filter(ChatMessage.session_id == session_id).order_by(ChatMessage.id.asc()).all()
    if not rows:
        # 不再兜底返回他人的 chat_messages —— 新会话无消息则返回空
        return ok([])
    items = [
        {
            "role": m.role, "method": m.method, "content": m.content,
            "time": m.time_str, "citations": loads(m.citations) or [],
            "toolLog": loads(getattr(m, "tool_log", None)) or [],
        }
        for m in rows
    ]
    return ok(items)


@router.get("/suggest-questions")
def suggest_questions(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """推荐提问方向 —— 不再硬编码，返回空列表让前端展示默认提示"""
    row = db.query(TeacherClassDashboard).filter(TeacherClassDashboard.data_type == "suggested_questions").first()
    if row:
        return ok(loads(row.data_json))
    return ok([])


def _agent_events(req: ChatReq, user):
    """运行 explain 流 Agent，返回事件 dict 生成器（流式/非流式共用）"""
    raw_sid = (req.sessionId or '').strip()
    session_id = None if (not raw_sid or raw_sid.lower() == 'new') else raw_sid
    context = {"courseId": req.courseId}
    if req.kpId:
        context["kpId"] = req.kpId
    return run_turn(
        message=req.question,
        flow_id="explain",
        session_id=session_id,
        context=context,
        user_id=user.user_id,
    )


def _set_ai_method(session_id: str, method: str) -> None:
    """把教学法标记到最后一条 AI 消息（展示用，非关键路径）"""
    db = SessionLocal()
    try:
        row = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == session_id, ChatMessage.role == "ai")
            .order_by(ChatMessage.id.desc())
            .first()
        )
        if row:
            row.method = method
            db.commit()
    finally:
        db.close()


@router.post("/chat")
def ai_chat(
    req: ChatReq,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """AI 智能答疑（非流式聚合版）：内部复用 explain 流 Agent，落库由 AgentStore 完成"""
    content_parts: list[str] = []
    citations: list = []
    session_id = ""
    out_of_scope = True
    demo = False
    for ev in _agent_events(req, user):
        etype = ev.get("type")
        if etype == "session":
            session_id = ev.get("session_id") or ""
        elif etype == "text":
            content_parts.append(ev.get("delta") or "")
        elif etype == "citations":
            citations = ev.get("items") or []
        elif etype == "done":
            demo = bool(ev.get("demo"))
    out_of_scope = not citations
    _set_ai_method(session_id, req.method)
    result = {
        "messageId": "MSG" + uuid.uuid4().hex[:12],
        "method": req.method,
        "content": "".join(content_parts),
        "citations": citations,
        "outOfScope": out_of_scope,
        "sourceCount": len(citations),
        "demo": demo,
        "sessionId": session_id,
    }
    return ok(result)


@router.post("/chat/stream")
async def ai_chat_stream(
    req: ChatReq,
    user=Depends(get_current_user),
):
    """SSE 真实流式答疑：meta → tool_start/tool_end → content(逐 token) → citations → done"""
    from sse_starlette.sse import EventSourceResponse

    def gen():  # 同步生成器：sse_starlette 会放入线程池迭代，避免阻塞事件循环
        session_id = ""
        out_of_scope = True
        for ev in _agent_events(req, user):
            etype = ev.get("type")
            if etype == "session":
                session_id = ev.get("session_id") or ""
                yield {"event": "meta", "data": json.dumps({
                    "sessionId": session_id,
                    "messageId": "MSG" + uuid.uuid4().hex[:12],
                    "flowId": ev.get("flow_id") or "explain",
                    "citations": [],
                }, ensure_ascii=False)}
            elif etype == "text":
                # content 事件统一 JSON 编码（delta 中可能含换行/markdown 符号，裸文本会破坏 SSE 解析）
                yield {"event": "content", "data": json.dumps(
                    {"delta": ev.get("delta") or ""}, ensure_ascii=False)}
            elif etype in ("tool_start", "tool_end", "draft"):
                yield {"event": etype, "data": json.dumps(ev, ensure_ascii=False)}
            elif etype == "citations":
                items = ev.get("items") or []
                out_of_scope = not items
                yield {"event": "citations", "data": json.dumps({"items": items}, ensure_ascii=False)}
            elif etype == "error":
                yield {"event": "error", "data": json.dumps({"message": ev.get("message")}, ensure_ascii=False)}
            elif etype == "done":
                done_payload = {"outOfScope": out_of_scope, "demo": bool(ev.get("demo")),
                                "drafts": ev.get("drafts") or []}
                yield {"event": "done", "data": json.dumps(done_payload, ensure_ascii=False)}
        _set_ai_method(session_id, req.method)

    return EventSourceResponse(gen())


@router.post("/feedback")
def ai_feedback(
    req: FeedbackReq,
    user=Depends(get_current_user),
):
    """点赞/点踩反馈，用于知识库迭代 —— TODO"""
    return ok({"accepted": True})
