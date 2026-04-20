"""Translation ORM models: config history, glossary, presets, backend stats, whisper jobs, memory cache.

All column types and defaults match the existing SCHEMA DDL in db/__init__.py exactly.
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from extensions import db


class TranslationConfigHistory(db.Model):
    """History of translation config hashes for tracking config changes."""

    __tablename__ = "translation_config_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    config_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    ollama_model: Mapped[str | None] = mapped_column(Text)
    prompt_template: Mapped[str | None] = mapped_column(Text)
    target_language: Mapped[str | None] = mapped_column(Text)
    first_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class GlossaryEntry(db.Model):
    """Per-series or global glossary for consistent term translation.

    When series_id is NULL, the entry is a global glossary entry that applies
    to all series. Per-series entries (series_id set) override global entries
    with the same source_term during translation.
    """

    __tablename__ = "glossary_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    series_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_term: Mapped[str] = mapped_column(Text, nullable=False)
    target_term: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, default="")
    term_type: Mapped[str] = mapped_column(Text, nullable=False, default="other")
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    approved: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

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
    is_default: Mapped[int | None] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TranslationBackendStats(db.Model):
    """Per-backend translation performance and reliability statistics."""

    __tablename__ = "translation_backend_stats"

    backend_name: Mapped[str] = mapped_column(Text, primary_key=True)
    total_requests: Mapped[int | None] = mapped_column(Integer, default=0)
    successful_translations: Mapped[int | None] = mapped_column(Integer, default=0)
    failed_translations: Mapped[int | None] = mapped_column(Integer, default=0)
    total_characters: Mapped[int | None] = mapped_column(Integer, default=0)
    avg_response_time_ms: Mapped[float | None] = mapped_column(Float, default=0)
    last_response_time_ms: Mapped[float | None] = mapped_column(Float, default=0)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, default="")
    consecutive_failures: Mapped[int | None] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("idx_translation_backend_stats_updated", "updated_at"),)


class WhisperJob(db.Model):
    """Whisper speech-to-text transcription job tracking."""

    __tablename__ = "whisper_jobs"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    progress: Mapped[float | None] = mapped_column(Float, default=0.0)
    phase: Mapped[str | None] = mapped_column(Text, default="")
    backend_name: Mapped[str | None] = mapped_column(Text, default="")
    detected_language: Mapped[str | None] = mapped_column(Text, default="")
    language_probability: Mapped[float | None] = mapped_column(Float, default=0.0)
    srt_content: Mapped[str | None] = mapped_column(Text, default="")
    segment_count: Mapped[int | None] = mapped_column(Integer, default=0)
    duration_seconds: Mapped[float | None] = mapped_column(Float, default=0.0)
    processing_time_ms: Mapped[float | None] = mapped_column(Float, default=0.0)
    audio_track_index: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    error: Mapped[str | None] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_whisper_jobs_status", "status"),
        Index("idx_whisper_jobs_created", "created_at"),
    )


class TranslationMemory(db.Model):
    """Persistent translation memory cache.

    Stores successfully translated lines keyed by source language, target language,
    and a normalized+hashed form of the source text. Enables reuse of previous
    translations for identical or near-identical lines, reducing LLM calls.

    The text_hash column stores the SHA-256 of source_text_normalized and is used
    for fast exact-match lookups. source_text_normalized is kept for optional
    similarity matching via difflib.
    """

    __tablename__ = "translation_memory"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_lang: Mapped[str] = mapped_column(Text, nullable=False)
    target_lang: Mapped[str] = mapped_column(Text, nullable=False)
    source_text_normalized: Mapped[str] = mapped_column(Text, nullable=False)
    text_hash: Mapped[str] = mapped_column(Text, nullable=False)
    translated_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Plan A follow-up — Backend that produced this translation (nullable; older rows pre-A1 are NULL).
    backend: Mapped[str | None] = mapped_column(String(32), nullable=True, default=None)

    __table_args__ = (
        # Fast exact-match lookup
        Index("idx_tm_lang_hash", "source_lang", "target_lang", "text_hash"),
        # For similarity scan within a language pair
        Index("idx_tm_lang_pair", "source_lang", "target_lang"),
        # Uniqueness: one translation per (source_lang, target_lang, text_hash)
        UniqueConstraint("source_lang", "target_lang", "text_hash", name="uq_tm_lang_hash"),
    )


class TranslationEvent(db.Model):
    """One row per translate_batch call.

    Populated by translator/events.py::write_translation_event.
    Retention controlled by ``translation_events_retention_days`` + the
    ``translation_events_cleanup`` cron job.
    """

    __tablename__ = "translation_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    backend: Mapped[str] = mapped_column(String(32), nullable=False)
    source_lang: Mapped[str] = mapped_column(String(16), nullable=False)
    target_lang: Mapped[str] = mapped_column(String(16), nullable=False)
    lines_count: Mapped[int] = mapped_column(Integer, nullable=False)
    chars_in: Mapped[int] = mapped_column(Integer, nullable=False)
    chars_out: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_estimate_micro_usd: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    cache_hit: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    error_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)
    job_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index(
            "ix_translation_events_backend_started_at",
            "backend",
            "started_at",
        ),
        Index("ix_translation_events_started_at", "started_at"),
        Index("ix_translation_events_status", "status"),
        Index("ix_translation_events_job_id", "job_id"),
    )


__all__ = [
    "TranslationConfigHistory",
    "GlossaryEntry",
    "PromptPreset",
    "TranslationBackendStats",
    "WhisperJob",
    "TranslationMemory",
    "TranslationEvent",
]
