"""Tests for metadata/__init__.py — MetadataResolver orchestration.

Covers:
- Lazy client creation (TMDB, AniList, TVDB)
- Cache hit / miss paths
- resolve_series: anime path (AniList + TMDB cross-ref), TMDB primary, TVDB fallback, filename fallback
- resolve_movie: TMDB primary, filename fallback
- All normalize_* helpers (TMDB TV, TMDB movie, AniList, TVDB)
- Edge cases: missing keys, None details, string IDs, year parsing
"""

from unittest.mock import MagicMock, patch

import pytest

from metadata import TMDB_POSTER_BASE, MetadataResolver

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def resolver():
    """Resolver with all three API keys set."""
    return MetadataResolver(tmdb_key="tmdb-key", tvdb_key="tvdb-key", tvdb_pin="pin")


@pytest.fixture
def resolver_no_keys():
    """Resolver with no API keys (AniList only)."""
    return MetadataResolver()


@pytest.fixture
def resolver_tmdb_only():
    """Resolver with TMDB key only."""
    return MetadataResolver(tmdb_key="tmdb-key")


# ---------------------------------------------------------------------------
# Lazy client creation
# ---------------------------------------------------------------------------


class TestLazyClients:
    def test_tmdb_none_without_key(self, resolver_no_keys):
        assert resolver_no_keys._tmdb is None

    def test_tmdb_created_with_key(self, resolver):
        client = resolver._tmdb
        assert client is not None
        # Same instance on second access (lazy singleton)
        assert resolver._tmdb is client

    def test_anilist_always_available(self, resolver_no_keys):
        client = resolver_no_keys._anilist
        assert client is not None
        assert resolver_no_keys._anilist is client

    def test_tvdb_none_without_key(self, resolver_no_keys):
        assert resolver_no_keys._tvdb is None

    def test_tvdb_created_with_key(self, resolver):
        client = resolver._tvdb
        assert client is not None
        assert resolver._tvdb is client


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------


class TestCache:
    def test_get_cached_returns_none_when_db_raises(self, resolver):
        """get_db raises -> _get_cached returns None silently."""
        with patch("db.get_db", side_effect=RuntimeError("no db")):
            assert resolver._get_cached("key") is None

    def test_get_cached_returns_none_without_method(self, resolver):
        """DB object lacks standalone.get_cached_metadata -> returns None."""
        mock_db = MagicMock(spec=[])  # no 'standalone' attribute
        with patch("db.get_db", return_value=mock_db):
            assert resolver._get_cached("key") is None

    def test_get_cached_returns_data(self, resolver):
        expected = {"title": "Cached"}
        mock_standalone = MagicMock()
        mock_standalone.get_cached_metadata.return_value = expected
        mock_db = MagicMock()
        mock_db.standalone = mock_standalone
        with patch("db.get_db", return_value=mock_db):
            result = resolver._get_cached("key")
        assert result == expected

    def test_set_cached_silently_ignores_errors(self, resolver):
        """set_cached should not raise even if get_db explodes."""
        with patch("db.get_db", side_effect=RuntimeError("no db")):
            resolver._set_cached("key", {"data": 1})  # no exception

    def test_set_cached_writes_data(self, resolver):
        mock_standalone = MagicMock()
        mock_db = MagicMock()
        mock_db.standalone = mock_standalone
        with patch("db.get_db", return_value=mock_db):
            resolver._set_cached("key", {"title": "Test"})
        mock_standalone.cache_metadata.assert_called_once_with("key", {"title": "Test"})


# ---------------------------------------------------------------------------
# Normalize helpers
# ---------------------------------------------------------------------------


