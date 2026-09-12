from __future__ import annotations

import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable, TypeVar

from openai import OpenAI, RateLimitError


T = TypeVar("T")


@dataclass
class LLMToolCall:
    id: str
    name: str
    arguments: str


@dataclass
class LLMResponse:
    content: str | None
    tool_calls: list[LLMToolCall]
    finish_reason: str | None
    raw: Any


class LLMProvider(ABC):
    @abstractmethod
    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        raise NotImplementedError

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        raise NotImplementedError


class KloudeksProvider(LLMProvider):
    BASE_URL = "https://mia.csp.kloudeks.com/v1"
    CHAT_MODEL = "kkbhackathon2026/Qwen3.8-27B"
    EMBEDDING_MODEL = "kkbhackathon2026/Qwen3-Embedding-8B"
    OCR_MODEL = "kkbhackathon2026/Unlimited-OCR"

    def __init__(
        self,
        api_key: str | None = None,
        *,
        client: Any | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self.api_key = api_key or os.getenv("MIA_API_KEY")
        if not self.api_key and client is None:
            raise ValueError("MIA_API_KEY is required")

        self.client = client or OpenAI(
            api_key=self.api_key,
            base_url=self.BASE_URL,
        )
        self._sleep = sleep_fn

    def _with_rate_limit_retry(self, operation: Callable[[], T]) -> T:
        delays = (2, 4, 8)

        for attempt in range(len(delays) + 1):
            try:
                return operation()
            except RateLimitError:
                if attempt >= len(delays):
                    raise
                self._sleep(delays[attempt])

        raise RuntimeError("Unreachable retry state")

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        kwargs: dict[str, Any] = {
            "model": self.CHAT_MODEL,
            "messages": messages,
        }

        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        response = self._with_rate_limit_retry(
            lambda: self.client.chat.completions.create(**kwargs)
        )

        choice = response.choices[0]
        message = choice.message

        tool_calls = [
            LLMToolCall(
                id=tool_call.id,
                name=tool_call.function.name,
                arguments=tool_call.function.arguments,
            )
            for tool_call in (message.tool_calls or [])
        ]

        return LLMResponse(
            content=message.content,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason,
            raw=response,
        )

    def embed(self, text: str) -> list[float]:
        if not text.strip():
            raise ValueError("Embedding text must not be empty")

        response = self._with_rate_limit_retry(
            lambda: self.client.embeddings.create(
                model=self.EMBEDDING_MODEL,
                input=text,
                encoding_format="float",
            )
        )
        return response.data[0].embedding

    def ocr(self, image_base64: str) -> str:
        if not image_base64.strip():
            raise ValueError("OCR image_base64 must not be empty")

        response = self._with_rate_limit_retry(
            lambda: self.client.chat.completions.create(
                model=self.OCR_MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{image_base64}"
                                },
                            },
                            {
                                "type": "text",
                                "text": "<image>\\ndocument parsing",
                            },
                        ],
                    }
                ],
                max_tokens=8192,
                temperature=0.0,
                extra_body={
                    "skip_special_tokens": False,
                    "vllm_xargs": {
                        "ngram_size": 35,
                        "window_size": 128,
                    },
                },
            )
        )

        return response.choices[0].message.content or ""
