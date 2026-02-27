"""Abstract base class for translation backends and shared data models.

All translation backends implement the same interface: translate a batch of
subtitle lines from source to target language. Adapted from the SubtitleProvider
ABC pattern in providers/base.py.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class TranslationResult:
    """Result from a backend translation call."""

    translated_lines: list[str] = field(default_factory=list)
    backend_name: str = ""
    response_time_ms: float = 0
    characters_used: int = 0
    error: str | None = None
    success: bool = True


class TranslationBackend(ABC):
    """Abstract base class for translation backends.

    Providers implement three required methods (translate_batch, health_check,
    get_config_fields) and one optional method (get_usage).

    Class-level attributes for config UI and manager orchestration:
        name: Unique backend identifier (lowercase, e.g. "ollama", "deepl")
        display_name: Human-readable name for Settings UI
        config_fields: Declarative config field definitions for dynamic UI forms.
            Each dict: {"key": str, "label": str, "type": "text"|"password"|"number",
                        "required": bool, "default": str, "help": str}
        supports_glossary: Whether this backend supports glossary/terminology
        supports_batch: Whether translate_batch handles multiple lines natively
        max_batch_size: Maximum lines per batch call (0 = unlimited)
    """

    name: str = "unknown"
    display_name: str = "Unknown"
    config_fields: list[dict] = []
    supports_glossary: bool = False
    supports_batch: bool = True
    max_batch_size: int = 0  # 0 = no limit

    def __init__(self, **config):
        self.config = config

    @abstractmethod
    def translate_batch(
        self,
        lines: list[str],
        source_lang: str,
        target_lang: str,
        glossary_entries: list[dict] | None = None,
    ) -> TranslationResult:
        """Translate a batch of subtitle lines.

        Args:
            lines: List of subtitle text lines to translate
            source_lang: ISO 639-1 source language code
            target_lang: ISO 639-1 target language code
            glossary_entries: Optional list of {source_term, target_term} dicts

        Returns:
            TranslationResult with translated_lines in same order as input
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
    def get_config_fields(self) -> list[dict]:
        """Return config field definitions for the Settings UI.

        Returns:
            List of field dicts with key, label, type, required, default, help
        """
        ...

    def get_usage(self) -> dict:
        """Return usage/quota information if available.

        Override in backends that track usage (e.g. DeepL character count).

        Returns:
            Dict with backend-specific usage info (empty by default)
        """
        return {}
