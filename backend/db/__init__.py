"""Database package - Schema, connection management, and migrations.

Provides thread-safe singleton SQLite connection with WAL mode.
Domain modules import get_db and _db_lock from this package.
"""

import os
import json
import sqlite3
import logging
import threading
from datetime import datetime
from typing import Optional

from config import get_settings

logger = logging.getLogger(__name__)

_db_lock = threading.Lock()
_connection: Optional[sqlite3.Connection] = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    file_path TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    source_format TEXT DEFAULT '',
    output_path TEXT DEFAULT '',
    stats_json TEXT DEFAULT '{}',
    error TEXT DEFAULT '',
    force INTEGER DEFAULT 0,
    bazarr_context_json TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    completed_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS daily_stats (
    date TEXT PRIMARY KEY,
    translated INTEGER DEFAULT 0,
    failed INTEGER DEFAULT 0,
    skipped INTEGER DEFAULT 0,
    by_format_json TEXT DEFAULT '{"ass": 0, "srt": 0}',
    by_source_json TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS config_entries (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS provider_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_name TEXT NOT NULL,
    query_hash TEXT NOT NULL,
    results_json TEXT NOT NULL,
    cached_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS subtitle_downloads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_name TEXT NOT NULL,
    subtitle_id TEXT NOT NULL,
    language TEXT NOT NULL,
    format TEXT DEFAULT '',
    file_path TEXT NOT NULL,
    score INTEGER DEFAULT 0,
    downloaded_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at);
CREATE INDEX IF NOT EXISTS idx_provider_cache_hash ON provider_cache(provider_name, query_hash);
CREATE INDEX IF NOT EXISTS idx_provider_cache_expires ON provider_cache(expires_at);
CREATE INDEX IF NOT EXISTS idx_subtitle_downloads_path ON subtitle_downloads(file_path);

CREATE TABLE IF NOT EXISTS wanted_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_type TEXT NOT NULL,
    sonarr_series_id INTEGER,
    sonarr_episode_id INTEGER,
    radarr_movie_id INTEGER,
    title TEXT NOT NULL DEFAULT '',
    season_episode TEXT DEFAULT '',
    file_path TEXT NOT NULL,
    existing_sub TEXT DEFAULT '',
    missing_languages TEXT DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'wanted',
    last_search_at TEXT DEFAULT '',
    search_count INTEGER DEFAULT 0,
    error TEXT DEFAULT '',
    added_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_wanted_status ON wanted_items(status);
CREATE INDEX IF NOT EXISTS idx_wanted_item_type ON wanted_items(item_type);
CREATE INDEX IF NOT EXISTS idx_wanted_file_path ON wanted_items(file_path);
CREATE INDEX IF NOT EXISTS idx_wanted_sonarr_series ON wanted_items(sonarr_series_id);
CREATE INDEX IF NOT EXISTS idx_wanted_sonarr_episode ON wanted_items(sonarr_episode_id);
CREATE INDEX IF NOT EXISTS idx_wanted_radarr_movie ON wanted_items(radarr_movie_id);

CREATE TABLE IF NOT EXISTS upgrade_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT NOT NULL,
    old_format TEXT,
    old_score INTEGER,
    new_format TEXT,
    new_score INTEGER,
    provider_name TEXT,
    upgrade_reason TEXT,
    upgraded_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_upgrade_history_path ON upgrade_history(file_path);

CREATE TABLE IF NOT EXISTS translation_config_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    config_hash TEXT NOT NULL UNIQUE,
    ollama_model TEXT,
    prompt_template TEXT,
    target_language TEXT,
    first_used_at TEXT NOT NULL,
    last_used_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS blacklist_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_name TEXT NOT NULL,
    subtitle_id TEXT NOT NULL,
    language TEXT DEFAULT '',
    file_path TEXT DEFAULT '',
    title TEXT DEFAULT '',
    reason TEXT DEFAULT '',
    added_at TEXT NOT NULL,
    UNIQUE(provider_name, subtitle_id)
);

CREATE INDEX IF NOT EXISTS idx_blacklist_provider ON blacklist_entries(provider_name, subtitle_id);

