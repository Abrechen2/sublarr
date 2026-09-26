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
  - ``sidecar_origins`` -- extractions (``origin="extraction"``, written by
    ``services.embedded_extractor._record_extraction``) and syncs of a
    genuine sidecar (``origin="resync"``, see ``vouch_before_rewrite``).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

logger = logging.getLogger(__name__)

REAL_SOURCES = frozenset(
    {"provider", "provider_interactive", "provider_source_srt", "manual", "extraction"}
)
_NOT_REAL_PROVIDERS = frozenset({"translation"})
_RESYNC = "resync"
_ORIGIN_KINDS = frozenset({"extraction", _RESYNC})
_SIDECAR_FORMATS = ("srt", "ass")
_VIDEO_EXTS = (".mkv", ".mp4", ".m4v", ".webm", ".mov", ".avi", ".ts")
# Rows that describe the MAIN sidecar. A forced/hi row describes
# ``.de.forced.srt`` and says nothing about the ``.de.srt`` next to it.
_MAIN_SUBTITLE_TYPES = (None, "", "full")
# A sidecar written after the record that vouches for it by more than this was
# replaced by a writer that keeps no history (translate_file, batch
# translation, translation jobs, the sidecar_translate drain) — its origin is
# unknown. The grace covers post-processing between save and record.
_REWRITE_GRACE = timedelta(seconds=60)
# Every writer records right after it wrote the file (downloads after
# post-processing, extractions immediately). A sidecar already on disk long
# before its record — a hand-copied or restored file with a preserved mtime —
# is not the file the record describes. For extractions this is the only
# link to the file: ``sidecar_origins`` carries no format.
_RECORD_WRITE_WINDOW = timedelta(minutes=10)


def _latest_download(video_path: str, language: str):
    from sqlalchemy import or_, select

    from db.models.providers import SubtitleDownload
    from extensions import db

    return db.session.execute(
        select(SubtitleDownload)
        .where(SubtitleDownload.file_path == video_path)
        .where(SubtitleDownload.language == language)
        .where(
            or_(
                SubtitleDownload.subtitle_type.is_(None),
                SubtitleDownload.subtitle_type.in_([t for t in _MAIN_SUBTITLE_TYPES if t]),
                SubtitleDownload.subtitle_type == "",
            )
        )
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


def _aware(value: datetime | None) -> datetime | None:
    """SQLite hands timestamps back naive; they were written as UTC."""
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)


