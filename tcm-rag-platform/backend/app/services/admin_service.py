"""后台管理服务。"""

from __future__ import annotations

from app.core.exceptions import AppException
from app.schemas.common import PaginatedResponse
from app.schemas.user import UserProfile
from app.services.auth_service import serialize_user
from app.services.store import store

VALID_ROLES = {"admin", "reviewer", "operator", "user"}


def get_dashboard_stats() -> dict[str, float | int]:
    thumbs_up = sum(1 for item in store.feedbacks.values() if item.feedback_type == "thumbs_up")
    thumbs_down = sum(1 for item in store.feedbacks.values() if item.feedback_type == "thumbs_down")
    feedback_total = thumbs_up + thumbs_down

    return {
        "total_users": len(store.users),
        "total_documents": len(store.documents),
        "total_sessions": len(store.sessions),
        "total_messages": len(store.messages),
        "documents_pending_review": sum(1 for item in store.documents.values() if item.status == "pending"),
        "feedback_positive_rate": round(thumbs_up / feedback_total, 3) if feedback_total else 1.0,
    }


def list_users(page: int = 1, size: int = 10, role: str | None = None) -> PaginatedResponse[UserProfile]:
    users = list(store.users.values())
    if role:
        users = [item for item in users if item.role == role]
    users.sort(key=lambda item: item.created_at, reverse=True)
    total = len(users)
    start = max(page - 1, 0) * size
    end = start + size
    return PaginatedResponse(
        items=[serialize_user(item) for item in users[start:end]],
        total=total,
        page=page,
        size=size,
    )


def update_user_role(user_id: int, role: str) -> UserProfile:
    if role not in VALID_ROLES:
        raise AppException(code=20006, message="无效的角色", http_status=400)
    user = store.users.get(user_id)
    if user is None:
        raise AppException(code=20007, message="用户不存在", http_status=404)
    user.role = role
    return serialize_user(user)
