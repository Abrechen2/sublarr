"""Shared fixer helpers: atomic write, cue counting, validation, backup."""

from __future__ import annotations

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
    """Delegate to the shared helper: readable mode, sweepable ``.sublarr-`` temp.

    This used its own bare ``mkstemp(suffix=".tmp")``, which a killed process
    left next to the episode as an anonymous ``tmpXXXXXXXX.tmp``.
    """
    from utils.atomic_write import atomic_write_bytes as _shared_atomic_write_bytes

    _shared_atomic_write_bytes(path, data)


def backup_sidecar(path: str) -> str | None:
    """Move a sidecar into the project trash, returning the trashed path or None."""
    # get_settings stays a lazy import so tests can patch "config.get_settings".
    from config import get_settings
    from services.sidecar_trash import get_batch_dir, trash_sidecar

    media_path = getattr(get_settings(), "media_path", "/media")
    batch_dir = get_batch_dir(media_path, "subtitle_health")
    trashed, err = trash_sidecar(path, media_path, batch_dir)
    if err is not None:
        return None
    return trashed
