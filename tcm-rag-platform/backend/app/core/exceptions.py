"""
统一异常体系 + 全局异常处理器。

错误码分段:
  20xxx — 认证 / 授权
  30xxx — 文档处理
  40xxx — 检索
  50xxx — 知识图谱
  60xxx — LLM
  70xxx — 评测
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.logger import get_logger, trace_id_ctx

logger = get_logger(__name__)


# ── 基类 ──────────────────────────────────────────────────

class AppException(Exception):
    """应用统一异常基类。"""

    def __init__(
        self,
        code: int = 10000,
        message: str = "服务内部错误",
        http_status: int = 500,
        data: object = None,
    ) -> None:
        self.code = code
        self.message = message
        self.http_status = http_status
        self.data = data
        super().__init__(message)


# ── 通用 10xxx ───────────────────────────────────────────

class ResourceNotFoundError(AppException):
    def __init__(self, message: str = "资源不存在", code: int = 10004):
        super().__init__(code=code, message=message, http_status=404)


class ConflictError(AppException):
    def __init__(self, message: str = "资源冲突", code: int = 10005):
        super().__init__(code=code, message=message, http_status=409)


class BadRequestError(AppException):
    def __init__(self, message: str = "请求参数错误", code: int = 10006):
        super().__init__(code=code, message=message, http_status=400)


# ── 认证 / 授权 20xxx ────────────────────────────────────

class AuthenticationError(AppException):
    def __init__(self, message: str = "认证失败", code: int = 20001):
        super().__init__(code=code, message=message, http_status=401)


class TokenExpiredError(AppException):
    def __init__(self, message: str = "令牌已过期"):
        super().__init__(code=20002, message=message, http_status=401)


class PermissionDeniedError(AppException):
    def __init__(self, message: str = "权限不足"):
        super().__init__(code=20003, message=message, http_status=403)


# ── 文档处理 30xxx ────────────────────────────────────────

class DocumentNotFoundError(AppException):
    def __init__(self, message: str = "文档不存在"):
        super().__init__(code=30001, message=message, http_status=404)


class UnsupportedFormatError(AppException):
    def __init__(self, message: str = "不支持的文件格式"):
        super().__init__(code=30002, message=message, http_status=400)


class IngestError(AppException):
    def __init__(self, message: str = "文档解析入库失败"):
        super().__init__(code=30003, message=message, http_status=500)


# ── 检索 40xxx ────────────────────────────────────────────

class RetrievalError(AppException):
    def __init__(self, message: str = "检索失败", code: int = 40001):
        super().__init__(code=code, message=message, http_status=500)


class RetrievalTimeoutError(AppException):
    def __init__(self, message: str = "检索超时"):
        super().__init__(code=40002, message=message, http_status=504)


class RerankerError(AppException):
    def __init__(self, message: str = "重排序失败"):
        super().__init__(code=40003, message=message, http_status=500)


# ── 知识图谱 50xxx ────────────────────────────────────────

class GraphError(AppException):
    def __init__(self, message: str = "图谱操作失败", code: int = 50001):
        super().__init__(code=code, message=message, http_status=500)


class GraphConnectionError(AppException):
    def __init__(self, message: str = "图数据库连接失败"):
        super().__init__(code=50002, message=message, http_status=503)


class GraphQueryError(AppException):
    def __init__(self, message: str = "图谱查询失败"):
        super().__init__(code=50003, message=message, http_status=500)


# ── LLM 60xxx ────────────────────────────────────────────

class LLMError(AppException):
    def __init__(self, message: str = "LLM 调用失败", code: int = 60001):
        super().__init__(code=code, message=message, http_status=500)


class LLMTimeoutError(AppException):
    def __init__(self, message: str = "LLM 调用超时"):
        super().__init__(code=60002, message=message, http_status=504)


class LLMQuotaError(AppException):
    def __init__(self, message: str = "LLM 配额不足"):
        super().__init__(code=60003, message=message, http_status=429)


# ── 评测 70xxx ────────────────────────────────────────────

class EvalError(AppException):
    def __init__(self, message: str = "评测失败", code: int = 70001):
        super().__init__(code=code, message=message, http_status=500)


class EvalDataError(AppException):
    def __init__(self, message: str = "评测数据异常"):
        super().__init__(code=70002, message=message, http_status=400)


# ── 全局异常处理器注册 ────────────────────────────────────

def register_exception_handlers(app: FastAPI) -> None:
    """在 FastAPI app 上注册全局异常处理器。"""

    @app.exception_handler(AppException)
    async def _app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
        logger.warning("AppException code=%s message=%s", exc.code, exc.message)
        return JSONResponse(
            status_code=exc.http_status,
            content={
                "code": exc.code,
                "message": exc.message,
                "data": exc.data,
                "trace_id": trace_id_ctx.get("-"),
            },
        )

    @app.exception_handler(Exception)
    async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception: %s", exc)
        return JSONResponse(
            status_code=500,
            content={
                "code": 10000,
                "message": "服务内部错误",
                "data": None,
                "trace_id": trace_id_ctx.get("-"),
            },
        )
