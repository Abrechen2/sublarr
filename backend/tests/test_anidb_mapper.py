"""Unit tests for anidb_mapper module — AniDB ID resolution from multiple sources."""

import gzip
import os
import xml.etree.ElementTree as ET
from unittest.mock import MagicMock, patch

import pytest

import anidb_mapper

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_settings(**overrides):
    """Create a mock settings object with sensible defaults for AniDB tests."""
    defaults = {
        "anidb_enabled": True,
        "anidb_custom_field_name": "anidb_id",
        "anidb_fallback_to_mapping": True,
    }
    defaults.update(overrides)
    mock = MagicMock()
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


def _build_title_dump_xml(entries: list[tuple[int, list[str]]]) -> bytes:
    """Build a minimal anime-titles.xml.gz payload.

    Args:
        entries: list of (aid, [title, ...]) tuples.

    Returns:
        gzip-compressed XML bytes.
    """
    root = ET.Element("animetitles")
    for aid, titles in entries:
        anime_el = ET.SubElement(root, "anime", aid=str(aid))
        for t in titles:
            title_el = ET.SubElement(anime_el, "title", type="official")
            title_el.text = t
    raw = ET.tostring(root, encoding="unicode").encode("utf-8")
    return gzip.compress(raw)


@pytest.fixture(autouse=True)
def _reset_title_index():
    """Reset module-level title index state between tests."""
    anidb_mapper._title_index = {}
    anidb_mapper._title_index_loaded_at = 0.0
    yield
    anidb_mapper._title_index = {}
    anidb_mapper._title_index_loaded_at = 0.0


@pytest.fixture(autouse=True)
def _reset_title_res_cache():
    """Reset the AniList title-resolution TTL cache between tests.

    Without this, resolve_anidb_from_title() calls from earlier tests leak
    cached (hit or miss) entries into later tests using the same title.
    """
    anidb_mapper._title_res_cache.clear()
    yield
    anidb_mapper._title_res_cache.clear()


# ===========================================================================
# extract_anidb_from_custom_fields
# ===========================================================================