class TestNormalizeTmdbTv:
    def test_basic_fields(self, resolver):
        search = {
            "name": "Attack on Titan",
            "id": 1234,
            "poster_path": "/aot.jpg",
            "first_air_date": "2013-04-07",
        }
        result = resolver._normalize_tmdb_tv(search)
        assert result["title"] == "Attack on Titan"
        assert result["tmdb_id"] == 1234
        assert result["poster_url"] == f"{TMDB_POSTER_BASE}/aot.jpg"
        assert result["year"] == 2013
        assert result["metadata_source"] == "tmdb"
        assert result["is_anime"] is False
        assert result["tvdb_id"] is None
        assert result["imdb_id"] is None

    def test_no_poster_path(self, resolver):
        result = resolver._normalize_tmdb_tv({"name": "X", "id": 1})
        assert result["poster_url"] is None

    def test_invalid_year(self, resolver):
        result = resolver._normalize_tmdb_tv({"name": "X", "id": 1, "first_air_date": "abcd"})
        assert result["year"] is None

    def test_short_first_air_date(self, resolver):
        result = resolver._normalize_tmdb_tv({"name": "X", "id": 1, "first_air_date": "20"})
        assert result["year"] is None

    def test_empty_first_air_date(self, resolver):
        result = resolver._normalize_tmdb_tv({"name": "X", "id": 1, "first_air_date": ""})
        assert result["year"] is None

    def test_enriched_from_details(self, resolver):
        search = {"name": "Naruto", "id": 10, "first_air_date": "2002-10-03"}
        details = {
            "number_of_seasons": 5,
            "number_of_episodes": 220,
            "genres": [{"name": "Animation"}, {"name": "Action"}],
            "origin_country": ["JP"],
        }
        result = resolver._normalize_tmdb_tv(search, details=details)
        assert result["season_count"] == 5
        assert result["episode_count"] == 220
        assert result["is_anime"] is True

    def test_animation_but_not_jp(self, resolver):
        search = {"name": "Rick and Morty", "id": 20, "first_air_date": "2013-12-02"}
        details = {
            "number_of_seasons": 7,
            "number_of_episodes": 71,
            "genres": [{"name": "Animation"}, {"name": "Comedy"}],
            "origin_country": ["US"],
        }
        result = resolver._normalize_tmdb_tv(search, details=details)
        assert result["is_anime"] is False

    def test_enriched_from_external_ids(self, resolver):
        search = {"name": "X", "id": 1}
        ext = {"tvdb_id": 999, "imdb_id": "tt0000001"}
        result = resolver._normalize_tmdb_tv(search, external_ids=ext)
        assert result["tvdb_id"] == 999
        assert result["imdb_id"] == "tt0000001"


class TestNormalizeAnilist:
    def test_basic_fields(self, resolver):
        data = {
            "id": 101,
            "title": {"english": "My Hero Academia", "romaji": "Boku no Hero Academia"},
            "seasonYear": 2016,
            "episodes": 13,
            "coverImage": {"large": "https://img.anilist.co/mha.jpg"},
        }
        result = resolver._normalize_anilist(data)
        assert result["title"] == "My Hero Academia"
        assert result["anilist_id"] == 101
        assert result["year"] == 2016
        assert result["episode_count"] == 13
        assert result["poster_url"] == "https://img.anilist.co/mha.jpg"
        assert result["is_anime"] is True
        assert result["metadata_source"] == "anilist"

    def test_fallback_to_romaji(self, resolver):
        data = {
            "id": 102,
            "title": {"english": None, "romaji": "Shingeki no Kyojin"},
            "seasonYear": 2013,
            "coverImage": {"large": None},
        }
        result = resolver._normalize_anilist(data)
        assert result["title"] == "Shingeki no Kyojin"
        assert result["poster_url"] is None

    def test_empty_title(self, resolver):
        data = {"id": 103, "title": {}, "coverImage": {}}
        result = resolver._normalize_anilist(data)
        assert result["title"] == ""

    def test_no_cover_image(self, resolver):
        data = {"id": 104, "title": {"english": "Test"}, "coverImage": None}
        result = resolver._normalize_anilist(data)
        assert result["poster_url"] is None


