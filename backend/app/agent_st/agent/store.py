from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from app.agent_st.agent.config import get_settings
from app.agent_st.rag.validate import next_question_id, validate_question
from app.utils import fmt_dt


class AgentStore:
    """原型 AgentStore 的正式版适配器。

    会话/消息写入正式系统的 chat_sessions / chat_messages（复用 D2 决策，
    前端历史会话 UI 零改动）；出题草稿写入 st_question_drafts（按 user_id
    归属个人，绝不写入 questions 正式题库）。不再使用独立 agent.db。
    """

    def __init__(self, user_id: str = ""):
        from .. import persistence

        self.persistence = persistence
        self.user_id = user_id or ""
        settings = get_settings()
        self.drafts_dir: Path = settings.drafts_dir
        self.drafts_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # 会话（chat_sessions / chat_messages）
    # ------------------------------------------------------------------
    def ensure_session(self, session_id: str | None, flow_id: str) -> str:
        db = self.persistence.SessionLocal()
        try:
            ChatSession, ChatMessage = self.persistence.ChatSession, self.persistence.ChatMessage
            sid = session_id
            if sid:
                row = db.query(ChatSession).filter(ChatSession.session_id == sid).first()
                if row:
                    # 属主校验：他人会话一律另开新会话，避免跨用户串写
                    if self.user_id and row.user_id and row.user_id != self.user_id:
                        sid = None
                    else:
                        return sid
            sid = sid or f"CH{uuid.uuid4().hex[:10].upper()}"
            db.add(ChatSession(
                session_id=sid, user_id=self.user_id or None,
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
    # 出题草稿（st_question_drafts，按用户隔离）
    # ------------------------------------------------------------------
    def save_draft(self, payload: dict, batch_id: str = "") -> dict:
        check = validate_question(payload, used_ids=existing_draft_and_bank_ids(self))
        draft_id = f"QD{uuid.uuid4().hex[:10].upper()}"
        status = "draft" if check["ok"] else "invalid"
        db = self.persistence.SessionLocal()
        try:
            STQuestionDraft = self.persistence.STQuestionDraft
            db.add(STQuestionDraft(
                draft_id=draft_id,
                user_id=self.user_id or None,
                batch_id=batch_id,
                payload_json=json.dumps(payload, ensure_ascii=False),
                status=status,
                errors_json=json.dumps(check["errors"], ensure_ascii=False),
            ))
            db.commit()
        finally:
            db.close()
        self._write_sidecar(draft_id, payload)
        return {"draft_id": draft_id, "status": status, "errors": check["errors"], "id": payload.get("id")}

    def list_drafts(self, limit: int = 50, user_id: str | None = None) -> list[dict]:
        db = self.persistence.SessionLocal()
        try:
            STQuestionDraft = self.persistence.STQuestionDraft
            q = db.query(STQuestionDraft)
            if user_id:
                q = q.filter(STQuestionDraft.user_id == user_id)
            rows = q.order_by(STQuestionDraft.created_at.desc()).limit(limit).all()
            out = []
            for row in rows:
                payload = json.loads(row.payload_json or "{}")
                out.append({
                    "draft_id": row.draft_id,
                    "status": row.status,
                    "created_at": fmt_dt(row.created_at, "%Y-%m-%d %H:%M:%S"),
                    "errors": json.loads(row.errors_json or "[]"),
                    "id": payload.get("id"),
                    "chapter": payload.get("chapter"),
                    "question": payload.get("question"),
                    "payload": payload,
                })
            return out
        finally:
            db.close()

    def draft_ids(self) -> set[int]:
        db = self.persistence.SessionLocal()
        try:
            STQuestionDraft = self.persistence.STQuestionDraft
            rows = db.query(STQuestionDraft.payload_json).all()
        finally:
            db.close()
        ids: set[int] = set()
        for (payload_json,) in rows:
            try:
                pid = int(json.loads(payload_json or "{}").get("id"))
                ids.add(pid)
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
        return ids

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

    def _write_sidecar(self, draft_id: str, payload: dict) -> None:
        """调试用 sidecar JSON（与库内记录同 id，可随时清空目录）"""
        try:
            path = self.drafts_dir / f"{draft_id}.json"
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:  # noqa: BLE001  sidecar 失败不影响主流程
            pass


def existing_draft_and_bank_ids(store: AgentStore | None = None) -> set[int]:
    from app.agent_st.rag.bank import existing_ids

    store = store or AgentStore()
    return existing_ids() | store.draft_ids()


def allocate_question_id(store: AgentStore | None = None) -> int:
    return next_question_id(existing_draft_and_bank_ids(store))
