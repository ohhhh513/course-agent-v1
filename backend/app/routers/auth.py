"""
认证相关接口: /auth/*
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from datetime import date

from ..database import get_db
from ..models.user import User, TeacherClass
from ..middleware.auth import hash_password, verify_password, create_jwt, get_current_user
from ..schemas.common import ok, fail
from ..services.user_profiles import MAX_AVATAR_BYTES, find_avatar, normalize_avatar, save_profile, user_profile_dict

router = APIRouter(prefix="/api/v1/auth", tags=["认证"])


class LoginReq(BaseModel):
    username: str
    password: str
    role: str = "student"


class ResetReq(BaseModel):
    username: str
    password: str
    currentPassword: str = Field(default="", max_length=256)


class PasswordChangeReq(BaseModel):
    currentPassword: str = Field(min_length=1, max_length=256)
    password: str = Field(min_length=6, max_length=72)


def _add_classes(db: Session, user: User, data: dict) -> dict:
    if user.role == "teacher":
        rows = db.query(TeacherClass).filter(TeacherClass.teacher_user_id == user.user_id).all()
        data["classes"] = [{"classId": row.class_id, "name": row.class_name, "studentCount": row.student_count} for row in rows]
    return data


def _change_password(db: Session, user: User, current: str, password: str):
    if not current:
        raise HTTPException(400, "请输入当前密码")
    if not verify_password(current, user.password):
        raise HTTPException(400, "当前密码不正确")
    if len(password) < 6:
        raise HTTPException(400, "新密码至少 6 位")
    if len(password.encode("utf-8")) > 72:
        raise HTTPException(400, "新密码过长，请缩短后再试")
    if current == password:
        raise HTTPException(400, "新密码不能与当前密码相同")
    previous = user.password
    changed = db.query(User).filter(User.user_id == user.user_id, User.password == previous).update(
        {User.password: hash_password(password)}, synchronize_session=False)
    if changed != 1:
        db.rollback()
        raise HTTPException(409, "密码已发生变化，请重新输入当前密码")
    db.commit()
    return ok({"ok": True})


@router.post("/login")
def login(req: LoginReq, db: Session = Depends(get_db)):
    """账号密码登录，返回 JWT + 用户信息"""
    user = db.query(User).filter(User.username == req.username).first()
    if not user:
        return fail("账号不存在", 404)
    if not verify_password(req.password, user.password):
        return fail("密码错误，请重试", 401)
    # 签发 JWT
    token = create_jwt(user.user_id, user.role)
    # 学生登录即打卡：记录今天为学习/签到日（幂等，重复登录不重复计）
    if user.role == "student":
        from ..models.checkin import StudyCheckin
        _today = date.today()
        _exists = db.query(StudyCheckin.id).filter(
            StudyCheckin.user_id == user.user_id, StudyCheckin.day == _today
        ).first()
        if not _exists:
            db.add(StudyCheckin(user_id=user.user_id, day=_today, kind="login"))
            db.commit()
    user_dict = _add_classes(db, user, user_profile_dict(db, user))
    return ok({"token": token, "user": user_dict})


@router.post("/reset-password")
def reset_password(
    req: ResetReq,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """兼容旧入口：必须已登录并验证当前密码，只能修改本人密码。"""
    if req.username != current_user.username:
        return fail("只能重置当前登录账号的密码", 403)
    user = db.query(User).filter(User.username == req.username).first()
    if not user:
        return fail("账号不存在", 404)
    return _change_password(db, user, req.currentPassword, req.password)


@router.post("/change-password")
def change_password(req: PasswordChangeReq, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _change_password(db, user, req.currentPassword, req.password)


@router.get("/profile")
def profile(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取当前登录用户信息"""
    return ok(_add_classes(db, user, user_profile_dict(db, user)))


@router.put("/profile")
def update_profile(
    signature: str = Form(default="", max_length=120),
    useDefaultAvatar: bool = Form(default=False),
    avatar: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    data = normalize_avatar(avatar.file.read(MAX_AVATAR_BYTES + 1), avatar.filename or "") if avatar else None
    updated = save_profile(db, user, signature, data, useDefaultAvatar)
    return ok(_add_classes(db, user, updated))


@router.get("/avatars/{avatar_id}.png")
def read_avatar(avatar_id: str, db: Session = Depends(get_db)):
    # 图片使用不可枚举的随机标识；只返回仍由有效账号资料引用的头像。
    path = find_avatar(db, avatar_id)
    return FileResponse(path, media_type="image/png", headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "public, max-age=31536000, immutable"})


@router.post("/logout")
def logout():
    """退出登录（后端端可做 token 黑名单，原型仅返回成功）"""
    return ok({"ok": True})
