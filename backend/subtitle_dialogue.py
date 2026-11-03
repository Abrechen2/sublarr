"""Is a subtitle plausibly the full dialogue track, or only signs?

Prod 2026-11 (Slime S03E24): AnimeTosho's "English Signs [Official]" track,
7 events in style "Default" with actor "Sign", passed every check. The style
classifier reads "Default" as dialogue, and the cues spanned 68 % of the
episode, so the coverage check passed too. The file replaced a 405-cue SRT
as an upgrade and was translated to a "German subtitle" without one line of
dialogue.

This module counts what a viewer would read as dialogue and judges that
count against the video length. The thresholds are deliberately low: a sparse
but genuine subtitle (a near-silent episode, a three-minute short) must pass,
because the verdict blocks downloads and translations unattended.
"""

from __future__ import annotations

import logging
import os
import re
import threading
from dataclasses import dataclass

logger = logging.getLogger(__name__)

#: Fewer dialogue lines than this are never a full subtitle — unless the video
#: is known to be shorter than MIN_RATED_DURATION_S (a one-minute short may
#: hold seven lines; only an empty one is judged there).
MIN_DIALOGUE_EVENTS = 10
#: With a known length of at least MIN_RATED_DURATION_S: fewer than
#: RATED_DIALOGUE_EVENTS lines AND fewer than MIN_EVENTS_PER_MINUTE is sparse.
#: A 24-minute episode holds 250-400 lines; on the reference library every
#: full-named sidecar under 40 lines for such an episode was a signs track.
#: The 40 matches the dubtitle detector's _MIN_FULLTEXT_CUES.
RATED_DIALOGUE_EVENTS = 40
MIN_EVENTS_PER_MINUTE = 2.0
MIN_RATED_DURATION_S = 180.0
#: A replacement holding less than this share of the old file's lines lost
#: the dialogue — if the old file had at least DROP_MIN_OLD_EVENTS (below
#: that a few lines more or less are noise, not a lost track).
DROP_MAX_SHARE = 0.25
DROP_MIN_OLD_EVENTS = 8

# Actor names typesetters use for sign events. Anchored: a character named
# "Signe" or "Tsuki" must not match.
_SIGN_ACTOR = re.compile(r"^\s*(?:signs?|typeset(?:ting)?|ts)\s*$", re.IGNORECASE)
# No nested "{": an unclosed block stops at the next one, keeping this linear.
_CLOSED_BLOCK = re.compile(r"\{[^{}]*\}")


@dataclass(frozen=True)
class DialogueAssessment:
    dialogue_events: int
    total_events: int
    per_minute: float | None
    sparse_reason: str | None


def _plain(text: str) -> str:
    """The readable text: tags and drawing geometry removed (linear lexer).

    The lexer refuses malformed events (an unclosed override block); those fall
    back to dropping closed blocks, which still counts the text they hold.
    """
    from ass_utils import text_outside_drawing

    try:
        visible = text_outside_drawing(text)
    except Exception:  # noqa: BLE001 — ASSNeedsReviewError and friends: count, don't fail
        visible = _CLOSED_BLOCK.sub("", text)
    return visible.replace("\\N", " ").replace("\\n", " ").replace("\\h", " ").strip()


def _visible_events(subs, dialog_styles):
    """Yield (event, plain text, is_dialogue) for every event a viewer sees."""
    for event in subs.events:
        if event.is_comment:
            continue
        plain = _plain(event.text)
        if not plain:
            continue
        is_dialogue = (
            dialog_styles is None or event.style in dialog_styles
        ) and not _SIGN_ACTOR.match(event.name or "")
        yield event, plain, is_dialogue


def _dialogue_lines(subs, dialog_styles) -> tuple[int, int]:
    """(dialogue lines, visible events): layers and repeats counted once."""
    seen: set[tuple[int, int, str]] = set()
    visible = 0
    for event, plain, is_dialogue in _visible_events(subs, dialog_styles):
        visible += 1
        if is_dialogue:
            seen.add((event.start, event.end, plain))
    return len(seen), visible


def assess(subs, duration_s: float | None, *, is_ass: bool) -> DialogueAssessment:
    """Judge a parsed subtitle. ``is_ass`` selects style-aware counting."""
    dialog_styles = None
    if is_ass:
        from ass_utils import classify_styles

        dialog_styles, _signs = classify_styles(subs)
    lines, visible = _dialogue_lines(subs, dialog_styles)
    return judge(lines, visible, duration_s)


def judge(lines: int, visible: int, duration_s: float | None) -> DialogueAssessment:
    """The sparse verdict for a dialogue-line count against the video length.

    Shared by :func:`assess` and the sidecar check, which caches the counts.
    """
    per_minute = lines / (duration_s / 60) if duration_s and duration_s > 0 else None

    reason = None
    short = duration_s is not None and 0 < duration_s < MIN_RATED_DURATION_S
    if lines == 0 or (lines < MIN_DIALOGUE_EVENTS and not short):
        reason = f"{lines} dialogue lines of {visible} events"
    elif (
        per_minute is not None
        and duration_s >= MIN_RATED_DURATION_S
        and lines < RATED_DIALOGUE_EVENTS
        and per_minute < MIN_EVENTS_PER_MINUTE
    ):
        reason = f"{lines} dialogue lines in {duration_s / 60:.0f} min ({per_minute:.1f}/min)"
    return DialogueAssessment(lines, visible, per_minute, reason)