class TestExtractAnidbFromCustomFields:
    """Tests for extracting AniDB IDs from Sonarr custom fields."""

    @patch("anidb_mapper.get_settings")
    def test_returns_none_for_empty_series(self, mock_get_settings):
        mock_get_settings.return_value = _make_settings()
        assert anidb_mapper.extract_anidb_from_custom_fields({}) is None
        assert anidb_mapper.extract_anidb_from_custom_fields(None) is None

    @patch("anidb_mapper.get_settings")
    def test_extracts_int_value_from_configured_field(self, mock_get_settings):
        mock_get_settings.return_value = _make_settings(anidb_custom_field_name="anidb_id")
        series = {"customFields": {"anidb_id": 9876}}
        assert anidb_mapper.extract_anidb_from_custom_fields(series) == 9876

    @patch("anidb_mapper.get_settings")
    def test_extracts_string_value_from_configured_field(self, mock_get_settings):
        mock_get_settings.return_value = _make_settings(anidb_custom_field_name="anidb_id")
        series = {"customFields": {"anidb_id": "1234"}}
        assert anidb_mapper.extract_anidb_from_custom_fields(series) == 1234

    @patch("anidb_mapper.get_settings")
    def test_tries_fallback_field_names(self, mock_get_settings):
        mock_get_settings.return_value = _make_settings(anidb_custom_field_name="nonexistent")
        series = {"customFields": {"AniDB": 555}}
        assert anidb_mapper.extract_anidb_from_custom_fields(series) == 555

    @patch("anidb_mapper.get_settings")
    def test_tries_anidb_id_camel_case(self, mock_get_settings):
        mock_get_settings.return_value = _make_settings(anidb_custom_field_name="")
        series = {"customFields": {"anidbId": 777}}
        assert anidb_mapper.extract_anidb_from_custom_fields(series) == 777

    @patch("anidb_mapper.get_settings")
    def test_returns_none_when_no_custom_fields(self, mock_get_settings):
        mock_get_settings.return_value = _make_settings()
        series = {"title": "Some Series"}
        assert anidb_mapper.extract_anidb_from_custom_fields(series) is None

    @patch("anidb_mapper.get_settings")
    def test_returns_none_for_invalid_string_value(self, mock_get_settings):
        mock_get_settings.return_value = _make_settings()
        series = {"customFields": {"anidb_id": "not_a_number"}}
        assert anidb_mapper.extract_anidb_from_custom_fields(series) is None

    @patch("anidb_mapper.get_settings")
    def test_returns_none_for_zero_value(self, mock_get_settings):
        mock_get_settings.return_value = _make_settings()
        series = {"customFields": {"anidb_id": 0}}
        assert anidb_mapper.extract_anidb_from_custom_fields(series) is None

    @patch("anidb_mapper.get_settings")
    def test_returns_none_for_negative_value(self, mock_get_settings):
        mock_get_settings.return_value = _make_settings()
        series = {"customFields": {"anidb_id": -5}}
        assert anidb_mapper.extract_anidb_from_custom_fields(series) is None

    @patch("anidb_mapper.get_settings")
    def test_explicit_custom_field_name_overrides_config(self, mock_get_settings):
        mock_get_settings.return_value = _make_settings(anidb_custom_field_name="wrong_name")
        series = {"customFields": {"my_field": 42}}
        result = anidb_mapper.extract_anidb_from_custom_fields(series, custom_field_name="my_field")
        assert result == 42

    @patch("anidb_mapper.get_settings")
    def test_empty_custom_fields_dict(self, mock_get_settings):
        mock_get_settings.return_value = _make_settings()
        series = {"customFields": {}}
        assert anidb_mapper.extract_anidb_from_custom_fields(series) is None


# ===========================================================================
# get_anidb_id
# ===========================================================================


