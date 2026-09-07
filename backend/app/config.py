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

    # ===== 智能体 agent_st（题库 / 智能解析 / 智能出题，源自 tmp_ST_problem_model 集成）=====
    # Chat Completions（OpenAI 兼容）；未填 KEY 时进入演示模式（真实检索、不访问外网）
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "deepseek-chat")
    # Embeddings；留空 KEY 时用本地哈希向量（local-hash-256）
    EMBEDDING_BASE_URL: str = os.getenv("EMBEDDING_BASE_URL", "")
    EMBEDDING_API_KEY: str = os.getenv("EMBEDDING_API_KEY", "")
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "bge-m3")

    # 数据目录（全部相对项目根推导，禁止硬编码绝对路径）
    AGENT_DATA_DIR: Path = BASE_DIR / "data" / "st"
    ST_BANK_PATH: Path = AGENT_DATA_DIR / "st_bank" / "after_class.json"
    RAG_DB_PATH: Path = AGENT_DATA_DIR / "rag.db"
    ST_DRAFTS_DIR: Path = AGENT_DATA_DIR / "drafts"

    # 检索与编排参数
    MIN_RETRIEVE_SCORE: float = 0.12
    RETRIEVE_TOP_K: int = 6
    AGENT_MAX_STEPS: int = 6
    # 越界判定阈值：主题不确定且不像课程问题时，检索最高分低于该值即视为越界
    # （生活类问题对课程切片的混合检索分通常 < 0.3，课程问题一般 > 0.4）
    OFF_TOPIC_SCORE: float = 0.28

    # .env 与本文件同目录（backend/app/.env），兼容 backend/.env 与环境变量
    model_config = {"env_file": (str(BASE_DIR / ".env"), ".env")}


settings = Settings()
