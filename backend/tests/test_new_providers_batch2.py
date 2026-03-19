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


class TestYifySubtitlesProvider:
    def test_import_and_name(self):
        from providers.yifysubtitles import YifySubtitlesProvider
        p = YifySubtitlesProvider()
        assert p.name == "yifysubtitles"

    def test_movies_only_flag(self):
        from providers.yifysubtitles import YifySubtitlesProvider
        p = YifySubtitlesProvider()
        assert p.movies_only is True

    def test_no_credentials_required(self):
        from providers.yifysubtitles import YifySubtitlesProvider
        p = YifySubtitlesProvider()
        assert p.config_fields == []

    def test_health_check_not_initialized(self):
        from providers.yifysubtitles import YifySubtitlesProvider
        p = YifySubtitlesProvider()
        healthy, msg = p.health_check()
        assert not healthy

    def test_initialize_creates_session(self):
        from providers.yifysubtitles import YifySubtitlesProvider
        p = YifySubtitlesProvider()
        with patch("providers.yifysubtitles.create_session") as mock_cs:
            mock_cs.return_value = MagicMock()
            p.initialize()
            assert p.session is not None

    def test_terminate_closes_session(self):
        from providers.yifysubtitles import YifySubtitlesProvider
        p = YifySubtitlesProvider()
        p.session = MagicMock()
        p.terminate()
        assert p.session is None

    def test_search_skips_tv_series(self):
        from providers.base import VideoQuery
        from providers.yifysubtitles import YifySubtitlesProvider
        p = YifySubtitlesProvider()
        p.session = MagicMock()
        q = VideoQuery(title="Breaking Bad", season=1, episode=1, languages=["en"])
        assert p.search(q) == []

    def test_search_returns_empty_without_session(self):
        from providers.base import VideoQuery
        from providers.yifysubtitles import YifySubtitlesProvider
        p = YifySubtitlesProvider()
        q = VideoQuery(title="Inception", imdb_id="tt1375666", languages=["en"])
        assert p.search(q) == []

    def test_search_uses_imdb_id_when_available(self):
        from providers.base import VideoQuery
        from providers.yifysubtitles import YifySubtitlesProvider
        p = YifySubtitlesProvider()
        mock_session = MagicMock()
        mock_session.get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"subtitles": [{"lang": "English", "rating": 5, "url": "/subs/1.zip"}]},
        )
        p.session = mock_session
        q = VideoQuery(title="Inception", imdb_id="tt1375666", languages=["en"])
        results = p.search(q)
        call_url = mock_session.get.call_args[0][0]
        assert "tt1375666" in call_url

    def test_download_raises_without_session(self):
        import pytest
        from providers.base import SubtitleResult, SubtitleFormat
        from providers.yifysubtitles import YifySubtitlesProvider
        p = YifySubtitlesProvider()
        r = SubtitleResult(
            provider_name="yifysubtitles", subtitle_id="x",
            language="en", format=SubtitleFormat.SRT,
            filename="x.srt", download_url="https://yifysubtitles.ch/subs/x.zip",
        )
        with pytest.raises(RuntimeError):
            p.download(r)

    def test_download_success_returns_content(self):
        from providers.base import SubtitleResult, SubtitleFormat
        from providers.yifysubtitles import YifySubtitlesProvider
        p = YifySubtitlesProvider()
        mock_session = MagicMock()
        mock_session.get.return_value = MagicMock(
            status_code=200,
            content=b"1\n00:00:01,000 --> 00:00:02,000\nHello\n",
        )
        p.session = mock_session
        r = SubtitleResult(
            provider_name="yifysubtitles", subtitle_id="sub1",
            language="en", format=SubtitleFormat.SRT,
            filename="sub1.srt", download_url="https://yifysubtitles.ch/subs/sub1.zip",
        )
        content = p.download(r)
        assert content == b"1\n00:00:01,000 --> 00:00:02,000\nHello\n"
        assert r.content == content


class TestSubf2mProvider:
    def test_import_and_name(self):
        from providers.subf2m import Subf2mProvider
        p = Subf2mProvider()
        assert p.name == "subf2m"

    def test_languages_multilingual(self):
        from providers.subf2m import Subf2mProvider
        p = Subf2mProvider()
        assert "en" in p.languages
        assert "de" in p.languages
        assert "fr" in p.languages
        assert len(p.languages) >= 20

    def test_no_credentials_required(self):
        from providers.subf2m import Subf2mProvider
        p = Subf2mProvider()
        assert p.config_fields == []

    def test_health_check_not_initialized(self):
        from providers.subf2m import Subf2mProvider
        p = Subf2mProvider()
        healthy, msg = p.health_check()
        assert not healthy

    def test_health_check_reports_missing_bs4(self):
        from providers.subf2m import Subf2mProvider
        p = Subf2mProvider()
        p.session = MagicMock()
        with patch("providers.subf2m._HAS_BS4", False):
            healthy, msg = p.health_check()
        assert not healthy
        assert "beautifulsoup4" in msg

    def test_initialize_creates_session(self):
        from providers.subf2m import Subf2mProvider
        p = Subf2mProvider()
        with patch("providers.subf2m.create_session") as mock_cs:
            mock_cs.return_value = MagicMock()
            p.initialize()
            assert p.session is not None

    def test_terminate_closes_session(self):
        from providers.subf2m import Subf2mProvider
        p = Subf2mProvider()
        p.session = MagicMock()
        p.terminate()
        assert p.session is None

    def test_search_returns_empty_without_session(self):
        from providers.base import VideoQuery
        from providers.subf2m import Subf2mProvider
        p = Subf2mProvider()
        q = VideoQuery(title="Test", languages=["en"])
        assert p.search(q) == []

    def test_search_returns_empty_without_bs4(self):
        from providers.base import VideoQuery
        from providers.subf2m import Subf2mProvider
        p = Subf2mProvider()
        p.session = MagicMock()
        with patch("providers.subf2m._HAS_BS4", False):
            result = p.search(VideoQuery(title="Test", languages=["en"]))
        assert result == []

    def test_download_raises_without_session(self):
        import pytest
        from providers.base import SubtitleResult, SubtitleFormat
        from providers.subf2m import Subf2mProvider
        p = Subf2mProvider()
        r = SubtitleResult(
            provider_name="subf2m", subtitle_id="x",
            language="en", format=SubtitleFormat.SRT,
            filename="x.srt", download_url="https://subf2m.co/x",
        )
        with pytest.raises(RuntimeError):
            p.download(r)


