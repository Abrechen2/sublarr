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
            json=lambda: {
                "subs": [
                    {"linkName": "sub1", "releaseName": "Movie.2023.BluRay", "lang": "english"}
                ]
            },
        )
        p.session = mock_session
        q = VideoQuery(title="Some Movie", year=2023, languages=["en"])
        results = p.search(q)
        assert isinstance(results, list)
        mock_session.post.assert_called_once()

    def test_download_raises_without_session(self):
        import pytest

        from providers.base import SubtitleFormat, SubtitleResult
        from providers.subsource import SubsourceProvider

        p = SubsourceProvider()
        r = SubtitleResult(
            provider_name="subsource",
            subtitle_id="x",
            language="en",
            format=SubtitleFormat.SRT,
            filename="x.srt",
            download_url="https://subsource.net/x",
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
        p.search(q)
        call_url = mock_session.get.call_args[0][0]
        assert "tt1375666" in call_url

    def test_download_raises_without_session(self):
        import pytest

        from providers.base import SubtitleFormat, SubtitleResult
        from providers.yifysubtitles import YifySubtitlesProvider

        p = YifySubtitlesProvider()
        r = SubtitleResult(
            provider_name="yifysubtitles",
            subtitle_id="x",
            language="en",
            format=SubtitleFormat.SRT,
            filename="x.srt",
            download_url="https://yifysubtitles.ch/subs/x.zip",
        )
        with pytest.raises(RuntimeError):
            p.download(r)

    def test_download_success_returns_content(self):
        from providers.base import SubtitleFormat, SubtitleResult
        from providers.yifysubtitles import YifySubtitlesProvider

        p = YifySubtitlesProvider()
        mock_session = MagicMock()
        mock_session.get.return_value = MagicMock(
            status_code=200,
            content=b"1\n00:00:01,000 --> 00:00:02,000\nHello\n",
        )
        p.session = mock_session
        r = SubtitleResult(
            provider_name="yifysubtitles",
            subtitle_id="sub1",
            language="en",
            format=SubtitleFormat.SRT,
            filename="sub1.srt",
            download_url="https://yifysubtitles.ch/subs/sub1.zip",
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

        from providers.base import SubtitleFormat, SubtitleResult
        from providers.subf2m import Subf2mProvider

        p = Subf2mProvider()
        r = SubtitleResult(
            provider_name="subf2m",
            subtitle_id="x",
            language="en",
            format=SubtitleFormat.SRT,
            filename="x.srt",
            download_url="https://subf2m.co/x",
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

        from providers.base import SubtitleFormat, SubtitleResult
        from providers.zimuku import ZimukuProvider

        p = ZimukuProvider()
        r = SubtitleResult(
            provider_name="zimuku",
            subtitle_id="x",
            language="zh",
            format=SubtitleFormat.SRT,
            filename="x.srt",
            download_url="https://zimuku.net/x",
        )
        with pytest.raises(RuntimeError):
            p.download(r)

    def test_download_handles_rar_archive(self):
        """Zimuku often serves RAR archives — must not crash on RAR magic bytes."""
        import pytest

        from providers.base import SubtitleFormat, SubtitleResult
        from providers.zimuku import ZimukuProvider

        p = ZimukuProvider()
        mock_session = MagicMock()
        # RAR magic: Rar! (0x52 0x61 0x72 0x21)
        rar_bytes = b"Rar!\x1a\x07\x00" + b"\x00" * 50
        mock_session.get.return_value = MagicMock(status_code=200, content=rar_bytes)
        p.session = mock_session
        r = SubtitleResult(
            provider_name="zimuku",
            subtitle_id="x",
            language="zh",
            format=SubtitleFormat.SRT,
            filename="x.rar",
            download_url="https://zimuku.net/x",
            provider_data={"detail_url": "https://zimuku.net/subs/123"},
        )
        # Should attempt RAR extraction and raise RuntimeError on invalid RAR
        with pytest.raises((RuntimeError, Exception)):
            p.download(r)

    def test_download_success_returns_content(self):
        from providers.base import SubtitleFormat, SubtitleResult
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
            provider_name="zimuku",
            subtitle_id="123",
            language="zh",
            format=SubtitleFormat.SRT,
            filename="sub.srt",
            download_url="https://zimuku.net/dld/123",
            provider_data={"detail_url": "https://zimuku.net/subs/123"},
        )
        content = p.download(r)
        assert content == srt_content
        assert r.content == content


class TestBetaSeriesProvider:
    """Tests for the BetaSeries provider."""

    def test_import_and_name(self):
        from providers.betaseries import BetaSeriesProvider

        p = BetaSeriesProvider()
        assert p.name == "betaseries"

    def test_has_api_key_config_field(self):
        from providers.betaseries import BetaSeriesProvider

        p = BetaSeriesProvider()
        field_keys = [f["key"] for f in p.config_fields]
        assert "betaseries_api_key" in field_keys

    def test_languages_includes_french(self):
        from providers.betaseries import BetaSeriesProvider

        p = BetaSeriesProvider()
        assert "fr" in p.languages
        assert "en" in p.languages

    def test_health_check_not_initialized(self):
        from providers.betaseries import BetaSeriesProvider

        p = BetaSeriesProvider()
        healthy, msg = p.health_check()
        assert not healthy

    def test_health_check_no_api_key(self):
        from providers.betaseries import BetaSeriesProvider

        p = BetaSeriesProvider()
        p.session = MagicMock()
        p.api_key = ""
        healthy, msg = p.health_check()
        assert not healthy
        assert "API key" in msg

    def test_initialize_creates_session(self):
        from providers.betaseries import BetaSeriesProvider

        p = BetaSeriesProvider(api_key="test-key")
        with patch("providers.betaseries.create_session") as mock_cs:
            mock_cs.return_value = MagicMock()
            p.initialize()
            assert p.session is not None

    def test_terminate_closes_session(self):
        from providers.betaseries import BetaSeriesProvider

        p = BetaSeriesProvider()
        p.session = MagicMock()
        p.terminate()
        assert p.session is None

    def test_search_returns_empty_without_session(self):
        from providers.base import VideoQuery
        from providers.betaseries import BetaSeriesProvider

        p = BetaSeriesProvider()
        q = VideoQuery(title="Test", languages=["fr"])
        assert p.search(q) == []

    def test_search_returns_empty_without_api_key(self):
        from providers.base import VideoQuery
        from providers.betaseries import BetaSeriesProvider

        p = BetaSeriesProvider(api_key="")
        p.session = MagicMock()
        q = VideoQuery(title="Lupin", season=1, episode=1, languages=["fr"])
        assert p.search(q) == []

    def test_download_raises_without_session(self):
        import pytest

        from providers.base import SubtitleFormat, SubtitleResult
        from providers.betaseries import BetaSeriesProvider

        p = BetaSeriesProvider()
        r = SubtitleResult(
            provider_name="betaseries",
            subtitle_id="12345",
            language="fr",
            format=SubtitleFormat.SRT,
            filename="x.srt",
            download_url="https://api.betaseries.com/x",
        )
        with pytest.raises(RuntimeError):
            p.download(r)

    def test_download_success_returns_content(self):
        from providers.base import SubtitleFormat, SubtitleResult
        from providers.betaseries import BetaSeriesProvider

        p = BetaSeriesProvider(api_key="test-key")
        mock_session = MagicMock()
        srt_bytes = b"1\n00:00:01,000 --> 00:00:02,000\nBonjour\n"
        mock_session.get.return_value = MagicMock(
            status_code=200,
            content=srt_bytes,
        )
        p.session = mock_session
        r = SubtitleResult(
            provider_name="betaseries",
            subtitle_id="12345",
            language="fr",
            format=SubtitleFormat.SRT,
            filename="12345.srt",
            download_url="https://api.betaseries.com/subs/12345.srt",
        )
        content = p.download(r)
        assert content == srt_bytes
        assert r.content == content


class TestTitloviProvider:
    """Tests for the Titlovi provider (Balkan subtitles)."""

    def test_import_and_name(self):
        from providers.titlovi import TitloviProvider

        p = TitloviProvider()
        assert p.name == "titlovi"

    def test_languages_balkan(self):
        from providers.titlovi import TitloviProvider

        p = TitloviProvider()
        assert "hr" in p.languages  # Croatian
        assert "sr" in p.languages  # Serbian
        assert "bs" in p.languages  # Bosnian
        assert "sl" in p.languages  # Slovenian
        assert "mk" in p.languages  # Macedonian
        assert "zh" not in p.languages

    def test_no_credentials_required(self):
        from providers.titlovi import TitloviProvider

        p = TitloviProvider()
        assert p.config_fields == []

    def test_health_check_not_initialized(self):
        from providers.titlovi import TitloviProvider

        p = TitloviProvider()
        healthy, msg = p.health_check()
        assert not healthy

    def test_initialize_creates_session(self):
        from providers.titlovi import TitloviProvider

        p = TitloviProvider()
        with patch("providers.titlovi.create_session") as mock_cs:
            mock_cs.return_value = MagicMock()
            p.initialize()
            assert p.session is not None

    def test_terminate_closes_session(self):
        from providers.titlovi import TitloviProvider

        p = TitloviProvider()
        p.session = MagicMock()
        p.terminate()
        assert p.session is None

    def test_search_returns_empty_without_session(self):
        from providers.base import VideoQuery
        from providers.titlovi import TitloviProvider

        p = TitloviProvider()
        q = VideoQuery(title="Test", languages=["hr"])
        assert p.search(q) == []

    def test_search_skips_non_balkan_languages(self):
        from providers.base import VideoQuery
        from providers.titlovi import TitloviProvider

        p = TitloviProvider()
        p.session = MagicMock()
        result = p.search(VideoQuery(title="Test", languages=["en", "de", "fr"]))
        assert result == []

    def test_search_builds_correct_params(self):
        from providers.base import VideoQuery
        from providers.titlovi import TitloviProvider

        p = TitloviProvider()
        mock_session = MagicMock()
        mock_session.get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"subtitles": []},
        )
        p.session = mock_session
        q = VideoQuery(title="Squid Game", season=1, episode=1, languages=["hr"])
        p.search(q)
        mock_session.get.assert_called_once()
        call_kwargs = mock_session.get.call_args
        params = call_kwargs.kwargs.get("params") or {}
        assert params.get("title") == "Squid Game"

    def test_download_raises_without_session(self):
        import pytest

        from providers.base import SubtitleFormat, SubtitleResult
        from providers.titlovi import TitloviProvider

        p = TitloviProvider()
        r = SubtitleResult(
            provider_name="titlovi",
            subtitle_id="12345",
            language="hr",
            format=SubtitleFormat.SRT,
            filename="x.srt",
            download_url="https://titlovi.com/download/12345",
        )
        with pytest.raises(RuntimeError):
            p.download(r)

    def test_download_success_returns_content(self):
        from providers.base import SubtitleFormat, SubtitleResult
        from providers.titlovi import TitloviProvider

        p = TitloviProvider()
        mock_session = MagicMock()
        srt_bytes = b"1\n00:00:01,000 --> 00:00:02,000\nHvala\n"
        mock_session.get.return_value = MagicMock(
            status_code=200,
            content=srt_bytes,
        )
        p.session = mock_session
        r = SubtitleResult(
            provider_name="titlovi",
            subtitle_id="12345",
            language="hr",
            format=SubtitleFormat.SRT,
            filename="sub.srt",
            download_url="https://titlovi.com/download/12345",
        )
        content = p.download(r)
        assert content == srt_bytes
        assert r.content == content


