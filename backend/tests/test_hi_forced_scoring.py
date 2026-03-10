"""Tests for HI and Forced subtitle preference scoring modifiers."""

import os
from unittest.mock import patch

import pytest


def _make_result(hearing_impaired=False, forced=False, provider="opensubtitles"):
    from providers.base import SubtitleFormat, SubtitleResult

    return SubtitleResult(
        provider_name=provider,
        subtitle_id="test-1",
        language="de",
        format=SubtitleFormat.SRT,
        hearing_impaired=hearing_impaired,
        forced=forced,
        matches={"series", "season", "episode"},
    )


def _make_query(is_episode=True):
    from providers.base import VideoQuery

    return VideoQuery(
        series_title="Test Show",
        season=1,
        episode=1,
        languages=["de"],
    )


@pytest.fixture(autouse=True)
def reset_settings(monkeypatch):
    """Ensure clean settings state for each test."""
    monkeypatch.setenv("SUBLARR_MEDIA_PATH", "/tmp/test_media")
    from config import reload_settings

    reload_settings()
    yield
    reload_settings()


class TestHIPreferenceScoring:
    def _score(self, hi_preference, hearing_impaired):
        from config import reload_settings
        from providers.base import compute_score, invalidate_scoring_cache

        invalidate_scoring_cache()
        reload_settings({"hi_preference": hi_preference})
        result = _make_result(hearing_impaired=hearing_impaired)
        query = _make_query()
        return compute_score(result, query)

    def test_include_hi_no_change(self):
        """include: HI subtitle gets no bonus or penalty."""
        score_hi = self._score("include", hearing_impaired=True)
        score_non_hi = self._score("include", hearing_impaired=False)
        assert score_hi == score_non_hi

    def test_prefer_hi_gets_bonus(self):
        """prefer: HI subtitle scores +30 over non-HI."""
        score_hi = self._score("prefer", hearing_impaired=True)
        score_non_hi = self._score("prefer", hearing_impaired=False)
        assert score_hi == score_non_hi + 30

    def test_prefer_non_hi_no_bonus(self):
        """prefer: non-HI subtitle gets no bonus."""
        score_include = self._score("include", hearing_impaired=False)
        score_prefer = self._score("prefer", hearing_impaired=False)
        assert score_prefer == score_include

    def test_exclude_hi_gets_penalty(self):
        """exclude: HI subtitle is heavily penalized."""
        score_hi = self._score("exclude", hearing_impaired=True)
        score_non_hi = self._score("exclude", hearing_impaired=False)
        assert score_hi == score_non_hi - 999

    def test_exclude_non_hi_no_penalty(self):
        """exclude: non-HI subtitle is not penalized."""
        score_include = self._score("include", hearing_impaired=False)
        score_exclude = self._score("exclude", hearing_impaired=False)
        assert score_exclude == score_include

    def test_only_non_hi_gets_penalty(self):
        """only: non-HI subtitle is heavily penalized."""
        score_non_hi = self._score("only", hearing_impaired=False)
        score_hi = self._score("only", hearing_impaired=True)
        assert score_non_hi == score_hi - 999

    def test_only_hi_no_penalty(self):
        """only: HI subtitle is not penalized."""
        score_include = self._score("include", hearing_impaired=True)
        score_only = self._score("only", hearing_impaired=True)
        assert score_only == score_include

    def test_unknown_preference_treated_as_include(self):
        """Unknown preference value falls back to include (no modifier)."""
        score_unknown = self._score("bogus", hearing_impaired=True)
        score_include = self._score("include", hearing_impaired=True)
        assert score_unknown == score_include


class TestForcedPreferenceScoring:
    def _score(self, forced_preference, forced):
        from config import reload_settings
        from providers.base import compute_score, invalidate_scoring_cache

        invalidate_scoring_cache()
        reload_settings({"forced_preference": forced_preference})
        result = _make_result(forced=forced)
        query = _make_query()
        return compute_score(result, query)

    def test_include_forced_no_change(self):
        score_forced = self._score("include", forced=True)
        score_normal = self._score("include", forced=False)
        assert score_forced == score_normal

    def test_prefer_forced_gets_bonus(self):
        score_forced = self._score("prefer", forced=True)
        score_normal = self._score("prefer", forced=False)
        assert score_forced == score_normal + 30

    def test_exclude_forced_gets_penalty(self):
        score_forced = self._score("exclude", forced=True)
        score_normal = self._score("exclude", forced=False)
        assert score_forced == score_normal - 999

    def test_only_non_forced_gets_penalty(self):
        score_normal = self._score("only", forced=False)
        score_forced = self._score("only", forced=True)
        assert score_normal == score_forced - 999

    def test_only_forced_no_penalty(self):
        score_include = self._score("include", forced=True)
        score_only = self._score("only", forced=True)
        assert score_only == score_include


class TestHIAndForcedCombined:
    def test_both_prefer_additive(self):
        """When both HI and forced are preferred and result matches both, bonuses stack."""
        from config import reload_settings
        from providers.base import compute_score, invalidate_scoring_cache

        invalidate_scoring_cache()
        reload_settings({"hi_preference": "prefer", "forced_preference": "prefer"})
        result_both = _make_result(hearing_impaired=True, forced=True)
        result_neither = _make_result(hearing_impaired=False, forced=False)
        query = _make_query()
        assert compute_score(result_both, query) == compute_score(result_neither, query) + 60

    def test_exclude_hi_independent_of_forced(self):
        """Excluding HI does not affect forced subtitle scoring."""
        from config import reload_settings
        from providers.base import compute_score, invalidate_scoring_cache

        invalidate_scoring_cache()
        reload_settings({"hi_preference": "exclude", "forced_preference": "include"})
        result_forced_only = _make_result(hearing_impaired=False, forced=True)
        result_neither = _make_result(hearing_impaired=False, forced=False)
        query = _make_query()
        assert compute_score(result_forced_only, query) == compute_score(result_neither, query)
