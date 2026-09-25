"""Which languages a genuine sidecar already covers next to a video.

Policy B of the track variant policy removes the embedded main track when a
real sidecar covers its language. "Real" is decided by the download/origin
history, never by the file alone: a machine translation or a file of unknown
origin must never cost the video its genuine embedded track (owner rule
2026-09-13: self-translated is always the last resort).

Two tables carry provenance, and the newer record for a (video, language)
pair decides (owner ruling 2026-09-25):

  - ``subtitle_downloads`` -- provider downloads, manual uploads, machine
    translations. NOT written for extractions: that table backs dashboard
    counts, average score, usage stats and history, and a firehose of
    extraction rows would skew every one of them.
  - ``sidecar_origins`` -- extractions only (``origin="extraction"``),
    written by ``services.embedded_extractor._record_extraction``.
"""

from __future__ import annotations

import os

REAL_SOURCES = frozenset(
    {"provider", "provider_interactive", "provider_source_srt", "manual", "extraction"}
)
_NOT_REAL_PROVIDERS = frozenset({"translation"})
_ORIGIN_KINDS = frozenset({"extraction"})


def _latest_download(video_path: str, language: str):
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


def _latest_origin(video_path: str, language: str):
    from sqlalchemy import select

    from db.models.providers import SidecarOrigin
    from extensions import db

    return db.session.execute(
        select(SidecarOrigin)
        .where(SidecarOrigin.video_path == video_path)
        .where(SidecarOrigin.language == language)
        .order_by(SidecarOrigin.recorded_at.desc(), SidecarOrigin.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def _is_real(video_path: str, language: str) -> bool:
    """Whether the newer of the two provenance records is a "real" one."""
    download = _latest_download(video_path, language)
    origin = _latest_origin(video_path, language)
    if download is None and origin is None:
        return False

    download_at = download.downloaded_at if download is not None else None
    origin_at = origin.recorded_at if origin is not None else None

    if origin_at is not None and (download_at is None or origin_at >= download_at):
        return origin.origin in _ORIGIN_KINDS

    return (download.source or "provider") in REAL_SOURCES and (
        download.provider_name not in _NOT_REAL_PROVIDERS
    )


def _usable(path: str | None, fmt: str) -> bool:
    """Whether the sidecar at ``path`` is a genuine, validated ``fmt`` file.

    Runs the WHOLE file through the same validation
    ``providers.download_manager.save_subtitle`` applies to a freshly
    downloaded subtitle before it is trusted: the binary/executable-content
    guard (``format_validator._validate_subtitle_content``), a content/format
    agreement check (``format_validator.detect_format_from_content``), and
    the structural shape check save_subtitle's own pipeline applies via
    ``subtitle_normalise.normalise_downloaded_content`` ->
    ``subtitle_sanitizer.sanitize_subtitle`` ->
    ``subtitle_sanitizer.validate_content_type`` — so a garbage file saved
    under a subtitle extension (e.g. an HTML error page saved as ``.srt``)
    never counts, no matter what the download history says. Read errors
    (missing file, permission, decode) are never usable.
    """
    if not path or ".forced." in os.path.basename(path).lower():
        return False

    from providers.format_validator import _validate_subtitle_content, detect_format_from_content
    from subtitle_sanitizer import validate_content_type

    try:
        with open(path, "rb") as fh:
            content = fh.read()
    except (OSError, UnicodeDecodeError):
        return False

    if not content:
        return False

    valid, _reason = _validate_subtitle_content(content, fmt)
    if not valid:
        return False

    if detect_format_from_content(content).value != fmt:
        return False

    try:
        return validate_content_type(content, fmt)
    except (OSError, UnicodeDecodeError):
        return False


def real_sidecar_languages(video_path: str, languages: set[str]) -> set[str]:
    """Return the 2-letter codes (of ``languages``) a genuine sidecar covers.

    A language counts only when both hold: a usable, validated sidecar file
    exists on disk (see ``_usable``), and the newer of its download/origin
    history records for (video, language) is "real" (see ``_is_real``).
    Unknown-origin sidecars (no record in either table) and machine
    translations never count.
    """
    from translator import find_existing_target_file

    covered: set[str] = set()
    for lang in languages:
        sidecar = None
        fmt = None
        for candidate_fmt in ("srt", "ass"):
            candidate = find_existing_target_file(video_path, lang, candidate_fmt)
            if candidate:
                sidecar, fmt = candidate, candidate_fmt
                break

        if sidecar is None or not _usable(sidecar, fmt):
            continue
        if _is_real(video_path, lang):
            covered.add(lang)
    return covered
