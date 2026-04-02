"""Tests for video_codec weight in defaults and codec-match scoring."""


class TestVideoCodecWeightDefault:
    def test_episode_weights_include_video_codec(self):
        from db.repositories.scoring import _DEFAULT_EPISODE_WEIGHTS
        assert "video_codec" in _DEFAULT_EPISODE_WEIGHTS
        assert _DEFAULT_EPISODE_WEIGHTS["video_codec"] == 2

    def test_movie_weights_include_video_codec(self):
        from db.repositories.scoring import _DEFAULT_MOVIE_WEIGHTS
        assert "video_codec" in _DEFAULT_MOVIE_WEIGHTS
        assert _DEFAULT_MOVIE_WEIGHTS["video_codec"] == 2

    def test_get_all_scoring_weights_includes_video_codec(self):
        from unittest.mock import MagicMock, patch

        from db.repositories.scoring import ScoringRepository

        # Mock the session and get_scoring_weights method
        with patch.object(ScoringRepository, 'get_scoring_weights', return_value={}):
            repo = ScoringRepository.__new__(ScoringRepository)
            weights = repo.get_all_scoring_weights()
        assert weights["episode"]["video_codec"] == 2
        assert weights["movie"]["video_codec"] == 2


class TestApplyVideoCodecBonus:
    def _make_result(self, release_info: str, score: int = 100) -> dict:
        return {"release_info": release_info, "score": score}

    def test_x265_match_adds_bonus(self):
        from wanted_search.scoring import apply_video_codec_bonus
        results = [self._make_result("Show.S01E01.BluRay.x265")]
        apply_video_codec_bonus(results, video_codec="x265", weight=2)
        assert results[0]["score"] == 102

    def test_x264_match_adds_bonus(self):
        from wanted_search.scoring import apply_video_codec_bonus
        results = [self._make_result("Show.S01E01.BluRay.x264")]
        apply_video_codec_bonus(results, video_codec="x264", weight=2)
        assert results[0]["score"] == 102

    def test_hevc_maps_to_x265_family(self):
        from wanted_search.scoring import apply_video_codec_bonus
        results = [self._make_result("Show.S01E01.BluRay.HEVC")]
        apply_video_codec_bonus(results, video_codec="hevc", weight=2)
        assert results[0]["score"] == 102

    def test_no_match_no_change(self):
        from wanted_search.scoring import apply_video_codec_bonus
        results = [self._make_result("Show.S01E01.BluRay.x264")]
        apply_video_codec_bonus(results, video_codec="x265", weight=2)
        assert results[0]["score"] == 100

    def test_empty_codec_no_change(self):
        from wanted_search.scoring import apply_video_codec_bonus
        results = [self._make_result("Show.S01E01.BluRay.x265")]
        apply_video_codec_bonus(results, video_codec="", weight=2)
        assert results[0]["score"] == 100

    def test_empty_results_no_error(self):
        from wanted_search.scoring import apply_video_codec_bonus
        apply_video_codec_bonus([], video_codec="x265", weight=2)  # must not raise

    def test_av1_match(self):
        from wanted_search.scoring import apply_video_codec_bonus
        results = [self._make_result("Show.S01E01.BluRay.AV1")]
        apply_video_codec_bonus(results, video_codec="av1", weight=2)
        assert results[0]["score"] == 102
