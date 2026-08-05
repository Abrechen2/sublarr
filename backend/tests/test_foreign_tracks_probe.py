"""Tests for the shared per-file foreign-track verdict."""

from services.foreign_tracks.probe import expand_keep_languages, foreign_languages


def _probe(*langs):
    return {"streams": [{"codec_type": "subtitle", "tags": {"language": lang}} for lang in langs]}


def test_returns_languages_outside_the_keep_set():
    keep = expand_keep_languages(["de", "en"])
    assert foreign_languages(_probe("spa", "ger", "ita"), keep, keep_und=False) == ["spa", "ita"]


def test_keeps_every_tag_of_a_kept_language():
    keep = expand_keep_languages(["de"])
    assert foreign_languages(_probe("ger", "deu", "de"), keep, keep_und=False) == []


def test_und_is_foreign_unless_kept():
    keep = expand_keep_languages(["de"])
    assert foreign_languages(_probe("und"), keep, keep_und=False) == ["und"]
    assert foreign_languages(_probe("und"), keep, keep_und=True) == []


def test_a_missing_language_tag_counts_as_und():
    keep = expand_keep_languages(["de"])
    probe = {"streams": [{"codec_type": "subtitle", "tags": {}}]}
    assert foreign_languages(probe, keep, keep_und=False) == ["und"]


def test_non_subtitle_streams_are_ignored():
    keep = expand_keep_languages(["de"])
    probe = {"streams": [{"codec_type": "audio", "tags": {"language": "spa"}}]}
    assert foreign_languages(probe, keep, keep_und=False) == []


def test_empty_keep_set_yields_nothing_rather_than_everything():
    """Guard duty belongs to the caller, but this helper must not be the one
    that hands back 'strip every subtitle in the library'."""
    assert foreign_languages(_probe("spa", "ger"), set(), keep_und=False) == []
