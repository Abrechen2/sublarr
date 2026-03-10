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


def _remux_mkvmerge(video_path: str, subtitle_track_index: int, output_path: str) -> None:
    """Remove subtitle stream using mkvmerge.

    `subtitle_track_index` is the 0-based index within subtitle tracks only
    (as used by mkvmerge's --subtitle-tracks !N flag).
    """

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
    trash_dir: str = ".sublarr",
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
    trash_dir:
        Relative or absolute path for the trash folder (default ".sublarr").
        Backups land in <trash_dir>/trash/<date>/<file>.<timestamp>.bak.

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
        if backend == "mkvmerge" and _which("mkvmerge"):
            _remux_mkvmerge(video_path, subtitle_track_index, tmp_path)
        elif backend == "mkvmerge":
            logger.warning(
                "mkvmerge not found — falling back to ffmpeg for MKV (install mkvtoolnix for better support)"
            )
            _remux_ffmpeg(video_path, stream_index, tmp_path)
        else:
            _remux_ffmpeg(video_path, stream_index, tmp_path)

        _verify(video_path, tmp_path)

        # Atomic swap: original → trash dir, temp → original
        bak_path = _make_backup(video_path, use_reflink, trash_dir)
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
