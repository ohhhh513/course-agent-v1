"""教师试卷管理；草稿使用题目快照，发布时将自出或修改题正式写入题库。"""
from datetime import datetime, timezone
import json
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_course_id, require_teacher
from app.middleware.auth import get_current_user
from app.models.intervention import TeacherClassDashboard
from app.services.exam_papers import (
    DATA_TYPE, normalize_paper, publish_question_snapshots, score_units,
)
from app.schemas.common import ok

router = APIRouter(prefix="/api/v1/teacher/exams", tags=["教师试卷"],
                   dependencies=[Depends(require_teacher)])


class SavePaper(BaseModel):
    title: str = Field(default="", max_length=120)
    totalScore: float = 100
    scoreMode: str = "auto"
    items: list[dict] = Field(default_factory=list, max_length=200)
    revision: int = 0
    publish: bool = False


class PublishPaper(BaseModel):
    revision: int


def own_query(db, user, course_id):
    return db.query(TeacherClassDashboard).filter(
        TeacherClassDashboard.data_type == DATA_TYPE,
        func.json_extract(TeacherClassDashboard.data_json, "$.userId") == user.user_id,
        func.json_extract(TeacherClassDashboard.data_json, "$.courseId") == course_id,
    )


def own_paper(db, user, course_id, paper_id):
    row = own_query(db, user, course_id).filter(TeacherClassDashboard.data_key == paper_id).first()
    if row is None:
        raise HTTPException(404, "试卷不存在或无权访问")
    return row, json.loads(row.data_json)


def describe(db, course_id, paper, *, detail=True):
    try:
        _, issues = normalize_paper(db, course_id, paper, paper)
    except (ValueError, TypeError, KeyError) as exc:
        # 目录调整后保留可读快照，并让教师在编辑器内修正归属再发布。
        issues = [str(exc)]
    result = dict(paper)
    result.update(ready=not issues, issues=issues,
                  questionCount=len(paper["items"]),
                  assignedScore=sum(score_units(i["score"]) for i in paper["items"]) / 10)
    if not detail:
        result.pop("items", None)
    return result


def save(db, user, course_id, req, row=None, previous=None):
    previous = previous or {}
    if row is not None and req.revision != previous["revision"]:
        raise HTTPException(409, "试卷已在其它窗口修改，请重新打开后再保存")
    if len(json.dumps(req.model_dump(), ensure_ascii=False)) > 2_000_000:
        raise HTTPException(400, "试卷内容过大")
    try:
        paper, issues = normalize_paper(db, course_id, req.model_dump(), previous)
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(400, str(exc)) from exc
    published = req.publish or previous.get("status") == "published"
    if published and issues:
        raise HTTPException(400, "暂不能发布：" + "；".join(issues[:8]))
    now = datetime.now(timezone.utc).isoformat()
    paper.update(paperId=previous.get("paperId") or "EP" + uuid.uuid4().hex[:24],
                 userId=user.user_id, courseId=course_id,
                 status="published" if published else "draft",
                 revision=previous.get("revision", 0) + 1,
                 createdAt=previous.get("createdAt", now), updatedAt=now)
    if published:
        try:
            publish_question_snapshots(db, course_id, paper)
        except (ValueError, TypeError, KeyError) as exc:
            db.rollback()
            raise HTTPException(400, str(exc)) from exc
    encoded = json.dumps(paper, ensure_ascii=False, allow_nan=False)
    if row is None:
        db.add(TeacherClassDashboard(class_id=None, data_type=DATA_TYPE,
                                     data_key=paper["paperId"], data_json=encoded))
    else:
        changed = db.query(TeacherClassDashboard).filter(
            TeacherClassDashboard.id == row.id,
            TeacherClassDashboard.data_json == row.data_json,
        ).update({TeacherClassDashboard.data_json: encoded,
                  TeacherClassDashboard.updated_at: datetime.now(timezone.utc).replace(tzinfo=None)},
                 synchronize_session=False)
        if changed != 1:
            db.rollback()
            raise HTTPException(409, "试卷已在其它窗口修改，请重新打开后再保存")
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    return ok(describe(db, course_id, paper))


@router.get("")
def list_papers(db: Session = Depends(get_db), user=Depends(get_current_user),
                course_id: str = Depends(get_current_course_id)):
    rows = own_query(db, user, course_id).order_by(TeacherClassDashboard.updated_at.desc()).all()
    items = [describe(db, course_id, json.loads(row.data_json), detail=False) for row in rows]
    return ok({"list": items, "total": len(items)})


@router.post("")
def create_paper(req: SavePaper, db: Session = Depends(get_db), user=Depends(get_current_user),
                 course_id: str = Depends(get_current_course_id)):
    return save(db, user, course_id, req)


@router.get("/{paper_id}")
def get_paper(paper_id: str, db: Session = Depends(get_db), user=Depends(get_current_user),
              course_id: str = Depends(get_current_course_id)):
    _, paper = own_paper(db, user, course_id, paper_id)
    return ok(describe(db, course_id, paper))


@router.put("/{paper_id}")
def update_paper(paper_id: str, req: SavePaper, db: Session = Depends(get_db),
                 user=Depends(get_current_user), course_id: str = Depends(get_current_course_id)):
    row, paper = own_paper(db, user, course_id, paper_id)
    return save(db, user, course_id, req, row, paper)


@router.post("/{paper_id}/publish")
def publish_paper(paper_id: str, req: PublishPaper, db: Session = Depends(get_db),
                  user=Depends(get_current_user), course_id: str = Depends(get_current_course_id)):
    row, paper = own_paper(db, user, course_id, paper_id)
    return save(db, user, course_id, SavePaper(**{**paper, "publish": True, "revision": req.revision}), row, paper)
