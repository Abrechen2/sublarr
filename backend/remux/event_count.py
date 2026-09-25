"""Per-file subtitle event counts for the track variant tie-break.

``select_tracks`` breaks a tie between two equally ranked main tracks of one
language by their number of dialogue events. Counting them means reading the
whole file (``ffprobe -count_packets``), so the counter is lazy — nothing
runs until a tie asks for a count — and memoised: one ffprobe per file
answers every stream. A failed count answers 0 for every stream, which makes
the tie fall back to the lower stream index.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from collections.abc import Callable

logger = logging.getLogger(__name__)

# A packet count reads the whole file; a large remux over NFS takes a while.
_COUNT_TIMEOUT_S = 600


def _which(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def _count_subtitle_packets(video_path: str) -> dict[int, int]:
    """``{global stream index: packet count}`` for every subtitle stream."""
    from security_utils import safe_subprocess_arg

    if not _which("ffprobe"):
        raise RuntimeError("ffprobe not found")
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "s",
        "-count_packets",
        "-show_entries",
        "stream=index,nb_read_packets",
        "-of",
        "json",
        safe_subprocess_arg(video_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=_COUNT_TIMEOUT_S)
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


def make_event_counter(video_path: str) -> Callable[[int], int]:
    """A memoised ``count_events(stream_index) -> int`` for ``video_path``.

    The first call runs one ffprobe over the file; later calls read the
    cached result. On failure every count is 0 (logged as a warning), so the
    tie-break falls back to the lower stream index — the pre-1.15.0 order.
    """
    cache: dict[int, int] | None = None

    def count_events(stream_index: int) -> int:
        nonlocal cache
        if cache is None:
            try:
                cache = _count_subtitle_packets(video_path)
            except Exception as exc:  # noqa: BLE001 — a tie-break must never fail the strip
                logger.warning(
                    "subtitle packet count failed for %s: %s — tie falls back to the lower index",
                    video_path,
                    exc,
                )
                cache = {}
        return cache.get(stream_index, 0)

    return count_events
