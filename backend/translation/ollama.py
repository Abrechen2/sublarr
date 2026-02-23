"""Ollama translation backend.

Migrated from ollama_client.py into the TranslationBackend ABC.
Preserves all existing translation logic: batch translation, retry with
exponential backoff, CJK hallucination detection, and single-line fallback.
"""

import time
import logging

import requests

from translation.base import TranslationBackend, TranslationResult
from translation.llm_utils import (
    build_translation_prompt,
    parse_llm_response,
    has_cjk_hallucination,
)

logger = logging.getLogger(__name__)


class OllamaBackend(TranslationBackend):
    """Ollama (Local LLM) translation backend.

    Uses the Ollama /api/generate endpoint for text translation.
    Config values are loaded from config_entries (backend.ollama.*) by the
    TranslationManager, with fallback to Pydantic Settings for migration.
    """

    name = "ollama"
    display_name = "Ollama (Local LLM)"
    supports_glossary = True  # Via prompt injection
    supports_batch = True
    max_batch_size = 25

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

    def translate_batch(
        self,
        lines: list[str],
        source_lang: str,
        target_lang: str,
        glossary_entries: list[dict] | None = None,
    ) -> TranslationResult:
        """Translate a batch of subtitle lines via Ollama.

        Includes retry logic with exponential backoff and CJK hallucination
        detection. Falls back to single-line translation if batch fails.
        """
        if not lines:
            return TranslationResult(
                translated_lines=[],
                backend_name=self.name,
                success=True,
            )

        start_time = time.time()
        prompt = build_translation_prompt(
            lines, source_lang, target_lang, glossary_entries
        )

        last_error = None
        for attempt in range(1, self._max_retries + 1):
            try:
                response = self._call_ollama(prompt)
                parsed = parse_llm_response(response, len(lines))
                if parsed is not None:
                    # Check for CJK hallucination in any line
                    tainted = [i for i, t in enumerate(parsed) if has_cjk_hallucination(t)]
                    if tainted:
                        logger.warning(
                            "Attempt %d: CJK hallucination in %d lines (indices %s), retrying...",
                            attempt, len(tainted), tainted,
                        )
                        last_error = "CJK hallucination detected"
                    else:
                        elapsed_ms = (time.time() - start_time) * 1000
                        return TranslationResult(
                            translated_lines=parsed,
                            backend_name=self.name,
                            response_time_ms=elapsed_ms,
                            characters_used=sum(len(l) for l in lines),
                            success=True,
                        )
                else:
                    logger.warning("Attempt %d: line count mismatch, retrying...", attempt)
                    last_error = f"Expected {len(lines)} lines, got different count"
            except (requests.RequestException, RuntimeError) as e:
                logger.warning("Attempt %d failed: %s", attempt, e)
                last_error = str(e)

            if attempt < self._max_retries:
                wait = self._backoff_base * (2 ** (attempt - 1))
                logger.info("Waiting %ds before retry...", wait)
                time.sleep(wait)

        # Fallback: translate lines individually
        logger.warning("Batch translation failed, falling back to single-line mode")
        return self._translate_singles(lines, source_lang, target_lang, glossary_entries, start_time)

    def _translate_singles(
        self,
        lines: list[str],
        source_lang: str,
        target_lang: str,
        glossary_entries: list[dict] | None,
        start_time: float,
    ) -> TranslationResult:
        """Translate lines one by one as fallback, with retries."""
        import re

        results = []
        for i, line in enumerate(lines):
            prompt = build_translation_prompt(
                [line], source_lang, target_lang, glossary_entries
            )
            last_error = None

            for attempt in range(1, self._max_retries + 1):
                try:
                    response = self._call_ollama(prompt)
                    translated = re.sub(r"^\d+[\.:]\s*", "", response.strip().split("\n")[0])
                    if has_cjk_hallucination(translated):
                        logger.warning(
                            "Single line %d, attempt %d: CJK hallucination, retrying",
                            i, attempt,
                        )
                        last_error = "CJK hallucination detected"
                    else:
                        results.append(translated)
                        last_error = None
                        break
                except (requests.RequestException, RuntimeError) as e:
                    logger.warning("Single line %d, attempt %d failed: %s", i, attempt, e)
                    last_error = str(e)
                if attempt < self._max_retries:
                    wait = self._backoff_base * (2 ** (attempt - 1))
                    time.sleep(wait)

            if last_error is not None:
                logger.error(
                    "Failed to translate line %d after %d attempts, keeping original",
                    i, self._max_retries,
                )
                results.append(line)

        elapsed_ms = (time.time() - start_time) * 1000
        fallback_count = sum(1 for orig, trans in zip(lines, results) if orig.strip() == trans.strip())
        if fallback_count > len(lines) * 0.5:
            return TranslationResult(
                success=False,
                translated_lines=[],
                backend_name=self.name,
                response_time_ms=elapsed_ms,
                characters_used=sum(len(l) for l in lines),
                error=f"Too many line failures: {fallback_count}/{len(lines)} fell back to original",
            )
        return TranslationResult(
            translated_lines=results,
            backend_name=self.name,
            response_time_ms=elapsed_ms,
            characters_used=sum(len(l) for l in lines),
            success=True,
        )

    def _call_ollama(self, prompt: str) -> str:
        """Make a single Ollama API call.

        Returns:
            Model response text

        Raises:
            RuntimeError: On API errors or invalid responses
            requests.RequestException: On network errors
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

        # Handle rate limiting (429) before raise_for_status
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
        except ValueError:
            raise RuntimeError("Ollama returned invalid JSON response")

        if "error" in data:
            raise RuntimeError(f"Ollama error: {data['error']}")

        if "response" not in data:
            raise RuntimeError(f"Ollama response missing 'response' key: {list(data.keys())}")

        return data["response"].strip()

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
