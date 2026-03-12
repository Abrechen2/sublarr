# backend/op_ed_detector.py
"""OP/ED region detection for subtitle files.

Detects Opening (OP) and Ending (ED) cue regions using two passes:
  Pass 1 (ASS/SSA only): Match event style names against known OP/ED patterns.
                          Per-type gating — Pass 2 is skipped only for types
                          already found by Pass 1.
  Pass 2 (fallback):     Position + duration heuristic — cluster of ≥3 events
                          near start/end with expected OP/ED duration.

Returns detected regions as list[dict] without modifying the file.
"""

import re

# ─── Compiled patterns ────────────────────────────────────────────────────────

_OP_STYLE = re.compile(r"^(OP|Opening|OP Theme|Opening Theme)$", re.IGNORECASE)
_ED_STYLE = re.compile(r"^(ED|Ending|ED Theme|Ending Theme)$", re.IGNORECASE)

# ─── Constants ────────────────────────────────────────────────────────────────

_OP_MIN_MS = 60_000  # 60 s minimum OP duration
_OP_MAX_MS = 120_000  # 120 s maximum OP duration
_ED_MIN_MS = 10_000  # 10 s minimum ED duration (ED length varies widely)
_ED_MAX_MS = 180_000  # 180 s maximum ED duration
_MAX_GAP_MS = 3_000  # max gap between events in a cluster
_MIN_EVENTS = 3  # minimum events to form a valid cluster

# ─── SRT timestamp regex ──────────────────────────────────────────────────────

_SRT_TS_RE = re.compile(r"(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})")


def _get_op_window_ms() -> int:
    """Return the OP/ED window size in milliseconds."""
    import os

    env_val = os.environ.get("SUBLARR_OP_WINDOW_SEC")
    if env_val:
        try:
            return int(env_val) * 1_000
        except ValueError:
            pass
    try:
        from config import get_settings

        return getattr(get_settings(), "op_window_sec", 300) * 1_000
    except Exception:
        return 300_000


def detect_op_ed_from_ass(content: str) -> list[dict]:
    """Detect OP/ED regions from ASS/SSA content.

    Returns:
        List of region dicts: {type, start_ms, end_ms, event_count, method}
    """
    try:
        import pysubs2
    except ImportError:
        return []

    subs = pysubs2.SSAFile.from_string(content)
    dialogues = [e for e in subs if not e.is_comment]
    if not dialogues:
        return []

    # Pass 1: style name matching (per-type gating)
    op_region = _pass1_style(dialogues, _OP_STYLE, "OP")
    ed_region = _pass1_style(dialogues, _ED_STYLE, "ED")

    # Pass 2: duration heuristic for types not found by Pass 1
    total_end_ms = max(e.end for e in dialogues)
    window_ms = _get_op_window_ms()

    if window_ms * 2 < total_end_ms:  # windows don't overlap
        events = [{"start": e.start, "end": e.end} for e in dialogues]
        if op_region is None:
            op_region = _pass2_cluster(events, total_end_ms, window_ms, "OP")
        if ed_region is None:
            ed_region = _pass2_cluster(events, total_end_ms, window_ms, "ED")

    return [r for r in [op_region, ed_region] if r is not None]


def detect_op_ed_from_srt(content: str) -> list[dict]:
    """Detect OP/ED regions from SRT content (duration heuristic only).

    Returns:
        List of region dicts: {type, start_ms, end_ms, event_count, method}
    """
    events = _parse_srt_events(content)
    if not events:
        return []

    total_end_ms = max(e["end"] for e in events)
    window_ms = _get_op_window_ms()

    if window_ms * 2 >= total_end_ms:
        return []

    op_region = _pass2_cluster(events, total_end_ms, window_ms, "OP")
    ed_region = _pass2_cluster(events, total_end_ms, window_ms, "ED")

    return [r for r in [op_region, ed_region] if r is not None]


# ─── Detection helpers ────────────────────────────────────────────────────────


def _pass1_style(dialogues: list, pattern: re.Pattern, region_type: str) -> dict | None:
    """Find a region by matching ASS event style names."""
    matching = [{"start": e.start, "end": e.end} for e in dialogues if pattern.match(e.style or "")]
    if not matching:
        return None
    return {
        "type": region_type,
        "start_ms": min(e["start"] for e in matching),
        "end_ms": max(e["end"] for e in matching),
        "event_count": len(matching),
        "method": "style",
    }


def _pass2_cluster(
    events: list[dict],
    total_end_ms: int,
    window_ms: int,
    region_type: str,
) -> dict | None:
    """Find OP or ED region by position + duration heuristic."""
    if region_type == "OP":
        window_start, window_end = 0, window_ms
        min_dur, max_dur = _OP_MIN_MS, _OP_MAX_MS
    else:
        window_start = total_end_ms - window_ms
        window_end = total_end_ms
        min_dur, max_dur = _ED_MIN_MS, _ED_MAX_MS

    candidates = sorted(
        [e for e in events if window_start <= e["start"] < window_end],
        key=lambda e: e["start"],
    )
    if len(candidates) < _MIN_EVENTS:
        return None

    clusters = _split_into_clusters(candidates)
    valid = [
        c
        for c in clusters
        if len(c) >= _MIN_EVENTS and min_dur <= (c[-1]["end"] - c[0]["start"]) <= max_dur
    ]
    if not valid:
        return None

    best = max(valid, key=lambda c: c[-1]["end"] - c[0]["start"])
    region_start, region_end = best[0]["start"], best[-1]["end"]

    return {
        "type": region_type,
        "start_ms": region_start,
        "end_ms": region_end,
        "event_count": sum(1 for e in events if region_start <= e["start"] <= region_end),
        "method": "duration",
    }


def _split_into_clusters(events: list[dict]) -> list[list[dict]]:
    """Split sorted events into contiguous clusters (no gap > _MAX_GAP_MS)."""
    if not events:
        return []
    clusters: list[list[dict]] = []
    current = [events[0]]
    for event in events[1:]:
        if event["start"] - current[-1]["end"] > _MAX_GAP_MS:
            clusters.append(current)
            current = [event]
        else:
            current.append(event)
    clusters.append(current)
    return clusters


def _parse_srt_events(content: str) -> list[dict]:
    """Parse SRT content into event dicts with start/end in ms."""
    events = []
    for block in content.strip().split("\n\n"):
        for line in block.strip().split("\n"):
            m = _SRT_TS_RE.match(line.strip())
            if m:
                start_ms = (
                    int(m.group(1)) * 3_600_000
                    + int(m.group(2)) * 60_000
                    + int(m.group(3)) * 1_000
                    + int(m.group(4))
                )
                end_ms = (
                    int(m.group(5)) * 3_600_000
                    + int(m.group(6)) * 60_000
                    + int(m.group(7)) * 1_000
                    + int(m.group(8))
                )
                events.append({"start": start_ms, "end": end_ms})
                break
    return events
