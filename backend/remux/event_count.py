"""Per-file subtitle event counts for the track variant tie-break.

``select_tracks`` breaks a tie between two equally ranked main tracks of one
language by their number of dialogue events. The count must never read the
whole file: on prod (2026-09-26) ``ffprobe -count_packets`` took 5 minutes
for one 44 GB remux and would have stretched the sweep's probe phase over
21 066 files to weeks.

Sources, in order:

1. The MKV statistics tags. mkvmerge writes ``NUMBER_OF_FRAMES`` (the packet
   count) into every track, and the stream probe the caller already holds
   returns it — no extra read at all.
2. A short sample from the start of the file (``-read_intervals``) when any
   subtitle stream lacks the tag. One missing tag makes the whole file use
   the sample, so a tie never compares a whole-file count with a partial one.

The counter is lazy (nothing runs until a tie asks) and memoised (one source
per file). A failed count answers 0 for every stream, which makes the tie
fall back to the lower stream index.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from collections.abc import Callable

logger = logging.getLogger(__name__)

# Seconds of the file the fallback sample reads, and its timeout.
_SAMPLE_SECONDS = 300
_SAMPLE_TIMEOUT_S = 120
_FRAMES_TAG = "NUMBER_OF_FRAMES"


def _which(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def _tag_count(stream: dict) -> int | None:
    """``NUMBER_OF_FRAMES`` (or ``NUMBER_OF_FRAMES-<lang>``) as an int, else None."""
    for key, value in (stream.get("tags") or {}).items():
        name = str(key).upper()
        if name == _FRAMES_TAG or name.startswith(_FRAMES_TAG + "-"):
            try:
                return int(str(value).strip())
            except (TypeError, ValueError):
                return None
    return None


def _counts_from_tags(streams: list[dict] | None) -> dict[int, int] | None:
    """Counts for every subtitle stream from its statistics tag, or None when
    any subtitle stream lacks a usable tag."""
    if not streams:
        return None
    counts: dict[int, int] = {}
    for stream in streams:
        if stream.get("codec_type") != "subtitle" or stream.get("index") is None:
            continue
        count = _tag_count(stream)
        if count is None:
            return None
        counts[int(stream["index"])] = count
    return counts or None


def _count_sample_packets(video_path: str) -> dict[int, int]:
    """``{global stream index: packets in the first _SAMPLE_SECONDS}``."""
    from security_utils import safe_subprocess_arg

    if not _which("ffprobe"):
        raise RuntimeError("ffprobe not found")
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-read_intervals",
        f"%+{_SAMPLE_SECONDS}",
        "-select_streams",
        "s",
        "-count_packets",
        "-show_entries",
        "stream=index,nb_read_packets",
        "-of",
        "json",
        safe_subprocess_arg(video_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=_SAMPLE_TIMEOUT_S)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe exited {result.returncode}: {result.stderr[:300]}")
    counts: dict[int, int] = {}
    for stream in json.loads(result.stdout or "{}").get("streams", []):
        index = stream.get("index")
        if index is None:
            continue
        try:
            counts[int(index)] = int(stream.get("nb_read_packets") or 0)
        except (TypeError, ValueError):
            counts[int(index)] = 0
    return counts


def make_event_counter(video_path: str, streams: list[dict] | None = None) -> Callable[[int], int]:
    """A memoised ``count_events(stream_index) -> int`` for ``video_path``.

    ``streams`` is the probe the caller already holds; its statistics tags
    answer without any read. Without them the first call counts a short
    sample. On failure every count is 0 (logged as a warning), so the
    tie-break falls back to the lower stream index — the pre-1.15.0 order.
    """
    cache: dict[int, int] | None = None

    def count_events(stream_index: int) -> int:
        nonlocal cache
        if cache is None:
            cache = _counts_from_tags(streams)
        if cache is None:
            try:
                cache = _count_sample_packets(video_path)
            except Exception as exc:  # noqa: BLE001 — a tie-break must never fail the strip
                logger.warning(
                    "subtitle packet count failed for %s: %s — tie falls back to the lower index",
                    video_path,
                    exc,
                )
                cache = {}
        return cache.get(stream_index, 0)

    return count_events
