"""Whisper-Subgen subtitle provider -- DEPRECATED.

This provider is deprecated. Use the Whisper backend system
(whisper/subgen_backend.py) instead. This provider will be removed in v1.0.0.

The new Whisper backend system provides:
- Queue-based transcription with concurrency control
- WebSocket progress tracking
- Multiple backend support (faster-whisper, Subgen)
- Persistent job tracking in the database

License: GPL-3.0
"""

import warnings
import logging

from providers.base import (
    SubtitleProvider,
    SubtitleResult,
    SubtitleFormat,
    VideoQuery,
    ProviderError,
)
from providers import register_provider

warnings.warn(
    "WhisperSubgenProvider is deprecated. Use the Whisper backend system "
    "(whisper/subgen_backend.py) instead. This provider will be removed in v1.0.0.",
    DeprecationWarning,
    stacklevel=2,
)

logger = logging.getLogger(__name__)

# All Whisper-supported languages (ISO 639-1 codes)
WHISPER_LANGUAGES = {
    "en", "ja", "de", "fr", "es", "it", "pt", "ru", "zh", "ko",
    "ar", "nl", "pl", "sv", "cs", "hu", "tr", "th", "vi", "id",
    "hi", "uk", "ro", "el", "da", "fi", "no", "sk", "hr", "bg",
    "lt", "lv", "sl", "et", "ms", "he", "ca", "ta", "te", "bn",
    "ml", "ka", "sr", "mk", "is", "gl", "eu", "af", "cy", "be",
    "ur", "sw", "tl", "fa", "az", "kk", "hy", "my", "ne", "mn",
    "bs", "sq", "lb", "mt",
}


@register_provider
class WhisperSubgenProvider(SubtitleProvider):
    """Whisper-Subgen provider -- DEPRECATED.

    This provider is deprecated. Use the Whisper backend system instead.
    search() returns an empty list; download() raises ProviderError.
    """

    name = "whisper_subgen"
    languages = WHISPER_LANGUAGES

    config_fields = [
        {
            "key": "endpoint",
            "label": "Subgen URL",
            "type": "text",
            "required": True,
            "default": "http://subgen:9000",
        },
        {
            "key": "timeout",
            "label": "Timeout (seconds)",
            "type": "number",
            "required": False,
            "default": "600",
        },
    ]
    rate_limit = (2, 60)
    timeout = 600
    max_retries = 1

    def __init__(self, endpoint: str = "http://subgen:9000", timeout: str = "600", **kwargs):
        super().__init__(**kwargs)
        self.endpoint = endpoint.rstrip("/") if endpoint else "http://subgen:9000"
        try:
            self.config_timeout = int(timeout) if timeout else 600
        except (ValueError, TypeError):
            self.config_timeout = 600

    def initialize(self):
        logger.warning(
            "WhisperSubgenProvider is deprecated. Use the Whisper backend system "
            "(whisper/subgen_backend.py) instead."
        )

    def terminate(self):
        pass

    def health_check(self) -> tuple[bool, str]:
        return False, "WhisperSubgenProvider is deprecated. Use Whisper backend system instead."

    def search(self, query: VideoQuery) -> list[SubtitleResult]:
        """Deprecated: always returns an empty list."""
        logger.warning("WhisperSubgenProvider.search() is deprecated. Use Whisper backend system instead.")
        return []

    def download(self, result: SubtitleResult) -> bytes:
        """Deprecated: always raises ProviderError."""
        raise ProviderError("WhisperSubgenProvider is deprecated. Use Whisper backend system instead.")