class TestEmbeddedSubtitlesProvider:
    """Tests for the EmbeddedSubtitles provider (pipeline integration)."""

    def test_import_and_name(self):
        from providers.embedded import EmbeddedSubtitlesProvider

        p = EmbeddedSubtitlesProvider()
        assert p.name == "embedded"

    def test_no_credentials_required(self):
        from providers.embedded import EmbeddedSubtitlesProvider

        p = EmbeddedSubtitlesProvider()
        assert p.config_fields == []

    def test_no_session_attribute(self):
        """Must not have session attr — avoids ProviderManager's session=None guard."""
        from providers.embedded import EmbeddedSubtitlesProvider

        p = EmbeddedSubtitlesProvider()
        assert not hasattr(p, "session")

    def test_health_check_returns_true_when_initialized(self):
        from providers.embedded import EmbeddedSubtitlesProvider

        p = EmbeddedSubtitlesProvider()
        p.initialize()
        healthy, msg = p.health_check()
        assert healthy

    def test_initialize_and_terminate_no_crash(self):
        from providers.embedded import EmbeddedSubtitlesProvider

        p = EmbeddedSubtitlesProvider()
        p.initialize()
        p.terminate()  # must not raise

    def test_search_returns_empty_when_no_file_path(self):
        from providers.base import VideoQuery
        from providers.embedded import EmbeddedSubtitlesProvider

        p = EmbeddedSubtitlesProvider()
        p.initialize()
        q = VideoQuery(title="Test", languages=["de"])  # file_path=""
        result = p.search(q)
        assert result == []

    def test_search_returns_empty_when_file_not_on_disk(self):
        from providers.base import VideoQuery
        from providers.embedded import EmbeddedSubtitlesProvider

        p = EmbeddedSubtitlesProvider()
        p.initialize()
        q = VideoQuery(
            file_path="/nonexistent/path/video.mkv",
            title="Test",
            languages=["de"],
        )
        result = p.search(q)
        assert result == []

    def test_search_calls_ffprobe_with_file_path(self):
        from unittest.mock import patch

        from providers.base import VideoQuery
        from providers.embedded import EmbeddedSubtitlesProvider

        p = EmbeddedSubtitlesProvider()
        p.initialize()
        streams = {
            "streams": [
                {
                    "index": 2,
                    "codec_type": "subtitle",
                    "codec_name": "ass",
                    "tags": {"language": "ger"},
                    "disposition": {"forced": 0, "default": 0},
                }
            ]
        }
        with (
            patch("providers.embedded.get_media_streams", return_value=streams),
            patch("os.path.exists", return_value=True),
        ):
            q = VideoQuery(
                file_path="/data/video.mkv",
                title="Test",
                languages=["de"],
            )
            results = p.search(q)
        assert len(results) == 1
        assert results[0].language == "de"
        assert results[0].provider_name == "embedded"

    def test_search_filters_to_requested_languages(self):
        from unittest.mock import patch

        from providers.base import VideoQuery
        from providers.embedded import EmbeddedSubtitlesProvider

        p = EmbeddedSubtitlesProvider()
        p.initialize()
        streams = {
            "streams": [
                {
                    "index": 2,
                    "codec_type": "subtitle",
                    "codec_name": "ass",
                    "tags": {"language": "ger"},
                    "disposition": {"forced": 0, "default": 0},
                },
                {
                    "index": 3,
                    "codec_type": "subtitle",
                    "codec_name": "srt",
                    "tags": {"language": "eng"},
                    "disposition": {"forced": 0, "default": 0},
                },
            ]
        }
        with (
            patch("providers.embedded.get_media_streams", return_value=streams),
            patch("os.path.exists", return_value=True),
        ):
            # Only request German
            q = VideoQuery(file_path="/data/video.mkv", title="Test", languages=["de"])
            results = p.search(q)
        assert len(results) == 1
        assert results[0].language == "de"

    def test_search_result_carries_stream_index_in_provider_data(self):
        from unittest.mock import patch

        from providers.base import VideoQuery
        from providers.embedded import EmbeddedSubtitlesProvider

        p = EmbeddedSubtitlesProvider()
        p.initialize()
        streams = {
            "streams": [
                {
                    "index": 5,
                    "codec_type": "subtitle",
                    "codec_name": "ass",
                    "tags": {"language": "ger"},
                    "disposition": {"forced": 0, "default": 0},
                }
            ]
        }
        with (
            patch("providers.embedded.get_media_streams", return_value=streams),
            patch("os.path.exists", return_value=True),
        ):
            q = VideoQuery(file_path="/data/video.mkv", title="Test", languages=["de"])
            results = p.search(q)
        assert results[0].provider_data["stream_index"] == 5
        assert results[0].provider_data["file_path"] == "/data/video.mkv"

    def test_download_raises_when_ffmpeg_fails(self):
        from unittest.mock import patch

        import pytest

        from providers.base import SubtitleFormat, SubtitleResult
        from providers.embedded import EmbeddedSubtitlesProvider

        p = EmbeddedSubtitlesProvider()
        p.initialize()
        r = SubtitleResult(
            provider_name="embedded",
            subtitle_id="track_5",
            language="de",
            format=SubtitleFormat.ASS,
            filename="track_5.ass",
            download_url="",
            provider_data={
                "file_path": "/data/video.mkv",
                "stream_index": 5,
                "sub_index": 0,
                "codec": "ass",
            },
        )
        with (
            patch(
                "providers.embedded.extract_subtitle_stream",
                side_effect=RuntimeError("ffmpeg failed"),
            ),
            pytest.raises(RuntimeError, match="ffmpeg failed"),
        ):
            p.download(r)
