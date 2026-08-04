"""DeepL translation backend using the official deepl Python SDK.

Supports both Free and Pro plans (auto-detected from API key suffix).
Native glossary support with caching for repeated translations.
"""

import concurrent.futures
import hashlib
import json
import logging

from translation.base import TranslationBackend, TranslationResult
from translation.concurrency import get_concurrency

logger = logging.getLogger(__name__)

# Import guard: deepl is an optional dependency
try:
    import deepl

    _DEEPL_AVAILABLE = True
except ImportError:
    _DEEPL_AVAILABLE = False
    logger.warning(
        "deepl package not installed -- DeepL backend will not be available. "
        "Install with: pip install deepl"
    )


# DeepL language code mapping (ISO 639-1 -> DeepL codes)
_DEEPL_LANG_MAP = {
    "en": "EN",
    "de": "DE",
    "fr": "FR",
    "es": "ES",
    "it": "IT",
    "ja": "JA",
    "zh": "ZH",
    "ko": "KO",
    "pt": "PT",
    "ru": "RU",
    "pl": "PL",
    "nl": "NL",
    "sv": "SV",
    "da": "DA",
    "fi": "FI",
    "cs": "CS",
    "hu": "HU",
    "tr": "TR",
    "el": "EL",
    "ro": "RO",
    "bg": "BG",
    "sk": "SK",
    "sl": "SL",
    "lt": "LT",
    "lv": "LV",
    "et": "ET",
    "id": "ID",
    "uk": "UK",
    "nb": "NB",  # Norwegian Bokmal
    "ar": "AR",
}


# DeepL's source and target vocabularies differ for the languages that have
# regional variants. As a *target*, bare "EN" and "PT" are rejected outright
# ('target_lang="EN" is deprecated, please use "EN-GB" or "EN-US" instead');
# as a *source*, only the bare code is accepted and the variant is rejected.
# One map cannot serve both directions — hence the target-side overrides.
_DEEPL_TARGET_OVERRIDES = {
    "en": "EN-US",
    "pt": "PT-BR",  # Default to Brazilian Portuguese
}


def _to_deepl_lang(iso_code: str, *, target: bool = False) -> str:
    """Map ISO 639-1 language code to DeepL language code.

    DeepL uses uppercase codes with some regional variants (EN-US, PT-BR).
    Falls back to uppercased ISO code for unmapped languages.

    Args:
        iso_code: ISO 639-1 code, case-insensitive.
        target: True when the code is used as ``target_lang``, which
            requires the regional variant for English and Portuguese.
    """
    code = iso_code.lower()
    if target and code in _DEEPL_TARGET_OVERRIDES:
        return _DEEPL_TARGET_OVERRIDES[code]
    return _DEEPL_LANG_MAP.get(code, iso_code.upper())