class TestNormalizeTvdb:
    def test_basic_fields(self, resolver):
        data = {
            "name": "Breaking Bad",
            "id": "81189",
            "year": "2008",
            "image_url": "https://tvdb.com/bb.jpg",
        }
        result = resolver._normalize_tvdb(data)
        assert result["title"] == "Breaking Bad"
        assert result["tvdb_id"] == 81189
        assert result["year"] == 2008
        assert result["poster_url"] == "https://tvdb.com/bb.jpg"
        assert result["metadata_source"] == "tvdb"

    def test_tvdb_id_field_fallback(self, resolver):
        data = {"name": "X", "tvdb_id": "12345"}
        result = resolver._normalize_tvdb(data)
        assert result["tvdb_id"] == 12345

    def test_int_tvdb_id(self, resolver):
        data = {"name": "X", "tvdb_id": 777}
        result = resolver._normalize_tvdb(data)
        assert result["tvdb_id"] == 777

    def test_invalid_string_tvdb_id(self, resolver):
        data = {"name": "X", "tvdb_id": "not-a-number"}
        result = resolver._normalize_tvdb(data)
        assert result["tvdb_id"] is None

    def test_invalid_string_year(self, resolver):
        data = {"name": "X", "id": 1, "year": "unknown"}
        result = resolver._normalize_tvdb(data)
        assert result["year"] is None

    def test_int_year(self, resolver):
        data = {"name": "X", "id": 1, "year": 2020}
        result = resolver._normalize_tvdb(data)
        assert result["year"] == 2020

    def test_thumbnail_fallback(self, resolver):
        data = {"name": "X", "id": 1, "thumbnail": "https://tvdb.com/thumb.jpg"}
        result = resolver._normalize_tvdb(data)
        assert result["poster_url"] == "https://tvdb.com/thumb.jpg"


class TestNormalizeTmdbMovie:
    def test_basic_fields(self, resolver):
        search = {
            "title": "Inception",
            "id": 27205,
            "poster_path": "/inc.jpg",
            "release_date": "2010-07-16",
        }
        result = resolver._normalize_tmdb_movie(search)
        assert result["title"] == "Inception"
        assert result["tmdb_id"] == 27205
        assert result["poster_url"] == f"{TMDB_POSTER_BASE}/inc.jpg"
        assert result["year"] == 2010
        assert result["metadata_source"] == "tmdb"

    def test_no_release_date(self, resolver):
        result = resolver._normalize_tmdb_movie({"title": "X", "id": 1})
        assert result["year"] is None

    def test_invalid_release_date(self, resolver):
        result = resolver._normalize_tmdb_movie({"title": "X", "id": 1, "release_date": "tbd"})
        assert result["year"] is None

    def test_enriched_from_external_ids(self, resolver):
        search = {"title": "X", "id": 1}
        ext = {"imdb_id": "tt1234567"}
        result = resolver._normalize_tmdb_movie(search, external_ids=ext)
        assert result["imdb_id"] == "tt1234567"

    def test_no_poster(self, resolver):
        result = resolver._normalize_tmdb_movie({"title": "X", "id": 1, "poster_path": None})
        assert result["poster_url"] is None


# ---------------------------------------------------------------------------
# resolve_series
# ---------------------------------------------------------------------------


