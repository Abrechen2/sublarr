"""Tests for wanted_search/profile_filters.py helpers."""

from unittest.mock import MagicMock


def _make_result(release_info: str):
    from providers.base import SubtitleFormat, SubtitleResult

    r = SubtitleResult(
        provider_name="test", subtitle_id="1", language="de", format=SubtitleFormat.SRT
    )
    r.release_info = release_info
    return r


def test_must_contain_filters_out_non_matching():
    from wanted_search.profile_filters import apply_must_contain

    results = [_make_result("BluRay.x265"), _make_result("WEB-DL.x264")]
    filtered = apply_must_contain(results, ["BluRay"])
    assert len(filtered) == 1
    assert filtered[0].release_info == "BluRay.x265"


def test_must_not_contain_removes_matching():
    from wanted_search.profile_filters import apply_must_not_contain

    results = [_make_result("BluRay.x265"), _make_result("HDCAM.x264")]
    filtered = apply_must_not_contain(results, ["HDCAM"])
    assert len(filtered) == 1
    assert filtered[0].release_info == "BluRay.x265"


def test_must_contain_empty_returns_all():
    from wanted_search.profile_filters import apply_must_contain

    results = [_make_result("BluRay"), _make_result("WEB")]
    assert apply_must_contain(results, []) == results


def test_must_not_contain_empty_returns_all():
    from wanted_search.profile_filters import apply_must_not_contain

    results = [_make_result("BluRay"), _make_result("WEB")]
    assert apply_must_not_contain(results, []) == results


def test_load_profile_filters_from_none():
    from wanted_search.profile_filters import load_profile_filters

    pf = load_profile_filters(None)
    assert pf["must_contain"] == []
    assert pf["must_not_contain"] == []
    assert pf["cutoff_language"] == ""
    assert pf["audio_exclude_languages"] == []


def test_load_profile_filters_from_profile():
    from wanted_search.profile_filters import load_profile_filters

    profile = MagicMock()
    profile.must_contain_json = '["BluRay"]'
    profile.must_not_contain_json = '["HDCAM","CAM"]'
    profile.cutoff_language = "de"
    profile.audio_exclude_languages_json = '["de","fr"]'
    pf = load_profile_filters(profile)
    assert pf["must_contain"] == ["BluRay"]
    assert pf["must_not_contain"] == ["HDCAM", "CAM"]
    assert pf["cutoff_language"] == "de"
    assert pf["audio_exclude_languages"] == ["de", "fr"]


def test_load_profile_filters_handles_invalid_json():
    from wanted_search.profile_filters import load_profile_filters

    profile = MagicMock()
    profile.must_contain_json = "not-json"
    profile.must_not_contain_json = '["HDCAM"]'
    profile.cutoff_language = ""
    profile.audio_exclude_languages_json = "[]"
    pf = load_profile_filters(profile)
    assert pf["must_contain"] == []  # graceful fallback on bad JSON
    assert pf["must_not_contain"] == ["HDCAM"]


def test_language_profile_has_filter_columns():
    from db.models.core import LanguageProfile

    assert hasattr(LanguageProfile, "must_contain_json")
    assert hasattr(LanguageProfile, "must_not_contain_json")
    assert hasattr(LanguageProfile, "cutoff_language")
    assert hasattr(LanguageProfile, "audio_exclude_languages_json")
