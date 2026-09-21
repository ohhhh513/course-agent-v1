from __future__ import annotations

import json
import time
import uuid

from app.agent_st.rag.bank import existing_q_ids
from app.agent_st.rag.validate import validate_question
from app.utils import fmt_dt


class AgentStore:
    """原型 AgentStore 的正式版适配器。

    会话/消息写入正式系统的 chat_sessions / chat_messages（复用 D2 决策，
    前端历史会话 UI 零改动）；出题草稿写入 st_question_drafts（按 user_id
    归属个人 + 按 course_id 归属课程，绝不写入 questions 正式题库）。
    不再使用独立 agent.db。

    草稿**只落库**，不再写本地 JSON 副本（原 sidecar 的落盘路径与库解耦，
    测试时会把临时库的草稿泄漏到真实工作区、留下孤儿文件，已整体移除）。

    course_id 是本 store 的隔离边界：会话与草稿都要带上它，
    否则多课程下会串数据、且按课程过滤的列表查询看不到自己刚写的数据。
    """

    def __init__(self, user_id: str = "", course_id: str = ""):
        from .. import persistence

        self.persistence = persistence
        self.user_id = user_id or ""
        self.course_id = course_id or ""

    # ------------------------------------------------------------------
    # 会话（chat_sessions / chat_messages）
    # ------------------------------------------------------------------
    def ensure_session(self, session_id: str | None, flow_id: str) -> str:
        db = self.persistence.SessionLocal()
        try:
            ChatSession = self.persistence.ChatSession
            sid = session_id
            if sid:
                row = db.query(ChatSession).filter(ChatSession.session_id == sid).first()
                if row:
                    # 属主校验：他人会话一律另开新会话，避免跨用户串写
                    if self.user_id and row.user_id and row.user_id != self.user_id:
                        sid = None
                    # 课程校验：跨课程复用会话等于把两门课的对话串在一起
                    elif self.course_id and row.course_id and row.course_id != self.course_id:
                        sid = None
                    else:
                        return sid
            sid = sid or f"CH{uuid.uuid4().hex[:10].upper()}"
            db.add(ChatSession(
                session_id=sid, user_id=self.user_id or None,
                course_id=self.course_id or None,
                title="", flow_id=flow_id, rounds=0,
            ))
            db.commit()
            return sid
        finally:
            db.close()

    def add_message(self, session_id: str, role: str, content: str) -> None:
        db = self.persistence.SessionLocal()
        try:
            ChatSession, ChatMessage = self.persistence.ChatSession, self.persistence.ChatMessage
            # 原型角色 user/assistant → 正式 me/ai
            formal_role = {"user": "me", "assistant": "ai"}.get(role, role)
            db.add(ChatMessage(
                session_id=session_id,
                role=formal_role,
                content=content,
                time_str=time.strftime("%H:%M"),
            ))
            session = db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
            if session:
                if formal_role == "me" and not session.title:
                    session.title = (content or "新会话")[:50]
                session.rounds = (session.rounds or 0) + (1 if formal_role == "ai" else 0)
            db.commit()
        finally:
            db.close()

    def history(self, session_id: str, limit: int = 12) -> list[dict]:
        db = self.persistence.SessionLocal()
        try:
            ChatMessage = self.persistence.ChatMessage
            rows = (
                db.query(ChatMessage)
                .filter(
                    ChatMessage.session_id == session_id,
                    ChatMessage.role.in_(["me", "ai"]),
                )
                .order_by(ChatMessage.id.desc())
                .limit(limit)
                .all()
            )
            rows = list(reversed(rows))
            # 正式 me/ai → 原型 user/assistant
            return [{"role": {"me": "user", "ai": "assistant"}.get(r.role, r.role),
                     "content": r.content} for r in rows]
        finally:
            db.close()

    # ------------------------------------------------------------------
    # 出题草稿（st_question_drafts，按 user_id + course_id 隔离）
    # ------------------------------------------------------------------
    def save_draft(self, payload: dict, batch_id: str = "") -> dict:
        check = validate_question(
            payload, course_id=self.course_id, used_q_ids=self.reserved_q_ids()
        )
        draft_id = f"QD{uuid.uuid4().hex[:10].upper()}"
        status = "draft" if check["ok"] else "invalid"
        db = self.persistence.SessionLocal()
        try:
            STQuestionDraft = self.persistence.STQuestionDraft
            db.add(STQuestionDraft(
                draft_id=draft_id,
                user_id=self.user_id or None,
                course_id=self.course_id or None,
                batch_id=batch_id,
                payload_json=json.dumps(payload, ensure_ascii=False),
                status=status,
                errors_json=json.dumps(check["errors"], ensure_ascii=False),
            ))
            db.commit()
        finally:
            db.close()
        return {"draft_id": draft_id, "status": status, "errors": check["errors"],
                "q_id": payload.get("q_id")}

    def list_drafts(
        self, limit: int = 50, user_id: str | None = None, course_id: str | None = None
    ) -> list[dict]:
        db = self.persistence.SessionLocal()
        try:
            STQuestionDraft = self.persistence.STQuestionDraft
            q = db.query(STQuestionDraft)
            if user_id:
                q = q.filter(STQuestionDraft.user_id == user_id)
            if course_id:
                q = q.filter(STQuestionDraft.course_id == course_id)
            rows = q.order_by(STQuestionDraft.created_at.desc()).limit(limit).all()
            out = []
            for row in rows:
                payload = json.loads(row.payload_json or "{}")
                out.append({
                    "draft_id": row.draft_id,
                    "status": row.status,
                    "created_at": fmt_dt(row.created_at, "%Y-%m-%d %H:%M:%S"),
                    "errors": json.loads(row.errors_json or "[]"),
                    "q_id": payload.get("q_id"),
                    "chapter_id": payload.get("chapter_id"),
                    "kp_id": payload.get("kp_id"),
                    "question": payload.get("question"),
                    "payload": payload,
                })
            return out
        finally:
            db.close()

    def draft_q_ids(self) -> set[str]:
        """本课程已有草稿占用的题号集合（防止同一课程内重复分配 AI 号）"""
        if not self.course_id:
            return set()
        db = self.persistence.SessionLocal()
        try:
            STQuestionDraft = self.persistence.STQuestionDraft
            rows = (
                db.query(STQuestionDraft.payload_json)
                .filter(STQuestionDraft.course_id == self.course_id)
                .all()
            )
        finally:
            db.close()
        ids: set[str] = set()
        for (payload_json,) in rows:
            try:
                qid = str(json.loads(payload_json or "{}").get("q_id") or "").strip()
            except json.JSONDecodeError:
                continue
            if qid:
                ids.add(qid)
        return ids

    def reserved_q_ids(self) -> set[str]:
        """本课程已被占用的题号 = 正式题库已发布题号 ∪ 本课程草稿题号。"""
        if not self.course_id:
            return set()
        return existing_q_ids(self.course_id) | self.draft_q_ids()

    def set_last_tool_log(self, session_id: str, tool_log: list, draft_id: str = "") -> None:
        """把本轮工具调用日志回填到最后一条 AI 消息（供历史会话展示溯源过程）"""
        db = self.persistence.SessionLocal()
        try:
            ChatMessage = self.persistence.ChatMessage
            row = (
                db.query(ChatMessage)
                .filter(ChatMessage.session_id == session_id, ChatMessage.role == "ai")
                .order_by(ChatMessage.id.desc())
                .first()
            )
            if row:
                row.tool_log = json.dumps(tool_log, ensure_ascii=False)
                if draft_id:
                    row.draft_id = draft_id
                db.commit()
        finally:
            db.close()
