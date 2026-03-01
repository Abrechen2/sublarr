"""Unit tests for the 4 new subtitle providers."""

from unittest.mock import MagicMock, patch


class TestSubsceneProvider:
    """Tests for the Subscene provider."""

    def test_import_and_name(self):
        from providers.subscene import SubsceneProvider

        p = SubsceneProvider()
        assert p.name == "subscene"

    def test_languages(self):
        from providers.subscene import SubsceneProvider

        p = SubsceneProvider()
        assert "en" in p.languages
        assert "de" in p.languages
        assert "ja" in p.languages
        assert len(p.languages) >= 50

    def test_no_credentials_required(self):
        from providers.subscene import SubsceneProvider

        p = SubsceneProvider()
        assert p.config_fields == []

    def test_health_check_not_initialized(self):
        from providers.subscene import SubsceneProvider

        p = SubsceneProvider()
        healthy, msg = p.health_check()
        assert not healthy

    def test_initialize_creates_session(self):
        from providers.subscene import SubsceneProvider

        p = SubsceneProvider()
        with patch("providers.subscene.create_session") as mock_cs:
            mock_session = MagicMock()
            mock_cs.return_value = mock_session
            p.initialize()
            assert p.session is not None

    def test_terminate_closes_session(self):
        from providers.subscene import SubsceneProvider

        p = SubsceneProvider()
        p.session = MagicMock()
        p.terminate()
        assert p.session is None

    def test_search_returns_empty_without_session(self):
        from providers.base import VideoQuery
        from providers.subscene import SubsceneProvider

        p = SubsceneProvider()
        q = VideoQuery(title="Test", languages=["en"])
        assert p.search(q) == []

    def test_search_skips_unsupported_language(self):
        from providers.base import VideoQuery
        from providers.subscene import SubsceneProvider

        p = SubsceneProvider()
        p.session = MagicMock()
        q = VideoQuery(title="Test", languages=["xx-unknown"])
        # All unknown langs → no requests made, empty result
        with patch("providers.subscene._HAS_BS4", True):
            result = p.search(q)
        assert result == []

    def test_download_raises_without_session(self):
        import pytest

        from providers.base import SubtitleResult
        from providers.subscene import SubsceneProvider

        p = SubsceneProvider()
        r = SubtitleResult(
            provider_name="subscene",
            subtitle_id="1",
            language="en",
            download_url="https://example.com",
        )
        with pytest.raises(RuntimeError):
            p.download(r)

    def test_no_bs4_health_check(self):
        from providers.subscene import SubsceneProvider

        p = SubsceneProvider()
        p.session = MagicMock()
        with patch("providers.subscene._HAS_BS4", False):
            healthy, msg = p.health_check()
            assert not healthy
            assert "beautifulsoup4" in msg.lower()

    def test_no_bs4_search_returns_empty(self):
        from providers.base import VideoQuery
        from providers.subscene import SubsceneProvider

        p = SubsceneProvider()
        p.session = MagicMock()
        q = VideoQuery(title="Test", languages=["en"])
        with patch("providers.subscene._HAS_BS4", False):
            result = p.search(q)
        assert result == []


class TestTVSubtitlesProvider:
    """Tests for the TVSubtitles provider."""

    def test_import_and_name(self):
        from providers.tvsubtitles import TVSubtitlesProvider

        p = TVSubtitlesProvider()
        assert p.name == "tvsubtitles"

    def test_languages(self):
        from providers.tvsubtitles import TVSubtitlesProvider

        p = TVSubtitlesProvider()
        assert "en" in p.languages
        assert "de" in p.languages
        assert len(p.languages) >= 25

    def test_no_credentials_required(self):
        from providers.tvsubtitles import TVSubtitlesProvider

        p = TVSubtitlesProvider()
        assert p.config_fields == []

    def test_health_check_not_initialized(self):
        from providers.tvsubtitles import TVSubtitlesProvider

        p = TVSubtitlesProvider()
        healthy, msg = p.health_check()
        assert not healthy

    def test_initialize_creates_session(self):
        from providers.tvsubtitles import TVSubtitlesProvider

        p = TVSubtitlesProvider()
        with patch("providers.tvsubtitles.create_session") as mock_cs:
            mock_cs.return_value = MagicMock()
            p.initialize()
            assert p.session is not None

    def test_terminate_closes_session(self):
        from providers.tvsubtitles import TVSubtitlesProvider

        p = TVSubtitlesProvider()
        p.session = MagicMock()
        p.terminate()
        assert p.session is None

    def test_search_returns_empty_without_session(self):
        from providers.base import VideoQuery
        from providers.tvsubtitles import TVSubtitlesProvider

        p = TVSubtitlesProvider()
        q = VideoQuery(title="Test", languages=["en"])
        assert p.search(q) == []

    def test_search_skips_movies(self):
        from providers.base import VideoQuery
        from providers.tvsubtitles import TVSubtitlesProvider

        p = TVSubtitlesProvider()
        p.session = MagicMock()
        q = VideoQuery(title="Inception", languages=["en"])
        with patch("providers.tvsubtitles._HAS_BS4", True), \
             patch.object(type(q), "is_movie", new_callable=lambda: property(lambda self: True)):
            result = p.search(q)
        assert result == []

    def test_download_raises_without_session(self):
        import pytest

        from providers.base import SubtitleResult
        from providers.tvsubtitles import TVSubtitlesProvider

        p = TVSubtitlesProvider()
        r = SubtitleResult(
            provider_name="tvsubtitles",
            subtitle_id="1",
            language="en",
            download_url="https://example.com",
        )
        with pytest.raises(RuntimeError):
            p.download(r)

    def test_no_bs4_health_check(self):
        from providers.tvsubtitles import TVSubtitlesProvider

        p = TVSubtitlesProvider()
        p.session = MagicMock()
        with patch("providers.tvsubtitles._HAS_BS4", False):
            healthy, msg = p.health_check()
            assert not healthy
            assert "beautifulsoup4" in msg.lower()

    def test_no_bs4_search_returns_empty(self):
        from providers.base import VideoQuery
        from providers.tvsubtitles import TVSubtitlesProvider

        p = TVSubtitlesProvider()
        p.session = MagicMock()
        q = VideoQuery(title="Test", languages=["en"])
        with patch("providers.tvsubtitles._HAS_BS4", False):
            result = p.search(q)
        assert result == []


