"""LibreTranslate translation backend using REST API.

Self-hosted open-source machine translation. Translates line-by-line
via the /translate endpoint. No glossary support.
"""

import logging

import requests

from translation.base import TranslationBackend, TranslationResult

logger = logging.getLogger(__name__)


class LibreTranslateBackend(TranslationBackend):
    """LibreTranslate backend with per-line translation.

    Connects to a self-hosted LibreTranslate instance via REST API.
    Each line is translated individually to guarantee 1:1 line mapping.
    """

    name = "libretranslate"
    display_name = "LibreTranslate (Self-Hosted)"
    supports_glossary = False
    supports_batch = False
    max_batch_size = 1  # Translate one line at a time

    config_fields = [
        {
            "key": "url",
            "label": "LibreTranslate URL",
            "type": "text",
            "required": True,
            "default": "http://libretranslate:5000",
            "help": "LibreTranslate API endpoint",
        },
        {
            "key": "api_key",
            "label": "API Key (optional)",
            "type": "password",
            "required": False,
            "default": "",
            "help": "Only needed for public instances",
        },
        {
            "key": "request_timeout",
            "label": "Timeout (seconds)",
            "type": "number",
            "required": False,
            "default": "30",
            "help": "Request timeout per line",
        },
    ]

    def translate_batch(
        self,
        lines: list[str],
        source_lang: str,
        target_lang: str,
        glossary_entries: list[dict] | None = None,
    ) -> TranslationResult:
        """Translate lines one-by-one via LibreTranslate REST API.

        Args:
            lines: Subtitle text lines to translate
            source_lang: ISO 639-1 source language code
            target_lang: ISO 639-1 target language code
            glossary_entries: Ignored (LibreTranslate has no glossary support)

        Returns:
            TranslationResult with translated lines
        """
        url = self.config.get("url", "http://libretranslate:5000").rstrip("/")
        api_key = self.config.get("api_key", "")
        timeout = int(self.config.get("request_timeout", 30))

        translated = []
        try:
            for line in lines:
                payload = {
                    "q": line,
                    "source": source_lang,
                    "target": target_lang,
                    "format": "text",
                }
                if api_key:
                    payload["api_key"] = api_key

                resp = requests.post(
                    f"{url}/translate",
                    json=payload,
                    timeout=timeout,
                )
                resp.raise_for_status()
                data = resp.json()
                translated.append(data.get("translatedText", line))

            return TranslationResult(
                translated_lines=translated,
                backend_name=self.name,
                characters_used=sum(len(line) for line in lines),
            )
        except Exception as e:
            logger.error("LibreTranslate translation failed: %s", e)
            return TranslationResult(
                translated_lines=[],
                backend_name=self.name,
                error=str(e),
                success=False,
            )

    def health_check(self) -> tuple[bool, str]:
        """Check LibreTranslate availability by querying /languages."""
        url = self.config.get("url", "http://libretranslate:5000").rstrip("/")
        try:
            resp = requests.get(f"{url}/languages", timeout=10)
            if resp.status_code == 200:
                langs = resp.json()
                return True, f"OK ({len(langs)} languages available)"
            return False, f"HTTP {resp.status_code}"
        except Exception as e:
            return False, str(e)

    def get_usage(self) -> dict:
        """LibreTranslate has no usage tracking."""
        return {}

    def get_config_fields(self) -> list[dict]:
        """Return config field definitions for the Settings UI."""
        return self.config_fields
