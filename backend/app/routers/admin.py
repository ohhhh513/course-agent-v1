"""
管理员接口: /admin/*
仅 role=admin 可访问；创建 / 删除教师、学生账号。
删除时按外键与业务表级联清理个人数据，并保护课程 owner。
"""
from fastapi import APIRouter, Depends, Body, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional, List

from ..database import get_db
from ..models.user import User, TeacherClass
from ..models.user_course import UserCourse
from ..models.course import Course, ResourceProgress, ResourceStudyLog
from ..models.graph import LearningPath
from ..models.practice import PracticeSession, AnswerRecord
from ..models.ai import ChatSession, ChatMessage
from ..models.alert import Alert, Message
from ..models.checkin import StudyCheckin
from ..models.agent_st import STQuestionDraft
from ..middleware.auth import get_current_user, hash_password
from ..schemas.common import ok, fail
from ..utils import to_user_dict

router = APIRouter(prefix="/api/v1/admin", tags=["管理员"])


def _require_admin(user: User = Depends(get_current_user)) -> User:
    if getattr(user, "role", "") != "admin":
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="仅管理员可访问")
    return user


class CreateUserReq(BaseModel):
    username: str
    password: str
    role: str                       # teacher | student
    name: str
    className: str = ""             # 学生
    dept: str = ""                  # 教师
    title: str = ""
    studentNo: str = ""


@router.get("/users")
def list_users(
    role: str = "",
    keyword: str = "",
    db: Session = Depends(get_db),
    admin: User = Depends(_require_admin),
):
    q = db.query(User).filter(User.role != "admin")
    if role and role in ("teacher", "student"):
        q = q.filter(User.role == role)
    if keyword:
        like = f"%{keyword}%"
        q = q.filter(User.username.like(like) | User.name.like(like))
    rows = q.order_by(User.user_id.asc()).all()
    items = []
    for u in rows:
        d = to_user_dict(u)
        d["username"] = u.username
        d["className"] = u.class_name or ""
        d["dept"] = u.dept or ""
        items.append(d)
    return ok({"total": len(items), "list": items})


@router.post("/users")
def create_user(
    body: CreateUserReq,
    db: Session = Depends(get_db),
    admin: User = Depends(_require_admin),
):
    """创建教师或学生账号"""
    role = (body.role or "").strip()
    if role not in ("teacher", "student"):
        return fail("角色仅支持 teacher / student", 400)
    username = (body.username or "").strip()
    name = (body.name or "").strip()
    password = body.password or ""
    if not username or not name:
        return fail("用户名与姓名不能为空", 400)
    if len(password) < 6:
        return fail("密码至少 6 位", 400)
    if db.query(User).filter(User.username == username).first():
        return fail("用户名已存在", 400)

    if role == "teacher":
        uid = "T" + username[:12]
        while db.query(User).filter(User.user_id == uid).first():
            uid = "T" + username[:8] + str(db.query(User).count())[-4:]
    else:
        uid = "S" + username[:12]
        while db.query(User).filter(User.user_id == uid).first():
            uid = "S" + username[:8] + str(db.query(User).count())[-4:]

    user = User(
        user_id=uid,
        username=username,
        password=hash_password(password),
        name=name,
        role=role,
        avatar_char=name[0],
        student_no=(body.studentNo or "").strip() if role == "student" else "",
        class_name=(body.className or "").strip() if role == "student" else "",
        title=(body.title or "").strip() if role == "teacher" else "",
        dept=(body.dept or "").strip() if role == "teacher" else "",
    )
    db.add(user)
    db.commit()
    return ok({
        "userId": uid,
        "username": username,
        "role": role,
        "name": name,
    })


class UpdateUserReq(BaseModel):
    username: str = ""
    name: str = ""
    password: str = ""              # 留空 = 不修改密码
    className: str = ""             # 学生
    studentNo: str = ""             # 学生
    dept: str = ""                  # 教师
    title: str = ""                 # 教师


@router.put("/users/{user_id}")
def update_user(
    user_id: str,
    body: UpdateUserReq,
    db: Session = Depends(get_db),
    admin: User = Depends(_require_admin),
):
    """编辑教师/学生账号（管理员）。

    - 角色不可改（user_id 前缀与角色绑定）
    - 用户名改动会做唯一性校验；姓名改动同步刷新 avatar_char
    - password 留空表示不修改
    """
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        return fail("账号不存在", 404)
    if user.role == "admin":
        return fail("不能编辑管理员账号", 400)

    username = (body.username or "").strip()
    if username and username != user.username:
        if db.query(User).filter(User.username == username, User.user_id != user_id).first():
            return fail("用户名已存在", 400)
        user.username = username

    name = (body.name or "").strip()
    if name:
        user.name = name
        user.avatar_char = name[0]

    if body.password:
        if len(body.password) < 6:
            return fail("密码至少 6 位", 400)
        user.password = hash_password(body.password)

    if user.role == "student":
        user.class_name = (body.className or "").strip()
        user.student_no = (body.studentNo or "").strip()
    else:
        user.dept = (body.dept or "").strip()
        user.title = (body.title or "").strip()

    db.commit()
    d = to_user_dict(user)
    d["username"] = user.username
    d["className"] = user.class_name or ""
    d["dept"] = user.dept or ""
    return ok(d)


