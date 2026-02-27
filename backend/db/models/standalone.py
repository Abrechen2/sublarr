"""Standalone mode ORM models: watched folders, series, movies, metadata cache, AniDB mappings.

All column types and defaults match the existing SCHEMA DDL in db/__init__.py exactly.
"""


from sqlalchemy import Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from extensions import db


class WatchedFolder(db.Model):
    """User-configured folder to watch for media files (standalone mode)."""

    __tablename__ = "watched_folders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    path: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    label: Mapped[str | None] = mapped_column(Text, default="")
    media_type: Mapped[str | None] = mapped_column(Text, default="auto")
    enabled: Mapped[int | None] = mapped_column(Integer, default=1)
    last_scan_at: Mapped[str | None] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


class StandaloneSeries(db.Model):
    """Series discovered in standalone mode (not from Sonarr)."""

    __tablename__ = "standalone_series"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    folder_path: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    tmdb_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tvdb_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    anilist_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    imdb_id: Mapped[str | None] = mapped_column(Text, default="")
    poster_url: Mapped[str | None] = mapped_column(Text, default="")
    is_anime: Mapped[int | None] = mapped_column(Integer, default=0)
    episode_count: Mapped[int | None] = mapped_column(Integer, default=0)
    season_count: Mapped[int | None] = mapped_column(Integer, default=0)
    metadata_source: Mapped[str | None] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        Index("idx_standalone_series_tmdb", "tmdb_id"),
        Index("idx_standalone_series_anilist", "anilist_id"),
    )


class StandaloneMovie(db.Model):
    """Movie discovered in standalone mode (not from Radarr)."""

    __tablename__ = "standalone_movies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_path: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    tmdb_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    imdb_id: Mapped[str | None] = mapped_column(Text, default="")
    poster_url: Mapped[str | None] = mapped_column(Text, default="")
    metadata_source: Mapped[str | None] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (Index("idx_standalone_movies_tmdb", "tmdb_id"),)


class MetadataCache(db.Model):
    """Cache for external metadata provider responses (TMDB, AniList, etc.)."""

    __tablename__ = "metadata_cache"

    cache_key: Mapped[str] = mapped_column(Text, primary_key=True)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    response_json: Mapped[str] = mapped_column(Text, nullable=False)
    cached_at: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (Index("idx_metadata_cache_expires", "expires_at"),)


class AnidbMapping(db.Model):
    """TVDB to AniDB ID mapping cache."""

    __tablename__ = "anidb_mappings"

    tvdb_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    anidb_id: Mapped[int] = mapped_column(Integer, nullable=False)
    series_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str | None] = mapped_column(Text)
    last_used: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (Index("idx_anidb_mappings_anidb_id", "anidb_id"),)


__all__ = [
    "WatchedFolder",
    "StandaloneSeries",
    "StandaloneMovie",
    "MetadataCache",
    "AnidbMapping",
]