class TestGetAnidbId:
    """Tests for the main get_anidb_id orchestrator function."""

    @patch("anidb_mapper.get_settings")
    def test_returns_none_when_anidb_disabled(self, mock_get_settings):
        mock_get_settings.return_value = _make_settings(anidb_enabled=False)
        assert anidb_mapper.get_anidb_id(tvdb_id=123, series_title="Naruto") is None

    @patch("anidb_mapper.save_anidb_mapping")
    @patch("anidb_mapper.extract_anidb_from_custom_fields", return_value=9999)
    @patch("anidb_mapper.get_settings")
    def test_custom_fields_highest_priority(self, mock_settings, mock_extract, mock_save):
        mock_settings.return_value = _make_settings()
        series = {"customFields": {"anidb_id": 9999}}
        result = anidb_mapper.get_anidb_id(tvdb_id=100, series_title="Test", series=series)
        assert result == 9999
        mock_extract.assert_called_once_with(series)

    @patch("anidb_mapper.save_anidb_mapping")
    @patch("anidb_mapper.extract_anidb_from_custom_fields", return_value=9999)
    @patch("anidb_mapper.get_settings")
    def test_caches_mapping_when_tvdb_id_available(self, mock_settings, mock_extract, mock_save):
        mock_settings.return_value = _make_settings()
        series = {"customFields": {"anidb_id": 9999}}
        anidb_mapper.get_anidb_id(tvdb_id=100, series_title="Test", series=series)
        mock_save.assert_called_once_with(100, 9999, "Test")

    @patch("anidb_mapper.save_anidb_mapping", side_effect=Exception("DB error"))
    @patch("anidb_mapper.extract_anidb_from_custom_fields", return_value=9999)
    @patch("anidb_mapper.get_settings")
    def test_cache_save_failure_does_not_propagate(self, mock_settings, mock_extract, mock_save):
        mock_settings.return_value = _make_settings()
        series = {"customFields": {"anidb_id": 9999}}
        # Should not raise despite DB error
        result = anidb_mapper.get_anidb_id(tvdb_id=100, series_title="Test", series=series)
        assert result == 9999

    @patch("anidb_mapper.extract_anidb_from_custom_fields", return_value=9999)
    @patch("anidb_mapper.get_settings")
    def test_skips_caching_without_tvdb_id(self, mock_settings, mock_extract):
        mock_settings.return_value = _make_settings()
        series = {"customFields": {"anidb_id": 9999}}
        with patch("anidb_mapper.save_anidb_mapping") as mock_save:
            anidb_mapper.get_anidb_id(tvdb_id=None, series=series)
            mock_save.assert_not_called()

    @patch("anidb_mapper.get_anidb_mapping", return_value=5555)
    @patch("anidb_mapper.get_settings")
    def test_falls_back_to_cache(self, mock_settings, mock_get_mapping):
        mock_settings.return_value = _make_settings()
        result = anidb_mapper.get_anidb_id(tvdb_id=200)
        assert result == 5555
        mock_get_mapping.assert_called_once_with(200)

    @patch("anidb_mapper.get_anidb_mapping", return_value=None)
    @patch("anidb_mapper.get_settings")
    def test_returns_none_when_cache_empty(self, mock_settings, mock_get_mapping):
        mock_settings.return_value = _make_settings()
        result = anidb_mapper.get_anidb_id(tvdb_id=200)
        assert result is None

    @patch("anidb_mapper.get_settings")
    def test_skips_cache_when_fallback_disabled(self, mock_settings):
        mock_settings.return_value = _make_settings(anidb_fallback_to_mapping=False)
        with patch("anidb_mapper.get_anidb_mapping") as mock_get_mapping:
            result = anidb_mapper.get_anidb_id(tvdb_id=200)
            assert result is None
            mock_get_mapping.assert_not_called()

    @patch("anidb_mapper.get_settings")
    def test_returns_none_when_no_tvdb_id_and_no_series(self, mock_settings):
        mock_settings.return_value = _make_settings()
        assert anidb_mapper.get_anidb_id() is None

    @patch("anidb_mapper.save_anidb_mapping")
    @patch("anidb_mapper.extract_anidb_from_custom_fields", return_value=9999)
    @patch("anidb_mapper.get_settings")
    def test_skips_caching_when_fallback_disabled(self, mock_settings, mock_extract, mock_save):
        """Even with tvdb_id, caching should not happen when fallback is disabled."""
        mock_settings.return_value = _make_settings(anidb_fallback_to_mapping=False)
        series = {"customFields": {"anidb_id": 9999}}
        anidb_mapper.get_anidb_id(tvdb_id=100, series_title="Test", series=series)
        mock_save.assert_not_called()


# ===========================================================================
# resolve_anidb_from_anilist
# ===========================================================================


