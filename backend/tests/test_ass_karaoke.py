"""Tests for the ASS karaoke syllable parser (Plan B8 Task 9).

Parses `\\k<cs>`, `\\K<cs>`, `\\kf<cs>`, `\\ko<cs>` override tags out of
an ASS event's raw text and returns per-syllable timing offsets in
seconds. The parser is pure: no pysubs2, no I/O — just string scanning,
so it can be tested in isolation and reused outside the route handler.
"""

from __future__ import annotations


def test_basic_two_syllable_split():
    from services.ass_karaoke import parse_ass_syllables

    syllables = parse_ass_syllables(r"{\k50}Hel{\k60}lo")

    assert len(syllables) == 2
    assert syllables[0]["text"] == "Hel"
    assert syllables[0]["start"] == 0.0
    assert syllables[0]["end"] == 0.5
    assert syllables[1]["text"] == "lo"
    assert syllables[1]["start"] == 0.5
    assert syllables[1]["end"] == 1.1


def test_handles_capital_k_alias():
    """`\\K` is the un-filled variant of `\\k` and uses the same timing."""
    from services.ass_karaoke import parse_ass_syllables

    syllables = parse_ass_syllables(r"{\K30}A{\K40}B")

    assert [s["text"] for s in syllables] == ["A", "B"]
    assert syllables[0]["end"] == 0.3
    assert syllables[1]["end"] == 0.7


def test_handles_kf_and_ko_variants():
    """`\\kf` (sweep) and `\\ko` (outline) also count as syllable boundaries."""
    from services.ass_karaoke import parse_ass_syllables

    syllables = parse_ass_syllables(r"{\kf25}A{\ko75}B")

    assert [s["text"] for s in syllables] == ["A", "B"]
    assert syllables[0]["end"] == 0.25
    assert syllables[1]["end"] == 1.0


def test_no_karaoke_returns_empty():
    """Plain text (no \\k tags) has no syllable structure."""
    from services.ass_karaoke import parse_ass_syllables

    assert parse_ass_syllables("Just plain dialogue") == []


def test_strips_other_override_tags_from_syllable_text():
    """Non-karaoke override blocks (e.g. \\b1) shouldn't leak into the visible syllable text."""
    from services.ass_karaoke import parse_ass_syllables

    syllables = parse_ass_syllables(r"{\k20\b1}Bold{\k30\b0}Plain")

    assert [s["text"] for s in syllables] == ["Bold", "Plain"]


def test_zero_duration_syllable_keeps_position():
    """A `{\\k0}` with no following text shouldn't crash; it just defines a marker."""
    from services.ass_karaoke import parse_ass_syllables

    syllables = parse_ass_syllables(r"{\k50}A{\k0}{\k50}B")

    assert [s["text"] for s in syllables] == ["A", "", "B"]
    assert syllables[1]["start"] == 0.5
    assert syllables[1]["end"] == 0.5


def test_trailing_text_without_terminating_tag():
    """Text after the last `\\k` block belongs to that final syllable."""
    from services.ass_karaoke import parse_ass_syllables

    syllables = parse_ass_syllables(r"{\k40}Hel{\k60}lo there")

    assert [s["text"] for s in syllables] == ["Hel", "lo there"]


def test_text_before_first_k_tag_is_ignored():
    """ASS treats pre-first-\\k content as non-karaoke; we drop it."""
    from services.ass_karaoke import parse_ass_syllables

    syllables = parse_ass_syllables(r"prelude{\k50}A{\k50}B")

    assert [s["text"] for s in syllables] == ["A", "B"]