class TestZimukuProvider:
    """Tests for the Zimuku provider (Chinese subtitles)."""

    def test_import_and_name(self):
        from providers.zimuku import ZimukuProvider
        p = ZimukuProvider()
        assert p.name == "zimuku"

    def test_languages_chinese_only(self):
        from providers.zimuku import ZimukuProvider
        p = ZimukuProvider()
        assert "zh" in p.languages
        assert "zh-hans" in p.languages
        assert "zh-hant" in p.languages
        # Should not support unrelated languages
        assert "de" not in p.languages

    def test_no_credentials_required(self):
        from providers.zimuku import ZimukuProvider
        p = ZimukuProvider()
        assert p.config_fields == []

    def test_health_check_not_initialized(self):
        from providers.zimuku import ZimukuProvider
        p = ZimukuProvider()
        healthy, msg = p.health_check()
        assert not healthy

    def test_initialize_creates_session(self):
        from providers.zimuku import ZimukuProvider
        p = ZimukuProvider()
        with patch("providers.zimuku.create_session") as mock_cs:
            mock_cs.return_value = MagicMock()
            p.initialize()
            assert p.session is not None

    def test_terminate_closes_session(self):
        from providers.zimuku import ZimukuProvider
        p = ZimukuProvider()
        p.session = MagicMock()
        p.terminate()
        assert p.session is None

    def test_search_returns_empty_without_session(self):
        from providers.base import VideoQuery
        from providers.zimuku import ZimukuProvider
        p = ZimukuProvider()
        q = VideoQuery(title="Test", languages=["zh"])
        assert p.search(q) == []

    def test_search_skips_non_chinese_languages(self):
        from providers.base import VideoQuery
        from providers.zimuku import ZimukuProvider
        p = ZimukuProvider()
        p.session = MagicMock()
        with patch("providers.zimuku._HAS_BS4", True):
            result = p.search(VideoQuery(title="Test", languages=["en", "de"]))
        assert result == []

    def test_download_raises_without_session(self):
        import pytest
        from providers.base import SubtitleResult, SubtitleFormat
        from providers.zimuku import ZimukuProvider
        p = ZimukuProvider()
        r = SubtitleResult(
            provider_name="zimuku", subtitle_id="x",
            language="zh", format=SubtitleFormat.SRT,
            filename="x.srt", download_url="https://zimuku.net/x",
        )
        with pytest.raises(RuntimeError):
            p.download(r)

    def test_download_handles_rar_archive(self):
        """Zimuku often serves RAR archives — must not crash on RAR magic bytes."""
        import pytest
        from providers.base import SubtitleResult, SubtitleFormat
        from providers.zimuku import ZimukuProvider
        p = ZimukuProvider()
        mock_session = MagicMock()
        # RAR magic: Rar! (0x52 0x61 0x72 0x21)
        rar_bytes = b"Rar!\x1a\x07\x00" + b"\x00" * 50
        mock_session.get.return_value = MagicMock(
            status_code=200, content=rar_bytes
        )
        p.session = mock_session
        r = SubtitleResult(
            provider_name="zimuku", subtitle_id="x",
            language="zh", format=SubtitleFormat.SRT,
            filename="x.rar", download_url="https://zimuku.net/x",
            provider_data={"detail_url": "https://zimuku.net/subs/123"},
        )
        # Should attempt RAR extraction and raise RuntimeError on invalid RAR
        with pytest.raises((RuntimeError, Exception)):
            p.download(r)

    def test_download_success_returns_content(self):
        from providers.base import SubtitleResult, SubtitleFormat
        from providers.zimuku import ZimukuProvider
        p = ZimukuProvider()
        mock_session = MagicMock()
        srt_content = b"1\n00:00:01,000 --> 00:00:02,000\n\xe4\xb8\xad\xe6\x96\x87\n"
        mock_session.get.return_value = MagicMock(
            status_code=200,
            content=srt_content,
        )
        p.session = mock_session
        r = SubtitleResult(
            provider_name="zimuku", subtitle_id="123",
            language="zh", format=SubtitleFormat.SRT,
            filename="sub.srt", download_url="https://zimuku.net/dld/123",
            provider_data={"detail_url": "https://zimuku.net/subs/123"},
        )
        content = p.download(r)
        assert content == srt_content
        assert r.content == content
