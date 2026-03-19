"""Unit tests for new subtitle providers (batch 2)."""

from unittest.mock import MagicMock, patch


class TestSubsourceProvider:
    def test_import_and_name(self):
        from providers.subsource import SubsourceProvider
        p = SubsourceProvider()
        assert p.name == "subsource"

    def test_languages_multilingual(self):
        from providers.subsource import SubsourceProvider
        p = SubsourceProvider()
        assert "en" in p.languages
        assert "de" in p.languages
        assert "fr" in p.languages
        assert "zh" in p.languages
        assert len(p.languages) >= 20

    def test_no_credentials_required(self):
        from providers.subsource import SubsourceProvider
        p = SubsourceProvider()
        assert p.config_fields == []

    def test_health_check_not_initialized(self):
        from providers.subsource import SubsourceProvider
        p = SubsourceProvider()
        healthy, msg = p.health_check()
        assert not healthy

    def test_initialize_creates_session(self):
        from providers.subsource import SubsourceProvider
        p = SubsourceProvider()
        with patch("providers.subsource.create_session") as mock_cs:
            mock_cs.return_value = MagicMock()
            p.initialize()
            assert p.session is not None

    def test_terminate_closes_session(self):
        from providers.subsource import SubsourceProvider
        p = SubsourceProvider()
        p.session = MagicMock()
        p.terminate()
        assert p.session is None

    def test_search_returns_empty_without_session(self):
        from providers.base import VideoQuery
        from providers.subsource import SubsourceProvider
        p = SubsourceProvider()
        q = VideoQuery(title="Test", languages=["en"])
        assert p.search(q) == []

    def test_search_returns_empty_for_unknown_language(self):
        from providers.base import VideoQuery
        from providers.subsource import SubsourceProvider
        p = SubsourceProvider()
        p.session = MagicMock()
        q = VideoQuery(title="Test", languages=["xx-unknown"])
        assert p.search(q) == []

    def test_search_movie_builds_correct_request(self):
        from providers.base import VideoQuery
        from providers.subsource import SubsourceProvider
        p = SubsourceProvider()
        mock_session = MagicMock()
        mock_session.post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"subs": [{"linkName": "sub1", "releaseName": "Movie.2023.BluRay", "lang": "english"}]},
        )
        p.session = mock_session
        q = VideoQuery(title="Some Movie", year=2023, languages=["en"])
        results = p.search(q)
        assert isinstance(results, list)
        mock_session.post.assert_called_once()

    def test_download_raises_without_session(self):
        import pytest
        from providers.base import SubtitleResult, SubtitleFormat
        from providers.subsource import SubsourceProvider
        p = SubsourceProvider()
        r = SubtitleResult(
            provider_name="subsource", subtitle_id="x",
            language="en", format=SubtitleFormat.SRT,
            filename="x.srt", download_url="https://subsource.net/x",
        )
        with pytest.raises(RuntimeError):
            p.download(r)
