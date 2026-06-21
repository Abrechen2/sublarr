import pytest

from services.subtitle_health.fixers import common


def test_atomic_write_replaces(tmp_path):
    p = tmp_path / "x.srt"
    p.write_bytes(b"old")
    common.atomic_write_bytes(str(p), b"new content")
    assert p.read_bytes() == b"new content"


def test_count_cues_matches():
    raw = b"1\n00:00:01,000 --> 00:00:02,000\nA\n\n2\n00:00:03,000 --> 00:00:04,000\nB\n"
    assert common.count_cues(raw) == 2


def test_validate_cue_count_raises_on_mismatch():
    before = b"1\n00:00:01,000 --> 00:00:02,000\nA\n"
    after = b""
    with pytest.raises(common.FixValidationError):
        common.validate_cue_count(before, after)
