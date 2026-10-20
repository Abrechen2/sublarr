"""Does a subtitle's time span fit the video it is meant for?

Prod 2026-10 (Clevatess): a 787-event ASS ending at 2738 s — the Blu-ray
double-length episode 1 — was saved for a 1420 s TV episode, and ffsubsync
then "aligned" it by -5 s. Nothing downstream asked whether the file could
belong to that video at all. This module answers that from the cue times
alone (no full parse — a 20 MB typeset ASS is read as text, once):

  - **overrun**: more cues end past ``duration + max(10 %, 120 s)`` than a
    stray late event explains. Applied to every subtitle, forced or not.
  - **coverage**: the cues span less than half of the video. Skipped for
    forced/signs subtitles, which legitimately cover only a few scenes.

Both checks need the video duration and are skipped when it is unknown.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

#: Allowed overrun past the video end: the larger of 10 % and 120 s.
OVERRUN_FRACTION = 0.10
OVERRUN_MIN_S = 120.0
#: Below this share of the video the subtitle is taken to be for another cut.
MIN_COVERAGE = 0.5
#: A few events past the end are a stray line or a fansub's end marker, not a
#: second episode: reject only when more than this many (or this share) overrun.
_STRAY_EVENTS = 3
_STRAY_SHARE = 0.02

# Subtitle content is untrusted provider input (up to 20 MB). Both patterns are
# applied per line with ``match`` (anchored), every quantifier is bounded and
# overlong lines are skipped, so a pathological file costs linear time.
_TS = r"(\d{1,2}):(\d{1,2}):(\d{1,2})(?:[.,](\d{1,3}))?"
_ASS_EVENT = re.compile(
    r"Dialogue:[ \t]{0,8}[^,\n]{0,16},[ \t]{0,8}" + _TS + r"[ \t]{0,8},[ \t]{0,8}" + _TS
)
_SRT_TS = r"(?:(\d{1,2}):)?(\d{1,2}):(\d{2})[,.](\d{1,3})"
_SRT_EVENT = re.compile(r"[ \t]{0,8}" + _SRT_TS + r"[ \t]{0,8}-->[ \t]{0,8}" + _SRT_TS)
#: Lines longer than this are not timing lines (an ASS Dialogue line keeps its
#: times in the first few dozen characters, so only that prefix is examined).
_MAX_TIMING_PREFIX = 128
#: Upper bound on timing lines examined; far above any real subtitle.
_MAX_EVENTS = 200_000
_PARTIAL_RELEASE = re.compile(r"(?<![a-z])(signs?|forced|songs?)(?![a-z])", re.IGNORECASE)


@dataclass(frozen=True)
class SubtitleSpan:
    first_start: float
    last_end: float
    events: int
    ends: tuple[float, ...]


def _seconds(h, m, s, frac) -> float:
    frac = frac or "0"
    return int(h or 0) * 3600 + int(m) * 60 + int(s) + int(frac) / (10 ** len(frac))


def _decode(content: bytes) -> str:
    from subtitle_encoding import ensure_utf8, is_wide_unicode

    if is_wide_unicode(content):
        content = ensure_utf8(content)
    # Timestamps are ASCII in every encoding a subtitle comes in.
    return content.decode("utf-8", "ignore")


def subtitle_span(content: bytes) -> SubtitleSpan | None:
    """Start of the first and end of the last cue, or None when none is found.

    ASS: ``Dialogue:`` lines only — ``Comment:`` lines are never shown.
    SRT/VTT: every ``-->`` timing line.
    """
    if not content:
        return None
    ass_pairs: list[tuple[float, float]] = []
    srt_pairs: list[tuple[float, float]] = []
    for line in _decode(content).splitlines():
        if len(ass_pairs) + len(srt_pairs) >= _MAX_EVENTS:
            break
        head = line[:_MAX_TIMING_PREFIX]
        if head.startswith("Dialogue:"):
            m = _ASS_EVENT.match(head)
            if m:
                ass_pairs.append((_seconds(*m.groups()[:4]), _seconds(*m.groups()[4:])))
        elif len(line) <= _MAX_TIMING_PREFIX and "-->" in line:
            m = _SRT_EVENT.match(line)
            if m:
                srt_pairs.append((_seconds(*m.groups()[:4]), _seconds(*m.groups()[4:])))
    pairs = ass_pairs or srt_pairs
    if not pairs:
        return None
    ends = tuple(sorted(end for _, end in pairs))
    return SubtitleSpan(
        first_start=min(start for start, _ in pairs),
        last_end=ends[-1],
        events=len(pairs),
        ends=ends,
    )


def _overrun_limit(duration_s: float) -> float:
    return duration_s + max(duration_s * OVERRUN_FRACTION, OVERRUN_MIN_S)


def _plausible_end(span: SubtitleSpan) -> float:
    """The last cue end once a few stray late events are discounted."""
    stray = max(_STRAY_EVENTS, int(span.events * _STRAY_SHARE))
    if span.events <= stray:
        return span.last_end
    return span.ends[-(stray + 1)]


def length_mismatch(content: bytes, duration_s: float | None, *, partial_ok: bool) -> str | None:
    """Why ``content`` cannot be a subtitle for a ``duration_s`` video, or None.

    ``partial_ok`` (forced/signs) skips the coverage check; the overrun check
    always applies. An unknown duration or unreadable cue times check nothing.
    """
    if not duration_s or duration_s <= 0:
        return None
    span = subtitle_span(content)
    if span is None:
        return None
    limit = _overrun_limit(duration_s)
    if _plausible_end(span) > limit:
        return (
            f"subtitle ends at {span.last_end:.0f} s ({span.events} events), "
            f"video is {duration_s:.0f} s long"
        )
    if partial_ok:
        return None
    coverage = (min(span.last_end, duration_s) - span.first_start) / duration_s
    if coverage < MIN_COVERAGE:
        return (
            f"subtitle cues cover {coverage:.0%} of the video "
            f"({span.first_start:.0f}-{span.last_end:.0f} s of {duration_s:.0f} s)"
        )
    return None


def is_partial_subtitle(result, query=None) -> bool:
    """Forced/signs subtitles cover only some scenes — no coverage check for them."""
    if query is not None and getattr(query, "forced_only", False):
        return True
    if getattr(result, "forced", False):
        return True
    label = f"{getattr(result, 'release_info', '') or ''} {getattr(result, 'filename', '') or ''}"
    return bool(_PARTIAL_RELEASE.search(label))


def video_duration_s(video_path: str) -> float | None:
    """The video's length from the (cached) stream probe, or None when unknown.

    Uses ``get_media_streams``, which the wanted scan and the search already
    fill per file and mtime — normally a cache hit, never a full decode.
    """
    if not video_path or not os.path.isfile(video_path):
        return None
    try:
        from ass_probe import get_media_streams
        from remux import _video_duration

        duration = _video_duration(get_media_streams(video_path) or {})
    except Exception as exc:  # noqa: BLE001 — an unknown length only skips the check
        logger.debug("plausibility: no duration for %s: %s", video_path, exc)
        return None
    return duration if duration > 0 else None


def file_overruns_video(subtitle_path: str, video_path: str) -> str | None:
    """Overrun check for a sidecar on disk (coverage is not judged here)."""
    duration = video_duration_s(video_path)
    if duration is None:
        return None
    try:
        with open(subtitle_path, "rb") as fh:
            content = fh.read()
    except OSError:
        return None
    return length_mismatch(content, duration, partial_ok=True)
