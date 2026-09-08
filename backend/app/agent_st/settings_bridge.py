"""
settings_bridge —— 把正式系统的 Settings 适配成原型 agent.config.Settings 的字段形状。
原型模块统一经 agent_st.agent.config.get_settings() 取配置，此处是唯一桥接点。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..config import settings as app_settings


@dataclass
class AgentSettings:
    """字段名与原型 agent/config.py.Settings 保持一致（小写下划线）"""
    llm_base_url: str
    llm_api_key: str
    llm_model: str

    embedding_base_url: str
    embedding_api_key: str
    embedding_model: str

    bank_path: Path
    data_dir: Path
    rag_db_path: Path
    agent_db_path: Path          # 不再使用独立 agent.db，保留字段兼容原型代码
    drafts_dir: Path

    min_retrieve_score: float
    retrieve_top_k: int
    max_steps: int
    off_topic_score: float

    extra: dict = field(default_factory=dict)


@dataclass
class _Bridge:
    """惰性代理：每次访问属性都从正式 settings 读取（支持环境变量热更新测试）"""
    _cache: AgentSettings | None = None

    def _build(self) -> AgentSettings:
        data_dir = Path(app_settings.AGENT_DATA_DIR)
        return AgentSettings(
            llm_base_url=app_settings.LLM_BASE_URL,
            llm_api_key=app_settings.LLM_API_KEY,
            llm_model=app_settings.LLM_MODEL,
            embedding_base_url=app_settings.EMBEDDING_BASE_URL,
            embedding_api_key=app_settings.EMBEDDING_API_KEY,
            embedding_model=app_settings.EMBEDDING_MODEL,
            bank_path=Path(app_settings.ST_BANK_PATH),
            data_dir=data_dir,
            rag_db_path=Path(app_settings.RAG_DB_PATH),
            agent_db_path=data_dir / "agent.db",
            drafts_dir=Path(app_settings.ST_DRAFTS_DIR),
            min_retrieve_score=app_settings.MIN_RETRIEVE_SCORE,
            retrieve_top_k=app_settings.RETRIEVE_TOP_K,
            max_steps=app_settings.AGENT_MAX_STEPS,
            off_topic_score=app_settings.OFF_TOPIC_SCORE,
        )

    def refresh(self) -> AgentSettings:
        self._cache = self._build()
        self._cache.data_dir.mkdir(parents=True, exist_ok=True)
        self._cache.drafts_dir.mkdir(parents=True, exist_ok=True)
        self._cache.bank_path.parent.mkdir(parents=True, exist_ok=True)
        return self._cache

    def get(self) -> AgentSettings:
        if self._cache is None:
            return self.refresh()
        return self._cache

    def __getattr__(self, name: str):
        return getattr(self.get(), name)


_bridge = _Bridge()


def get_settings() -> AgentSettings:
    """兼容原型 agent.config.get_settings() 的调用方式"""
    return _bridge.get()


def refresh_settings() -> AgentSettings:
    """强制重建（测试间隔离用）"""
    return _bridge.refresh()
