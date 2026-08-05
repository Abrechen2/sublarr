"""Decide which subtitle tracks of one file are foreign.

Shared by the batched sweep and the legacy one-shot executor so the two can
never disagree about what counts as foreign.
"""

import logging

logger = logging.getLogger(__name__)


def expand_keep_languages(raw: list[str]) -> set[str]:
    """Expand keep-language codes to every tag ffprobe might report.

    ``de`` also has to match ``ger`` and ``deu``, or a German track gets
    stripped because the container used a different ISO variant.
    """
    from services.cleanup_executors import _get_language_tags

    keep: set[str] = set()
    for lang in raw or []:
        keep.update(_get_language_tags(str(lang).lower()))
    return keep


def foreign_languages(probe: dict, keep_languages: set[str], keep_und: bool) -> list[str]:
    """Return the languages of subtitle streams that are not kept.

    One entry per stream, so ``len()`` is the track count. Returns an empty
    list for an empty keep set: the "strip everything" guard lives in the
    caller, and this helper must never be the thing that produces it.
    """
    if not keep_languages:
        return []

    foreign: list[str] = []
    for stream in probe.get("streams", []):
        if stream.get("codec_type") != "subtitle":
            continue
        lang = (stream.get("tags", {}).get("language", "und") or "und").lower()
        if lang in keep_languages:
            continue
        if keep_und and lang == "und":
            continue
        foreign.append(lang)
    return foreign
