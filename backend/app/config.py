"""
应用配置
"""
import os
import secrets
from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    # 项目根目录
    BASE_DIR: Path = Path(__file__).resolve().parent          # backend/app
    PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent  # backend
    # 前端目录（用于静态文件挂载）
    FRONTEND_DIR: Path = Path(__file__).resolve().parent.parent.parent

    # 数据库（SQLite，零配置）
    DATABASE_URL: str = f"sqlite:///{BASE_DIR}/data/course_agent.db"

    # JWT（生产环境务必通过环境变量 JWT_SECRET 设置强随机密钥）
    # 若未显式设置，则每次启动生成一个随机密钥（fail-secure，避免已知占位符被伪造令牌），
    # 但同时会在启动日志告警，提示生产环境应通过环境变量固定密钥。
    _jwt_secret_env = os.getenv("JWT_SECRET", "")
    JWT_SECRET: str = _jwt_secret_env if _jwt_secret_env else secrets.token_hex(32)
    JWT_SECRET_AUTO: bool = not bool(_jwt_secret_env)
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 天

    # 服务
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = False  # 生产环境关闭调试（关闭 SQL 日志与报错栈外泄）

    # CORS（生产环境通过环境变量 CORS_ORIGINS 设置，默认仅允许同源 127.0.0.1:8000）
    CORS_ORIGINS: str = os.getenv("CORS_ORIGINS", "http://127.0.0.1:8000,http://localhost:8000")

    model_config = {"env_file": ".env"}


settings = Settings()
