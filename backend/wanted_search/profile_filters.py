"""Post-search result filtering derived from a LanguageProfile's filter settings."""

import json
import logging

logger = logging.getLogger(__name__)


def apply_must_contain(results: list, must_contain: list[str]) -> list:
    """Keep only results whose release_info contains ALL must_contain terms (AND logic, Bazarr parity)."""
    if not must_contain:
        return results
    terms = [t.lower() for t in must_contain if t.strip()]
    if not terms:
        return results
    filtered = [r for r in results if all(t in r.release_info.lower() for t in terms)]
    logger.debug("mustContain(%s): %d → %d results", terms, len(results), len(filtered))
    return filtered


def apply_must_not_contain(results: list, must_not_contain: list[str]) -> list:
    """Remove results whose release_info contains any must_not_contain term."""
    if not must_not_contain:
        return results
    terms = [t.lower() for t in must_not_contain if t.strip()]
    if not terms:
        return results
    filtered = [r for r in results if not any(t in r.release_info.lower() for t in terms)]
    logger.debug("mustNotContain(%s): %d → %d results", terms, len(results), len(filtered))
    return filtered


def load_profile_filters(profile) -> dict:
    """Extract filter config from a LanguageProfile ORM instance (or None).

    Returns a dict with keys:
        must_contain: list[str]
        must_not_contain: list[str]
        cutoff_language: str  (empty = no cutoff)
        audio_exclude_languages: list[str]
        hi_preference: str  (include | prefer | exclude | only)
    """
    if profile is None:
        return {
            "must_contain": [],
            "must_not_contain": [],
            "cutoff_language": "",
            "audio_exclude_languages": [],
            "hi_preference": "include",
        }

    def _load(attr: str, default: str = "[]") -> list:
        raw = getattr(profile, attr, default) or default
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, TypeError):
            return []

    return {
        "must_contain": _load("must_contain_json"),
        "must_not_contain": _load("must_not_contain_json"),
        "cutoff_language": getattr(profile, "cutoff_language", "") or "",
        "audio_exclude_languages": _load("audio_exclude_languages_json"),
        "hi_preference": getattr(profile, "hi_preference", "include") or "include",
    }
