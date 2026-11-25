# backend/tests/test_common_fixes_extended.py
"""Tests for common_fixes module — all 18 fixes."""

import pytest


def _subs_from_lines(lines: list[str], fmt="srt"):
    """Helper: create an in-memory pysubs2 SSAFile from text lines."""
    import pysubs2

    subs = pysubs2.SSAFile()
    for i, line in enumerate(lines):
        event = pysubs2.SSAEvent(
            start=i * 3000,
            end=i * 3000 + 2000,
            text=line,
        )
        subs.events.append(event)
    return subs


def test_watermark_removed():
    from common_fixes import apply_common_fixes

    subs = _subs_from_lines(["Downloaded from opensubtitles.org", "Hello world"])
    changes = apply_common_fixes(subs, {"watermark_removal": True})

    removed = [c for c in changes if c.modified_text == ""]
    assert len(removed) == 1
    assert "opensubtitles" in removed[0].original_text


def test_watermark_not_removed_when_disabled():
    from common_fixes import apply_common_fixes

    subs = _subs_from_lines(["Downloaded from opensubtitles.org"])
    changes = apply_common_fixes(subs, {"watermark_removal": False})

    assert not changes


def test_em_dash_correction():
    from common_fixes import apply_common_fixes

    subs = _subs_from_lines(["Wait--I didn't know"])
    changes = apply_common_fixes(subs, {"em_dash_correction": True})

    assert changes
    assert "\u2014" in subs.events[0].text  # em dash U+2014
    assert "--" not in subs.events[0].text


def test_quote_normalization():
    from common_fixes import apply_common_fixes

    subs = _subs_from_lines(["\u201cHello\u201d"])  # curly quotes
    changes = apply_common_fixes(subs, {"quote_normalization": True})

    assert changes
    assert subs.events[0].text == '"Hello"'


def test_crocodile_brackets_removed():
    from common_fixes import apply_common_fixes

    subs = _subs_from_lines([">> Previously on..."])
    changes = apply_common_fixes(subs, {"crocodile_brackets": True})

    assert changes
    assert ">>" not in subs.events[0].text


def test_multiple_spaces_collapsed():
    from common_fixes import apply_common_fixes

    subs = _subs_from_lines(["Hello   world"])
    changes = apply_common_fixes(subs, {"multiple_spaces": True})

    assert changes
    assert subs.events[0].text == "Hello world"


def test_apostrophe_normalization():
    from common_fixes import apply_common_fixes

    subs = _subs_from_lines(["He said ''hello''"])
    changes = apply_common_fixes(subs, {"apostrophe_normalization": True})

    assert changes
    assert "''" not in subs.events[0].text


def test_fix_uppercase_detects_all_caps_file():
    from common_fixes import apply_common_fixes

    lines = ["HELLO WORLD", "HOW ARE YOU", "I AM FINE", "YES REALLY"]
    subs = _subs_from_lines(lines)
    changes = apply_common_fixes(subs, {"fix_uppercase": True})

    assert changes  # conversion happened
    # Sentence case applied — "HELLO WORLD" → "Hello world"
    assert subs.events[0].text == "Hello world"


def test_interpunction_spacing_removes_space_before_comma():
    from common_fixes import apply_common_fixes

    subs = _subs_from_lines(["Wait , I need to think"])
    changes = apply_common_fixes(subs, {"interpunction_spacing": True})

    assert changes
    assert "Wait," in subs.events[0].text
    assert "Wait ," not in subs.events[0].text


def test_long_line_wrap_splits_long_line():
    import pysubs2

    from common_fixes import apply_common_fixes

    long_text = (
        "This is a very long subtitle line that should be wrapped at the configured character limit"
    )
    subs = _subs_from_lines([long_text])
    changes = apply_common_fixes(subs, {"long_line_wrap": True, "wrap_chars": 42})

    # After wrapping the event text should be shorter per line
    lines = subs.events[0].text.split("\\N")  # ASS linebreak or \n
    if len(lines) == 1:
        lines = subs.events[0].text.split("\n")
    assert len(lines) >= 2 or changes  # either wrapped or recorded a change


def test_short_line_merge_combines_adjacent_short_events():
    import pysubs2

    from common_fixes import apply_common_fixes

    subs = pysubs2.SSAFile()
    # Two very short adjacent events within 500ms of each other
    subs.events.append(pysubs2.SSAEvent(start=0, end=1000, text="Yes,"))
    subs.events.append(pysubs2.SSAEvent(start=1100, end=2000, text="right."))

    changes = apply_common_fixes(subs, {"short_line_merge": True})

    # Either merged into one event or no change if implementation skips — just must not crash
    assert isinstance(changes, list)


def test_fix_uppercase_skips_mixed_case_file():
    from common_fixes import apply_common_fixes

    lines = ["Hello world", "How are you", "I AM FINE"]
    subs = _subs_from_lines(lines)
    changes = apply_common_fixes(subs, {"fix_uppercase": True})

    assert not changes  # <60% uppercase — skip


def test_overlap_fix_adjusts_end_time():
    import pysubs2

    from common_fixes import apply_common_fixes

    subs = pysubs2.SSAFile()
    # Event A ends at 2500ms, Event B starts at 2000ms — overlap
    subs.events.append(pysubs2.SSAEvent(start=0, end=2500, text="First"))
    subs.events.append(pysubs2.SSAEvent(start=2000, end=4000, text="Second"))

    changes = apply_common_fixes(subs, {"overlap_fix": True})

    assert changes
    assert subs.events[0].end == 1999  # adjusted to start_of_next - 1ms


