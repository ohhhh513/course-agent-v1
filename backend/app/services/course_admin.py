"""管理员课程治理：建课 / 改课 / 删空课，以及把学生绑进课程。

只使用现有列，不改表结构：
- 课程写 ``courses``（教学班号仍折进 ``code`` 的 ``代码||班号``）；
- 成员写 ``user_courses``；
- 学生入课后走与「凭邀请码加入」相同的 ``learning_path.sync_user``。

删除只允许还没有教学内容的空课：有资源、题目、图谱、学习记录等外键数据时拒绝，
避免误删教师已经在用的课。移出成员只删 ``user_courses`` 这一行，学习记录保留。
"""
from __future__ import annotations

import random
import re
from collections import Counter, defaultdict
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.ai import ChatSession
from app.models.agent_st import STQuestionDraft
from app.models.alert import Alert
from app.models.course import Course, Resource, pack_course_code, unpack_course_code
from app.models.graph import GraphLink, GraphNode, KpDetail, LearningPath
from app.models.intervention import TeacherClassDashboard
from app.models.practice import AnswerRecord, PracticeSession
from app.models.question import Question
from app.models.tag import Tag
from app.models.user import User
from app.models.user_course import UserCourse
from app.services.account_import import norm_header, rows_from_upload

MAX_ROSTER_ROWS = 2000
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

ROSTER_ALIASES = {
    "username": ["用户名", "账号", "登录名", "username", "user", "login"],
    "studentNo": ["学号", "studentno"],
    "name": ["姓名", "名字", "name", "真实姓名"],
}

# 有外键指向 courses 的内容。有任意一条就不能删课（成员关系没有外键，删课时单独清掉）。
_CONTENT_COUNTERS = (
    ("资源", Resource, Resource.course_id),
    ("题目", Question, Question.course_id),
    ("图谱节点", GraphNode, GraphNode.course_id),
    ("图谱连线", GraphLink, GraphLink.course_id),
    ("知识点详情", KpDetail, KpDetail.course_id),
    ("学习路径", LearningPath, LearningPath.course_id),
    ("练习", PracticeSession, PracticeSession.course_id),
    ("答题记录", AnswerRecord, AnswerRecord.course_id),
    ("答疑会话", ChatSession, ChatSession.course_id),
    ("出题草稿", STQuestionDraft, STQuestionDraft.course_id),
    ("预警", Alert, Alert.course_id),
    ("标签", Tag, Tag.course_id),
)


class CourseAdminError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def class_key(name: str) -> str:
    """班级归组键：去掉全部空白并小写，让「计算机 2301」和「计算机2301」算同一个班。"""
    return re.sub(r"\s+", "", (name or "")).strip().lower()


def _gen_course_id(db: Session) -> str:
    while True:
        cid = "C" + "".join(random.choices(_ALPHABET, k=7))
        if not db.query(Course.course_id).filter(Course.course_id == cid).first():
            return cid


def _gen_invite_code(db: Session) -> str:
    while True:
        code = "".join(random.choices(_ALPHABET, k=8))
        if not db.query(Course.course_id).filter(Course.invite_code == code).first():
            return code


def _clean_code_pair(code: str, class_no: str) -> tuple[str, str]:
    code = (code or "").strip()
    class_no = (class_no or "").strip()
    if len(code) > 32 or len(class_no) > 32:
        raise CourseAdminError("课程代码和教学班号不能超过 32 个字")
    if "||" in code or "||" in class_no:
        raise CourseAdminError("课程代码和教学班号不能包含 ||")
    return code, class_no


def _teacher(db: Session, user_id: str) -> User:
    teacher = db.query(User).filter(User.user_id == (user_id or "").strip()).first()
    if teacher is None or teacher.role != "teacher":
        raise CourseAdminError("请选择一位已有的教师作为课程负责人")
    return teacher


def _get_course(db: Session, course_id: str) -> Course:
    course = db.query(Course).filter(Course.course_id == course_id).first()
    if course is None:
        raise CourseAdminError("课程不存在")
    return course


def _count(db: Session, model, column, course_id: str) -> int:
    return int(db.query(func.count()).select_from(model).filter(column == course_id).scalar() or 0)


