"""协作式停止信号和短期任务所有权（仅内存，不写数据库）。

聊天停止按会话 ID 标记；智能出题停止按随机任务 ID 标记，并绑定发起教师及课程。
底层模型流可注册关闭回调，批量草稿则通过任务锁确保停止已生效后不再写入。
"""
from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any


class Stopped(Exception):
    """内部信号：本轮已被用户停止，属于正常收尾。"""


_lock = threading.Lock()
_cancelled: set[str] = set()
_aborters: dict[str, Callable[[], Any]] = {}
_tasks: dict[str, tuple[str, str]] = {}
_task_locks: dict[str, threading.Lock] = {}


def _key(value: str) -> str:
    return str(value or "").strip()


def register_task(task_id: str, user_id: str, course_id: str) -> bool:
    """登记一个教师出题任务，避免其他用户或课程停止该任务。"""
    key = _key(task_id)
    if not key:
        return False
    with _lock:
        if key in _tasks:
            return False
        _cancelled.discard(key)
        _tasks[key] = (str(user_id or ""), str(course_id or ""))
        _task_locks[key] = threading.Lock()
    return True


def unregister_task(task_id: str) -> None:
    """释放任务归属、停止标记和并发控制锁。"""
    key = _key(task_id)
    if not key:
        return
    with _lock:
        _tasks.pop(key, None)
        _task_locks.pop(key, None)
        _cancelled.discard(key)
        _aborters.pop(key, None)


def request_task(task_id: str, user_id: str, course_id: str) -> bool:
    """只允许任务发起者在同一课程中请求停止。"""
    key = _key(task_id)
    with _lock:
        owner = _tasks.get(key)
        task_lock = _task_locks.get(key)
    if not owner or owner != (str(user_id or ""), str(course_id or "")) or not task_lock:
        return False

    # 与批量草稿提交串行化：若提交先取得锁，它会先完成并作为已保存草稿保留；
    # 若停止先取得锁，之后的提交会检测到取消标记并被拦截。
    with task_lock:
        with _lock:
            if _tasks.get(key) != owner:
                return False
            _cancelled.add(key)
            aborter = _aborters.get(key)
    _invoke_aborter(aborter)
    return True


def request(session_id: str) -> None:
    """请求停止会话生成，并尽量立即关闭当前上游模型流。"""
    key = _key(session_id)
    if not key:
        return
    with _lock:
        _cancelled.add(key)
        aborter = _aborters.get(key)
    _invoke_aborter(aborter)


def is_requested(session_id: str) -> bool:
    key = _key(session_id)
    if not key:
        return False
    with _lock:
        return key in _cancelled


def clear(session_id: str) -> None:
    """清除聊天会话上一轮的停止标记。"""
    key = _key(session_id)
    if key:
        with _lock:
            _cancelled.discard(key)


def register_aborter(key: str, aborter: Callable[[], Any]) -> bool:
    """登记当前上游流的关闭回调；若已停止则立即关闭并返回 False。"""
    normalized = _key(key)
    if not normalized:
        return True
    with _lock:
        cancelled = normalized in _cancelled
        if not cancelled:
            _aborters[normalized] = aborter
    if cancelled:
        _invoke_aborter(aborter)
        return False
    return True


def unregister_aborter(key: str, aborter: Callable[[], Any] | None = None) -> None:
    normalized = _key(key)
    if not normalized:
        return
    with _lock:
        current = _aborters.get(normalized)
        if current is not None and (aborter is None or current is aborter):
            _aborters.pop(normalized, None)


def run_if_active(task_id: str, action: Callable[[], Any]) -> tuple[bool, Any]:
    """在任务未取消的同一临界区执行不可撤销写入。"""
    key = _key(task_id)
    with _lock:
        task_lock = _task_locks.get(key)
        registered = key in _tasks
    if not key:
        return True, action()
    if not registered or not task_lock:
        return False, None
    with task_lock:
        with _lock:
            if key not in _tasks or key in _cancelled:
                return False, None
        return True, action()


def _invoke_aborter(aborter: Callable[[], Any] | None) -> None:
    if not aborter:
        return
    try:
        aborter()
    except Exception:  # 关闭流失败时仍由协作式检查点完成收尾。
        pass
