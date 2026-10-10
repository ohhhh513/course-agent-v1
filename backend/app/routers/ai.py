"""
AI 智能答疑接口：/ai/*

智能解析（RAG 讲解 Agent，源自 tmp_ST_problem_model 集成）：
    1. /ai/chat        → 聚合完整回答（信封 {code,message,data}）
    2. /ai/chat/stream → SSE 真实流式输出（event: meta/tool_start/tool_end/content/citations/done）
会话历史复用 chat_sessions / chat_messages（flow_id='explain'）。
"""
import json, uuid
from fastapi import APIRouter, Depends, Body, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from ..database import get_db
from ..models.ai import ChatSession, ChatMessage
from ..models.intervention import TeacherClassDashboard
from ..middleware.auth import get_current_user
from ..dependencies import get_current_course_id
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
    # 课程上下文以请求头 X-Course-Id 为准（get_current_course_id 依赖）。
    # 这里的 body 字段仅作无头调用时的兜底，**不再默认演示课 C2026DS001**。
    courseId: str = ""


class FeedbackReq(BaseModel):
    messageId: str
    feedback: int = 1   # 1=点赞 -1=点踩


# ========= 路由实现 =========
@router.get("/sessions")
def ai_sessions(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    course_id: str = Depends(get_current_course_id),
):
    """答疑历史会话 —— 按当前学生和当前课程检索。"""
    rows = db.query(ChatSession).filter(
        ChatSession.user_id == user.user_id,
        ChatSession.course_id == course_id,
    ).order_by(ChatSession.updated_at.desc()).all()
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
    course_id: str = Depends(get_current_course_id),
):
    """删除会话（含全部消息），仅限本人会话"""
    s = db.query(ChatSession).filter(
        ChatSession.session_id == session_id,
        ChatSession.user_id == user.user_id,
        ChatSession.course_id == course_id,
    ).first()
    if not s:
        return fail("会话不存在", 404)
    from ..services.chat_attachments import delete_chat_attachments, session_attachment_ids

    attachment_ids = session_attachment_ids(db, session_id)
    db.query(ChatMessage).filter(ChatMessage.session_id == session_id).delete()
    db.delete(s)
    db.commit()
    delete_chat_attachments(attachment_ids)
    return ok({"sessionId": session_id, "deleted": True})


@router.get("/sessions/{session_id}/messages")
def ai_session_messages(
    session_id: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    course_id: str = Depends(get_current_course_id),
):
    session = db.query(ChatSession).filter(
        ChatSession.session_id == session_id,
        ChatSession.user_id == user.user_id,
        ChatSession.course_id == course_id,
    ).first()
    if not session:
        return fail("会话不存在", 404)
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


