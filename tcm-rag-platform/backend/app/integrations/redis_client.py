"""Redis client helpers for caching and request control."""

from __future__ import annotations

import json
from typing import Any

import redis.asyncio as aioredis

from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)

_redis_client: aioredis.Redis | None = None


async def init_redis() -> aioredis.Redis | None:
    """Initialise a shared async Redis client."""
    global _redis_client

    try:
        _redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        await _redis_client.ping()
        logger.info("Redis 连接就绪: %s", settings.REDIS_URL)
    except Exception as exc:
        _redis_client = None
        logger.warning("Redis 不可用，继续以降级模式运行: %s", exc)
    return _redis_client


def get_redis_client() -> aioredis.Redis | None:
    return _redis_client


def set_redis_client(client: aioredis.Redis | None) -> None:
    """Testing hook for overriding the shared Redis client."""
    global _redis_client
    _redis_client = client


async def close_redis() -> None:
    global _redis_client
    if _redis_client is None:
        return
    await _redis_client.aclose()
    logger.info("Redis 连接已关闭")
    _redis_client = None


async def get_json(key: str) -> Any | None:
    client = get_redis_client()
    if client is None:
        return None
    try:
        raw = await client.get(key)
    except Exception as exc:
        logger.warning("Redis GET 失败 key=%s: %s", key, exc)
        return None
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Redis JSON 解析失败 key=%s", key)
        return None


async def set_json(key: str, value: Any, ttl_seconds: int | None = None) -> bool:
    client = get_redis_client()
    if client is None:
        return False
    try:
        payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        if ttl_seconds and ttl_seconds > 0:
            await client.set(key, payload, ex=ttl_seconds)
        else:
            await client.set(key, payload)
        return True
    except Exception as exc:
        logger.warning("Redis SET 失败 key=%s: %s", key, exc)
        return False


async def delete_pattern(pattern: str) -> int:
    client = get_redis_client()
    if client is None:
        return 0

    deleted = 0
    try:
        async for key in client.scan_iter(match=pattern):
            deleted += int(await client.delete(key) or 0)
    except Exception as exc:
        logger.warning("Redis 删除模式失败 pattern=%s: %s", pattern, exc)
        return 0
    return deleted
