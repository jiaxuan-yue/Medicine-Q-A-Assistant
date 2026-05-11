import asyncio
import fnmatch
import time

from starlette.requests import Request

from app.integrations.redis_client import set_redis_client
from app.services.rate_limit_service import rate_limit_service
from app.services.session_cache_service import session_cache_service


class FakeRedis:
    def __init__(self):
        self._values: dict[str, str] = {}
        self._expires_at: dict[str, float] = {}

    def _purge_expired(self) -> None:
        now = time.time()
        expired_keys = [
            key
            for key, expires_at in self._expires_at.items()
            if expires_at <= now
        ]
        for key in expired_keys:
            self._values.pop(key, None)
            self._expires_at.pop(key, None)

    async def ping(self) -> bool:
        return True

    async def aclose(self) -> None:
        return None

    async def get(self, key: str):
        self._purge_expired()
        return self._values.get(key)

    async def set(self, key: str, value: str, ex: int | None = None):
        self._values[key] = value
        if ex:
            self._expires_at[key] = time.time() + ex
        else:
            self._expires_at.pop(key, None)
        return True

    async def delete(self, *keys: str):
        deleted = 0
        for key in keys:
            if key in self._values:
                deleted += 1
            self._values.pop(key, None)
            self._expires_at.pop(key, None)
        return deleted

    async def incr(self, key: str):
        self._purge_expired()
        current = int(self._values.get(key, "0"))
        current += 1
        self._values[key] = str(current)
        return current

    async def expire(self, key: str, seconds: int):
        if key in self._values:
            self._expires_at[key] = time.time() + seconds
            return True
        return False

    async def scan_iter(self, match: str | None = None):
        self._purge_expired()
        for key in list(self._values.keys()):
            if match is None or fnmatch.fnmatch(key, match):
                yield key


def _build_request(path: str, method: str = "POST") -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": method,
            "path": path,
            "raw_path": path.encode("utf-8"),
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 9000),
            "server": ("testserver", 80),
            "scheme": "http",
        }
    )


def test_session_cache_roundtrip_and_invalidation():
    async def _run() -> None:
        fake_redis = FakeRedis()
        set_redis_client(fake_redis)

        try:
            items = [{"session_id": "s1", "title": "会话 1"}]
            messages = [{"id": "m1", "role": "user", "content": "你好"}]
            history = [{"role": "user", "content": "你好"}]

            await session_cache_service.set_session_list(
                user_id=1,
                page=1,
                size=20,
                items=items,
                total=1,
            )
            await session_cache_service.set_message_list(
                user_id=1,
                session_id="s1",
                items=messages,
            )
            await session_cache_service.set_conversation_history(
                user_id=1,
                session_id="s1",
                limit=6,
                history=history,
            )

            assert await session_cache_service.get_session_list(user_id=1, page=1, size=20) == (items, 1)
            assert await session_cache_service.get_message_list(user_id=1, session_id="s1") == messages
            assert (
                await session_cache_service.get_conversation_history(
                    user_id=1,
                    session_id="s1",
                    limit=6,
                )
                == history
            )

            await session_cache_service.invalidate_session(user_id=1, session_id="s1")

            assert await session_cache_service.get_session_list(user_id=1, page=1, size=20) is None
            assert await session_cache_service.get_message_list(user_id=1, session_id="s1") is None
            assert (
                await session_cache_service.get_conversation_history(
                    user_id=1,
                    session_id="s1",
                    limit=6,
                )
                is None
            )
        finally:
            set_redis_client(None)

    asyncio.run(_run())


def test_rate_limit_blocks_high_frequency_stream_requests():
    async def _run() -> None:
        fake_redis = FakeRedis()
        set_redis_client(fake_redis)

        try:
            request = _build_request("/api/v1/chats/session-1/stream")

            first = await rate_limit_service.evaluate(request)
            second = await rate_limit_service.evaluate(request)
            third = await rate_limit_service.evaluate(request)
            blocked = await rate_limit_service.evaluate(request)

            assert first.allowed is True
            assert second.allowed is True
            assert third.allowed is True
            assert blocked.allowed is False
            assert blocked.scope == "qa"
            assert blocked.retry_after >= 1
        finally:
            set_redis_client(None)

    asyncio.run(_run())
