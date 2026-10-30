"""Video subtitle synchronization service.

Wraps ffsubsync and alass CLI tools. Both are optional dependencies —
``SyncUnavailableError`` is raised when an engine is not installed.

**Plan B7 note:** These top-level functions remain the public legacy API
(used by ``routes/sync.py``, ``routes/video_sync.py``, ``wanted_search``,
and CLI ``backend/cli/commands/sync.py``) and keep their historic dict
return shape. The new engine-class pattern lives in
``services.sync_engines.*`` and is orchestrated via
``services.sync_engines.orchestrator.SyncOrchestrator`` — it does NOT
replace these wrappers, it runs alongside them so the orchestrator can
layer new engines on top without touching legacy callers. The module-level
``shutil``, ``subprocess``, ``_check_module``, ``_parse_ffsubsync_shift``,
``_make_backup`` and ``run_trigger`` symbols are intentionally preserved
because existing tests patch them.
"""

import contextlib
import logging
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile

# Plan B6 — post-processing pipeline trigger (module-level import so tests can
# patch("services.video_sync.run_trigger")).
from post_processing.pipeline import run_trigger
from services.foreign_tracks.sidecars import carry_origin_after_rewrite, vouch_before_rewrite
from services.sync_engines.ffsubsync_output import NO_OFFSET_MESSAGE
from services.sync_engines.ffsubsync_output import (
    parse_ffsubsync_shift as _parse_ffsubsync_shift,
)
from subtitle_encoding import load_subtitle_file

logger = logging.getLogger(__name__)


def _fire_after_sync_trigger(subtitle_path: str, video_or_ref: str, engine: str) -> None:
    """Fire the after_sync post-processing trigger. Never raises."""
    try:
        from post_processing.config_store import get_trigger_ops

        op_ids = get_trigger_ops("after_sync")
        if op_ids:
            run_trigger(
                trigger="after_sync",
                op_ids=op_ids,
                context={
                    "subtitle_path": subtitle_path,
                    "video_path": video_or_ref,
                    "lang": "",
                    "score": 0,
                    "trigger": "after_sync",
                    "engine": engine,
                },
            )
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("post_processing after_sync skipped: %s", exc)


def _check_module(name: str) -> bool:
    try:
        __import__(name)
        return True
    except ImportError:
        return False


class SyncUnavailableError(Exception):
    """Raised when the requested sync engine is not installed."""


class SyncSanityThresholdError(Exception):
    """Raised when an engine returned a shift larger than ``sync_sanity_threshold_ms``.

    Mirrors the gate the orchestrator applies in ``services.sync_engines``.
    Legacy callers (route + bulk paths) should treat this as a soft failure
    that signals "engine output is not trustworthy, leave the sidecar
    untouched" — the destination file is never written when this is raised.
    """


class SyncShiftRejectedError(SyncSanityThresholdError):
    """The measured shift exceeded ``sync_sanity_threshold_ms``.

    Split from the framerate-scale rejection: a shift this large usually means
    the subtitle belongs to another episode or cut, which callers may act on
    (see ``services.suspect_sidecars``). ``shift_ms`` is the measured shift.
    """

    def __init__(self, message: str, shift_ms: int) -> None:
        super().__init__(message)
        self.shift_ms = shift_ms


class SubtitleLengthMismatchError(SyncSanityThresholdError):
    """The subtitle runs well past the end of the video it is to be timed to.

    No shift can fix that: it is another episode or cut (prod 2026-10: a BD
    double-length episode 1 "aligned" by -5 s to a 24-min file). Raised before
    ffsubsync runs; the sidecar is left untouched.
    """


