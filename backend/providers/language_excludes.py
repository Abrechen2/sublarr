"""Per-provider language exclusion (#192).

Operators can pin languages to the providers that do them well: e.g. keep
Serbian on Titlovi and stop OpenSubtitles from ever serving its (often
lower-quality) Serbian uploads, while still using OpenSubtitles for English.

The configuration lives in the ``provider_language_excludes_json`` setting as
a JSON object mapping provider name to a list of ISO 639-1 codes::

    {"opensubtitles": ["sr", "hr"], "subdl": ["en"]}

``parse_language_excludes`` is the single reader; it validates defensively
(config text is user input) and never raises — a malformed value means "no
exclusions" rather than a broken search path.
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)


def parse_language_excludes(raw: str) -> dict[str, frozenset[str]]:
    """Parse the excludes setting into ``{provider_name: {lang, ...}}``.

    Language codes are normalised to stripped lowercase. Entries that are not
    a list of strings are dropped (with a log line, so a typo in hand-edited
    config is visible instead of silently ignored).
    """
    if not raw or not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning("provider_language_excludes_json is not valid JSON: %s", e)
        return {}
    if not isinstance(data, dict):
        logger.warning(
            "provider_language_excludes_json must be a JSON object, got %s",
            type(data).__name__,
        )
        return {}

    excludes: dict[str, frozenset[str]] = {}
    for provider, langs in data.items():
        if not isinstance(provider, str) or not isinstance(langs, list):
            logger.warning(
                "provider_language_excludes_json: ignoring entry %r (expected a list of codes)",
                provider,
            )
            continue
        normalized = frozenset(
            code.strip().lower() for code in langs if isinstance(code, str) and code.strip()
        )
        if normalized:
            excludes[provider] = normalized
    return excludes
