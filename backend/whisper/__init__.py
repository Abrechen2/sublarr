"""Whisper package -- speech-to-text transcription management.

Provides the WhisperManager singleton which registers backends, manages
the active backend instance with lazy creation, delegates transcription
calls with circuit breaker protection, and tracks progress.
"""

import logging
import time
from collections.abc import Callable

from circuit_breaker import CircuitBreaker
from whisper.base import TranscriptionResult, WhisperBackend

logger = logging.getLogger(__name__)


class WhisperManager:
    """Manages Whisper transcription backends.

    Backend classes are registered at import time. A single active backend
    is used (configured via whisper_backend config entry). Instances are
    created lazily on first use, with config loaded from the config_entries
    DB table using whisper.<name>.<key> namespacing.
    """

    def __init__(self):
        self._backend_classes: dict[str, type[WhisperBackend]] = {}
        self._backend: WhisperBackend | None = None
        self._backend_name: str | None = None
        self._circuit_breaker: CircuitBreaker | None = None

    def register_backend(self, cls: type[WhisperBackend]) -> None:
        """Register a backend class by its name attribute."""
        self._backend_classes[cls.name] = cls
        logger.debug("Registered whisper backend: %s", cls.name)

    def get_backend(self, name: str) -> WhisperBackend | None:
        """Get or create a backend instance by name (lazy creation).

        Config is loaded from config_entries DB table using
        whisper.<name>.<key> namespacing.
        """
        # Return cached instance if same backend
        if self._backend is not None and self._backend_name == name:
            return self._backend

        cls = self._backend_classes.get(name)
        if not cls:
            logger.warning("Unknown whisper backend: %s", name)
            return None

        config = self._load_backend_config(name)
        try:
            instance = cls(**config)
            self._backend = instance
            self._backend_name = name
            logger.info("Created whisper backend instance: %s", name)
            return instance
        except Exception as e:
            logger.error("Failed to create whisper backend %s: %s", name, e)
            return None

    def get_active_backend(self) -> WhisperBackend | None:
        """Get the currently configured active backend.

        Reads whisper_backend config entry to determine which backend to use.
        Defaults to "subgen" if not configured.
        """
        backend_name = self._get_configured_backend_name()
        return self.get_backend(backend_name)

    def get_all_backends(self) -> list[dict]:
        """Return info about all registered backends.

        Returns:
            List of dicts with name, display_name, config_fields,
            configured status, and capability flags.
        """
        result = []
        active_name = self._get_configured_backend_name()

        for name, cls in self._backend_classes.items():
            config = self._load_backend_config(name)
            has_config = bool(config)

            result.append({
                "name": cls.name,
                "display_name": cls.display_name,
                "config_fields": cls.config_fields,
                "configured": has_config,
                "active": name == active_name,
                "supports_gpu": cls.supports_gpu,
                "supports_language_detection": cls.supports_language_detection,
            })
        return result

    def transcribe(
        self,
        audio_path: str,
        language: str = "",
        progress_callback: Callable[[float], None] | None = None,
    ) -> TranscriptionResult:
        """Transcribe audio using the active backend with circuit breaker.

        Args:
            audio_path: Path to the audio file (WAV, 16kHz mono)
            language: ISO 639-1 language code (empty = auto-detect)
            progress_callback: Optional progress callback (0.0 - 1.0)

        Returns:
            TranscriptionResult from the active backend
        """
        backend = self.get_active_backend()
        if not backend:
            return TranscriptionResult(
                success=False,
                error="No whisper backend configured or available",
            )

        # Check circuit breaker
        cb = self._get_circuit_breaker()
        if not cb.allow_request():
            return TranscriptionResult(
                success=False,
                error=f"Whisper backend '{self._backend_name}' circuit breaker is OPEN",
                backend_name=self._backend_name or "",
            )

        try:
            start_time = time.time()
            result = backend.transcribe(audio_path, language, progress_callback=progress_callback)
            elapsed_ms = (time.time() - start_time) * 1000

            if result.success:
                if result.processing_time_ms == 0:
                    result.processing_time_ms = elapsed_ms
                cb.record_success()
            else:
                cb.record_failure()

            return result
        except Exception as e:
            cb.record_failure()
            logger.error("Whisper transcription failed: %s", e)
            return TranscriptionResult(
                success=False,
                error=str(e),
                backend_name=self._backend_name or "",
            )

    def invalidate_backend(self) -> None:
        """Clear cached backend instance (for config changes)."""
        self._backend = None
        self._backend_name = None
        logger.info("Invalidated whisper backend instance")

    def _load_backend_config(self, name: str) -> dict:
        """Load backend config from config_entries DB table.

        Keys are namespaced as whisper.<name>.<key>.

        Returns:
            Flat dict of config key-value pairs
        """
        config = {}
        try:
            from db.config import get_all_config_entries
            all_entries = get_all_config_entries()
            prefix = f"whisper.{name}."
            for key, value in all_entries.items():
                if key.startswith(prefix):
                    short_key = key[len(prefix):]
                    config[short_key] = value
        except Exception as e:
            logger.debug("Could not load config_entries for whisper backend %s: %s", name, e)

        return config

    def _get_configured_backend_name(self) -> str:
        """Read which backend is configured as active.

        Returns:
            Backend name string (defaults to "subgen")
        """
        try:
            from db.config import get_config_entry
            name = get_config_entry("whisper_backend")
            if name and name in self._backend_classes:
                return name
        except Exception:
            pass
        return "subgen"

    def _get_circuit_breaker(self) -> CircuitBreaker:
        """Get or create the circuit breaker for the active backend."""
        if self._circuit_breaker is None:
            try:
                from config import get_settings
                settings = get_settings()
                threshold = settings.circuit_breaker_failure_threshold
                cooldown = settings.circuit_breaker_cooldown_seconds
            except Exception:
                threshold = 5
                cooldown = 60
            self._circuit_breaker = CircuitBreaker(
                name=f"whisper:{self._backend_name or 'unknown'}",
                failure_threshold=threshold,
                cooldown_seconds=cooldown,
            )
        return self._circuit_breaker


# --- Singleton ---

_manager: WhisperManager | None = None


def get_whisper_manager() -> WhisperManager:
    """Get or create the singleton WhisperManager instance."""
    global _manager
    if _manager is None:
        _manager = WhisperManager()
        _register_builtin_backends(_manager)
    return _manager


def invalidate_whisper_manager() -> None:
    """Destroy the singleton instance (for testing or config reload)."""
    global _manager
    _manager = None


def _register_builtin_backends(manager: WhisperManager) -> None:
    """Register all built-in Whisper backends."""
    # faster-whisper: optional dependency (faster_whisper package may not be installed)
    try:
        from whisper.faster_whisper_backend import FasterWhisperBackend
        manager.register_backend(FasterWhisperBackend)
    except ImportError:
        logger.info("Faster Whisper backend not available (faster-whisper package not installed)")

    # Subgen: uses stdlib requests (always available)
    try:
        from whisper.subgen_backend import SubgenBackend
        manager.register_backend(SubgenBackend)
    except ImportError:
        logger.info("Subgen backend not available (module not found)")
