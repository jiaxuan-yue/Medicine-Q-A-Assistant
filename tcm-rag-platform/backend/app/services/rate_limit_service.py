"""Redis-backed intelligent rate limiting."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass

from starlette.requests import Request

from app.core.config import settings
from app.core.logger import get_logger
from app.core.security import decode_token
from app.integrations.redis_client import get_redis_client

logger = get_logger(__name__)

_SKIP_PATHS = ("/health", "/docs", "/redoc", "/openapi.json")


@dataclass(slots=True)
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    retry_after: int
    scope: str
    identity: str


class RateLimitService:
    def __init__(self) -> None:
        self._prefix = settings.REDIS_CACHE_PREFIX

    async def evaluate(self, request: Request) -> RateLimitResult:
        if not settings.RATE_LIMIT_ENABLED or request.method.upper() == "OPTIONS":
            return RateLimitResult(True, 0, 0, 0, "bypass", "bypass")
        if any(request.url.path.startswith(path) for path in _SKIP_PATHS):
            return RateLimitResult(True, 0, 0, 0, "bypass", "bypass")

        redis_client = get_redis_client()
        if redis_client is None:
            return RateLimitResult(True, 0, 0, 0, "disabled", "redis-unavailable")

        identity, role = self._resolve_identity(request)
        scope, minute_limit = self._resolve_policy(request, role)
        if minute_limit <= 0:
            return RateLimitResult(True, 0, 0, 0, scope, identity)

        burst_window = max(1, settings.RATE_LIMIT_BURST_WINDOW_SECONDS)
        minute_window = max(1, settings.RATE_LIMIT_WINDOW_SECONDS)
        burst_limit = self._resolve_burst_limit(minute_limit, minute_window, burst_window)
        now_ts = int(time.time())

        minute_count = await self._hit_bucket(
            identity=identity,
            scope=scope,
            now_ts=now_ts,
            window_seconds=minute_window,
        )
        burst_count = await self._hit_bucket(
            identity=identity,
            scope=scope,
            now_ts=now_ts,
            window_seconds=burst_window,
        )

        if burst_count > burst_limit:
            retry_after = self._seconds_until_window_reset(now_ts, burst_window)
            logger.warning(
                "rate limit blocked (burst): scope=%s identity=%s path=%s count=%d limit=%d",
                scope,
                identity,
                request.url.path,
                burst_count,
                burst_limit,
            )
            return RateLimitResult(False, minute_limit, 0, retry_after, scope, identity)

        if minute_count > minute_limit:
            retry_after = self._seconds_until_window_reset(now_ts, minute_window)
            logger.warning(
                "rate limit blocked (minute): scope=%s identity=%s path=%s count=%d limit=%d",
                scope,
                identity,
                request.url.path,
                minute_count,
                minute_limit,
            )
            return RateLimitResult(False, minute_limit, 0, retry_after, scope, identity)

        remaining = max(0, minute_limit - minute_count)
        return RateLimitResult(True, minute_limit, remaining, 0, scope, identity)

    def _resolve_identity(self, request: Request) -> tuple[str, str]:
        authorization = request.headers.get("Authorization", "")
        if authorization.startswith("Bearer "):
            token = authorization[7:]
            try:
                payload = decode_token(token)
                subject = str(payload.get("sub") or "").strip()
                if subject:
                    return f"user:{subject}", str(payload.get("role") or "user")
            except Exception:
                logger.debug("rate limit token parse failed")

        client_host = request.client.host if request.client else "unknown"
        forwarded_for = request.headers.get("X-Forwarded-For", "").split(",", 1)[0].strip()
        ip = forwarded_for or client_host
        return f"ip:{ip}", "anonymous"

    def _resolve_policy(self, request: Request, role: str) -> tuple[str, int]:
        path = request.url.path
        api_prefix = settings.API_V1_PREFIX

        if path.startswith(f"{api_prefix}/chats") and path.endswith("/stream"):
            return "qa", settings.RATE_LIMIT_QA
        if path.startswith(f"{api_prefix}/admin") or role == "admin":
            return "admin", settings.RATE_LIMIT_ADMIN
        if path.startswith(f"{api_prefix}/auth/"):
            return "auth", settings.RATE_LIMIT_AUTH
        return "user", settings.RATE_LIMIT_USER

    def _resolve_burst_limit(
        self,
        minute_limit: int,
        minute_window: int,
        burst_window: int,
    ) -> int:
        expected = math.ceil(minute_limit * burst_window / max(1, minute_window))
        return max(3, min(minute_limit, expected + 1))

    async def _hit_bucket(
        self,
        *,
        identity: str,
        scope: str,
        now_ts: int,
        window_seconds: int,
    ) -> int:
        redis_client = get_redis_client()
        if redis_client is None:
            return 0

        bucket = now_ts // window_seconds
        key = f"{self._prefix}:ratelimit:{scope}:{identity}:w{window_seconds}:b{bucket}"
        try:
            count = int(await redis_client.incr(key))
            if count == 1:
                await redis_client.expire(key, window_seconds + 1)
            return count
        except Exception as exc:
            logger.warning("Redis 限流计数失败 key=%s: %s", key, exc)
            return 0

    @staticmethod
    def _seconds_until_window_reset(now_ts: int, window_seconds: int) -> int:
        return max(1, window_seconds - (now_ts % window_seconds))


rate_limit_service = RateLimitService()
