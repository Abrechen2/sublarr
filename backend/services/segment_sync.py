"""One shift per stretch for a subtitle timed to another edit of the video.

A subtitle taken from another release often fits the video stretch by
stretch but not as a whole: the other release had a few seconds more before
the episode title or at the eyecatch. ffsubsync can only shift, or stretch
the whole timeline, and answers such a file with a framerate scale, which the
scale gate rejects (prod 2026-10-30: Slime S02E19 stayed 2.5-4 s late).

Here the dialogue is split into blocks at its pauses, every block is scored
against the video's speech at every shift, and a Viterbi pass picks one shift
per block, paying a penalty for every change. Blocks that end up with the
same shift form one stretch. Signs and songs carry no speech the detector
can rely on; a change of shift is placed in the last pause between the two
blocks where nothing at all is shown, and every line moves with the stretch
it starts in.

A plan is refused when the shifts change more often than an edit plausibly
does (a framerate drift would become a staircase) or when it does not beat
what the same search finds against the video's speech rolled out of place.
"""

from __future__ import annotations

import glob
import logging
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger(__name__)

_CS = 10  # ms per speech sample: ffsubsync's speech arrays run at 100 Hz
_STEP_CS = 2  # shifts are tried in 20 ms steps
_SPLIT_GAP_MS = 5_000  # a pause this long may hide a cut
_MAX_BLOCK_MS = 90_000  # longer blocks are split at their widest pause
_CHANGE_PENALTY_CS = 1_500  # 15 s of net speech: a cut must clearly pay off
_MAX_JUMP_MS = 10_000  # an edit adds or drops seconds, not half a minute
_MAX_CHANGES = 3  # cold open / opening, eyecatch, ending: more is a drift
_DECOYS = 8  # the speech rolled by k/9 of its length, k = 1..8

_NON_DIALOGUE_STYLE = re.compile(
    r"(?i)(?:^|[^a-z])(?:op|ed|ts)(?:[^a-z]|$)|sign|title|kara|song|insert|note"
)
_SONG_STYLE = re.compile(r"(?i)(?:^|[^a-z])(?:op|ed)(?:[^a-z]|$)|kara|song|insert")
_KARAOKE_TAG = re.compile(r"\\(?:k|kf|ko|K)\d")
_MIN_CUT_PAUSE_MS = 300
_SONG_MERGE_MS = 20_000  # an opening's instrumental bars are still the opening
_TYPESET_TAG = re.compile(r"\\(?:pos|move|k|kf|ko|K|p[1-9])\b")


@dataclass(frozen=True)
class SegmentPlan:
    """Where each stretch starts (in the subtitle's time) and how far it moves.

    The first stretch starts at 0; a stretch runs until the next one starts,
    the last one until ``end_ms``.
    """

    stretches: tuple[tuple[int, int], ...]
    end_ms: int

    @property
    def offsets(self) -> list[int]:
        return [off for _, off in self.stretches]

    def offset_at(self, ms: int) -> int:
        off = self.stretches[0][1]
        for start, stretch_off in self.stretches:
            if ms >= start:
                off = stretch_off
        return off

    @property
    def main_offset_ms(self) -> int:
        """The shift of the longest stretch."""
        bounds = [start for start, _ in self.stretches] + [self.end_ms]
        longest = max(range(len(self.stretches)), key=lambda i: bounds[i + 1] - bounds[i])
        return self.stretches[longest][1]


def is_dialogue(event) -> bool:
    if event.is_comment or not event.text:
        return False
    if _NON_DIALOGUE_STYLE.search(event.style or ""):
        return False
    return not _TYPESET_TAG.search(event.text)


def _blocks(spans: list[tuple[int, int]]) -> list[list[tuple[int, int]]]:
    blocks: list[list[tuple[int, int]]] = []
    end = None
    for span in spans:
        if end is None or span[0] - end >= _SPLIT_GAP_MS:
            blocks.append([])
            end = span[1]
        blocks[-1].append(span)
        end = max(end, span[1])
    out: list[list[tuple[int, int]]] = []
    for block in blocks:
        out.extend(_split_long(block))
    return out


