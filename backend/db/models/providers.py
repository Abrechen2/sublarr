"""Provider ORM models: cache, downloads, stats, score modifiers, scoring weights.

All column types and defaults match the existing SCHEMA DDL in db/__init__.py exactly.
"""

from typing import Optional

from sqlalchemy import Index, Integer, Float, Text, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from extensions import db


class ProviderCache(db.Model):
    """Cached provider search results with TTL expiry."""

    __tablename__ = "provider_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider_name: Mapped[str] = mapped_column(Text, nullable=False)
    query_hash: Mapped[str] = mapped_column(Text, nullable=False)
    results_json: Mapped[str] = mapped_column(Text, nullable=False)
    cached_at: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        Index("idx_provider_cache_hash", "provider_name", "query_hash"),
        Index("idx_provider_cache_expires", "expires_at"),
    )


class SubtitleDownload(db.Model):
    """Record of downloaded subtitles from providers."""

    __tablename__ = "subtitle_downloads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider_name: Mapped[str] = mapped_column(Text, nullable=False)
    subtitle_id: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(Text, nullable=False)
    format: Mapped[Optional[str]] = mapped_column(Text, default="")
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    subtitle_type: Mapped[Optional[str]] = mapped_column(Text, default="full")
    source: Mapped[Optional[str]] = mapped_column(Text, default="provider")  # "provider" | "whisper"
    downloaded_at: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (Index("idx_subtitle_downloads_path", "file_path"),)


class ProviderStats(db.Model):
    """Per-provider performance and reliability statistics."""

    __tablename__ = "provider_stats"

    provider_name: Mapped[str] = mapped_column(Text, primary_key=True)
    total_searches: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    successful_downloads: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    failed_downloads: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    avg_score: Mapped[Optional[float]] = mapped_column(Float, default=0)
    last_success_at: Mapped[Optional[str]] = mapped_column(Text)
    last_failure_at: Mapped[Optional[str]] = mapped_column(Text)
    consecutive_failures: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    avg_response_time_ms: Mapped[Optional[float]] = mapped_column(Float, default=0)
    last_response_time_ms: Mapped[Optional[float]] = mapped_column(Float, default=0)
    auto_disabled: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    disabled_until: Mapped[Optional[str]] = mapped_column(Text, default="")
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (Index("idx_provider_stats_updated", "updated_at"),)


class ProviderScoreModifier(db.Model):
    """Manual score modifier per provider (user-configured bias)."""

    __tablename__ = "provider_score_modifiers"

    provider_name: Mapped[str] = mapped_column(Text, primary_key=True)
    modifier: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


class ScoringWeights(db.Model):
    """Configurable scoring weights for subtitle matching."""

    __tablename__ = "scoring_weights"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    score_type: Mapped[str] = mapped_column(Text, nullable=False)
    weight_key: Mapped[str] = mapped_column(Text, nullable=False)
    weight_value: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (UniqueConstraint("score_type", "weight_key"),)


__all__ = [
    "ProviderCache",
    "SubtitleDownload",
    "ProviderStats",
    "ProviderScoreModifier",
    "ScoringWeights",
]
