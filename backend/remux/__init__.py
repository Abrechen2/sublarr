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


def _make_backup(video_path: str, use_reflink: bool) -> str:
    """Create <video_path>.bak and return the backup path."""
    bak_path = video_path + ".bak"
    if use_reflink and _try_reflink(video_path, bak_path):
        logger.info("Remux: reflink backup created: %s", bak_path)
    else:
        shutil.copy2(video_path, bak_path)
        logger.info("Remux: regular copy backup created: %s", bak_path)
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


def _remux_mkvmerge(video_path: str, stream_index: int, output_path: str) -> None:
    """Remove subtitle stream `stream_index` using mkvmerge.

    mkvmerge uses 0-based subtitle-track IDs within the subtitle track list.
    `stream_index` here is the ffprobe-style global stream index; we pass it
    as the subtitle track number because mkvmerge numbers subtitle tracks
    separately starting at 0.
    """
    if not _which("mkvmerge"):
        raise RemuxError("mkvmerge not found — install mkvtoolnix")

    # --subtitle-tracks !N removes subtitle track N (0-based within subtitle tracks)
    cmd = [
        "mkvmerge",
        "-o",
        output_path,
        "--subtitle-tracks",
        f"!{stream_index}",
        video_path,
    ]
    logger.debug("Remux mkvmerge: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode not in (0, 1):  # mkvmerge exit 1 = warnings, still OK
        raise RemuxError(f"mkvmerge failed (exit {result.returncode}): {result.stderr[:500]}")


# ---------------------------------------------------------------------------
# ffmpeg backend
# ---------------------------------------------------------------------------


def _remux_ffmpeg(video_path: str, stream_index: int, output_path: str) -> None:
    """Remove subtitle stream `stream_index` using ffmpeg stream copy."""
    if not _which("ffmpeg"):
        raise RemuxError("ffmpeg not found")

    # Map all streams, then un-map the target subtitle stream by global index
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        video_path,
        "-map",
        "0",
        "-map",
        f"-0:{stream_index}",
        "-c",
        "copy",
        output_path,
    ]
    logger.debug("Remux ffmpeg: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
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


def _verify(original_path: str, remuxed_path: str) -> None:
    """Compare duration, stream count, and file size between original and remux."""
    orig_info = _probe(original_path)
    new_info = _probe(remuxed_path)

    # Duration check (±2 s)
    orig_dur = float(orig_info.get("format", {}).get("duration", 0))
    new_dur = float(new_info.get("format", {}).get("duration", 0))
    if orig_dur > 0 and abs(orig_dur - new_dur) > 2.0:
        raise RemuxError(f"Duration mismatch: original={orig_dur:.1f}s remuxed={new_dur:.1f}s")

    # Video + audio stream count must not decrease
    def _count(info: dict, codec_type: str) -> int:
        return sum(1 for s in info.get("streams", []) if s.get("codec_type") == codec_type)

    if _count(new_info, "video") < _count(orig_info, "video"):
        raise RemuxError("Video stream count decreased after remux")
    if _count(new_info, "audio") < _count(orig_info, "audio"):
        raise RemuxError("Audio stream count decreased after remux")
    # Subtitle count should be exactly one less
    orig_subs = _count(orig_info, "subtitle")
    new_subs = _count(new_info, "subtitle")
    if new_subs != orig_subs - 1:
        raise RemuxError(
            f"Unexpected subtitle stream count: expected {orig_subs - 1}, got {new_subs}"
        )

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
# Public entry point
# ---------------------------------------------------------------------------


def remove_subtitle_stream(
    video_path: str,
    stream_index: int,
    subtitle_track_index: int,
    use_reflink: bool = True,
) -> str:
    """Remove a subtitle stream from a video container.

    Parameters
    ----------
    video_path:
        Absolute path to the source video file.
    stream_index:
        The ffprobe global stream index (0-based across all streams).
    subtitle_track_index:
        The 0-based index within the subtitle-only track list (for mkvmerge).
    use_reflink:
        Attempt CoW reflink for the backup copy (Btrfs/XFS).

    Returns
    -------
    str
        Path to the created backup file (<video_path>.bak).

    Raises
    ------
    RemuxError
        On any failure (backend not found, remux error, verification failure).
    """
    backend = _detect_backend(video_path)
    video_dir = os.path.dirname(video_path)
    suffix = os.path.splitext(video_path)[1]

    # Write remux output to a temp file in the same directory (same filesystem)
    fd, tmp_path = tempfile.mkstemp(suffix=suffix, dir=video_dir)
    os.close(fd)

    try:
        logger.info(
            "Remux: starting (%s) — removing stream %d (sub_idx %d) from %s",
            backend,
            stream_index,
            subtitle_track_index,
            video_path,
        )
        if backend == "mkvmerge":
            _remux_mkvmerge(video_path, subtitle_track_index, tmp_path)
        else:
            _remux_ffmpeg(video_path, stream_index, tmp_path)

        _verify(video_path, tmp_path)

        # Atomic swap: original → .bak, temp → original
        bak_path = _make_backup(video_path, use_reflink)
        os.replace(tmp_path, video_path)
        logger.info("Remux: complete — backup at %s", bak_path)
        return bak_path

    except Exception:
        # Clean up temp file on any failure
        if os.path.exists(tmp_path):
            with contextlib_suppress(OSError):
                os.unlink(tmp_path)
        raise


def contextlib_suppress(exc_type):
    """Tiny suppress context manager to avoid extra import."""
    import contextlib

    return contextlib.suppress(exc_type)