def content_blockers(db: Session, course_id: str) -> list[tuple[str, int]]:
    found = [(label, n) for label, model, col in _CONTENT_COUNTERS if (n := _count(db, model, col, course_id))]
    papers = int(
        db.query(func.count())
        .select_from(TeacherClassDashboard)
        .filter(func.json_extract(TeacherClassDashboard.data_json, "$.courseId") == course_id)
        .scalar()
        or 0
    )
    if papers:
        found.append(("试卷或教师端记录", papers))
    return found


def _member_counts(db: Session) -> tuple[dict[str, int], dict[str, int]]:
    rows = (
        db.query(UserCourse.course_id, UserCourse.role_in_course, func.count())
        .group_by(UserCourse.course_id, UserCourse.role_in_course)
        .all()
    )
    students: dict[str, int] = defaultdict(int)
    teachers: dict[str, int] = defaultdict(int)
    for cid, role, n in rows:
        (teachers if role == "teacher" else students)[cid] += int(n)
    return students, teachers


def _live_counts(db: Session) -> dict[str, dict[str, int]]:
    def grouped(model, column, *filters):
        q = db.query(column, func.count()).select_from(model)
        for cond in filters:
            q = q.filter(cond)
        return {cid: int(n) for cid, n in q.group_by(column).all()}

    return {
        "chapters": grouped(GraphNode, GraphNode.course_id, GraphNode.graph_type == "chapter"),
        "knowledgePoints": grouped(GraphNode, GraphNode.course_id, GraphNode.graph_type == "knowledge"),
        "resources": grouped(Resource, Resource.course_id),
        "questions": grouped(Question, Question.course_id),
    }


def _course_dict(course: Course, owner: User | None, students: int, teachers: int, live: dict) -> dict:
    code, class_no = unpack_course_code(course.code)
    cid = course.course_id
    return {
        "courseId": cid,
        "name": course.name,
        "code": code,
        "classNo": class_no,
        "term": course.term or "",
        "teacher": (owner.name if owner else "") or course.teacher or "",
        "ownerId": course.owner_id or "",
        "ownerUsername": owner.username if owner else "",
        "inviteCode": course.invite_code or "",
        "studentCount": students,
        "teacherCount": teachers,
        "chapters": live.get("chapters", {}).get(cid, 0),
        "knowledgePoints": live.get("knowledgePoints", {}).get(cid, 0),
        "resources": live.get("resources", {}).get(cid, 0),
        "questions": live.get("questions", {}).get(cid, 0),
    }


def list_courses(db: Session) -> list[dict]:
    courses = db.query(Course).order_by(Course.course_id.asc()).all()
    owner_ids = [c.owner_id for c in courses if c.owner_id]
    owners = {
        u.user_id: u for u in db.query(User).filter(User.user_id.in_(owner_ids)).all()
    } if owner_ids else {}
    students, teachers = _member_counts(db)
    live = _live_counts(db)
    return [
        _course_dict(c, owners.get(c.owner_id), students[c.course_id], teachers[c.course_id], live)
        for c in courses
    ]


def _role_count(db: Session, course_id: str, role: str) -> int:
    return int(
        db.query(func.count()).select_from(UserCourse).filter(
            UserCourse.course_id == course_id, UserCourse.role_in_course == role,
        ).scalar() or 0
    )


def _one(db: Session, course: Course) -> dict:
    # 会话关闭了 autoflush，成员刚写入时要先刷出，计数才看得到。
    db.flush()
    owner = db.query(User).filter(User.user_id == course.owner_id).first() if course.owner_id else None
    cid = course.course_id
    live = {
        "chapters": {cid: int(db.query(func.count()).select_from(GraphNode).filter(
            GraphNode.course_id == cid, GraphNode.graph_type == "chapter").scalar() or 0)},
        "knowledgePoints": {cid: int(db.query(func.count()).select_from(GraphNode).filter(
            GraphNode.course_id == cid, GraphNode.graph_type == "knowledge").scalar() or 0)},
        "resources": {cid: _count(db, Resource, Resource.course_id, cid)},
        "questions": {cid: _count(db, Question, Question.course_id, cid)},
    }
    return _course_dict(course, owner, _role_count(db, cid, "student"), _role_count(db, cid, "teacher"), live)


def _ensure_teacher_member(db: Session, teacher: User, course_id: str) -> None:
    exists = db.query(UserCourse).filter(
        UserCourse.user_id == teacher.user_id, UserCourse.course_id == course_id,
    ).first()
    if exists:
        if exists.role_in_course != "teacher":
            exists.role_in_course = "teacher"
        return
    db.add(UserCourse(
        user_id=teacher.user_id, course_id=course_id,
        role_in_course="teacher", joined_at=datetime.utcnow(),
    ))


