"""
FastAPI 应用主入口
启动:  uvicorn app.main:app --host 0.0.0.0 --port 8000
       或项目根 start.bat

设计说明（精简启动 · 不再灌演示数据）：
  - 空库首次启动：只建表 + 创建管理员 admin/admin
  - 业务数据（教师/学生/课程/章节/资源/题目）一律由：
      管理员界面建号 → 教师建课 → API/教师端 UI 产生
  - 可选：环境变量 DEMO_SEED=1 时才执行旧 run_seed/bootstrap（仅本地演示）
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
import os
import traceback

from .config import settings
from .database import init_db
from .schemas.common import fail

# ========== 创建 FastAPI 应用 ==========
app = FastAPI(
    title="课程智能体系统 API",
    version="v1",
    description=(
        "课程智能体（Course Agent）后端。\n"
        "空库启动后请使用管理员账号 admin/admin 创建教师与学生，再由教师建课。"
    ),
)

# ========== 中间件 ==========
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
async def not_found_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=404, content={"detail": "Not Found"})


# ========== 开发阶段禁用浏览器缓存 ==========
from starlette.middleware.base import BaseHTTPMiddleware


class NoCacheMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        path = request.url.path.lower()
        if path.endswith((".js", ".css", ".html")) or "/assets/" in path:
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response


app.add_middleware(NoCacheMiddleware)


# ========== 注册路由 ==========
from .routers.auth import router as auth_router
from .routers.admin import router as admin_router
from .routers.course import router as course_router
from .routers.graph import router as graph_router
from .routers.student import router as student_router
from .routers.teacher import router as teacher_router, analysis_router, question_router
from .routers.ai import router as ai_router
from .routers.practice import router as practice_router
from .routers.intervention import intervention_router, report_router
from .routers.st_agent import router as st_agent_router

app.include_router(auth_router)
app.include_router(admin_router)
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
app.include_router(st_agent_router)


# ========== 健康检查 ==========
@app.get("/health")
def health():
    return {"status": "ok", "service": "course-agent-backend", "version": "v1"}


# ========== 资源文件服务（支持 HTTP Range） ==========
def _mount_resource_files(application, directory: str) -> None:
    """把 /resources 挂成「支持 Range 请求」的文件服务。

    背景：当前依赖的 starlette 0.38 里 StaticFiles/FileResponse 不处理 Range
    （Range 支持到 0.45+ 才有），响应里既没有 Accept-Ranges 也不会返回 206。
    浏览器因此把视频当「不可定位流」：无法 seek 到尚未下载的位置（记录点续播失效），
    每次观看都要从第 0 字节重新下载，表现就是「边下边播、进度记录不准」。
    这里只替换 /resources 这一个目录，其余静态目录仍走 StaticFiles。
    """
    import mimetypes
    from email.utils import formatdate
    from pathlib import Path as _Path
    from fastapi import Request
    from fastapi.responses import Response, StreamingResponse

    root = _Path(directory).resolve()
    CHUNK = 512 * 1024

    def _resolve(rel: str):
        p = (root / rel).resolve()
        if not p.is_relative_to(root):
            return None
        return p if p.is_file() else None

    def _iter_file(path, start: int, length: int):
        with open(path, "rb") as fh:
            fh.seek(start)
            remaining = length
            while remaining > 0:
                chunk = fh.read(min(CHUNK, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    @application.api_route("/resources/{file_path:path}", methods=["GET", "HEAD"],
                           include_in_schema=False)
    def resource_file(file_path: str, request: Request):
        path = _resolve(file_path)
        if path is None:
            return Response(status_code=404)
        st = path.stat()
        size = st.st_size
        headers = {
            "accept-ranges": "bytes",
            "content-type": mimetypes.guess_type(str(path))[0] or "application/octet-stream",
            "last-modified": formatdate(st.st_mtime, usegmt=True),
            "cache-control": "public, max-age=3600",
        }
        if request.method == "HEAD":
            headers["content-length"] = str(size)
            return Response(status_code=200, headers=headers)

        rng = request.headers.get("range")
        if rng and rng.lower().startswith("bytes="):
            spec = rng.split("=", 1)[1].split(",")[0].strip()
            try:
                if spec.startswith("-"):                       # 后缀范围：最后 N 字节
                    n = int(spec[1:])
                    start, end = max(0, size - n), size - 1
                else:
                    a, _, b = spec.partition("-")
                    start = int(a) if a else 0
                    end = int(b) if b else size - 1
            except ValueError:
                start, end = 0, size - 1
            if start >= size or end < start:
                return Response(status_code=416,
                                headers={**headers, "content-range": f"bytes */{size}"})
            end = min(end, size - 1)
            headers["content-range"] = f"bytes {start}-{end}/{size}"
            headers["content-length"] = str(end - start + 1)
            return StreamingResponse(_iter_file(path, start, end - start + 1),
                                     status_code=206, headers=headers)

        headers["content-length"] = str(size)
        return StreamingResponse(_iter_file(path, 0, size), status_code=200, headers=headers)


# ========== 挂载前端静态文件 ==========
frontend_dir = str(settings.FRONTEND_DIR.resolve())
if os.path.exists(os.path.join(frontend_dir, "index.html")):
    resources_dir = os.path.join(frontend_dir, "resources")
    if os.path.isdir(resources_dir):
        _mount_resource_files(app, resources_dir)
    app.mount("/assets", StaticFiles(directory=os.path.join(frontend_dir, "assets")), name="assets")
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")


def _ensure_admin() -> None:
    """确保管理员账号存在（admin/admin）。幂等；不覆盖已有密码。"""
    from pathlib import Path
    from .config import settings
    from .database import SessionLocal
    from .middleware.auth import hash_password
    from .models.user import User as _User

    db_file = Path(settings.BASE_DIR) / "data" / "course_agent.db"
    print(f"[admin] DATABASE_URL={settings.DATABASE_URL}", flush=True)
    print(f"[admin] db file exists={db_file.exists()} path={db_file}", flush=True)

    db = SessionLocal()
    try:
        # 确认连到的是 users 表（空表也应存在）
        count_users = db.query(_User).count()
        print(f"[admin] users count={count_users}", flush=True)
        if not db.query(_User).filter(_User.username == "admin").first():
            db.add(_User(
                user_id="ADMIN",
                username="admin",
                password=hash_password("admin"),
                name="系统管理员",
                role="admin",
                avatar_char="管",
            ))
            db.commit()
            print("[admin] 已创建管理员账号 admin/admin", flush=True)
        else:
            print("[admin] 管理员已存在，跳过创建", flush=True)
        # 回读校验
        again = db.query(_User).filter(_User.username == "admin").first()
        print(f"[admin] verify user_id={again.user_id if again else None} role={again.role if again else None}", flush=True)
    except Exception as e:
        db.rollback()
        print(f"[admin] 创建失败: {type(e).__name__}: {e}", flush=True)
        raise
    finally:
        db.close()


def _ensure_data_dirs() -> None:
    """保证运行所需本地目录存在（库文件、资源根目录）"""
    from pathlib import Path
    from .config import settings as _s

    # SQLite 数据目录（与 config.DATABASE_URL 指向同一位置）
    data_dir = Path(_s.BASE_DIR) / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    try:
        from .media_utils import RESOURCES_DIR, COVERS_DIR
        RESOURCES_DIR.mkdir(parents=True, exist_ok=True)
        COVERS_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(f"[dirs] 创建 resources 目录失败（可忽略）: {e}", flush=True)


# ========== 启动事件 ==========
@app.on_event("startup")
def on_startup():
    if settings.JWT_SECRET_AUTO:
        print(
            "[SECURITY WARNING] JWT_SECRET 未通过环境变量设置，已使用本次启动随机密钥；"
            "生产/团队协作请在 backend/app/.env 中设置固定 JWT_SECRET，否则重启后旧令牌失效！",
            flush=True,
        )

    _ensure_data_dirs()
    # 只建表，不灌演示业务数据
    init_db()
    print("[startup] 数据库表已就绪（空库可直接使用）", flush=True)

    # 管理员账号（失败不阻断启动，但必须打出日志）
    try:
        _ensure_admin()
    except Exception as e:
        print(f"[admin] 初始化管理员失败: {e}", flush=True)

    # 可选：本地演示模式（默认关闭）。设置 DEMO_SEED=1 才灌旧 seed/bootstrap。
    demo = (os.environ.get("DEMO_SEED", "") or "").strip().lower()
    if demo in ("1", "true", "yes", "on"):
        print("[startup] DEMO_SEED=1 → 执行演示 seed/bootstrap（仅本地演示）", flush=True)
        try:
            from .seed.seed_data import run_seed
            run_seed()
        except Exception as e:
            print(f"[seed] 跳过（{e}）", flush=True)
        try:
            from .services.bootstrap import bootstrap
            bootstrap()
        except Exception as e:
            print(f"[bootstrap] 跳过（{e}）", flush=True)
        # seed 可能插入过 admin；若仍无则再确保一次
        _ensure_admin()
    else:
        print(
            "[startup] 演示数据已关闭。请用 admin/admin 登录后创建教师与课程；"
            "本地演示可设 DEMO_SEED=1 后重启。",
            flush=True,
        )

    # 预警检测：空库无害；有数据则刷新
    try:
        from .services.alert_detector import detect_alerts
        from .database import SessionLocal

        _db = SessionLocal()
        try:
            print(f"[alert-detect] {detect_alerts(_db)}", flush=True)
        finally:
            _db.close()
    except Exception as e:
        print(f"[alert-detect] 跳过（{e}）", flush=True)