class DeepLBackend(TranslationBackend):
    """DeepL translation backend with glossary support.

    Uses the official deepl Python SDK. Auto-detects Free vs Pro plan
    from the API key suffix (:fx = Free).
    """

    name = "deepl"
    display_name = "DeepL"
    supports_glossary = True
    supports_batch = True
    max_batch_size = 50  # DeepL limit: 50 texts per request
    # The deepl SDK's own backoff/retry has no reliable upper bound in
    # practice — under concurrent load we observed calls hang indefinitely
    # (TCP socket stuck in CLOSE_WAIT with unread bytes, no exception ever
    # raised). _run_with_timeout() below abandons the call past this many
    # seconds rather than trusting the SDK to time out on its own.
    timeout_s = 60

    config_fields = [
        {
            "key": "api_key",
            "label": "API Key",
            "type": "password",
            "required": True,
            "default": "",
            "help": "DeepL API key (Free keys end with :fx)",
        },
    ]

    def __init__(self, **config):
        super().__init__(**config)
        self._client: object | None = None
        self._glossary_cache: dict[tuple, object] = {}  # key: (source, target, content_hash)

    def _get_client(self):
        """Create or return cached DeepL client (lazy initialization)."""
        if not _DEEPL_AVAILABLE:
            raise RuntimeError("deepl package not installed. Install with: pip install deepl")
        if self._client is None:
            api_key = self.config.get("api_key", "")
            if not api_key:
                raise RuntimeError("DeepL API key not configured")
            self._client = deepl.DeepLClient(auth_key=api_key)
        return self._client

    def _run_with_timeout(self, fn, *args, **kwargs):
        """Run fn in a throwaway thread, abandoning it if it exceeds timeout_s.

        A fresh single-use executor per call (rather than a shared pool) means
        a hung call only leaks one thread — it never blocks subsequent calls,
        which a reused executor's single worker would.
        """
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = executor.submit(fn, *args, **kwargs)
        try:
            return future.result(timeout=self.timeout_s)
        except concurrent.futures.TimeoutError:
            raise TimeoutError(f"DeepL request exceeded {self.timeout_s}s") from None
        finally:
            executor.shutdown(wait=False)

    def translate_batch(
        self,
        lines: list[str],
        source_lang: str,
        target_lang: str,
        glossary_entries: list[dict] | None = None,
        series_context: str | None = None,
        *,
        lookback: list[str] | None = None,
        lookahead: list[str] | None = None,
    ) -> TranslationResult:
        """Translate a batch of lines using DeepL API.

        Args:
            lines: Subtitle text lines to translate
            source_lang: ISO 639-1 source language code
            target_lang: ISO 639-1 target language code
            glossary_entries: Optional glossary terms for consistent terminology
            series_context: Ignored (DeepL has no system-prompt concept)
            lookback: Ignored (DeepL has no system-prompt concept)
            lookahead: Ignored (DeepL has no system-prompt concept)

        Returns:
            TranslationResult with translated lines
        """
        # Non-LLM backends accept context kwargs for a uniform interface,
        # but DeepL's REST contract has no prompt/system concept — drop them.
        del series_context, lookback, lookahead
        if not _DEEPL_AVAILABLE:
            raise RuntimeError("deepl package not installed. Install with: pip install deepl")

        try:
            with get_concurrency().slot(self.name, timeout_s=self.timeout_s):
                client = self._get_client()

                source = _to_deepl_lang(source_lang)
                target = _to_deepl_lang(target_lang, target=True)

                kwargs = {"source_lang": source, "target_lang": target}

                # Handle glossary if entries provided. Glossaries are keyed by
                # the *base* target code — DeepL rejects the regional variant
                # here even though translate_text above requires it.
                if glossary_entries:
                    glossary = self._get_or_create_glossary(
                        source, _to_deepl_lang(target_lang), glossary_entries
                    )
                    if glossary:
                        kwargs["glossary"] = glossary

                results = self._run_with_timeout(client.translate_text, lines, **kwargs)
                translated = [r.text for r in results]

            return TranslationResult(
                translated_lines=translated,
                backend_name=self.name,
                characters_used=sum(len(line) for line in lines),
            )
        except Exception as e:
            logger.error("DeepL translation failed: %s", e)
            return TranslationResult(
                translated_lines=[],
                backend_name=self.name,
                error=str(e),
                success=False,
            )

    def _get_or_create_glossary(
        self,
        source_lang: str,
        target_lang: str,
        entries: list[dict],
    ):
        """Get cached glossary or create a new one on DeepL.

        Args:
            source_lang: DeepL source language code
            target_lang: DeepL target language code
            entries: List of {source_term, target_term} dicts

        Returns:
            DeepL glossary object or None on failure
        """
        # Include content hash in cache key so changed glossary entries create a new glossary
        entries_hash = hashlib.sha256(
            json.dumps(
                sorted(entries, key=lambda e: e.get("source_term", "")),
                sort_keys=True,
            ).encode()
        ).hexdigest()[:16]
        cache_key = (source_lang, target_lang, entries_hash)

        if cache_key in self._glossary_cache:
            return self._glossary_cache[cache_key]

        try:
            client = self._get_client()

            # Build entries dict for DeepL glossary creation
            entries_dict = {
                e["source_term"]: e["target_term"]
                for e in entries
                if e.get("source_term") and e.get("target_term")
            }

            if not entries_dict:
                return None

            glossary_name = f"sublarr_{source_lang}_{target_lang}"
            glossary = self._run_with_timeout(
                client.create_glossary,
                glossary_name,
                source_lang=source_lang,
                target_lang=target_lang,
                entries=entries_dict,
            )

            self._glossary_cache[cache_key] = glossary
            logger.info(
                "Created DeepL glossary '%s' with %d entries",
                glossary_name,
                len(entries_dict),
            )
            return glossary
        except Exception as e:
            logger.warning(
                "Failed to create DeepL glossary for %s->%s: %s",
                source_lang,
                target_lang,
                e,
            )
            return None

    def health_check(self) -> tuple[bool, str]:
        """Check DeepL API availability and report plan type + usage."""
        try:
            client = self._get_client()
            usage = client.get_usage()
            plan = "Free" if self.config.get("api_key", "").endswith(":fx") else "Pro"
            return (
                True,
                f"OK ({plan}, {usage.character.count}/{usage.character.limit} chars)",
            )
        except Exception as e:
            return False, str(e)

    def get_usage(self) -> dict:
        """Return DeepL usage statistics (character count and limit)."""
        try:
            client = self._get_client()
            usage = client.get_usage()
            plan = "Free" if self.config.get("api_key", "").endswith(":fx") else "Pro"
            return {
                "characters_used": usage.character.count,
                "characters_limit": usage.character.limit,
                "plan": plan,
            }
        except Exception:
            return {}

    def get_config_fields(self) -> list[dict]:
        """Return config field definitions for the Settings UI."""
        return self.config_fields
