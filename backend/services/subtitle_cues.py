"""Shared subtitle cue loading + density statistics.

Extracted from services/dubtitle/detector.py so the dubtitle detector and
the signs classifier share one implementation. A dense cue track is full
dialogue; a sparse one (few cues / low cues-per-minute) is signs/forced.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Cue:
    start_ms: int
    end_ms: int
    text: str


def load_cues(path: str) -> list[Cue]:
    """Parse a subtitle file into plaintext cues via pysubs2 (encoding-safe)."""
    import pysubs2

    try:
        subs = pysubs2.load(path)
    except Exception:
        try:
            import chardet

            with open(path, "rb") as fh:
                raw = fh.read()
            enc = (chardet.detect(raw).get("encoding") or "utf-8").lower()
            subs = pysubs2.SSAFile.from_string(raw.decode(enc, errors="replace"))
        except Exception as exc:
            logger.debug("subtitle_cues: could not parse %s: %s", path, exc)
            return []

    cues: list[Cue] = []
    for ev in subs:
        if ev.is_comment:
            continue
        text = ev.plaintext or ev.text or ""
        if not text.strip():
            continue
        cues.append(Cue(start_ms=int(ev.start), end_ms=int(ev.end), text=text))
    return cues


def cue_statistics(cues: list[Cue]) -> tuple[float, float, float]:
    """Return (cue_density_per_min, avg_cps, overlap_ratio) for a cue list."""
    if not cues:
        return 0.0, 0.0, 0.0

    span_ms = max(c.end_ms for c in cues) - min(c.start_ms for c in cues)
    span_min = max(span_ms / 60_000.0, 1e-6)
    density = len(cues) / span_min

    cps_values: list[float] = []
    for c in cues:
        dur_s = max((c.end_ms - c.start_ms) / 1000.0, 1e-3)
        chars = len(c.text.replace("\\N", " ").strip())
        if chars:
            cps_values.append(chars / dur_s)
    avg_cps = sum(cps_values) / len(cps_values) if cps_values else 0.0

    ordered = sorted(cues, key=lambda c: c.start_ms)
    overlaps = sum(1 for a, b in zip(ordered, ordered[1:]) if b.start_ms < a.end_ms)
    overlap_ratio = overlaps / max(len(ordered) - 1, 1)

    return density, avg_cps, overlap_ratio
