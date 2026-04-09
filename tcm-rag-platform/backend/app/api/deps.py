"""
FastAPI 依赖注入 — DB session / 当前用户 / 角色检查。
"""

from __future__ import annotations

from typing import Any, Callable

from fastapi import Depends, Header
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthenticationError, PermissionDeniedError
from app.core.security import decode_token
from app.db.session import async_session_factory


async def get_db() -> AsyncSession:  # type: ignore[misc]
    """每个请求获取一个异步 DB session，请求结束后自动关闭。"""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_current_user(
    authorization: str = Header(None, alias="Authorization"),
) -> dict[str, Any]:
    """从 Authorization: Bearer <token> 中解析当前用户信息。

    返回 JWT payload dict，至少包含 ``sub`` (user_id) 和 ``role``。
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise AuthenticationError(message="缺少或无效的 Authorization 头")
    token = authorization[7:]
    try:
        payload = decode_token(token)
    except JWTError:
        raise AuthenticationError(message="无效的令牌")
    if payload.get("type") != "access":
        raise AuthenticationError(message="令牌类型错误")
    return payload


def require_role(*allowed_roles: str) -> Callable:
    """返回一个 FastAPI 依赖，检查当前用户角色是否在允许列表中。

    用法::

        @router.get("/admin/dashboard", dependencies=[Depends(require_role("admin"))])
        async def admin_dashboard(): ...
    """

    async def _check_role(
        current_user: dict[str, Any] = Depends(get_current_user),
    ) -> dict[str, Any]:
        user_role = current_user.get("role", "")
        if user_role not in allowed_roles:
            raise PermissionDeniedError(message=f"需要角色: {', '.join(allowed_roles)}")
        return current_user

    return _check_role
