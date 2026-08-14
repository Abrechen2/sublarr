"""Core ORM models: jobs, stats, config, wanted, upgrades, profiles, cache, blacklist.

All column types and defaults match the existing SCHEMA DDL in db/__init__.py exactly.
Timestamp columns use DateTime(timezone=True) for proper datetime handling.
"""

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from extensions import db


class Job(db.Model):
    """Translation job tracking."""

    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(8), primary_key=True)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    source_format: Mapped[str | None] = mapped_column(String(10), default="")
    output_path: Mapped[str | None] = mapped_column(Text, default="")
    stats_json: Mapped[str | None] = mapped_column(Text, default="{}")
    error: Mapped[str | None] = mapped_column(Text, default="")
    force: Mapped[int | None] = mapped_column(Integer, default=0)
    bazarr_context_json: Mapped[str | None] = mapped_column(Text, default="")
    config_hash: Mapped[str | None] = mapped_column(String(12), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_jobs_status", "status"),
        Index("idx_jobs_created", "created_at"),
    )


class DailyStats(db.Model):
    """Daily translation statistics."""

    __tablename__ = "daily_stats"

    date: Mapped[str] = mapped_column(Text, primary_key=True)
    translated: Mapped[int | None] = mapped_column(Integer, default=0)
    failed: Mapped[int | None] = mapped_column(Integer, default=0)
    skipped: Mapped[int | None] = mapped_column(Integer, default=0)
    by_format_json: Mapped[str | None] = mapped_column(Text, default='{"ass": 0, "srt": 0}')
    by_source_json: Mapped[str | None] = mapped_column(Text, default="{}")


class ConfigEntry(db.Model):
    """Runtime configuration overrides stored in database."""

    __tablename__ = "config_entries"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class WantedItem(db.Model):
    """Items needing subtitle download or translation."""

    __tablename__ = "wanted_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_type: Mapped[str] = mapped_column(String(20), nullable=False)
    sonarr_series_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sonarr_episode_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    radarr_movie_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False, default="")
    season_episode: Mapped[str | None] = mapped_column(Text, default="")
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    existing_sub: Mapped[str | None] = mapped_column(Text, default="")
    embedded_languages: Mapped[str | None] = mapped_column(Text, default="[]")
    missing_languages: Mapped[str | None] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="wanted")
    last_search_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    search_count: Mapped[int | None] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, default="")
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    upgrade_candidate: Mapped[int | None] = mapped_column(Integer, default=0)
    current_score: Mapped[int | None] = mapped_column(Integer, default=0)
    target_language: Mapped[str | None] = mapped_column(Text, default="")
    instance_name: Mapped[str | None] = mapped_column(Text, default="")
    standalone_series_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    standalone_movie_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    subtitle_type: Mapped[str | None] = mapped_column(String(20), default="full")
    retry_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # ── Phase 1 scheduler fields (migration b1u2d3g4e5t6) ──────────────────
    # Priority tier for budget-aware scheduling: 'premium' (fresh, < 7d),
    # 'standard' (default), or 'backlog' (> 180d + prior failures).
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="standard")
    # Distinguishes 'no_result' (genuine — providers have nothing) from
    # 'provider_error' (network/429/circuit-breaker) so transient outages
    # don't burn retries. 'no_result_slow' marks items past max_attempts that
    # enter slow-mode (1x / 30d) instead of the old permanent freeze.
    failure_kind: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Provider-side errors are counted separately from search_count so they
    # don't poison an item when a provider has a bad day.
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # ── Provisional-MT re-seek fields (feature #8b Phase 2 Task 2,
    # migration 3c4b1a2d5e6f) ─────────────────────────────────────────────
    # User-edited/confirmed machine translation: never auto-replaced or
    # re-searched by mt_reseek, regardless of the profile's
    # mt_keep_seeking_original setting. Honoured by services.mt_reseek._is_pinned.
    # Nullable (like upgrade_candidate above) rather than NOT NULL: the raw-SQL
    # upsert path (db/repositories/wanted_upsert.py) enumerates columns
    # explicitly and does not know about this one — a NOT NULL constraint
    # would break every plain upsert_wanted_item() insert. NULL == falsy ==
    # unpinned, so _is_pinned's bool(item.get("mt_pinned")) stays correct.
    mt_pinned: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    # JSON payload recording a qualifying original found during a
    # mt_on_original_found="notify" re-seek pass (provider, score, output_path,
    # found_at). NULL when there is no pending original. Set by
    # services.mt_reseek, read/cleared by the Task-3 approve/reject API.
    mt_pending_original: Mapped[str | None] = mapped_column(Text, nullable=True)
    # JSON snapshot of the most recent search decision log for items where NO
    # subtitle was downloaded (not_found / failed / upgrade-rejected) — answers
    # "why was nothing found?". Successful downloads carry their snapshot on
    # subtitle_downloads.decision_log_json instead (the wanted row is deleted).
    # Stripped from list responses; served via GET /wanted/<id>/decision.
    last_decision_log_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("idx_wanted_status", "status"),
        Index("idx_wanted_item_type", "item_type"),
        Index("idx_wanted_file_path", "file_path"),
        # idx_wanted_sonarr_series and idx_wanted_radarr_movie were dropped in
        # migration h1i2j3k4l5m6 — prod showed 0 scans on both over ~2 weeks
        # and the only non-trivial FK query uses sonarr_episode_id (kept below).
        Index("idx_wanted_sonarr_episode", "sonarr_episode_id"),
        # Composite index for the most common multi-filter pattern:
        # get_wanted_items() filters by both status and item_type together.
        # Avoids SQLite merging two single-column index scans.
        Index("idx_wanted_composite", "status", "item_type"),
        Index("idx_wanted_retry_after", "retry_after"),
        Index("idx_wanted_status_retry_after", "status", "retry_after"),
        # Prevent duplicate entries for the same file + language + subtitle type.
        # The upsert logic relies on this for race-condition safety.
        UniqueConstraint(
            "file_path", "target_language", "subtitle_type", name="uq_wanted_file_lang_type"
        ),
    )


