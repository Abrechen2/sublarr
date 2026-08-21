"""Unit tests for new subtitle providers (batch 2)."""

from unittest.mock import MagicMock, patch

from providers.base import ProviderError


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
        p.session = MagicMock()
        r = SubtitleResult(
            provider_name="yifysubtitles",
            subtitle_id="sub1",
            language="en",
            format=SubtitleFormat.SRT,
            filename="sub1.srt",
            download_url="https://yifysubtitles.ch/subs/sub1.zip",
        )
        # P5: fetch goes through _stream_download (50 MB cap) — mock it.
        expected = b"1\n00:00:01,000 --> 00:00:02,000\nHello\n"
        with patch("providers.yifysubtitles._stream_download", return_value=expected):
            content = p.download(r)
        assert content == expected
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
        p.session = MagicMock()
        # RAR magic: Rar! (0x52 0x61 0x72 0x21)
        rar_bytes = b"Rar!\x1a\x07\x00" + b"\x00" * 50
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
        with (
            patch("providers.zimuku._stream_download", return_value=rar_bytes),
            pytest.raises((RuntimeError, Exception)),
        ):
            p.download(r)

    def test_download_success_returns_content(self):
        from providers.base import SubtitleFormat, SubtitleResult
        from providers.zimuku import ZimukuProvider

        p = ZimukuProvider()
        p.session = MagicMock()
        srt_content = b"1\n00:00:01,000 --> 00:00:02,000\n\xe4\xb8\xad\xe6\x96\x87\n"
        r = SubtitleResult(
            provider_name="zimuku",
            subtitle_id="123",
            language="zh",
            format=SubtitleFormat.SRT,
            filename="sub.srt",
            download_url="https://zimuku.net/dld/123",
            provider_data={"detail_url": "https://zimuku.net/subs/123"},
        )
        with patch("providers.zimuku._stream_download", return_value=srt_content):
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
        with pytest.raises(ProviderError):
            p.download(r)

    def test_download_success_returns_content(self):
        from providers.base import SubtitleFormat, SubtitleResult
        from providers.betaseries import BetaSeriesProvider

        p = BetaSeriesProvider(api_key="test-key")
        srt_bytes = b"1\n00:00:01,000 --> 00:00:02,000\nBonjour\n"
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.iter_content.return_value = [srt_bytes]
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.raise_for_status = MagicMock()
        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
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
    """Tests for the Titlovi provider (Balkan subtitles, account required — #191)."""

    def _provider(self, **kwargs):
        from providers.titlovi import TitloviProvider

        kwargs.setdefault("username", "user")
        kwargs.setdefault("password", "pass")
        return TitloviProvider(**kwargs)

    @staticmethod
    def _token_response(token="tok-1", user_id=7, expires="2099-01-01T00:00:00"):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "Token": token,
            "UserId": user_id,
            "ExpirationDate": expires,
        }
        return resp

    def test_import_and_name(self):
        p = self._provider()
        assert p.name == "titlovi"

    def test_languages_balkan(self):
        p = self._provider()
        assert "hr" in p.languages  # Croatian
        assert "sr" in p.languages  # Serbian
        assert "bs" in p.languages  # Bosnian
        assert "sl" in p.languages  # Slovenian
        assert "mk" in p.languages  # Macedonian
        assert "zh" not in p.languages

    def test_credentials_required(self):
        from providers.titlovi import TitloviProvider

        keys = {f["key"]: f for f in TitloviProvider.config_fields}
        assert keys["titlovi_username"]["required"] is True
        assert keys["titlovi_password"]["required"] is True

    def test_initialize_without_credentials_disables_provider(self):
        from providers.titlovi import TitloviProvider

        p = TitloviProvider()
        p.initialize()
        assert p.session is None

    def test_health_check_not_initialized(self):
        from providers.titlovi import TitloviProvider

        p = TitloviProvider()
        healthy, msg = p.health_check()
        assert not healthy

    def test_initialize_creates_session(self):
        p = self._provider()
        with patch("providers.titlovi.create_session") as mock_cs:
            mock_cs.return_value = MagicMock()
            p.initialize()
            assert p.session is not None

    def test_terminate_closes_session(self):
        p = self._provider()
        p.session = MagicMock()
        p.terminate()
        assert p.session is None

    def test_login_obtains_token(self):
        p = self._provider()
        p.session = MagicMock()
        p.session.post.return_value = self._token_response()

        assert p._ensure_token() is True
        assert p._token == "tok-1"
        assert p._user_id == 7
        call = p.session.post.call_args
        assert call.args[0].endswith("/gettoken")
        assert call.kwargs["params"]["username"] == "user"
        assert call.kwargs["params"]["password"] == "pass"

    def test_login_rejected_credentials(self):
        p = self._provider(password="wrong")
        p.session = MagicMock()
        resp = MagicMock()
        resp.status_code = 401
        p.session.post.return_value = resp

        assert p._ensure_token() is False
        assert p._token is None

    def test_cached_token_is_reused(self):
        from datetime import UTC, datetime, timedelta

        p = self._provider()
        p.session = MagicMock()
        p._token = "cached"
        p._user_id = 1
        p._token_expires = datetime.now(UTC) + timedelta(days=1)

        assert p._ensure_token() is True
        p.session.post.assert_not_called()

    def test_expired_token_triggers_relogin(self):
        from datetime import UTC, datetime, timedelta

        p = self._provider()
        p.session = MagicMock()
        p.session.post.return_value = self._token_response(token="renewed")
        p._token = "stale"
        p._user_id = 1
        p._token_expires = datetime.now(UTC) - timedelta(minutes=5)

        assert p._ensure_token() is True
        assert p._token == "renewed"

    def test_search_returns_empty_without_session(self):
        from providers.base import VideoQuery

        p = self._provider()
        q = VideoQuery(title="Test", languages=["hr"])
        assert p.search(q) == []

    def test_search_skips_non_balkan_languages(self):
        from providers.base import VideoQuery

        p = self._provider()
        p.session = MagicMock()
        result = p.search(VideoQuery(title="Test", languages=["en", "de", "fr"]))
        assert result == []
        p.session.get.assert_not_called()

    def test_search_builds_correct_params(self):
        from providers.base import VideoQuery

        p = self._provider()
        mock_session = MagicMock()
        mock_session.post.return_value = self._token_response()
        mock_session.get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"SubtitleResults": [], "PagesAvailable": 1},
        )
        p.session = mock_session
        q = VideoQuery(title="Squid Game", season=1, episode=1, languages=["hr", "sr"])
        p.search(q)
        mock_session.get.assert_called_once()
        params = mock_session.get.call_args.kwargs.get("params") or {}
        # The Kodi API takes `query` + titlovi language names + token/userid.
        assert params.get("query") == "Squid Game"
        assert set(params.get("lang", "").split("|")) == {"Hrvatski", "Srpski"}
        assert params.get("token") == "tok-1"
        assert params.get("userid") == 7
        assert params.get("season") == 1
        assert params.get("json") is True

    def test_search_parses_results(self):
        from providers.base import VideoQuery

        p = self._provider()
        mock_session = MagicMock()
        mock_session.post.return_value = self._token_response()
        mock_session.get.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "SubtitleResults": [
                    {
                        "Id": 111,
                        "Title": "Squid Game",
                        "Link": "https://titlovi.com/download/?type=1&mediaid=111",
                        "Release": "Squid.Game.S01E01.1080p.WEB",
                        "Lang": "Hrvatski",
                        "Season": 1,
                        "Episode": 1,
                    },
                    {
                        # Cyrillic Serbian maps back to "sr"
                        "Id": 222,
                        "Title": "Squid Game",
                        "Link": "https://titlovi.com/download/?type=1&mediaid=222",
                        "Release": "Squid.Game.S01E01.720p",
                        "Lang": "Cirilica",
                        "Season": 1,
                        "Episode": 1,
                    },
                    {
                        # Wrong episode — must be filtered out
                        "Id": 333,
                        "Title": "Squid Game",
                        "Link": "https://titlovi.com/download/?type=1&mediaid=333",
                        "Release": "Squid.Game.S01E02.1080p",
                        "Lang": "Hrvatski",
                        "Season": 1,
                        "Episode": 2,
                    },
                ],
                "PagesAvailable": 1,
            },
        )
        p.session = mock_session
        q = VideoQuery(title="Squid Game", season=1, episode=1, languages=["hr", "sr"])
        results = p.search(q)

        assert [r.subtitle_id for r in results] == ["111", "222"]
        assert results[0].language == "hr"
        assert results[1].language == "sr"
        assert results[0].download_url == "https://titlovi.com/download/?type=1&mediaid=111"
        assert results[0].release_info == "Squid.Game.S01E01.1080p.WEB"

    def test_search_season_pack_is_kept_and_marked(self):
        from providers.base import VideoQuery

        p = self._provider()
        mock_session = MagicMock()
        mock_session.post.return_value = self._token_response()
        mock_session.get.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "SubtitleResults": [
                    {
                        "Id": 444,
                        "Title": "Squid Game",
                        "Link": "https://titlovi.com/download/?type=1&mediaid=444",
                        "Release": "Squid.Game.S01.Complete",
                        "Lang": "Srpski",
                        "Season": 1,
                        "Episode": 0,  # 0 == season pack
                    }
                ],
                "PagesAvailable": 1,
            },
        )
        p.session = mock_session
        q = VideoQuery(title="Squid Game", season=1, episode=3, languages=["sr"])
        results = p.search(q)

        assert len(results) == 1
        assert results[0].provider_data.get("is_pack") is True
        assert results[0].provider_data.get("episode") == 3

    def test_search_relogs_in_on_401(self):
        from providers.base import VideoQuery

        p = self._provider()
        mock_session = MagicMock()
        mock_session.post.return_value = self._token_response(token="renewed")
        ok_resp = MagicMock(
            status_code=200,
            json=lambda: {"SubtitleResults": [], "PagesAvailable": 1},
        )
        unauth_resp = MagicMock(status_code=401)
        mock_session.get.side_effect = [unauth_resp, ok_resp]
        p.session = mock_session
        p._token = "stale"
        p._user_id = 1
        p._token_expires = None  # unknown expiry — trusted until the API says 401

        results = p.search(VideoQuery(title="Test", languages=["hr"]))

        assert results == []
        assert mock_session.get.call_count == 2
        assert p._token == "renewed"

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
        with pytest.raises(ProviderError):
            p.download(r)

    def test_download_success_returns_content(self):
        from providers.base import SubtitleFormat, SubtitleResult

        p = self._provider()
        srt_bytes = b"1\n00:00:01,000 --> 00:00:02,000\nHvala\n"
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.iter_content.return_value = [srt_bytes]
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.raise_for_status = MagicMock()
        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
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

    def test_download_pack_zip_picks_matching_episode(self):
        import io
        import zipfile

        from providers.base import SubtitleFormat, SubtitleResult

        p = self._provider()
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("Show.S01E01.srt", "1\n00:00:01,000 --> 00:00:02,000\nEp1\n")
            zf.writestr("Show.S01E03.srt", "1\n00:00:01,000 --> 00:00:02,000\nEp3\n")
        zip_bytes = buf.getvalue()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.iter_content.return_value = [zip_bytes]
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.raise_for_status = MagicMock()
        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        p.session = mock_session
        r = SubtitleResult(
            provider_name="titlovi",
            subtitle_id="444",
            language="sr",
            format=SubtitleFormat.SRT,
            filename="pack.zip",
            download_url="https://titlovi.com/download/444",
            provider_data={"is_pack": True, "season": 1, "episode": 3},
        )
        content = p.download(r)
        assert b"Ep3" in content
        assert "E03" in r.filename or "e03" in r.filename


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
            patch("providers.embedded.os.path.exists", return_value=True),
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
            patch("providers.embedded.os.path.exists", return_value=True),
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
            patch("providers.embedded.os.path.exists", return_value=True),
        ):
            q = VideoQuery(file_path="/data/video.mkv", title="Test", languages=["de"])
            results = p.search(q)
        assert results[0].provider_data["stream_index"] == 5
        assert results[0].provider_data["file_path"] == "/data/video.mkv"

    def test_download_raises_when_no_file_path_in_provider_data(self):
        import pytest

        from providers.base import SubtitleFormat, SubtitleResult
        from providers.embedded import EmbeddedSubtitlesProvider

        p = EmbeddedSubtitlesProvider()
        p.initialize()
        r = SubtitleResult(
            provider_name="embedded",
            subtitle_id="track_2",
            language="de",
            format=SubtitleFormat.SRT,
            filename="track_2.srt",
            download_url="",
            provider_data={},  # no file_path
        )
        with pytest.raises(RuntimeError, match="no file_path"):
            p.download(r)

    def test_download_cleans_up_tempfile_on_ffmpeg_error(self):
        import os
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
        created_tmp = []

        real_mkstemp = __import__("tempfile").mkstemp

        def fake_mkstemp(suffix=""):
            fd, path = real_mkstemp(suffix=suffix)
            created_tmp.append(path)
            return fd, path

        with (
            patch("tempfile.mkstemp", side_effect=fake_mkstemp),
            patch(
                "providers.embedded.extract_subtitle_stream",
                side_effect=RuntimeError("ffmpeg failed"),
            ),
            pytest.raises(RuntimeError, match="ffmpeg failed"),
        ):
            p.download(r)

        # Tempfile must be cleaned up
        for path in created_tmp:
            assert not os.path.exists(path), f"Tempfile not cleaned up: {path}"

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
