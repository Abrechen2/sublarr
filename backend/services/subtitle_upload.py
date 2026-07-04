"""Validation + sanitization for manually-uploaded subtitle files.

Pure (no Flask/DB/disk). Format is detected from CONTENT, never trusted from
the filename extension. Archives are rejected here (raw files only).
"""

from __future__ import annotations

import logging
import os
import re

logger = logging.getLogger(__name__)

ALLOWED_UPLOAD_EXTS: frozenset[str] = frozenset({"srt", "ass", "ssa", "vtt"})
MAX_UPLOAD_BYTES: int = 5 * 1024 * 1024
_ARCHIVE_EXTS: frozenset[str] = frozenset({"zip", "rar", "7z", "gz", "tar"})

_LANGUAGE_RE = re.compile(r"^[a-z]{2,3}\Z")
_ALLOWED_MODIFIERS: frozenset[str] = frozenset({"hi", "forced", "sdh", "cc"})


class UploadError(Exception):
    """Raised when an uploaded subtitle is rejected. Carries an HTTP status."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def _ext_of(filename: str) -> str:
    return os.path.splitext(filename or "")[1].lstrip(".").lower()


def _sanitize_or_raise(raw: bytes, fmt) -> bytes:
    """Run the sanitizer, converting a ValueError into an UploadError(422).

    Shared by every accepted-format branch so the try/except isn't duplicated.
    """
    from subtitle_sanitizer import sanitize_subtitle

    try:
        return sanitize_subtitle(raw, fmt)
    except ValueError as e:
        raise UploadError(422, f"Subtitle failed the security check: {e}") from e


def prepare_upload(filename: str, raw: bytes) -> tuple[bytes, str]:
    """Validate + sanitize an uploaded subtitle. Returns (content, detected_ext).

    Raises UploadError(status, message) on any rejection.
    """
    ext = _ext_of(filename)
    if ext in _ARCHIVE_EXTS:
        raise UploadError(
            415,
            "Archive uploads are not supported yet — extract the subtitle and "
            "upload the .srt/.ass/.vtt file directly.",
        )
    if ext not in ALLOWED_UPLOAD_EXTS:
        raise UploadError(415, f"Unsupported subtitle type: .{ext or '?'}")
    if not raw:
        raise UploadError(422, "Uploaded file is empty.")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise UploadError(
            413, f"File too large: {len(raw) // 1024} KB > {MAX_UPLOAD_BYTES // 1024} KB limit"
        )

    from providers.base import SubtitleFormat
    from providers.format_validator import _validate_subtitle_content, detect_format_from_content
    from subtitle_sanitizer import validate_content_type

    # detect_format_from_content() only ever distinguishes ASS from SRT — it
    # never returns VTT. Detect the WEBVTT magic ourselves first so content
    # detection (not the extension) still wins: a genuine .vtt upload (or a
    # WEBVTT file misnamed .srt) must not be misdetected as SRT and rejected.
    #
    # BOM-tolerant only (no general whitespace-skipping): this must mirror the
    # inner validate_content_type() check exactly — WEBVTT must sit right at
    # the start after an optional BOM. Otherwise a file that tolerates leading
    # blank lines here but not there passes this sniff and then fails the
    # inner check with a confusing 422.
    stripped = raw.lstrip(b"\xef\xbb\xbf")
    if stripped.startswith(b"WEBVTT"):
        # Whole-payload magic-byte/control-byte check (P4 defense) — the
        # outer content-type sniff above only looks at the first bytes, so a
        # payload like b"WEBVTT\n" + binary would otherwise sail through and
        # get written to disk verbatim (VTT sanitization fails open on a
        # parse error). Must run BEFORE sanitizing.
        valid, reason = _validate_subtitle_content(raw, "vtt")
        if not valid:
            raise UploadError(422, reason or "File content is not a recognised text subtitle.")
        return _sanitize_or_raise(raw, SubtitleFormat.VTT), "vtt"

    fmt = detect_format_from_content(raw)
    detected = getattr(fmt, "value", "unknown")
    if detected == "unknown" or not validate_content_type(raw, fmt):
        raise UploadError(422, "File content is not a recognised text subtitle.")

    # Same whole-payload check for srt/ass/ssa — a decoy header like
    # "[Script Info]\n" or "1\n" followed by binary passes the first-line-only
    # validate_content_type() check above; ASS sanitization also fails open on
    # a parse error, so without this the binary payload would be written to
    # disk unchanged.
    valid, reason = _validate_subtitle_content(raw, detected)
    if not valid:
        raise UploadError(422, reason or "File content is not a recognised text subtitle.")

    return _sanitize_or_raise(raw, fmt), detected


def build_sidecar_path(video_path: str, language: str, modifier: str | None, ext: str) -> str:
    """Build the sidecar subtitle path next to a video file.

    E.g. ("/m/Show - S01E01.mkv", "de", None, "srt") -> "/m/Show - S01E01.de.srt"
    E.g. ("/m/Show - S01E01.mkv", "en", "forced", "ass") -> "/m/Show - S01E01.en.forced.ass"
    """
    base, _ = os.path.splitext(video_path)
    parts = [base, language]
    if modifier:
        parts.append(modifier)
    parts.append(ext)
    return ".".join(parts)


def save_manual_subtitle(
    video_path: str,
    content: bytes,
    ext: str,
    language: str,
    modifier: str | None,
    overwrite: bool,
    media_roots: list[str],
) -> str:
    """Write a validated manual subtitle as a sidecar and record it. Returns the path."""
    import security_utils
    from services.sidecar_scan import scan_subtitle_sidecars
    from utils.atomic_write import atomic_write_bytes

    # Defense-in-depth: language/modifier are spliced directly into the sidecar
    # path below. A value like language="../../etc" would resolve to a path
    # still inside a configured root (so is_safe_path passes) but outside the
    # video's own directory. Reject anything that isn't a plain language/
    # modifier token before it ever reaches path construction.
    if not _LANGUAGE_RE.match(language or ""):
        raise UploadError(400, "Invalid language code")
    if modifier is not None and modifier not in _ALLOWED_MODIFIERS:
        raise UploadError(400, "Invalid subtitle modifier")

    out_path = build_sidecar_path(video_path, language, modifier, ext)

    # Multi-root libraries: a video may live under the primary media_path OR
    # any configured extra_media_paths root. Accept the sidecar as long as it
    # resolves inside ANY configured root; an empty root list fails closed.
    media_root = next(
        (root for root in media_roots if security_utils.is_safe_path(out_path, root)), None
    )
    if media_root is None:
        raise UploadError(400, "Resolved subtitle path is outside the media directory.")

    existing = None
    for side in scan_subtitle_sidecars(video_path):
        if side.get("language") == language and side.get("modifier") == modifier:
            existing = side["path"]
            break
    if existing and not overwrite:
        raise UploadError(409, f"A {language} subtitle already exists — set overwrite to replace.")
    if existing and overwrite:
        try:
            from services.sidecar_trash import get_batch_dir, trash_sidecar

            batch_dir = get_batch_dir(media_root, "manual-upload")
            os.makedirs(batch_dir, exist_ok=True)
            _, trash_error = trash_sidecar(existing, media_root, batch_dir)
            if trash_error is not None:
                logger.warning(
                    "manual upload: could not trash prior sidecar %s: %s", existing, trash_error
                )
        except Exception as e:
            # The atomic overwrite below still replaces the file; do not abort,
            # but do NOT swallow silently — log so a failing trash is visible.
            logger.warning("manual upload: could not trash prior sidecar %s: %s", existing, e)

    atomic_write_bytes(out_path, content)

    # Register the content hash exactly like download_manager does after a
    # provider download, so a manual overwrite doesn't leave a stale hash
    # behind and manual files participate in dedup/cleanup like any other.
    try:
        from db.repositories.cleanup import CleanupRepository
        from dedup_engine import compute_content_hash_from_bytes

        content_hash = compute_content_hash_from_bytes(content)
        CleanupRepository().upsert_hash(
            file_path=out_path,
            content_hash=content_hash,
            file_size=len(content),
            format=ext,
            language=language,
        )
    except Exception as e:
        try:
            from extensions import db as _db

            _db.session.rollback()
        except Exception:
            pass
        logger.warning("manual upload: hash registration failed for %s: %s", out_path, e)

    try:
        from db.providers import record_subtitle_download

        record_subtitle_download(
            provider_name="manual",
            subtitle_id=f"manual:{os.path.basename(out_path)}",
            language=language,
            fmt=ext,
            file_path=out_path,
            score=0,
            source="manual",
        )
    except Exception as e:
        # History recording must never lose the written file — but log it (not silent).
        logger.warning("manual upload: history record failed for %s: %s", out_path, e)

    return out_path
