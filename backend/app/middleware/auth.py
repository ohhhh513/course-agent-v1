"""
JWT 鉴权中间件与依赖
"""
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import Depends, HTTPException, status, Request
from jose import JWTError, jwt
from passlib.context import CryptContext
from ..config import settings
from ..database import get_db
from sqlalchemy.orm import Session
from ..models.user import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_jwt(user_id: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    payload = {
        "sub": user_id,
        "role": role,
        "exp": expire,
        # jti：登出吊销用的一次性标识。没有它就无法在「不改密钥」的前提下
        # 让某个 token 提前失效（JWT 本身是无状态的）。
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_jwt(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return None


# ========== 登出吊销表（进程内） ==========
# 背景：JWT 无状态，退出登录若不主动作废，旧 token 在有效期内仍然能用
# （共用电脑上换人登录后，前一个人的身份还能被使用）。
# 这里维护 jti → 过期时间戳 的最小实现：
#   - /auth/logout 把当前 token 的 jti 记入；
#   - get_current_user 每次校验该 jti 是否已被吊销；
#   - 过期条目在写入/校验时惰性清理，不会无限增长。
# 已知限制（文档已标注）：仅当前进程有效 —— 进程重启后旧 token 重新可用；
# 多 worker / 多实例部署时各进程各有一份表，不共享。当前单进程 uvicorn 下
# 即「退出登录后旧 token 立刻不可用」。
_REVOKED_JTI: dict = {}


def _purge_revoked(now: Optional[float] = None) -> None:
    """惰性清理已自然过期的吊销记录"""
    now = time.time() if now is None else now
    for jti, exp in list(_REVOKED_JTI.items()):
        if not exp or exp <= now:
            _REVOKED_JTI.pop(jti, None)


def revoke_token(payload: Optional[dict]) -> bool:
    """把已解析的 JWT payload 记入吊销表；无 jti 的旧 token 无法吊销，返回 False"""
    if not payload:
        return False
    jti = payload.get("jti")
    if not jti:
        return False
    _purge_revoked()
    _REVOKED_JTI[str(jti)] = float(payload.get("exp") or 0)
    return True


def is_revoked(payload: Optional[dict]) -> bool:
    """该 payload（token）是否已被吊销"""
    if not payload:
        return False
    jti = payload.get("jti")
    if not jti:
        return False
    _purge_revoked()
    return str(jti) in _REVOKED_JTI


def _extract_token(request: Request) -> Optional[str]:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


def extract_token(request: Request) -> Optional[str]:
    """公开别名：供 /auth/logout 取当前请求携带的 token"""
    return _extract_token(request)


async def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    """FastAPI 依赖：从 JWT 解析当前登录用户"""
    token = _extract_token(request)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录或 token 缺失")
    payload = decode_jwt(token)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="token 无效或已过期")
    if is_revoked(payload):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录状态已失效，请重新登录")
    user = db.query(User).filter(User.user_id == payload["sub"]).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在")
    return user


async def require_teacher(
    user: User = Depends(get_current_user),
) -> User:
    """教师端依赖：非教师角色一律 403。

    挂在教师端 router 上（`APIRouter(dependencies=[Depends(require_teacher)])`），
    用于拦住「拿学生 token 直接调教师接口」这一类越权 —— 在此之前
    `/teacher/*`、`/analysis/*`、`/question/*`、`/intervention/*`、`/report/*`
    只校验了登录状态，没校验角色。
    """
    if getattr(user, "role", "") != "teacher":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅教师可访问该接口")
    return user


async def get_current_user_optional(
    request: Request,
    db: Session = Depends(get_db),
) -> Optional[User]:
    """可选鉴权（请求有 token 就解析，没有不报错）"""
    token = _extract_token(request)
    if not token:
        return None
    payload = decode_jwt(token)
    if not payload:
        return None
    if is_revoked(payload):
        return None
    return db.query(User).filter(User.user_id == payload["sub"]).first()
