"""协作式「停止生成」标记（内存态，不落库）。

链路：前端点「停止」→ 调 `POST /ai/chat/stop` 或 `/admin/agent/chat/stop` 置标记
→ `run_turn` 在流式循环里轮询该标记，提前收尾并**把已经流出的部分**作为本轮回答落库。

两种收敛方式（双保险）：
1. **主动中断底层流**：deltas 经 `llm.complete_stream` 的回调进来，回调里发现标记
   就抛 `Stopped` —— 直接展开生成器、关闭上游 HTTP 流，不再继续消耗 token；
2. **轮询兜底**：模型长时间没有 delta（例如纯思考阶段）时，循环里的检查点也能停下。

实现约定：单进程内存集合即可（本服务单 worker 运行）；键 = chat session_id，
每轮开始前 `clear()`，避免上一轮的停止标记误伤下一轮。
注意：`AGENT_RUNTIME=sdk`（OpenAI Agents SDK 运行层）暂未接入该机制 ——
该运行层非默认，启用时「停止」只作用于前端（不等生成结束），服务端会跑完本轮。
"""
from __future__ import annotations

import threading


class Stopped(Exception):
    """内部信号：本轮被用户停止（属正常收尾，不是错误）。"""


_lock = threading.Lock()
_cancelled: set[str] = set()


def _key(session_id: str) -> str:
    return str(session_id or "").strip()


def request(session_id: str) -> None:
    """请求停止某个会话当前正在进行的生成。"""
    key = _key(session_id)
    if key:
        with _lock:
            _cancelled.add(key)


def is_requested(session_id: str) -> bool:
    key = _key(session_id)
    if not key:
        return False
    with _lock:
        return key in _cancelled


def clear(session_id: str) -> None:
    """清掉标记（每轮开始时调用，防止旧标记误伤新一轮）。"""
    key = _key(session_id)
    if key:
        with _lock:
            _cancelled.discard(key)
