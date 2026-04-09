"""用户服务。"""

from __future__ import annotations

from app.core.exceptions import ResourceNotFoundError
from app.models.role import RoleName
from app.models.user import User


def get_primary_role(user: User) -> str:
    if not user.roles:
        return RoleName.USER.value
    role = user.roles[0].name
    return role.value if hasattr(role, "value") else str(role)


def serialize_user(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": get_primary_role(user),
        "status": user.status.value if hasattr(user.status, "value") else str(user.status),
        "created_at": user.created_at,
    }


class UserService:
    async def get_user_or_raise(self, db, user_repo, user_id: int) -> User:
        user = await user_repo.get_by_id(db, user_id)
        if not user:
            raise ResourceNotFoundError(message="用户不存在")
        return user


user_service = UserService()