def create_course(db: Session, *, name: str, term: str, code: str, class_no: str, teacher_user_id: str) -> dict:
    title = (name or "").strip()
    if not title:
        raise CourseAdminError("课程名称不能为空")
    if len(title) > 128:
        raise CourseAdminError("课程名称不能超过 128 个字")
    term = (term or "").strip()
    if len(term) > 64:
        raise CourseAdminError("学期不能超过 64 个字")
    code, class_no = _clean_code_pair(code, class_no)
    teacher = _teacher(db, teacher_user_id)
    course = Course(
        course_id=_gen_course_id(db),
        name=title,
        code=pack_course_code(code, class_no),
        term=term,
        teacher=teacher.name,
        invite_code=_gen_invite_code(db),
        owner_id=teacher.user_id,
    )
    db.add(course)
    db.flush()
    _ensure_teacher_member(db, teacher, course.course_id)
    return _one(db, course)


def update_course(
    db: Session, course_id: str, *,
    name: str | None, term: str | None, code: str | None, class_no: str | None,
    teacher_user_id: str | None,
) -> dict:
    course = _get_course(db, course_id)
    if name is not None:
        title = name.strip()
        if not title:
            raise CourseAdminError("课程名称不能为空")
        if len(title) > 128:
            raise CourseAdminError("课程名称不能超过 128 个字")
        course.name = title
    if term is not None:
        term = term.strip()
        if len(term) > 64:
            raise CourseAdminError("学期不能超过 64 个字")
        course.term = term
    if code is not None or class_no is not None:
        old_code, old_class = unpack_course_code(course.code)
        code, class_no = _clean_code_pair(
            old_code if code is None else code,
            old_class if class_no is None else class_no,
        )
        course.code = pack_course_code(code, class_no)
    if teacher_user_id is not None and teacher_user_id.strip() and teacher_user_id.strip() != course.owner_id:
        teacher = _teacher(db, teacher_user_id)
        course.owner_id = teacher.user_id
        course.teacher = teacher.name
        _ensure_teacher_member(db, teacher, course.course_id)
    return _one(db, course)


def delete_course(db: Session, course_id: str) -> dict:
    course = _get_course(db, course_id)
    blocked = content_blockers(db, course.course_id)
    if blocked:
        detail = "、".join(f"{label} {n}" for label, n in blocked)
        raise CourseAdminError(f"课程仍有教学内容，不能删除（{detail}）。可以先移出学生；已有章节、资源和题目需由教师端处理。")
    removed = db.query(UserCourse).filter(UserCourse.course_id == course.course_id).delete(synchronize_session=False)
    db.delete(course)
    return {"courseId": course.course_id, "name": course.name, "membersRemoved": int(removed or 0)}


def list_members(db: Session, course_id: str) -> dict:
    course = _get_course(db, course_id)
    rows = (
        db.query(UserCourse, User)
        .join(User, User.user_id == UserCourse.user_id)
        .filter(UserCourse.course_id == course.course_id)
        .order_by(UserCourse.role_in_course.asc(), User.class_name.asc(), User.username.asc())
        .all()
    )
    members = []
    for uc, user in rows:
        members.append({
            "userId": user.user_id,
            "username": user.username,
            "name": user.name,
            "role": uc.role_in_course,
            "className": user.class_name or "",
            "studentNo": user.student_no or "",
            "isOwner": user.user_id == course.owner_id,
            "joinedAt": uc.joined_at.isoformat(sep=" ", timespec="seconds") if uc.joined_at else "",
        })
    # ownerBound：负责人是否仍在成员表里。
    # 软退绑会删掉这行但保留 courses.owner_id，所以可能出现
    # ownerId 非空、而 ownerBound=false —— 那就是「待指派负责人」的课。
    owner_bound = any(m["isOwner"] for m in members)
    return {
        "courseId": course.course_id,
        "name": course.name,
        "total": len(members),
        "ownerId": course.owner_id or "",
        "ownerName": course.teacher or "",
        "ownerBound": owner_bound,
        "list": members,
    }


