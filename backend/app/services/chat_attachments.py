"""Persistent storage for files attached to agent chat messages.

File bytes live under AGENT_DATA_DIR; chat_messages.tool_log stores only a
random attachment id and display metadata. Access control is enforced by the
session-scoped router endpoints before a stored file is returned.
"""
from __future__ import annotations

import json
import mimetypes
import re
import uuid
from pathlib import Path

from app.config import settings
from app.models.ai import ChatMessage, ChatSession


_ATTACHMENT_ID_RE = re.compile(r"^[0-9a-f]{32}$")


class ChatAttachmentStorageError(OSError):
    """Raised when an uploaded chat attachment cannot be stored safely."""


def _storage_root() -> Path:
    return Path(settings.AGENT_DATA_DIR) / "uploads" / "chat_attachments"


def _path_for_id(attachment_id: str) -> Path | None:
    if not isinstance(attachment_id, str) or not _ATTACHMENT_ID_RE.fullmatch(attachment_id):
        return None
    return _storage_root() / attachment_id[:2] / attachment_id[2:]


def _display_name(name: str) -> str:
    # Upload names are metadata only; never use them as filesystem path parts.
    basename = str(name or "attachment").replace("\\", "/").split("/")[-1] or "attachment"
    cleaned = "".join(char for char in basename if ord(char) >= 32 and ord(char) != 127)
    return (cleaned or "attachment")[:255]


def persist_chat_uploads(raw_uploads: list[tuple[str, bytes]], attachments: list[dict]) -> None:
    """Write each accepted upload and attach its opaque reference to its request data."""
    if len(raw_uploads) != len(attachments):
        raise ChatAttachmentStorageError("uploaded attachment metadata does not match file data")

    created: list[Path] = []
    try:
        for attachment, (uploaded_name, data) in zip(attachments, raw_uploads):
            if not isinstance(data, bytes):
                data = bytes(data)
            attachment_id = uuid.uuid4().hex
            path = _path_for_id(attachment_id)
            if path is None:  # Defensive; UUID hex always satisfies the validator.
                raise ChatAttachmentStorageError("could not create an attachment reference")
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as target:
                created.append(path)
                target.write(data)

            name = _display_name(uploaded_name)
            attachment["name"] = name
            attachment["attachment_id"] = attachment_id
            attachment["mime_type"] = attachment.get("image_mime") or mimetypes.guess_type(name)[0] or "application/octet-stream"
            attachment["size"] = len(data)
    except Exception as exc:  # noqa: BLE001 - remove partial writes before surfacing a storage error.
        for path in created:
            try:
                path.unlink(missing_ok=True)
                path.parent.rmdir()
            except OSError:
                pass
        if isinstance(exc, ChatAttachmentStorageError):
            raise
        raise ChatAttachmentStorageError("could not persist chat attachment") from exc


def _attachment_refs(tool_log_text: str | None) -> list[dict]:
    try:
        entries = json.loads(tool_log_text or "[]")
    except (TypeError, ValueError):
        return []
    if not isinstance(entries, list):
        return []
    refs: list[dict] = []
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("kind") != "attach":
            continue
        files = entry.get("files")
        if isinstance(files, list):
            refs.extend(item for item in files if isinstance(item, dict))
    return refs


def find_session_attachment(db, session_id: str, attachment_id: str) -> dict | None:
    """Find attachment metadata only when it is referenced by this session."""
    if not _path_for_id(attachment_id):
        return None
    rows = db.query(ChatMessage.tool_log).filter(ChatMessage.session_id == session_id).all()
    for row in rows:
        tool_log_text = row[0] if row else None
        for ref in _attachment_refs(tool_log_text):
            if ref.get("attachmentId") == attachment_id:
                return ref
    return None


def resolve_chat_attachment(attachment_id: str) -> Path | None:
    path = _path_for_id(attachment_id)
    return path if path and path.is_file() else None


def session_attachment_ids(db, session_id: str) -> set[str]:
    rows = db.query(ChatMessage.tool_log).filter(ChatMessage.session_id == session_id).all()
    return {
        ref["attachmentId"]
        for row in rows
        for ref in _attachment_refs(row[0] if row else None)
        if _path_for_id(ref.get("attachmentId"))
    }


def user_session_attachment_ids(db, user_id: str) -> set[str]:
    rows = db.query(ChatMessage.tool_log).join(
        ChatSession, ChatMessage.session_id == ChatSession.session_id,
    ).filter(ChatSession.user_id == user_id).all()
    return {
        ref["attachmentId"]
        for row in rows
        for ref in _attachment_refs(row[0] if row else None)
        if _path_for_id(ref.get("attachmentId"))
    }


def delete_chat_attachments(attachment_ids: set[str]) -> None:
    """Remove session-owned files after the associated session rows are deleted."""
    for attachment_id in attachment_ids:
        path = _path_for_id(attachment_id)
        if not path:
            continue
        try:
            path.unlink(missing_ok=True)
            path.parent.rmdir()
        except OSError:
            # A failed cleanup leaves an ignored orphan file, not a broken session deletion.
            continue