class TestAddic7edProvider:
    """Tests for the Addic7ed provider."""

    def test_import_and_name(self):
        from providers.addic7ed import Addic7edProvider

        p = Addic7edProvider()
        assert p.name == "addic7ed"

    def test_languages(self):
        from providers.addic7ed import Addic7edProvider

        p = Addic7edProvider()
        assert "en" in p.languages
        assert "de" in p.languages
        assert len(p.languages) >= 30

    def test_credentials_optional(self):
        from providers.addic7ed import Addic7edProvider

        p = Addic7edProvider()
        fields = {f["key"]: f for f in p.config_fields}
        assert "addic7ed_username" in fields
        assert fields["addic7ed_username"]["required"] is False
        assert "addic7ed_password" in fields
        assert fields["addic7ed_password"]["required"] is False

    def test_health_check_not_initialized(self):
        from providers.addic7ed import Addic7edProvider

        p = Addic7edProvider()
        healthy, msg = p.health_check()
        assert not healthy

    def test_initialize_creates_session(self):
        from providers.addic7ed import Addic7edProvider

        p = Addic7edProvider()
        with patch("providers.addic7ed.create_session") as mock_cs:
            mock_cs.return_value = MagicMock()
            p.initialize()
            assert p.session is not None

    def test_initialize_without_credentials_no_login(self):
        from providers.addic7ed import Addic7edProvider

        p = Addic7edProvider()
        with patch("providers.addic7ed.create_session") as mock_cs:
            mock_cs.return_value = MagicMock()
            with patch.object(p, "_login") as mock_login:
                p.initialize()
                mock_login.assert_not_called()
        assert not p._logged_in

    def test_initialize_with_credentials_calls_login(self):
        from providers.addic7ed import Addic7edProvider

        p = Addic7edProvider(username="user", password="pass")
        with patch("providers.addic7ed.create_session") as mock_cs:
            mock_cs.return_value = MagicMock()
            with patch.object(p, "_login") as mock_login:
                p.initialize()
                mock_login.assert_called_once()

    def test_terminate_closes_session(self):
        from providers.addic7ed import Addic7edProvider

        p = Addic7edProvider()
        p.session = MagicMock()
        p.terminate()
        assert p.session is None

    def test_search_returns_empty_without_session(self):
        from providers.base import VideoQuery
        from providers.addic7ed import Addic7edProvider

        p = Addic7edProvider()
        q = VideoQuery(title="Test", languages=["en"])
        assert p.search(q) == []

    def test_search_skips_movies(self):
        from providers.base import VideoQuery
        from providers.addic7ed import Addic7edProvider

        p = Addic7edProvider()
        p.session = MagicMock()
        q = VideoQuery(title="Inception", languages=["en"])
        with patch("providers.addic7ed._HAS_BS4", True), \
             patch.object(type(q), "is_movie", new_callable=lambda: property(lambda self: True)):
            result = p.search(q)
        assert result == []

    def test_download_raises_without_session(self):
        import pytest

        from providers.base import SubtitleResult
        from providers.addic7ed import Addic7edProvider

        p = Addic7edProvider()
        r = SubtitleResult(
            provider_name="addic7ed",
            subtitle_id="1",
            language="en",
            download_url="https://example.com",
        )
        with pytest.raises(RuntimeError):
            p.download(r)

    def test_no_bs4_health_check(self):
        from providers.addic7ed import Addic7edProvider

        p = Addic7edProvider()
        p.session = MagicMock()
        with patch("providers.addic7ed._HAS_BS4", False):
            healthy, msg = p.health_check()
            assert not healthy
            assert "beautifulsoup4" in msg.lower()

    def test_no_bs4_search_returns_empty(self):
        from providers.base import VideoQuery
        from providers.addic7ed import Addic7edProvider

        p = Addic7edProvider()
        p.session = MagicMock()
        q = VideoQuery(title="Test", languages=["en"])
        with patch("providers.addic7ed._HAS_BS4", False):
            result = p.search(q)
        assert result == []


