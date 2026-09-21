"""
智能体状态与知识库维护接口：/agent/*
- /agent/status            ：运行模式（live/demo）与模型信息
- /agent/ingest/stats      ：RAG 切片统计（teacher，按当前课程）
- /agent/ingest/bank|file  ：手动触发知识入库（teacher，写入当前课程）

课程隔离：所有写库端点都经 get_current_course_id 取值（含成员校验 403），
入库的切片一律带上该课程 ID —— 缺少它会写进默认演示课，前端永远访问不到。
"""
from pathlib import Path

from fastapi import APIRouter, Depends, UploadFile, File, Form
from sqlalchemy.orm import Session

from ..database import get_db
from ..middleware.auth import get_current_user
from ..dependencies import get_current_course_id
from ..schemas.common import ok, fail
from ..config import settings

router = APIRouter(prefix="/api/v1/agent", tags=["智能体状态"])


def _require_teacher(user):
    if getattr(user, "role", "") != "teacher":
        return False
    return True


@router.get("/status")
def agent_status(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    from ..agent_st.agent.llm import chat_available
    from ..agent_st.rag.embed import active_model_name

    live = chat_available()
    return ok({
        "mode": "live" if live else "demo",
        "model": settings.LLM_MODEL,
        "embeddingModel": active_model_name(),
        "flows": ["explain", "generate_items"],
        "hint": "" if live else "未配置 LLM_API_KEY，当前为演示模式（真实检索、无生成）",
    })


@router.get("/ingest/stats")
def ingest_stats(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    course_id: str = Depends(get_current_course_id),
):
    if not _require_teacher(user):
        return fail("仅教师可查看知识库统计", code=403)
    from ..agent_st.rag.store import ChunkStore
    from ..agent_st.rag.embed import active_model_name

    store = ChunkStore()
    return ok({
        "courseId": course_id,
        "chunks": store.count(course_id),
        "chunksAllCourses": store.count(),
        "byCourse": store.course_counts(),
        "sources": store.source_counts(course_id),
        "embeddingModels": store.embedding_model_counts(course_id),
        "activeEmbeddingModel": active_model_name(),
    })


@router.post("/ingest/bank")
def ingest_bank_route(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    course_id: str = Depends(get_current_course_id),
):
    """按**当前课程**的 questions 表重建题库切片（幂等）"""
    if not _require_teacher(user):
        return fail("仅教师可触发知识入库", code=403)
    from ..agent_st.rag.ingest import ingest_question_bank

    try:
        result = ingest_question_bank(course_id)
        return ok(result) if result.get("ok") else fail(result.get("error") or "入库失败")
    except Exception as exc:  # noqa: BLE001
        return fail(f"入库失败：{exc}")


@router.post("/ingest/file")
def ingest_file_route(
    file: UploadFile = File(...),
    chapterId: str = Form(""),
    kpIds: str = Form(""),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    course_id: str = Depends(get_current_course_id),
):
    """上传补充资料（pdf/pptx/txt/md）入**当前课程**的 RAG 库 —— teacher 运维入口

    chapterId / kpIds 可选：给了就按主库规范的结构 id 归属切片，
    由 `retrieve_chunks` 的 chapter_id / kp_id 过滤命中。
    """
    if not _require_teacher(user):
        return fail("仅教师可触发知识入库", code=403)
    from ..agent_st.rag import structure
    from ..agent_st.rag.ingest import ingest_path

    allowed = {".pdf", ".pptx", ".ppt", ".txt", ".md"}
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in allowed:
        return fail(f"不支持的文件类型：{suffix or '(无后缀)'}")
    chapter = chapterId.strip()
    if chapter and not structure.chapter_name_by_id(course_id, chapter):
        return fail(f"章节 {chapter} 不属于本课程", 400)
    kps = [k.strip() for k in (kpIds or "").split(",") if k.strip()]
    valid = structure.valid_kp_ids(course_id)
    bad = [k for k in kps if k not in valid]
    if bad:
        return fail(f"知识点不属于本课程：{bad}", 400)

    filename = Path(file.filename or "upload.bin").name
    dest_dir = settings.AGENT_DATA_DIR / "uploads" / course_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / filename
    try:
        with open(dest, "wb") as f:
            f.write(file.file.read())
        result = ingest_path(
            dest, course_id=course_id, source_key=f"manual/{filename}",
            chapter_id=chapter, kp_ids=kps,
        )
        return ok(result) if result.get("ok") else fail(result.get("error") or "入库失败")
    except Exception as exc:  # noqa: BLE001
        return fail(f"入库失败：{exc}")
