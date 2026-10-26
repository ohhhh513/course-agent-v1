"""管理员班级管理；删除仅发生在明确确认后的写请求中。"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_admin
from app.schemas.common import ok
from app.services import class_admin
from app.services.chat_attachments import delete_chat_attachments

router = APIRouter(prefix="/api/v1/admin/classes", tags=["管理员班级"],
                   dependencies=[Depends(require_admin)])


class ClassBody(BaseModel):
    name: str = Field(min_length=1, max_length=64)


class StudentSelection(BaseModel):
    userIds: list[str] = Field(min_length=1, max_length=class_admin.MAX_CLASS_SELECTION)


class DeleteClassBody(BaseModel):
    revision: str = Field(min_length=64, max_length=64)


def commit(db, operation):
    try:
        result = operation()
        db.commit()
        return ok(result)
    except Exception:
        db.rollback()
        raise


@router.get("")
def list_classes(keyword: str = "", db: Session = Depends(get_db)):
    rows = class_admin.list_classes(db, keyword)
    return ok({"list": rows, "total": len(rows)})


@router.post("")
def create_class(body: ClassBody, db: Session = Depends(get_db)):
    return commit(db, lambda: class_admin.create_class(db, body.name))


@router.get("/{class_id}/students")
def students(class_id: str, db: Session = Depends(get_db)):
    return ok(class_admin.members(db, class_id))


@router.post("/{class_id}/students")
def assign_students(class_id: str, body: StudentSelection, db: Session = Depends(get_db)):
    return commit(db, lambda: class_admin.assign_students(db, class_id, body.userIds))


@router.get("/{class_id}/delete-preview")
def delete_preview(class_id: str, db: Session = Depends(get_db)):
    return ok(class_admin.deletion_preview(db, class_id))


def remove(db, operation):
    try:
        result, attachment_ids = operation()
        db.commit()
    except Exception:
        db.rollback()
        raise
    delete_chat_attachments(attachment_ids)
    return ok(result)


@router.post("/{class_id}/students/batch-delete")
def delete_students(class_id: str, body: StudentSelection, db: Session = Depends(get_db),
                    admin=Depends(require_admin)):
    return remove(db, lambda: class_admin.delete_students(db, class_id, admin.user_id, body.userIds))


@router.delete("/{class_id}")
def delete_class(class_id: str, body: DeleteClassBody, db: Session = Depends(get_db),
                 admin=Depends(require_admin)):
    return remove(db, lambda: class_admin.delete_students(db, class_id, admin.user_id, revision=body.revision))
