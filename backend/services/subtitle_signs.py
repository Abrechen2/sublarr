"""Classify a subtitle (sidecar or embedded stream) as full/signs/forced/songs.

Combines the existing multi-signal forced/signs detector
(forced_detection.detect_subtitle_type — disposition, filename, title,
ASS-style) with a cue-density fallback (a signs/forced track is sparse; a
dialogue track is dense). Pure functions, no filesystem mutation.
"""

from __future__ import annotations

import logging
from enum import StrEnum
from typing import Literal

from services.subtitle_cues import cue_statistics

logger = logging.getLogger(__name__)

Subtype = Literal["full", "signs", "forced", "songs"]

SIGNS_MAX_DENSITY = 3.0
MIN_FULLTEXT_CUES = 40
MIN_SPAN_MS = 120_000  # don't density-judge a clip shorter than 2 min


class SignsRemovalLevel(StrEnum):
    OFF = "off"
    SIGNS = "signs"
    SIGNS_FORCED = "signs_forced"
    SIGNS_FORCED_SONGS = "signs_forced_songs"

    @classmethod
    def from_str(cls, value: str | None) -> SignsRemovalLevel:
        try:
            return cls(value) if value else cls.OFF
        except ValueError:
            return cls.OFF


_REMOVABLE_BY_LEVEL: dict[SignsRemovalLevel, frozenset[str]] = {
    SignsRemovalLevel.OFF: frozenset(),
    SignsRemovalLevel.SIGNS: frozenset({"signs"}),
    SignsRemovalLevel.SIGNS_FORCED: frozenset({"signs", "forced"}),
    SignsRemovalLevel.SIGNS_FORCED_SONGS: frozenset({"signs", "forced", "songs"}),
}


def is_removable(subtype: Subtype, level: SignsRemovalLevel) -> bool:
    if subtype == "full":
        return False
    return subtype in _REMOVABLE_BY_LEVEL.get(level, frozenset())


def _is_songs_title(title: str) -> bool:
    t = (title or "").lower()
    return "song" in t and "sign" not in t


def _density_is_sparse(cues: list | None) -> bool:
    if not cues:
        return False
    span = max(c.end_ms for c in cues) - min(c.start_ms for c in cues)
    if span < MIN_SPAN_MS:
        return False
    density, _cps, _overlap = cue_statistics(cues)
    return len(cues) < MIN_FULLTEXT_CUES or density <= SIGNS_MAX_DENSITY


def classify_stream(stream_info: dict, *, cues: list | None = None) -> Subtype:
    """Classify an embedded subtitle stream. Density only consulted if cues given."""
    from forced_detection import detect_subtitle_type

    title = ""
    tags = stream_info.get("tags") or {}
    if isinstance(tags, dict):
        title = (tags.get("title") or "").strip()
    if _is_songs_title(title):
        return "songs"

    subtype, _conf = detect_subtitle_type(stream_info=stream_info)
    if subtype in ("signs", "forced"):
        return subtype  # type: ignore[return-value]

    if cues is not None and _density_is_sparse(cues):
        return "signs"
    return "full"


def classify_sidecar(path: str, *, use_density: bool) -> Subtype:
    """Classify a sidecar file by filename/ASS-style and optionally density."""
    import os

    from forced_detection import detect_subtitle_type

    name = os.path.basename(path).lower()
    if "song" in name and "sign" not in name:
        return "songs"

    ass_content = None
    if path.lower().endswith((".ass", ".ssa")):
        try:
            import pysubs2

            ass_content = pysubs2.load(path)
        except Exception as exc:
            logger.debug("subtitle_signs: could not parse ASS %s: %s", path, exc)
            ass_content = None

    subtype, _conf = detect_subtitle_type(file_path=path, ass_content=ass_content)
    if subtype in ("signs", "forced"):
        return subtype  # type: ignore[return-value]

    if use_density:
        from services.subtitle_cues import load_cues

        if _density_is_sparse(load_cues(path)):
            return "signs"
    return "full"
