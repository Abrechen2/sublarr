"""Anthropic Claude translation backend.

Inherits from LLMBackend. Implements the three provider hooks for
Anthropic's Messages API:
- _build_request: splits system prompt from messages (Anthropic shape)
  AND wraps system with cache_control for 90% cost reduction via
  Anthropic's prompt-caching feature.
- _call_api: uses anthropic.Anthropic() SDK.
- _parse_response: extracts text + token counts + maps refusal to
  content_filter sentinel.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

import anthropic

from translation.llm_base import LLMBackend, LLMResponse
from translation.price_sheet import get_llm_price

logger = logging.getLogger(__name__)


class ClaudeBackend(LLMBackend):
    """Anthropic Claude translation backend with prompt caching."""

    name = "claude"
    display_name = "Anthropic Claude"
    default_model = "claude-sonnet-4-6"
    timeout_s = 120
    supports_glossary = True
    supports_batch = True
    max_batch_size = 50

    cost_per_1m_tokens_in = Decimal("3.00")
    cost_per_1m_tokens_out = Decimal("15.00")

    config_fields = [
        {"key": "api_key", "type": "password", "label": "API Key", "required": True},
        {
            "key": "model",
            "type": "text",
            "label": "Model",
            "required": False,
            "default": "claude-sonnet-4-6",
        },
    ]

    def __init__(self, api_key: str, model: str | None = None, **_: Any) -> None:
        if not api_key:
            raise ValueError("ClaudeBackend: api_key is required")
        self.api_key = api_key
        self._model = model or self.default_model
        self.cost_per_1m_tokens_in, self.cost_per_1m_tokens_out = get_llm_price(
            self.name, self._model
        )
        self._client: anthropic.Anthropic | None = None
        # Preserve dict-style config for any downstream code that expects it
        self.config = {"api_key": api_key, "model": self._model}

    @property
    def model(self) -> str:
        return self._model

    def _get_client(self) -> anthropic.Anthropic:
        if self._client is None:
            self._client = anthropic.Anthropic(api_key=self.api_key)
        return self._client

    def _build_request(self, messages: list[dict], max_tokens: int) -> dict:
        """Anthropic wants system as a separate top-level param.

        Split the first system message out of the messages list and wrap
        it with cache_control for prompt caching (90% cost reduction on
        reads after the first write).
        """
        system_text = ""
        user_messages = []
        for m in messages:
            if m["role"] == "system":
                system_text = m["content"]
            else:
                user_messages.append(m)

        # Wrap system block with cache_control for Anthropic prompt caching
        system = (
            [
                {
                    "type": "text",
                    "text": system_text,
                    "cache_control": {"type": "ephemeral"},
                }
            ]
            if system_text
            else []
        )

        return {
            "model": self._model,
            "system": system,
            "messages": user_messages,
            "max_tokens": max_tokens,
        }

    def _call_api(self, payload: dict, timeout_s: int) -> dict:
        client = self._get_client()
        resp = client.messages.create(
            model=payload["model"],
            system=payload["system"],
            messages=payload["messages"],
            max_tokens=payload["max_tokens"],
            timeout=float(timeout_s),
        )
        return resp.model_dump()

    def _parse_response(self, raw: dict) -> LLMResponse:
        content_blocks = raw.get("content", [])
        text = "".join(b.get("text", "") for b in content_blocks if b.get("type") == "text")
        lines = text.split("\n")
        usage = raw.get("usage", {}) or {}
        # Split Anthropic's three token counters so the cost calculator can
        # bill them at their respective rates:
        #   - input_tokens: fresh tokens billed at 1× price_in
        #   - cache_read_input_tokens: billed at 0.1× price_in (90% discount)
        #   - cache_creation_input_tokens: billed at 1.25× price_in (one-time premium)
        tokens_in = int(usage.get("input_tokens", 0) or 0)
        cache_read_tokens = int(usage.get("cache_read_input_tokens", 0) or 0)
        cache_write_tokens = int(usage.get("cache_creation_input_tokens", 0) or 0)
        tokens_out = int(usage.get("output_tokens", 0) or 0)

        stop_reason = raw.get("stop_reason")
        # Map Anthropic's refusal to our generic content_filter sentinel
        if stop_reason == "refusal":
            stop_reason = "content_filter"

        return LLMResponse(
            translations=lines,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cache_read_tokens=cache_read_tokens,
            cache_write_tokens=cache_write_tokens,
            model=raw.get("model", self._model),
            finish_reason=stop_reason,
            raw_latency_ms=0,
        )

    def health_check(self) -> tuple[bool, str]:
        """Quick API-key-validity check."""
        try:
            self._get_client().messages.create(
                model=self._model,
                system=[],
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=10,
            )
            return True, "OK"
        except Exception as exc:
            return False, str(exc)

    def get_config_fields(self) -> list[dict]:
        """Return config field definitions for the Settings UI."""
        return self.config_fields