def sparse_source_reason(subs, video_path: str | None, *, is_ass: bool) -> str | None:
    """Why ``subs`` is no full source for translating ``video_path``, or None.

    Judged only against a known video length: without one there is no way to
    tell a signs track from a short. Never raises — a check that cannot run
    must not block a translation.
    """
    try:
        import subtitle_plausibility

        duration = subtitle_plausibility.video_duration_s(video_path) if video_path else None
        if not duration:
            return None
        return assess(subs, duration, is_ass=is_ass).sparse_reason
    except Exception as exc:  # noqa: BLE001
        logger.debug("Sparse-source check skipped for %s: %s", video_path, exc)
        return None


def _parse(content: bytes):
    """(subs, is_ass) or None when the content is no readable subtitle."""
    if not content:
        return None
    try:
        import pysubs2

        from subtitle_encoding import ensure_utf8, is_wide_unicode

        if is_wide_unicode(content):
            content = ensure_utf8(content)
        text = content.decode("utf-8-sig", errors="replace")
        subs = pysubs2.SSAFile.from_string(text)
    except Exception:  # noqa: BLE001 — unreadable: no verdict, other checks decide
        return None
    if not subs.events:
        return None
    return subs, subs.format in ("ass", "ssa")


def assess_content(content: bytes, duration_s: float | None) -> DialogueAssessment | None:
    """Judge raw subtitle bytes; None when they cannot be read."""
    parsed = _parse(content)
    if parsed is None:
        return None
    subs, is_ass = parsed
    try:
        return assess(subs, duration_s, is_ass=is_ass)
    except Exception as exc:  # noqa: BLE001 — no verdict rather than a failed download
        logger.debug("Dialogue assessment skipped: %s", exc)
        return None


def dialogue_drop(old_content: bytes, new_content: bytes) -> str | None:
    """Why ``new_content`` would lose the dialogue ``old_content`` holds, or None.

    Cue counts differ between releases (merged or split lines), so only a
    collapse counts: the new file keeps under a quarter of the old lines.
    """
    old = assess_content(old_content, None)
    new = assess_content(new_content, None)
    if old is None or new is None or old.dialogue_events < DROP_MIN_OLD_EVENTS:
        return None
    if new.dialogue_events < old.dialogue_events * DROP_MAX_SHARE:
        return (
            f"replacement holds {new.dialogue_events} dialogue lines, "
            f"the existing subtitle {old.dialogue_events}"
        )
    return None


#: Largest sidecar read for the on-disk check; a real subtitle is far smaller.
_MAX_SIDECAR_BYTES = 8 * 1024 * 1024
_COUNT_CACHE_MAX = 8192
_count_cache: dict[tuple[str, int, int], tuple[int, int] | None] = {}
_count_lock = threading.Lock()


def _sidecar_counts(path: str) -> tuple[int, int] | None:
    """(dialogue lines, visible events) of a sidecar, cached per path, mtime and size."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    key = (path, st.st_mtime_ns, st.st_size)
    with _count_lock:
        if key in _count_cache:
            return _count_cache[key]
    counts = None
    if 0 < st.st_size <= _MAX_SIDECAR_BYTES:
        try:
            with open(path, "rb") as fh:
                parsed = _parse(fh.read())
            if parsed is not None:
                subs, is_ass = parsed
                assessment = assess(subs, None, is_ass=is_ass)
                counts = (assessment.dialogue_events, assessment.total_events)
        except Exception as exc:  # noqa: BLE001 — no verdict, never a failed scan
            logger.debug("Sparse sidecar check skipped for %s: %s", path, exc)
    with _count_lock:
        if len(_count_cache) >= _COUNT_CACHE_MAX:
            _count_cache.clear()
        _count_cache[key] = counts
    return counts


def sparse_sidecar_reason(sidecar_path: str | None, video_path: str | None) -> str | None:
    """Why the full sidecar on disk is signs/credits only, or None.

    Prod 2026-11: a German ``.de.ass`` of 10 title-card and credit lines for a
    24-minute episode counted as the full subtitle, so the episode was never
    searched again. Judged only against a known video length (the cached
    stream probe): without one a signs track cannot be told from a short.
    Only for full sidecars — the caller passes ``.de.ass``/``.de.srt``, never
    a ``.forced`` or signs file. Never raises.
    """
    if not sidecar_path or not video_path:
        return None
    try:
        counts = _sidecar_counts(sidecar_path)
        if counts is None:
            return None
        lines, visible = counts
        if lines >= RATED_DIALOGUE_EVENTS:
            return None  # never sparse; skip the duration lookup
        import subtitle_plausibility

        duration = subtitle_plausibility.video_duration_s(video_path)
        if not duration:
            return None
        return judge(lines, visible, duration).sparse_reason
    except Exception as exc:  # noqa: BLE001
        logger.debug("Sparse sidecar check skipped for %s: %s", sidecar_path, exc)
        return None


def dialogue_starts(content: bytes) -> list[float] | None:
    """Sorted start times (seconds) of the dialogue lines; None when unreadable.

    Signs, songs and typesetting are left out the way :func:`assess` leaves
    them out, so two releases of the same episode compare on what is spoken.
    """
    parsed = _parse(content)
    if parsed is None:
        return None
    subs, is_ass = parsed
    try:
        dialog_styles = None
        if is_ass:
            from ass_utils import classify_styles

            dialog_styles, _signs = classify_styles(subs)
        starts = {
            event.start
            for event, _plain, is_dialogue in _visible_events(subs, dialog_styles)
            if is_dialogue
        }
    except Exception as exc:  # noqa: BLE001 — no timing verdict rather than a failed download
        logger.debug("Dialogue start times skipped: %s", exc)
        return None
    return [ms / 1000.0 for ms in sorted(starts)]
