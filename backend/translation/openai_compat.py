"""OpenAI-compatible translation backend.

Supports any OpenAI-compatible endpoint via configurable base_url:
OpenAI, Azure OpenAI, LM Studio, vLLM, and other compatible services.

Shares LLM utilities (prompt building, response parsing, CJK hallucination
detection) with OllamaBackend via translation.llm_utils.
"""

import time
import logging
import threading

from translation.base import TranslationBackend, TranslationResult

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


class OpenAICompatBackend(TranslationBackend):
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

    def _get_client(self) -> "OpenAI":
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

    def translate_batch(
        self,
        lines: list[str],
        source_lang: str,
        target_lang: str,
        glossary_entries: list[dict] | None = None,
    ) -> TranslationResult:
        """Translate a batch of subtitle lines via OpenAI-compatible API.

        Uses shared LLM utilities for prompt building, response parsing,
        and CJK hallucination detection (same as OllamaBackend).
        """
        if not lines:
            return TranslationResult(
                translated_lines=[],
                backend_name=self.name,
                success=True,
            )

        from translation.llm_utils import (
            build_translation_prompt,
            parse_llm_response,
            has_cjk_hallucination,
        )

        start_time = time.time()
        prompt = build_translation_prompt(
            lines, source_lang, target_lang, glossary_entries
        )

        try:
            client = self._get_client()
        except RuntimeError as e:
            return TranslationResult(
                translated_lines=[],
                backend_name=self.name,
                error=str(e),
                success=False,
            )

        last_error = None
        for attempt in range(1, self._max_retries + 1):
            try:
                completion = client.chat.completions.create(
                    model=self._model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=self._temperature,
                )
                response_text = completion.choices[0].message.content.strip()

                parsed = parse_llm_response(response_text, len(lines))
                if parsed is None:
                    logger.warning(
                        "Attempt %d: line count mismatch, retrying...", attempt
                    )
                    last_error = f"Expected {len(lines)} lines, got different count"
                    continue

                # Check for CJK hallucination in any line
                tainted = [i for i, t in enumerate(parsed) if has_cjk_hallucination(t)]
                if tainted:
                    logger.warning(
                        "Attempt %d: CJK hallucination in %d lines (indices %s), retrying...",
                        attempt, len(tainted), tainted,
                    )
                    last_error = "CJK hallucination detected"
                    continue

                elapsed_ms = (time.time() - start_time) * 1000
                return TranslationResult(
                    translated_lines=parsed,
                    backend_name=self.name,
                    response_time_ms=elapsed_ms,
                    characters_used=sum(len(l) for l in lines),
                    success=True,
                )

            except Exception as e:
                logger.warning("Attempt %d failed: %s", attempt, e)
                last_error = str(e)

            # Backoff between retries
            if attempt < self._max_retries:
                wait = 2 ** (attempt - 1)
                logger.info("Waiting %ds before retry...", wait)
                time.sleep(wait)

        elapsed_ms = (time.time() - start_time) * 1000
        return TranslationResult(
            translated_lines=[],
            backend_name=self.name,
            response_time_ms=elapsed_ms,
            error=f"All {self._max_retries} attempts failed. Last error: {last_error}",
            success=False,
        )

    def health_check(self) -> tuple[bool, str]:
        """Check if the OpenAI-compatible service is reachable and model available."""
        try:
            client = self._get_client()
            models_response = client.models.list()
            model_ids = [m.id for m in list(models_response)[:10]]
            if self._model in model_ids:
                return True, f"OK (model '{self._model}' available)"
            # Model might still work even if not in first 10
            return True, f"OK (connected; model '{self._model}' not in first 10 listed: {model_ids})"
        except RuntimeError as e:
            return False, str(e)
        except Exception as e:
            return False, f"Health check failed: {e}"

    def get_config_fields(self) -> list[dict]:
        """Return config field definitions for the Settings UI."""
        return self.config_fields
