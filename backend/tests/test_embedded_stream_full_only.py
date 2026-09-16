"""Only a full-dialogue embedded track satisfies a language.

Codex review 2026-09-16: has_target_language_stream checked language and codec
only, so an English "Signs & Songs" or forced ASS counted as full English
subtitles. With 1.14.3 that result also drops wanted rows (standalone scanner)
and hides "missing" in the episode list — a signs-only track would stop the
search for the dialogue subtitle.
"""

import pytest

from ass_probe import has_target_language_stream


def _stream(codec="ass", lang="eng", title="", forced=0):
    return {
        "codec_type": "subtitle",
        "codec_name": codec,
        "tags": {"language": lang, "title": title},
        "disposition": {"forced": forced},
    }


@pytest.mark.parametrize(
    "stream",
    [
        _stream(forced=1),
        _stream(title="Signs & Songs"),
        _stream(title="Forced"),
        _stream(codec="subrip", title="Signs"),
    ],
)
def test_forced_or_signs_track_does_not_satisfy_the_language(app_ctx, stream):
    assert has_target_language_stream({"streams": [stream]}, "en") is None


def test_full_track_next_to_a_signs_track_still_counts(app_ctx):
    probe = {"streams": [_stream(title="Signs & Songs"), _stream(title="Dialogue")]}

    assert has_target_language_stream(probe, "en") == "ass"


def test_untitled_track_without_disposition_is_full(app_ctx):
    probe = {
        "streams": [{"codec_type": "subtitle", "codec_name": "ass", "tags": {"language": "eng"}}]
    }

    assert has_target_language_stream(probe, "en") == "ass"
