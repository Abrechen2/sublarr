"""Non-destructive sync preview for the side-by-side compare modal (V1.6 #4).

Runs the sync engines (ffsubsync against the video, alass against a reference
subtitle) to a temp file WITHOUT overwriting the sidecar, then returns the
original vs candidate cues so the UI can show a diff and let the user pick which
to keep. "Apply chosen" is the existing ``/video-sync`` job — this module never
mutates the sidecar.

The subprocess orchestration mirrors ``services.video_sync`` (same concurrency
lock, nice prefix, shift parse, sanity gate) but stops before the copy-over step.
It is deliberately kept separate from the proven in-place sync path.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile

import pysubs2

from services.video_sync import (
    SyncSanityThresholdError,
    SyncUnavailableError,
    _check_module,
    _parse_ffsubsync_shift,
    _safe_remove,
)

logger = logging.getLogger(__name__)

# Preview is an interactive, user-initiated action holding the process-wide
# sync_subprocess_lock, so bound it far tighter than the batch in-place sync
# (600s/300s). A single-file preview that can't finish in a few minutes isn't
# worth blocking the app for.
_FFSUBSYNC_PREVIEW_TIMEOUT = 180
_ALASS_PREVIEW_TIMEOUT = 120
# Refuse to queue behind a long-running sync (or, since the lock became the
# process-wide media IO gate, a remux/extraction) rather than pile up on it:
# four such requests would otherwise hold every gunicorn thread.
_LOCK_WAIT_TIMEOUT = 10


def _locked_subprocess(cmd: list[str], timeout: int):
    """Run ``cmd`` holding the process-wide sync lock, acquired with a bounded
    wait so a compare can't pile up behind a long in-place sync (H1 DoS guard).
    """
    from services.sync_engines.concurrency import sync_subprocess_lock

    if not sync_subprocess_lock.acquire(timeout=_LOCK_WAIT_TIMEOUT):
        raise RuntimeError("sync engine is busy — try again in a moment")
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"sync preview timed out after {timeout}s") from None
    finally:
        sync_subprocess_lock.release()


def load_cues(path: str) -> list[dict]:
    """Parse a subtitle file into ``[{start, end, text}]`` (ms + plaintext)."""
    subs = pysubs2.load(path)
    return [
        {"start": e.start, "end": e.end, "text": e.plaintext}
        for e in subs.events
        if not e.is_comment
    ]


def _run_ffsubsync_preview(subtitle_path: str, video_path: str) -> tuple[int, str]:
    """Run ffsubsync to a temp file. Returns ``(shift_ms, out_path)``; caller owns out_path.

    Raises SyncUnavailableError / SyncSanityThresholdError / RuntimeError just like
    ``services.video_sync.sync_with_ffsubsync``, but never touches the sidecar.
    """
    from config import get_settings
    from security_utils import safe_subprocess_arg
    from services.sync_engines.concurrency import nice_prefix

    if not (shutil.which("ffsubsync") or _check_module("ffsubsync")):
        raise SyncUnavailableError("ffsubsync is not installed")

    ext = os.path.splitext(subtitle_path)[1]
    fd, out_path = tempfile.mkstemp(suffix=ext)
    os.close(fd)

    cmd = [
        *nice_prefix(),
        "ffsubsync",
        safe_subprocess_arg(video_path),
        "-i",
        safe_subprocess_arg(subtitle_path),
        "-o",
        safe_subprocess_arg(out_path),
    ]
    # Any failure after the tempfile is created removes it (incl. get_settings /
    # shift-parse errors that sit between the subprocess and the return).
    try:
        result = _locked_subprocess(cmd, _FFSUBSYNC_PREVIEW_TIMEOUT)
        if result.returncode != 0:
            raise RuntimeError(f"ffsubsync failed: {result.stderr.strip()}")
        shift_ms = _parse_ffsubsync_shift(result.stderr + result.stdout)
        threshold = getattr(get_settings(), "sync_sanity_threshold_ms", 60_000)
        if abs(shift_ms) > threshold:
            raise SyncSanityThresholdError(
                f"ffsubsync shift {shift_ms}ms exceeds sanity threshold {threshold}ms"
            )
        return shift_ms, out_path
    except BaseException:
        _safe_remove(out_path)
        raise


def _run_alass_preview(subtitle_path: str, reference_path: str) -> tuple[int | None, str]:
    """Run alass to a temp file. Returns ``(None, out_path)`` (alass reports no shift)."""
    from security_utils import safe_subprocess_arg
    from services.sync_engines.concurrency import nice_prefix

    if not shutil.which("alass"):
        raise SyncUnavailableError("alass is not installed")

    ext = os.path.splitext(subtitle_path)[1]
    fd, out_path = tempfile.mkstemp(suffix=ext)
    os.close(fd)

    cmd = [
        *nice_prefix(),
        "alass",
        safe_subprocess_arg(reference_path),
        safe_subprocess_arg(subtitle_path),
        safe_subprocess_arg(out_path),
    ]
    try:
        result = _locked_subprocess(cmd, _ALASS_PREVIEW_TIMEOUT)
        if result.returncode != 0:
            raise RuntimeError(f"alass failed: {result.stderr.strip()}")
        return None, out_path
    except BaseException:
        _safe_remove(out_path)
        raise


def _preview(engine: str, run_fn, subtitle_path: str, ref: str) -> dict:
    """Run one engine preview and shape the result. Never raises."""
    try:
        shift_ms, out_path = run_fn(subtitle_path, ref)
    except SyncUnavailableError as exc:
        return {"engine": engine, "status": "unavailable", "error": str(exc)}
    except SyncSanityThresholdError as exc:
        return {"engine": engine, "status": "rejected", "error": str(exc)}
    except Exception as exc:
        return {"engine": engine, "status": "error", "error": str(exc)}

    try:
        cues = load_cues(out_path)
    except Exception as exc:
        return {"engine": engine, "status": "error", "error": f"unreadable output: {exc}"}
    finally:
        _safe_remove(out_path)

    return {"engine": engine, "status": "ok", "shift_ms": shift_ms, "cues": cues}


def sync_compare(
    subtitle_path: str,
    video_path: str | None = None,
    reference_path: str | None = None,
) -> dict:
    """Produce a non-destructive comparison of the sidecar against each engine.

    Returns ``{original: [cues], candidates: [{engine, status, shift_ms?, cues?,
    error?}], any_output: bool}``. Runs ffsubsync when ``video_path`` is given and
    alass when ``reference_path`` is given.
    """
    original = load_cues(subtitle_path)
    candidates: list[dict] = []
    if video_path:
        candidates.append(_preview("ffsubsync", _run_ffsubsync_preview, subtitle_path, video_path))
    if reference_path:
        candidates.append(_preview("alass", _run_alass_preview, subtitle_path, reference_path))

    any_output = any(c["status"] == "ok" for c in candidates)
    return {"original": original, "candidates": candidates, "any_output": any_output}
