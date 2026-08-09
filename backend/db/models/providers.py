"""Provider ORM models: cache, downloads, stats, score modifiers, scoring weights.

All column types and defaults match the existing SCHEMA DDL in db/__init__.py exactly.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from extensions import db


class ProviderCache(db.Model):
    """Cached provider search results with TTL expiry."""

    __tablename__ = "provider_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider_name: Mapped[str] = mapped_column(Text, nullable=False)
    query_hash: Mapped[str] = mapped_column(Text, nullable=False)
    results_json: Mapped[str] = mapped_column(Text, nullable=False)
    cached_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

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
    format: Mapped[str | None] = mapped_column(Text, default="")
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[int | None] = mapped_column(Integer, default=0)
    # JSON dict of per-component score points ({"hash": 359, ...});
    # NULL for rows recorded before the column existed or non-provider sources.
    score_breakdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    subtitle_type: Mapped[str | None] = mapped_column(Text, default="full")
    source: Mapped[str | None] = mapped_column(
        Text, default="provider"
    )  # "provider" | "whisper" | "manual"
    downloaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    upgraded_from_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # JSON snapshot of the selection decision log (see decision_log.py).
    # NULL for rows recorded outside a wanted-search run or with the
    # decision_log_enabled setting off. Stripped from list responses —
    # served via GET /history/<id>/decision only.
    decision_log_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        # idx_subtitle_downloads_path dropped in migration h1i2j3k4l5m6 —
        # 0 scans in prod; planner prefers seq scan on this small table and
        # the query patterns use file_path IN (...) which still does well
        # without a dedicated index at current row counts.
        Index("idx_subtitle_downloads_downloaded_at", "downloaded_at"),
        Index("idx_subtitle_downloads_language", "language"),
    )


class ProviderStats(db.Model):
    """Per-provider performance and reliability statistics."""

    __tablename__ = "provider_stats"

    provider_name: Mapped[str] = mapped_column(Text, primary_key=True)
    total_searches: Mapped[int | None] = mapped_column(Integer, default=0)
    successful_searches: Mapped[int | None] = mapped_column(Integer, default=0)
    successful_downloads: Mapped[int | None] = mapped_column(Integer, default=0)
    failed_downloads: Mapped[int | None] = mapped_column(Integer, default=0)
    avg_score: Mapped[float | None] = mapped_column(Float, default=0)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Search and download are separate paths with separate credentials, and one
    # can die while the other keeps working — an OpenSubtitles download token
    # expires after 24h while search runs on the API key alone. Both used to
    # stamp last_success_at, which made that failure invisible for three days.
    last_search_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_download_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consecutive_failures: Mapped[int | None] = mapped_column(Integer, default=0)
    avg_response_time_ms: Mapped[float | None] = mapped_column(Float, default=0)
    last_response_time_ms: Mapped[float | None] = mapped_column(Float, default=0)
    auto_disabled: Mapped[int | None] = mapped_column(Integer, default=0)
    disabled_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("idx_provider_stats_updated", "updated_at"),)


class ProviderScoreModifier(db.Model):
    """Manual score modifier per provider (user-configured bias)."""

    __tablename__ = "provider_score_modifiers"

    provider_name: Mapped[str] = mapped_column(Text, primary_key=True)
    modifier: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ScoringWeights(db.Model):
    """Configurable scoring weights for subtitle matching."""

    __tablename__ = "scoring_weights"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    score_type: Mapped[str] = mapped_column(Text, nullable=False)
    weight_key: Mapped[str] = mapped_column(Text, nullable=False)
    weight_value: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (UniqueConstraint("score_type", "weight_key"),)


class CustomScoringRule(db.Model):
    """User-defined regex scoring rule (Sonarr-style release profile condition).

    ``pattern`` is matched case-insensitively against a candidate's
    release_info during penalty-pipeline scoring; a hit adds the signed
    ``weight`` to the candidate's score.
    """

    __tablename__ = "custom_scoring_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    pattern: Mapped[str] = mapped_column(Text, nullable=False)
    weight: Mapped[int] = mapped_column(Integer, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


__all__ = [
    "ProviderCache",
    "SubtitleDownload",
    "ProviderStats",
    "ProviderScoreModifier",
    "ScoringWeights",
    "CustomScoringRule",
]