def sync_with_ffsubsync(subtitle_path: str, video_path: str) -> dict:
    """Sync subtitle to video using ffsubsync (speech-detection based).

    Creates a .bak copy before modifying the subtitle in-place.

    Plan B7.1 follow-up: writes a row to ``sync_job_runs`` on every call
    (success or failure) so legacy route callers get the same audit trail
    as orchestrator-based calls.

    Returns:
        dict with keys: output_path, shift_ms, engine, backup_path

    Raises:
        SyncUnavailableError: ffsubsync is not installed
        RuntimeError: ffsubsync exited with a non-zero status
        SyncSanityThresholdError: ffsubsync returned a shift larger
            than ``sync_sanity_threshold_ms`` — or stretched the
            timeline (framerate scaling) — sidecar is left untouched.
    """
    import time as _time

    start = _time.monotonic()

    def _audit(status: str, offset_ms: int | None, reason: str = "") -> None:
        """Write an audit row; never raises."""
        try:
            from services.sync_engines.events import write_sync_job_run

            write_sync_job_run(
                engine="ffsubsync",
                status=status,
                offset_ms=offset_ms,
                duration_ms=int((_time.monotonic() - start) * 1000),
                subtitle_path=subtitle_path,
                video_path=video_path,
                reason=reason,
            )
        except Exception as _exc:  # pragma: no cover — defensive
            logger.debug("sync audit write failed: %s", _exc)

    if not (shutil.which("ffsubsync") or _check_module("ffsubsync")):
        _audit("skipped", None, "unavailable")
        raise SyncUnavailableError(
            "ffsubsync is not installed. Install with: pip install ffsubsync"
        )

    import subtitle_plausibility

    overrun = subtitle_plausibility.file_overruns_video(subtitle_path, video_path)
    if overrun:
        logger.warning("ffsubsync: not syncing %s — %s", subtitle_path, overrun)
        _audit("rejected", None, "length_mismatch")
        raise SubtitleLengthMismatchError(f"subtitle does not fit the video: {overrun}")

    backup = _make_backup(subtitle_path)
    logger.info("ffsubsync: syncing %s against %s (backup: %s)", subtitle_path, video_path, backup)
    vouch = vouch_before_rewrite(subtitle_path)

    ext = os.path.splitext(subtitle_path)[1]
    fd, out_path = tempfile.mkstemp(suffix=ext)
    os.close(fd)

    from security_utils import safe_subprocess_arg
    from services.sync_engines.concurrency import nice_prefix, sync_subprocess_lock

    cmd = [
        *nice_prefix(),
        "ffsubsync",
        safe_subprocess_arg(video_path),
        "-i",
        safe_subprocess_arg(subtitle_path),
        "-o",
        safe_subprocess_arg(out_path),
    ]
    try:
        with sync_subprocess_lock:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        _safe_remove(out_path)
        _audit("error", None, "timeout 600s")
        raise RuntimeError("ffsubsync timed out after 600s") from None

    if result.returncode != 0:
        _safe_remove(out_path)
        _audit("error", None, (result.stderr or "").strip()[:64] or "non-zero exit")
        raise RuntimeError(f"ffsubsync failed: {result.stderr.strip()}")

    # Parse shift BEFORE touching the destination so the sanity gate can
    # reject mis-locks without overwriting the existing sidecar.
    shift_ms = _parse_ffsubsync_shift(result.stderr + result.stdout)
    if shift_ms is None:
        # Exit 0 without an offset line: the shift is unknown, not 0 ms.
        _safe_remove(out_path)
        _audit("error", None, "no_offset_in_output")
        raise RuntimeError(NO_OFFSET_MESSAGE)

    # Sanity gate (matches services.sync_engines.orchestrator at line 70):
    # ffsubsync's speech detection can lock onto the wrong reference
    # section (cold-open vs main theme, intro vs scene) and return a
    # large shift in a narrow band just under the previous hard-coded
    # 60s ceiling. Reject anything beyond the configured threshold so the
    # legacy / bulk callers get the same protection as orchestrator-based
    # auto-sync.
    from config import get_settings

    threshold = getattr(get_settings(), "sync_sanity_threshold_ms", 45_000)
    if abs(shift_ms) > threshold:
        _safe_remove(out_path)
        logger.warning(
            "ffsubsync: insane shift %dms (>%dms threshold) — leaving sidecar untouched",
            shift_ms,
            threshold,
        )
        _audit("rejected", shift_ms, f"exceeds_sanity_threshold:{threshold}ms")
        raise SyncShiftRejectedError(
            f"ffsubsync shift {shift_ms}ms exceeds sanity threshold {threshold}ms", shift_ms
        )

    scale = _parse_ffsubsync_scale(result.stderr + result.stdout)
    reason = ""
    if framerate_scale_is_insane(scale):
        plan = segment_sync_fallback(
            subtitle_path, video_path, out_path, threshold, scale, shift_ms
        )
        if plan is None:
            _safe_remove(out_path)
            _audit("rejected", shift_ms, f"framerate_scale:{scale:.3f}")
            raise SyncSanityThresholdError(framerate_scale_message(scale))
        shift_ms, reason = plan.main_offset_ms, segment_reason(plan)
    else:
        shift_original_into(subtitle_path, out_path, shift_ms)

    # NOTE: shutil.move falls back to copy2 across filesystems and copy2's
    # copystat raises PermissionError on bind-mounted /media owned by a
    # different host user — leaving the destination already overwritten by
    # copyfile but the call as a whole raising. Use copyfile + _safe_remove
    # instead so we never touch utime/owner metadata.
    shutil.copyfile(out_path, subtitle_path)
    _safe_remove(out_path)
    carry_origin_after_rewrite(vouch)
    logger.info("ffsubsync: done, estimated shift %dms", shift_ms)
    _audit("ok", shift_ms, reason)

    # Plan B6 — fire after_sync post-processing trigger on the happy path.
    _fire_after_sync_trigger(subtitle_path, video_path, "ffsubsync")

    return {
        "output_path": subtitle_path,
        "shift_ms": shift_ms,
        "engine": "ffsubsync",
        "backup_path": backup,
    }


