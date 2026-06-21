"""Shared fixer helpers: atomic write, cue counting, validation, backup."""

from __future__ import annotations

import os
import tempfile

from services.subtitle_health.text_utils import decode_with_confidence


class FixValidationError(Exception):
    """Raised when a fix would change the cue structure unexpectedly."""


def count_cues(raw: bytes) -> int:
    import pysubs2

    text, _enc, _conf = decode_with_confidence(raw)
    try:
        subs = pysubs2.SSAFile.from_string(text)
    except Exception:
        return 0
    return sum(1 for ev in subs.events if not ev.is_comment and ev.text.strip())


def validate_cue_count(before: bytes, after: bytes) -> None:
    b, a = count_cues(before), count_cues(after)
    if b != a:
        raise FixValidationError(f"cue count changed {b} -> {a}")


def atomic_write_bytes(path: str, data: bytes) -> None:
    d = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass


def backup_sidecar(path: str) -> str | None:
    """Move a sidecar into the project trash, returning the trashed path or None."""
    from config import get_settings
    from routes.subtitles.helpers import _get_batch_dir, _trash_sidecar

    media_path = getattr(get_settings(), "media_path", "/media")
    batch_dir = _get_batch_dir(media_path, "subtitle_health")
    trashed, err = _trash_sidecar(path, media_path, batch_dir)
    if err is not None:
        return None
    return trashed
