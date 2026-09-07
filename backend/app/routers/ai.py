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

from ..database import get_db
from ..models.ai import ChatSession, ChatMessage
from ..models.intervention import TeacherClassDashboard
from ..middleware.auth import get_current_user
from ..schemas.common import ok, fail
from ..utils import loads, fmt_dt
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
@router.get("/sessions")
def ai_sessions(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    rows = db.query(ChatSession).filter(ChatSession.user_id == user.user_id).order_by(ChatSession.updated_at.desc()).all()
    items = [
        {
            "sessionId": s.session_id, "title": s.title,
            "time": fmt_dt(s.updated_at, "%m-%d %H:%M"),
            "rounds": s.rounds, "kp": s.kp_name,
        }
        for s in rows
    ]
    # 不再兜底返回他人的 chat_history —— 新用户无会话则返回空
    return ok({"total": len(items), "list": items})


@router.delete("/sessions/{session_id}")
def ai_delete_session(
    session_id: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """删除会话（含全部消息），仅限本人会话"""
    s = db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
    if not s:
        return fail("会话不存在", 404)
    if s.user_id and s.user_id != user.user_id:
        return fail("无权删除他人的会话", 403)
    db.query(ChatMessage).filter(ChatMessage.session_id == session_id).delete()
    db.delete(s)
    db.commit()
    return ok({"sessionId": session_id, "deleted": True})


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
            elif etype == "think":
                # 模型内部推理（reasoning_content）→ 前端折叠面板实时展示
                yield {"event": "think", "data": json.dumps(
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

    return EventSourceResponse(gen())


@router.post("/feedback")
def ai_feedback(
    req: FeedbackReq,
    user=Depends(get_current_user),
):
    """点赞/点踩反馈，用于知识库迭代 —— TODO"""
    return ok({"accepted": True})