@router.get("/sessions/{session_id}/attachments/{attachment_id}")
def ai_session_attachment(
    session_id: str,
    attachment_id: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    course_id: str = Depends(get_current_course_id),
):
    """Return a file only when its reference belongs to the current user's course session."""
    from ..services.chat_attachments import find_session_attachment, resolve_chat_attachment

    session = db.query(ChatSession).filter(
        ChatSession.session_id == session_id,
        ChatSession.user_id == user.user_id,
        ChatSession.course_id == course_id,
    ).first()
    if not session:
        return JSONResponse(status_code=404, content=fail("会话不存在", 404))
    attachment = find_session_attachment(db, session_id, attachment_id)
    path = resolve_chat_attachment(attachment_id) if attachment else None
    if not attachment or not path:
        return JSONResponse(status_code=404, content=fail("附件不存在或已清理", 404))
    return FileResponse(
        path,
        media_type=attachment.get("mimeType") or "application/octet-stream",
        filename=attachment.get("name") or "attachment",
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


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


def _agent_events(req: ChatReq, user, course_id=None, flow_id: str = "explain", extra_context: dict = None):
    """运行 Agent，返回事件 dict 生成器（流式/非流式共用）。

    flow_id 默认 explain（学生/教师答疑）；管理员平台治理流传 admin_ops。
    extra_context 用于把调用方额外上下文（如上传文件抽取出的文本）透传给 run_turn。
    """
    raw_sid = (req.sessionId or '').strip()
    session_id = None if (not raw_sid or raw_sid.lower() == 'new') else raw_sid
    # 请求头（经成员校验）优先；无头调用才回退 body，body 也不再默认演示课
    resolved = (course_id or req.courseId or "").strip()
    context = {}
    if resolved:
        context["courseId"] = resolved
    if req.kpId:
        context["kpId"] = req.kpId
    # 服务端注入调用者角色：任务流级校验 + 工具清单过滤都靠它（模型无法指定）。
    context["role"] = (getattr(user, "role", "") or "").strip()
    # 调用方额外上下文（如附件）：合并进 context，run_turn 会据此注入本轮 prompt
    if extra_context:
        context.update(extra_context)
    return run_turn(
        message=req.question,
        flow_id=flow_id,
        session_id=session_id,
        context=context,
        user_id=user.user_id,
        course_id=resolved,
    )


@router.post("/chat")
def ai_chat(
    req: ChatReq,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    course_id: str = Depends(get_current_course_id),
):
    """AI 智能答疑（非流式聚合版）：内部复用 explain 流 Agent，落库由 AgentStore 完成"""
    content_parts: list[str] = []
    citations: list = []
    session_id = ""
    out_of_scope = False
    demo = False
    actions: list = []
    for ev in _agent_events(req, user, course_id):
        etype = ev.get("type")
        if etype == "session":
            session_id = ev.get("session_id") or ""
        elif etype == "text":
            content_parts.append(ev.get("delta") or "")
        elif etype == "citations":
            citations = ev.get("items") or []
        elif etype == "action":
            actions = ev.get("actions") or []
        elif etype == "done":
            demo = bool(ev.get("demo"))
            out_of_scope = bool(ev.get("out_of_scope"))
    result = {
        "messageId": "MSG" + uuid.uuid4().hex[:12],
        "method": req.method,
        "content": "".join(content_parts),
        "citations": citations,
        "outOfScope": out_of_scope,
        "sourceCount": len(citations),
        "demo": demo,
        "sessionId": session_id,
        "actions": actions,
    }
    return ok(result)


def agent_sse_events(req: ChatReq, user, course_id: str = "", flow_id: str = "explain", extra_context: dict = None):
    """SSE 事件流生成器（meta → tool_start/tool_end → content(逐 token) → citations → done）。

    `/ai/chat/stream` 与 `/admin/agent/chat/stream` 共用：**事件名与字段完全一致**
    （交接文档第 3 节事件契约），前端只认这一套。
    extra_context 透传给 run_turn（如上传文件抽取出的文本）。
    """
    def gen():  # 同步生成器：sse_starlette 会放入线程池迭代，避免阻塞事件循环
        session_id = ""
        for ev in _agent_events(req, user, course_id, flow_id=flow_id, extra_context=extra_context):
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
                yield {"event": "citations", "data": json.dumps({"items": items}, ensure_ascii=False)}
            elif etype == "action":
                # 工具建议的界面动作（suggest_action）→ 前端渲染成按钮，用户点击才生效
                yield {"event": "action", "data": json.dumps(
                    {"actions": ev.get("actions") or []}, ensure_ascii=False)}
            elif etype == "error":
                yield {"event": "error", "data": json.dumps({"message": ev.get("message")}, ensure_ascii=False)}
            elif etype == "done":
                done_payload = {"outOfScope": bool(ev.get("out_of_scope")), "demo": bool(ev.get("demo")),
                                "stopped": bool(ev.get("stopped")),
                                "drafts": ev.get("drafts") or []}
                yield {"event": "done", "data": json.dumps(done_payload, ensure_ascii=False)}

    return gen()


@router.post("/chat/stream")
async def ai_chat_stream(
    request: Request,
    user=Depends(get_current_user),
    course_id: str = Depends(get_current_course_id),
):
    """SSE 真实流式答疑：meta → tool_start/tool_end → content(逐 token) → citations → done

    两种请求体（与 `/admin/agent/chat/stream` 同一约定）：
    - **JSON** `{sessionId?, question, courseId?, kpId?}`（无附件时的原样兼容路径）；
    - **multipart** `{sessionId?, question, files[]}`：附件抽取纯文本**附到本轮问题**
      （语义、上限与管理员端一致，见 `services/attachments.py`）；不落库正文、不进知识库。
    """
    from sse_starlette.sse import EventSourceResponse

    from ..services.attachments import AttachmentError, collect_attachments

    ct = (request.headers.get("content-type") or "").lower()
    extra: dict | None = None

    if ct.startswith("multipart/form-data"):
        try:
            form = await request.form()
        except Exception as exc:  # noqa: BLE001
            return JSONResponse(status_code=400, content=fail(f"表单解析失败：{exc}"))
        question = str(form.get("question") or "").strip()
        session_id = (str(form.get("sessionId") or "").strip() or None)
        if not question:
            return JSONResponse(status_code=400, content=fail("请输入问题内容后再发送"))
        raw_files = [f for f in form.getlist("files") if getattr(f, "filename", None)]
        try:
            attachments, raw_uploads = await collect_attachments(raw_files)
        except AttachmentError as exc:
            return JSONResponse(status_code=400, content=fail(str(exc)))
        from ..services.chat_attachments import ChatAttachmentStorageError, persist_chat_uploads
        try:
            persist_chat_uploads(raw_uploads, attachments)
        except ChatAttachmentStorageError:
            return JSONResponse(status_code=500, content=fail("附件保存失败，请重新上传"))
        req = ChatReq(sessionId=session_id, question=question)
        if attachments:
            extra = {"attachments": attachments}
    else:
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            return JSONResponse(status_code=400, content=fail("请求体不是合法 JSON"))
        if not isinstance(body, dict):
            return JSONResponse(status_code=400, content=fail("请求体必须是 JSON 对象"))
        question = str(body.get("question") or "").strip()
        if not question:
            return JSONResponse(status_code=400, content=fail("请输入问题内容"))
        req = ChatReq(
            sessionId=(str(body.get("sessionId") or "").strip() or None),
            question=question,
            method=str(body.get("method") or "guided"),
            kpId=body.get("kpId"),
            courseId=str(body.get("courseId") or ""),
        )

    return EventSourceResponse(agent_sse_events(req, user, course_id, extra_context=extra))


class StopReq(BaseModel):
    sessionId: Optional[str] = None


@router.post("/chat/stop")
def ai_chat_stop(
    req: StopReq = Body(default=StopReq()),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    course_id: str = Depends(get_current_course_id),
):
    """停止当前会话正在进行的生成（协作式「停止思考」）。

    只置一个内存标记：本轮生成在下一个检查点收尾，并把**已经生成的部分**作为回答落库
    （刷新后看到的是被停止的那一版，而不是完整版）。会话归属校验：非本人 / 非当前课程 404。
    """
    from ..agent_st.agent import cancel

    sid = (req.sessionId or "").strip()
    if not sid or sid.lower() == "new":
        return ok({"stopped": False})
    s = db.query(ChatSession).filter(
        ChatSession.session_id == sid,
        ChatSession.user_id == user.user_id,
        ChatSession.course_id == course_id,
    ).first()
    if not s:
        return fail("会话不存在", 404)
    cancel.request(sid)
    return ok({"stopped": True, "sessionId": sid})


@router.post("/feedback")
def ai_feedback(
    req: FeedbackReq,
    user=Depends(get_current_user),
):
    """点赞/点踩反馈，用于知识库迭代 —— TODO"""
    return ok({"accepted": True})
