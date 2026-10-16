"""账号资料复用现有 JSON 数据表；头像文件保存为随机标识的规范 PNG。"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import io
import json
import logging
import os
import re
import uuid
import warnings

from fastapi import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import event
from sqlalchemy.orm import Session

from ..models.intervention import TeacherClassDashboard
from ..models.user import User
from ..utils import to_user_dict

DATA_TYPE = "account_profile"
MAX_AVATAR_BYTES = 5 * 1024 * 1024
AVATAR_ID = re.compile(r"^[a-f0-9]{32}$")
logger = logging.getLogger(__name__)


def avatar_directory() -> Path:
    configured = os.environ.get("USER_AVATAR_DIR")
    return Path(configured).resolve() if configured else Path(__file__).resolve().parents[1] / "data" / "avatars"


def _read(row) -> dict:
    try:
        value = json.loads(row.data_json or "{}")
        if isinstance(value, dict) and value.get("userId") == row.data_key:
            return value
    except (ValueError, TypeError):
        pass
    return {}


def profile_metadata(db: Session, user_ids: list[str]) -> dict[str, dict]:
    ids = list(dict.fromkeys(user_ids))
    result = {uid: {"signature": "", "avatarUrl": ""} for uid in ids}
    for start in range(0, len(ids), 500):
        rows = db.query(TeacherClassDashboard).filter(
            TeacherClassDashboard.data_type == DATA_TYPE,
            TeacherClassDashboard.class_id.is_(None),
            TeacherClassDashboard.data_key.in_(ids[start:start + 500]),
        ).order_by(TeacherClassDashboard.id.desc()).all()
        seen = set()
        for row in rows:
            if row.data_key in seen:
                continue
            seen.add(row.data_key)
            value = _read(row)
            signature = value.get("signature", "")
            avatar_id = str(value.get("avatarId") or "")
            result[row.data_key] = {
                "signature": signature[:120] if isinstance(signature, str) else "",
                "avatarUrl": f"/api/v1/auth/avatars/{avatar_id}.png" if AVATAR_ID.fullmatch(avatar_id) else "",
            }
    return result


def user_profile_dict(db: Session, user: User) -> dict:
    result = to_user_dict(user)
    result["username"] = user.username
    result.update(profile_metadata(db, [user.user_id])[user.user_id])
    return result


def normalize_avatar(data: bytes, filename: str) -> bytes:
    if not data or len(data) > MAX_AVATAR_BYTES:
        raise HTTPException(400, "头像文件不能为空或超过 5MB")
    if Path(filename or "").suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
        raise HTTPException(400, "头像只支持 JPG、PNG 或 WEBP")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                if image.format not in {"JPEG", "PNG", "WEBP"}:
                    raise HTTPException(400, "头像实际内容不是支持的图片格式")
                if image.width != image.height or not 64 <= image.width <= 2048:
                    raise HTTPException(400, "请先按 1:1 正方形裁剪头像，边长须为 64–2048 像素")
                if getattr(image, "n_frames", 1) != 1:
                    raise HTTPException(400, "头像须为静态图片，请先完成裁剪")
                image.load()
                rgba = ImageOps.exif_transpose(image).convert("RGBA").resize((512, 512), Image.Resampling.LANCZOS)
                output = Image.new("RGB", (512, 512), "white")
                output.paste(rgba, mask=rgba.getchannel("A"))
                stream = io.BytesIO()
                output.save(stream, "PNG", optimize=True)
                return stream.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise HTTPException(400, "图片无法读取或尺寸不安全，请重新选择并裁剪") from error


def _remove_avatar(avatar_id: str) -> None:
    if AVATAR_ID.fullmatch(avatar_id or ""):
        try:
            (avatar_directory() / f"{avatar_id}.png").unlink(missing_ok=True)
        except OSError:
            logger.warning("旧头像文件清理失败：%s", avatar_id)


@event.listens_for(Session, "after_commit")
def _remove_deleted_account_avatars(session):
    for avatar_id in session.info.pop("deleted_account_avatars", set()):
        _remove_avatar(avatar_id)


@event.listens_for(Session, "after_rollback")
def _cancel_avatar_cleanup(session):
    session.info.pop("deleted_account_avatars", None)


def delete_profile(db: Session, user_id: str) -> int:
    query = db.query(TeacherClassDashboard).filter(
        TeacherClassDashboard.data_type == DATA_TYPE,
        TeacherClassDashboard.class_id.is_(None),
        TeacherClassDashboard.data_key == user_id,
    )
    for row in query.all():
        avatar_id = str(_read(row).get("avatarId") or "")
        if AVATAR_ID.fullmatch(avatar_id):
            db.info.setdefault("deleted_account_avatars", set()).add(avatar_id)
    return query.delete(synchronize_session=False)


def save_profile(db: Session, user: User, signature: str, avatar: bytes | None, use_default: bool) -> dict:
    signature = signature.strip()
    if len(signature) > 120:
        raise HTTPException(400, "个性签名最多 120 字")
    if avatar is not None and use_default:
        raise HTTPException(400, "请选择新头像或恢复默认头像，不能同时操作")
    new_id = ""
    try:
        # 先锁住账号写入，再读取资料；并发保存也只产生一条账号资料记录。
        db.query(User).filter(User.user_id == user.user_id).update({User.updated_at: datetime.utcnow()}, synchronize_session=False)
        row = db.query(TeacherClassDashboard).filter(
            TeacherClassDashboard.data_type == DATA_TYPE,
            TeacherClassDashboard.class_id.is_(None),
            TeacherClassDashboard.data_key == user.user_id,
        ).order_by(TeacherClassDashboard.id.desc()).first()
        previous = _read(row) if row else {}
        old_id = str(previous.get("avatarId") or "")
        avatar_id = old_id if AVATAR_ID.fullmatch(old_id) else ""
        if avatar is not None:
            new_id = uuid.uuid4().hex
            directory = avatar_directory()
            directory.mkdir(parents=True, exist_ok=True)
            with (directory / f"{new_id}.png").open("xb") as target:
                target.write(avatar)
            avatar_id = new_id
        elif use_default:
            avatar_id = ""
        if row is None:
            row = TeacherClassDashboard(class_id=None, data_type=DATA_TYPE, data_key=user.user_id)
            db.add(row)
        row.data_json = json.dumps({"userId": user.user_id, "signature": signature, "avatarId": avatar_id}, ensure_ascii=False)
        row.updated_at = datetime.utcnow()
        db.commit()
    except Exception:
        db.rollback()
        if new_id:
            _remove_avatar(new_id)
        raise
    if old_id and old_id != avatar_id:
        _remove_avatar(old_id)
    return user_profile_dict(db, user)


def find_avatar(db: Session, avatar_id: str) -> Path:
    if not AVATAR_ID.fullmatch(avatar_id):
        raise HTTPException(404, "头像不存在")
    rows = db.query(TeacherClassDashboard).join(User, User.user_id == TeacherClassDashboard.data_key).filter(
        TeacherClassDashboard.data_type == DATA_TYPE,
        TeacherClassDashboard.class_id.is_(None),
        TeacherClassDashboard.data_json.like(f"%{avatar_id}%"),
    ).all()
    path = avatar_directory() / f"{avatar_id}.png"
    if not any(_read(row).get("avatarId") == avatar_id for row in rows) or not path.is_file():
        raise HTTPException(404, "头像不存在")
    return path
