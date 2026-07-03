"""Validation + sanitization for manually-uploaded subtitle files.

Pure (no Flask/DB/disk). Format is detected from CONTENT, never trusted from
the filename extension. Archives are rejected here (raw files only).
"""

from __future__ import annotations

import os

ALLOWED_UPLOAD_EXTS: frozenset[str] = frozenset({"srt", "ass", "ssa", "vtt"})
MAX_UPLOAD_BYTES: int = 5 * 1024 * 1024
_ARCHIVE_EXTS: frozenset[str] = frozenset({"zip", "rar", "7z", "gz", "tar"})


class UploadError(Exception):
    """Raised when an uploaded subtitle is rejected. Carries an HTTP status."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def _ext_of(filename: str) -> str:
    return os.path.splitext(filename or "")[1].lstrip(".").lower()


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
    from providers.format_validator import detect_format_from_content
    from subtitle_sanitizer import sanitize_subtitle, validate_content_type

    # detect_format_from_content() only ever distinguishes ASS from SRT — it
    # never returns VTT. Detect the WEBVTT magic ourselves first so content
    # detection (not the extension) still wins: a genuine .vtt upload (or a
    # WEBVTT file misnamed .srt) must not be misdetected as SRT and rejected.
    stripped = raw.lstrip(b"\xef\xbb\xbf")
    if stripped.lstrip()[:6] == b"WEBVTT":
        try:
            content = sanitize_subtitle(raw, SubtitleFormat.VTT)
        except ValueError as e:
            raise UploadError(422, f"Subtitle failed the security check: {e}") from e
        return content, "vtt"

    fmt = detect_format_from_content(raw)
    detected = getattr(fmt, "value", "unknown")
    if detected == "unknown" or not validate_content_type(raw, fmt):
        raise UploadError(422, "File content is not a recognised text subtitle.")

    try:
        content = sanitize_subtitle(raw, fmt)
    except ValueError as e:
        raise UploadError(422, f"Subtitle failed the security check: {e}") from e

    return content, detected