def sync_with_alass(subtitle_path: str, reference_path: str) -> dict:
    """Sync subtitle to a reference subtitle using alass.

    Creates a .bak copy before modifying the subtitle in-place.

    Plan B7.1 follow-up: writes a row to ``sync_job_runs`` on every call
    (success or failure) so legacy route callers get the same audit trail
    as orchestrator-based calls.

    Returns:
        dict with keys: output_path, engine, backup_path

    Raises:
        SyncUnavailableError: alass is not installed
        RuntimeError: alass exited with a non-zero status
    """
    import time as _time

    start = _time.monotonic()

    def _audit(status: str, reason: str = "") -> None:
        """Write an audit row; never raises."""
        try:
            from services.sync_engines.events import write_sync_job_run

            write_sync_job_run(
                engine="alass",
                status=status,
                offset_ms=None,  # alass doesn't report shift
                duration_ms=int((_time.monotonic() - start) * 1000),
                subtitle_path=subtitle_path,
                video_path=reference_path,
                reason=reason,
            )
        except Exception as _exc:  # pragma: no cover — defensive
            logger.debug("sync audit write failed: %s", _exc)

    if not shutil.which("alass"):
        _audit("skipped", "unavailable")
        raise SyncUnavailableError(
            "alass is not installed. Download from: https://github.com/kaegi/alass/releases"
        )

    backup = _make_backup(subtitle_path)
    logger.info("alass: syncing %s against %s", subtitle_path, reference_path)
    vouch = vouch_before_rewrite(subtitle_path)

    ext = os.path.splitext(subtitle_path)[1]
    fd, out_path = tempfile.mkstemp(suffix=ext)
    os.close(fd)

    from security_utils import safe_subprocess_arg
    from services.sync_engines.concurrency import nice_prefix, sync_subprocess_lock

    cmd = [
        *nice_prefix(),
        "alass",
        safe_subprocess_arg(reference_path),
        safe_subprocess_arg(subtitle_path),
        safe_subprocess_arg(out_path),
    ]
    try:
        with sync_subprocess_lock:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        _safe_remove(out_path)
        _audit("error", "timeout 300s")
        raise RuntimeError("alass timed out after 300s") from None

    if result.returncode != 0:
        _safe_remove(out_path)
        _audit("error", (result.stderr or "").strip()[:64] or "non-zero exit")
        raise RuntimeError(f"alass failed: {result.stderr.strip()}")

    # See ffsubsync branch above for why this is copyfile + _safe_remove
    # rather than shutil.move.
    shutil.copyfile(out_path, subtitle_path)
    _safe_remove(out_path)
    carry_origin_after_rewrite(vouch)
    logger.info("alass: sync complete")
    _audit("ok", "")

    # Plan B6 — fire after_sync post-processing trigger on the happy path.
    _fire_after_sync_trigger(subtitle_path, reference_path, "alass")

    return {
        "output_path": subtitle_path,
        "engine": "alass",
        "backup_path": backup,
    }