def list_classes(db: Session, course_id: str) -> dict:
    course = _get_course(db, course_id)
    _, class_no = unpack_course_code(course.code)
    token = class_key(class_no)
    bound = {
        uid for (uid,) in db.query(UserCourse.user_id).filter(
            UserCourse.course_id == course.course_id,
            UserCourse.role_in_course == "student",
        ).all()
    }
    students = db.query(User).filter(User.role == "student").order_by(User.username.asc()).all()
    grouped: dict[str, dict] = {}
    spellings: dict[str, Counter] = defaultdict(Counter)
    for user in students:
        key = class_key(user.class_name)
        spellings[key][(user.class_name or "").strip()] += 1
        bucket = grouped.setdefault(key, {"classKey": key, "studentCount": 0, "boundCount": 0})
        bucket["studentCount"] += 1
        if user.user_id in bound:
            bucket["boundCount"] += 1
    items = []
    for key, bucket in grouped.items():
        raw, _ = spellings[key].most_common(1)[0]
        bucket["className"] = raw or "（未填写班级）"
        bucket["matchesCourseClass"] = bool(token) and len(token) >= 2 and (key == token or token in key)
        items.append(bucket)
    items.sort(key=lambda x: (not x["matchesCourseClass"], x["className"]))
    return {
        "courseId": course.course_id,
        "classNo": class_no,
        "total": len(items),
        "list": items,
    }


def _students_for_keys(db: Session, class_keys: list[str]) -> list[User]:
    wanted = []
    seen = set()
    for key in class_keys or []:
        text = "" if key is None else str(key)
        if text in seen:
            continue
        seen.add(text)
        wanted.append(text)
    if not wanted:
        raise CourseAdminError("请先选择班级")
    want = set(wanted)
    return [u for u in db.query(User).filter(User.role == "student").all() if class_key(u.class_name) in want]


def bind_users(db: Session, course: Course, users: list[User]) -> dict:
    if len(users) > MAX_ROSTER_ROWS:
        raise CourseAdminError(f"单次最多绑定 {MAX_ROSTER_ROWS} 名学生")
    from app.services.learning_path import sync_user

    existing = {
        uid for (uid,) in db.query(UserCourse.user_id).filter(UserCourse.course_id == course.course_id).all()
    }
    bound = already = 0
    for user in users:
        if user.role != "student":
            continue
        if user.user_id in existing:
            already += 1
            continue
        db.add(UserCourse(
            user_id=user.user_id, course_id=course.course_id,
            role_in_course="student", joined_at=datetime.utcnow(),
        ))
        existing.add(user.user_id)
        sync_user(db, user.user_id, course.course_id)
        bound += 1
    return {"bound": bound, "already": already}


def bind_classes(db: Session, course_id: str, class_keys: list[str]) -> dict:
    course = _get_course(db, course_id)
    users = _students_for_keys(db, class_keys)
    if not users:
        raise CourseAdminError("这些班级下没有学生")
    result = bind_users(db, course, users)
    result["courseId"] = course.course_id
    result["selected"] = len(users)
    return result


def unbind_classes(db: Session, course_id: str, class_keys: list[str]) -> dict:
    course = _get_course(db, course_id)
    users = _students_for_keys(db, class_keys)
    return _unbind(db, course, users)


def unbind_member(db: Session, course_id: str, user_id: str) -> dict:
    """退绑一名成员。

    负责人（owner）**可以退绑**，这是刻意放开的一条路：以前这里直接拒绝，
    而 update_course 又只能「换成另一位教师」、无法设为「无负责人」，
    于是出现死锁 —— 教师自己建的课（owner 就是他）既换不掉也移不出，
    管理端永远删不掉这门课。

    软退绑语义：只删 user_courses 这一行，courses.owner_id 保留原值。
    课程因此处于「待指派负责人」状态：管理员仍能在编辑里改负责人，
    也可以直接删课（delete_course 会清掉剩余成员关系）。
    代价是该教师此刻已不再是该课成员，教师端权限校验
    （teacher.py 按 user_courses.role_in_course == "teacher" 判定）会拒绝他 ——
    这正是「退绑生效」的预期表现。
    """
    course = _get_course(db, course_id)
    user = db.query(User).filter(User.user_id == user_id).first()
    if user is None:
        raise CourseAdminError("账号不存在")
    return _unbind(db, course, [user])


