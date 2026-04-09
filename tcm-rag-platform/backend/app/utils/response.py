"""统一响应封装。"""

from __future__ import annotations

from typing import Any

from app.core.logger import trace_id_ctx


def success_response(data: Any = None, message: str = "ok", code: int = 0) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "data": data,
        "trace_id": trace_id_ctx.get("-"),
    }
