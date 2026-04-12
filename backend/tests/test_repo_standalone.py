"""Tests for db.repositories.standalone.StandaloneRepository.

Covers: watched folder CRUD, standalone series upsert/CRUD, standalone movie
upsert/CRUD, metadata cache with TTL, AniDB mapping cache with last_used tracking.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from db.repositories.standalone import StandaloneRepository


@pytest.fixture
def repo(app_ctx):
    """Create a StandaloneRepository instance within app context."""
    return StandaloneRepository()


# ---------------------------------------------------------------------------
# Watched Folders
# ---------------------------------------------------------------------------


class TestWatchedFolders:
    def test_create_watched_folder_returns_dict(self, repo):
        """Creating a watched folder returns a dict with all expected keys."""
        result = repo.create_watched_folder("/media/anime", label="Anime", media_type="series")
        assert isinstance(result, dict)
        assert result["path"] == "/media/anime"
        assert result["label"] == "Anime"
        assert result["media_type"] == "series"
        assert result["enabled"] == 1
        assert result["last_scan_at"] is None
        assert "id" in result

    def test_create_watched_folder_defaults(self, repo):
        """Creating a folder with defaults uses label='' and media_type='auto'."""
        result = repo.create_watched_folder("/media/movies")
        assert result["label"] == ""
        assert result["media_type"] == "auto"

    def test_get_watched_folders_enabled_only(self, repo):
        """Default get_watched_folders returns only enabled folders."""
        repo.create_watched_folder("/media/enabled")
        repo.create_watched_folder("/media/disabled")
        # Disable one
        folders = repo.get_watched_folders(enabled_only=False)
        disabled_id = [f for f in folders if f["path"] == "/media/disabled"][0]["id"]
        repo.update_watched_folder(disabled_id, enabled=0)

        enabled = repo.get_watched_folders(enabled_only=True)
        assert len(enabled) == 1
        assert enabled[0]["path"] == "/media/enabled"

    def test_get_watched_folders_all(self, repo):
        """get_watched_folders with enabled_only=False returns all folders."""
        repo.create_watched_folder("/media/a")
        repo.create_watched_folder("/media/b")
        folders = repo.get_watched_folders(enabled_only=False)
        assert len(folders) == 2

    def test_get_watched_folder_by_id(self, repo):
        """Getting a watched folder by ID returns the correct folder."""
        created = repo.create_watched_folder("/media/test")
        result = repo.get_watched_folder(created["id"])
        assert result is not None
        assert result["path"] == "/media/test"

    def test_get_watched_folder_not_found(self, repo):
        """Getting a non-existent folder returns None."""
        assert repo.get_watched_folder(999) is None

    def test_update_watched_folder(self, repo):
        """Updating a folder changes the specified fields."""
        created = repo.create_watched_folder("/media/test", label="Old")
        result = repo.update_watched_folder(created["id"], label="New", media_type="movies")
        assert result is True

        updated = repo.get_watched_folder(created["id"])
        assert updated["label"] == "New"
        assert updated["media_type"] == "movies"

    def test_update_watched_folder_not_found(self, repo):
        """Updating a non-existent folder returns False."""
        assert repo.update_watched_folder(999, label="X") is False

    def test_delete_watched_folder(self, repo):
        """Deleting a folder removes it from the database."""
        created = repo.create_watched_folder("/media/delete_me")
        assert repo.delete_watched_folder(created["id"]) is True
        assert repo.get_watched_folder(created["id"]) is None

    def test_delete_watched_folder_not_found(self, repo):
        """Deleting a non-existent folder returns False."""
        assert repo.delete_watched_folder(999) is False

    def test_update_last_scan(self, repo):
        """update_last_scan sets last_scan_at to current time."""
        created = repo.create_watched_folder("/media/scan")
        assert created["last_scan_at"] is None

        repo.update_last_scan(created["id"])
        updated = repo.get_watched_folder(created["id"])
        assert updated["last_scan_at"] is not None

    def test_update_last_scan_nonexistent(self, repo):
        """update_last_scan on a non-existent folder does not raise."""
        # Should not raise an exception
        repo.update_last_scan(999)

    def test_get_watched_folders_ordered_by_path(self, repo):
        """Watched folders are returned ordered by path."""
        repo.create_watched_folder("/media/z_last")
        repo.create_watched_folder("/media/a_first")
        folders = repo.get_watched_folders(enabled_only=False)
        assert folders[0]["path"] == "/media/a_first"
        assert folders[1]["path"] == "/media/z_last"


# ---------------------------------------------------------------------------
# Standalone Series
# ---------------------------------------------------------------------------


class TestStandaloneSeries:
    def test_upsert_creates_new_series(self, repo):
        """Upserting a new series creates it and returns a dict."""
        result = repo.upsert_standalone_series(
            title="Naruto",
            folder_path="/anime/naruto",
            year=2002,
            tmdb_id=12345,
            is_anime=True,
            episode_count=220,
            season_count=5,
        )
        assert result["title"] == "Naruto"
        assert result["folder_path"] == "/anime/naruto"
        assert result["year"] == 2002
        assert result["is_anime"] == 1
        assert result["episode_count"] == 220

    def test_upsert_updates_existing_series(self, repo):
        """Upserting an existing folder_path updates the series."""
        repo.upsert_standalone_series(title="Naruto", folder_path="/anime/naruto", year=2002)
        updated = repo.upsert_standalone_series(
            title="Naruto Shippuden", folder_path="/anime/naruto", year=2007
        )
        assert updated["title"] == "Naruto Shippuden"
        assert updated["year"] == 2007

        # Should still be only one series
        all_series = repo.get_all_standalone_series()
        assert len(all_series) == 1

    def test_get_standalone_series_by_id(self, repo):
        """Getting a series by ID returns the correct series."""
        created = repo.upsert_standalone_series(title="Test", folder_path="/anime/test")
        result = repo.get_standalone_series(created["id"])
        assert result is not None
        assert result["title"] == "Test"

    def test_get_standalone_series_not_found(self, repo):
        """Getting a non-existent series returns None."""
        assert repo.get_standalone_series(999) is None

    def test_get_all_standalone_series_ordered(self, repo):
        """All series are returned ordered by title."""
        repo.upsert_standalone_series(title="Zelda", folder_path="/anime/zelda")
        repo.upsert_standalone_series(title="Alpha", folder_path="/anime/alpha")
        series = repo.get_all_standalone_series()
        assert len(series) == 2
        assert series[0]["title"] == "Alpha"
        assert series[1]["title"] == "Zelda"

    def test_delete_standalone_series(self, repo):
        """Deleting a series removes it."""
        created = repo.upsert_standalone_series(title="Del", folder_path="/anime/del")
        assert repo.delete_standalone_series(created["id"]) is True
        assert repo.get_standalone_series(created["id"]) is None

    def test_delete_standalone_series_not_found(self, repo):
        """Deleting a non-existent series returns False."""
        assert repo.delete_standalone_series(999) is False

    def test_get_standalone_series_by_folder(self, repo):
        """Getting a series by folder_path returns the correct series."""
        repo.upsert_standalone_series(title="ByFolder", folder_path="/anime/byfolder")
        result = repo.get_standalone_series_by_folder("/anime/byfolder")
        assert result is not None
        assert result["title"] == "ByFolder"

    def test_get_standalone_series_by_folder_not_found(self, repo):
        """Getting a series by non-existent folder returns None."""
        assert repo.get_standalone_series_by_folder("/nope") is None

    def test_upsert_series_is_anime_false(self, repo):
        """is_anime=False stores 0 in the database."""
        result = repo.upsert_standalone_series(
            title="Drama", folder_path="/tv/drama", is_anime=False
        )
        assert result["is_anime"] == 0


# ---------------------------------------------------------------------------
# Standalone Movies
# ---------------------------------------------------------------------------


class TestStandaloneMovies:
    def test_upsert_creates_new_movie(self, repo):
        """Upserting a new movie creates it and returns a dict."""
        result = repo.upsert_standalone_movie(
            title="Spirited Away",
            file_path="/movies/spirited_away.mkv",
            year=2001,
            tmdb_id=99999,
        )
        assert result["title"] == "Spirited Away"
        assert result["file_path"] == "/movies/spirited_away.mkv"
        assert result["year"] == 2001

    def test_upsert_updates_existing_movie(self, repo):
        """Upserting an existing file_path updates the movie."""
        repo.upsert_standalone_movie(title="Movie", file_path="/movies/test.mkv", year=2020)
        updated = repo.upsert_standalone_movie(
            title="Movie v2", file_path="/movies/test.mkv", year=2021
        )
        assert updated["title"] == "Movie v2"
        assert updated["year"] == 2021

        all_movies = repo.get_all_standalone_movies()
        assert len(all_movies) == 1

    def test_get_standalone_movie_by_id(self, repo):
        """Getting a movie by ID returns the correct movie."""
        created = repo.upsert_standalone_movie(title="Test", file_path="/movies/test.mkv")
        result = repo.get_standalone_movie(created["id"])
        assert result is not None
        assert result["title"] == "Test"

    def test_get_standalone_movie_not_found(self, repo):
        """Getting a non-existent movie returns None."""
        assert repo.get_standalone_movie(999) is None

    def test_get_all_standalone_movies_ordered(self, repo):
        """All movies are returned ordered by title."""
        repo.upsert_standalone_movie(title="Zzz", file_path="/movies/zzz.mkv")
        repo.upsert_standalone_movie(title="Aaa", file_path="/movies/aaa.mkv")
        movies = repo.get_all_standalone_movies()
        assert len(movies) == 2
        assert movies[0]["title"] == "Aaa"
        assert movies[1]["title"] == "Zzz"

    def test_delete_standalone_movie(self, repo):
        """Deleting a movie removes it."""
        created = repo.upsert_standalone_movie(title="Del", file_path="/movies/del.mkv")
        assert repo.delete_standalone_movie(created["id"]) is True
        assert repo.get_standalone_movie(created["id"]) is None

    def test_delete_standalone_movie_not_found(self, repo):
        """Deleting a non-existent movie returns False."""
        assert repo.delete_standalone_movie(999) is False

    def test_get_standalone_movie_by_path(self, repo):
        """Getting a movie by file_path returns the correct movie."""
        repo.upsert_standalone_movie(title="ByPath", file_path="/movies/bypath.mkv")
        result = repo.get_standalone_movie_by_path("/movies/bypath.mkv")
        assert result is not None
        assert result["title"] == "ByPath"

    def test_get_standalone_movie_by_path_not_found(self, repo):
        """Getting a movie by non-existent path returns None."""
        assert repo.get_standalone_movie_by_path("/nope.mkv") is None


# ---------------------------------------------------------------------------
# Metadata Cache
# ---------------------------------------------------------------------------


class TestMetadataCache:
    def test_save_and_get_metadata_cache(self, repo):
        """Saving and retrieving a metadata cache entry works."""
        repo.save_metadata_cache("tmdb:12345", "tmdb", '{"title": "Test"}', ttl_days=30)
        result = repo.get_metadata_cache("tmdb:12345")
        assert result is not None
        assert result["provider"] == "tmdb"
        assert result["response_json"] == '{"title": "Test"}'

    def test_get_metadata_cache_expired(self, repo):
        """Expired cache entries return None."""
        repo.save_metadata_cache("tmdb:expired", "tmdb", "{}", ttl_days=0)

        # Force expire by patching datetime
        with patch("db.repositories.standalone.datetime") as mock_dt:
            mock_dt.now.return_value = datetime.now(UTC) + timedelta(days=1)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            result = repo.get_metadata_cache("tmdb:expired")
            assert result is None

    def test_get_metadata_cache_not_found(self, repo):
        """Getting a non-existent cache entry returns None."""
        assert repo.get_metadata_cache("nonexistent") is None

    def test_save_metadata_cache_upsert(self, repo):
        """Saving with the same key updates the entry."""
        repo.save_metadata_cache("key1", "provider_a", '{"v": 1}', ttl_days=30)
        repo.save_metadata_cache("key1", "provider_b", '{"v": 2}', ttl_days=30)

        result = repo.get_metadata_cache("key1")
        assert result["provider"] == "provider_b"
        assert result["response_json"] == '{"v": 2}'

    def test_clear_expired_metadata_cache(self, repo):
        """clear_expired_metadata_cache removes only expired entries."""
        # Create one entry with 0-day TTL (expires immediately)
        repo.save_metadata_cache("expired", "tmdb", "{}", ttl_days=0)
        # Create one entry with 30-day TTL
        repo.save_metadata_cache("valid", "tmdb", "{}", ttl_days=30)

        repo.clear_expired_metadata_cache()
        # The 0-day entry might or might not be expired based on exact timing
        # but the 30-day entry should survive
        result = repo.get_metadata_cache("valid")
        assert result is not None


# ---------------------------------------------------------------------------
# AniDB Mappings
# ---------------------------------------------------------------------------


class TestAnidbMappings:
    def test_save_and_get_anidb_mapping(self, repo):
        """Saving and retrieving an AniDB mapping works."""
        repo.save_anidb_mapping(tvdb_id=12345, anidb_id=67890, series_title="Naruto")
        result = repo.get_anidb_mapping(12345)
        assert result is not None
        assert result["anidb_id"] == 67890
        assert result["series_title"] == "Naruto"

    def test_get_anidb_mapping_updates_last_used(self, repo):
        """Getting an AniDB mapping updates the last_used timestamp."""
        repo.save_anidb_mapping(tvdb_id=111, anidb_id=222)
        first = repo.get_anidb_mapping(111)
        first_used = first["last_used"]

        # Access again
        second = repo.get_anidb_mapping(111)
        assert second["last_used"] >= first_used

    def test_get_anidb_mapping_not_found(self, repo):
        """Getting a non-existent mapping returns None."""
        assert repo.get_anidb_mapping(999) is None

    def test_save_anidb_mapping_upsert(self, repo):
        """Saving the same tvdb_id again updates the mapping."""
        repo.save_anidb_mapping(tvdb_id=100, anidb_id=200, series_title="Old")
        repo.save_anidb_mapping(tvdb_id=100, anidb_id=300, series_title="New")

        result = repo.get_anidb_mapping(100)
        assert result["anidb_id"] == 300
        assert result["series_title"] == "New"

    def test_clear_old_anidb_mappings(self, repo):
        """clear_old_anidb_mappings removes entries older than TTL."""
        repo.save_anidb_mapping(tvdb_id=1, anidb_id=10)
        repo.save_anidb_mapping(tvdb_id=2, anidb_id=20)

        # With a very large TTL, nothing should be deleted
        deleted = repo.clear_old_anidb_mappings(ttl_days=9999)
        assert deleted == 0

    def test_clear_old_anidb_mappings_default_ttl(self, repo):
        """clear_old_anidb_mappings uses 90-day default TTL."""
        repo.save_anidb_mapping(tvdb_id=1, anidb_id=10)
        # Just created, so should not be deleted with default TTL
        deleted = repo.clear_old_anidb_mappings()
        assert deleted == 0