def _unbind(db: Session, course: Course, users: list[User]) -> dict:
    """退绑一批成员，逐个删 user_courses 行。

    负责人也照删（软退绑，见 unbind_member 的说明）——课程因此进入
    「待指派负责人」状态，但 courses.owner_id 保留原值，管理员之后仍可改派。
    ownerUnbound 单独回报，用来告诉调用方这次退绑里有没有动到负责人。
    """
    removed = 0
    owner_unbound = False
    for user in users:
        n = db.query(UserCourse).filter(
            UserCourse.user_id == user.user_id,
            UserCourse.course_id == course.course_id,
        ).delete(synchronize_session=False)
        if n:
            removed += int(n)
        if user.user_id == course.owner_id:
            owner_unbound = True
    return {
        "courseId": course.course_id,
        "removed": removed,
        "ownerUnbound": owner_unbound,
    }


def unbind_members(db: Session, course_id: str, user_ids: list[str]) -> dict:
    """批量退绑（管理端「当前成员」勾选后一次移出多个）。"""
    course = _get_course(db, course_id)
    wanted = []
    seen = set()
    for raw in user_ids or []:
        uid = (raw or "").strip()
        if uid and uid not in seen:
            seen.add(uid)
            wanted.append(uid)
    if not wanted:
        raise CourseAdminError("请先勾选要移出的成员")
    if len(wanted) > MAX_ROSTER_ROWS:
        raise CourseAdminError(f"单次最多移出 {MAX_ROSTER_ROWS} 名成员")
    users = db.query(User).filter(User.user_id.in_(wanted)).all()
    missing = [uid for uid in wanted if uid not in {u.user_id for u in users}]
    if missing:
        raise CourseAdminError(f"有 {len(missing)} 个账号不存在：{'、'.join(missing[:3])}")
    result = _unbind(db, course, users)
    result["requested"] = len(wanted)
    return result


def _cell(value: str) -> str:
    text = (value or "").strip()
    if re.fullmatch(r"\d+\.0", text):
        return text[:-2]
    return text


def _looks_like_student_no(text: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9\-]{3,31}", text)) and any(ch.isdigit() for ch in text)


def parse_roster_rows(rows: list) -> list[dict]:
    """选课名单 → {rowIndex, username, studentNo, name, identifier}。首行像表头则跳过。"""
    if not rows:
        return []
    alias = {norm_header(name): field for field, names in ROSTER_ALIASES.items() for name in names}
    header: dict[int, str] = {}
    for index, cell in enumerate(rows[0]):
        field = alias.get(norm_header(_cell(str(cell or ""))))
        if field and field not in header.values():
            header[index] = field
    has_header = any(field in header.values() for field in ("username", "studentNo", "name"))
    data = rows[1:] if has_header else rows
    records = []
    for offset, row in enumerate(data, start=1):
        cells = [_cell(str(c or "")) for c in row]
        if not any(cells):
            continue
        rec = {"rowIndex": offset, "username": "", "studentNo": "", "name": "", "identifier": ""}
        if has_header:
            for index, field in header.items():
                if index < len(cells):
                    rec[field] = cells[index]
        elif len([c for c in cells if c]) == 1:
            rec["identifier"] = next(c for c in cells if c)
        else:
            filled = [c for c in cells if c]
            first = filled[0]
            if _looks_like_student_no(first) and not re.search(r"[A-Za-z]", first[:1]):
                rec["studentNo"] = first
                if len(filled) > 1:
                    rec["name"] = filled[1]
                if len(filled) > 2:
                    rec["username"] = filled[2]
            else:
                rec["username"] = first
                if len(filled) > 1:
                    rec["name"] = filled[1]
                if len(filled) > 2:
                    rec["studentNo"] = filled[2]
        if not any(rec[k] for k in ("username", "studentNo", "name", "identifier")):
            continue
        records.append(rec)
    return records


def _indexes(db: Session):
    users = db.query(User).all()
    by_username = {u.username: u for u in users}
    by_no: dict[str, list[User]] = defaultdict(list)
    by_name: dict[str, list[User]] = defaultdict(list)
    for user in users:
        if user.role != "student":
            continue
        if (user.student_no or "").strip():
            by_no[user.student_no.strip()].append(user)
        if (user.name or "").strip():
            by_name[user.name.strip()].append(user)
    return by_username, by_no, by_name


