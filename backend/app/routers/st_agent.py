"""
智能体状态与知识库维护接口：/agent/*
- /agent/status            ：运行模式（live/demo）与模型信息
- /agent/ingest/stats      ：RAG 切片统计（教师/管理员，按当前课程）
- /agent/ingest/bank|file  ：手动触发知识入库（教师/管理员，写入当前课程）
- /agent/actions/{id}/approve|reject ：写操作审批闸门（P2c，教师/管理员）

课程隔离：所有写库端点都经 get_current_course_id 取值（含成员校验 403），
入库的切片一律带上该课程 ID —— 缺少它会写进默认演示课，前端永远访问不到。

角色闸门：入库类端点与写操作审批统一用 dependencies.require_role("teacher", "admin")，
与 /teacher、/analysis、/question、/intervention、/report 五个前缀同一套语义；
/agent/status 面向全部登录用户，不加闸门。逐个端点显式挂依赖，
而不是整个前缀 —— 避免「给 /agent 挂上闸门就把 status 也锁掉」。
"""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session

from ..database import get_db
from ..middleware.auth import get_current_user
from ..dependencies import get_current_course_id, require_role
from ..schemas.common import ok, fail
from ..config import settings

router = APIRouter(prefix="/api/v1/agent", tags=["智能体状态"])

# 教师或管理员可用（管理员与教师端前缀口径一致；学生一律 403）
require_ingest_role = require_role("teacher", "admin")


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
    _role=Depends(require_ingest_role),
    course_id: str = Depends(get_current_course_id),
):
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
    _role=Depends(require_ingest_role),
    course_id: str = Depends(get_current_course_id),
):
    """按**当前课程**的 questions 表重建题库切片（幂等）"""
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
    _role=Depends(require_ingest_role),
    course_id: str = Depends(get_current_course_id),
):
    """上传补充资料（pdf/pptx/txt/md）入**当前课程**的 RAG 库 —— 教师/管理员运维入口

    chapterId / kpIds 可选：给了就按主库规范的结构 id 归属切片，
    由 `retrieve_chunks` 的 chapter_id / kp_id 过滤命中。
    """
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


# ======================================================================
# 写操作审批闸门（P2c）：Agent 提出的写操作先落成「待批准动作」，
# 由用户在这里点确认后才真正执行。动作与状态都存放在 chat_messages.tool_log
# （JSON 文本列，不建表）。
# ======================================================================
def _load_action(store, user_id: str, course_id: str, action_id: str):
    """取出待批准动作；查不到一律 403。

    归属校验靠 `find_action` 的查询范围（只在当前用户 + 当前课程的会话里找）——
    别人的 action_id 根本查不到，也就不存在「越权读到它」的问题。
    """
    hit = store.find_action(user_id, course_id, action_id)
    if not hit:
        raise HTTPException(status_code=403, detail="该动作不存在，或不属于你的当前课程")
    return hit


@router.post("/actions/{action_id}/approve")
def approve_action(
    action_id: str,
    db: Session = Depends(get_db),
    user=Depends(require_ingest_role),
    course_id: str = Depends(get_current_course_id),
):
    """确认执行某个待批准动作。

    - 参数以 tool_log 里**落库的那份**为准，不信任前端回传的 args；
    - 执行走 registry.execute（角色 + 任务流双校验），并打上 approval_replay 标记，
      让写工具知道「构思/查重已在原轮校验过，本次只做结构校验与写入」；
    - 重复确认是幂等的：状态已是 executed 时直接返回上次结果，不再写一次。
    """
    from ..agent_st.agent.context import ToolContext
    from ..agent_st.agent.registry import TOOLS, execute, tool_ok
    from ..agent_st.agent.store import AgentStore

    store = AgentStore(user_id=user.user_id, course_id=course_id)
    message_id, action = _load_action(store, user.user_id, course_id, action_id)
    status = str(action.get("status") or "pending")

    if status == "executed":
        return ok({"actionId": action_id, "status": "executed", "idempotent": True,
                   "result": action.get("result") or {}})
    if status == "rejected":
        raise HTTPException(status_code=409, detail="该动作已被拒绝，不能再次执行")

    tool = str(action.get("tool") or "")
    spec = TOOLS.get(tool)
    if spec is None:
        raise HTTPException(status_code=400, detail=f"该动作引用的工具已不存在：{tool}")

    ctx = ToolContext(
        store=store,
        flow_id=spec.flows[0] if spec.flows else "generate_items",
        extra={"courseId": course_id, "role": (getattr(user, "role", "") or "").strip()},
        user_id=user.user_id,
    )
    ctx.turn["approval_replay"] = True
    result = execute(tool, dict(action.get("args") or {}), ctx)

    if not tool_ok(result):
        # 执行失败不改状态：动作仍留在待批准，用户可以重试或直接拒绝
        reason = ""
        if isinstance(result, dict):
            reason = result.get("error") or "；".join(result.get("errors") or []) or ""
        raise HTTPException(status_code=400, detail=f"执行失败：{reason or '未知原因'}")

    summary = {k: result.get(k) for k in ("draft_id", "status", "q_id", "errors")
               if isinstance(result, dict) and k in result}
    store.set_action_status(message_id, action_id, "executed", result=summary)
    return ok({
        "actionId": action_id, "status": "executed", "idempotent": False,
        "tool": tool, "result": summary,
        "message": "已执行：该题已写入你的草稿箱，可在「AI 出题与题库」里查看。",
    })


@router.post("/actions/{action_id}/reject")
def reject_action(
    action_id: str,
    db: Session = Depends(get_db),
    user=Depends(require_ingest_role),
    course_id: str = Depends(get_current_course_id),
):
    """拒绝某个待批准动作：只改状态，不产生任何副作用。"""
    from ..agent_st.agent.store import AgentStore

    store = AgentStore(user_id=user.user_id, course_id=course_id)
    message_id, action = _load_action(store, user.user_id, course_id, action_id)
    status = str(action.get("status") or "pending")

    if status == "rejected":
        return ok({"actionId": action_id, "status": "rejected", "idempotent": True})
    if status == "executed":
        raise HTTPException(status_code=409, detail="该动作已执行，不能再拒绝")

    store.set_action_status(message_id, action_id, "rejected")
    return ok({"actionId": action_id, "status": "rejected", "idempotent": False})
