"""
agent_st.agent.config —— 原型配置的正式版桥接。
原型的 agent/config.py 在集成时改为从正式 Settings（backend/app/config.py）取值，
保证 LLM/EMBEDDING 密钥与数据路径统一管理，禁止硬编码绝对路径。
"""
from __future__ import annotations

from pathlib import Path

from ..settings_bridge import get_settings, refresh_settings  # noqa: F401

# 本文件位于 backend/app/agent_st/agent/config.py
AGENT_DIR = Path(__file__).resolve().parent
ROOT = AGENT_DIR.parent.parent          # backend/app
