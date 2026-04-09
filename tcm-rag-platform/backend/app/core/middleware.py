"""
ASGI 中间件 — TraceID 注入 + 请求日志 / 耗时统计。
"""

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.logger import get_logger, trace_id_ctx

logger = get_logger(__name__)


class TraceIDMiddleware(BaseHTTPMiddleware):
    """为每个请求生成或传递 X-Trace-ID，并注入到 ContextVar。"""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        incoming_id = request.headers.get("X-Trace-ID")
        tid = incoming_id or uuid.uuid4().hex
        trace_id_ctx.set(tid)

        response = await call_next(request)
        response.headers["X-Trace-ID"] = tid
        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """记录请求方法、路径、状态码和耗时。"""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000

        logger.info(
            "%s %s -> %s (%.1f ms)",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
        return response
