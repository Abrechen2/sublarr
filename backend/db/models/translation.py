"""Translation ORM models: config history, glossary, presets, backend stats, whisper jobs.

All column types and defaults match the existing SCHEMA DDL in db/__init__.py exactly.
"""

from typing import Optional

from sqlalchemy import Index, Integer, Float, Text, String
from sqlalchemy.orm import Mapped, mapped_column

from extensions import db


class TranslationConfigHistory(db.Model):
    """History of translation config hashes for tracking config changes."""

    __tablename__ = "translation_config_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    config_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    ollama_model: Mapped[Optional[str]] = mapped_column(Text)
    prompt_template: Mapped[Optional[str]] = mapped_column(Text)
    target_language: Mapped[Optional[str]] = mapped_column(Text)
    first_used_at: Mapped[str] = mapped_column(Text, nullable=False)
    last_used_at: Mapped[str] = mapped_column(Text, nullable=False)


class GlossaryEntry(db.Model):
    """Per-series or global glossary for consistent term translation.

    When series_id is NULL, the entry is a global glossary entry that applies
    to all series. Per-series entries (series_id set) override global entries
    with the same source_term during translation.
    """

    __tablename__ = "glossary_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    series_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    source_term: Mapped[str] = mapped_column(Text, nullable=False)
    target_term: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        Index("idx_glossary_series_id", "series_id"),
        Index("idx_glossary_source_term", "source_term"),
    )


class PromptPreset(db.Model):
    """Saved translation prompt templates."""

    __tablename__ = "prompt_presets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    prompt_template: Mapped[str] = mapped_column(Text, nullable=False)
    is_default: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


class TranslationBackendStats(db.Model):
    """Per-backend translation performance and reliability statistics."""

    __tablename__ = "translation_backend_stats"

    backend_name: Mapped[str] = mapped_column(Text, primary_key=True)
    total_requests: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    successful_translations: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    failed_translations: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    total_characters: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    avg_response_time_ms: Mapped[Optional[float]] = mapped_column(Float, default=0)
    last_response_time_ms: Mapped[Optional[float]] = mapped_column(Float, default=0)
    last_success_at: Mapped[Optional[str]] = mapped_column(Text)
    last_failure_at: Mapped[Optional[str]] = mapped_column(Text)
    last_error: Mapped[Optional[str]] = mapped_column(Text, default="")
    consecutive_failures: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        Index("idx_translation_backend_stats_updated", "updated_at"),
    )


class WhisperJob(db.Model):
    """Whisper speech-to-text transcription job tracking."""

    __tablename__ = "whisper_jobs"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    progress: Mapped[Optional[float]] = mapped_column(Float, default=0.0)
    phase: Mapped[Optional[str]] = mapped_column(Text, default="")
    backend_name: Mapped[Optional[str]] = mapped_column(Text, default="")
    detected_language: Mapped[Optional[str]] = mapped_column(Text, default="")
    language_probability: Mapped[Optional[float]] = mapped_column(Float, default=0.0)
    srt_content: Mapped[Optional[str]] = mapped_column(Text, default="")
    segment_count: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float, default=0.0)
    processing_time_ms: Mapped[Optional[float]] = mapped_column(Float, default=0.0)
    error: Mapped[Optional[str]] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[Optional[str]] = mapped_column(Text, default="")
    completed_at: Mapped[Optional[str]] = mapped_column(Text, default="")

    __table_args__ = (
        Index("idx_whisper_jobs_status", "status"),
        Index("idx_whisper_jobs_created", "created_at"),
    )


__all__ = [
    "TranslationConfigHistory",
    "GlossaryEntry",
    "PromptPreset",
    "TranslationBackendStats",
    "WhisperJob",
]