class UpgradeHistory(db.Model):
    """History of subtitle format upgrades (e.g., SRT -> ASS)."""

    __tablename__ = "upgrade_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    old_format: Mapped[str | None] = mapped_column(Text)
    old_score: Mapped[int | None] = mapped_column(Integer)
    new_format: Mapped[str | None] = mapped_column(Text)
    new_score: Mapped[int | None] = mapped_column(Integer)
    provider_name: Mapped[str | None] = mapped_column(Text)
    upgrade_reason: Mapped[str | None] = mapped_column(Text)
    upgraded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("idx_upgrade_history_path", "file_path"),)


class LanguageProfile(db.Model):
    """Language profile for translation source/target configuration."""

    __tablename__ = "language_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    source_language: Mapped[str] = mapped_column(Text, nullable=False, default="en")
    source_language_name: Mapped[str] = mapped_column(Text, nullable=False, default="English")
    target_languages_json: Mapped[str] = mapped_column(Text, nullable=False, default='["de"]')
    target_language_names_json: Mapped[str] = mapped_column(
        Text, nullable=False, default='["German"]'
    )
    is_default: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    translation_backend: Mapped[str | None] = mapped_column(Text, default="ollama")
    fallback_chain_json: Mapped[str | None] = mapped_column(Text, default='["ollama"]')
    forced_preference: Mapped[str | None] = mapped_column(Text, default="disabled")
    hi_preference: Mapped[str | None] = mapped_column(Text, default="include")
    forced_scoring: Mapped[str | None] = mapped_column(Text, default="include")
    # Filter fields (Bazarr parity)
    must_contain_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    must_not_contain_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    cutoff_language: Mapped[str] = mapped_column(Text, nullable=False, default="")
    audio_exclude_languages_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    # Provisional machine-translation (feature #8). When mt_keep_seeking_original
    # is on, a Sublarr-translated sub is recorded as source="machine_translation"
    # and the wanted item is kept "provisional" (seeking the human original)
    # instead of being deleted. See docs/plans/2026-07-03-v1.6-provisional-mt.md.
    mt_keep_seeking_original: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    mt_on_original_found: Mapped[str] = mapped_column(Text, nullable=False, default="notify")
    mt_min_original_score: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # Combined / bilingual subtitles (feature #1). When combine_enabled is on,
    # after download/extract Sublarr composes the combine_languages sidecars into
    # one combined file (combine_format). combine_position drives ASS \an placement
    # (primary = first entry in combine_languages). See
    # docs/plans/2026-07-04-v1.6-combined-subtitles.md.
    combine_enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    combine_format: Mapped[str] = mapped_column(Text, nullable=False, default="ass")
    combine_languages_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    combine_position_json: Mapped[str] = mapped_column(
        Text, nullable=False, default='{"primary": "bottom", "secondary": "top"}'
    )
    # Provider profile: JSON list of provider names this profile searches.
    # NULL / empty list = inherit the global providers_enabled selection.
    enabled_providers_json: Mapped[str | None] = mapped_column(Text, default=None)
    # Scoring preset name (bundled preset, e.g. "Anime"/"Movies"/"TV").
    # NULL / "" = use the global scoring weights from scoring_weights.
    scoring_preset: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


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
    cached_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("idx_ffprobe_cache_mtime", "mtime"),)