def _is_real(video_path: str, language: str, sidecar: str, fmt: str) -> bool:
    """Whether the newest provenance record is "real" AND describes ``sidecar``.

    History is keyed by (video, language), not by the file, so a record only
    vouches for the sidecar actually found when (spec §4, final-review C1):

      - it is a main-track record (forced/hi rows are ignored, see
        ``_latest_download``);
      - a download row's format matches the sidecar's format (a real ``.ass``
        download says nothing about a ``.srt`` placed by hand);
      - the sidecar was not rewritten after the record (mtime newer than the
        record + ``_REWRITE_GRACE`` → a non-recording writer replaced it);
      - the sidecar was written around the time of the record, not long
        before it (``_RECORD_WRITE_WINDOW``) — for an extraction origin (no
        format column) this is the only tie to the file.
    """
    download = _latest_download(video_path, language)
    origin = _latest_origin(video_path, language)
    if download is None and origin is None:
        return False

    download_at = _aware(download.downloaded_at) if download is not None else None
    origin_at = _aware(origin.recorded_at) if origin is not None else None

    if origin_at is not None and (download_at is None or origin_at >= download_at):
        if origin.origin not in _ORIGIN_KINDS:
            return False
        decided_at = origin_at
    else:
        if (download.source or "provider") not in REAL_SOURCES:
            return False
        if download.provider_name in _NOT_REAL_PROVIDERS:
            return False
        if (download.format or "").lower() != fmt:
            return False
        decided_at = download_at
    earliest = decided_at - _RECORD_WRITE_WINDOW

    try:
        mtime = datetime.fromtimestamp(os.path.getmtime(sidecar), tz=UTC)
    except OSError:
        return False
    if mtime > decided_at + _REWRITE_GRACE:
        logger.debug(
            "real sidecar check: %s was rewritten after its record (%s > %s) — unknown origin",
            sidecar,
            mtime.isoformat(),
            decided_at.isoformat(),
        )
        return False
    if mtime < earliest:
        logger.debug(
            "real sidecar check: %s predates its record — not the file it describes",
            sidecar,
        )
        return False
    return True


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

    A language counts only when a usable, validated sidecar file exists on
    disk (see ``_usable``) AND the newest provenance record for (video,
    language) is "real" and describes that very file (see ``_is_real``).
    Unknown-origin sidecars (no record in either table, a record for a
    different format or a forced track, or a file rewritten after its
    record) and machine translations never count.
    """
    from translator import find_existing_target_file

    covered: set[str] = set()
    for lang in languages:
        for fmt in _SIDECAR_FORMATS:
            sidecar = find_existing_target_file(video_path, lang, fmt)
            if sidecar is None or not _usable(sidecar, fmt):
                continue
            if _is_real(video_path, lang, sidecar, fmt):
                covered.add(lang)
                break
    return covered


# --- carrying provenance through an in-place rewrite (sync) -------------------


@dataclass(frozen=True)
class RewriteVouch:
    """A sidecar that was genuine right before a sync rewrote it."""

    sidecar: str
    video_path: str
    language: str
    mtime: float


def _identify(sidecar_path: str) -> tuple[str, str, str] | None:
    """``(video_path, language, fmt)`` of a main sidecar, or None.

    Only a file ``real_sidecar_languages`` itself would pick for its video
    and language qualifies - a forced/hi variant or a file without a video
    next to it never does.
    """
    from config_language_data import normalize_language_code
    from translator import find_existing_target_file

    base, ext = os.path.splitext(sidecar_path)
    fmt = ext.lstrip(".").lower()
    if fmt not in _SIDECAR_FORMATS or "." not in os.path.basename(base):
        return None
    video_base, tag = base.rsplit(".", 1)
    language = normalize_language_code(tag.lower())
    if not language:
        return None
    wanted = os.path.normcase(os.path.abspath(sidecar_path))
    for video_ext in _VIDEO_EXTS:
        video = video_base + video_ext
        if not os.path.isfile(video):
            continue
        found = find_existing_target_file(video, language, fmt)
        if found and os.path.normcase(os.path.abspath(found)) == wanted:
            return video, language, fmt
    return None


def vouch_before_rewrite(sidecar_path: str) -> RewriteVouch | None:
    """Call BEFORE a sync rewrites ``sidecar_path`` in place.

    Returns a vouch when the sidecar is genuine right now (the same check as
    ``real_sidecar_languages``), else None. Never raises: a sync must not
    fail over bookkeeping - without a vouch the synced file counts as
    unknown origin, which keeps the embedded track (safe side).
    """
    try:
        identity = _identify(sidecar_path)
        if identity is None:
            return None
        video, language, fmt = identity
        if not (_usable(sidecar_path, fmt) and _is_real(video, language, sidecar_path, fmt)):
            return None
        return RewriteVouch(sidecar_path, video, language, os.path.getmtime(sidecar_path))
    except Exception as exc:  # noqa: BLE001 - bookkeeping only, see docstring
        logger.warning("sidecar provenance: could not vouch for %s: %s", sidecar_path, exc)
        return None


def carry_origin_after_rewrite(vouch: RewriteVouch | None) -> None:
    """Call AFTER a successful rewrite: record a ``resync`` origin so the
    rewritten file keeps the standing the vouched one had.

    Nothing is recorded without a vouch or when the file was not actually
    rewritten. Never raises (see ``vouch_before_rewrite``).
    """
    if vouch is None:
        return
    try:
        if os.path.getmtime(vouch.sidecar) == vouch.mtime:
            return
        from db.models.providers import SidecarOrigin
        from extensions import db

        db.session.add(
            SidecarOrigin(
                video_path=vouch.video_path,
                language=vouch.language,
                origin=_RESYNC,
                recorded_at=datetime.now(UTC),
            )
        )
        db.session.commit()
    except Exception as exc:  # noqa: BLE001 - bookkeeping only
        try:
            from extensions import db

            db.session.rollback()
        except Exception:  # noqa: BLE001
            pass
        logger.warning("sidecar provenance: resync record failed for %s: %s", vouch.sidecar, exc)
