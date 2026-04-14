"""DashScope LLM API Client (qwen-max / qwen-plus)"""
from __future__ import annotations

import dashscope
from dashscope import Generation
from typing import Any, AsyncGenerator
from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)

_PLACEHOLDER_API_KEYS = {
    "",
    "your_dashscope_api_key",
    "sk-your-dashscope-api-key",
}


def _mask_secret(secret: str) -> str:
    secret = (secret or "").strip()
    if not secret:
        return "(empty)"
    if len(secret) <= 8:
        return f"{secret[:2]}***"
    return f"{secret[:4]}...{secret[-4:]}"


def _api_key_status(api_key: str) -> str:
    normalized = (api_key or "").strip()
    if not normalized:
        return "missing"
    if normalized in _PLACEHOLDER_API_KEYS:
        return "placeholder"
    return "configured"


class LLMClient:
    def __init__(self):
        dashscope.api_key = settings.DASHSCOPE_API_KEY
        self.model = settings.LLM_MODEL
        self.rewrite_model = settings.LLM_REWRITE_MODEL
        self.timeout = settings.LLM_TIMEOUT

    @staticmethod
    def _ensure_api_key() -> None:
        api_key = (settings.DASHSCOPE_API_KEY or "").strip()
        if api_key in _PLACEHOLDER_API_KEYS:
            raise RuntimeError(
                "DashScope API key 未配置，请在 .env 中设置有效的 DASHSCOPE_API_KEY"
            )

    @staticmethod
    def get_config_status() -> dict[str, Any]:
        api_key = settings.DASHSCOPE_API_KEY
        return {
            "provider": "DashScope",
            "api_key_status": _api_key_status(api_key),
            "api_key_masked": _mask_secret(api_key),
            "chat_model": settings.LLM_MODEL,
            "rewrite_model": settings.LLM_REWRITE_MODEL,
            "embedding_model": settings.EMBEDDING_MODEL,
            "reranker_model": settings.RERANKER_MODEL,
            "timeout_seconds": settings.LLM_TIMEOUT,
        }

    # ── non-streaming ─────────────────────────────────────
    async def generate(self, messages: list[dict], model: str | None = None,
                       temperature: float = 0.7, max_tokens: int = 2000) -> str:
        """Non-streaming full response."""
        self._ensure_api_key()
        response = Generation.call(
            model=model or self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            result_format='message',
        )
        if response.status_code == 200:
            return response.output.choices[0].message.content
        raise RuntimeError(f"LLM API error: {response.code} - {response.message}")

    async def chat(self, messages: list[dict], model: str | None = None,
                   temperature: float = 0.7, max_tokens: int = 2000) -> str:
        """Alias for generate() — non-streaming single response."""
        return await self.generate(messages, model=model,
                                   temperature=temperature, max_tokens=max_tokens)

    # ── streaming ─────────────────────────────────────────
    async def generate_stream(self, messages: list[dict], model: str | None = None,
                              temperature: float = 0.7, max_tokens: int = 2000) -> AsyncGenerator[str, None]:
        """Streaming response — yields incremental content strings."""
        self._ensure_api_key()
        responses = Generation.call(
            model=model or self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            result_format='message',
            stream=True,
            incremental_output=True,
        )
        for response in responses:
            if response.status_code == 200:
                content = response.output.choices[0].message.content
                if content:
                    yield content
            else:
                raise RuntimeError(f"LLM stream error: {response.code} - {response.message}")

    async def chat_stream(self, messages: list[dict], model: str | None = None,
                          temperature: float = 0.7, max_tokens: int = 2000) -> AsyncGenerator[str, None]:
        """Alias for generate_stream() — streaming response."""
        async for chunk in self.generate_stream(messages, model=model,
                                                temperature=temperature,
                                                max_tokens=max_tokens):
            yield chunk


llm_client = LLMClient()
