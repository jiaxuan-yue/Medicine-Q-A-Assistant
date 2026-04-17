"""MCP client for flash-calling the environment server over stdio."""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.logger import get_logger
from app.services.live_context_service import get_live_context_async

logger = get_logger(__name__)

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
except Exception:  # pragma: no cover - dependency may be absent before install
    ClientSession = None  # type: ignore[assignment]
    StdioServerParameters = None  # type: ignore[assignment]
    stdio_client = None  # type: ignore[assignment]


def _extract_tool_payload(result: Any) -> dict[str, Any]:
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        return structured

    content = getattr(result, "content", None) or []
    for item in content:
        text = getattr(item, "text", None)
        if isinstance(text, str):
            return {"environmental_context": text}
    return {}


def _has_environment_mcp_server() -> bool:
    try:
        return importlib.util.find_spec("mcp.server.fastmcp") is not None
    except ModuleNotFoundError:
        return False


async def flash_call_environment_mcp(preferred_location: dict[str, Any] | None = None) -> dict[str, Any]:
    """Spawn the MCP server over stdio, call get_live_context, then exit."""
    if not settings.LIVE_CONTEXT_ENABLED:
        return {}

    if (
        not settings.MCP_ENVIRONMENT_ENABLED
        or not ClientSession
        or not StdioServerParameters
        or not stdio_client
        or not _has_environment_mcp_server()
    ):
        logger.info("environment MCP disabled or unavailable, using direct live context fallback")
        return await get_live_context_async(preferred_location)

    backend_dir = Path(settings.BASE_DIR) / "backend"
    pythonpath = str(backend_dir)
    if os.environ.get("PYTHONPATH"):
        pythonpath = f"{pythonpath}{os.pathsep}{os.environ['PYTHONPATH']}"
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "app.services.environment_service"],
        env={
            **os.environ,
            "PYTHONPATH": pythonpath,
        },
    )

    try:
        async with asyncio.timeout(settings.LIVE_CONTEXT_TIMEOUT_SECONDS):
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    arguments = {"preferred_location": preferred_location} if preferred_location else {}
                    result = await session.call_tool("get_live_context", arguments=arguments)
                    payload = _extract_tool_payload(result)
                    if isinstance(payload, dict) and payload:
                        return payload
    except Exception as exc:
        logger.warning("environment MCP flash call failed, fallback to direct context: %s", exc)

    return await get_live_context_async(preferred_location)
