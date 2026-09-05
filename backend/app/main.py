"""
FastAPI 应用主入口
启动:  uvicorn app.main:app --host 0.0.0.0 --port 8000
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
import traceback

from .config import settings
from .database import init_db
from .schemas.common import fail

# ========== 创建 FastAPI 应用 ==========
app = FastAPI(
    title="课程智能体系统 API",
    version="v1",
    description=(
        "课程智能体（Course Agent）后端 —— 为前端 HTML 原型提供数据接口。\n"
        "AI Agent 开发部分（/ai/chat、/question/gen 等）已预留路由与数据结构，"
        "后续可在 `app/routers/ai.py` 和 `app/routers/teacher.py` 中接入 LLM。"
    ),
)

# ========== 中间件 ==========
# CORS：读取环境变量 CORS_ORIGINS，默认仅允许同源开发地址
_cors_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
if not _cors_origins:
    _cors_origins = ["http://127.0.0.1:8000", "http://localhost:8000"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ========== 全局异常处理 ==========
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    traceback.print_exc()
    return JSONResponse(
        status_code=200,  # 前端期望 HTTP 200 + 信封 code != 0
        content=fail(str(exc) or "服务器内部错误", code=500),
    )


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    return JSONResponse(status_code=404, content={"detail": "Not Found"})


# ========== 开发阶段禁用浏览器缓存（确保前端 JS 改动能立即生效）==========
from starlette.middleware.base import BaseHTTPMiddleware
class NoCacheMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        path = request.url.path.lower()
        if path.endswith(('.js', '.css', '.html')) or '/assets/' in path:
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response
app.add_middleware(NoCacheMiddleware)


# ========== 注册路由 ==========
from .routers.auth import router as auth_router
from .routers.course import router as course_router
from .routers.graph import router as graph_router
from .routers.student import router as student_router
from .routers.teacher import router as teacher_router, analysis_router, question_router
from .routers.ai import router as ai_router
from .routers.practice import router as practice_router
from .routers.intervention import intervention_router, report_router

app.include_router(auth_router)
app.include_router(course_router)
app.include_router(graph_router)
app.include_router(student_router)
app.include_router(teacher_router)
app.include_router(analysis_router)
app.include_router(question_router)
app.include_router(ai_router)
app.include_router(practice_router)
app.include_router(intervention_router)
app.include_router(report_router)


# ========== 健康检查 ==========
@app.get("/health")
def health():
    return {"status": "ok", "service": "course-agent-backend", "version": "v1"}


# ========== 挂载前端静态文件（开发联调用）==========
# 前端目录在项目根 course-agent/ 下，index.html 等直接暴露
import os
frontend_dir = str(settings.FRONTEND_DIR.resolve())
if os.path.exists(os.path.join(frontend_dir, "index.html")):
    # 挂载根路径下的静态文件（会匹配 index.html、student.html 等）
    # 注意：这是为了方便开发联调，正式部署建议前后端分离
    app.mount("/assets", StaticFiles(directory=os.path.join(frontend_dir, "assets")), name="assets")
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")


# ========== 启动事件 ==========
@app.on_event("startup")
def on_startup():
    # 安全自检：JWT 密钥为启动时自动生成的随机值（未通过环境变量固定）时给出明确告警
    if settings.JWT_SECRET_AUTO:
        print("[SECURITY WARNING] JWT_SECRET 未通过环境变量设置，已使用本次启动随机密钥；生产环境请通过环境变量 JWT_SECRET 设置固定强随机密钥，否则重启后旧令牌失效！", flush=True)
    # 初始化数据库表
    init_db()
    # 运行种子数据（如果表为空）
    from .seed.seed_data import run_seed
    run_seed()