CREATE TABLE IF NOT EXISTS language_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    source_language TEXT NOT NULL DEFAULT 'en',
    source_language_name TEXT NOT NULL DEFAULT 'English',
    target_languages_json TEXT NOT NULL DEFAULT '["de"]',
    target_language_names_json TEXT NOT NULL DEFAULT '["German"]',
    is_default INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS series_language_profiles (
    sonarr_series_id INTEGER PRIMARY KEY,
    profile_id INTEGER NOT NULL,
    FOREIGN KEY (profile_id) REFERENCES language_profiles(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS movie_language_profiles (
    radarr_movie_id INTEGER PRIMARY KEY,
    profile_id INTEGER NOT NULL,
    FOREIGN KEY (profile_id) REFERENCES language_profiles(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ffprobe_cache (
    file_path TEXT PRIMARY KEY,
    mtime REAL NOT NULL,
    probe_data_json TEXT NOT NULL,
    cached_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ffprobe_cache_mtime ON ffprobe_cache(mtime);

CREATE TABLE IF NOT EXISTS glossary_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    series_id INTEGER NOT NULL,
    source_term TEXT NOT NULL,
    target_term TEXT NOT NULL,
    notes TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_glossary_series_id ON glossary_entries(series_id);
CREATE INDEX IF NOT EXISTS idx_glossary_source_term ON glossary_entries(source_term);

CREATE TABLE IF NOT EXISTS prompt_presets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    prompt_template TEXT NOT NULL,
    is_default INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS provider_stats (
    provider_name TEXT PRIMARY KEY,
    total_searches INTEGER DEFAULT 0,
    successful_downloads INTEGER DEFAULT 0,
    failed_downloads INTEGER DEFAULT 0,
    avg_score REAL DEFAULT 0,
    last_success_at TEXT,
    last_failure_at TEXT,
    consecutive_failures INTEGER DEFAULT 0,
    avg_response_time_ms REAL DEFAULT 0,
    last_response_time_ms REAL DEFAULT 0,
    auto_disabled INTEGER DEFAULT 0,
    disabled_until TEXT DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_provider_stats_updated ON provider_stats(updated_at);

CREATE TABLE IF NOT EXISTS anidb_mappings (
    tvdb_id INTEGER PRIMARY KEY,
    anidb_id INTEGER NOT NULL,
    series_title TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_anidb_mappings_anidb_id ON anidb_mappings(anidb_id);
"""


def get_db() -> sqlite3.Connection:
    """Get or create the database connection (thread-safe singleton)."""
    global _connection
    if _connection is not None:
        return _connection

    with _db_lock:
        if _connection is not None:
            return _connection

        settings = get_settings()
        db_dir = os.path.dirname(settings.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

        _connection = sqlite3.connect(
            settings.db_path,
            check_same_thread=False,
            isolation_level="DEFERRED",
        )
        _connection.row_factory = sqlite3.Row
        _connection.execute("PRAGMA journal_mode=WAL")
        _connection.execute("PRAGMA busy_timeout=5000")
        _connection.executescript(SCHEMA)
        _run_migrations(_connection)
        _connection.commit()
        logger.info("Database initialized at %s", settings.db_path)
        return _connection


def close_db():
    """Close the database connection."""
    global _connection
    if _connection:
        _connection.close()
        _connection = None


def init_db():
    """Initialize the database (convenience wrapper for create_app factory)."""
    return get_db()


def _run_migrations(conn):
    """Run schema migrations for columns added after initial release."""
    cursor = conn.execute("PRAGMA table_info(wanted_items)")
    columns = {row[1] for row in cursor.fetchall()}

    if "upgrade_candidate" not in columns:
        conn.execute("ALTER TABLE wanted_items ADD COLUMN upgrade_candidate INTEGER DEFAULT 0")
    if "current_score" not in columns:
        conn.execute("ALTER TABLE wanted_items ADD COLUMN current_score INTEGER DEFAULT 0")

    cursor = conn.execute("PRAGMA table_info(jobs)")
    columns = {row[1] for row in cursor.fetchall()}
    if "config_hash" not in columns:
        conn.execute("ALTER TABLE jobs ADD COLUMN config_hash TEXT DEFAULT ''")

    # Add target_language to wanted_items
    cursor = conn.execute("PRAGMA table_info(wanted_items)")
    columns = {row[1] for row in cursor.fetchall()}
    if "target_language" not in columns:
        conn.execute("ALTER TABLE wanted_items ADD COLUMN target_language TEXT DEFAULT ''")

    # Add instance_name to wanted_items (for multi-library support)
    if "instance_name" not in columns:
        conn.execute("ALTER TABLE wanted_items ADD COLUMN instance_name TEXT DEFAULT ''")

    # Create default language profile if none exists
    row = conn.execute("SELECT COUNT(*) FROM language_profiles").fetchone()
    if row[0] == 0:
        from config import get_settings
        s = get_settings()
        now = datetime.utcnow().isoformat()
        conn.execute(
            """INSERT INTO language_profiles
               (name, source_language, source_language_name,
                target_languages_json, target_language_names_json,
                is_default, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, 1, ?, ?)""",
            ("Default", s.source_language, s.source_language_name,
             json.dumps([s.target_language]),
             json.dumps([s.target_language_name]),
             now, now),
        )

    # Check if glossary_entries table exists (migration for existing DBs)
    try:
        conn.execute("SELECT 1 FROM glossary_entries LIMIT 1")
    except sqlite3.OperationalError:
        # Table doesn't exist, create it
        conn.execute("""
            CREATE TABLE IF NOT EXISTS glossary_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                series_id INTEGER NOT NULL,
                source_term TEXT NOT NULL,
                target_term TEXT NOT NULL,
                notes TEXT DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_glossary_series_id ON glossary_entries(series_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_glossary_source_term ON glossary_entries(source_term)")
        logger.info("Created glossary_entries table")

    # Check if prompt_presets table exists (migration for existing DBs)
    try:
        conn.execute("SELECT 1 FROM prompt_presets LIMIT 1")
    except sqlite3.OperationalError:
        # Table doesn't exist, create it
        conn.execute("""
            CREATE TABLE IF NOT EXISTS prompt_presets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                prompt_template TEXT NOT NULL,
                is_default INTEGER DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        logger.info("Created prompt_presets table")

        # Create default preset from current config
        from config import get_settings
        s = get_settings()
        default_prompt = s.get_prompt_template()
        now = datetime.utcnow().isoformat()
        conn.execute(
            """INSERT INTO prompt_presets (name, prompt_template, is_default, created_at, updated_at)
               VALUES (?, ?, 1, ?, ?)""",
            ("Default", default_prompt, now, now),
        )
        logger.info("Created default prompt preset")

    # Add response time and auto-disable columns to provider_stats
    cursor = conn.execute("PRAGMA table_info(provider_stats)")
    ps_columns = {row[1] for row in cursor.fetchall()}
    if "avg_response_time_ms" not in ps_columns:
        conn.execute("ALTER TABLE provider_stats ADD COLUMN avg_response_time_ms REAL DEFAULT 0")
    if "last_response_time_ms" not in ps_columns:
        conn.execute("ALTER TABLE provider_stats ADD COLUMN last_response_time_ms REAL DEFAULT 0")
    if "auto_disabled" not in ps_columns:
        conn.execute("ALTER TABLE provider_stats ADD COLUMN auto_disabled INTEGER DEFAULT 0")
    if "disabled_until" not in ps_columns:
        conn.execute("ALTER TABLE provider_stats ADD COLUMN disabled_until TEXT DEFAULT ''")

    # Check if anidb_mappings table exists (migration for existing DBs)
    try:
        conn.execute("SELECT 1 FROM anidb_mappings LIMIT 1")
    except sqlite3.OperationalError:
        # Table doesn't exist, create it
        conn.execute("""
            CREATE TABLE IF NOT EXISTS anidb_mappings (
                tvdb_id INTEGER PRIMARY KEY,
                anidb_id INTEGER NOT NULL,
                series_title TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_anidb_mappings_anidb_id ON anidb_mappings(anidb_id)")
        logger.info("Created anidb_mappings table")
