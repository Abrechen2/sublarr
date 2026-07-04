"""Translation package -- multi-backend translation management.

Provides the TranslationManager singleton which registers backends, manages
instances with lazy creation, delegates translation calls with fallback chains,
and tracks per-backend statistics via circuit breakers.
"""

import logging
import threading
import time

from circuit_breaker import CircuitBreaker
from translation.base import TranslationBackend, TranslationResult

logger = logging.getLogger(__name__)


class TranslationManager:
    """Manages translation backends and orchestrates fallback chains.

    Backend classes are registered at import time. Instances are created lazily
    on first use, with config loaded from the config_entries DB table using
    backend.<name>.<key> namespacing.
    """

    def __init__(self):
        self._backend_classes: dict[str, type[TranslationBackend]] = {}
        self._backends: dict[str, TranslationBackend] = {}
        self._circuit_breakers: dict[str, CircuitBreaker] = {}
        self._backends_lock = threading.Lock()

    def register_backend(self, cls: type[TranslationBackend]) -> None:
        """Register a backend class by its name attribute.

        Also registers the backend with ``BackendConcurrency`` (Phase A1),
        reading the per-backend slot limit from ``config_entries`` with key
        ``translation_concurrency_<name>`` (default 3).
        """
        self._backend_classes[cls.name] = cls

        # Phase A1: register with per-backend concurrency limiter.
        # Failures must never break backend registration -- log and continue.
        try:
            from db.config import get_config_entry
            from translation.concurrency import get_concurrency

            limit_raw = get_config_entry(f"translation_concurrency_{cls.name}")
            limit = int(limit_raw) if limit_raw else 3
            if limit < 1:
                limit = 3
            get_concurrency().register(cls.name, limit)
            logger.debug("Registered translation backend: %s (concurrency=%d)", cls.name, limit)
        except Exception:
            logger.warning("Failed to register concurrency limit for %s", cls.name, exc_info=True)
            logger.debug("Registered translation backend: %s (concurrency default)", cls.name)

    def get_backend(self, name: str) -> TranslationBackend | None:
        """Get or create a backend instance by name (lazy, thread-safe creation).

        Config is loaded from config_entries DB table using
        backend.<name>.<key> namespacing. For Ollama, falls back to
        Pydantic Settings values (migration compatibility).
        """
        with self._backends_lock:
            if name in self._backends:
                return self._backends[name]

            cls = self._backend_classes.get(name)
            if not cls:
                logger.warning("Unknown translation backend: %s", name)
                return None

            config = self._load_backend_config(name)
            try:
                instance = cls(**config)
                self._backends[name] = instance
                logger.info("Created translation backend instance: %s", name)
                return instance
            except Exception as e:
                logger.error("Failed to create backend %s: %s", name, e)
                return None

    def get_all_backends(self) -> list[dict]:
        """Return info about all registered backends.

        Returns:
            List of dicts with name, display_name, config_fields,
            configured status, and supports_* flags.
        """
        result = []
        for name, cls in self._backend_classes.items():
            # Check if this backend has config in config_entries
            config = self._load_backend_config(name)
            has_config = bool(config)

            result.append(
                {
                    "name": cls.name,
                    "display_name": cls.display_name,
                    "config_fields": cls.config_fields,
                    "configured": has_config,
                    "supports_glossary": cls.supports_glossary,
                    "supports_batch": cls.supports_batch,
                    "max_batch_size": cls.max_batch_size,
                }
            )
        return result

    def translate_with_fallback(
        self,
        lines: list[str],
        source_lang: str,
        target_lang: str,
        fallback_chain: list[str],
        glossary_entries: list[dict] | None = None,
        *,
        lookback: list[str] | None = None,
        lookahead: list[str] | None = None,
    ) -> TranslationResult:
        """Try each backend in the fallback chain until one succeeds.

        Uses circuit breakers to skip known-failing backends. Records
        success/failure stats for each attempt.

        Args:
            lines: Subtitle lines to translate
            source_lang: ISO 639-1 source language code
            target_lang: ISO 639-1 target language code
            fallback_chain: Ordered list of backend names to try
            glossary_entries: Optional glossary terms
            lookback: Optional lookback lines forwarded to backends as
                context-only (LLM backends consume; rule-based backends
                ignore). See :meth:`TranslationBackend.translate_batch`.
            lookahead: Optional lookahead lines, same semantics as lookback.

        Returns:
            TranslationResult from the first successful backend,
            or a failure result if all backends fail
        """
        last_error = None
        attempted = 0

        for backend_name in fallback_chain:
            # Check circuit breaker
            cb = self._get_circuit_breaker(backend_name)
            if not cb.allow_request():
                logger.info("Skipping backend %s (circuit breaker OPEN)", backend_name)
                continue

            backend = self.get_backend(backend_name)
            if not backend:
                logger.warning(
                    "Backend %r in fallback chain is not registered/instantiable — skipping",
                    backend_name,
                )
                continue

            attempted += 1

            try:
                start_time = time.time()
                result = backend.translate_batch(
                    lines,
                    source_lang,
                    target_lang,
                    glossary_entries,
                    lookback=lookback,
                    lookahead=lookahead,
                )
                elapsed_ms = (time.time() - start_time) * 1000

                if result.success:
                    # Update response_time_ms if the backend didn't set it
                    if result.response_time_ms == 0:
                        result.response_time_ms = elapsed_ms
                    cb.record_success()
                    self._record_success(backend_name, result)
                    return result
                else:
                    last_error = result.error
                    cb.record_failure()
                    self._record_failure(backend_name, result.error or "Unknown error")
            except Exception as e:
                last_error = str(e)
                cb.record_failure()
                self._record_failure(backend_name, str(e))
                logger.warning("Backend %s failed: %s", backend_name, e)

        if attempted == 0:
            # No backend ever ran: chain empty, all unregistered, or all
            # circuit-open. "Last error: None" was actively misleading here.
            error = (
                f"No usable translation backend in fallback chain {list(fallback_chain)} "
                "(none registered/configured, or all circuit breakers open). "
                "Check the language profile's translation_backend / fallback_chain."
            )
        else:
            error = f"All backends failed. Last error: {last_error}"

        return TranslationResult(
            translated_lines=[],
            backend_name="none",
            error=error,
            success=False,
        )

    def evaluate_line_quality(
        self,
        source_text: str,
        translated_text: str,
        source_lang: str,
        target_lang: str,
        fallback_chain: list[str],
    ) -> int:
        """Evaluate translation quality for a single line using the first available LLM backend.

        Sends a short evaluation prompt to the primary (first available) LLM backend
        and parses a 0-100 quality score from the response. Falls back to
        DEFAULT_QUALITY_SCORE (50) on any error to avoid blocking translation.

        Only backends that use LLM inference (Ollama, OpenAI-compatible) support
        evaluation -- rule-based backends (DeepL, LibreTranslate, Google) do not
        generate evaluation responses and are skipped.

        Args:
            source_text: Original source subtitle line
            translated_text: Translated subtitle line
            source_lang: ISO 639-1 source language code
            target_lang: ISO 639-1 target language code
            fallback_chain: Backend names to try in order (same as translation chain)

        Returns:
            Integer quality score 0-100; DEFAULT_QUALITY_SCORE (50) on failure
        """
        from translation.llm_utils import (
            DEFAULT_QUALITY_SCORE,
            build_evaluation_prompt,
            parse_quality_score,
        )

        # Only LLM-based backends can evaluate; skip rule-based translation services
        _LLM_BACKENDS = {"ollama", "openai_compat"}

        prompt = build_evaluation_prompt(source_text, translated_text, source_lang, target_lang)

        for backend_name in fallback_chain:
            if backend_name not in _LLM_BACKENDS:
                continue

            cb = self._get_circuit_breaker(backend_name)
            if not cb.allow_request():
                continue

            backend = self.get_backend(backend_name)
            if backend is None:
                continue

            try:
                raw_response = self._call_backend_raw(backend, prompt)
                if raw_response is not None:
                    score = parse_quality_score(raw_response)
                    logger.debug(
                        "Quality eval via %s: score=%d for %r -> %r",
                        backend_name,
                        score,
                        source_text[:40],
                        translated_text[:40],
                    )
                    return score
            except Exception as exc:
                logger.debug("Quality eval failed via %s: %s", backend_name, exc)
                continue

        logger.debug(
            "No LLM backend available for quality eval, using default score %d",
            DEFAULT_QUALITY_SCORE,
        )
        return DEFAULT_QUALITY_SCORE

    def _call_backend_raw(self, backend, prompt: str) -> "str | None":
        """Call a backend with a raw prompt and return the raw text response.

        Supports Ollama (_call_ollama) and OpenAI-compatible (_call_openai) backends.
        Returns None if the backend does not expose a raw call method.

        Args:
            backend: A TranslationBackend instance
            prompt: Raw prompt string to send to the LLM

        Returns:
            Raw response text or None if unsupported
        """
        if hasattr(backend, "_call_ollama"):
            return backend._call_ollama(prompt)
        if hasattr(backend, "_call_openai"):
            return backend._call_openai(prompt)
        return None

    def invalidate_backend(self, name: str) -> None:
        """Remove cached backend instance (for config changes)."""
        self._backends.pop(name, None)
        logger.info("Invalidated backend instance: %s", name)

    def _load_backend_config(self, name: str) -> dict:
        """Load backend config from config_entries DB table.

        Keys are namespaced as backend.<name>.<key>. For Ollama, falls back
        to Pydantic Settings values if no config_entries exist (migration path).

        Returns:
            Flat dict of config key-value pairs
        """
        config = {}
        try:
            from db.config import get_all_config_entries

            all_entries = get_all_config_entries()
            prefix = f"backend.{name}."
            for key, value in all_entries.items():
                if key.startswith(prefix):
                    short_key = key[len(prefix) :]
                    config[short_key] = value
        except Exception as e:
            logger.debug("Could not load config_entries for backend %s: %s", name, e)

        # For Ollama: fall back to Pydantic Settings if no config_entries found
        if name == "ollama" and not config:
            try:
                from config import get_settings

                settings = get_settings()
                config = {
                    "url": settings.ollama_url,
                    "model": settings.ollama_model,
                    "temperature": str(settings.temperature),
                    "request_timeout": str(settings.request_timeout),
                    "max_retries": str(settings.max_retries),
                    "backoff_base": str(settings.backoff_base),
                    "batch_size": str(settings.batch_size),
                }
            except Exception:
                pass

        return config

    def _get_circuit_breaker(self, name: str) -> CircuitBreaker:
        """Get or create a circuit breaker for a backend (thread-safe)."""
        with self._backends_lock:
            if name not in self._circuit_breakers:
                try:
                    from config import get_settings

                    settings = get_settings()
                    threshold = settings.circuit_breaker_failure_threshold
                    cooldown = settings.circuit_breaker_cooldown_seconds
                except Exception:
                    threshold = 5
                    cooldown = 60
                self._circuit_breakers[name] = CircuitBreaker(
                    name=f"translation:{name}",
                    failure_threshold=threshold,
                    cooldown_seconds=cooldown,
                )
            return self._circuit_breakers[name]

    def _record_success(self, backend_name: str, result: TranslationResult) -> None:
        """Record successful translation in backend stats."""
        try:
            from db.translation import record_backend_success

            record_backend_success(
                backend_name,
                result.response_time_ms,
                result.characters_used,
            )
        except Exception as e:
            logger.debug("Failed to record backend success: %s", e)

    def _record_failure(self, backend_name: str, error: str) -> None:
        """Record failed translation in backend stats."""
        try:
            from db.translation import record_backend_failure

            record_backend_failure(backend_name, error)
        except Exception as e:
            logger.debug("Failed to record backend failure: %s", e)