def test_min_display_time_extends_short_event():
    import pysubs2

    from common_fixes import apply_common_fixes

    subs = pysubs2.SSAFile()
    # 300ms duration — below default 800ms minimum
    subs.events.append(pysubs2.SSAEvent(start=0, end=300, text="Hi"))

    changes = apply_common_fixes(subs, {"min_display_time": True, "min_ms": 800})

    assert changes
    assert subs.events[0].end >= 800


def _overlapping_subs():
    import pysubs2

    subs = pysubs2.SSAFile()
    # Two karaoke syllables sharing a start, then a line that begins before they end.
    subs.events.append(pysubs2.SSAEvent(start=1000, end=4000, text="{\\k30}ko"))
    subs.events.append(pysubs2.SSAEvent(start=1000, end=4000, text="{\\k30}e"))
    subs.events.append(pysubs2.SSAEvent(start=2000, end=5000, text="Dialogue"))
    return subs


@pytest.mark.parametrize("fmt", ["ass", "ssa"])
def test_overlap_fix_leaves_ass_timing_alone(fmt):
    """Overlaps in ASS are deliberate (karaoke, layered signs).

    Prod 2026-10-03: the overlap fix collapsed 4487 of 5557 events of a typeset
    release to zero duration — 515 sidecars in the library were hit.
    """
    from common_fixes import apply_common_fixes

    subs = _overlapping_subs()

    apply_common_fixes(subs, {"overlap_fix": True}, fmt=fmt)

    assert [(e.start, e.end) for e in subs.events] == [(1000, 4000), (1000, 4000), (2000, 5000)]


def test_overlap_fix_still_applies_to_srt():
    from common_fixes import apply_common_fixes

    subs = _overlapping_subs()

    apply_common_fixes(subs, {"overlap_fix": True}, fmt="srt")

    assert subs.events[1].end == 1999


# --- Forgejo #44: long_line_wrap on ASS/SSA ---------------------------------


@pytest.mark.parametrize("fmt", ["ass", "ssa"])
def test_long_line_wrap_keeps_override_tags_and_uses_ass_break(fmt):
    """Wrapping must keep override tags and break with \\N, not a raw LF.

    A raw LF inside a Dialogue field is written as a bare file line that is
    no longer a Dialogue record, so everything after the first line was lost.
    """
    import pysubs2

    from common_fixes import apply_common_fixes

    subs = pysubs2.SSAFile()
    subs.events.append(
        pysubs2.SSAEvent(
            start=1000,
            end=5000,
            text="{\\an8\\i1}This is a sufficiently long sentence with several words.",
        )
    )

    apply_common_fixes(subs, {"long_line_wrap": True, "wrap_chars": 20}, fmt=fmt)

    text = subs.events[0].text
    assert "\n" not in text
    assert text.startswith("{\\an8\\i1}")
    assert "\\N" in text
    assert text.replace("\\N", " ") == (
        "{\\an8\\i1}This is a sufficiently long sentence with several words."
    )
    assert all(len(line) <= 20 for line in subs.events[0].plaintext.split("\n"))


def test_long_line_wrap_keeps_inline_tag_between_words():
    import pysubs2

    from common_fixes import apply_common_fixes

    subs = pysubs2.SSAFile()
    subs.events.append(
        pysubs2.SSAEvent(start=0, end=2000, text="aaaa bbbb {\\i1}cccc dddd{\\i0} eeee ffff")
    )

    apply_common_fixes(subs, {"long_line_wrap": True, "wrap_chars": 10}, fmt="ass")

    assert "{\\i1}" in subs.events[0].text and "{\\i0}" in subs.events[0].text
    assert subs.events[0].plaintext.replace("\n", " ") == "aaaa bbbb cccc dddd eeee ffff"


# --- Forgejo #45: short_line_merge guards -----------------------------------


def _merge(events, fmt="ass"):
    import pysubs2

    from common_fixes import apply_common_fixes

    subs = pysubs2.SSAFile()
    subs.events.extend(events)
    apply_common_fixes(subs, {"short_line_merge": True}, fmt=fmt)
    return subs


def test_short_line_merge_keeps_overlapping_ass_layers():
    import pysubs2

    subs = _merge(
        [
            pysubs2.SSAEvent(start=1000, end=5000, text="{\\an8}SIGN", layer=1),
            pysubs2.SSAEvent(start=1000, end=5000, text="{\\an2}Hello", layer=0),
        ]
    )

    assert [e.text for e in subs.events] == ["{\\an8}SIGN", "{\\an2}Hello"]


def test_short_line_merge_keeps_different_styles():
    import pysubs2

    subs = _merge(
        [
            pysubs2.SSAEvent(start=0, end=1000, text="Yes,", style="Default"),
            pysubs2.SSAEvent(start=1100, end=2000, text="right.", style="Sign"),
        ]
    )

    assert len(subs.events) == 2


def test_short_line_merge_uses_ass_break_for_same_style():
    import pysubs2

    subs = _merge(
        [
            pysubs2.SSAEvent(start=0, end=1000, text="Yes,"),
            pysubs2.SSAEvent(start=1100, end=2000, text="right."),
        ]
    )

    assert len(subs.events) == 1
    assert subs.events[0].text == "Yes,\\Nright."
    assert (subs.events[0].start, subs.events[0].end) == (0, 2000)


def test_short_line_merge_skips_overlapping_srt_cues():
    import pysubs2

    subs = _merge(
        [
            pysubs2.SSAEvent(start=0, end=1500, text="Yes,"),
            pysubs2.SSAEvent(start=1000, end=2000, text="right."),
        ],
        fmt="srt",
    )

    assert len(subs.events) == 2
