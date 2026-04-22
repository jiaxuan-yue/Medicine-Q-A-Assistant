"""Redis-backed chat session caches."""

from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.integrations.redis_client import delete_pattern, get_json, set_json


class SessionCacheService:
    def __init__(self) -> None:
        self._prefix = settings.REDIS_CACHE_PREFIX

    def _session_list_key(self, user_id: int, page: int, size: int) -> str:
        return f"{self._prefix}:chat:user:{user_id}:sessions:page:{page}:size:{size}"

    def _message_list_key(self, user_id: int, session_id: str) -> str:
        return f"{self._prefix}:chat:user:{user_id}:session:{session_id}:messages"

    def _history_key(self, user_id: int, session_id: str, limit: int) -> str:
        return f"{self._prefix}:chat:user:{user_id}:session:{session_id}:history:{limit}"

    async def get_session_list(
        self,
        *,
        user_id: int,
        page: int,
        size: int,
    ) -> tuple[list[dict[str, Any]], int] | None:
        payload = await get_json(self._session_list_key(user_id, page, size))
        if not isinstance(payload, dict):
            return None
        items = payload.get("items")
        total = payload.get("total")
        if not isinstance(items, list) or not isinstance(total, int):
            return None
        return items, total

    async def set_session_list(
        self,
        *,
        user_id: int,
        page: int,
        size: int,
        items: list[dict[str, Any]],
        total: int,
    ) -> None:
        await set_json(
            self._session_list_key(user_id, page, size),
            {"items": items, "total": total},
            settings.SESSION_CACHE_TTL_SECONDS,
        )

    async def get_message_list(
        self,
        *,
        user_id: int,
        session_id: str,
    ) -> list[dict[str, Any]] | None:
        payload = await get_json(self._message_list_key(user_id, session_id))
        return payload if isinstance(payload, list) else None

    async def set_message_list(
        self,
        *,
        user_id: int,
        session_id: str,
        items: list[dict[str, Any]],
    ) -> None:
        await set_json(
            self._message_list_key(user_id, session_id),
            items,
            settings.SESSION_CACHE_TTL_SECONDS,
        )

    async def get_conversation_history(
        self,
        *,
        user_id: int,
        session_id: str,
        limit: int,
    ) -> list[dict[str, str]] | None:
        payload = await get_json(self._history_key(user_id, session_id, limit))
        return payload if isinstance(payload, list) else None

    async def set_conversation_history(
        self,
        *,
        user_id: int,
        session_id: str,
        limit: int,
        history: list[dict[str, str]],
    ) -> None:
        await set_json(
            self._history_key(user_id, session_id, limit),
            history,
            settings.SESSION_CACHE_TTL_SECONDS,
        )

    async def invalidate_session(self, *, user_id: int, session_id: str) -> None:
        await delete_pattern(f"{self._prefix}:chat:user:{user_id}:session:{session_id}:*")
        await delete_pattern(f"{self._prefix}:chat:user:{user_id}:sessions:*")

    async def invalidate_user_sessions(self, *, user_id: int) -> None:
        await delete_pattern(f"{self._prefix}:chat:user:{user_id}:sessions:*")


session_cache_service = SessionCacheService()
