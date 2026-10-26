"""管理员课程治理：建课 / 改课 / 删课，以及把学生绑进课程。

只使用现有列，不改表结构：
- 课程写 ``courses``（教学班号仍折进 ``code`` 的 ``代码||班号``）；
- 成员写 ``user_courses``；
- 学生入课后走与「凭邀请码加入」相同的 ``learning_path.sync_user``。

删除口径（2026-10-26 变更）：**只要课程内没有任何成员就可以删除**，删课时
一并清掉该课程的全部关联数据（题库 / 资源 / 图谱 / 学习记录 / 会话 / 报告等），
磁盘资源文件与向量库切片由调用方在 commit 之后调用 :func:`purge_course_assets` 清理。
课程里还有成员时拒绝删除，提示先移出成员。

退绑成员只删 ``user_courses`` 这一行；当课程退到**一个成员都不剩**时，
同时把 ``courses.owner_id`` 置空，课程回到「无负责人」状态（不再是「待指派原负责人」）。
"""
from __future__ import annotations

import random
import re
from collections import Counter, defaultdict
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.ai import ChatMessage, ChatSession
from app.models.agent_st import STQuestionDraft
from app.models.alert import Alert
from app.models.course import Course, Resource, ResourceProgress, pack_course_code, unpack_course_code
from app.models.graph import GraphLink, GraphNode, KpDetail, LearningPath
from app.models.intervention import Report, TeacherClassDashboard
from app.models.practice import AnswerRecord, PracticeSession
from app.models.question import Question
from app.models.tag import QuestionTagLink, ResourceTagLink, Tag
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

