"""Tests for the signs/forced/songs classifier + level mapping."""

import pytest


def test_level_from_str_defaults_off():
    from services.subtitle_signs import SignsRemovalLevel

    assert SignsRemovalLevel.from_str(None) is SignsRemovalLevel.OFF
    assert SignsRemovalLevel.from_str("bogus") is SignsRemovalLevel.OFF
    assert SignsRemovalLevel.from_str("signs_forced") is SignsRemovalLevel.SIGNS_FORCED


@pytest.mark.parametrize(
    "subtype,level,expected",
    [
        ("full", "signs_forced_songs", False),  # full is NEVER removable
        ("signs", "off", False),
        ("signs", "signs", True),
        ("forced", "signs", False),
        ("forced", "signs_forced", True),
        ("songs", "signs_forced", False),
        ("songs", "signs_forced_songs", True),
    ],
)
def test_is_removable(subtype, level, expected):
    from services.subtitle_signs import SignsRemovalLevel, is_removable

    assert is_removable(subtype, SignsRemovalLevel(level)) is expected


def test_classify_stream_forced_disposition():
    from services.subtitle_signs import classify_stream

    stream = {"disposition": {"forced": 1}, "tags": {}}
    assert classify_stream(stream) == "forced"


def test_classify_stream_signs_title():
    from services.subtitle_signs import classify_stream

    stream = {"disposition": {}, "tags": {"title": "Signs & Songs"}}
    assert classify_stream(stream) == "signs"


def test_classify_sidecar_filename(tmp_path):
    from services.subtitle_signs import classify_sidecar

    p = tmp_path / "Show.S01E01.en.signs.ass"
    p.write_text("x", encoding="utf-8")
    assert classify_sidecar(str(p), use_density=False) == "signs"


def test_classify_stream_density_sparse_when_unlabeled():
    from services.subtitle_cues import Cue
    from services.subtitle_signs import classify_stream

    stream = {"disposition": {}, "tags": {}}  # no metadata label
    sparse = [Cue(0, 2000, "SHOP"), Cue(600_000, 602_000, "EXIT")]
    # density signal only applies when cues passed
    assert classify_stream(stream, cues=sparse) == "signs"


def test_classify_stream_density_full_when_dense():
    from services.subtitle_cues import Cue
    from services.subtitle_signs import classify_stream

    stream = {"disposition": {}, "tags": {}}
    dense = [Cue(i * 1000, i * 1000 + 800, "hello there friend") for i in range(120)]
    assert classify_stream(stream, cues=dense) == "full"