class ChapterCache(db.Model):
    """Per-video chapter list cache, invalidated by file mtime.

    chapters_json: JSON-encoded list of {"id", "title", "start_ms", "end_ms"} dicts.
    Populated lazily when a video is opened in the sync UI.
    """

    __tablename__ = "chapter_cache"

    file_path: Mapped[str] = mapped_column(Text, primary_key=True)
    mtime: Mapped[float] = mapped_column(Float, nullable=False)
    chapters_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    cached_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DubtitleDetection(db.Model):
    """Cached dubtitle-detection result per video, invalidated by file mtime.

    ``result_json`` holds the full serialized DubtitleDetectionResult
    (candidates + per-track scores) so the UI can render the flag without
    re-running detection, and a scheduled sweep can skip files it has
    already seen at the same mtime — including the "no dubtitle present"
    outcome, which is cached too.
    """

    __tablename__ = "dubtitle_detections"

    file_path: Mapped[str] = mapped_column(Text, primary_key=True)
    mtime: Mapped[float] = mapped_column(Float, nullable=False)
    dubtitle_sub_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    method: Mapped[str] = mapped_column(Text, nullable=False, default="none")
    result_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class BlacklistEntry(db.Model):
    """Blacklisted subtitle provider results."""

    __tablename__ = "blacklist_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider_name: Mapped[str] = mapped_column(Text, nullable=False)
    subtitle_id: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str | None] = mapped_column(Text, default="")
    file_path: Mapped[str | None] = mapped_column(Text, default="")
    title: Mapped[str | None] = mapped_column(Text, default="")
    reason: Mapped[str | None] = mapped_column(Text, default="")
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Plan B3 — file-hash dimension for provider-agnostic retry suppression
    file_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)

    __table_args__ = (
        UniqueConstraint("provider_name", "subtitle_id"),
        Index("idx_blacklist_provider", "provider_name", "subtitle_id"),
        Index(
            "idx_blacklist_provider_hash",
            "provider_name",
            "file_hash",
            unique=True,
            postgresql_where=text("file_hash IS NOT NULL"),
            sqlite_where=text("file_hash IS NOT NULL"),
        ),
    )


class PostProcessingRun(db.Model):
    """Audit row for one post-processing pipeline run (Plan B6)."""

    __tablename__ = "post_processing_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trigger: Mapped[str] = mapped_column(String(32), nullable=False)
    ops_executed: Mapped[dict] = mapped_column(JSON, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("idx_pp_runs_created_at", "created_at"),
        Index("idx_pp_runs_trigger", "trigger"),
    )


class SyncJobRun(db.Model):
    """Audit row for one sync engine attempt (Plan B7)."""

    __tablename__ = "sync_job_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    engine: Mapped[str] = mapped_column(String(32), nullable=False)
    offset_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    subtitle_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    video_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("idx_sync_runs_created_at", "created_at"),
        Index("idx_sync_runs_engine", "engine"),
    )


class FilterPreset(db.Model):
    """Saved filter configurations per page scope."""

    __tablename__ = "filter_presets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    scope: Mapped[str] = mapped_column(String(50), nullable=False)  # 'wanted'|'library'|'history'
    conditions: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}"
    )  # JSON condition tree
    is_default: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 1 = auto-apply
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("idx_filter_presets_scope", "scope"),)


