# backend/subtitle_types.py
"""Shared types for subtitle processing — no imports from other project modules."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Change:
    event_index: int
    timestamp: str       # "HH:MM:SS,mmm --> HH:MM:SS,mmm"
    original_text: str
    modified_text: str   # empty string = event removed
    mod_name: str


def _ms_to_str(ms: int) -> str:
    h = ms // 3_600_000
    m = (ms % 3_600_000) // 60_000
    s = (ms % 60_000) // 1_000
    rem = ms % 1_000
    return f"{h:02d}:{m:02d}:{s:02d},{rem:03d}"