def _content_counters():
    """按 course_id 直接归属该课程的表，**删除顺序即本元组顺序**（先子后父）。

    - ``answer_records`` 同时引用 ``practice_sessions`` 与 ``questions``，必须先删；
    - ``resource_progress`` / ``resource_tags`` / ``question_tags`` 属于第二级，
      在 :func:`_purge_course_rows` 里按一级表的主键集合处理。

    这个元组只用于「删除」，不再用于判定「能不能删」—— 判据已改为成员数量。
    """
    return (
        ("答题记录", AnswerRecord, AnswerRecord.course_id),
        ("学习路径", LearningPath, LearningPath.course_id),
        ("练习", PracticeSession, PracticeSession.course_id),
        ("答疑会话", ChatSession, ChatSession.course_id),
        ("出题草稿", STQuestionDraft, STQuestionDraft.course_id),
        ("预警", Alert, Alert.course_id),
        ("资源", Resource, Resource.course_id),
        ("题目", Question, Question.course_id),
        ("图谱连线", GraphLink, GraphLink.course_id),
        ("图谱节点", GraphNode, GraphNode.course_id),
        ("知识点详情", KpDetail, KpDetail.course_id),
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


def member_count(db: Session, course_id: str) -> int:
    return int(db.query(func.count()).select_from(UserCourse)
               .filter(UserCourse.course_id == course_id).scalar() or 0)


def content_blockers(db: Session, course_id: str) -> list[tuple[str, int]]:
    """删除前的前置阻碍 —— 现在唯一的阻碍是「课程里还有成员」。

    保留函数名与返回形状（[(说明, 数量)]），调用方（智能助手 preview 工具）
    不用改契约；语义已从「有多少教学内容」变成「有多少成员」。
    """
    members = member_count(db, course_id)
    return [("成员", members)] if members else []


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
    # 负责人「更换 / 添加」都走这里：
    # - 课程无负责人（owner_id 为空，通常是成员被清空后退绑）→ 这是「添加」；
    # - 已有负责人且换了人 → 这是「更换」，旧负责人仍是成员（不会被自动移出）。
    # 两种情况都保证新负责人是课程成员，教师端才能看到这门课
    # （教师端权限校验按 user_courses.role_in_course == "teacher" 判定）。
    # 传空字符串 == 不修改负责人；要清空负责人只能通过退绑全部成员。
    if teacher_user_id is not None and teacher_user_id.strip() and teacher_user_id.strip() != course.owner_id:
        teacher = _teacher(db, teacher_user_id)
        course.owner_id = teacher.user_id
        course.teacher = teacher.name
        _ensure_teacher_member(db, teacher, course.course_id)
    return _one(db, course)


def _purge_course_rows(db: Session, course_id: str) -> dict[str, int]:
    """删除该课程的全部关联行，返回 {中文表名: 删除条数}。

    顺序严格「先子后父」，因为 ``PRAGMA foreign_keys = ON``：
    1. 先取一级表（按 course_id 归属）的主键集合；
    2. 删二级表（依赖一级主键的）：resource_progress / resource_tags / question_tags；
    3. 删 chat_messages（依赖 chat_sessions）；
    4. 删一级表本身；
    5. courses 行由 :func:`delete_course` 删除。
    """
    stats: dict[str, int] = {}

    # ① 一级表的主键集合（二级表删完前不能删它们）
    res_ids = [rid for (rid,) in db.query(Resource.res_id).filter(Resource.course_id == course_id).all()]
    q_ids = [qid for (qid,) in db.query(Question.q_id).filter(Question.course_id == course_id).all()]
    tag_ids = [tid for (tid,) in db.query(Tag.tag_id).filter(Tag.course_id == course_id).all()]
    session_ids = [sid for (sid,) in db.query(ChatSession.session_id)
                   .filter(ChatSession.course_id == course_id).all()]

    # ② 二级表：依赖 resources / questions / tags
    def _del(Model, column, ids, label):
        total = 0
        for start in range(0, len(ids), 500):      # SQLite 绑定变量上限，分批
            chunk = ids[start:start + 500]
            total += int(db.query(Model).filter(column.in_(chunk))
                         .delete(synchronize_session=False) or 0)
        if total:
            stats[label] = int(stats.get(label, 0)) + total

    _del(ResourceProgress, ResourceProgress.res_id, res_ids, "资源学习进度")
    _del(ResourceTagLink, ResourceTagLink.res_id, res_ids, "资源标签")
    _del(QuestionTagLink, QuestionTagLink.q_id, q_ids, "题目标签")
    # 反向：其它课程的资源/题目若挂了本课程的标签，也要先摘掉链接，标签才能删
    _del(ResourceTagLink, ResourceTagLink.tag_id, tag_ids, "跨课资源标签")
    _del(QuestionTagLink, QuestionTagLink.tag_id, tag_ids, "跨课题目标签")

    # ③ 消息依赖会话
    _del(ChatMessage, ChatMessage.session_id, session_ids, "会话消息")

    # ④ 一级表
    for label, model, column in _content_counters():
        n = int(db.query(model).filter(column == course_id)
                .delete(synchronize_session=False) or 0)
        if n:
            stats[label] = int(stats.get(label, 0)) + n

    # ⑤ 教师端聚合数据与学情报告：无外键，靠 JSON 里的 courseId 关联
    n = int(db.query(TeacherClassDashboard)
            .filter(func.json_extract(TeacherClassDashboard.data_json, "$.courseId") == course_id)
            .delete(synchronize_session=False) or 0)
    if n:
        stats["教师端记录"] = n

    n = int(db.query(Report)
            .filter(func.json_extract(Report.detail_json, "$.meta.courseId") == course_id)
            .delete(synchronize_session=False) or 0)
    if n:
        stats["学情报告"] = n

    return stats


def delete_course(db: Session, course_id: str) -> dict:
    """删除课程及其全部关联数据。

    前置条件（2026-10-26 起的口径）：**课程内不能有任何成员**。
    有成员时拒绝并提示先移出 —— 以前是「有教学内容就拒绝」，已反转。

    磁盘资源文件与向量库切片不在这里删（DB 事务不该管文件系统）：
    调用方在 commit 成功后调用 :func:`purge_course_assets`。
    """
    course = _get_course(db, course_id)
    members = member_count(db, course.course_id)
    if members:
        raise CourseAdminError(
            f"课程里还有 {members} 名成员，不能删除。请先移出成员，再删除课程。"
        )
    data = {
        "courseId": course.course_id,
        "name": course.name,
        "membersRemoved": 0,
        "purged": _purge_course_rows(db, course.course_id),
    }
    # 兜底：正常情况下成员数已为 0，这里只清掉可能的并发残留。
    removed = int(db.query(UserCourse).filter(UserCourse.course_id == course.course_id)
                  .delete(synchronize_session=False) or 0)
    if removed:
        data["membersRemoved"] = removed
    db.delete(course)
    db.flush()
    return data


def course_resource_urls(db: Session, course_id: str) -> dict[str, str]:
    """取该课程资源的 ``{res_id: url}`` —— 必须在删库**之前**调用。

    行删掉之后就查不到 URL，磁盘文件也就无法反解路径了，
    所以删除流程是：先取 URL 表 → 删库并 commit → 用 URL 表清磁盘/向量库。
    """
    return {
        rid: (url or "")
        for rid, url in db.query(Resource.res_id, Resource.url)
        .filter(Resource.course_id == course_id).all()
    }


def purge_course_assets(course_id: str, url_map: dict[str, str] | None = None) -> dict:
    """清理课程在 **数据库之外** 的痕迹：磁盘资源文件 + 向量库切片。

    必须在 :func:`delete_course` 的 DB commit **成功之后** 调用 ——
    顺序反过来的话，DB 回滚会留下「数据还在、文件没了」的坏状态。
    本函数自身失败不影响已提交的删除（只留孤儿文件，不破坏一致性），
    但会把错误放进返回值供调用方记录。
    """
    from app import media_utils

    out: dict = {"resourceFiles": 0, "ragChunks": 0, "errors": []}

    # ① 磁盘资源文件
    for url in (url_map or {}).values():
        try:
            path = media_utils.url_to_path(url)
            if path is None:
                continue
            if path.is_file():
                path.unlink(missing_ok=True)
                out["resourceFiles"] += 1
            media_utils.cleanup_empty_dirs(path)
        except Exception as exc:  # noqa: BLE001 - 单个文件失败不影响其它
            out["errors"].append(f"资源文件清理失败：{exc}")

    # ② 向量库切片
    try:
        from app.agent_st.rag.store import ChunkStore

        out["ragChunks"] = int(ChunkStore().delete_course(course_id) or 0)
    except Exception as exc:  # noqa: BLE001
        out["errors"].append(f"向量库清理失败：{exc}")

    return out


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

    负责人（owner）**可以退绑**：以前这里直接拒绝，而 update_course 又只能
    「换成另一位教师」、无法设为「无负责人」，于是出现死锁 —— 教师自己建的课
    （owner 就是他）既换不掉也移不出，管理端永远删不掉这门课。

    退绑只删 ``user_courses`` 这一行；**当课程退到没有任何成员时，
    ``courses.owner_id`` 一并置空**（见 :func:`_unbind`），课程回到「无负责人」状态。
    该教师此刻已不是该课成员，教师端权限校验（teacher.py 按
    ``user_courses.role_in_course == "teacher"`` 判定）会拒绝他 —— 这正是退绑生效的表现。
    """
    course = _get_course(db, course_id)
    user = db.query(User).filter(User.user_id == user_id).first()
    if user is None:
        raise CourseAdminError("账号不存在")
    return _unbind(db, course, [user])


def _unbind(db: Session, course: Course, users: list[User]) -> dict:
    """退绑一批成员，逐个删 user_courses 行。

    负责人也照删，并且**当课程退到没有任何成员时，把 ``courses.owner_id`` 一并置空**
    （2026-10-26 起）：课程回到「无负责人」状态，而不再是「待指派原负责人」。
    这样 admin 列表/编辑界面可以直接显示「无负责人」，教师端也不会再看到这门课。

    ``ownerUnbound`` 报告这次是否动到了负责人；``ownerCleared`` 报告 owner_id 是否已置空。
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

    # 删完这批之后课程里还剩几个人（autoflush 关闭，先 flush 让计数看到本次删除）
    db.flush()
    owner_cleared = False
    remaining = member_count(db, course.course_id)
    if remaining == 0 and (course.owner_id or "").strip():
        course.owner_id = ""
        course.teacher = ""
        owner_cleared = True
        db.flush()

    return {
        "courseId": course.course_id,
        "removed": removed,
        "ownerUnbound": owner_unbound,
        "ownerCleared": owner_cleared,
        "memberCount": remaining,
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