class AnidbAbsoluteMapping(db.Model):
    """AniDB absolute episode order mapping (TVDB S/E → AniDB absolute ep).

    Populated by the weekly AniDB sync job that fetches the anime-lists XML.
    The unique constraint on (tvdb_id, season, episode) enables safe upserts.
    """

    __tablename__ = "anidb_absolute_mappings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tvdb_id: Mapped[int] = mapped_column(Integer, nullable=False)
    season: Mapped[int] = mapped_column(Integer, nullable=False)
    episode: Mapped[int] = mapped_column(Integer, nullable=False)
    anidb_absolute_episode: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str | None] = mapped_column(Text, default="")

    __table_args__ = (
        UniqueConstraint("tvdb_id", "season", "episode", name="uq_anidb_tvdb_se"),
        Index("idx_anidb_mappings_tvdb_id", "tvdb_id"),
    )


class SeriesSettings(db.Model):
    """Per-series configuration flags.

    Primary key is sonarr_series_id for O(1) lookup.
    absolute_order=1 means the series uses AniDB absolute episode ordering
    instead of TVDB season/episode numbering when searching providers.
    """

    __tablename__ = "series_settings"

    sonarr_series_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    absolute_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 0=off, 1=on
    preferred_audio_track_index: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=None
    )
    processing_config: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority_override: Mapped[str | None] = mapped_column(String(20), nullable=True)
    min_attempts_per_day: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 0.71.0: per-series override for foreign-track cleanup. NULL = inherit global
    # `cleanup_foreign_tracks_default`. True/False = explicit opt-in/opt-out.
    cleanup_foreign_tracks: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True, default=None
    )
    # 0.73.0: per-series overrides for LanguageProfile fields.
    # NULL = inherit from assigned profile (which inherits from global).
    forced_preference_override: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )
    hi_preference_override: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    forced_scoring_override: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    target_languages_override: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )  # JSON array string
    cutoff_language_override: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    must_contain_override: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )  # JSON array string
    must_not_contain_override: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )  # JSON array string
    audio_exclude_languages_override: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )  # JSON array string
    # Per-series subtitle format requirement. NULL = inherit global behavior
    # (ASS preferred with SRT fallback). "require_ass" = never fall back to
    # SRT provider results for this series.
    subtitle_format_requirement: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MovieSettings(db.Model):
    """Per-movie configuration mirror of SeriesSettings (minus
    absolute_order which is anime-specific).

    Primary key is radarr_movie_id for O(1) lookup. NULL on override
    columns = inherit from the assigned LanguageProfile which inherits
    from global config. See services.inheritance_resolver.
    """

    __tablename__ = "movie_settings"

    radarr_movie_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    preferred_audio_track_index: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=None
    )
    cleanup_foreign_tracks: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True, default=None
    )
    priority_override: Mapped[str | None] = mapped_column(String(20), nullable=True)
    min_attempts_per_day: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    forced_preference_override: Mapped[str | None] = mapped_column(Text, nullable=True)
    hi_preference_override: Mapped[str | None] = mapped_column(Text, nullable=True)
    forced_scoring_override: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_languages_override: Mapped[str | None] = mapped_column(Text, nullable=True)
    cutoff_language_override: Mapped[str | None] = mapped_column(Text, nullable=True)
    must_contain_override: Mapped[str | None] = mapped_column(Text, nullable=True)
    must_not_contain_override: Mapped[str | None] = mapped_column(Text, nullable=True)
    audio_exclude_languages_override: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    def __init__(self, **kwargs: object) -> None:
        kwargs.setdefault("min_attempts_per_day", 0)
        super().__init__(**kwargs)


class SubtitleAutomationQueueEntry(db.Model):
    """Persistent drain queue for subtitle automation work (0.71.0).

    One row per (wanted_item, task_type) waiting for the drain worker. Rows
    survive restarts so work can resume across deploys without losing state.

    `task_type` distinguishes the two kinds of work the worker performs:
    `embedded_extract` (pull a target-language track out of the container,
    the only thing this queue held before 1.11.3) and `sidecar_translate`
    (translate an external source-language sidecar found on disk). The two
    are not mutually exclusive for one item, which is why `wanted_item_id`
    is no longer unique on its own.

    State machine: pending → running → done | failed. Failed rows carry
    `last_error` + `next_retry_at` for backoff-driven retries.
    """

    __tablename__ = "subtitle_automation_queue"

    TASK_EMBEDDED_EXTRACT = "embedded_extract"
    TASK_SIDECAR_TRANSLATE = "sidecar_translate"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    wanted_item_id: Mapped[int] = mapped_column(Integer, nullable=False)
    # String(24) fits both values with room to spare. The 1.11.2 incident was a
    # VARCHAR(16) that a 17-character status did not fit — SQLite ignores the
    # length, so CI would not have caught a repeat.
    task_type: Mapped[str] = mapped_column(
        String(24), nullable=False, default=TASK_EMBEDDED_EXTRACT
    )
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    target_language: Mapped[str] = mapped_column(String(8), nullable=False)
    # Only meaningful for sidecar_translate: the language of the source file.
    source_language: Mapped[str | None] = mapped_column(String(8), nullable=True)
    state: Mapped[str] = mapped_column(String(10), nullable=False, default="pending")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index(
            "idx_subtitle_automation_queue_drain",
            "state",
            "next_retry_at",
        ),
        UniqueConstraint("wanted_item_id", "task_type", name="uq_automation_queue_item_task"),
    )