def get_available_engines() -> dict:
    """Return which sync engines are currently installed (checked at call time)."""
    return {
        "ffsubsync": bool(shutil.which("ffsubsync") or _check_module("ffsubsync")),
        "alass": bool(shutil.which("alass")),
    }


def _install_alass_binary() -> None:
    """Download and install the alass binary for the current platform."""
    import stat
    import urllib.request

    system = platform.system().lower()
    machine = platform.machine().lower()

    # Map platform to GitHub release asset name
    if system == "linux":
        asset = "alass-linux64" if "x86_64" in machine or "amd64" in machine else None
    elif system == "darwin":
        asset = "alass-osx"
    elif system == "windows":
        asset = "alass-win64.exe"
    else:
        asset = None

    if not asset:
        raise RuntimeError(f"No alass binary available for {system}/{machine}")

    url = f"https://github.com/kaegi/alass/releases/latest/download/{asset}"
    install_name = "alass.exe" if system == "windows" else "alass"

    # Install to ~/.local/bin (Linux/Mac) or next to Python (Windows)
    if system == "windows":
        install_dir = os.path.dirname(sys.executable)
    else:
        install_dir = os.path.expanduser("~/.local/bin")
        os.makedirs(install_dir, exist_ok=True)

    install_path = os.path.join(install_dir, install_name)
    logger.info("Downloading alass from %s → %s", url, install_path)

    with urllib.request.urlopen(url, timeout=60) as resp:  # noqa: S310
        data = resp.read()

    with open(install_path, "wb") as f:
        f.write(data)

    if system != "windows":
        os.chmod(
            install_path, os.stat(install_path).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH
        )

    logger.info("alass installed to %s", install_path)


def install_engine(engine: str) -> dict:
    """Install a sync engine. Returns { success, message }.

    Supported engines:
        ffsubsync — installed via pip
        alass     — downloaded binary from GitHub releases
    """
    if engine == "ffsubsync":
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "ffsubsync"],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            raise RuntimeError(f"pip install ffsubsync failed: {result.stderr.strip()}")
        logger.info("ffsubsync installed successfully")
        return {"success": True, "message": "ffsubsync installed"}

    elif engine == "alass":
        _install_alass_binary()
        return {"success": True, "message": "alass installed"}

    else:
        raise ValueError(f"Unknown engine: {engine!r}")


def _make_backup(file_path: str) -> str:
    """Return the single-slot bak for ``file_path``, creating it if absent.

    Backups live in ``<dir>/.sublarr/backups/<base>.bak<ext>`` rather than
    beside the active sub, so media servers don't read ``.bak`` as a Bashkir
    subtitle track and the retention/cleanup/UI tooling can manage them.

    Delegates to ``subtitle_restore.create_or_get_bak``: an existing bak is
    the undo point of the *original* text and is returned untouched — the
    unconditional ``shutil.copy2`` this used to do both destroyed that undo
    point on every sync run and raised EPERM on bak files created under an
    older PUID (53 auto_sync items stuck for weeks, 2026-08).
    """
    from services.subtitle_restore import create_or_get_bak

    return create_or_get_bak(file_path)


def _safe_remove(path: str) -> None:
    with contextlib.suppress(OSError):
        os.unlink(path)


