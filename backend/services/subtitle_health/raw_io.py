"""Raw subtitle I/O for health analysis.

IRON RULE: embedded tracks are extracted with ``ffmpeg -c:s copy`` so the raw
codec payload is preserved. Never use ``ass_probe.extract_subtitle_stream`` or
``ffmpeg -f srt`` for analysis — the SRT encoder silently converts literal
``\\N`` (ASS hard line-break) into real newlines, which hides the very defect
this module exists to detect.
"""

from __future__ import annotations

import hashlib
import logging
import os
import subprocess
import tempfile

logger = logging.getLogger(__name__)

_COPY_EXT = {
    "subrip": "srt",
    "srt": "srt",
    "ass": "ass",
    "ssa": "ass",
    "webvtt": "vtt",
    # mov_text excluded: -c:s copy yields binary TTXT, not text
    "text": "srt",
}

_TEXT_CODECS = frozenset(_COPY_EXT)


def md5_bytes(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def is_text_codec(codec: str) -> bool:
    return (codec or "").lower() in _TEXT_CODECS


def read_sidecar(path: str) -> bytes:
    """Return the raw bytes of a sidecar file."""
    with open(path, "rb") as fh:
        return fh.read()


def list_subtitle_streams(video_path: str) -> list[dict]:
    """Return normalized subtitle streams: sub_index, codec, lang, title, flags."""
    from ass_probe import get_media_streams

    probe = get_media_streams(video_path)
    out: list[dict] = []
    sub_index = 0
    for s in probe.get("streams", []):
        if (s.get("codec_type") or "").lower() != "subtitle":
            continue
        tags = s.get("tags") or {}
        disp = s.get("disposition") or {}
        out.append(
            {
                "sub_index": sub_index,
                "codec": (s.get("codec_name") or "").lower(),
                "lang": tags.get("language") or tags.get("lang") or "und",
                "title": tags.get("title") or "",
                "forced": bool(disp.get("forced")),
                "default": bool(disp.get("default")),
            }
        )
        sub_index += 1
    return out


def extract_track_raw(video_path: str, sub_index: int, codec: str) -> bytes:
    """Extract one subtitle stream's RAW payload via ``ffmpeg -c:s copy``."""
    ext = _COPY_EXT.get((codec or "").lower())
    if ext is None:
        raise RuntimeError(f"unsupported subtitle codec for raw extract: {codec!r}")

    from remux import _safe_arg_path

    fd, tmp_path = tempfile.mkstemp(suffix="." + ext)
    os.close(fd)
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        _safe_arg_path(video_path),
        "-map",
        f"0:s:{sub_index}",
        "-c:s",
        "copy",
        _safe_arg_path(tmp_path),
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
        )
        if result.returncode != 0:
            raise RuntimeError(f"raw extract failed: {result.stderr}")
        with open(tmp_path, "rb") as fh:
            data = fh.read()
        if not data:
            raise RuntimeError("raw extract produced empty output")
        return data
    finally:
        if os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                logger.warning("could not remove tempfile %s", tmp_path)