class TestTurkcealtyaziProvider:
    """Tests for the Turkcealtyazi provider."""

    def test_import_and_name(self):
        from providers.turkcealtyazi import TurkcealtyaziProvider

        p = TurkcealtyaziProvider()
        assert p.name == "turkcealtyazi"

    def test_languages(self):
        from providers.turkcealtyazi import TurkcealtyaziProvider

        p = TurkcealtyaziProvider()
        assert "tr" in p.languages
        assert len(p.languages) == 1

    def test_credentials_required(self):
        from providers.turkcealtyazi import TurkcealtyaziProvider

        p = TurkcealtyaziProvider()
        fields = {f["key"]: f for f in p.config_fields}
        assert "turkcealtyazi_username" in fields
        assert fields["turkcealtyazi_username"]["required"] is True
        assert "turkcealtyazi_password" in fields
        assert fields["turkcealtyazi_password"]["required"] is True

    def test_health_check_missing_credentials(self):
        from providers.turkcealtyazi import TurkcealtyaziProvider

        p = TurkcealtyaziProvider()
        healthy, msg = p.health_check()
        assert not healthy
        assert "credential" in msg.lower() or "configured" in msg.lower()

    def test_health_check_not_logged_in(self):
        from providers.turkcealtyazi import TurkcealtyaziProvider

        p = TurkcealtyaziProvider(username="u", password="p")
        p.session = MagicMock()
        with patch("providers.turkcealtyazi._HAS_BS4", True):
            healthy, msg = p.health_check()
            assert not healthy

    def test_initialize_without_credentials_skips(self):
        from providers.turkcealtyazi import TurkcealtyaziProvider

        p = TurkcealtyaziProvider()
        p.initialize()
        assert p.session is None

    def test_initialize_with_credentials_creates_session(self):
        from providers.turkcealtyazi import TurkcealtyaziProvider

        p = TurkcealtyaziProvider(username="user", password="pass")
        with patch("providers.turkcealtyazi.create_session") as mock_cs:
            mock_session = MagicMock()
            mock_cs.return_value = mock_session
            with patch.object(p, "_login"):
                p.initialize()
                assert p.session is not None

    def test_terminate_closes_session(self):
        from providers.turkcealtyazi import TurkcealtyaziProvider

        p = TurkcealtyaziProvider()
        p.session = MagicMock()
        p.terminate()
        assert p.session is None
        assert not p._logged_in

    def test_search_returns_empty_not_logged_in(self):
        from providers.base import VideoQuery
        from providers.turkcealtyazi import TurkcealtyaziProvider

        p = TurkcealtyaziProvider()
        q = VideoQuery(title="Test", languages=["tr"])
        assert p.search(q) == []

    def test_search_skips_non_turkish(self):
        from providers.base import VideoQuery
        from providers.turkcealtyazi import TurkcealtyaziProvider

        p = TurkcealtyaziProvider(username="u", password="p")
        p.session = MagicMock()
        p._logged_in = True
        q = VideoQuery(title="Test", languages=["en"])
        with patch("providers.turkcealtyazi._HAS_BS4", True):
            result = p.search(q)
        assert result == []

    def test_download_raises_without_session(self):
        import pytest

        from providers.base import SubtitleResult
        from providers.turkcealtyazi import TurkcealtyaziProvider

        p = TurkcealtyaziProvider()
        r = SubtitleResult(
            provider_name="turkcealtyazi",
            subtitle_id="1",
            language="tr",
            download_url="https://example.com",
        )
        with pytest.raises(RuntimeError):
            p.download(r)

    def test_download_raises_not_logged_in(self):
        import pytest

        from providers.base import SubtitleResult
        from providers.turkcealtyazi import TurkcealtyaziProvider

        p = TurkcealtyaziProvider()
        p.session = MagicMock()
        r = SubtitleResult(
            provider_name="turkcealtyazi",
            subtitle_id="1",
            language="tr",
            download_url="https://example.com",
        )
        with pytest.raises(Exception):
            p.download(r)

    def test_no_bs4_health_check(self):
        from providers.turkcealtyazi import TurkcealtyaziProvider

        p = TurkcealtyaziProvider(username="u", password="p")
        p.session = MagicMock()
        p._logged_in = True
        with patch("providers.turkcealtyazi._HAS_BS4", False):
            healthy, msg = p.health_check()
            assert not healthy
            assert "beautifulsoup4" in msg.lower()

    def test_no_bs4_search_returns_empty(self):
        from providers.base import VideoQuery
        from providers.turkcealtyazi import TurkcealtyaziProvider

        p = TurkcealtyaziProvider(username="u", password="p")
        p.session = MagicMock()
        p._logged_in = True
        q = VideoQuery(title="Test", languages=["tr"])
        with patch("providers.turkcealtyazi._HAS_BS4", False):
            result = p.search(q)
        assert result == []
