"""班级与学生治理：复用 classes 和 users.class_name，不改变数据库结构。"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import uuid

from fastapi import HTTPException
from app.models.alert import Alert
from app.models.course import Course
from app.models.intervention import Intervention, Report, TeacherClassDashboard
from app.models.user import ClassInfo, TeacherClass, User
from app.models.user_course import UserCourse
from app.services.course_admin import class_key

MAX_CLASS_SELECTION = 2000


def class_catalog(db):
    """只读合并班级登记与历史学生班级名；同名的空白差异归为同一班。"""
    groups = {}
    for row in db.query(ClassInfo).order_by(ClassInfo.class_id).all():
        key = class_key(row.name)
        if not key:
            continue
        group = groups.setdefault(key, {"classId": row.class_id, "name": row.name,
                                       "classKey": key, "recordIds": [], "students": []})
        group["recordIds"].append(row.class_id)
    for user in db.query(User).filter(User.role == "student").order_by(User.username).all():
        key = class_key(user.class_name)
        if not key:
            continue
        group = groups.setdefault(key, {
            "classId": "CL" + hashlib.sha256(key.encode()).hexdigest()[:24].upper(),
            "name": user.class_name.strip(), "classKey": key, "recordIds": [], "students": [],
        })
        group["students"].append(user)
    return groups


def get_class(db, class_id):
    for group in class_catalog(db).values():
        if class_id == group["classId"] or class_id in group["recordIds"]:
            return group
    raise HTTPException(404, "班级不存在或已删除，请刷新列表")


def describe(group):
    return {"classId": group["classId"], "name": group["name"],
            "studentCount": len(group["students"])}


def list_classes(db, keyword=""):
    return [describe(group) for _, group in sorted(class_catalog(db).items())
            if not keyword or keyword.casefold() in group["name"].casefold()]


def ensure_class(db, name):
    name = str(name or "").strip()
    if not name or len(name) > 64:
        raise HTTPException(400, "班级名称须为 1～64 个字符")
    key = class_key(name)
    if not key:
        raise HTTPException(400, "班级名称不能为空")
    group = class_catalog(db).get(key)
    if group and group["recordIds"]:
        return db.get(ClassInfo, group["classId"])
    row = ClassInfo(class_id=group["classId"] if group else "CL" + uuid.uuid4().hex[:24].upper(),
                    name=group["name"] if group else name, student_count=0)
    db.add(row)
    db.flush()
    return row


def refresh_class_counts(db):
    db.flush()
    counts = Counter(class_key(name) for (name,) in db.query(User.class_name).filter(User.role == "student").all())
    names = {row.class_id: row.name for row in db.query(ClassInfo).all()}
    for row in db.query(ClassInfo).all():
        row.student_count = counts[class_key(row.name)]
    for row in db.query(TeacherClass).all():
        row.student_count = counts[class_key(names.get(row.class_id) or row.class_name)]


def create_class(db, name):
    if class_key(name) in class_catalog(db):
        raise HTTPException(409, "已存在同名班级")
    row = ensure_class(db, name)
    return {"classId": row.class_id, "name": row.name, "studentCount": 0}


def student_dict(user):
    return {"userId": user.user_id, "username": user.username, "name": user.name,
            "studentNo": user.student_no or "", "className": user.class_name or ""}


def members(db, class_id):
    group = get_class(db, class_id)
    return {**describe(group), "list": [student_dict(user) for user in group["students"]]}


def assign_students(db, class_id, user_ids):
    group = get_class(db, class_id)
    ids = list(dict.fromkeys(user_ids))
    if not ids or len(ids) > MAX_CLASS_SELECTION:
        raise HTTPException(400, f"请选择 1～{MAX_CLASS_SELECTION} 名学生")
    users = db.query(User).filter(User.user_id.in_(ids), User.role == "student").all()
    if len(users) != len(ids):
        raise HTTPException(400, "选中的账号不存在或不是学生，请刷新后重选")
    row = ensure_class(db, group["name"])
    for user in users:
        user.class_name = row.name
    refresh_class_counts(db)
    return {"classId": row.class_id, "assigned": len(users)}


def deletion_preview(db, class_id):
    group = get_class(db, class_id)
    students = [student_dict(user) for user in group["students"]]
    revision = hashlib.sha256(json.dumps(
        [group["classId"], group["name"], students], ensure_ascii=False, sort_keys=True,
    ).encode()).hexdigest()
    ids = [student["userId"] for student in students]
    courses = db.query(Course.course_id, Course.name).join(
        UserCourse, UserCourse.course_id == Course.course_id,
    ).filter(UserCourse.user_id.in_(ids)).distinct().all() if ids else []
    return {**describe(group), "revision": revision, "students": students,
            "courses": [{"courseId": cid, "name": name} for cid, name in courses]}


def delete_students(db, class_id, actor_id, user_ids=None, *, revision=None):
    """整批删除只提交一次；班级成员变化时必须重新预览，不扩大已确认的删除范围。"""
    from app.services.account_import import delete_block_reason, delete_user_cascade
    from app.services.chat_attachments import user_session_attachment_ids

    group = get_class(db, class_id)
    row = ensure_class(db, group["name"])
    # 在读取最终删除范围前取得 SQLite 写锁，避免确认检查与删除之间混入新学生。
    db.query(ClassInfo).filter(ClassInfo.class_id == row.class_id).update(
        {ClassInfo.student_count: ClassInfo.student_count}, synchronize_session=False,
    )
    group = get_class(db, class_id)
    all_ids = {user.user_id for user in group["students"]}
    deleting_class = revision is not None
    if deleting_class:
        if deletion_preview(db, class_id)["revision"] != revision:
            raise HTTPException(409, "班级或学生名单已变化，请重新预览后确认删除")
        selected = group["students"]
    else:
        ids = list(dict.fromkeys(user_ids or []))
        if not ids or len(ids) > MAX_CLASS_SELECTION or not set(ids).issubset(all_ids):
            raise HTTPException(400, "请选择当前班级中的学生；单次最多删除 2000 人")
        selected = [user for user in group["students"] if user.user_id in set(ids)]
    for user in selected:
        reason = delete_block_reason(db, user, actor_id)
        if reason:
            raise HTTPException(400, f"{user.name}：{reason}；本次未删除任何学生")
    attachment_ids = set()
    stats = Counter()
    for user in selected:
        attachment_ids.update(user_session_attachment_ids(db, user.user_id))
        stats.update(delete_user_cascade(db, user, refresh_classes=False))
    if deleting_class:
        ids = group["recordIds"]
        for model in (Alert, Intervention, Report, TeacherClassDashboard, TeacherClass):
            stats[model.__tablename__] += db.query(model).filter(model.class_id.in_(ids)).delete(synchronize_session=False)
        stats["classes"] += db.query(ClassInfo).filter(ClassInfo.class_id.in_(ids)).delete(synchronize_session=False)
    refresh_class_counts(db)
    return {"classId": class_id, "name": group["name"], "deletedStudents": len(selected),
            "deleted": dict(stats)}, attachment_ids