class DeleteUserReq(BaseModel):
    confirmUsername: str = ""
    force: bool = False


def _delete_user_cascade(db: Session, user: User) -> dict:
    """删除用户及其个人关联数据（不动课程内容与资源文件）。

    顺序：先子表后 users，保证 FK 不失败。
    教师若仍是某课 owner（courses.owner_id），默认拒绝；force 仅解除 owner 清空字段，不删课。
    """
    uid = user.user_id
    stats = {}

    # 课程 owner 保护
    owned = db.query(Course).filter(Course.owner_id == uid).all()
    if owned:
        return {
            "blocked": True,
            "reason": f"该用户是 {len(owned)} 门课程的创建者（owner），请先转交或归档课程后再删号",
            "ownedCourses": [{"courseId": c.course_id, "name": c.name} for c in owned],
        }

    # AI 会话消息 → 会话
    sess_ids = [r[0] for r in db.query(ChatSession.session_id).filter(ChatSession.user_id == uid).all()]
    if sess_ids:
        stats["chatMessages"] = db.query(ChatMessage).filter(ChatMessage.session_id.in_(sess_ids)).delete(synchronize_session=False)
        stats["chatSessions"] = db.query(ChatSession).filter(ChatSession.user_id == uid).delete(synchronize_session=False)

    # 练习
    ps_ids = [r[0] for r in db.query(PracticeSession.session_id).filter(PracticeSession.user_id == uid).all()]
    if ps_ids:
        stats["answerRecords"] = db.query(AnswerRecord).filter(
            (AnswerRecord.user_id == uid) | (AnswerRecord.session_id.in_(ps_ids))
        ).delete(synchronize_session=False)
    else:
        stats["answerRecords"] = db.query(AnswerRecord).filter(AnswerRecord.user_id == uid).delete(synchronize_session=False)
    stats["practiceSessions"] = db.query(PracticeSession).filter(PracticeSession.user_id == uid).delete(synchronize_session=False)

    # 学习进度 / 路径 / 打卡
    stats["resourceProgress"] = db.query(ResourceProgress).filter(ResourceProgress.user_id == uid).delete(synchronize_session=False)
    stats["studyLogs"] = db.query(ResourceStudyLog).filter(ResourceStudyLog.user_id == uid).delete(synchronize_session=False)
    stats["learningPaths"] = db.query(LearningPath).filter(LearningPath.user_id == uid).delete(synchronize_session=False)
    stats["checkins"] = db.query(StudyCheckin).filter(StudyCheckin.user_id == uid).delete(synchronize_session=False)

    # 预警 / 消息
    stats["alerts"] = db.query(Alert).filter(Alert.user_id == uid).delete(synchronize_session=False)
    stats["messages"] = db.query(Message).filter(
        (Message.user_id == uid) | (Message.from_user == uid)
    ).delete(synchronize_session=False)

    # AI 出题草稿
    stats["drafts"] = db.query(STQuestionDraft).filter(STQuestionDraft.user_id == uid).delete(synchronize_session=False)

    # 课程成员 / 教师班级关联
    stats["userCourses"] = db.query(UserCourse).filter(UserCourse.user_id == uid).delete(synchronize_session=False)
    stats["teacherClasses"] = db.query(TeacherClass).filter(TeacherClass.teacher_user_id == uid).delete(synchronize_session=False)

    db.delete(user)
    return {"blocked": False, "deleted": stats}


@router.delete("/users/{user_id}")
def delete_user(
    user_id: str,
    body: DeleteUserReq = Body(default=DeleteUserReq()),
    db: Session = Depends(get_db),
    admin: User = Depends(_require_admin),
):
    """删除教师/学生账号（管理员）。

    - 禁止删自己、禁止删 role=admin
    - 教师若为课程 owner → 400（需先处理课程）
    - 级联清理：练习/答题、资源进度、学习路径、AI 会话、预警消息、草稿、成员关系等
    """
    if user_id == admin.user_id:
        return fail("不能删除当前登录的管理员账号", 400)
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        return fail("账号不存在", 404)
    if user.role == "admin":
        return fail("不能删除管理员账号", 400)
    if body.confirmUsername and body.confirmUsername.strip() != user.username:
        return fail("确认用户名不一致", 400)

    try:
        result = _delete_user_cascade(db, user)
    except Exception as e:
        db.rollback()
        return fail(f"删除失败：{e}", 500)

    if result.get("blocked"):
        db.rollback()
        owned = result.get("ownedCourses") or []
        names = "、".join(x["name"] for x in owned[:3])
        return fail(f"{result['reason']}：{names}", 400)

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        return fail(f"提交失败：{e}", 500)

    return ok({
        "userId": user_id,
        "username": user.username,
        "role": user.role,
        "deleted": result.get("deleted") or {},
    })