class TestResolveSeries:
    def _patch_cache(self, resolver, cached_val=None):
        """Patch cache to return given value and capture set_cached calls."""
        resolver._get_cached = MagicMock(return_value=cached_val)
        resolver._set_cached = MagicMock()

    def test_cache_hit(self, resolver):
        cached = {"title": "Cached Series", "metadata_source": "tmdb"}
        self._patch_cache(resolver, cached)
        result = resolver.resolve_series("Test", year=2020)
        assert result == cached
        resolver._set_cached.assert_not_called()

    def test_tmdb_primary_for_non_anime(self, resolver):
        self._patch_cache(resolver)
        tmdb_search = {"name": "The Office", "id": 2316, "first_air_date": "2005-03-24"}
        tmdb_details = {
            "number_of_seasons": 9,
            "number_of_episodes": 201,
            "genres": [],
            "origin_country": ["US"],
        }
        tmdb_ext = {"tvdb_id": 73244, "imdb_id": "tt0386676"}

        resolver._tmdb_instance = MagicMock()
        resolver._tmdb_instance.search_tv.return_value = tmdb_search
        resolver._tmdb_instance.get_tv_details.return_value = tmdb_details
        resolver._tmdb_instance.get_tv_external_ids.return_value = tmdb_ext

        result = resolver.resolve_series("The Office", year=2005)
        assert result["title"] == "The Office"
        assert result["tmdb_id"] == 2316
        assert result["tvdb_id"] == 73244
        assert result["metadata_source"] == "tmdb"
        resolver._set_cached.assert_called_once()

    def test_tvdb_fallback_when_tmdb_fails(self, resolver):
        self._patch_cache(resolver)
        resolver._tmdb_instance = MagicMock()
        resolver._tmdb_instance.search_tv.return_value = None

        resolver._tvdb_instance = MagicMock()
        resolver._tvdb_instance.search_series.return_value = {
            "name": "Lost",
            "id": "73739",
            "year": "2004",
            "image_url": "https://tvdb.com/lost.jpg",
        }

        result = resolver.resolve_series("Lost", year=2004)
        assert result["title"] == "Lost"
        assert result["tvdb_id"] == 73739
        assert result["metadata_source"] == "tvdb"

    def test_filename_fallback(self, resolver_no_keys):
        resolver_no_keys._get_cached = MagicMock(return_value=None)
        resolver_no_keys._set_cached = MagicMock()
        resolver_no_keys._anilist_instance = MagicMock()
        resolver_no_keys._anilist_instance.search_anime.return_value = None

        result = resolver_no_keys.resolve_series("Unknown Show", year=2024, is_anime=True)
        assert result["metadata_source"] == "filename"
        assert result["title"] == "Unknown Show"
        assert result["year"] == 2024
        assert result["is_anime"] is True

    def test_anime_anilist_with_tmdb_crossref(self, resolver):
        self._patch_cache(resolver)

        # AniList returns a hit
        resolver._anilist_instance = MagicMock()
        resolver._anilist_instance.search_anime.return_value = {
            "id": 101,
            "title": {"english": "Attack on Titan", "romaji": "Shingeki no Kyojin"},
            "seasonYear": 2013,
            "episodes": 25,
            "coverImage": {"large": "https://img.anilist.co/aot.jpg"},
        }

        # TMDB provides cross-reference IDs
        resolver._tmdb_instance = MagicMock()
        resolver._tmdb_instance.search_tv.return_value = {
            "name": "Attack on Titan",
            "id": 1429,
            "first_air_date": "2013-04-07",
        }
        resolver._tmdb_instance.get_tv_details.return_value = {
            "number_of_seasons": 4,
            "number_of_episodes": 87,
            "genres": [{"name": "Animation"}],
            "origin_country": ["JP"],
        }
        resolver._tmdb_instance.get_tv_external_ids.return_value = {
            "tvdb_id": 267440,
            "imdb_id": "tt2560140",
        }

        result = resolver.resolve_series("Attack on Titan", is_anime=True)
        assert result["metadata_source"] == "anilist"
        assert result["anilist_id"] == 101
        assert result["tmdb_id"] == 1429
        assert result["tvdb_id"] == 267440
        assert result["imdb_id"] == "tt2560140"

    def test_anime_anilist_without_tmdb(self, resolver_tmdb_only):
        resolver_tmdb_only._get_cached = MagicMock(return_value=None)
        resolver_tmdb_only._set_cached = MagicMock()

        resolver_tmdb_only._anilist_instance = MagicMock()
        resolver_tmdb_only._anilist_instance.search_anime.return_value = {
            "id": 200,
            "title": {"english": "Demon Slayer"},
            "seasonYear": 2019,
            "episodes": 26,
            "coverImage": {"large": "https://img.anilist.co/ds.jpg"},
        }

        # TMDB search returns None
        resolver_tmdb_only._tmdb_instance = MagicMock()
        resolver_tmdb_only._tmdb_instance.search_tv.return_value = None
        resolver_tmdb_only._tmdb_instance.get_tv_details.return_value = None
        resolver_tmdb_only._tmdb_instance.get_tv_external_ids.return_value = None

        result = resolver_tmdb_only.resolve_series("Demon Slayer", is_anime=True)
        assert result["metadata_source"] == "anilist"
        assert result["anilist_id"] == 200
        # No cross-ref since TMDB failed
        assert result["tmdb_id"] is None

    def test_anime_anilist_miss_falls_to_tmdb(self, resolver):
        self._patch_cache(resolver)

        # AniList returns nothing
        resolver._anilist_instance = MagicMock()
        resolver._anilist_instance.search_anime.return_value = None

        # TMDB picks it up
        resolver._tmdb_instance = MagicMock()
        resolver._tmdb_instance.search_tv.return_value = {
            "name": "Anime Show",
            "id": 555,
            "first_air_date": "2020-01-01",
        }
        resolver._tmdb_instance.get_tv_details.return_value = None
        resolver._tmdb_instance.get_tv_external_ids.return_value = None

        result = resolver.resolve_series("Anime Show", is_anime=True)
        assert result["metadata_source"] == "tmdb"
        assert result["tmdb_id"] == 555

    def test_filename_fallback_no_keys(self, resolver_no_keys):
        resolver_no_keys._get_cached = MagicMock(return_value=None)
        resolver_no_keys._set_cached = MagicMock()

        result = resolver_no_keys.resolve_series("Some Show")
        assert result["metadata_source"] == "filename"
        assert result["title"] == "Some Show"
        assert result["year"] is None
        assert result["is_anime"] is False

    def test_cache_key_format(self, resolver):
        self._patch_cache(resolver)
        resolver._tmdb_instance = MagicMock()
        resolver._tmdb_instance.search_tv.return_value = None
        resolver._tvdb_instance = MagicMock()
        resolver._tvdb_instance.search_series.return_value = None

        resolver.resolve_series("Test Show", year=2020)
        resolver._get_cached.assert_called_once_with("series:test show:2020")

    def test_cache_key_no_year(self, resolver):
        self._patch_cache(resolver)
        resolver._tmdb_instance = MagicMock()
        resolver._tmdb_instance.search_tv.return_value = None
        resolver._tvdb_instance = MagicMock()
        resolver._tvdb_instance.search_series.return_value = None

        resolver.resolve_series("Test Show")
        resolver._get_cached.assert_called_once_with("series:test show:")


