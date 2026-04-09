"""认证服务。"""

from __future__ import annotations

from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, AuthenticationError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    password_hash,
    verify_password,
)
from app.db.repositories.user_repo import user_repo
from app.models.role import RoleName
from app.schemas.auth import AuthTokens, RegisterRequest, LoginRequest
from app.schemas.user import UserProfile
from app.services.store import UserRecord, store


def serialize_user(user: UserRecord) -> UserProfile:
    return UserProfile(
        id=user.id,
        username=user.username,
        email=user.email,
        role=user.role,
        status=user.status,
        created_at=user.created_at,
    )


def issue_tokens(user: UserRecord) -> AuthTokens:
    return AuthTokens(
        access_token=create_access_token(user.id, extra={"role": user.role}),
        refresh_token=create_refresh_token(user.id, extra={"role": user.role}),
        token_type="bearer",
        user=serialize_user(user),
    )


def authenticate_user(username: str, password: str) -> AuthTokens:
    user = next((item for item in store.users.values() if item.username == username), None)
    if user is None or not verify_password(password, user.password_hash):
        raise AuthenticationError(message="用户名或密码错误")
    if user.status != "active":
        raise AuthenticationError(message="用户已被禁用")
    return issue_tokens(user)


def register_user(payload: RegisterRequest) -> AuthTokens:
    if any(item.username == payload.username for item in store.users.values()):
        raise AppException(code=20004, message="用户名已存在", http_status=400)
    if any(item.email == payload.email for item in store.users.values()):
        raise AppException(code=20005, message="邮箱已存在", http_status=400)
    user = store.add_user(
        username=payload.username,
        email=payload.email,
        password=payload.password,
        role="user",
    )
    return issue_tokens(user)


def refresh_tokens(refresh_token: str) -> AuthTokens:
    try:
        payload = decode_token(refresh_token)
    except JWTError as exc:
        raise AuthenticationError(message="无效的 refresh token") from exc
    if payload.get("type") != "refresh":
        raise AuthenticationError(message="令牌类型错误")
    user_id = int(payload.get("sub", 0))
    user = store.users.get(user_id)
    if user is None:
        raise AuthenticationError(message="用户不存在")
    return issue_tokens(user)


def resolve_access_token(token: str) -> UserProfile:
    try:
        payload = decode_token(token)
    except JWTError as exc:
        raise AuthenticationError(message="无效的访问令牌") from exc
    if payload.get("type") != "access":
        raise AuthenticationError(message="令牌类型错误")
    user_id = int(payload.get("sub", 0))
    user = store.users.get(user_id)
    if user is None:
        raise AuthenticationError(message="用户不存在")
    return serialize_user(user)


# ── DB-backed AuthService (used by API layer) ────────────────

class AuthService:
    """Async auth service that works with the database via user_repo."""

    async def register(self, db: AsyncSession, payload: RegisterRequest) -> dict:
        existing = await user_repo.get_by_username(db, payload.username)
        if existing:
            raise AppException(code=20004, message="用户名已存在", http_status=400)
        existing_email = await user_repo.get_by_email(db, payload.email)
        if existing_email:
            raise AppException(code=20005, message="邮箱已存在", http_status=400)
        hashed = password_hash(payload.password)
        user = await user_repo.create(
            db, username=payload.username, email=payload.email,
            password_hash=hashed, role_name=RoleName.USER,
        )
        tokens = self._issue_tokens(user)
        return tokens

    async def login(self, db: AsyncSession, payload: LoginRequest) -> dict:
        user = await user_repo.get_by_username(db, payload.username)
        if user is None or not verify_password(payload.password, user.password_hash):
            raise AuthenticationError(message="用户名或密码错误")
        if hasattr(user, "status") and getattr(user.status, "value", user.status) != "active":
            raise AuthenticationError(message="用户已被禁用")
        tokens = self._issue_tokens(user)
        return tokens

    async def refresh(self, db: AsyncSession, refresh_token: str) -> dict:
        try:
            payload = decode_token(refresh_token)
        except JWTError as exc:
            raise AuthenticationError(message="无效的 refresh token") from exc
        if payload.get("type") != "refresh":
            raise AuthenticationError(message="令牌类型错误")
        user_id = int(payload.get("sub", 0))
        user = await user_repo.get_by_id(db, user_id)
        if user is None:
            raise AuthenticationError(message="用户不存在")
        tokens = self._issue_tokens(user)
        return tokens

    @staticmethod
    def _issue_tokens(user) -> dict:
        from app.services.user_service import get_primary_role
        role = get_primary_role(user) if hasattr(user, "roles") else "user"
        return {
            "access_token": create_access_token(user.id, extra={"role": role}),
            "refresh_token": create_refresh_token(user.id, extra={"role": role}),
            "token_type": "bearer",
        }


auth_service = AuthService()
