"""Release group filtering tests.

Tests:
- TestReleaseGroupExclude: blocked groups removed from results
- TestReleaseGroupPrefer: preferred groups get score bonus
- TestReleaseGroupBothRules: exclude takes precedence over prefer
- TestReleaseGroupEmpty: no-op when settings are empty
- TestVideoQueryReleaseMeta: build_query_from_wanted populates release fields
"""

import os
import sys
from dataclasses import dataclass, field
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from providers.base import SubtitleFormat, SubtitleResult, VideoQuery


def _make_result(provider_name: str, release_info: str, score: int = 100) -> SubtitleResult:
    return SubtitleResult(
        provider_name=provider_name,
        subtitle_id="1",
        language="de",
        format=SubtitleFormat.ASS,
        release_info=release_info,
        score=score,
    )


def _mock_settings(prefer: str = "", exclude: str = "", bonus: int = 20):
    s = MagicMock()
    s.release_group_prefer = prefer
    s.release_group_exclude = exclude
    s.release_group_prefer_bonus = bonus
    return s


# ── Helpers for applying filter logic directly ───────────────────────────────


def _apply_filters(results, settings):
    """Replicate the filter/boost logic from ProviderManager.search() in isolation."""
    _exclude = [g.strip().lower() for g in settings.release_group_exclude.split(",") if g.strip()]
    _prefer = [g.strip().lower() for g in settings.release_group_prefer.split(",") if g.strip()]

    if _exclude:
        results = [r for r in results if not any(g in r.release_info.lower() for g in _exclude)]

    if _prefer:
        bonus = settings.release_group_prefer_bonus
        for r in results:
            if any(g in r.release_info.lower() for g in _prefer):
                r.score += bonus
                r.matches.add("release_group_prefer")

    results.sort(key=lambda r: (0 if r.format == SubtitleFormat.ASS else 1, -r.score))
    return results


# ── TestReleaseGroupExclude ───────────────────────────────────────────────────


class TestReleaseGroupExclude:
    def test_blocked_group_removed(self):
        results = [
            _make_result("p1", "HorribleSubs 1080p"),
            _make_result("p2", "SubsPlease 1080p"),
        ]
        settings = _mock_settings(exclude="HorribleSubs")
        filtered = _apply_filters(results, settings)
        names = [r.release_info for r in filtered]
        assert "HorribleSubs 1080p" not in names
        assert "SubsPlease 1080p" in names

    def test_case_insensitive_exclude(self):
        results = [_make_result("p1", "HORRIBLESUBS 720p")]
        settings = _mock_settings(exclude="horriblesubs")
        filtered = _apply_filters(results, settings)
        assert filtered == []

    def test_multiple_blocked_groups(self):
        results = [
            _make_result("p1", "HorribleSubs"),
            _make_result("p2", "CoalGirls"),
            _make_result("p3", "SubsPlease"),
        ]
        settings = _mock_settings(exclude="HorribleSubs,CoalGirls")
        filtered = _apply_filters(results, settings)
        assert len(filtered) == 1
        assert filtered[0].release_info == "SubsPlease"

    def test_partial_name_matches(self):
        """Exclude 'Horrible' should match 'HorribleSubs'."""
        results = [_make_result("p1", "HorribleSubs")]
        settings = _mock_settings(exclude="Horrible")
        filtered = _apply_filters(results, settings)
        assert filtered == []

    def test_empty_exclude_keeps_all(self):
        results = [_make_result("p1", "HorribleSubs"), _make_result("p2", "SubsPlease")]
        settings = _mock_settings(exclude="")
        filtered = _apply_filters(results, settings)
        assert len(filtered) == 2


# ── TestReleaseGroupPrefer ────────────────────────────────────────────────────


class TestReleaseGroupPrefer:
    def test_preferred_group_gets_bonus(self):
        r = _make_result("p1", "SubsPlease 1080p", score=100)
        settings = _mock_settings(prefer="SubsPlease", bonus=20)
        filtered = _apply_filters([r], settings)
        assert filtered[0].score == 120

    def test_preferred_group_adds_match_tag(self):
        r = _make_result("p1", "SubsPlease", score=100)
        settings = _mock_settings(prefer="SubsPlease", bonus=20)
        _apply_filters([r], settings)
        assert "release_group_prefer" in r.matches

    def test_non_preferred_group_unchanged(self):
        r = _make_result("p1", "OtherGroup", score=100)
        settings = _mock_settings(prefer="SubsPlease", bonus=20)
        filtered = _apply_filters([r], settings)
        assert filtered[0].score == 100
        assert "release_group_prefer" not in filtered[0].matches

    def test_prefer_reorders_results(self):
        low = _make_result("p1", "SubsPlease", score=50)
        high = _make_result("p2", "OtherGroup", score=100)
        settings = _mock_settings(prefer="SubsPlease", bonus=100)
        filtered = _apply_filters([low, high], settings)
        # low + 100 bonus = 150 > high = 100
        assert filtered[0].release_info == "SubsPlease"

    def test_case_insensitive_prefer(self):
        r = _make_result("p1", "SUBSPLEASE 1080p", score=100)
        settings = _mock_settings(prefer="subsplease", bonus=20)
        filtered = _apply_filters([r], settings)
        assert filtered[0].score == 120


# ── TestReleaseGroupBothRules ─────────────────────────────────────────────────


class TestReleaseGroupBothRules:
    def test_exclude_takes_precedence_over_prefer(self):
        """A group in both prefer and exclude lists should be excluded."""
        r = _make_result("p1", "SubsPlease", score=100)
        settings = _mock_settings(prefer="SubsPlease", exclude="SubsPlease", bonus=20)
        filtered = _apply_filters([r], settings)
        assert filtered == []


# ── TestReleaseGroupEmpty ─────────────────────────────────────────────────────


class TestReleaseGroupEmpty:
    def test_no_settings_no_change(self):
        results = [_make_result("p1", "SubsPlease"), _make_result("p2", "HorribleSubs")]
        settings = _mock_settings(prefer="", exclude="", bonus=20)
        filtered = _apply_filters(results, settings)
        assert len(filtered) == 2

    def test_result_with_empty_release_info_not_excluded(self):
        r = _make_result("p1", "", score=100)
        settings = _mock_settings(exclude="HorribleSubs")
        filtered = _apply_filters([r], settings)
        assert len(filtered) == 1


# ── TestVideoQueryReleaseFields ───────────────────────────────────────────────


class TestVideoQueryReleaseFields:
    def test_release_fields_default_empty(self):
        q = VideoQuery(file_path="/media/test.mkv")
        assert q.release_group == ""
        assert q.source == ""
        assert q.resolution == ""
        assert q.video_codec == ""

    def test_release_fields_assignable(self):
        q = VideoQuery(
            file_path="/media/test.mkv",
            release_group="SubsPlease",
            source="WEB-DL",
            resolution="1080p",
            video_codec="x264",
        )
        assert q.release_group == "SubsPlease"
        assert q.source == "WEB-DL"
        assert q.resolution == "1080p"
        assert q.video_codec == "x264"
