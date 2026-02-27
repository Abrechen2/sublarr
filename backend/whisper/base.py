"""Abstract base class for Whisper speech-to-text backends and shared data models.

All Whisper backends implement the same interface: transcribe audio to SRT.
Adapted from the TranslationBackend ABC pattern in translation/base.py.
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class TranscriptionResult:
    """Result from a backend transcription call."""

    srt_content: str = ""
    detected_language: str = ""
    language_probability: float = 0.0
    duration_seconds: float = 0.0
    segment_count: int = 0
    backend_name: str = ""
    processing_time_ms: float = 0.0
    error: str | None = None
    success: bool = True


class WhisperBackend(ABC):
    """Abstract base class for Whisper transcription backends.

    Providers implement three required methods (transcribe, health_check,
    get_available_models).

    Class-level attributes for config UI and manager orchestration:
        name: Unique backend identifier (lowercase, e.g. "faster_whisper", "subgen")
        display_name: Human-readable name for Settings UI
        config_fields: Declarative config field definitions for dynamic UI forms.
            Each dict: {"key": str, "label": str, "type": "text"|"password"|"number",
                        "required": bool, "default": str, "help": str}
        supports_gpu: Whether this backend supports GPU acceleration
        supports_language_detection: Whether this backend can auto-detect language
    """

    name: str = "unknown"
    display_name: str = "Unknown"
    config_fields: list[dict] = []
    supports_gpu: bool = False
    supports_language_detection: bool = True

    def __init__(self, **config):
        self.config = config

    @abstractmethod
    def transcribe(
        self,
        audio_path: str,
        language: str = "",
        task: str = "transcribe",
        progress_callback: Callable[[float], None] | None = None,
    ) -> TranscriptionResult:
        """Transcribe audio file to SRT subtitle content.

        Args:
            audio_path: Path to the audio file (WAV, 16kHz mono)
            language: ISO 639-1 language code (empty = auto-detect)
            task: "transcribe" or "translate" (translate = transcribe + translate to English)
            progress_callback: Optional callback with progress ratio (0.0 - 1.0)

        Returns:
            TranscriptionResult with SRT content and metadata
        """
        ...

    @abstractmethod
    def health_check(self) -> tuple[bool, str]:
        """Check if the backend is reachable and configured correctly.

        Returns:
            (is_healthy, message) tuple
        """
        ...

    @abstractmethod
    def get_available_models(self) -> list[dict]:
        """Return list of available models for this backend.

        Returns:
            List of model dicts with name, size, and other info
        """
        ...

    def get_config_fields(self) -> list[dict]:
        """Return config field definitions for the Settings UI.

        Returns:
            List of field dicts with key, label, type, required, default, help
        """
        return self.config_fields
