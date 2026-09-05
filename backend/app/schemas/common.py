"""
统一响应信封工具
前端期望格式: { code: 0, message: "success", data: {...}, traceId: "..." }
"""
import uuid
from typing import Any, Optional


def ok(data: Any = None, trace_id: Optional[str] = None) -> dict:
    return {
        "code": 0,
        "message": "success",
        "data": data,
        "traceId": trace_id or "svc-" + uuid.uuid4().hex[:12],
    }


def fail(message: str, code: int = -1, trace_id: Optional[str] = None) -> dict:
    return {
        "code": code,
        "message": message,
        "data": None,
        "traceId": trace_id or "svc-" + uuid.uuid4().hex[:12],
    }


def list_response(items: list, total: int = None) -> dict:
    """列表类接口统一返回 { total, list }"""
    return {"total": total if total is not None else len(items), "list": items}
