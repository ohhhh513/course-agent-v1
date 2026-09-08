"""
智能体状态与知识库维护接口：/agent/*
- /agent/status            ：运行模式（live/demo）与模型信息
- /agent/ingest/stats      ：RAG 切片统计（teacher）
- /agent/ingest/bank|file  ：手动触发知识入库（teacher，可选运维入口）
"""
from pathlib import Path

from fastapi import APIRouter, Depends, UploadFile, File
from sqlalchemy.orm import Session

from ..database import get_db
from ..middleware.auth import get_current_user
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
):
    if not _require_teacher(user):
        return fail("仅教师可查看知识库统计", code=403)
    from ..agent_st.rag.store import ChunkStore
    from ..agent_st.rag.embed import active_model_name

    store = ChunkStore()
    return ok({
        "chunks": store.count(),
        "embeddingModels": store.embedding_model_counts(),
        "activeEmbeddingModel": active_model_name(),
    })


@router.post("/ingest/bank")
def ingest_bank_route(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """重建题库索引（幂等）——运维入口，避免依赖离线脚本也可用"""
    if not _require_teacher(user):
        return fail("仅教师可触发知识入库", code=403)
    from ..agent_st.rag.ingest import ingest_bank

    try:
        result = ingest_bank()
        return ok(result) if result.get("ok") else fail(result.get("error") or "入库失败")
    except Exception as exc:  # noqa: BLE001
        return fail(f"入库失败：{exc}")


@router.post("/ingest/file")
def ingest_file_route(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """上传补充资料（json/pdf/pptx/txt/md）入 RAG 库 —— teacher 运维入口"""
    if not _require_teacher(user):
        return fail("仅教师可触发知识入库", code=403)
    from ..agent_st.rag.ingest import ingest_path

    allowed = {".json", ".pdf", ".pptx", ".ppt", ".txt", ".md"}
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in allowed:
        return fail(f"不支持的文件类型：{suffix or '(无后缀)'}")
    dest_dir = settings.AGENT_DATA_DIR / "uploads"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / (file.filename or "upload.bin")
    try:
        with open(dest, "wb") as f:
            f.write(file.file.read())
        result = ingest_path(dest)
        return ok(result) if result.get("ok") else fail(result.get("error") or "入库失败")
    except Exception as exc:  # noqa: BLE001
        return fail(f"入库失败：{exc}")
