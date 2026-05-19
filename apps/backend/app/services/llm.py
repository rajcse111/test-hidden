import asyncio
import json
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

import httpx
from app.core.config import Settings
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


class OllamaProvider(LlmProvider):
    def __init__(self, host: str):
        self.host = host.rstrip("/")
        self._client = httpx.AsyncClient(timeout=None)

    async def stream(self, messages: list[dict[str, str]], model: str) -> AsyncIterator[str]:
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "keep_alive": -1,
            "options": {"num_predict": 800},
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
        # Kept isolated so the optional Gemini SDK can be added without changing callers.
        prompt = "\n\n".join(message["content"] for message in messages)
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent",
                params={"key": self.api_key, "alt": "sse"},
                json={"contents": [{"parts": [{"text": prompt}]}]},
            ) as response:
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


class LlmOrchestrator:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.providers: dict[str, LlmProvider] = {
            "openai": OpenAIProvider(settings.openai_api_key),
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
