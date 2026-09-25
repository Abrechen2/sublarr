"""Which languages a genuine sidecar already covers next to a video.

Policy B of the track variant policy removes the embedded main track when a
real sidecar covers its language. "Real" is decided by the download history,
never by the file alone: a machine translation or a file of unknown origin
must never cost the video its genuine embedded track (owner rule 2026-09-13:
self-translated is always the last resort).
"""

from __future__ import annotations

import os

REAL_SOURCES = frozenset(
    {"provider", "provider_interactive", "provider_source_srt", "manual", "extraction"}
)
_NOT_REAL_PROVIDERS = frozenset({"translation"})


def _latest_record(video_path: str, language: str):
    from sqlalchemy import select

    from db.models.providers import SubtitleDownload
    from extensions import db

    return db.session.execute(
        select(SubtitleDownload)
        .where(SubtitleDownload.file_path == video_path)
        .where(SubtitleDownload.language == language)
        .order_by(SubtitleDownload.downloaded_at.desc(), SubtitleDownload.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def _usable(path: str | None) -> bool:
    if not path or ".forced." in os.path.basename(path).lower():
        return False
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return bool(fh.read(4096).strip())
    except OSError:
        return False


def real_sidecar_languages(video_path: str, languages: set[str]) -> set[str]:
    """Return the 2-letter codes (of ``languages``) a genuine sidecar covers.

    A language counts only when both hold: a usable (non-empty, non-forced)
    sidecar file exists on disk, and the latest download-history record for
    (video, language) has a "real" source. Unknown-origin sidecars (no
    history row) and machine translations never count.
    """
    from translator import find_existing_target_file

    covered: set[str] = set()
    for lang in languages:
        sidecar = find_existing_target_file(video_path, lang, "srt") or find_existing_target_file(
            video_path, lang, "ass"
        )
        if not _usable(sidecar):
            continue
        row = _latest_record(video_path, lang)
        if row is None:
            continue
        if (
            row.source or "provider"
        ) in REAL_SOURCES and row.provider_name not in _NOT_REAL_PROVIDERS:
            covered.add(lang)
    return covered