# ─── Singleton ────────────────────────────────────────────────────────────────

_manager: TranslationManager | None = None
_manager_lock = threading.Lock()


def get_translation_manager() -> TranslationManager:
    """Get or create the singleton TranslationManager instance (thread-safe)."""
    global _manager
    if _manager is None:
        with _manager_lock:
            if _manager is None:
                _manager = TranslationManager()
                _register_builtin_backends(_manager)
    return _manager


def invalidate_translation_manager() -> None:
    """Destroy the singleton instance (for testing or config reload)."""
    global _manager
    _manager = None


def _register_builtin_backends(manager: TranslationManager) -> None:
    """Register all built-in translation backends."""
    from translation.ollama import OllamaBackend

    manager.register_backend(OllamaBackend)

    # DeepL: optional dependency (deepl package may not be installed)
    try:
        from translation.deepl_backend import DeepLBackend

        manager.register_backend(DeepLBackend)
    except ImportError:
        logger.info("DeepL backend not available (deepl package not installed)")

    # LibreTranslate: uses stdlib requests (always available)
    from translation.libretranslate import LibreTranslateBackend

    manager.register_backend(LibreTranslateBackend)

    # OpenAI-compatible: optional dependency (openai package may not be installed)
    try:
        from translation.openai_compat import OpenAICompatBackend

        manager.register_backend(OpenAICompatBackend)
    except ImportError:
        logger.info("OpenAI-compatible backend not available (openai package not installed)")

    # Google Cloud Translation: optional dependency (google-cloud-translate may not be installed)
    try:
        from translation.google_translate import GoogleTranslateBackend

        manager.register_backend(GoogleTranslateBackend)
    except ImportError:
        logger.info(
            "Google Translation backend not available (google-cloud-translate package not installed)"
        )

    # Claude: optional dependency (anthropic package may not be installed)
    try:
        from translation.claude import ClaudeBackend

        manager.register_backend(ClaudeBackend)
    except ImportError:
        logger.info("Claude backend not available (anthropic package not installed)")

    # Gemini: optional dependency (google-generativeai package may not be installed)
    try:
        from translation.gemini import GeminiBackend

        manager.register_backend(GeminiBackend)
    except ImportError:
        logger.info("Gemini backend not available (google-generativeai package not installed)")

    # DeepSeek: optional dependency (openai package may not be installed)
    try:
        from translation.deepseek import DeepSeekBackend

        manager.register_backend(DeepSeekBackend)
    except ImportError:
        logger.info("DeepSeek backend not available (openai package not installed)")

    # Mistral: optional dependency (mistralai package may not be installed)
    try:
        from translation.mistral import MistralBackend

        manager.register_backend(MistralBackend)
    except ImportError:
        logger.info("Mistral backend not available (mistralai package not installed)")

    # ChatGPT: optional dependency (openai package may not be installed)
    try:
        from translation.chatgpt import ChatGPTBackend

        manager.register_backend(ChatGPTBackend)
    except ImportError:
        logger.info("ChatGPT backend not available (openai package not installed)")

    # Azure Translator: optional dependency (azure-cognitiveservices-language-translator may not be installed)
    try:
        from translation.azure_translator import AzureTranslatorBackend

        manager.register_backend(AzureTranslatorBackend)
    except ImportError:
        logger.info(
            "Azure Translator backend not available (azure-cognitiveservices-language-translator package not installed)"
        )

    # MyMemory: uses stdlib requests (always available)
    try:
        from translation.mymemory import MyMemoryBackend

        manager.register_backend(MyMemoryBackend)
    except ImportError:
        logger.info("MyMemory backend not available")
