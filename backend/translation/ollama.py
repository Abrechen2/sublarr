"""Ollama translation backend.

Inherits from LLMBackend (Phase A1 telemetry) — the shared orchestration
(concurrency, retry on line-count mismatch, cost+event write) lives in
:mod:`translation.llm_base`. This module supplies the three provider hooks
(_build_request / _call_api / _parse_response) plus an _assemble_messages
override that preserves the V8/V9-trained prompt format built by
:mod:`translation.llm_utils.build_translation_prompt`.

Helper methods ``_call_ollama`` / ``_call_ollama_chat`` / ``health_check``
remain available for external callers and tests.
"""

from __future__ import annotations

import logging
import re
from decimal import Decimal

import requests

from translation.llm_base import LLMBackend, LLMResponse
from translation.llm_utils import build_translation_prompt, has_cjk_hallucination
from translation.prompt_safety import escape_for_prompt

logger = logging.getLogger(__name__)


class OllamaBackend(LLMBackend):
    """Ollama (Local LLM) translation backend.

    Uses the Ollama /api/generate or /api/chat endpoint. The selection is
    driven by the ``use_chat_api`` config flag (V9+ models).
    Config values are loaded from config_entries (backend.ollama.*) by the
    TranslationManager, with fallback to Pydantic Settings for migration.
    """

    name = "ollama"
    display_name = "Ollama (Local LLM)"
    supports_glossary = True  # Via prompt injection
    supports_batch = True
    max_batch_size = 25

    # LLMBackend class-level contract: self-hosted, no cost.
    default_model = "qwen2.5:14b-instruct"
    cost_per_1m_tokens_in = Decimal("0")
    cost_per_1m_tokens_out = Decimal("0")
    timeout_s = 120

    config_fields = [
        {
            "key": "url",
            "label": "Ollama URL",
            "type": "text",
            "required": True,
            "default": "http://localhost:11434",
            "help": "Ollama API endpoint",
        },
        {
            "key": "model",
            "label": "Model",
            "type": "text",
            "required": True,
            "default": "qwen2.5:14b-instruct",
            "help": "Model name as shown in 'ollama list'",
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
            "default": "90",
            "help": "Request timeout for Ollama API calls",
        },
        {
            "key": "max_retries",
            "label": "Max Retries",
            "type": "number",
            "required": False,
            "default": "3",
            "help": "Number of retry attempts on failure",
        },
        {
            "key": "use_chat_api",
            "label": "Chat API (V9+)",
            "type": "checkbox",
            "required": False,
            "default": "false",
            "help": "Use /api/chat instead of /api/generate for V9+ models",
        },
        {
            "key": "system_prompt",
            "label": "System Prompt",
            "type": "textarea",
            "required": False,
            "default": (
                "Du bist ein spezialisierter Anime-Untertitel-Übersetzer. "
                "Übersetze englische Anime-Untertitel präzise und natürlich ins Deutsche. "
                "Verwende informelle Sprache (du-Form). Behalte Charakternamen und "
                "Eigennamen unverändert. Keine Erklärungen oder Kommentare — nur die Übersetzung."
            ),
            "help": "System prompt for chat API mode. Use {series_context} as placeholder.",
        },
    ]

    def __init__(self, **config):
        super().__init__(**config)
        # Apply Pydantic fallbacks for Ollama (migration compatibility)
        self._apply_pydantic_fallbacks()

    def _apply_pydantic_fallbacks(self):
        """Fill missing config values from Pydantic Settings (migration path).

        Existing installations have Ollama config in env vars / .env,
        not yet in config_entries. This ensures they keep working.
        """
        try:
            from config import get_settings

            settings = get_settings()
            defaults = {
                "url": settings.ollama_url,
                "model": settings.ollama_model,
                "temperature": str(settings.temperature),
                "request_timeout": str(settings.request_timeout),
                "max_retries": str(settings.max_retries),
                "backoff_base": str(settings.backoff_base),
                "batch_size": str(settings.batch_size),
            }
            for key, default_value in defaults.items():
                if key not in self.config or not self.config[key]:
                    self.config[key] = default_value
        except Exception as e:
            logger.warning("Failed to load settings for Ollama backend: %s", e)
            # Fall through to use hardcoded defaults in property accessors

    @property
    def _url(self) -> str:
        return self.config.get("url", "http://localhost:11434")

    @property
    def _model(self) -> str:
        return self.config.get("model", "qwen2.5:14b-instruct")

    # Expose `model` for the LLMBackend contract — parity with other LLM backends.
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
            return int(self.config.get("request_timeout", 90))
        except (ValueError, TypeError):
            return 90

    @property
    def _max_retries(self) -> int:
        try:
            return int(self.config.get("max_retries", 3))
        except (ValueError, TypeError):
            return 3

    @property
    def _backoff_base(self) -> int:
        try:
            return int(self.config.get("backoff_base", 5))
        except (ValueError, TypeError):
            return 5

    @property
    def _use_chat_api(self) -> bool:
        val = self.config.get("use_chat_api", "false")
        if isinstance(val, bool):
            return val
        return str(val).lower() in ("true", "1", "yes")

    @property
    def _system_prompt(self) -> str:
        return self.config.get("system_prompt", "")

    def _build_system_prompt(self, series_context: str | None) -> str:
        base = self._system_prompt or (
            "Du bist ein spezialisierter Anime-Untertitel-Übersetzer. "
            "Übersetze englische Anime-Untertitel präzise und natürlich ins Deutsche. "
            "Verwende informelle Sprache (du-Form). Behalte Charakternamen und "
            "Eigennamen unverändert. Keine Erklärungen oder Kommentare — nur die Übersetzung."
        )
        # P3: escape series_context BEFORE substitution. series_context comes
        # from upstream metadata (Sonarr/Radarr `overview` field) which is
        # ultimately attacker-controllable. Substituting raw text into the
        # system prompt would re-introduce the very vulnerability the
        # llm_base/llm_utils escape pipeline closes for the user message.
        safe_context = escape_for_prompt(series_context)
        if not safe_context:
            return base.replace("{series_context}", "").strip()
        if "{series_context}" in base:
            return base.replace("{series_context}", safe_context)
        return f"{base} {safe_context}"

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
        """Build OpenAI-style messages using the V8/V9-trained prompt format.

        Generate-API mode (legacy V8 fine-tune): everything goes in one user
        message — the model was trained on the numbered/glossary format built
        by ``build_translation_prompt``. We don't use a separate system
        message so we don't drift from training.

        Chat-API mode (V9+): a separate system message carries role/tone;
        the user message still uses the trained numbered format.

        Note: ``lookback`` and ``lookahead`` are accepted but IGNORED here —
        the trained prompt format has a fixed shape and any extra context
        would drift from the fine-tune distribution. Surrounding-line
        context is only consumed by generic LLMBackend subclasses.
        """
        # Explicit no-op to silence unused-argument lints; drift-prevention note above.
        del lookback, lookahead
        # ``strict`` must reach the USER message. LLMBackend puts the retry
        # constraint in the system message, but generate mode drops that — so
        # a strict retry would otherwise re-send a byte-identical prompt and
        # fail on the same line count it just failed on. It is threaded into
        # the prompt builder rather than appended, because a trailing
        # instruction gets echoed back as an extra output line by the
        # fine-tune (measured 4/10 on anime-translator-en-de-v15).
        user_content = build_translation_prompt(
            lines, source_lang, target_lang, glossary_entries, strict=strict
        )
        if self._use_chat_api:
            system_content = self._build_system_prompt(series_context)
            return [
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_content},
            ]
        return [{"role": "user", "content": user_content}]

    def _build_request(self, messages: list[dict], max_tokens: int) -> dict:
        """Build the Ollama request payload.

        Wraps the messages assembled upstream into either ``/api/chat`` or
        ``/api/generate`` shape. ``mode`` is consumed by ``_call_api`` to
        pick the right endpoint.
        """
        if self._use_chat_api:
            return {
                "_mode": "chat",
                "model": self._model,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": self._temperature,
                    "num_predict": max(max_tokens, 4096),
                    "num_ctx": 4096,
                },
            }
        # Generate-API: the single user message carries the full trained prompt.
        prompt = next(
            (m["content"] for m in messages if m.get("role") == "user"),
            "",
        )
        return {
            "_mode": "generate",
            "model": self._model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": self._temperature,
                "num_predict": max(max_tokens, 4096),
            },
        }

    def _call_api(self, payload: dict, timeout_s: int) -> dict:
        """Execute the HTTP call against /api/generate or /api/chat.

        Returns the raw JSON. Raises RuntimeError on API-level errors
        (including 429 rate-limiting) and ``requests.RequestException``
        on network errors.
        """
        mode = payload.pop("_mode", "generate")
        endpoint = "/api/chat" if mode == "chat" else "/api/generate"
        effective_timeout = timeout_s or self._request_timeout

        resp = requests.post(
            f"{self._url}{endpoint}",
            json=payload,
            timeout=effective_timeout,
        )

        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After")
            try:
                wait_seconds = int(retry_after) if retry_after else 60
            except ValueError:
                wait_seconds = 60
            logger.warning("Ollama API rate limited, waiting %ds", wait_seconds)
            raise RuntimeError(f"Ollama rate limited, retry after {wait_seconds}s")

        resp.raise_for_status()

        try:
            data = resp.json()
        except ValueError as e:
            raise RuntimeError("Ollama returned invalid JSON response") from e

        if "error" in data:
            raise RuntimeError(f"Ollama error: {data['error']}")

        # Stash mode on the JSON so _parse_response knows where to find content.
        data["_mode"] = mode
        return data

    def _parse_response(self, raw: dict) -> LLMResponse:
        """Extract translations + token counts from the Ollama response.

        Ollama returns prompt/eval token counts on both /api/generate and
        /api/chat as ``prompt_eval_count`` / ``eval_count``.

        This hook splits and nothing else. It used to claim it called
        :func:`translation.llm_utils.parse_llm_response`, which it never did —
        that function has no caller in the production path at all, so the
        merge repair it carries could not fire. Numbering, stray break markers
        and wrapped lines are handled by
        :func:`translation.llm_utils.repair_line_mapping` in
        ``LLMBackend._attempt``, where every LLM backend passes through.
        """
        mode = raw.pop("_mode", "generate")
        if mode == "chat":
            msg = raw.get("message") or {}
            content = msg.get("content")
            if content is None:
                raise RuntimeError(
                    f"Ollama chat response missing 'message.content': {list(raw.keys())}"
                )
        else:
            if "response" not in raw:
                raise RuntimeError(f"Ollama response missing 'response' key: {list(raw.keys())}")
            content = raw["response"]

        # Strip reasoning-model <think>…</think> blocks (qwen3, deepseek-r1, …)
        # so chain-of-thought never leaks into the subtitle output. Handles
        # well-formed pairs and the "reasoning … </think> answer" shape where
        # the opening tag was suppressed by the API.
        text = content or ""
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
        if "</think>" in text.lower():
            text = text[text.lower().rfind("</think>") + len("</think>") :]
        text = text.strip()

        # Splitting is all this hook does. Numbering, stray break markers and
        # wrapped lines are repaired by ``llm_utils.repair_line_mapping`` in
        # LLMBackend._attempt, so every LLM backend gets the same treatment —
        # ChatGPT and Claude never had any. Length validation and the retry
        # stay with LLMBackend._verify_line_count.
        translations = text.split("\n") or [text]

        tokens_in = int(raw.get("prompt_eval_count") or 0)
        tokens_out = int(raw.get("eval_count") or 0)
        # total_duration is in nanoseconds when present.
        raw_latency_ms = int((raw.get("total_duration") or 0) / 1_000_000)

        return LLMResponse(
            translations=translations,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            model=raw.get("model", self._model),
            finish_reason=raw.get("done_reason"),
            raw_latency_ms=raw_latency_ms,
        )

    def _verify_line_count(
        self,
        resp: LLMResponse,
        lines: list[str],
        source_lang: str,
        target_lang: str,
        glossary_entries: list[dict] | None,
        series_context: str | None = None,
        *,
        lookback: list[str] | None = None,
        lookahead: list[str] | None = None,
    ) -> LLMResponse:
        """Ollama's line-count retry, plus one extra retry on CJK hallucination.

        Qwen2.5 and other multilingual LLMs occasionally drift into Chinese
        characters when translating between non-CJK languages. This override
        first defers to the base-class line-count retry; if that succeeds but
        any output line contains CJK characters, we attempt one more retry
        with ``is_retry=True`` (strict prompt). If CJK persists after the
        retry we keep the best-effort output — a translation with some
        hallucinated characters is more useful than no translation — and log
        a warning so the issue is visible.
        """
        resp = super()._verify_line_count(
            resp,
            lines,
            source_lang,
            target_lang,
            glossary_entries,
            series_context,
            lookback=lookback,
            lookahead=lookahead,
        )

        tainted = [i for i, t in enumerate(resp.translations) if has_cjk_hallucination(t)]
        if not tainted:
            return resp

        logger.warning(
            "%s: CJK hallucination in %d/%d lines (indices %s) — retrying with strict prompt",
            self.name,
            len(tainted),
            len(resp.translations),
            tainted,
        )
        resp_retry = self._attempt(
            lines,
            source_lang,
            target_lang,
            glossary_entries,
            series_context=series_context,
            is_retry=True,
            lookback=lookback,
            lookahead=lookahead,
        )

        # Always sum tokens — we paid for both attempts regardless of outcome
        resp_retry.tokens_in += resp.tokens_in
        resp_retry.tokens_out += resp.tokens_out
        resp_retry.cache_read_tokens += resp.cache_read_tokens
        resp_retry.cache_write_tokens += resp.cache_write_tokens

        still_tainted = [
            i for i, t in enumerate(resp_retry.translations) if has_cjk_hallucination(t)
        ]
        if len(resp_retry.translations) == len(lines) and not still_tainted:
            return resp_retry

        # Retry didn't help — keep original (best-effort). The token counters
        # of the retry are merged into ``resp`` so the event captures full spend.
        resp.tokens_in = resp_retry.tokens_in
        resp.tokens_out = resp_retry.tokens_out
        resp.cache_read_tokens = resp_retry.cache_read_tokens
        resp.cache_write_tokens = resp_retry.cache_write_tokens
        logger.warning(
            "%s: CJK hallucination persisted after retry (still %d tainted), keeping original output",
            self.name,
            len(still_tainted) if still_tainted else len(tainted),
        )
        return resp

    # ------------------------------------------------------------------ #
    # Legacy helpers (kept for health_check + tests + external callers)
    # ------------------------------------------------------------------ #

    def _call_ollama(self, prompt: str) -> str:
        """Single Ollama /api/generate call returning the stripped response text.

        Preserved for backward compatibility with health-check code and
        existing tests. The new translate_batch path goes through
        :meth:`_call_api` directly.
        """
        payload = {
            "model": self._model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": self._temperature,
                "num_predict": 4096,
            },
        }
        resp = requests.post(
            f"{self._url}/api/generate",
            json=payload,
            timeout=self._request_timeout,
        )

        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After")
            if retry_after:
                try:
                    wait_seconds = int(retry_after)
                except ValueError:
                    wait_seconds = 60
            else:
                wait_seconds = 60
            logger.warning("Ollama API rate limited, waiting %ds", wait_seconds)
            raise RuntimeError(f"Ollama rate limited, retry after {wait_seconds}s")

        resp.raise_for_status()

        try:
            data = resp.json()
        except ValueError as e:
            raise RuntimeError("Ollama returned invalid JSON response") from e

        if "error" in data:
            raise RuntimeError(f"Ollama error: {data['error']}")

        if "response" not in data:
            raise RuntimeError(f"Ollama response missing 'response' key: {list(data.keys())}")

        return data["response"].strip()

    def _call_ollama_chat(self, system_prompt: str, user_prompt: str) -> str:
        """Single Ollama /api/chat call returning the stripped message content."""
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": {"temperature": self._temperature, "num_predict": 4096, "num_ctx": 4096},
        }
        resp = requests.post(f"{self._url}/api/chat", json=payload, timeout=self._request_timeout)

        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After")
            try:
                wait_seconds = int(retry_after) if retry_after else 60
            except ValueError:
                wait_seconds = 60
            raise RuntimeError(f"Ollama rate limited, retry after {wait_seconds}s")

        resp.raise_for_status()

        try:
            data = resp.json()
        except ValueError as e:
            raise RuntimeError("Ollama returned invalid JSON response") from e

        if "error" in data:
            raise RuntimeError(f"Ollama error: {data['error']}")

        if "message" not in data or "content" not in data.get("message", {}):
            raise RuntimeError(
                f"Ollama chat response missing 'message.content': {list(data.keys())}"
            )

        return data["message"]["content"].strip()

    def health_check(self) -> tuple[bool, str]:
        """Check if Ollama is reachable and the model is available."""
        try:
            resp = requests.get(f"{self._url}/api/tags", timeout=10)
            if resp.status_code != 200:
                return False, f"Ollama returned status {resp.status_code}"
            try:
                data = resp.json()
            except ValueError:
                return False, "Ollama returned invalid JSON"
            models = [m["name"] for m in data.get("models", [])]
            model_found = any(self._model in name for name in models)
            if not model_found:
                return False, f"Model '{self._model}' not found. Available: {models}"
            return True, "OK"
        except requests.Timeout:
            return False, f"Ollama health check timed out at {self._url}"
        except requests.ConnectionError:
            return False, f"Cannot connect to Ollama at {self._url}"
        except Exception as e:
            return False, f"Ollama health check failed: {e}"

    def get_config_fields(self) -> list[dict]:
        """Return config field definitions for the Settings UI."""
        return self.config_fields

    def get_usage(self) -> dict:
        """Ollama has no usage tracking -- returns empty dict."""
        return {}

    # Backward-compat parsed_llm_response re-exports in case legacy callers
    # still reach into this module for those names.
    # (build_translation_prompt + parse_llm_response remain importable via
    # ``translation.llm_utils`` directly; the legacy ``from translation.ollama
    # import build_translation_prompt`` path continues to work via the module
    # imports above.)