class TestResolveAnidbFromAnilist:
    """Tests for AniList external links resolution."""

    @patch("anidb_mapper.save_anidb_mapping")
    def test_resolves_anidb_from_external_links(self, mock_save):
        mock_client = MagicMock()
        mock_client.get_details.return_value = {
            "externalLinks": [
                {"site": "MyAnimeList", "url": "https://myanimelist.net/anime/1"},
                {"site": "AniDB", "url": "https://anidb.net/anime/4563"},
            ]
        }
        with (
            patch.dict("sys.modules", {"metadata.anilist_client": MagicMock()}),
            patch("anidb_mapper.AniListClient", return_value=mock_client, create=True),
        ):
            # Need to re-import within the patched context
            pass

        # Simpler approach: patch at the import point
        mock_module = MagicMock()
        mock_module.get_anilist_client.return_value = mock_client
        with patch.dict(
            "sys.modules", {"metadata": MagicMock(), "metadata.anilist_client": mock_module}
        ):
            result = anidb_mapper.resolve_anidb_from_anilist(12345, tvdb_id=100)
        assert result == 4563
        mock_save.assert_called_once_with(100, 4563)

    @patch("anidb_mapper.save_anidb_mapping")
    def test_returns_none_when_no_details(self, mock_save):
        mock_client = MagicMock()
        mock_client.get_details.return_value = None
        mock_module = MagicMock()
        mock_module.get_anilist_client.return_value = mock_client
        with patch.dict(
            "sys.modules", {"metadata": MagicMock(), "metadata.anilist_client": mock_module}
        ):
            result = anidb_mapper.resolve_anidb_from_anilist(99999)
        assert result is None
        mock_save.assert_not_called()

    @patch("anidb_mapper.save_anidb_mapping")
    def test_returns_none_when_no_anidb_link(self, mock_save):
        mock_client = MagicMock()
        mock_client.get_details.return_value = {
            "externalLinks": [
                {"site": "MyAnimeList", "url": "https://myanimelist.net/anime/1"},
            ]
        }
        mock_module = MagicMock()
        mock_module.get_anilist_client.return_value = mock_client
        with patch.dict(
            "sys.modules", {"metadata": MagicMock(), "metadata.anilist_client": mock_module}
        ):
            result = anidb_mapper.resolve_anidb_from_anilist(12345)
        assert result is None

    @patch("anidb_mapper.save_anidb_mapping")
    def test_skips_caching_without_tvdb_id(self, mock_save):
        mock_client = MagicMock()
        mock_client.get_details.return_value = {
            "externalLinks": [
                {"site": "AniDB", "url": "https://anidb.net/anime/4563"},
            ]
        }
        mock_module = MagicMock()
        mock_module.get_anilist_client.return_value = mock_client
        with patch.dict(
            "sys.modules", {"metadata": MagicMock(), "metadata.anilist_client": mock_module}
        ):
            result = anidb_mapper.resolve_anidb_from_anilist(12345, tvdb_id=None)
        assert result == 4563
        mock_save.assert_not_called()

    def test_handles_import_error_gracefully(self):
        """If metadata.anilist_client cannot be imported, returns None."""
        with patch.dict("sys.modules", {"metadata": None, "metadata.anilist_client": None}):
            # Force ImportError by making module None
            result = anidb_mapper.resolve_anidb_from_anilist(12345)
        assert result is None

    @patch("anidb_mapper.save_anidb_mapping", side_effect=Exception("DB error"))
    def test_cache_save_failure_still_returns_id(self, mock_save):
        mock_client = MagicMock()
        mock_client.get_details.return_value = {
            "externalLinks": [
                {"site": "AniDB", "url": "https://anidb.net/anime/4563"},
            ]
        }
        mock_module = MagicMock()
        mock_module.get_anilist_client.return_value = mock_client
        with patch.dict(
            "sys.modules", {"metadata": MagicMock(), "metadata.anilist_client": mock_module}
        ):
            result = anidb_mapper.resolve_anidb_from_anilist(12345, tvdb_id=100)
        assert result == 4563

    def test_handles_malformed_url(self):
        """AniDB link with no numeric anime ID in URL returns None for that link."""
        mock_client = MagicMock()
        mock_client.get_details.return_value = {
            "externalLinks": [
                {"site": "AniDB", "url": "https://anidb.net/no-id-here"},
            ]
        }
        mock_module = MagicMock()
        mock_module.get_anilist_client.return_value = mock_client
        with patch.dict(
            "sys.modules", {"metadata": MagicMock(), "metadata.anilist_client": mock_module}
        ):
            result = anidb_mapper.resolve_anidb_from_anilist(12345)
        assert result is None

    def test_empty_external_links(self):
        mock_client = MagicMock()
        mock_client.get_details.return_value = {"externalLinks": []}
        mock_module = MagicMock()
        mock_module.get_anilist_client.return_value = mock_client
        with patch.dict(
            "sys.modules", {"metadata": MagicMock(), "metadata.anilist_client": mock_module}
        ):
            result = anidb_mapper.resolve_anidb_from_anilist(12345)
        assert result is None


