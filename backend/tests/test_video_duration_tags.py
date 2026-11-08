"""The video length from a stream probe, whatever spelling the muxer used.

Prod 2026-11: MakeMKV and mkvmerge write the per-track length as
``DURATION-eng``, and the shared stream probe carries no ``format`` section.
The length came out as 0, so every check that needs it (sparse signs tracks,
length plausibility, timing) silently skipped those files.
"""

from remux import _video_duration


def _video(tags: dict, **extra) -> dict:
    return {"streams": [{"codec_type": "video", "tags": tags, **extra}]}


def test_language_suffixed_duration_tag():
    info = _video({"DURATION-eng": "00:23:42.003916666"})
    assert abs(_video_duration(info) - 1422.0039) < 0.01


def test_plain_duration_tag_still_read():
    assert _video_duration(_video({"DURATION": "00:01:30.000000000"})) == 90.0


def test_numeric_stream_duration_wins():
    info = _video({"DURATION-eng": "00:23:42.0"}, duration="1400.5")
    assert _video_duration(info) == 1400.5


def test_unrelated_tag_is_not_a_length():
    assert _video_duration(_video({"NUMBER_OF_FRAMES-eng": "34094"})) == 0.0
