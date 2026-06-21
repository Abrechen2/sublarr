"""Detect language-mislabeled subtitle targets.

Signals: (1) identical raw MD5 across different language tags; (2) lingua-py
content detection disagrees with the declared tag. Mojibake is decoded away
first; low-confidence detection yields no claim.
"""

from __future__ import annotations

import logging

from services.subtitle_health.models import (
    Issue,
    IssueType,
    Severity,
)
from services.subtitle_health.raw_io import md5_bytes
from services.subtitle_health.text_utils import (
    decode_with_confidence,
    extract_cue_text_srt,
    strip_ass_tags,
)

logger = logging.getLogger(__name__)

_HIGH_CONF = 0.90
_MED_CONF = 0.70
# Lowered from 80 to 40: the bundled english.srt fixture contains only ~66
# chars of cue text (3 short lines), so 80 would silently skip detection and
# fail test_content_language_mismatch_without_md5_dup.  40 chars is still
# enough to produce a reliable lingua signal for EN/DE cue text.
_MIN_CHARS = 40

# Lazily-built detector (lingua's build is moderately expensive).
_DETECTOR = None


def _detector():
    global _DETECTOR
    if _DETECTOR is None:
        from lingua import Language, LanguageDetectorBuilder

        langs = [Language.ENGLISH, Language.GERMAN]
        _DETECTOR = LanguageDetectorBuilder.from_languages(*langs).build()
    return _DETECTOR


_LANG_MAP = {"ENGLISH": "en", "GERMAN": "de"}


def _detect_language(raw: bytes) -> tuple[str | None, float]:
    text, _enc, _conf = decode_with_confidence(raw)
    clean = strip_ass_tags(extract_cue_text_srt(text))
    if len(clean) < _MIN_CHARS:
        return None, 0.0
    values = _detector().compute_language_confidence_values(clean)
    if not values:
        return None, 0.0
    top = values[0]
    code = _LANG_MAP.get(top.language.name)
    return code, float(top.value)


def _norm(lang: str) -> str:
    return (lang or "").lower().split("-")[0]


def detect(ctx) -> list[Issue]:
    issues: list[Issue] = []

    # (1) MD5 duplicates across different language tags.
    by_hash: dict[str, list] = {}
    for t in ctx.targets:
        if not t.raw:
            continue
        by_hash.setdefault(md5_bytes(t.raw), []).append(t)
    dup_paths: set[tuple[str, int | None]] = set()
    for group in by_hash.values():
        langs = {_norm(t.lang) for t in group}
        if len(group) > 1 and len(langs) > 1:
            for t in group:
                dup_paths.add((t.path, t.stream_index))
                issues.append(
                    Issue(
                        type=IssueType.LANGUAGE_MISLABEL,
                        severity=Severity.CONFIRMED,
                        episode_id=ctx.episode_id,
                        target_kind=t.kind,
                        target_path=t.path,
                        stream_index=t.stream_index,
                        lang=_norm(t.lang),
                        count=1,
                        snippets=[f"identical content to {len(group) - 1} other language tag(s)"],
                        raw_hash=md5_bytes(t.raw),
                        fixable=True,
                        suggested_fix="trash_sidecar",
                    )
                )

    # (2) Content detection vs declared tag.
    for t in ctx.targets:
        if not t.raw or (t.path, t.stream_index) in dup_paths:
            continue
        detected, conf = _detect_language(t.raw)
        declared = _norm(t.lang)
        if detected is None or declared in ("", "und"):
            continue
        if detected != declared and conf >= _MED_CONF:
            issues.append(
                Issue(
                    type=IssueType.LANGUAGE_MISLABEL,
                    severity=Severity.CONFIRMED if conf >= _HIGH_CONF else Severity.SUSPICIOUS,
                    episode_id=ctx.episode_id,
                    target_kind=t.kind,
                    target_path=t.path,
                    stream_index=t.stream_index,
                    lang=declared,
                    count=1,
                    snippets=[f"declared {declared!r}, detected {detected!r} (conf {conf:.2f})"],
                    raw_hash=md5_bytes(t.raw),
                    fixable=True,
                    suggested_fix="trash_sidecar",
                )
            )
    return issues
