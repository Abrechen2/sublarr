"""Embedded target-language tracks for display, read from the ffprobe cache.

The scanners probe containers and treat an embedded target ASS as satisfying
the language; the series detail endpoints only looked for sidecar files, so an
episode the scanner had rightly left alone was shown as "No subtitle found"
(Forgejo #35). This module lets a page answer the same question without ever
starting a probe: a series lists 100+ episodes, so only cached probe data — the
scanners fill the cache — is consulted, and a miss simply reports nothing.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_PROBEABLE_CONTAINERS = (".mkv", ".mp4", ".m4v")


def cached_embedded_formats(
    file_paths: list[str], languages: list[str]
) -> dict[str, dict[str, str]]:
    """``{path: {language: "embedded_ass" | "embedded_srt"}}`` from cached probes.

    Only paths with a cache entry whose mtime matches the file are reported.
    Must run where a database session is available (not inside a worker pool
    without an app context).
    """
    from config import get_settings

    if not getattr(get_settings(), "use_embedded_subs", False) or not languages:
        return {}
    probeable = [p for p in file_paths if p and p.lower().endswith(_PROBEABLE_CONTAINERS)]
    if not probeable:
        return {}

    from ass_probe import has_target_language_stream
    from db.cache import get_ffprobe_cache_many

    try:
        cached = get_ffprobe_cache_many(probeable)
    except Exception as exc:  # noqa: BLE001 — display enrichment is best-effort
        logger.warning("embedded track lookup failed: %s", exc)
        return {}

    result: dict[str, dict[str, str]] = {}
    for path, (mtime, probe_data) in cached.items():
        try:
            if os.path.getmtime(path) != mtime:
                continue
        except OSError:
            continue
        for lang in languages:
            embedded = has_target_language_stream(probe_data, lang)
            if embedded in ("ass", "srt"):
                result.setdefault(path, {})[lang] = f"embedded_{embedded}"
    return result


def merge_subtitle_format(sidecar: str | None, embedded: str | None) -> str:
    """Combine a sidecar result with an embedded one, ranked like the scanner.

    An ASS satisfies the language whether it is a file or a track, so an
    embedded ASS outranks a sidecar SRT; otherwise the file on disk wins.
    """
    if sidecar == "ass":
        return "ass"
    if embedded == "embedded_ass":
        return "embedded_ass"
    return sidecar or embedded or ""