# ffsubsync may decide the subtitle was timed for another framerate and stretch
# the whole timeline (25/24, 25/23.976, ...). Prod 2026-10-03: all ten scaled
# results in a day were wrong — the subtitle already matched the video's length,
# and the stretch put the end of the episode ~60 s out. The shift alone stays
# under sync_sanity_threshold_ms, so it needs its own gate.
_MAX_FRAMERATE_SCALE_DEVIATION = 0.001


def framerate_scale_is_insane(scale: float) -> bool:
    return abs(scale - 1.0) > _MAX_FRAMERATE_SCALE_DEVIATION


def framerate_scale_message(scale: float) -> str:
    return f"ffsubsync framerate scale factor {scale:.3f} would stretch the timeline"


_SEGMENT_MAX_SCALE_DEVIATION = 0.002  # 1000/1001 and its rounding, not 25/24


def segment_sync_fallback(
    subtitle_path: str,
    video_path: str,
    out_path: str,
    max_offset_ms: int,
    scale: float,
    shift_ms: int,
):
    """After a rejected framerate scale: one shift per stretch, written to ``out_path``.

    ffsubsync answers a subtitle timed to another edit (a few seconds more
    after the opening, at the eyecatch) with a framerate scale; the stretches
    still fit by plain shifts (prod 2026-10-30, Slime S02E19). Returns the
    plan, or None when there is none and the rejection stands.

    Only for a scale near 1 (1000/1001): a 25/24 scale is a real speed-up
    that no set of shifts repairs (prod dry run 2026-10-30: plans at -45 s
    and +23 s for such files). ``shift_ms`` is ffsubsync's own shift, the
    plan's anchor.
    """
    from services.segment_sync import segment_sync_into

    if abs(scale - 1.0) > _SEGMENT_MAX_SCALE_DEVIATION:
        return None

    logger.warning(
        "ffsubsync: framerate scale factor %.3f for %s — trying one shift per stretch",
        scale,
        subtitle_path,
    )
    try:
        return segment_sync_into(
            subtitle_path, video_path, out_path, max_offset_ms=max_offset_ms, anchor_ms=shift_ms
        )
    except Exception as exc:  # noqa: BLE001 — the rejection stands
        logger.warning("segment sync failed for %s: %s", subtitle_path, exc, exc_info=True)
        return None


def segment_reason(plan) -> str:
    """Audit reason for a segment sync: the shifts, cut to the column's 64 chars."""
    return ("segments:" + ",".join(str(o) for o in plan.offsets))[:64]


_PYSUBS2_FORMATS = {"srt": "srt", "ass": "ass", "ssa": "ssa", "vtt": "vtt"}


def shift_original_into(subtitle_path: str, out_path: str, shift_ms: int) -> bool:
    """Write the original subtitle, moved by ``shift_ms``, to ``out_path``.

    ffsubsync writes its output from the subtitles it parsed for alignment,
    and that parse caps every event at ``max_subtitle_seconds`` (10 s): on
    prod 2026-10-07, 120 signs and ED lines of one Attack on Titan episode
    came back ending exactly 10 s after they started. With the scale gate
    in place a sync is a pure shift, so the shift is applied to the
    original instead and nothing else about the file changes.

    Returns False when the original cannot be parsed; ``out_path`` then
    keeps ffsubsync's own output, as before.
    """

    ext = os.path.splitext(subtitle_path)[1].lstrip(".").lower()
    try:
        subs = load_subtitle_file(subtitle_path)
    except Exception as exc:  # noqa: BLE001 — undecodable or malformed: keep ffsubsync's file
        logger.warning("sync: could not re-read %s to apply the shift: %s", subtitle_path, exc)
        return False
    subs.shift(ms=shift_ms)
    subs.save(out_path, encoding="utf-8", format_=_PYSUBS2_FORMATS.get(ext))
    return True


def _parse_ffsubsync_scale(output: str) -> float:
    """Extract ffsubsync's framerate scale factor. Returns 1.0 if not reported."""
    m = re.search(r"framerate scale factor\s*:\s*(\d+(?:\.\d+)?)", output, re.IGNORECASE)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    return 1.0