# ---------------------------------------------------------------------------
# resolve_movie
# ---------------------------------------------------------------------------


class TestResolveMovie:
    def _patch_cache(self, resolver, cached_val=None):
        resolver._get_cached = MagicMock(return_value=cached_val)
        resolver._set_cached = MagicMock()

    def test_cache_hit(self, resolver):
        cached = {"title": "Cached Movie", "metadata_source": "tmdb"}
        self._patch_cache(resolver, cached)
        result = resolver.resolve_movie("Test Movie", year=2020)
        assert result == cached
        resolver._set_cached.assert_not_called()

    def test_tmdb_primary(self, resolver):
        self._patch_cache(resolver)

        resolver._tmdb_instance = MagicMock()
        resolver._tmdb_instance.search_movie.return_value = {
            "title": "Inception",
            "id": 27205,
            "poster_path": "/inc.jpg",
            "release_date": "2010-07-16",
        }
        resolver._tmdb_instance.get_movie_details.return_value = {"runtime": 148}
        resolver._tmdb_instance.get_movie_external_ids.return_value = {"imdb_id": "tt1375666"}

        result = resolver.resolve_movie("Inception", year=2010)
        assert result["title"] == "Inception"
        assert result["tmdb_id"] == 27205
        assert result["imdb_id"] == "tt1375666"
        assert result["metadata_source"] == "tmdb"
        resolver._set_cached.assert_called_once()

    def test_tmdb_no_results(self, resolver):
        self._patch_cache(resolver)
        resolver._tmdb_instance = MagicMock()
        resolver._tmdb_instance.search_movie.return_value = None

        result = resolver.resolve_movie("Unknown Movie", year=2024)
        assert result["metadata_source"] == "filename"
        assert result["title"] == "Unknown Movie"
        assert result["year"] == 2024

    def test_filename_fallback_no_key(self, resolver_no_keys):
        resolver_no_keys._get_cached = MagicMock(return_value=None)
        resolver_no_keys._set_cached = MagicMock()

        result = resolver_no_keys.resolve_movie("Some Movie")
        assert result["metadata_source"] == "filename"
        assert result["tmdb_id"] is None
        assert result["imdb_id"] is None

    def test_cache_key_format(self, resolver):
        self._patch_cache(resolver)
        resolver._tmdb_instance = MagicMock()
        resolver._tmdb_instance.search_movie.return_value = None

        resolver.resolve_movie("Test Movie", year=2020)
        resolver._get_cached.assert_called_once_with("movie:test movie:2020")

    def test_tmdb_search_hit_but_no_id(self, resolver):
        """search_movie returns a result without 'id' -> details/ext not fetched."""
        self._patch_cache(resolver)
        resolver._tmdb_instance = MagicMock()
        resolver._tmdb_instance.search_movie.return_value = {
            "title": "NoId",
            "poster_path": None,
            "release_date": "2020-01-01",
        }
        resolver._tmdb_instance.get_movie_details.return_value = None
        resolver._tmdb_instance.get_movie_external_ids.return_value = None

        result = resolver.resolve_movie("NoId", year=2020)
        assert result["title"] == "NoId"
        assert result["tmdb_id"] is None
        # get_movie_details should NOT be called since id is None/missing
        resolver._tmdb_instance.get_movie_details.assert_not_called()


