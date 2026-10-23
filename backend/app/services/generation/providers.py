"""LLM provider abstraction.

Providers are selected with ``LLM_PROVIDER``:

* ``openai``    — any OpenAI-compatible Chat Completions API (OpenAI, Azure OpenAI, Groq,
                  Together, vLLM, **Ollama** at ``http://localhost:11434/v1``).
* ``anthropic`` — Anthropic Messages API.
* ``extractive``— no LLM. Answers are composed from verbatim evidence sentences (see
                  ``generation.extractive``); query rewriting falls back to heuristics.
"""

from __future__ import annotations

import json
import logging
import time
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass
from functools import lru_cache

import httpx

from app.core.config import get_settings
from app.core.metrics import LLM_LATENCY, LLM_TOKENS

logger = logging.getLogger(__name__)


class LLMError(Exception):
    pass


@dataclass
class ChatMessage:
    role: str  # system | user | assistant
    content: str


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0


class LLMProvider(ABC):
    name: str
    model: str

    @abstractmethod
    def stream(
        self, messages: list[ChatMessage], *, max_tokens: int, temperature: float, usage: Usage
    ) -> Iterator[str]:
        """Yield text deltas. Implementations fill ``usage`` when the API reports it."""

    def complete(
        self, messages: list[ChatMessage], *, max_tokens: int = 512, temperature: float = 0.0
    ) -> tuple[str, Usage]:
        usage = Usage()
        began = time.perf_counter()
        text = "".join(self.stream(messages, max_tokens=max_tokens, temperature=temperature, usage=usage))
        self._record(began, usage)
        return text, usage

    def _record(self, began: float, usage: Usage) -> None:
        LLM_LATENCY.labels(self.name, self.model).observe(time.perf_counter() - began)
        LLM_TOKENS.labels(self.name, self.model, "prompt").inc(usage.prompt_tokens)
        LLM_TOKENS.labels(self.name, self.model, "completion").inc(usage.completion_tokens)


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


class OpenAICompatibleProvider(LLMProvider):
    name = "openai"

    def __init__(self, model: str, api_key: str | None, base_url: str | None, timeout: float) -> None:
        self.model = model
        self.base_url = (base_url or "https://api.openai.com/v1").rstrip("/")
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self.client = httpx.Client(headers=headers, timeout=httpx.Timeout(timeout, connect=10.0))

    def stream(
        self, messages: list[ChatMessage], *, max_tokens: int, temperature: float, usage: Usage
    ) -> Iterator[str]:
        payload = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        produced: list[str] = []
        try:
            with self.client.stream("POST", f"{self.base_url}/chat/completions", json=payload) as response:
                if response.status_code >= 400:
                    body = response.read().decode(errors="replace")[:500]
                    raise LLMError(f"LLM provider returned HTTP {response.status_code}: {body}")
                for line in response.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    event = json.loads(data)
                    if event.get("usage"):
                        usage.prompt_tokens = event["usage"].get("prompt_tokens", 0)
                        usage.completion_tokens = event["usage"].get("completion_tokens", 0)
                    for choice in event.get("choices", []):
                        delta = (choice.get("delta") or {}).get("content")
                        if delta:
                            produced.append(delta)
                            yield delta
        except httpx.HTTPError as exc:
            raise LLMError(f"LLM provider request failed: {exc.__class__.__name__}") from exc
        if not usage.completion_tokens:
            usage.prompt_tokens = sum(_estimate_tokens(m.content) for m in messages)
            usage.completion_tokens = _estimate_tokens("".join(produced))


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, model: str, api_key: str | None, base_url: str | None, timeout: float) -> None:
        if not api_key:
            raise LLMError("LLM_API_KEY is required for the anthropic provider")
        self.model = model
        self.base_url = (base_url or "https://api.anthropic.com").rstrip("/")
        self.client = httpx.Client(
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            timeout=httpx.Timeout(timeout, connect=10.0),
        )

    def stream(
        self, messages: list[ChatMessage], *, max_tokens: int, temperature: float, usage: Usage
    ) -> Iterator[str]:
        system = "\n\n".join(m.content for m in messages if m.role == "system")
        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system,
            "messages": [{"role": m.role, "content": m.content} for m in messages if m.role != "system"],
            "stream": True,
        }
        try:
            with self.client.stream("POST", f"{self.base_url}/v1/messages", json=payload) as response:
                if response.status_code >= 400:
                    body = response.read().decode(errors="replace")[:500]
                    raise LLMError(f"LLM provider returned HTTP {response.status_code}: {body}")
                for line in response.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    event = json.loads(line[5:].strip())
                    kind = event.get("type")
                    if kind == "message_start":
                        usage.prompt_tokens = event["message"].get("usage", {}).get("input_tokens", 0)
                    elif kind == "content_block_delta" and event["delta"].get("type") == "text_delta":
                        yield event["delta"]["text"]
                    elif kind == "message_delta":
                        usage.completion_tokens = event.get("usage", {}).get("output_tokens", 0)
                    elif kind == "error":
                        raise LLMError(
                            f"LLM provider error: {event.get('error', {}).get('message', 'unknown')}"
                        )
        except httpx.HTTPError as exc:
            raise LLMError(f"LLM provider request failed: {exc.__class__.__name__}") from exc


@lru_cache
def get_llm() -> LLMProvider | None:
    """The configured LLM, or ``None`` in extractive mode."""
    settings = get_settings()
    if settings.llm_provider == "extractive":
        return None
    if not settings.llm_model:
        raise LLMError("LLM_MODEL must be set when LLM_PROVIDER is not 'extractive'")
    if settings.llm_provider == "anthropic":
        return AnthropicProvider(
            settings.llm_model, settings.llm_api_key, settings.llm_base_url, settings.llm_timeout_seconds
        )
    return OpenAICompatibleProvider(
        settings.llm_model, settings.llm_api_key, settings.llm_base_url, settings.llm_timeout_seconds
    )
