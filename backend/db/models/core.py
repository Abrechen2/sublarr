"""Core ORM models: jobs, stats, config, wanted, upgrades, profiles, cache, blacklist.

All column types and defaults match the existing SCHEMA DDL in db/__init__.py exactly.
Timestamp columns use Text (not DateTime) to preserve backward compatibility.
"""

from typing import Optional

from sqlalchemy import Index, Integer, Float, Text, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from extensions import db


class Job(db.Model):
    """Translation job tracking."""

    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(8), primary_key=True)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    source_format: Mapped[Optional[str]] = mapped_column(String(10), default="")
    output_path: Mapped[Optional[str]] = mapped_column(Text, default="")
    stats_json: Mapped[Optional[str]] = mapped_column(Text, default="{}")
    error: Mapped[Optional[str]] = mapped_column(Text, default="")
    force: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    bazarr_context_json: Mapped[Optional[str]] = mapped_column(Text, default="")
    config_hash: Mapped[Optional[str]] = mapped_column(String(12), default="")
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    completed_at: Mapped[Optional[str]] = mapped_column(Text, default="")

    __table_args__ = (
        Index("idx_jobs_status", "status"),
        Index("idx_jobs_created", "created_at"),
    )


class DailyStats(db.Model):
    """Daily translation statistics."""

    __tablename__ = "daily_stats"

    date: Mapped[str] = mapped_column(Text, primary_key=True)
    translated: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    failed: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    skipped: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    by_format_json: Mapped[Optional[str]] = mapped_column(
        Text, default='{"ass": 0, "srt": 0}'
    )
    by_source_json: Mapped[Optional[str]] = mapped_column(Text, default="{}")


class ConfigEntry(db.Model):
    """Runtime configuration overrides stored in database."""

    __tablename__ = "config_entries"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


class WantedItem(db.Model):
    """Items needing subtitle download or translation."""

    __tablename__ = "wanted_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_type: Mapped[str] = mapped_column(String(20), nullable=False)
    sonarr_series_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sonarr_episode_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    radarr_movie_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False, default="")
    season_episode: Mapped[Optional[str]] = mapped_column(Text, default="")
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    existing_sub: Mapped[Optional[str]] = mapped_column(Text, default="")
    missing_languages: Mapped[Optional[str]] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="wanted")
    last_search_at: Mapped[Optional[str]] = mapped_column(Text, default="")
    search_count: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    error: Mapped[Optional[str]] = mapped_column(Text, default="")
    added_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)
    upgrade_candidate: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    current_score: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    target_language: Mapped[Optional[str]] = mapped_column(Text, default="")
    instance_name: Mapped[Optional[str]] = mapped_column(Text, default="")
    standalone_series_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    standalone_movie_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    subtitle_type: Mapped[Optional[str]] = mapped_column(String(20), default="full")

    __table_args__ = (
        Index("idx_wanted_status", "status"),
        Index("idx_wanted_item_type", "item_type"),
        Index("idx_wanted_file_path", "file_path"),
        Index("idx_wanted_sonarr_series", "sonarr_series_id"),
        Index("idx_wanted_sonarr_episode", "sonarr_episode_id"),
        Index("idx_wanted_radarr_movie", "radarr_movie_id"),
    )


class UpgradeHistory(db.Model):
    """History of subtitle format upgrades (e.g., SRT -> ASS)."""

    __tablename__ = "upgrade_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    old_format: Mapped[Optional[str]] = mapped_column(Text)
    old_score: Mapped[Optional[int]] = mapped_column(Integer)
    new_format: Mapped[Optional[str]] = mapped_column(Text)
    new_score: Mapped[Optional[int]] = mapped_column(Integer)
    provider_name: Mapped[Optional[str]] = mapped_column(Text)
    upgrade_reason: Mapped[Optional[str]] = mapped_column(Text)
    upgraded_at: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (Index("idx_upgrade_history_path", "file_path"),)


class LanguageProfile(db.Model):
    """Language profile for translation source/target configuration."""

    __tablename__ = "language_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    source_language: Mapped[str] = mapped_column(Text, nullable=False, default="en")
    source_language_name: Mapped[str] = mapped_column(
        Text, nullable=False, default="English"
    )
    target_languages_json: Mapped[str] = mapped_column(
        Text, nullable=False, default='["de"]'
    )
    target_language_names_json: Mapped[str] = mapped_column(
        Text, nullable=False, default='["German"]'
    )
    is_default: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    translation_backend: Mapped[Optional[str]] = mapped_column(
        Text, default="ollama"
    )
    fallback_chain_json: Mapped[Optional[str]] = mapped_column(
        Text, default='["ollama"]'
    )
    forced_preference: Mapped[Optional[str]] = mapped_column(
        Text, default="disabled"
    )
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


class SeriesLanguageProfile(db.Model):
    """Maps a Sonarr series to a language profile."""

    __tablename__ = "series_language_profiles"

    sonarr_series_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        Integer,
        db.ForeignKey("language_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )


class MovieLanguageProfile(db.Model):
    """Maps a Radarr movie to a language profile."""

    __tablename__ = "movie_language_profiles"

    radarr_movie_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        Integer,
        db.ForeignKey("language_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )


class FfprobeCache(db.Model):
    """Cache for ffprobe media file analysis results."""

    __tablename__ = "ffprobe_cache"

    file_path: Mapped[str] = mapped_column(Text, primary_key=True)
    mtime: Mapped[float] = mapped_column(Float, nullable=False)
    probe_data_json: Mapped[str] = mapped_column(Text, nullable=False)
    cached_at: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (Index("idx_ffprobe_cache_mtime", "mtime"),)


class BlacklistEntry(db.Model):
    """Blacklisted subtitle provider results."""

    __tablename__ = "blacklist_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider_name: Mapped[str] = mapped_column(Text, nullable=False)
    subtitle_id: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[Optional[str]] = mapped_column(Text, default="")
    file_path: Mapped[Optional[str]] = mapped_column(Text, default="")
    title: Mapped[Optional[str]] = mapped_column(Text, default="")
    reason: Mapped[Optional[str]] = mapped_column(Text, default="")
    added_at: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        UniqueConstraint("provider_name", "subtitle_id"),
        Index("idx_blacklist_provider", "provider_name", "subtitle_id"),
    )


class FilterPreset(db.Model):
    """Saved filter configurations per page scope."""
    __tablename__ = "filter_presets"

    id:          Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name:        Mapped[str] = mapped_column(String(100), nullable=False)
    scope:       Mapped[str] = mapped_column(String(50), nullable=False)   # 'wanted'|'library'|'history'
    conditions:  Mapped[str] = mapped_column(Text, nullable=False, default="{}")  # JSON condition tree
    is_default:  Mapped[int] = mapped_column(Integer, nullable=False, default=0)   # 1 = auto-apply
    created_at:  Mapped[str] = mapped_column(Text, nullable=False)
    updated_at:  Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        Index("idx_filter_presets_scope", "scope"),
    )


__all__ = [
    "Job",
    "DailyStats",
    "ConfigEntry",
    "WantedItem",
    "UpgradeHistory",
    "LanguageProfile",
    "SeriesLanguageProfile",
    "MovieLanguageProfile",
    "FfprobeCache",
    "BlacklistEntry",
    "FilterPreset",
]
