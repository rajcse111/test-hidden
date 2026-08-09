import asyncio
import json
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

import httpx
from app.core.config import Settings
from loguru import logger
from openai import AsyncOpenAI


class LlmProvider(ABC):
    @abstractmethod
    async def stream(self, messages: list[dict[str, str]], model: str) -> AsyncIterator[str]:
        raise NotImplementedError


class OpenAIProvider(LlmProvider):
    def __init__(self, api_key: str | None):
        self.client = AsyncOpenAI(api_key=api_key) if api_key else None

    async def stream(self, messages: list[dict[str, str]], model: str) -> AsyncIterator[str]:
        if self.client is None:
            yield "OpenAI API key is not configured. Add OPENAI_API_KEY or switch to Ollama local mode."
            return
        stream = await self.client.chat.completions.create(model=model, messages=messages, stream=True)
        async for event in stream:
            token = event.choices[0].delta.content
            if token:
                yield token


class OpenRouterProvider(LlmProvider):
    def __init__(self, api_key: str | None):
        self.client = AsyncOpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key) if api_key else None

    async def stream(self, messages: list[dict[str, str]], model: str) -> AsyncIterator[str]:
        if self.client is None:
            yield "OpenRouter API key is not configured. Add OPENROUTER_API_KEY or switch providers."
            return
        stream = await self.client.chat.completions.create(model=model, messages=messages, stream=True)
        async for event in stream:
            token = event.choices[0].delta.content
            if token:
                yield token


class AnthropicProvider(LlmProvider):
    _BASE_URL = "https://api.anthropic.com/v1/messages"
    _VERSION = "2023-06-01"

    def __init__(self, api_key: str | None):
        self.api_key = api_key

    async def stream(self, messages: list[dict[str, str]], model: str) -> AsyncIterator[str]:
        if not self.api_key:
            yield "Anthropic API key is not configured. Add ANTHROPIC_API_KEY to .env."
            return
        # Anthropic separates system prompt from the messages array
        system = next((m["content"] for m in messages if m["role"] == "system"), None)
        user_messages = [m for m in messages if m["role"] != "system"]
        payload: dict = {"model": model, "messages": user_messages, "max_tokens": 800, "stream": True}
        if system:
            payload["system"] = system
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                self._BASE_URL,
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": self._VERSION,
                    "content-type": "application/json",
                },
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = json.loads(line.removeprefix("data: "))
                    if data.get("type") == "content_block_delta":
                        text = data.get("delta", {}).get("text", "")
                        if text:
                            yield text


class OllamaProvider(LlmProvider):
    def __init__(self, host: str):
        self.host = host.rstrip("/")
        # read=None keeps streaming alive indefinitely; connect/write/pool timeouts
        # surface a fast error when Ollama is unreachable instead of hanging forever.
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=5.0, read=None, write=5.0, pool=5.0)
        )

    async def stream(self, messages: list[dict[str, str]], model: str) -> AsyncIterator[str]:
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "keep_alive": -1,
            "options": {"num_predict": 400, "num_ctx": 2048},
        }
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                async with self._client.stream("POST", f"{self.host}/api/chat", json=payload) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        data = json.loads(line)
                        content = data.get("message", {}).get("content")
                        if content:
                            yield content
                    return
            except (httpx.HTTPError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt == 2:
                    break
                await asyncio.sleep(0.25 * (2**attempt))
        if last_error:
            raise last_error


class GeminiProvider(LlmProvider):
    def __init__(self, api_key: str | None):
        self.api_key = api_key

    async def stream(self, messages: list[dict[str, str]], model: str) -> AsyncIterator[str]:
        if not self.api_key:
            yield "Gemini API key is not configured. Add GEMINI_API_KEY or switch providers."
            return
        prompt = "\n\n".join(message["content"] for message in messages)
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=None) as client:
                    async with client.stream(
                        "POST",
                        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent",
                        params={"key": self.api_key, "alt": "sse"},
                        json={"contents": [{"parts": [{"text": prompt}]}]},
                    ) as response:
                        if response.status_code == 429:
                            body = await response.aread()
                            logger.warning(f"Gemini 429 body: {body.decode()}")
                            wait = float(response.headers.get("Retry-After", 2**attempt))
                            last_error = httpx.HTTPStatusError(
                                "429 Too Many Requests", request=response.request, response=response
                            )
                            await asyncio.sleep(wait)
                            continue
                        response.raise_for_status()
                        async for line in response.aiter_lines():
                            if not line.startswith("data: "):
                                continue
                            data = json.loads(line.removeprefix("data: "))
                            parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                            for part in parts:
                                token = part.get("text")
                                if token:
                                    yield token
                        return
            except (httpx.HTTPError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt == 2:
                    break
                await asyncio.sleep(0.5 * (2**attempt))
        if last_error:
            yield f"Gemini error after 3 attempts: {last_error}. Check logs/backend.log for details."


class LlmOrchestrator:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.providers: dict[str, LlmProvider] = {
            "openai": OpenAIProvider(settings.openai_api_key),
            "anthropic": AnthropicProvider(settings.anthropic_api_key),
            "openrouter": OpenRouterProvider(settings.openrouter_api_key),
            "ollama": OllamaProvider(settings.ollama_host),
            "gemini": GeminiProvider(settings.gemini_api_key),
        }

    async def stream(self, provider: str, model: str, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        if self.settings.local_only and provider != "ollama":
            yield "Local-only mode is enabled. Switch provider to Ollama to avoid cloud calls."
            return
        selected = self.providers.get(provider)
        if selected is None:
            yield f"Unknown provider '{provider}'."
            return
        async for token in selected.stream(messages, model):
            yield token
