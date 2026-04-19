"""Google Gemini translation backend — REST API (no SDK)."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

import requests

from translation.llm_base import LLMBackend, LLMResponse
from translation.price_sheet import get_llm_price

logger = logging.getLogger(__name__)

_API_BASE = "https://generativelanguage.googleapis.com/v1/models"


class GeminiBackend(LLMBackend):
    """Google Gemini translation backend via REST."""

    name = "gemini"
    display_name = "Google Gemini"
    default_model = "gemini-2.5-pro"
    timeout_s = 120
    supports_glossary = True
    supports_batch = True
    max_batch_size = 50

    cost_per_1m_tokens_in = Decimal("1.25")
    cost_per_1m_tokens_out = Decimal("5.00")

    config_fields = [
        {"name": "api_key", "type": "password", "label": "API Key", "required": True},
        {
            "name": "model",
            "type": "text",
            "label": "Model",
            "required": False,
            "default": "gemini-2.5-pro",
        },
    ]

    def __init__(self, api_key: str, model: str | None = None, **_: Any) -> None:
        if not api_key:
            raise ValueError("GeminiBackend: api_key is required")
        self.api_key = api_key
        self._model = model or self.default_model
        self.cost_per_1m_tokens_in, self.cost_per_1m_tokens_out = get_llm_price(
            self.name, self._model
        )
        # Preserve dict-style config for any downstream code that expects it
        self.config = {"api_key": api_key, "model": self._model}

    @property
    def model(self) -> str:
        return self._model

    def _build_request(self, messages: list[dict], max_tokens: int) -> dict:
        """Convert OpenAI-style messages to Gemini shape.

        - system message → systemInstruction.parts
        - other messages → contents[].parts
        """
        system_text = ""
        contents: list[dict] = []
        for m in messages:
            if m["role"] == "system":
                system_text = m["content"]
            else:
                contents.append(
                    {
                        "role": "user" if m["role"] == "user" else "model",
                        "parts": [{"text": m["content"]}],
                    }
                )

        payload: dict = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": max_tokens,
            },
        }
        if system_text:
            payload["systemInstruction"] = {"parts": [{"text": system_text}]}
        return payload

    def _call_api(self, payload: dict, timeout_s: int) -> dict:
        url = f"{_API_BASE}/{self._model}:generateContent?key={self.api_key}"
        resp = requests.post(
            url,
            json=payload,
            timeout=timeout_s,
        )
        resp.raise_for_status()
        return resp.json()

    def _parse_response(self, raw: dict) -> LLMResponse:
        candidates = raw.get("candidates", [])
        text = ""
        finish_reason = None
        if candidates:
            cand = candidates[0]
            parts = cand.get("content", {}).get("parts", [])
            text = "".join(p.get("text", "") for p in parts)
            finish_reason = cand.get("finishReason")

        # Map Gemini's SAFETY refusal to our generic content_filter sentinel
        if finish_reason == "SAFETY":
            finish_reason = "content_filter"

        lines = text.split("\n")
        usage = raw.get("usageMetadata", {})
        return LLMResponse(
            translations=lines,
            tokens_in=int(usage.get("promptTokenCount", 0)),
            tokens_out=int(usage.get("candidatesTokenCount", 0)),
            model=raw.get("modelVersion", self._model),
            finish_reason=finish_reason,
            raw_latency_ms=0,
        )

    def health_check(self) -> tuple[bool, str]:
        """Quick API-key check via a 1-token generate call."""
        try:
            url = f"{_API_BASE}/{self._model}:generateContent?key={self.api_key}"
            requests.post(
                url,
                json={
                    "contents": [{"role": "user", "parts": [{"text": "ping"}]}],
                    "generationConfig": {"maxOutputTokens": 1},
                },
                timeout=10,
            ).raise_for_status()
            return True, "OK"
        except Exception as exc:
            return False, str(exc)

    def get_config_fields(self) -> list[dict]:
        """Return config field definitions for the Settings UI."""
        return self.config_fields
