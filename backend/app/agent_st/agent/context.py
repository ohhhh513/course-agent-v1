from dataclasses import dataclass, field
from typing import Any
from threading import RLock

from app.agent_st.agent.store import AgentStore


@dataclass
class ToolContext:
    store: AgentStore
    flow_id: str
    extra: dict[str, Any] = field(default_factory=dict)
    turn: dict[str, Any] = field(default_factory=dict)
    user_id: str = ""              # 集成新增：草稿归属用户
    tool_log: list = field(default_factory=list)   # 集成新增：本轮工具调用日志
    turn_lock: Any = field(default_factory=RLock, repr=False, compare=False)  # SDK 并发工具共享本轮状态