def _split_long(block: list[tuple[int, int]]) -> list[list[tuple[int, int]]]:
    if len(block) < 2 or block[-1][1] - block[0][0] <= _MAX_BLOCK_MS:
        return [block]
    reach, widest, at = block[0][1], -1, 1
    for i in range(1, len(block)):
        gap = block[i][0] - reach
        if gap > widest:
            widest, at = gap, i
        reach = max(reach, block[i][1])
    return _split_long(block[:at]) + _split_long(block[at:])


def _block_scores(block, prefix: np.ndarray, shifts_cs: np.ndarray) -> np.ndarray:
    """Net speech (speech minus silence, in samples) under the block at every shift."""
    last = len(prefix) - 1
    total = np.zeros(len(shifts_cs), dtype=np.int64)
    for start, end in block:
        a = np.clip(start // _CS + shifts_cs, 0, last)
        b = np.clip(end // _CS + shifts_cs, 0, last)
        total += prefix[b] - prefix[a]
    return total


def _window_argmax(values: np.ndarray, reach: int) -> np.ndarray:
    """For every index, the index of the largest value within ``reach`` of it."""
    floor = np.full(reach, np.iinfo(np.int64).min)
    windows = np.lib.stride_tricks.sliding_window_view(
        np.concatenate((floor, values, floor)), 2 * reach + 1
    )
    return np.argmax(windows, axis=1) + np.arange(len(values)) - reach


def _best_path(blocks, speech: np.ndarray, shifts_cs: np.ndarray) -> tuple[list[int], int]:
    """Viterbi over the blocks: one shift index each, a penalty per change."""
    signed = np.where(speech > 0.5, 1, -1).astype(np.int64)
    prefix = np.concatenate(([0], np.cumsum(signed)))
    reach = _MAX_JUMP_MS // (_CS * _STEP_CS)
    best = _block_scores(blocks[0], prefix, shifts_cs)
    back: list[np.ndarray] = []
    for block in blocks[1:]:
        jump_from = _window_argmax(best, reach)
        jump = best[jump_from] - _CHANGE_PENALTY_CS
        back.append(np.where(best >= jump, np.arange(len(best)), jump_from))
        best = np.maximum(best, jump) + _block_scores(block, prefix, shifts_cs)
    path = [int(np.argmax(best))]
    for came in reversed(back):
        path.append(int(came[path[-1]]))
    path.reverse()
    return path, int(best.max())


def _stands_out(net: int, blocks, speech: np.ndarray, shifts_cs: np.ndarray) -> bool:
    """Does the plan beat what the same search finds against unrelated speech?

    The search picks the best of thousands of shifts per block, so even a
    subtitle for another episode reaches a score. The decoys are the video's
    own speech, rolled far out of place: the plan must beat the best of them
    by their spread (Slime S02E19: 7000 above the best decoy, spread 3300;
    random subtitles stayed below their best decoy).
    """
    decoys = [
        _best_path(blocks, np.roll(speech, len(speech) * k // (_DECOYS + 1)), shifts_cs)[1]
        for k in range(1, _DECOYS + 1)
    ]
    margin = max(float(np.std(decoys)), float(_CHANGE_PENALTY_CS))
    if net < max(decoys) + margin:
        logger.info(
            "segment sync: plan %d does not beat the best decoy %d by %d", net, max(decoys), margin
        )
        return False
    return True


def _shown(subs) -> list[tuple[int, int]]:
    """When signs and songs are on screen; a song counts as one span."""
    songs, other = [], []
    for e in subs.events:
        if e.is_comment or is_dialogue(e) or e.end <= e.start:
            continue
        is_song = _SONG_STYLE.search(e.style or "") or _KARAOKE_TAG.search(e.text)
        (songs if is_song else other).append((e.start, e.end))
    merged: list[tuple[int, int]] = []
    for start, end in sorted(songs):
        if merged and start - merged[-1][1] < _SONG_MERGE_MS:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged + other


def _cut_between(lo: int, hi: int, shown: list[tuple[int, int]]) -> int:
    """Where in [lo, hi] the shift changes: the last pause in which nothing is shown.

    The pause must be ``_MIN_CUT_PAUSE_MS`` long; without one the cut sits
    just before ``hi``. The last pause, because what lies between two
    dialogue blocks (an opening, an eyecatch) belongs with what came before
    it: Slime S02E19's opening starts on the cold open's timing and the 2.5 s
    are missing after its last line, before the episode title. The widest
    pause would have been the opening's 17 s of bars before its first lyric.
    """
    covered = sorted((max(a, lo), min(b, hi)) for a, b in shown if b > lo and a < hi)
    at, reach = None, lo
    for a, b in [*covered, (hi, hi)]:
        if a - reach >= _MIN_CUT_PAUSE_MS:
            at = (reach + a) // 2
        reach = max(reach, b)
    return at if at is not None else max(lo, hi - _MIN_CUT_PAUSE_MS // 2)


def plan_segments(subs, speech: np.ndarray, *, max_offset_ms: int) -> SegmentPlan | None:
    """The per-stretch shifts that put ``subs``' dialogue on ``speech``, or None."""
    spans = sorted((e.start, e.end) for e in subs.events if is_dialogue(e) and e.end > e.start)
    speech = np.asarray(speech)
    if not spans or len(speech) == 0:
        return None
    blocks = _blocks(spans)
    limit = max_offset_ms // _CS
    shifts_cs = np.arange(-limit, limit + 1, _STEP_CS)

    path, net = _best_path(blocks, speech, shifts_cs)
    offsets = [int(shifts_cs[i]) * _CS for i in path]
    changes = sum(1 for a, b in zip(offsets, offsets[1:]) if a != b)
    if changes > _MAX_CHANGES:
        logger.info("segment sync: %d shift changes look like a drift, not an edit", changes)
        return None
    if not _stands_out(net, blocks, speech, shifts_cs):
        return None

    others = _shown(subs)
    stretches = [(0, offsets[0])]
    for k in range(1, len(blocks)):
        if offsets[k] != offsets[k - 1]:
            end_before = max(e for _, e in blocks[k - 1])
            stretches.append((_cut_between(end_before, blocks[k][0][0], others), offsets[k]))
    return SegmentPlan(stretches=tuple(stretches), end_ms=spans[-1][1])


def apply_plan(subs, plan: SegmentPlan) -> None:
    """Move every event of ``subs`` by its stretch's shift, in place."""
    for event in subs.events:
        off = plan.offset_at(event.start)
        event.start = max(0, event.start + off)
        event.end = max(0, event.end + off)


def load_speech(video_path: str) -> np.ndarray | None:
    """ffsubsync's speech detection of ``video_path``, 100 samples per second.

    ffsubsync writes the array next to its reference, so it reads the video
    through a symlink in a temporary directory, never beside the media.
    """
    from security_utils import safe_subprocess_arg
    from services.sync_engines.concurrency import nice_prefix, sync_subprocess_lock

    work = tempfile.mkdtemp(prefix="sublarr-speech-")
    try:
        link = os.path.join(work, "video" + os.path.splitext(video_path)[1])
        os.symlink(os.path.abspath(video_path), link)
        cmd = [*nice_prefix(), "ffsubsync", safe_subprocess_arg(link), "--serialize-speech"]
        with sync_subprocess_lock:
            subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        found = glob.glob(os.path.join(work, "*.npz"))
        if not found:
            return None
        with np.load(found[0]) as data:
            return np.asarray(data[data.files[0]])
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        logger.warning("segment sync: speech detection failed for %s: %s", video_path, exc)
        return None
    finally:
        shutil.rmtree(work, ignore_errors=True)


def segment_sync_into(
    subtitle_path: str, video_path: str, out_path: str, *, max_offset_ms: int
) -> SegmentPlan | None:
    """Write ``subtitle_path`` with one shift per stretch to ``out_path``.

    Returns the plan, or None (``out_path`` untouched) when there is none.
    """
    from services.video_sync import _PYSUBS2_FORMATS
    from subtitle_encoding import load_subtitle_file

    try:
        subs = load_subtitle_file(subtitle_path)
    except Exception as exc:  # noqa: BLE001 — undecodable or malformed: no plan
        logger.warning("segment sync: could not read %s: %s", subtitle_path, exc)
        return None
    speech = load_speech(video_path)
    if speech is None:
        return None
    plan = plan_segments(subs, speech, max_offset_ms=max_offset_ms)
    if plan is None:
        return None
    apply_plan(subs, plan)
    ext = os.path.splitext(subtitle_path)[1].lstrip(".").lower()
    subs.save(out_path, encoding="utf-8", format_=_PYSUBS2_FORMATS.get(ext))
    logger.info("segment sync: %s → shifts %s ms", subtitle_path, plan.offsets)
    return plan
