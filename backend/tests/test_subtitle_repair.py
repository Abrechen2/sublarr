"""Plan B5 — subtitle_repair unit tests."""

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "subtitle_repair"


def test_repair_strips_bom_from_srt():
    from subtitle_repair import repair_bytes

    raw = (FIXTURES / "bom_at_start.srt").read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")

    fixed = repair_bytes(raw, fmt="srt")
    assert not fixed.startswith(b"\xef\xbb\xbf")
    # Content after BOM is preserved
    assert b"Hello." in fixed
    assert b"World." in fixed


def test_repair_normalizes_wrong_newlines_in_srt():
    from subtitle_repair import repair_bytes

    raw = (FIXTURES / "wrong_newlines.srt").read_bytes()
    assert b"\r\r\n" in raw  # fixture precondition

    fixed = repair_bytes(raw, fmt="srt")
    assert b"\r\r\n" not in fixed
    assert b"\r\n" not in fixed  # we normalize to LF-only for consistency
    # Content preserved
    assert b"Hello." in fixed
    assert b"00:00:01,000 --> 00:00:02,000" in fixed


def test_repair_is_noop_on_valid_baseline():
    from subtitle_repair import repair_bytes

    raw = (FIXTURES / "valid_baseline.srt").read_bytes()
    fixed = repair_bytes(raw, fmt="srt")
    assert fixed == raw  # no-op on already-clean content


def test_repair_pads_invalid_decimals():
    from subtitle_repair import repair_bytes

    raw = (FIXTURES / "invalid_decimals.srt").read_bytes()
    assert b"00:00:01,4 " in raw  # precondition: 1-digit decimal
    assert b"00:00:02,45 " in raw or b"00:00:02,45\n" in raw  # 2-digit

    fixed_bytes = repair_bytes(raw, fmt="srt")
    fixed = fixed_bytes.decode("utf-8")
    # All timestamps now have 3-digit milliseconds
    assert "00:00:01,400" in fixed
    assert "00:00:02,450" in fixed
    # Valid ones untouched
    assert "00:00:03,123" in fixed
    assert "00:00:04,567" in fixed


def test_repair_clamps_overlapping_cues():
    from subtitle_repair import repair_bytes

    raw = (FIXTURES / "overlapping_cues.srt").read_bytes()
    fixed = repair_bytes(raw, fmt="srt").decode("utf-8")

    # Cue 1's end should be clamped to 00:00:02,999 (cue 2 starts at 03,000)
    # The 5,000 original end must be gone
    assert "00:00:05,000" not in fixed
    # The clamped end — one of 02,999 / 02,998 is acceptable (implementation choice)
    assert "00:00:02,999" in fixed or "00:00:02,998" in fixed
    # Cue 2 and 3 are untouched
    assert "00:00:03,000 --> 00:00:07,000" in fixed
    assert "00:00:10,000 --> 00:00:12,000" in fixed


def test_repair_recovers_windows1252_mislabeled_bytes():
    from subtitle_repair import repair_bytes

    raw = (FIXTURES / "windows1252_mislabeled.srt").read_bytes()
    # Precondition: raw is NOT valid UTF-8
    with pytest.raises(UnicodeDecodeError):
        raw.decode("utf-8")

    fixed_bytes = repair_bytes(raw, fmt="srt")
    # Result must be valid UTF-8
    fixed = fixed_bytes.decode("utf-8")
    # Smart quotes should either be preserved as UTF-8 (\u2019, \u201c, \u201d)
    # or replaced with a reasonable fallback (regular ASCII apostrophe/quote).
    # The exact choice depends on chardet's decision; accept either.
    assert "test" in fixed
    assert "Hello world" in fixed


def test_repair_handles_ass_format():
    """repair_bytes with fmt='ass' byte-level normalizes but doesn't touch timestamps."""
    from subtitle_repair import repair_bytes

    # BOM + CRLF inside an ASS file
    dirty = (
        b"\xef\xbb\xbf[Script Info]\r\nTitle: Test\r\n\r\n"
        b"[Events]\r\nFormat: Start, End, Text\r\n"
        b"Dialogue: 0:00:01.00,0:00:02.00,Hi\r\n"
    )
    fixed = repair_bytes(dirty, fmt="ass")
    assert not fixed.startswith(b"\xef\xbb\xbf")
    assert b"\r\n" not in fixed
    # ASS timestamps use dots, not commas — must NOT be touched by SRT repair
    assert b"0:00:01.00,0:00:02.00" in fixed
