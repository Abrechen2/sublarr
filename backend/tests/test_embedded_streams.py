"""Tests for get_all_subtitle_streams in ass_utils."""
from unittest.mock import patch

import pytest

PROBE_EN_ASS_JA_SRT = {
    "streams": [
        {"codec_type": "video", "codec_name": "h264"},
        {"codec_type": "audio", "codec_name": "aac", "tags": {"language": "jpn"}},
        {"codec_type": "subtitle", "codec_name": "ass", "tags": {"language": "eng"}},
        {"codec_type": "subtitle", "codec_name": "subrip", "tags": {"language": "jpn"}},
        {"codec_type": "subtitle", "codec_name": "ass", "tags": {"language": "deu"}},
    ]
}

PROBE_EMPTY = {"streams": []}

PROBE_NO_SUBS = {
    "streams": [
        {"codec_type": "video", "codec_name": "h264"},
        {"codec_type": "audio", "codec_name": "aac"},
    ]
}

PROBE_UNKNOWN_CODEC = {
    "streams": [
        {"codec_type": "subtitle", "codec_name": "dvd_subtitle", "tags": {"language": "eng"}},
        {"codec_type": "subtitle", "codec_name": "ass", "tags": {"language": "eng"}},
    ]
}

PROBE_DUPLICATE = {
    "streams": [
        {"codec_type": "subtitle", "codec_name": "ass", "tags": {"language": "eng"}},
        {"codec_type": "subtitle", "codec_name": "ass", "tags": {"language": "eng"}},
    ]
}


@pytest.fixture(autouse=True)
def mock_lang_tags():
    """Mock _get_language_tags to avoid real config loading."""
    def fake_tags(lang):
        mapping = {
            "de": {"deu", "ger", "de"},
            "en": {"eng", "en"},
            "ja": {"jpn", "ja"},
        }
        return mapping.get(lang, {lang})

    with patch("config._get_language_tags", side_effect=fake_tags):
        yield


def test_returns_all_non_target_streams():
    from ass_utils import get_all_subtitle_streams
    result = get_all_subtitle_streams(PROBE_EN_ASS_JA_SRT, exclude_language="de")
    langs = {r["lang"] for r in result}
    assert "eng" in langs
    assert "jpn" in langs
    assert "deu" not in langs


def test_excludes_target_language():
    from ass_utils import get_all_subtitle_streams
    result = get_all_subtitle_streams(PROBE_EN_ASS_JA_SRT, exclude_language="en")
    langs = {r["lang"] for r in result}
    assert "eng" not in langs
    assert "deu" in langs


def test_formats_correctly():
    from ass_utils import get_all_subtitle_streams
    result = get_all_subtitle_streams(PROBE_EN_ASS_JA_SRT, exclude_language="de")
    by_lang = {r["lang"]: r["format"] for r in result}
    assert by_lang["eng"] == "ass"
    assert by_lang["jpn"] == "srt"


def test_empty_probe_returns_empty():
    from ass_utils import get_all_subtitle_streams
    assert get_all_subtitle_streams(PROBE_EMPTY) == []


def test_no_subtitle_streams_returns_empty():
    from ass_utils import get_all_subtitle_streams
    assert get_all_subtitle_streams(PROBE_NO_SUBS) == []


def test_skips_unknown_codecs():
    from ass_utils import get_all_subtitle_streams
    result = get_all_subtitle_streams(PROBE_UNKNOWN_CODEC)
    assert len(result) == 1
    assert result[0]["format"] == "ass"


def test_deduplicates_same_lang_format():
    from ass_utils import get_all_subtitle_streams
    result = get_all_subtitle_streams(PROBE_DUPLICATE)
    assert len(result) == 1


def test_no_exclude_returns_all():
    from ass_utils import get_all_subtitle_streams
    result = get_all_subtitle_streams(PROBE_EN_ASS_JA_SRT, exclude_language=None)
    assert len(result) == 3  # eng, jpn, deu