def _resolve_student(rec: dict, by_username, by_no, by_name) -> tuple[User | None, str]:
    username = rec.get("username") or ""
    student_no = rec.get("studentNo") or ""
    name = rec.get("name") or ""
    identifier = rec.get("identifier") or ""

    if username:
        user = by_username.get(username)
        if user is None:
            return None, "找不到该用户名"
        if user.role != "student":
            return None, "不是学生账号"
        if student_no and (user.student_no or "").strip() and (user.student_no or "").strip() != student_no:
            return None, "用户名与学号不是同一人"
        return user, ""

    if identifier:
        user = by_username.get(identifier)
        if user is not None:
            if user.role != "student":
                return None, "不是学生账号"
            return user, ""
        matched = by_no.get(identifier) or []
        if len(matched) == 1:
            return matched[0], ""
        if len(matched) > 1:
            return None, "学号对应多名学生"
        return None, "找不到该用户名或学号"

    if student_no:
        matched = by_no.get(student_no) or []
        if len(matched) == 1:
            return matched[0], ""
        if len(matched) > 1:
            return None, "学号对应多名学生"
        return None, "找不到该学号"

    if name:
        matched = by_name.get(name) or []
        if len(matched) == 1:
            return matched[0], ""
        if len(matched) > 1:
            return None, "同名学生有多名，请改用学号或用户名"
        return None, "找不到该姓名"
    return None, "缺少用户名、学号或姓名"


def classify_roster(db: Session, course_id: str, rows: list) -> dict:
    course = _get_course(db, course_id)
    records = parse_roster_rows(rows)
    if not records:
        raise CourseAdminError("文件中没有可识别的学生行。表头请使用「学号 / 姓名 / 用户名」，至少要有学号或用户名。")
    if len(records) > MAX_ROSTER_ROWS:
        raise CourseAdminError(f"单次最多处理 {MAX_ROSTER_ROWS} 行")
    by_username, by_no, by_name = _indexes(db)
    member_ids = {
        uid for (uid,) in db.query(UserCourse.user_id).filter(UserCourse.course_id == course.course_id).all()
    }
    seen: set[str] = set()
    ready = already = skipped = 0
    out = []
    for rec in records:
        user, reason = _resolve_student(rec, by_username, by_no, by_name)
        item = {
            "rowIndex": rec["rowIndex"],
            "username": (user.username if user else "") or rec.get("username") or rec.get("identifier") or "",
            "name": (user.name if user else "") or rec.get("name") or "",
            "studentNo": (user.student_no if user else "") or rec.get("studentNo") or "",
            "className": (user.class_name if user else "") or "",
            "userId": user.user_id if user else "",
            "status": "skipped",
            "reason": reason,
        }
        if user is None:
            skipped += 1
        elif user.user_id in seen:
            skipped += 1
            item["reason"] = "名单里重复出现"
        elif user.user_id in member_ids:
            already += 1
            item["status"] = "already"
            item["reason"] = "已在该课程中"
            seen.add(user.user_id)
        else:
            ready += 1
            item["status"] = "ready"
            item["reason"] = ""
            seen.add(user.user_id)
        out.append(item)
    return {
        "courseId": course.course_id,
        "total": len(out),
        "ready": ready,
        "already": already,
        "skipped": skipped,
        "rows": out,
    }


def commit_roster(db: Session, course_id: str, rows: list) -> dict:
    preview = classify_roster(db, course_id, rows)
    ready_ids = [row["userId"] for row in preview["rows"] if row["status"] == "ready" and row["userId"]]
    users = []
    if ready_ids:
        found = {
            u.user_id: u
            for u in db.query(User).filter(User.user_id.in_(ready_ids), User.role == "student").all()
        }
        users = [found[uid] for uid in ready_ids if uid in found]
    course = _get_course(db, course_id)
    bound = bind_users(db, course, users)
    return {
        "courseId": course.course_id,
        "bound": bound["bound"],
        "already": preview["already"],
        "skipped": preview["skipped"],
    }


def read_roster_upload(filename: str, content: bytes) -> list:
    name = filename or "upload"
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in ("xlsx", "docx", "csv", "txt"):
        raise CourseAdminError("不支持的文件类型。请上传 .xlsx / .docx / .csv / .txt")
    if len(content) > 10 * 1024 * 1024:
        raise CourseAdminError("文件过大（上限 10MB）")
    try:
        rows = rows_from_upload(name, content)
    except Exception as exc:  # 解析库抛出的都转成页面能看懂的原因
        raise CourseAdminError(f"文件解析失败：{exc}") from exc
    if not rows:
        raise CourseAdminError("文件内容为空或无法识别有效数据行")
    return rows
