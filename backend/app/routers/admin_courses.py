"""管理员课程管理：/admin/courses/*

只挂 require_admin。不改教师建课、学生凭邀请码入课，也不吃 X-Course-Id。
写操作的校验与落库都在 services.course_admin，这里只做请求包装。
"""
import io
from typing import List, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import require_admin
from ..schemas.common import ok, fail
from ..services.course_admin import (
    CourseAdminError,
    bind_classes,
    classify_roster,
    commit_roster,
    create_course,
    delete_course,
    list_classes,
    list_courses,
    list_members,
    read_roster_upload,
    unbind_classes,
    unbind_member,
    update_course,
)

router = APIRouter(
    prefix="/api/v1/admin",
    tags=["管理员课程"],
    dependencies=[Depends(require_admin)],
)


class CourseWrite(BaseModel):
    name: Optional[str] = None
    term: Optional[str] = None
    code: Optional[str] = None
    classNo: Optional[str] = None
    teacherUserId: Optional[str] = None


class ClassKeysBody(BaseModel):
    classKeys: List[str] = []


def _guard(fn):
    try:
        return ok(fn())
    except CourseAdminError as exc:
        return fail(exc.message, 400)


@router.get("/courses")
def admin_list_courses(db: Session = Depends(get_db)):
    items = list_courses(db)
    return ok({"total": len(items), "list": items})


@router.post("/courses")
def admin_create_course(body: CourseWrite, db: Session = Depends(get_db)):
    def run():
        data = create_course(
            db,
            name=body.name or "",
            term=body.term or "",
            code=body.code or "",
            class_no=body.classNo or "",
            teacher_user_id=body.teacherUserId or "",
        )
        db.commit()
        return data

    try:
        return ok(run())
    except CourseAdminError as exc:
        db.rollback()
        return fail(exc.message, 400)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        return fail(f"创建失败：{exc}", 500)


@router.get("/courses/roster/template")
def admin_roster_template():
    """选课名单模板。列：学号、姓名、用户名。学号或用户名至少填一个。"""
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["学号", "姓名", "用户名"])
    ws.append(["20230001", "张三", "s_zhangsan"])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    filename = quote("选课名单模板.xlsx")
    disposition = f"attachment; filename=roster_template.xlsx; filename*=UTF-8''{filename}"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": disposition},
    )


@router.put("/courses/{course_id}")
def admin_update_course(course_id: str, body: CourseWrite, db: Session = Depends(get_db)):
    try:
        # 请求体里出现的字段才更新。模型默认 None = 未传。
        data = update_course(
            db, course_id,
            name=body.name, term=body.term, code=body.code, class_no=body.classNo,
            teacher_user_id=body.teacherUserId,
        )
        db.commit()
        return ok(data)
    except CourseAdminError as exc:
        db.rollback()
        return fail(exc.message, 400)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        return fail(f"保存失败：{exc}", 500)


@router.delete("/courses/{course_id}")
def admin_delete_course(course_id: str, db: Session = Depends(get_db)):
    try:
        data = delete_course(db, course_id)
        db.commit()
        return ok(data)
    except CourseAdminError as exc:
        db.rollback()
        return fail(exc.message, 400)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        return fail(f"删除失败：{exc}", 500)


@router.get("/courses/{course_id}/members")
def admin_course_members(course_id: str, db: Session = Depends(get_db)):
    return _guard(lambda: list_members(db, course_id))


@router.delete("/courses/{course_id}/members/{user_id}")
def admin_unbind_member(course_id: str, user_id: str, db: Session = Depends(get_db)):
    try:
        data = unbind_member(db, course_id, user_id)
        db.commit()
        return ok(data)
    except CourseAdminError as exc:
        db.rollback()
        return fail(exc.message, 400)


@router.get("/courses/{course_id}/classes")
def admin_course_classes(course_id: str, db: Session = Depends(get_db)):
    return _guard(lambda: list_classes(db, course_id))


@router.post("/courses/{course_id}/bind-classes")
def admin_bind_classes(course_id: str, body: ClassKeysBody, db: Session = Depends(get_db)):
    try:
        data = bind_classes(db, course_id, body.classKeys)
        db.commit()
        return ok(data)
    except CourseAdminError as exc:
        db.rollback()
        return fail(exc.message, 400)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        return fail(f"绑定失败：{exc}", 500)


@router.post("/courses/{course_id}/unbind-classes")
def admin_unbind_classes(course_id: str, body: ClassKeysBody, db: Session = Depends(get_db)):
    try:
        data = unbind_classes(db, course_id, body.classKeys)
        db.commit()
        return ok(data)
    except CourseAdminError as exc:
        db.rollback()
        return fail(exc.message, 400)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        return fail(f"移出失败：{exc}", 500)


@router.post("/courses/{course_id}/roster/preview")
async def admin_roster_preview(
    course_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    content = await file.read()
    try:
        rows = read_roster_upload(file.filename or "", content)
        return ok(classify_roster(db, course_id, rows))
    except CourseAdminError as exc:
        return fail(exc.message, 400)


@router.post("/courses/{course_id}/roster/commit")
async def admin_roster_commit(
    course_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    content = await file.read()
    try:
        rows = read_roster_upload(file.filename or "", content)
        data = commit_roster(db, course_id, rows)
        db.commit()
        return ok(data)
    except CourseAdminError as exc:
        db.rollback()
        return fail(exc.message, 400)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        return fail(f"绑定失败：{exc}", 500)
