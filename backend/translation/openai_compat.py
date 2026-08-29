"""OpenAI-compatible translation backend.

Inherits from LLMBackend (Phase A1 telemetry) — the shared orchestration
(concurrency, retry on line-count mismatch, cost+event write) lives in
:mod:`translation.llm_base`. This module supplies the three provider hooks.

Supports any OpenAI-compatible endpoint via configurable base_url:
OpenAI, Azure OpenAI, LM Studio, vLLM, and other compatible services.
"""

from __future__ import annotations

import logging
import threading
from decimal import Decimal

from translation.llm_base import LLMBackend, LLMResponse
from translation.llm_utils import build_translation_prompt
from translation.price_sheet import get_llm_price
from translation.prompt_safety import escape_for_prompt

logger = logging.getLogger(__name__)

# Import guard: openai is optional
try:
    from openai import OpenAI

    _HAS_OPENAI = True
except ImportError:
    _HAS_OPENAI = False
    logger.warning(
        "openai package not installed -- OpenAI-compatible backend unavailable. "
        "Install with: pip install openai>=1.0.0"
    )


class OpenAICompatBackend(LLMBackend):
    """OpenAI-compatible LLM translation backend.

    Uses the OpenAI Python SDK with configurable base_url to support
    OpenAI, Azure OpenAI, LM Studio, vLLM, and other compatible services.

    Config values are loaded from config_entries (backend.openai_compat.*)
    by the TranslationManager.
    """

    name = "openai_compat"
    display_name = "OpenAI-Compatible (OpenAI, Azure, LM Studio, vLLM)"
    supports_glossary = True  # Via prompt injection (same as Ollama)
    supports_batch = True
    max_batch_size = 25

    # LLMBackend class-level contract. Prices are overridden per-instance in
    # __init__ via the price sheet (depends on the selected model).
    default_model = "gpt-4o-mini"
    cost_per_1m_tokens_in = Decimal("0")
    cost_per_1m_tokens_out = Decimal("0")
    timeout_s = 120

    config_fields = [
        {
            "key": "api_key",
            "label": "API Key",
            "type": "password",
            "required": True,
            "default": "",
            "help": "API key for the OpenAI-compatible service",
        },
        {
            "key": "base_url",
            "label": "Base URL",
            "type": "text",
            "required": True,
            "default": "https://api.openai.com/v1",
            "help": "API base URL (e.g. https://api.openai.com/v1, http://localhost:1234/v1)",
        },
        {
            "key": "model",
            "label": "Model",
            "type": "text",
            "required": True,
            "default": "gpt-4o-mini",
            "help": "Model name (e.g. gpt-4o-mini, gpt-4o, local model name)",
        },
        {
            "key": "temperature",
            "label": "Temperature",
            "type": "number",
            "required": False,
            "default": "0.3",
            "help": "Lower = more deterministic (0.0-1.0)",
        },
        {
            "key": "request_timeout",
            "label": "Timeout (seconds)",
            "type": "number",
            "required": False,
            "default": "120",
            "help": "Request timeout for API calls",
        },
        {
            "key": "max_retries",
            "label": "Max Retries",
            "type": "number",
            "required": False,
            "default": "3",
            "help": "Number of retry attempts on failure",
        },
    ]

    def __init__(self, **config):
        super().__init__(**config)
        self._client = None
        self._client_lock = threading.Lock()
        # Look up instance-level prices from the price sheet. Overrides the
        # class defaults (0, 0) so cost_tracker produces real numbers.
        self.cost_per_1m_tokens_in, self.cost_per_1m_tokens_out = get_llm_price(
            self.name, self._model
        )

    @property
    def _api_key(self) -> str:
        return self.config.get("api_key", "")

    @property
    def _base_url(self) -> str:
        return self.config.get("base_url", "https://api.openai.com/v1")

    @property
    def _model(self) -> str:
        return self.config.get("model", "gpt-4o-mini")

    @property
    def model(self) -> str:
        return self._model

    @property
    def _temperature(self) -> float:
        try:
            return float(self.config.get("temperature", 0.3))
        except (ValueError, TypeError):
            return 0.3

    @property
    def _request_timeout(self) -> int:
        try:
            return int(self.config.get("request_timeout", 120))
        except (ValueError, TypeError):
            return 120

    @property
    def _max_retries(self) -> int:
        try:
            return int(self.config.get("max_retries", 3))
        except (ValueError, TypeError):
            return 3

    def _get_client(self) -> OpenAI:
        """Get or create the OpenAI client (lazy initialization, thread-safe)."""
        if not _HAS_OPENAI:
            raise RuntimeError(
                "openai package not installed. Install with: pip install openai>=1.0.0"
            )
        if self._client is None:
            with self._client_lock:
                if self._client is None:
                    self._client = OpenAI(
                        api_key=self._api_key,
                        base_url=self._base_url,
                        timeout=self._request_timeout,
                        max_retries=0,  # We handle retries ourselves
                    )
        return self._client

    # ------------------------------------------------------------------ #
    # LLMBackend hooks
    # ------------------------------------------------------------------ #

    def _assemble_messages(
        self,
        lines: list[str],
        source_lang: str,
        target_lang: str,
        glossary_entries: list[dict] | None,
        series_context: str | None = None,
        strict: bool = False,
        *,
        lookback: list[str] | None = None,
        lookahead: list[str] | None = None,
    ) -> list[dict]:
        """Build the OpenAI-style messages list.

        Uses the same numbered/glossary prompt format as Ollama
        (via :func:`build_translation_prompt`) so LLMs trained on that
        shape behave consistently. We put the full prompt in a single user
        message — the system-vs-user split doesn't add value here and keeps
        parity with Ollama's generate-mode.

        Lookback/lookahead context (Phase A4) is prepended to the prompt as
        a clearly marked "context only" block when provided, so generic
        OpenAI-compatible endpoints benefit from narrative context even
        though the main prompt shape stays compatible with Ollama's format.
        """
        prompt = build_translation_prompt(lines, source_lang, target_lang, glossary_entries)
        if series_context:
            # P3: series_context comes from upstream metadata (Sonarr/Radarr
            # `overview`), which is attacker-controllable. Escape before
            # injecting into the prompt to deny prompt-injection / batch-break.
            prompt = f"Context: {escape_for_prompt(series_context)}\n\n{prompt}"
        if strict:
            prompt = (
                f"STRICT: return exactly {len(lines)} numbered lines, "
                f"no commentary, no extra lines.\n\n{prompt}"
            )
        context_parts = []
        if lookback:
            safe_lookback = [escape_for_prompt(line) for line in lookback]
            context_parts.append(
                "Previous lines (for context only, do NOT translate or repeat):\n"
                + "\n".join(safe_lookback)
            )
        if lookahead:
            safe_lookahead = [escape_for_prompt(line) for line in lookahead]
            context_parts.append(
                "Following lines (for context only, do NOT translate or repeat):\n"
                + "\n".join(safe_lookahead)
            )
        if context_parts:
            prompt = "\n\n".join(context_parts) + "\n\n" + prompt
        return [{"role": "user", "content": prompt}]

    def _build_request(self, messages: list[dict], max_tokens: int) -> dict:
        """Build the chat/completions payload."""
        return {
            "model": self._model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": self._temperature,
        }

    def _call_api(self, payload: dict, timeout_s: int) -> dict:
        """Execute chat/completions via the OpenAI SDK.

        Uses the SDK's ``model_dump`` helper so we return a plain dict
        that :meth:`_parse_response` can consume in the same shape as
        the raw HTTP response.
        """
        client = self._get_client()
        completion = client.chat.completions.create(**payload)
        # The SDK returns a pydantic model; convert to dict for parse step.
        if hasattr(completion, "model_dump"):
            return completion.model_dump()
        # Fallback for MagicMock-based tests: build a shape-compatible dict.
        choice = completion.choices[0]
        return {
            "choices": [
                {
                    "message": {"content": choice.message.content},
                    "finish_reason": getattr(choice, "finish_reason", None),
                }
            ],
            "usage": getattr(completion, "usage", None),
            "model": getattr(completion, "model", self._model),
        }

    def _parse_response(self, raw: dict) -> LLMResponse:
        """Extract translations + usage stats from the completion response."""
        try:
            choice = raw["choices"][0]
        except (KeyError, IndexError, TypeError) as e:
            raise RuntimeError(f"OpenAI response missing 'choices': {raw!r}") from e

        message = choice.get("message") or {}
        content = message.get("content")
        if content is None:
            raise RuntimeError(f"OpenAI response missing 'message.content': {raw!r}")

        text = content.strip()
        # Splitting only — numbering, stray break markers and wrapped lines are
        # repaired centrally by LLMBackend._attempt.
        translations = text.split("\n") or [text]

        usage = raw.get("usage") or {}
        # usage may be a pydantic-ish object; accommodate both shapes.
        if isinstance(usage, dict):
            tokens_in = int(usage.get("prompt_tokens") or 0)
            tokens_out = int(usage.get("completion_tokens") or 0)
        else:
            tokens_in = int(getattr(usage, "prompt_tokens", 0) or 0)
            tokens_out = int(getattr(usage, "completion_tokens", 0) or 0)

        finish_reason = choice.get("finish_reason") if isinstance(choice, dict) else None

        return LLMResponse(
            translations=translations,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            model=raw.get("model", self._model),
            finish_reason=finish_reason,
            raw_latency_ms=0,  # OpenAI doesn't report server-side latency
        )

    # ------------------------------------------------------------------ #
    # Introspection
    # ------------------------------------------------------------------ #

    def health_check(self) -> tuple[bool, str]:
        """Check if the OpenAI-compatible service is reachable and model available."""
        try:
            client = self._get_client()
            models_response = client.models.list()
            model_ids = [m.id for m in list(models_response)[:10]]
            if self._model in model_ids:
                return True, f"OK (model '{self._model}' available)"
            # Model might still work even if not in first 10
            return (
                True,
                f"OK (connected; model '{self._model}' not in first 10 listed: {model_ids})",
            )
        except RuntimeError as e:
            return False, str(e)
        except Exception as e:
            return False, f"Health check failed: {e}"

    def get_config_fields(self) -> list[dict]:
        """Return config field definitions for the Settings UI."""
        return self.config_fields
