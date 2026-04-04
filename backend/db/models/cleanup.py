"""Cleanup ORM models for subtitle deduplication and disk management.

Stores content hashes for duplicate detection, configurable cleanup rules,
and execution history for tracking space reclamation over time.
"""

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from extensions import db


class SubtitleHash(db.Model):
    """Stores SHA-256 content hashes for subtitle files."""

    __tablename__ = "subtitle_hashes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_path: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    format: Mapped[str] = mapped_column(String(10), nullable=False)
    language: Mapped[str] = mapped_column(String(10), nullable=True)
    line_count: Mapped[int] = mapped_column(Integer, nullable=True)
    last_scanned: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("idx_subtitle_hashes_content_hash", "content_hash"),
        Index("idx_subtitle_hashes_file_path", "file_path"),
    )


class CleanupRule(db.Model):
    """Configurable cleanup rules (dedup, orphaned, old_backups)."""

    __tablename__ = "cleanup_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    rule_type: Mapped[str] = mapped_column(String(50), nullable=False)
    config_json: Mapped[str] = mapped_column(Text, default="{}")
    enabled: Mapped[int] = mapped_column(Integer, default=1)
    schedule: Mapped[str] = mapped_column(String(20), default="manual")
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CleanupHistory(db.Model):
    """Execution history for cleanup operations."""

    __tablename__ = "cleanup_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_id: Mapped[int] = mapped_column(Integer, nullable=True)
    action_type: Mapped[str] = mapped_column(String(50), nullable=False)
    files_processed: Mapped[int] = mapped_column(Integer, default=0)
    files_deleted: Mapped[int] = mapped_column(Integer, default=0)
    bytes_freed: Mapped[int] = mapped_column(Integer, default=0)
    details_json: Mapped[str] = mapped_column(Text, default="{}")
    performed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("idx_cleanup_history_performed_at", "performed_at"),)