class FansubPreference(db.Model):
    """Per-series fansub group preferences for subtitle result scoring.

    preferred_groups_json / excluded_groups_json: JSON-encoded list of group
    name strings (case-insensitive substring match against result.release_info).
    bonus: Score points added for preferred group hits; excluded hits get -999.
    """

    __tablename__ = "fansub_preferences"

    sonarr_series_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    preferred_groups_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    excluded_groups_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    bonus: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ProviderLearnedLimit(db.Model):
    """Observed rate-limit adjustments per (provider, window).

    Written by the budget manager when a provider returns HTTP 429; read by
    the budget manager to scale declared limits. See Phase 3 plan.
    """

    __tablename__ = "provider_learned_limits"

    provider_name: Mapped[str] = mapped_column(String(50), primary_key=True)
    window_type: Mapped[str] = mapped_column(String(10), primary_key=True)
    configured_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    observed_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    adjustment_factor: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    last_429_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consecutive_good_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class ProviderAccountPool(db.Model):
    """Multi-API-key pool per provider for budget aggregation (Phase 4a)."""

    __tablename__ = "provider_account_pools"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider_name: Mapped[str] = mapped_column(String(50), nullable=False)
    account_label: Mapped[str] = mapped_column(String(100), nullable=False)
    api_key: Mapped[str] = mapped_column(String(500), nullable=False)
    username: Mapped[str | None] = mapped_column(String(200), nullable=True)
    password: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Provider-account credential (not a user login). Encrypted at rest via
    # ProviderAccountPoolRepository (config_crypto Fernet); back-filled by
    # migration c9d0e1f2a3b4_encrypt_sensitive_at_rest.
    tier: Mapped[str] = mapped_column(String(20), nullable=False, default="free")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_429_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    __table_args__ = (
        UniqueConstraint("provider_name", "account_label", name="uq_pool_provider_label"),
        Index("ix_pool_provider_enabled", "provider_name", "enabled"),
    )


class SubtitleHealthFinding(db.Model):
    """A persisted subtitle-health issue for one target (sidecar or stream)."""

    __tablename__ = "subtitle_health_findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    episode_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    target_kind: Mapped[str] = mapped_column(Text, nullable=False)
    target_path: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    stream_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lang: Mapped[str] = mapped_column(Text, nullable=False, default="und")
    issue_type: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    snippets_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    raw_hash: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(Text, nullable=False, default="open")
    scanner_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    suggested_fix: Mapped[str | None] = mapped_column(Text, nullable=True)


class SubtitleHealthFix(db.Model):
    """A manifest row for an applied fix — enables rollback."""

    __tablename__ = "subtitle_health_fixes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    finding_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    fixer: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    target_path: Mapped[str] = mapped_column(Text, nullable=False)
    trashed_original_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_hash: Mapped[str] = mapped_column(Text, nullable=False, default="")
    fixed_hash: Mapped[str] = mapped_column(Text, nullable=False, default="")
    fixer_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    reversible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


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
    "ChapterCache",
    "BlacklistEntry",
    "PostProcessingRun",
    "FilterPreset",
    "AnidbAbsoluteMapping",
    "SeriesSettings",
    "MovieSettings",
    "SubtitleAutomationQueueEntry",
    "FansubPreference",
    "ProviderLearnedLimit",
    "ProviderAccountPool",
    "SubtitleHealthFinding",
    "SubtitleHealthFix",
]
