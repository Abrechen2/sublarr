"""Segment sync: a subtitle cut for another edit gets one shift per stretch.

Prod 2026-10-30, Slime S02E19: the subtitle came from a release with 2.5 s
more after the opening and another 1.5 s more at the eyecatch. ffsubsync
answered with a framerate scale, the scale gate rejected it, and the file
stayed late; a single shift fixed only the middle.
"""

import numpy as np
import pysubs2
import pytest

from services.segment_sync import apply_plan, plan_segments

HZ = 100


def _subs(lines):
    subs = pysubs2.SSAFile()
    for start, end, style in lines:
        subs.events.append(pysubs2.SSAEvent(start=start, end=end, style=style, text="x"))
    return subs


def _dialogue(start_s, end_s, every_s=4.0, length_s=2.5):
    t, out = start_s, []
    while t + length_s <= end_s:
        out.append((int(t * 1000), int((t + length_s) * 1000), "Default"))
        t += every_s + (0.7 if len(out) % 3 == 0 else 0)
    return out


def _speech(lines, offsets, duration_s=1400):
    """Speech where the video has it: each line moved by its stretch's offset."""
    speech = np.zeros(duration_s * HZ, dtype=bool)
    for start, end, style in lines:
        if style != "Default":
            continue
        off = next(o for lo, hi, o in offsets if lo <= start < hi)
        speech[max(0, (start + off) // 10) : max(0, (end + off) // 10)] = True
    return speech


# Cold open, then an opening without dialogue, then two acts split by an eyecatch.
COLD = _dialogue(10, 110)
OPENING = [(t, t + 3000, "OP Romaji") for t in range(114_000, 200_000, 3000)]
ACT_A = _dialogue(206, 660)
ACT_B = _dialogue(700, 1300)
LINES = COLD + OPENING + ACT_A + ACT_B
CUTS = [(0, 203_000, 0), (203_000, 680_000, -2540), (680_000, 10**9, -4040)]


def test_a_subtitle_cut_for_another_edit_gets_one_shift_per_stretch():
    plan = plan_segments(_subs(LINES), _speech(LINES, CUTS), max_offset_ms=45_000)

    assert plan is not None
    assert len(plan.offsets) == 3
    assert [abs(o - want) <= 40 for o, want in zip(plan.offsets, [0, -2540, -4040])] == [
        True,
        True,
        True,
    ]


def test_signs_and_songs_follow_the_nearest_stretch():
    subs = _subs(LINES)
    plan = plan_segments(subs, _speech(LINES, CUTS), max_offset_ms=45_000)

    apply_plan(subs, plan)

    by_style = {}
    for event, (start, _, style) in zip(subs.events, LINES):
        by_style.setdefault(style, set()).add(event.start - start)
    assert len(by_style["OP Romaji"]) == 1
    assert abs(by_style["OP Romaji"].pop()) <= 40


def test_a_plain_shift_stays_one_stretch():
    cuts = [(0, 10**9, -1500)]
    plan = plan_segments(_subs(LINES), _speech(LINES, cuts), max_offset_ms=45_000)

    assert plan is not None
    assert len(set(plan.offsets)) == 1
    assert abs(plan.offsets[0] + 1500) <= 40


def test_a_drifting_subtitle_is_not_turned_into_a_staircase():
    """A PAL speed-up drifts all the way; that is no edit, so no plan."""
    lines = _dialogue(10, 1300)
    cuts = [(t * 1000, (t + 60) * 1000, -int(t * 40)) for t in range(0, 1400, 60)]

    assert plan_segments(_subs(lines), _speech(lines, cuts), max_offset_ms=45_000) is None


def test_no_dialogue_means_no_plan():
    subs = _subs([(1000, 3000, "Sign")])

    assert plan_segments(subs, np.zeros(1000, dtype=bool), max_offset_ms=45_000) is None


@pytest.mark.parametrize("offset", [60_000, -60_000])
def test_a_shift_beyond_the_sanity_threshold_is_never_planned(offset):
    cuts = [(0, 10**9, offset)]
    plan = plan_segments(_subs(LINES), _speech(LINES, cuts, 1500), max_offset_ms=45_000)

    assert plan is None or all(abs(o) <= 45_000 for o in plan.offsets)


def test_the_main_offset_is_the_longest_stretchs():
    from services.segment_sync import SegmentPlan

    plan = SegmentPlan(stretches=((0, 160), (203_450, -2540), (739_130, -4080)), end_ms=1_418_930)

    assert plan.main_offset_ms == -4080
    assert plan.offset_at(0) == 160
    assert plan.offset_at(203_449) == 160
    assert plan.offset_at(203_450) == -2540


def test_the_cut_sits_in_the_last_pause_not_in_the_opening_bars():
    """Slime S02E19: 17 s of opening bars before the first lyric, then the song,
    then 1.6 s of nothing before the episode title; the 2.5 s went missing there."""
    from services.segment_sync import _cut_between

    shown = [(133_570, 202_640), (204_260, 208_520)]

    assert 202_640 < _cut_between(113_000, 205_760, shown) < 204_260


def test_overlapping_blocks_cut_where_the_next_one_starts():
    """Codex review 2026-10-30: the cut landed after the next block's first cue."""
    from services.segment_sync import _cut_between

    assert _cut_between(100_000, 99_000, []) == 99_000


def test_a_video_too_short_for_honest_decoys_gets_no_plan():
    """Codex review 2026-10-30: in a 3-minute video a rolled decoy can be the
    true alignment again, so no comparison is fair and nothing is trusted."""
    lines = [(t, t + 1000, "Default") for t in range(20_000, 150_000, 3000)]
    speech = _speech(lines, [(0, 10**9, 5000)], duration_s=180)

    assert plan_segments(_subs(lines), speech, max_offset_ms=45_000) is None


def test_karaoke_lines_are_not_dialogue():
    from services.segment_sync import is_dialogue

    event = pysubs2.SSAEvent(start=0, end=1000, style="Default", text="{\\k20}Hello {\\k40}world")

    assert not is_dialogue(event)


def test_a_plan_far_from_ffsubsyncs_own_shift_is_refused():
    """Prod dry run 2026-10-30: +6.1 s planned for a file ffsubsync put at +11.2 s."""
    speech = _speech(LINES, CUTS)

    assert plan_segments(_subs(LINES), speech, max_offset_ms=45_000, anchor_ms=-2520) is not None
    assert plan_segments(_subs(LINES), speech, max_offset_ms=45_000, anchor_ms=8000) is None


def test_a_shift_at_the_edge_of_the_search_is_refused():
    cuts = [(0, 10**9, 44_900)]
    speech = _speech(LINES, cuts, 1500)

    assert plan_segments(_subs(LINES), speech, max_offset_ms=45_000) is None
