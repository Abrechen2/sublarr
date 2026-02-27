"""Translation ORM models: config history, glossary, presets, backend stats, whisper jobs, memory cache.

All column types and defaults match the existing SCHEMA DDL in db/__init__.py exactly.
"""


from sqlalchemy import Float, Index, Integer, String, Text, UniqueConstraint
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
    series_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_term: Mapped[str] = mapped_column(Text, nullable=False)
    target_term: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, default="")
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
    is_default: Mapped[int | None] = mapped_column(Integer, default=0)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


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
    last_success_at: Mapped[str | None] = mapped_column(Text)
    last_failure_at: Mapped[str | None] = mapped_column(Text)
    last_error: Mapped[str | None] = mapped_column(Text, default="")
    consecutive_failures: Mapped[int | None] = mapped_column(Integer, default=0)
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
    progress: Mapped[float | None] = mapped_column(Float, default=0.0)
    phase: Mapped[str | None] = mapped_column(Text, default="")
    backend_name: Mapped[str | None] = mapped_column(Text, default="")
    detected_language: Mapped[str | None] = mapped_column(Text, default="")
    language_probability: Mapped[float | None] = mapped_column(Float, default=0.0)
    srt_content: Mapped[str | None] = mapped_column(Text, default="")
    segment_count: Mapped[int | None] = mapped_column(Integer, default=0)
    duration_seconds: Mapped[float | None] = mapped_column(Float, default=0.0)
    processing_time_ms: Mapped[float | None] = mapped_column(Float, default=0.0)
    error: Mapped[str | None] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[str | None] = mapped_column(Text, default="")
    completed_at: Mapped[str | None] = mapped_column(Text, default="")

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
    created_at: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        # Fast exact-match lookup
        Index("idx_tm_lang_hash", "source_lang", "target_lang", "text_hash"),
        # For similarity scan within a language pair
        Index("idx_tm_lang_pair", "source_lang", "target_lang"),
        # Uniqueness: one translation per (source_lang, target_lang, text_hash)
        UniqueConstraint("source_lang", "target_lang", "text_hash",
                         name="uq_tm_lang_hash"),
    )


__all__ = [
    "TranslationConfigHistory",
    "GlossaryEntry",
    "PromptPreset",
    "TranslationBackendStats",
    "WhisperJob",
    "TranslationMemory",
]
