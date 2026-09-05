"""
认证相关接口: /auth/*
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import date

from ..database import get_db
from ..models.user import User, TeacherClass
from ..middleware.auth import hash_password, verify_password, create_jwt, get_current_user
from ..schemas.common import ok, fail
from ..utils import to_user_dict

router = APIRouter(prefix="/api/v1/auth", tags=["认证"])


class LoginReq(BaseModel):
    username: str
    password: str
    role: str = "student"


class ResetReq(BaseModel):
    username: str
    password: str


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
    user_dict = to_user_dict(user)
    # 教师班级
    if user.role == "teacher":
        tc_list = db.query(TeacherClass).filter(TeacherClass.teacher_user_id == user.user_id).all()
        user_dict["classes"] = [
            {"classId": tc.class_id, "name": tc.class_name, "studentCount": tc.student_count}
            for tc in tc_list
        ]
    return ok({"token": token, "user": user_dict})


@router.post("/reset-password")
def reset_password(
    req: ResetReq,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """重置密码：必须已登录，且只能重置当前登录账号"""
    if req.username != current_user.username:
        return fail("只能重置当前登录账号的密码", 403)
    user = db.query(User).filter(User.username == req.username).first()
    if not user:
        return fail("账号不存在", 404)
    if not req.password or len(req.password) < 6:
        return fail("新密码至少 6 位")
    user.password = hash_password(req.password)
    db.commit()
    return ok({"ok": True})


@router.get("/profile")
def profile(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取当前登录用户信息"""
    user_dict = to_user_dict(user)
    if user.role == "teacher":
        tc_list = db.query(TeacherClass).filter(TeacherClass.teacher_user_id == user.user_id).all()
        user_dict["classes"] = [
            {"classId": tc.class_id, "name": tc.class_name, "studentCount": tc.student_count}
            for tc in tc_list
        ]
    return ok(user_dict)


@router.post("/logout")
def logout():
    """退出登录（后端端可做 token 黑名单，原型仅返回成功）"""
    return ok({"ok": True})
