"""Mistral translation backend — OpenAI-compatible API."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

import requests

from translation.llm_base import LLMBackend, LLMResponse
from translation.price_sheet import get_llm_price

logger = logging.getLogger(__name__)

_API_URL = "https://api.mistral.ai/v1/chat/completions"


class MistralBackend(LLMBackend):
    """Mistral translation backend via OpenAI-compat API."""

    name = "mistral"
    display_name = "Mistral"
    default_model = "mistral-large-latest"
    timeout_s = 120
    supports_glossary = True
    supports_batch = True
    max_batch_size = 50

    cost_per_1m_tokens_in = Decimal("2.00")
    cost_per_1m_tokens_out = Decimal("6.00")

    config_fields = [
        {
            "key": "api_key",
            "type": "password",
            "label": "API Key",
            "required": True,
        },
        {
            "key": "model",
            "type": "text",
            "label": "Model",
            "required": False,
            "default": "mistral-large-latest",
        },
    ]

    def __init__(self, api_key: str, model: str | None = None, **_: Any) -> None:
        if not api_key:
            raise ValueError("MistralBackend: api_key is required")
        self.api_key = api_key
        self._model = model or self.default_model
        self.cost_per_1m_tokens_in, self.cost_per_1m_tokens_out = get_llm_price(
            self.name, self._model
        )

    @property
    def model(self) -> str:
        return self._model

    def _build_request(self, messages: list[dict], max_tokens: int) -> dict:
        """Mistral uses OpenAI chat/completions shape unchanged."""
        return {
            "model": self._model,
            "messages": messages,
            "max_tokens": max_tokens,
        }

    def _call_api(self, payload: dict, timeout_s: int) -> dict:
        resp = requests.post(
            _API_URL,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=timeout_s,
        )
        resp.raise_for_status()
        return resp.json()

    def _parse_response(self, raw: dict) -> LLMResponse:
        choice = raw["choices"][0]
        content = choice["message"]["content"]
        lines = content.split("\n")
        usage = raw.get("usage", {})
        return LLMResponse(
            translations=lines,
            tokens_in=int(usage.get("prompt_tokens", 0)),
            tokens_out=int(usage.get("completion_tokens", 0)),
            model=raw.get("model", self._model),
            finish_reason=choice.get("finish_reason"),
            raw_latency_ms=0,
        )

    def health_check(self) -> tuple[bool, str]:
        try:
            requests.post(
                _API_URL,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self._model,
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 10,
                },
                timeout=10,
            ).raise_for_status()
            return True, "OK"
        except Exception as exc:
            return False, str(exc)

    def get_config_fields(self) -> list[dict]:
        """Return config field definitions for the Settings UI."""
        return self.config_fields