# ---------------------------------------------------------------------------
# _try_* helper methods
# ---------------------------------------------------------------------------


class TestTryHelpers:
    def test_try_anilist_series_hit(self, resolver):
        resolver._anilist_instance = MagicMock()
        resolver._anilist_instance.search_anime.return_value = {
            "id": 50,
            "title": {"english": "Test"},
            "seasonYear": 2020,
            "coverImage": {"large": None},
        }
        result = resolver._try_anilist_series("Test")
        assert result is not None
        assert result["anilist_id"] == 50

    def test_try_anilist_series_miss(self, resolver):
        resolver._anilist_instance = MagicMock()
        resolver._anilist_instance.search_anime.return_value = None
        assert resolver._try_anilist_series("NoMatch") is None

    def test_try_tmdb_series_no_client(self, resolver_no_keys):
        assert resolver_no_keys._try_tmdb_series("Test") is None

    def test_try_tmdb_series_no_results(self, resolver):
        resolver._tmdb_instance = MagicMock()
        resolver._tmdb_instance.search_tv.return_value = None
        assert resolver._try_tmdb_series("NoMatch") is None

    def test_try_tmdb_series_with_results(self, resolver):
        resolver._tmdb_instance = MagicMock()
        resolver._tmdb_instance.search_tv.return_value = {
            "name": "Show",
            "id": 99,
            "first_air_date": "2021-01-01",
        }
        resolver._tmdb_instance.get_tv_details.return_value = None
        resolver._tmdb_instance.get_tv_external_ids.return_value = None
        result = resolver._try_tmdb_series("Show")
        assert result["tmdb_id"] == 99

    def test_try_tvdb_series_no_client(self, resolver_no_keys):
        assert resolver_no_keys._try_tvdb_series("Test") is None

    def test_try_tvdb_series_no_results(self, resolver):
        resolver._tvdb_instance = MagicMock()
        resolver._tvdb_instance.search_series.return_value = None
        assert resolver._try_tvdb_series("NoMatch") is None

    def test_try_tvdb_series_with_results(self, resolver):
        resolver._tvdb_instance = MagicMock()
        resolver._tvdb_instance.search_series.return_value = {
            "name": "Found",
            "id": 42,
            "year": 2019,
        }
        result = resolver._try_tvdb_series("Found")
        assert result["tvdb_id"] == 42

    def test_try_tmdb_movie_no_client(self, resolver_no_keys):
        assert resolver_no_keys._try_tmdb_movie("Test") is None

    def test_try_tmdb_movie_no_results(self, resolver):
        resolver._tmdb_instance = MagicMock()
        resolver._tmdb_instance.search_movie.return_value = None
        assert resolver._try_tmdb_movie("NoMatch") is None

    def test_try_tmdb_movie_with_results(self, resolver):
        resolver._tmdb_instance = MagicMock()
        resolver._tmdb_instance.search_movie.return_value = {
            "title": "Film",
            "id": 88,
            "release_date": "2020-06-15",
        }
        resolver._tmdb_instance.get_movie_details.return_value = None
        resolver._tmdb_instance.get_movie_external_ids.return_value = None
        result = resolver._try_tmdb_movie("Film")
        assert result["tmdb_id"] == 88
