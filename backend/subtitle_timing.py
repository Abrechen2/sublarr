"""Does a subtitle's timing fit the video it is for?

Prod 2026-11 (Mushoku Tensei S01): three English sidecars passed every check
and sat next to the video for months. One ran 6 s late; two matched no line
of the episode at all (another cut), one of them ending 81 s after the video.
Name, episode number, language, length and kind were all right — only the
timing was wrong, and nothing looked at it.

The check compares when lines start. Two subtitles of the same video start
their lines at the same moments whatever their language, because both follow
the speech: on the reference library 85-100 % of a German track's lines found
an English line within 0.3 s. A track for another cut or episode finds 3-28 %
at any offset, and a delayed one finds the 85 % at a constant offset, which
can simply be undone.

A reference is needed for that, and a reference can be wrong too. An embedded
text track is part of the release and trusted; a sidecar of another language
is used only when no embedded track exists, and its verdict alone never
rejects every candidate (see ``providers.download_manager``).
"""

from __future__ import annotations

import bisect
import logging
from collections import Counter
from dataclasses import dataclass

logger = logging.getLogger(__name__)

#: Two lines "start together" within this many seconds.
TOLERANCE_S = 0.3
#: Offsets searched, in each direction.
MAX_OFFSET_S = 120.0
#: Histogram bucket for the offset search.
_BUCKET_S = 0.1
#: Share of lines that must start together for the timing to fit.
FIT_MATCH = 0.6
#: Below this share at every offset the subtitle belongs to another cut.
MISMATCH_MATCH = 0.35
#: A shift smaller than this is jitter between releases, not a delay.
SHIFT_MIN_S = 0.5
#: Fewer dialogue lines than this on either side give no verdict.
MIN_CUES = 40
#: More than this gives no verdict either: a feature film holds ~2,500 lines,
#: and the content comes from providers, so the work must stay bounded.
MAX_CUES = 6000
#: Line pairs the offset histogram may count before it stops early.
MAX_PAIRS = 2_000_000

FIT = "fit"
SHIFT = "shift"
MISMATCH = "mismatch"
UNCERTAIN = "uncertain"


@dataclass(frozen=True)
class Alignment:
    offset_s: float
    match: float
    verdict: str


def _matches_at(reference: list[float], candidate: list[float], offset: float) -> int:
    """Reference lines with a candidate line starting at ``t + offset`` (± tolerance)."""
    hits = 0
    for t in reference:
        i = bisect.bisect_left(candidate, t + offset - TOLERANCE_S)
        if i < len(candidate) and candidate[i] <= t + offset + TOLERANCE_S:
            hits += 1
    return hits


def align(reference: list[float], candidate: list[float]) -> Alignment | None:
    """Best constant offset of ``candidate`` against ``reference``; None without a verdict.

    ``offset_s`` is how late the candidate runs: shifting it by ``-offset_s``
    lines it up. ``match`` is the share of the shorter track's lines that start
    together at that offset.
    """
    if not (MIN_CUES <= len(reference) <= MAX_CUES and MIN_CUES <= len(candidate) <= MAX_CUES):
        return None
    # Histogram of pairwise start differences within the search window: the
    # true offset collects one vote per line pair, any other offset only
    # chance pairs. Linear in lines x lines-per-window.
    votes: Counter[int] = Counter()
    lo = pairs = 0
    for t in reference:
        if pairs > MAX_PAIRS:
            return None
        while lo < len(candidate) and candidate[lo] < t - MAX_OFFSET_S:
            lo += 1
        j = lo
        while j < len(candidate) and candidate[j] <= t + MAX_OFFSET_S:
            votes[round((candidate[j] - t) / _BUCKET_S)] += 1
            j += 1
        pairs += j - lo
    if not votes:
        return Alignment(0.0, 0.0, MISMATCH)
    # Score the strongest buckets exactly (a bucket edge can split a peak).
    best_offset, best_hits = 0.0, -1
    for bucket, _count in votes.most_common(5):
        for delta in (-1, 0, 1):
            offset = (bucket + delta) * _BUCKET_S
            hits = _matches_at(reference, candidate, offset)
            if hits > best_hits or (hits == best_hits and abs(offset) < abs(best_offset)):
                best_offset, best_hits = offset, hits
    match = best_hits / min(len(reference), len(candidate))
    offset = round(best_offset, 1)
    if match >= FIT_MATCH:
        verdict = FIT if abs(offset) <= SHIFT_MIN_S else SHIFT
    elif match < MISMATCH_MATCH:
        verdict = MISMATCH
    else:
        verdict = UNCERTAIN
    return Alignment(offset, round(match, 2), verdict)


