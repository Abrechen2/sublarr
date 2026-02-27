"""Standalone mode repository using SQLAlchemy ORM.

Replaces the raw sqlite3 queries in db/standalone.py with SQLAlchemy ORM operations.
CRUD for watched_folders, standalone_series, standalone_movies, metadata_cache,
and anidb_mappings tables. Return types match the existing functions exactly.
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import delete, select

from db.models.standalone import (
    AnidbMapping,
    MetadataCache,
    StandaloneMovie,
    StandaloneSeries,
    WatchedFolder,
)
from db.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class StandaloneRepository(BaseRepository):
    """Repository for standalone mode table operations."""

    # ---- Watched Folders ---------------------------------------------------------

    def create_watched_folder(self, path: str, label: str = "",
                               media_type: str = "auto") -> dict:
        """Create a new watched folder.

        Returns:
            Dict representing the created folder.
        """
        now = self._now()
        folder = WatchedFolder(
            path=path,
            label=label,
            media_type=media_type,
            enabled=1,
            last_scan_at="",
            created_at=now,
            updated_at=now,
        )
        self.session.add(folder)
        self._commit()
        return self._row_to_folder(folder)

    def get_watched_folders(self, enabled_only: bool = True) -> list:
        """Get all watched folders, optionally filtered to enabled-only.

        Returns:
            List of folder dicts.
        """
        stmt = select(WatchedFolder).order_by(WatchedFolder.path)
        if enabled_only:
            stmt = stmt.where(WatchedFolder.enabled == 1)
        entries = self.session.execute(stmt).scalars().all()
        return [self._row_to_folder(e) for e in entries]

    def get_watched_folder(self, folder_id: int) -> dict | None:
        """Get a single watched folder by ID."""
        entry = self.session.get(WatchedFolder, folder_id)
        if not entry:
            return None
        return self._row_to_folder(entry)

    def update_watched_folder(self, folder_id: int, **kwargs) -> bool:
        """Update a watched folder with arbitrary column values. Returns True if found."""
        entry = self.session.get(WatchedFolder, folder_id)
        if not entry:
            return False

        for key, value in kwargs.items():
            if hasattr(entry, key):
                setattr(entry, key, value)
        entry.updated_at = self._now()
        self._commit()
        return True

    def delete_watched_folder(self, folder_id: int) -> bool:
        """Delete a watched folder by ID. Returns True if deleted."""
        entry = self.session.get(WatchedFolder, folder_id)
        if not entry:
            return False
        self.session.delete(entry)
        self._commit()
        return True

    def update_last_scan(self, folder_id: int):
        """Update the last_scan_at timestamp for a folder."""
        entry = self.session.get(WatchedFolder, folder_id)
        if entry:
            now = self._now()
            entry.last_scan_at = now
            entry.updated_at = now
            self._commit()

    # ---- Standalone Series -------------------------------------------------------

    def upsert_standalone_series(self, title: str, folder_path: str,
                                  year: int = None, tmdb_id: int = None,
                                  tvdb_id: int = None, anilist_id: int = None,
                                  imdb_id: str = "", poster_url: str = "",
                                  is_anime: bool = False, episode_count: int = 0,
                                  season_count: int = 0,
                                  metadata_source: str = "") -> dict:
        """Insert or update a standalone series by folder_path.

        Returns:
            Dict representing the series.
        """
        now = self._now()
        is_anime_int = 1 if is_anime else 0

        # Check for existing series by folder_path
        stmt = select(StandaloneSeries).where(
            StandaloneSeries.folder_path == folder_path
        )
        existing = self.session.execute(stmt).scalars().first()

        if existing:
            existing.title = title
            existing.year = year
            existing.tmdb_id = tmdb_id
            existing.tvdb_id = tvdb_id
            existing.anilist_id = anilist_id
            existing.imdb_id = imdb_id
            existing.poster_url = poster_url
            existing.is_anime = is_anime_int
            existing.episode_count = episode_count
            existing.season_count = season_count
            existing.metadata_source = metadata_source
            existing.updated_at = now
            self._commit()
            return self._row_to_series(existing)
        else:
            series = StandaloneSeries(
                title=title,
                folder_path=folder_path,
                year=year,
                tmdb_id=tmdb_id,
                tvdb_id=tvdb_id,
                anilist_id=anilist_id,
                imdb_id=imdb_id,
                poster_url=poster_url,
                is_anime=is_anime_int,
                episode_count=episode_count,
                season_count=season_count,
                metadata_source=metadata_source,
                created_at=now,
                updated_at=now,
            )
            self.session.add(series)
            self._commit()
            return self._row_to_series(series)

    def get_standalone_series(self, series_id: int) -> dict | None:
        """Get a single standalone series by ID."""
        entry = self.session.get(StandaloneSeries, series_id)
        if not entry:
            return None
        return self._row_to_series(entry)

    def get_all_standalone_series(self) -> list:
        """Get all standalone series ordered by title."""
        stmt = select(StandaloneSeries).order_by(StandaloneSeries.title)
        entries = self.session.execute(stmt).scalars().all()
        return [self._row_to_series(e) for e in entries]

    def delete_standalone_series(self, series_id: int) -> bool:
        """Delete a standalone series by ID. Returns True if deleted."""
        entry = self.session.get(StandaloneSeries, series_id)
        if not entry:
            return False
        self.session.delete(entry)
        self._commit()
        return True

    def get_standalone_series_by_folder(self, folder_path: str) -> dict | None:
        """Get a standalone series by its folder path."""
        stmt = select(StandaloneSeries).where(
            StandaloneSeries.folder_path == folder_path
        )
        entry = self.session.execute(stmt).scalars().first()
        if not entry:
            return None
        return self._row_to_series(entry)

    # ---- Standalone Movies -------------------------------------------------------

    def upsert_standalone_movie(self, title: str, file_path: str,
                                 year: int = None, tmdb_id: int = None,
                                 imdb_id: str = "", poster_url: str = "",
                                 metadata_source: str = "") -> dict:
        """Insert or update a standalone movie by file_path.

        Returns:
            Dict representing the movie.
        """
        now = self._now()

        # Check for existing movie by file_path
        stmt = select(StandaloneMovie).where(
            StandaloneMovie.file_path == file_path
        )
        existing = self.session.execute(stmt).scalars().first()

        if existing:
            existing.title = title
            existing.year = year
            existing.tmdb_id = tmdb_id
            existing.imdb_id = imdb_id
            existing.poster_url = poster_url
            existing.metadata_source = metadata_source
            existing.updated_at = now
            self._commit()
            return self._row_to_movie(existing)
        else:
            movie = StandaloneMovie(
                title=title,
                file_path=file_path,
                year=year,
                tmdb_id=tmdb_id,
                imdb_id=imdb_id,
                poster_url=poster_url,
                metadata_source=metadata_source,
                created_at=now,
                updated_at=now,
            )
            self.session.add(movie)
            self._commit()
            return self._row_to_movie(movie)

    def get_standalone_movie(self, movie_id: int) -> dict | None:
        """Get a single standalone movie by ID."""
        entry = self.session.get(StandaloneMovie, movie_id)
        if not entry:
            return None
        return self._row_to_movie(entry)

    def get_all_standalone_movies(self) -> list:
        """Get all standalone movies ordered by title."""
        stmt = select(StandaloneMovie).order_by(StandaloneMovie.title)
        entries = self.session.execute(stmt).scalars().all()
        return [self._row_to_movie(e) for e in entries]

    def delete_standalone_movie(self, movie_id: int) -> bool:
        """Delete a standalone movie by ID. Returns True if deleted."""
        entry = self.session.get(StandaloneMovie, movie_id)
        if not entry:
            return False
        self.session.delete(entry)
        self._commit()
        return True

    def get_standalone_movie_by_path(self, file_path: str) -> dict | None:
        """Get a standalone movie by its file path."""
        stmt = select(StandaloneMovie).where(
            StandaloneMovie.file_path == file_path
        )
        entry = self.session.execute(stmt).scalars().first()
        if not entry:
            return None
        return self._row_to_movie(entry)

    # ---- Metadata Cache ----------------------------------------------------------

    def get_metadata_cache(self, cache_key: str) -> dict | None:
        """Get a cached metadata entry if not expired."""
        now = datetime.utcnow().isoformat()
        entry = self.session.get(MetadataCache, cache_key)
        if not entry:
            return None
        if entry.expires_at <= now:
            return None
        return self._to_dict(entry)

    def save_metadata_cache(self, cache_key: str, provider: str,
                             response_json: str, ttl_days: int = 30):
        """Insert or replace a metadata cache entry with TTL."""
        now = datetime.utcnow()
        cached_at = now.isoformat()
        expires_at = (now + timedelta(days=ttl_days)).isoformat()

        existing = self.session.get(MetadataCache, cache_key)
        if existing:
            existing.provider = provider
            existing.response_json = response_json
            existing.cached_at = cached_at
            existing.expires_at = expires_at
        else:
            entry = MetadataCache(
                cache_key=cache_key,
                provider=provider,
                response_json=response_json,
                cached_at=cached_at,
                expires_at=expires_at,
            )
            self.session.add(entry)
        self._commit()

    def clear_expired_metadata_cache(self) -> int:
        """Delete all expired metadata cache entries. Returns count deleted."""
        now = datetime.utcnow().isoformat()
        result = self.session.execute(
            delete(MetadataCache).where(MetadataCache.expires_at <= now)
        )
        self._commit()
        return result.rowcount

    # ---- AniDB Mappings ----------------------------------------------------------

    def get_anidb_mapping(self, tvdb_id: int) -> dict | None:
        """Get cached AniDB ID for a TVDB ID. Updates last_used on read."""
        entry = self.session.get(AnidbMapping, tvdb_id)
        if not entry:
            return None
        # Update last_used on access
        entry.last_used = self._now()
        self._commit()
        return self._to_dict(entry)

    def save_anidb_mapping(self, tvdb_id: int, anidb_id: int,
                            series_title: str = ""):
        """Save or update an AniDB mapping in the cache."""
        now = self._now()
        existing = self.session.get(AnidbMapping, tvdb_id)
        if existing:
            existing.anidb_id = anidb_id
            existing.series_title = series_title
            existing.last_used = now
        else:
            entry = AnidbMapping(
                tvdb_id=tvdb_id,
                anidb_id=anidb_id,
                series_title=series_title,
                created_at=now,
                last_used=now,
            )
            self.session.add(entry)
        self._commit()

    def clear_old_anidb_mappings(self, ttl_days: int = 90) -> int:
        """Remove AniDB mappings older than specified days. Returns count deleted."""
        cutoff = (datetime.utcnow() - timedelta(days=ttl_days)).isoformat()
        result = self.session.execute(
            delete(AnidbMapping).where(AnidbMapping.last_used < cutoff)
        )
        self._commit()
        return result.rowcount

    # ---- Helpers -----------------------------------------------------------------

    def _row_to_folder(self, entry: WatchedFolder) -> dict:
        """Convert a WatchedFolder model to a dict."""
        return self._to_dict(entry)

    def _row_to_series(self, entry: StandaloneSeries) -> dict:
        """Convert a StandaloneSeries model to a dict."""
        return self._to_dict(entry)

    def _row_to_movie(self, entry: StandaloneMovie) -> dict:
        """Convert a StandaloneMovie model to a dict."""
        return self._to_dict(entry)
