"""Plan B5 — subtitle_repair unit tests."""

from pathlib import Path

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
