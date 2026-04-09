"""通用响应模型。"""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel

from app.core.logger import trace_id_ctx

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    code: int = 0
    message: str = "success"
    data: T
    trace_id: str


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    size: int


def success_response(data: object, message: str = "success") -> dict[str, object]:
    """返回统一成功响应。"""
    return {
        "code": 0,
        "message": message,
        "data": data,
        "trace_id": trace_id_ctx.get("-"),
    }
