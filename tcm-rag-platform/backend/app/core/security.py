"""
安全工具 — JWT 令牌签发 / 验证 + 密码哈希。
"""

from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings

# ── 密码哈希 ──────────────────────────────────────────────


def password_hash(plain: str) -> str:
    """将明文密码哈希为 bcrypt 字符串。"""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """验证明文密码与哈希值是否匹配。"""
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


# ── JWT 令牌 ──────────────────────────────────────────────

def _create_token(data: dict[str, Any], expires_delta: timedelta) -> str:
    to_encode = data.copy()
    to_encode["exp"] = datetime.now(timezone.utc) + expires_delta
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_access_token(
    subject: str | int,
    extra: dict[str, Any] | None = None,
) -> str:
    """签发 access_token。

    Parameters
    ----------
    subject : 用户唯一标识（通常为 user_id）。
    extra   : 需要写入 payload 的附加字段，如 role。
    """
    payload: dict[str, Any] = {"sub": str(subject), "type": "access"}
    if extra:
        payload.update(extra)
    return _create_token(payload, timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))


def create_refresh_token(
    subject: str | int,
    extra: dict[str, Any] | None = None,
) -> str:
    """签发 refresh_token。"""
    payload: dict[str, Any] = {"sub": str(subject), "type": "refresh"}
    if extra:
        payload.update(extra)
    return _create_token(payload, timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS))


def decode_token(token: str) -> dict[str, Any]:
    """解码并验证 JWT。

    Raises
    ------
    JWTError
        当 token 无效或已过期时抛出。
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload
    except JWTError:
        raise
