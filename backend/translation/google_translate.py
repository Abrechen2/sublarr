"""Google Cloud Translation v3 backend.

Uses the official Google Cloud Translation v3 SDK for enterprise-grade
translation with native glossary support. Requires a Google Cloud project
with the Translation API enabled and service account credentials.
"""

import logging
import os

from translation.base import TranslationBackend, TranslationResult

logger = logging.getLogger(__name__)

# Import guard: google-cloud-translate is optional
try:
    from google.cloud import translate_v3

    _HAS_GOOGLE = True
except ImportError:
    _HAS_GOOGLE = False
    translate_v3 = None
    logger.warning(
        "google-cloud-translate package not installed -- Google backend unavailable. "
        "Install with: pip install google-cloud-translate>=3.10.0"
    )


class GoogleTranslateBackend(TranslationBackend):
    """Google Cloud Translation v3 backend.

    Uses the official v3 SDK with project-level authentication via service
    account credentials (JSON file or GOOGLE_APPLICATION_CREDENTIALS env var).

    Config values are loaded from config_entries (backend.google.*)
    by the TranslationManager.
    """

    name = "google"
    display_name = "Google Cloud Translation"
    supports_glossary = True  # Native API support
    supports_batch = True
    max_batch_size = 1024

    config_fields = [
        {
            "key": "project_id",
            "label": "Project ID",
            "type": "text",
            "required": True,
            "default": "",
            "help": "Google Cloud project ID with Translation API enabled",
        },
        {
            "key": "credentials_path",
            "label": "Credentials Path",
            "type": "text",
            "required": False,
            "default": "",
            "help": "Path to service account JSON file, or set GOOGLE_APPLICATION_CREDENTIALS env var",
        },
        {
            "key": "location",
            "label": "Location",
            "type": "text",
            "required": False,
            "default": "global",
            "help": "Google Cloud region (default: global)",
        },
    ]

    def __init__(self, **config):
        super().__init__(**config)

    @property
    def _project_id(self) -> str:
        return self.config.get("project_id", "")

    @property
    def _credentials_path(self) -> str:
        return self.config.get("credentials_path", "")

    @property
    def _location(self) -> str:
        return self.config.get("location", "global")

    @property
    def _parent(self) -> str:
        return f"projects/{self._project_id}/locations/{self._location}"

    def _create_client(self) -> "translate_v3.TranslationServiceClient":
        """Create a Google Cloud Translation client.

        Sets GOOGLE_APPLICATION_CREDENTIALS env var if credentials_path
        is configured before creating the client.
        """
        if not _HAS_GOOGLE:
            raise RuntimeError(
                "google-cloud-translate package not installed. "
                "Install with: pip install google-cloud-translate>=3.10.0"
            )

        # Set credentials path in environment if configured
        if self._credentials_path:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = self._credentials_path

        return translate_v3.TranslationServiceClient()

    def translate_batch(
        self,
        lines: list[str],
        source_lang: str,
        target_lang: str,
        glossary_entries: list[dict] | None = None,
    ) -> TranslationResult:
        """Translate a batch of subtitle lines via Google Cloud Translation API.

        Uses the v3 translate_text endpoint which supports batch translation
        natively (up to 1024 segments per request).
        """
        if not lines:
            return TranslationResult(
                translated_lines=[],
                backend_name=self.name,
                success=True,
            )

        import time

        start_time = time.time()

        try:
            client = self._create_client()

            response = client.translate_text(
                request={
                    "parent": self._parent,
                    "contents": lines,
                    "mime_type": "text/plain",
                    "source_language_code": source_lang,
                    "target_language_code": target_lang,
                }
            )

            translated_lines = [t.translated_text for t in response.translations]
            elapsed_ms = (time.time() - start_time) * 1000

            return TranslationResult(
                translated_lines=translated_lines,
                backend_name=self.name,
                response_time_ms=elapsed_ms,
                characters_used=sum(len(l) for l in lines),
                success=True,
            )

        except RuntimeError as e:
            # Package not installed
            return TranslationResult(
                translated_lines=[],
                backend_name=self.name,
                error=str(e),
                success=False,
            )
        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            logger.error("Google Translation failed: %s", e)
            return TranslationResult(
                translated_lines=[],
                backend_name=self.name,
                response_time_ms=elapsed_ms,
                error=f"Google Translation error: {e}",
                success=False,
            )

    def health_check(self) -> tuple[bool, str]:
        """Check if Google Cloud Translation is reachable and configured."""
        try:
            client = self._create_client()
            response = client.get_supported_languages(request={"parent": self._parent})
            lang_count = len(response.languages)
            return True, f"OK ({lang_count} languages supported)"
        except RuntimeError as e:
            return False, str(e)
        except Exception as e:
            error_msg = str(e)
            if "DefaultCredentialsError" in type(e).__name__ or "credentials" in error_msg.lower():
                return False, f"Credentials error: {error_msg}"
            return False, f"Health check failed: {error_msg}"

    def get_config_fields(self) -> list[dict]:
        """Return config field definitions for the Settings UI."""
        return self.config_fields

    def get_usage(self) -> dict:
        """Google uses billing-based quota -- no per-request usage tracking."""
        return {}