def shift_content(content: bytes, offset_s: float) -> bytes | None:
    """``content`` moved ``offset_s`` seconds earlier, format kept; None if unreadable."""
    try:
        import pysubs2

        from subtitle_encoding import ensure_utf8, is_wide_unicode

        if is_wide_unicode(content):
            content = ensure_utf8(content)
        subs = pysubs2.SSAFile.from_string(content.decode("utf-8-sig", errors="replace"))
        if not subs.events:
            return None
        subs.shift(s=-offset_s)
        fmt = subs.format if subs.format in ("ass", "ssa", "srt") else "srt"
        return subs.to_string(fmt).encode("utf-8")
    except Exception as exc:  # noqa: BLE001 — keep the original rather than fail the download
        logger.debug("Subtitle shift skipped: %s", exc)
        return None


@dataclass(frozen=True)
class Reference:
    starts: list[float]
    #: An embedded track is part of the release; a sidecar may itself be wrong.
    trusted: bool
    source: str


# Codecs ffmpeg can turn into SRT for a timing reference (mov_text included:
# MP4 releases carry their only text track that way).
_TEXT_CODECS = frozenset({"subrip", "srt", "ass", "ssa", "webvtt", "mov_text", "text"})
_SIDECAR_SKIP_MODIFIERS = frozenset({"forced", "signs"})


def _embedded_starts(video_path: str) -> tuple[list[float], str] | None:
    """Dialogue starts of the first full embedded text track, or None. Never raises."""
    import os
    import subprocess
    import tempfile

    try:
        from remux import _safe_arg_path
        from services.subtitle_health.raw_io import list_subtitle_streams

        streams = [s for s in list_subtitle_streams(video_path) if s["codec"] in _TEXT_CODECS]
        streams.sort(key=lambda s: s["forced"])  # full tracks first
        if not streams or streams[0]["forced"]:
            return None
        stream = streams[0]
        fd, tmp_path = tempfile.mkstemp(suffix=".srt")
        os.close(fd)
        try:
            cmd = [
                "ffmpeg", "-v", "error", "-y", "-i", _safe_arg_path(video_path),
                "-map", f"0:s:{stream['sub_index']}", "-c:s", "srt", _safe_arg_path(tmp_path),
            ]  # fmt: skip
            done = subprocess.run(cmd, capture_output=True, timeout=300)
            if done.returncode != 0:
                return None
            with open(tmp_path, "rb") as fh:
                starts = _dialogue_starts(fh.read())
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        if starts is None:
            return None
        return starts, f"embedded track {stream['sub_index']} ({stream['lang']})"
    except Exception as exc:  # noqa: BLE001 — no reference rather than a failed download
        logger.debug("Embedded timing reference skipped for %s: %s", video_path, exc)
        return None


def _dialogue_starts(content: bytes) -> list[float] | None:
    from subtitle_dialogue import dialogue_starts

    return dialogue_starts(content)


def _sidecar_starts(video_path: str, exclude_language: str) -> tuple[list[float], str] | None:
    """Dialogue starts of the fullest sidecar in another language, or None. Never raises."""
    try:
        from config_language_data import normalize_language_code
        from services.sidecar_scan import scan_subtitle_sidecars

        exclude = normalize_language_code(exclude_language or "")
        best: tuple[list[float], str] | None = None
        for entry in scan_subtitle_sidecars(video_path):
            if entry.get("combined") or entry.get("modifier") in _SIDECAR_SKIP_MODIFIERS:
                continue
            if normalize_language_code(entry.get("language") or "") == exclude:
                continue
            with open(entry["path"], "rb") as fh:
                starts = _dialogue_starts(fh.read())
            if starts and (best is None or len(starts) > len(best[0])):
                best = (starts, f"sidecar {entry['path']}")
        return best
    except Exception as exc:  # noqa: BLE001 — no reference rather than a failed download
        logger.debug("Sidecar timing reference skipped for %s: %s", video_path, exc)
        return None


def find_reference(video_path: str, language: str) -> Reference | None:
    """A timing reference for a ``language`` subtitle of ``video_path``, or None.

    Never the same language: the file being replaced may be the wrong one.
    """
    if not video_path:
        return None
    embedded = _embedded_starts(video_path)
    if embedded and len(embedded[0]) >= MIN_CUES:
        return Reference(embedded[0], True, embedded[1])
    sidecar = _sidecar_starts(video_path, language)
    if sidecar and len(sidecar[0]) >= MIN_CUES:
        return Reference(sidecar[0], False, sidecar[1])
    return None