# ===========================================================================
# _normalize
# ===========================================================================


class TestNormalize:
    """Tests for internal title normalization."""

    def test_lowercases(self):
        assert anidb_mapper._normalize("HELLO WORLD") == "hello world"

    def test_collapses_whitespace(self):
        assert anidb_mapper._normalize("hello   world") == "hello world"

    def test_strips_leading_trailing(self):
        assert anidb_mapper._normalize("  hello  ") == "hello"

    def test_handles_tabs_and_newlines(self):
        assert anidb_mapper._normalize("hello\t\nworld") == "hello world"

    def test_empty_string(self):
        assert anidb_mapper._normalize("") == ""

    def test_mixed_case_and_spaces(self):
        assert anidb_mapper._normalize("  Sword Art   Online  ") == "sword art online"


# ===========================================================================
# _fetch_dump
# ===========================================================================


class TestFetchDump:
    """Tests for downloading and validating the AniDB title dump."""

    @patch("anidb_mapper.urlopen")
    def test_successful_download(self, mock_urlopen, tmp_path):
        """Valid gzip with enough entries is accepted."""
        # Build valid XML with > _DUMP_MIN_ENTRIES entries
        root = ET.Element("animetitles")
        for i in range(8001):
            anime_el = ET.SubElement(root, "anime", aid=str(i + 1))
            title_el = ET.SubElement(anime_el, "title")
            title_el.text = f"Anime {i + 1}"
        raw = ET.tostring(root, encoding="unicode").encode("utf-8")
        compressed = gzip.compress(raw)

        mock_resp = MagicMock()
        mock_resp.read.return_value = compressed
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        cache_file = str(tmp_path / "test_dump.xml.gz")
        with patch.object(anidb_mapper, "_DUMP_CACHE_FILE", cache_file):
            result = anidb_mapper._fetch_dump()

        assert result is True
        assert os.path.exists(cache_file)

    @patch("anidb_mapper.urlopen")
    def test_rejects_too_few_entries(self, mock_urlopen, tmp_path):
        """Dump with fewer than _DUMP_MIN_ENTRIES is rejected."""
        root = ET.Element("animetitles")
        for i in range(100):
            ET.SubElement(root, "anime", aid=str(i + 1))
        raw = ET.tostring(root, encoding="unicode").encode("utf-8")
        compressed = gzip.compress(raw)

        mock_resp = MagicMock()
        mock_resp.read.return_value = compressed
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        cache_file = str(tmp_path / "test_dump.xml.gz")
        with patch.object(anidb_mapper, "_DUMP_CACHE_FILE", cache_file):
            result = anidb_mapper._fetch_dump()

        assert result is False

    @patch("anidb_mapper.urlopen")
    def test_rejects_invalid_gzip(self, mock_urlopen, tmp_path):
        """Non-gzip data causes parse failure and returns False."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"not gzip data"
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        cache_file = str(tmp_path / "test_dump.xml.gz")
        with patch.object(anidb_mapper, "_DUMP_CACHE_FILE", cache_file):
            result = anidb_mapper._fetch_dump()

        assert result is False

    @patch("anidb_mapper.urlopen", side_effect=Exception("Network error"))
    def test_network_error_returns_false(self, mock_urlopen):
        result = anidb_mapper._fetch_dump()
        assert result is False


# ===========================================================================
# _load_title_index
# ===========================================================================


class TestLoadTitleIndex:
    """Tests for building the in-memory title index."""

    @patch("anidb_mapper._fetch_dump", return_value=True)
    def test_loads_from_cache_file(self, mock_fetch, tmp_path):
        """Parses a valid gzip cache file into the title index."""
        data = _build_title_dump_xml(
            [
                (100, ["Naruto"]),
                (200, ["One Piece", "OP"]),
            ]
        )
        cache_file = str(tmp_path / "dump.xml.gz")
        with open(cache_file, "wb") as f:
            f.write(data)

        with (
            patch.object(anidb_mapper, "_DUMP_CACHE_FILE", cache_file),
            patch("os.path.exists", return_value=True),
            patch("os.path.getmtime", return_value=9999999999.0),
            patch("time.time", return_value=9999999999.0),
        ):
            anidb_mapper._load_title_index()

        assert anidb_mapper._title_index.get("naruto") == 100
        assert anidb_mapper._title_index.get("one piece") == 200
        assert anidb_mapper._title_index.get("op") == 200

    def test_skips_when_index_still_fresh(self):
        """Does not reload if the index was loaded within TTL."""
        import time as _time

        anidb_mapper._title_index = {"test": 1}
        anidb_mapper._title_index_loaded_at = _time.monotonic()  # just loaded

        with patch("anidb_mapper._fetch_dump") as mock_fetch:
            anidb_mapper._load_title_index()
            mock_fetch.assert_not_called()

        assert anidb_mapper._title_index == {"test": 1}

    @patch("anidb_mapper._fetch_dump", return_value=False)
    @patch("os.path.exists", return_value=False)
    def test_no_cache_file_and_download_fails(self, mock_exists, mock_fetch):
        """When download fails and no cache file exists, index stays empty."""
        anidb_mapper._load_title_index()
        assert anidb_mapper._title_index == {}

    @patch("anidb_mapper._fetch_dump", return_value=True)
    def test_handles_corrupt_cache_file(self, mock_fetch, tmp_path):
        """Corrupt gzip file does not crash, index stays empty."""
        cache_file = str(tmp_path / "dump.xml.gz")
        with open(cache_file, "wb") as f:
            f.write(b"corrupt data")

        with (
            patch.object(anidb_mapper, "_DUMP_CACHE_FILE", cache_file),
            patch("os.path.exists", return_value=True),
            patch("os.path.getmtime", return_value=9999999999.0),
            patch("time.time", return_value=9999999999.0),
        ):
            anidb_mapper._load_title_index()

        assert anidb_mapper._title_index == {}

    @patch("anidb_mapper._fetch_dump", return_value=False)
    def test_uses_stale_cache_when_download_fails(self, mock_fetch, tmp_path):
        """When download fails but a stale cache file exists, it still parses."""
        data = _build_title_dump_xml([(999, ["Stale Entry"])])
        cache_file = str(tmp_path / "dump.xml.gz")
        with open(cache_file, "wb") as f:
            f.write(data)

        with (
            patch.object(anidb_mapper, "_DUMP_CACHE_FILE", cache_file),
            # File exists but is old (triggers download attempt)
            patch("os.path.exists", return_value=True),
            patch("os.path.getmtime", return_value=0.0),
            patch("time.time", return_value=9999999999.0),
        ):
            anidb_mapper._load_title_index()

        assert anidb_mapper._title_index.get("stale entry") == 999

    @patch("anidb_mapper._fetch_dump", return_value=True)
    def test_skips_anime_with_invalid_aid(self, mock_fetch, tmp_path):
        """Anime entries with non-numeric or zero aid are skipped."""
        root = ET.Element("animetitles")
        # Valid entry
        a1 = ET.SubElement(root, "anime", aid="100")
        t1 = ET.SubElement(a1, "title")
        t1.text = "Valid"
        # Zero aid
        a2 = ET.SubElement(root, "anime", aid="0")
        t2 = ET.SubElement(a2, "title")
        t2.text = "Zero"
        # Invalid aid
        a3 = ET.SubElement(root, "anime", aid="abc")
        t3 = ET.SubElement(a3, "title")
        t3.text = "Invalid"

        raw = ET.tostring(root, encoding="unicode").encode("utf-8")
        data = gzip.compress(raw)
        cache_file = str(tmp_path / "dump.xml.gz")
        with open(cache_file, "wb") as f:
            f.write(data)

        with (
            patch.object(anidb_mapper, "_DUMP_CACHE_FILE", cache_file),
            patch("os.path.exists", return_value=True),
            patch("os.path.getmtime", return_value=9999999999.0),
            patch("time.time", return_value=9999999999.0),
        ):
            anidb_mapper._load_title_index()

        assert anidb_mapper._title_index.get("valid") == 100
        assert "zero" not in anidb_mapper._title_index
        assert "invalid" not in anidb_mapper._title_index

    @patch("anidb_mapper._fetch_dump", return_value=True)
    def test_skips_download_when_cache_fresh(self, mock_fetch, tmp_path):
        """When cache file is fresh (within TTL), no download is triggered."""
        data = _build_title_dump_xml([(111, ["Fresh"])])
        cache_file = str(tmp_path / "dump.xml.gz")
        with open(cache_file, "wb") as f:
            f.write(data)

        import time as _time

        current_time = _time.time()

        with (
            patch.object(anidb_mapper, "_DUMP_CACHE_FILE", cache_file),
            patch("os.path.exists", return_value=True),
            # File was just modified
            patch("os.path.getmtime", return_value=current_time),
            patch("time.time", return_value=current_time),
        ):
            anidb_mapper._load_title_index()

        # _fetch_dump should not be called (cache is fresh)
        mock_fetch.assert_not_called()
        assert anidb_mapper._title_index.get("fresh") == 111


# ===========================================================================
# resolve_anidb_from_title_dump
# ===========================================================================


class TestResolveAnidbFromTitleDump:
    """Tests for offline title dump resolution."""

    @patch("anidb_mapper._load_title_index")
    @patch("anidb_mapper.save_anidb_mapping")
    def test_exact_match(self, mock_save, mock_load):
        anidb_mapper._title_index = {"naruto": 100, "one piece": 200}
        result = anidb_mapper.resolve_anidb_from_title_dump("Naruto")
        assert result == 100

    @patch("anidb_mapper._load_title_index")
    @patch("anidb_mapper.save_anidb_mapping")
    def test_exact_match_caches_with_tvdb_id(self, mock_save, mock_load):
        anidb_mapper._title_index = {"naruto": 100}
        anidb_mapper.resolve_anidb_from_title_dump("Naruto", tvdb_id=999)
        mock_save.assert_called_once_with(999, 100)

    @patch("anidb_mapper._load_title_index")
    def test_exact_match_no_caching_without_tvdb_id(self, mock_load):
        anidb_mapper._title_index = {"naruto": 100}
        with patch("anidb_mapper.save_anidb_mapping") as mock_save:
            anidb_mapper.resolve_anidb_from_title_dump("Naruto", tvdb_id=None)
            mock_save.assert_not_called()

    @patch("anidb_mapper._load_title_index")
    @patch("anidb_mapper.save_anidb_mapping")
    def test_fuzzy_match_above_threshold(self, mock_save, mock_load):
        # "narutoo" vs "naruto" should be above 0.82 threshold
        anidb_mapper._title_index = {"naruto": 100}
        result = anidb_mapper.resolve_anidb_from_title_dump("Narutoo")
        # SequenceMatcher("naruto", "narutoo") ~ 0.923 — above threshold
        assert result == 100

    @patch("anidb_mapper._load_title_index")
    @patch("anidb_mapper.save_anidb_mapping")
    def test_fuzzy_match_below_threshold(self, mock_save, mock_load):
        anidb_mapper._title_index = {"naruto": 100}
        result = anidb_mapper.resolve_anidb_from_title_dump("Completely Different Title")
        assert result is None

    @patch("anidb_mapper._load_title_index")
    def test_returns_none_for_empty_title(self, mock_load):
        result = anidb_mapper.resolve_anidb_from_title_dump("")
        assert result is None
        mock_load.assert_not_called()

    @patch("anidb_mapper._load_title_index")
    def test_returns_none_when_index_empty(self, mock_load):
        anidb_mapper._title_index = {}
        result = anidb_mapper.resolve_anidb_from_title_dump("Naruto")
        assert result is None

    @patch("anidb_mapper._load_title_index")
    @patch("anidb_mapper.save_anidb_mapping")
    def test_fuzzy_match_caches_with_tvdb_id(self, mock_save, mock_load):
        anidb_mapper._title_index = {"naruto": 100}
        anidb_mapper.resolve_anidb_from_title_dump("Narutoo", tvdb_id=888)
        mock_save.assert_called_once_with(888, 100)

    @patch("anidb_mapper._load_title_index")
    @patch("anidb_mapper.save_anidb_mapping", side_effect=Exception("DB error"))
    def test_cache_save_failure_on_exact_match(self, mock_save, mock_load):
        """Cache save failure on exact match does not propagate."""
        anidb_mapper._title_index = {"naruto": 100}
        result = anidb_mapper.resolve_anidb_from_title_dump("Naruto", tvdb_id=999)
        assert result == 100

    @patch("anidb_mapper._load_title_index")
    @patch("anidb_mapper.save_anidb_mapping", side_effect=Exception("DB error"))
    def test_cache_save_failure_on_fuzzy_match(self, mock_save, mock_load):
        """Cache save failure on fuzzy match does not propagate."""
        anidb_mapper._title_index = {"naruto": 100}
        result = anidb_mapper.resolve_anidb_from_title_dump("Narutoo", tvdb_id=888)
        assert result == 100


# ===========================================================================
# resolve_anidb_from_title
# ===========================================================================


class TestResolveAnidbFromTitle:
    """Tests for AniList title-search-based resolution."""

    def test_returns_none_for_empty_title(self):
        result = anidb_mapper.resolve_anidb_from_title("")
        assert result is None

    def test_returns_none_for_none_title(self):
        result = anidb_mapper.resolve_anidb_from_title(None)
        assert result is None

    def test_resolves_via_anilist_search(self):
        mock_client = MagicMock()
        mock_client.search_anime.return_value = {
            "id": 555,
            "title": {"romaji": "Naruto"},
        }
        mock_module = MagicMock()
        mock_module.get_anilist_client.return_value = mock_client

        with (
            patch.dict(
                "sys.modules", {"metadata": MagicMock(), "metadata.anilist_client": mock_module}
            ),
            patch("anidb_mapper.resolve_anidb_from_anilist", return_value=1234) as mock_resolve,
        ):
            result = anidb_mapper.resolve_anidb_from_title("Naruto", tvdb_id=100)

        assert result == 1234
        mock_resolve.assert_called_once_with(555, tvdb_id=100)

    def test_returns_none_when_search_returns_nothing(self):
        mock_client = MagicMock()
        mock_client.search_anime.return_value = None
        mock_module = MagicMock()
        mock_module.get_anilist_client.return_value = mock_client

        with patch.dict(
            "sys.modules", {"metadata": MagicMock(), "metadata.anilist_client": mock_module}
        ):
            result = anidb_mapper.resolve_anidb_from_title("Unknown Series")

        assert result is None

    def test_returns_none_when_match_has_no_id(self):
        mock_client = MagicMock()
        mock_client.search_anime.return_value = {"title": {"romaji": "Test"}}
        mock_module = MagicMock()
        mock_module.get_anilist_client.return_value = mock_client

        with patch.dict(
            "sys.modules", {"metadata": MagicMock(), "metadata.anilist_client": mock_module}
        ):
            result = anidb_mapper.resolve_anidb_from_title("Test")

        assert result is None

    def test_handles_exception_gracefully(self):
        """Import or API errors return None."""
        with patch.dict("sys.modules", {"metadata": None, "metadata.anilist_client": None}):
            result = anidb_mapper.resolve_anidb_from_title("Naruto")
        assert result is None
