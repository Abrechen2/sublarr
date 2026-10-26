"""Standalone mode ORM models: watched folders, series, movies, metadata cache, AniDB mappings.

All column types and defaults match the existing SCHEMA DDL in db/__init__.py exactly.
"""

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text
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
    last_scan_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("idx_standalone_series_tmdb", "tmdb_id"),
        Index("idx_standalone_series_anilist", "anilist_id"),
        # The id is the owner key (-id) of rows in other tables; SQLite must
        # never hand a deleted series' id to a new one (migration
        # sa4_standalone_autoincrement rebuilds existing tables).
        {"sqlite_autoincrement": True},
    )


class StandaloneEpisode(db.Model):
    """One episode video file of a standalone series, with a stable id.

    The API hands out ``-id`` for a standalone episode (see
    docs/specs/standalone-ids.md). ``sqlite_autoincrement`` keeps SQLite from
    reusing the id of a deleted row, so a stale id can never name another file.
    No foreign key, like ``wanted_items.standalone_series_id``: rows are
    removed with their series in ``services.standalone_manager``.
    """

    __tablename__ = "standalone_episodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    standalone_series_id: Mapped[int] = mapped_column(Integer, nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    season: Mapped[int | None] = mapped_column(Integer, nullable=True)
    episode: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("idx_standalone_episodes_series", "standalone_series_id"),
        {"sqlite_autoincrement": True},
    )


class StandaloneLegacyClaim(db.Model):
    """A standalone title whose pre-1.18 positive-key rows are no longer read.

    Before 1.18.0 a standalone title's profile, settings, glossary and fansub
    rows were stored under its positive row id. They are still read from
    there (read-only) until the title's first write since the upgrade: that
    write copies them to the owner key (the negated id) and records the claim
    here, so a later delete under the owner key never brings the old rows
    back. Also written when the title is deleted, so a reused row id never
    inherits them. See docs/specs/standalone-ids.md.
    """

    __tablename__ = "standalone_legacy_claims"

    kind: Mapped[str] = mapped_column(String(10), primary_key=True)  # "series" | "movie"
    standalone_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    claimed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("idx_standalone_movies_tmdb", "tmdb_id"),
        # Never reuse a deleted movie's id, see StandaloneSeries.
        {"sqlite_autoincrement": True},
    )


class MetadataCache(db.Model):
    """Cache for external metadata provider responses (TMDB, AniList, etc.)."""

    __tablename__ = "metadata_cache"

    cache_key: Mapped[str] = mapped_column(Text, primary_key=True)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    response_json: Mapped[str] = mapped_column(Text, nullable=False)
    cached_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("idx_metadata_cache_expires", "expires_at"),)


class AnidbMapping(db.Model):
    """TVDB to AniDB ID mapping cache."""

    __tablename__ = "anidb_mappings"

    tvdb_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    anidb_id: Mapped[int] = mapped_column(Integer, nullable=False)
    series_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("idx_anidb_mappings_anidb_id", "anidb_id"),)


__all__ = [
    "WatchedFolder",
    "StandaloneSeries",
    "StandaloneMovie",
    "MetadataCache",
    "AnidbMapping",
]
