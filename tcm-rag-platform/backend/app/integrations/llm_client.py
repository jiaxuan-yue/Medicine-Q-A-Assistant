"""DashScope LLM API Client (qwen-max / qwen-plus)"""
from __future__ import annotations

import dashscope
from dashscope import Generation
from typing import AsyncGenerator
from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)


class LLMClient:
    def __init__(self):
        dashscope.api_key = settings.DASHSCOPE_API_KEY
        self.model = settings.LLM_MODEL
        self.rewrite_model = settings.LLM_REWRITE_MODEL
        self.timeout = settings.LLM_TIMEOUT

    # ── non-streaming ─────────────────────────────────────
    async def generate(self, messages: list[dict], model: str | None = None,
                       temperature: float = 0.7, max_tokens: int = 2000) -> str:
        """Non-streaming full response."""
        response = Generation.call(
            model=model or self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            result_format='message',
        )
        if response.status_code == 200:
            return response.output.choices[0].message.content
        raise Exception(f"LLM API error: {response.code} - {response.message}")

    async def chat(self, messages: list[dict], model: str | None = None,
                   temperature: float = 0.7, max_tokens: int = 2000) -> str:
        """Alias for generate() — non-streaming single response."""
        return await self.generate(messages, model=model,
                                   temperature=temperature, max_tokens=max_tokens)

    # ── streaming ─────────────────────────────────────────
    async def generate_stream(self, messages: list[dict], model: str | None = None,
                              temperature: float = 0.7, max_tokens: int = 2000) -> AsyncGenerator[str, None]:
        """Streaming response — yields incremental content strings."""
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
                raise Exception(f"LLM stream error: {response.code}")

    async def chat_stream(self, messages: list[dict], model: str | None = None,
                          temperature: float = 0.7, max_tokens: int = 2000) -> AsyncGenerator[str, None]:
        """Alias for generate_stream() — streaming response."""
        async for chunk in self.generate_stream(messages, model=model,
                                                temperature=temperature,
                                                max_tokens=max_tokens):
            yield chunk


llm_client = LLMClient()
