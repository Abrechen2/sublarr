"""Tests for score_breakdown in compute_score."""

from unittest.mock import patch


class TestScoreBreakdown:
    def test_breakdown_populated_on_episode_match(self):
        from providers.base import SubtitleFormat, SubtitleResult, VideoQuery, compute_score

        result = SubtitleResult(
            provider_name="test",
            subtitle_id="1",
            language="de",
            format=SubtitleFormat.ASS,
            matches={"series", "season", "episode"},
        )
        query = VideoQuery(series_title="Test Show", season=1, episode=5, languages=["de"])
        with (
            patch(
                "providers.base._get_cached_weights",
                return_value={
                    "series": 180,
                    "season": 30,
                    "episode": 30,
                    "format_bonus": 50,
                },
            ),
            patch("providers.base._get_cached_modifier", return_value=0),
        ):
            compute_score(result, query)

        assert "series" in result.score_breakdown
        assert result.score_breakdown["series"] == 180
        assert result.score_breakdown["episode"] == 30

    def test_format_bonus_in_breakdown(self):
        from providers.base import SubtitleFormat, SubtitleResult, VideoQuery, compute_score

        result = SubtitleResult(
            provider_name="test",
            subtitle_id="1",
            language="de",
            format=SubtitleFormat.ASS,
            matches=set(),
        )
        query = VideoQuery(title="Movie", languages=["de"])
        with (
            patch("providers.base._get_cached_weights", return_value={"format_bonus": 50}),
            patch("providers.base._get_cached_modifier", return_value=0),
        ):
            compute_score(result, query)

        assert result.score_breakdown.get("format_bonus") == 50

    def test_provider_modifier_in_breakdown(self):
        from providers.base import SubtitleFormat, SubtitleResult, VideoQuery, compute_score

        result = SubtitleResult(
            provider_name="test",
            subtitle_id="1",
            language="de",
            format=SubtitleFormat.SRT,
            matches=set(),
        )
        query = VideoQuery(title="Movie", languages=["de"])
        with (
            patch("providers.base._get_cached_weights", return_value={}),
            patch("providers.base._get_cached_modifier", return_value=15),
        ):
            compute_score(result, query)

        assert result.score_breakdown.get("provider_modifier") == 15

    def test_breakdown_empty_initially(self):
        from providers.base import SubtitleFormat, SubtitleResult

        result = SubtitleResult(
            provider_name="test",
            subtitle_id="1",
            language="de",
            format=SubtitleFormat.SRT,
        )
        assert result.score_breakdown == {}

    def test_total_equals_sum_of_breakdown(self):
        from providers.base import SubtitleFormat, SubtitleResult, VideoQuery, compute_score

        result = SubtitleResult(
            provider_name="test",
            subtitle_id="1",
            language="de",
            format=SubtitleFormat.ASS,
            matches={"series", "season"},
        )
        query = VideoQuery(series_title="Show", season=1, episode=1, languages=["de"])
        with (
            patch(
                "providers.base._get_cached_weights",
                return_value={
                    "series": 180,
                    "season": 30,
                    "format_bonus": 50,
                },
            ),
            patch("providers.base._get_cached_modifier", return_value=0),
        ):
            total = compute_score(result, query)

        assert total == sum(result.score_breakdown.values())
