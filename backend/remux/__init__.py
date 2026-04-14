"""Remux engine — safely removes subtitle streams from video containers.

Workflow:
  1. Probe container to confirm stream exists.
  2. Select backend: mkvmerge (MKV) or ffmpeg (MP4/other).
  3. Remux to a temp file in the same directory.
  4. Verify temp file (duration ±2 s, stream counts, size ≥ 50 %).
  5. Atomic swap: original → <original>.bak, temp → original.
  6. Optionally use CoW reflink for zero-cost backup on Btrfs/XFS.

License: GPL-3.0
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile

logger = logging.getLogger(__name__)


class RemuxError(Exception):
    """Raised when any remux step fails."""


# ---------------------------------------------------------------------------
# CoW / reflink helper
# ---------------------------------------------------------------------------


def _try_reflink(src: str, dst: str) -> bool:
    """Attempt `cp --reflink=auto src dst`. Returns True on success."""
    try:
        result = subprocess.run(
            ["cp", "--reflink=auto", src, dst],
            capture_output=True,
            timeout=120,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _resolve_trash_dir(video_path: str, trash_dir_setting: str) -> str:
    """Return the absolute path to the trash directory for this video.

    If `trash_dir_setting` is absolute, use it directly.
    Otherwise treat it as relative to the media root (first watched-folder root
    that is a parent of `video_path`, or the video's own directory).
    """
    if os.path.isabs(trash_dir_setting):
        return trash_dir_setting

    # Find longest watched-folder prefix
    try:
        from config import get_settings

        settings = get_settings()
        media_root = getattr(settings, "media_path", "") or os.path.dirname(video_path)
    except Exception:
        media_root = os.path.dirname(video_path)

    return os.path.join(media_root, trash_dir_setting)


def _make_backup(video_path: str, use_reflink: bool, trash_dir: str = "") -> str:
    """Move original to the trash directory and return the backup path.

    Layout: <trash_dir>/trash/<YYYY-MM-DD>/<basename>.<timestamp>.bak

    Falls back to a sibling .bak if the trash directory cannot be created.
    """
    import time as _time

    basename = os.path.basename(video_path)
    date_str = __import__("datetime").date.today().isoformat()
    timestamp = int(_time.time())

    resolved = _resolve_trash_dir(video_path, trash_dir or ".sublarr")
    dest_dir = os.path.join(resolved, "trash", date_str)

    try:
        os.makedirs(dest_dir, exist_ok=True)
        bak_path = os.path.join(dest_dir, f"{basename}.{timestamp}.bak")
        if use_reflink and _try_reflink(video_path, bak_path):
            logger.info("Remux: reflink backup in trash: %s", bak_path)
        else:
            shutil.copy2(video_path, bak_path)
            logger.info("Remux: backup moved to trash: %s", bak_path)
        return bak_path
    except OSError as exc:
        # Fallback: sibling .bak
        logger.warning("Remux: could not use trash dir (%s), falling back to sibling .bak", exc)
        bak_path = video_path + ".bak"
        shutil.copy2(video_path, bak_path)
        return bak_path


# ---------------------------------------------------------------------------
# Backend selection
# ---------------------------------------------------------------------------


def _detect_backend(video_path: str) -> str:
    """Return 'mkvmerge' for MKV files, 'ffmpeg' otherwise."""
    ext = os.path.splitext(video_path)[1].lower()
    if ext in (".mkv", ".mka", ".mk3d"):
        return "mkvmerge"
    return "ffmpeg"


def _which(cmd: str) -> bool:
    return shutil.which(cmd) is not None


# ---------------------------------------------------------------------------
# mkvmerge backend
# ---------------------------------------------------------------------------


def _remux_mkvmerge(video_path: str, stream_indices: list[int], output_path: str) -> None:
    """Remove subtitle streams using mkvmerge.

    `stream_indices` are the global track IDs as reported by ffprobe/mkvmerge -i
    (matches mkvmerge's --subtitle-tracks !N,M,... flag where the leading `!`
    applies to the whole comma-separated list, not to each element).
    """
    exclusions = "!" + ",".join(str(idx) for idx in stream_indices)
    cmd = [
        "mkvmerge",
        "-o",
        output_path,
        "--subtitle-tracks",
        exclusions,
        video_path,
    ]
    logger.debug("Remux mkvmerge: %s", " ".join(cmd))
    result = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600
    )
    if result.returncode not in (0, 1):  # mkvmerge exit 1 = warnings, still OK
        # mkvmerge writes hard errors to stdout, not stderr — include both so
        # failures are never logged with an empty reason.
        detail = (result.stderr or result.stdout or "").strip()[:500]
        raise RemuxError(f"mkvmerge failed (exit {result.returncode}): {detail}")


# ---------------------------------------------------------------------------
# ffmpeg backend
# ---------------------------------------------------------------------------


def _remux_ffmpeg(video_path: str, stream_indices: list[int], output_path: str) -> None:
    """Remove subtitle streams using ffmpeg stream copy."""
    if not _which("ffmpeg"):
        raise RemuxError("ffmpeg not found")

    # Map all streams, then un-map each target subtitle stream by global index
    cmd = ["ffmpeg", "-y", "-i", video_path, "-map", "0"]
    for idx in stream_indices:
        cmd += ["-map", f"-0:{idx}"]
    cmd += ["-c", "copy", output_path]

    logger.debug("Remux ffmpeg: %s", " ".join(cmd))
    result = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600
    )
    if result.returncode != 0:
        raise RemuxError(f"ffmpeg failed (exit {result.returncode}): {result.stderr[-500:]}")


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


def _probe(path: str) -> dict:
    """Run ffprobe and return parsed JSON."""
    if not _which("ffprobe"):
        raise RemuxError("ffprobe not found")
    cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_streams",
        "-show_format",
        path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RemuxError(f"ffprobe failed: {result.stderr[:300]}")
    import json

    return json.loads(result.stdout)


def _verify(original_path: str, remuxed_path: str, n_removed: int = 1) -> None:
    """Compare duration, stream count, and file size between original and remux.

    Args:
        n_removed: How many subtitle streams were intended to be removed.
    """
    orig_info = _probe(original_path)
    new_info = _probe(remuxed_path)

    # Duration check: allow ±5 s or 1 % of total duration (whichever is larger).
    # Some MKVs have phantom trailing segments that mkvmerge trims during remux,
    # causing ffprobe to report slightly different durations. A strict 2 s cap
    # produces false-positive failures for long files (24-min anime = ~1 % ≈ 14 s).
    orig_dur = float(orig_info.get("format", {}).get("duration", 0))
    new_dur = float(new_info.get("format", {}).get("duration", 0))
    dur_tolerance = max(5.0, orig_dur * 0.01)
    if orig_dur > 0 and abs(orig_dur - new_dur) > dur_tolerance:
        raise RemuxError(f"Duration mismatch: original={orig_dur:.1f}s remuxed={new_dur:.1f}s")

    # Video + audio stream count must not decrease
    def _count(info: dict, codec_type: str) -> int:
        return sum(1 for s in info.get("streams", []) if s.get("codec_type") == codec_type)

    if _count(new_info, "video") < _count(orig_info, "video"):
        raise RemuxError("Video stream count decreased after remux")
    if _count(new_info, "audio") < _count(orig_info, "audio"):
        raise RemuxError("Audio stream count decreased after remux")

    # Subtitle count should be exactly n_removed less.
    # If orig_subs < n_removed the container was already modified by a concurrent
    # worker — raise a clear error so the caller can log it as a harmless skip.
    orig_subs = _count(orig_info, "subtitle")
    new_subs = _count(new_info, "subtitle")
    if orig_subs < n_removed:
        raise RemuxError(
            f"Subtitle streams already removed (orig={orig_subs}, wanted to remove {n_removed})"
            " — concurrent modification?"
        )
    expected = orig_subs - n_removed
    if new_subs != expected:
        raise RemuxError(f"Unexpected subtitle stream count: expected {expected}, got {new_subs}")

    # File size sanity (≥ 50 % of original)
    orig_size = os.path.getsize(original_path)
    new_size = os.path.getsize(remuxed_path)
    if orig_size > 0 and new_size < orig_size * 0.5:
        raise RemuxError(f"Remuxed file suspiciously small: {new_size} vs original {orig_size}")

    logger.info(
        "Remux verification passed: dur=%.1fs streams(v=%d a=%d s=%d)",
        new_dur,
        _count(new_info, "video"),
        _count(new_info, "audio"),
        new_subs,
    )


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def remove_subtitle_streams(
    video_path: str,
    streams: list[tuple[int, int]],
    use_reflink: bool = True,
    trash_dir: str = ".sublarr",
) -> str:
    """Remove one or more subtitle streams from a video container in one pass.

    Parameters
    ----------
    video_path:
        Absolute path to the source video file.
    streams:
        List of (stream_index, subtitle_track_index) tuples.
        stream_index = global ffprobe index (used by ffmpeg -map).
        subtitle_track_index = 0-based subtitle-only index (used by mkvmerge).
    use_reflink:
        Attempt CoW reflink for the backup copy (Btrfs/XFS).
    trash_dir:
        Relative or absolute path for the trash folder (default ".sublarr").
        Backups land in <trash_dir>/trash/<date>/<file>.<timestamp>.bak.

    Returns
    -------
    str
        Path to the created backup file.

    Raises
    ------
    RemuxError
        On any failure (backend not found, remux error, verification failure).
    """
    if not streams:
        raise RemuxError("No streams specified for removal")

    backend = _detect_backend(video_path)
    video_dir = os.path.dirname(video_path)
    suffix = os.path.splitext(video_path)[1]

    # For mkvmerge: use global stream indices (same convention as single-stream)
    # For ffmpeg: use global stream indices
    stream_indices = [s[0] for s in streams]

    fd, tmp_path = tempfile.mkstemp(suffix=suffix, dir=video_dir)
    os.close(fd)

    try:
        logger.info(
            "Remux: starting (%s) — removing %d stream(s) %s from %s",
            backend,
            len(streams),
            stream_indices,
            video_path,
        )
        if backend == "mkvmerge" and _which("mkvmerge"):
            _remux_mkvmerge(video_path, stream_indices, tmp_path)
        elif backend == "mkvmerge":
            logger.warning(
                "mkvmerge not found — falling back to ffmpeg for MKV "
                "(install mkvtoolnix for better support)"
            )
            _remux_ffmpeg(video_path, stream_indices, tmp_path)
        else:
            _remux_ffmpeg(video_path, stream_indices, tmp_path)

        _verify(video_path, tmp_path, n_removed=len(streams))

        # Atomic swap: original → trash dir, temp → original
        bak_path = _make_backup(video_path, use_reflink, trash_dir)
        os.replace(tmp_path, video_path)
        logger.info("Remux: complete — %d stream(s) removed, backup at %s", len(streams), bak_path)
        return bak_path

    except Exception:
        if os.path.exists(tmp_path):
            with contextlib_suppress(OSError):
                os.unlink(tmp_path)
        raise


def remove_subtitle_stream(
    video_path: str,
    stream_index: int,
    subtitle_track_index: int,
    use_reflink: bool = True,
    trash_dir: str = ".sublarr",
) -> str:
    """Remove a single subtitle stream. Convenience wrapper around remove_subtitle_streams."""
    return remove_subtitle_streams(
        video_path=video_path,
        streams=[(stream_index, subtitle_track_index)],
        use_reflink=use_reflink,
        trash_dir=trash_dir,
    )


def contextlib_suppress(exc_type):
    """Tiny suppress context manager to avoid extra import."""
    import contextlib

    return contextlib.suppress(exc_type)


# ---------------------------------------------------------------------------
# Sidecar cleanup — post-extract language filtering
# ---------------------------------------------------------------------------

# Sidecar extensions we ever produce or import from providers.
_SIDECAR_EXTS = (".ass", ".srt", ".vtt", ".sub")

# Modifier suffixes that can appear between lang and extension:
#   show.en.forced.srt, show.de.sdh.ass, show.en.hi.vtt
# We preserve them so the cleanup knows "lang=en" even when there's a modifier.
_SIDECAR_MODIFIERS = ("forced", "sdh", "hi", "cc", "sign", "signs")


def _parse_sidecar_language(candidate: str, video_base: str) -> str | None:
    """Return the language tag (untreated) of a sidecar, or None if it is not
    a recognisable `<video_base>.<lang>[.<modifier>].<ext>` sidecar.

    The caller is expected to pass the fully-qualified sidecar path plus the
    media file's base (path without video extension). The function is tolerant
    to any of our supported sidecar extensions and to a single optional
    modifier token (forced/sdh/hi/cc/signs).
    """
    base_dir, base_file = os.path.split(video_base)
    name = os.path.basename(candidate)
    if not name.startswith(base_file + "."):
        return None
    ext = os.path.splitext(name)[1].lower()
    if ext not in _SIDECAR_EXTS:
        return None
    remainder = name[len(base_file) + 1 : -len(ext)]  # everything between '.' and '.ext'
    if not remainder:
        return None
    parts = remainder.split(".")
    # Strip a trailing known modifier, e.g. 'en.forced' -> 'en'
    if len(parts) >= 2 and parts[-1].lower() in _SIDECAR_MODIFIERS:
        parts = parts[:-1]
    if len(parts) != 1:
        return None
    return parts[0]


def trash_non_target_sidecars(
    video_path: str,
    keep_langs: set[str],
    trash_dir: str = ".sublarr",
) -> list[tuple[str, str]]:
    """Move extracted subtitle sidecars whose language is not in ``keep_langs``
    into the same trash folder used by the remux backup.

    Args:
        video_path: Absolute path to the media file (the sidecars are siblings).
        keep_langs: Normalised ISO 639-1 codes to preserve (e.g. {'de','en'}).
            Callers typically pass the profile's target_languages plus
            source_language when translation is enabled.
        trash_dir: Same semantics as in ``_make_backup`` — relative to the
            media root or absolute.

    Returns a list of ``(original_path, trash_path)`` tuples for logging.
    Unknown language tags (including 'und' and codes that are not in our
    lookup table) are KEPT on disk — we do not destroy data we cannot classify.
    """
    import datetime
    import glob

    # Late import to avoid a cycle with config_language_data -> config
    from config_language_data import normalize_language_code

    video_base = os.path.splitext(video_path)[0]
    moved: list[tuple[str, str]] = []

    # Build a candidate list across supported extensions.
    candidates: list[str] = []
    for ext in _SIDECAR_EXTS:
        candidates.extend(glob.glob(f"{video_base}.*{ext}"))

    for candidate in candidates:
        raw_lang = _parse_sidecar_language(candidate, video_base)
        if raw_lang is None:
            continue  # not a lang-tagged sidecar
        normalised = normalize_language_code(raw_lang)
        # Safety net: never delete ambiguous or unrecognised tags.
        if not normalised or normalised == "und":
            continue
        if normalised in keep_langs:
            continue
        # Build the trash destination using the existing helper layout.
        resolved = _resolve_trash_dir(video_path, trash_dir or ".sublarr")
        date_str = datetime.date.today().isoformat()
        dest_dir = os.path.join(resolved, "trash", date_str)
        try:
            os.makedirs(dest_dir, exist_ok=True)
            dest = os.path.join(dest_dir, os.path.basename(candidate))
            # Rare collision: if a file with the same name is already in trash,
            # append a unique suffix rather than overwriting.
            if os.path.exists(dest):
                import time as _time

                stem, ext = os.path.splitext(dest)
                dest = f"{stem}.{int(_time.time())}{ext}"
            shutil.move(candidate, dest)
            moved.append((candidate, dest))
            logger.info("Sidecar cleanup: trashed %s (lang=%s)", candidate, normalised)
        except OSError as exc:
            logger.warning("Sidecar cleanup: could not trash %s: %s", candidate, exc)
    return moved
