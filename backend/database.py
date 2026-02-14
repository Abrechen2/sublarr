"""SQLite database models and helpers for persistent storage.

Uses raw sqlite3 for minimal dependencies. Stores translation jobs,
daily statistics, and runtime configuration.
"""

import os
import json
import uuid
import sqlite3
import logging
import threading
from datetime import datetime, date
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


# ─── Job Operations ───────────────────────────────────────────────────────────


def create_job(file_path: str, force: bool = False, arr_context: dict = None) -> dict:
    """Create a new translation job in the database."""
    job_id = str(uuid.uuid4())[:8]
    now = datetime.utcnow().isoformat()
    context_json = json.dumps(arr_context) if arr_context else ""

    db = get_db()
    with _db_lock:
        db.execute(
            """INSERT INTO jobs (id, file_path, status, force, bazarr_context_json, created_at)
               VALUES (?, ?, 'queued', ?, ?, ?)""",
            (job_id, file_path, int(force), context_json, now),
        )
        db.commit()

    return {
        "id": job_id,
        "file_path": file_path,
        "status": "queued",
        "force": force,
        "arr_context": arr_context,
        "created_at": now,
        "completed_at": None,
        "result": None,
        "error": None,
    }


def update_job(job_id: str, status: str, result: dict = None, error: str = None):
    """Update a job's status and result."""
    now = datetime.utcnow().isoformat() if status in ("completed", "failed") else ""
    stats_json = json.dumps(result.get("stats", {})) if result else "{}"
    output_path = result.get("output_path", "") if result else ""
    source_format = ""
    config_hash = ""
    if result and result.get("stats"):
        source_format = result["stats"].get("format", "")
        config_hash = result["stats"].get("config_hash", "")

    db = get_db()
    with _db_lock:
        db.execute(
            """UPDATE jobs SET status=?, stats_json=?, output_path=?,
               source_format=?, error=?, completed_at=?, config_hash=?
               WHERE id=?""",
            (status, stats_json, output_path, source_format, error or "", now,
             config_hash, job_id),
        )
        db.commit()


def get_job(job_id: str) -> Optional[dict]:
    """Get a job by ID."""
    db = get_db()
    with _db_lock:
        row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not row:
        return None
    return _row_to_job(row)


def get_jobs(page: int = 1, per_page: int = 50, status: str = None) -> dict:
    """Get paginated job list."""
    db = get_db()
    offset = (page - 1) * per_page

    with _db_lock:
        if status:
            count = db.execute(
                "SELECT COUNT(*) FROM jobs WHERE status=?", (status,)
            ).fetchone()[0]
            rows = db.execute(
                "SELECT * FROM jobs WHERE status=? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (status, per_page, offset),
            ).fetchall()
        else:
            count = db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
            rows = db.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (per_page, offset),
            ).fetchall()

    total_pages = max(1, (count + per_page - 1) // per_page)
    return {
        "data": [_row_to_job(r) for r in rows],
        "page": page,
        "per_page": per_page,
        "total": count,
        "total_pages": total_pages,
    }


def get_pending_job_count() -> int:
    """Get count of queued/running jobs."""
    db = get_db()
    with _db_lock:
        row = db.execute(
            "SELECT COUNT(*) FROM jobs WHERE status IN ('queued', 'running')"
        ).fetchone()
    return row[0]


def _row_to_job(row) -> dict:
    """Convert a database row to a job dict."""
    d = dict(row)
    # Parse JSON fields
    if d.get("stats_json"):
        try:
            d["stats"] = json.loads(d["stats_json"])
        except json.JSONDecodeError:
            d["stats"] = {}
    else:
        d["stats"] = {}
    del d["stats_json"]

    if d.get("bazarr_context_json"):
        try:
            d["arr_context"] = json.loads(d["bazarr_context_json"])
        except json.JSONDecodeError:
            d["arr_context"] = None
    else:
        d["arr_context"] = None
    del d["bazarr_context_json"]

    d["force"] = bool(d.get("force", 0))
    return d


# ─── Stats Operations ────────────────────────────────────────────────────────


def record_stat(success: bool, skipped: bool = False, fmt: str = "", source: str = ""):
    """Record a translation result in daily stats."""
    today = date.today().isoformat()
    db = get_db()

    with _db_lock:
        row = db.execute("SELECT * FROM daily_stats WHERE date=?", (today,)).fetchone()

        if row:
            data = dict(row)
            by_format = json.loads(data.get("by_format_json", "{}"))
            by_source = json.loads(data.get("by_source_json", "{}"))

            if success and not skipped:
                data["translated"] = data["translated"] + 1
                if fmt:
                    by_format[fmt] = by_format.get(fmt, 0) + 1
                if source:
                    by_source[source] = by_source.get(source, 0) + 1
            elif success and skipped:
                data["skipped"] = data["skipped"] + 1
            else:
                data["failed"] = data["failed"] + 1

            db.execute(
                """UPDATE daily_stats SET translated=?, failed=?, skipped=?,
                   by_format_json=?, by_source_json=? WHERE date=?""",
                (data["translated"], data["failed"], data["skipped"],
                 json.dumps(by_format), json.dumps(by_source), today),
            )
        else:
            by_format = {}
            by_source = {}
            translated = 0
            failed = 0
            skip_count = 0

            if success and not skipped:
                translated = 1
                if fmt:
                    by_format[fmt] = 1
                if source:
                    by_source[source] = 1
            elif success and skipped:
                skip_count = 1
            else:
                failed = 1

            db.execute(
                """INSERT INTO daily_stats (date, translated, failed, skipped, by_format_json, by_source_json)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (today, translated, failed, skip_count, json.dumps(by_format), json.dumps(by_source)),
            )
        db.commit()


def get_stats_summary() -> dict:
    """Get aggregated stats summary."""
    db = get_db()
    with _db_lock:
        rows = db.execute("SELECT * FROM daily_stats ORDER BY date DESC LIMIT 30").fetchall()

    total_translated = 0
    total_failed = 0
    total_skipped = 0
    by_format_total = {}
    by_source_total = {}
    daily = []

    for row in rows:
        d = dict(row)
        total_translated += d["translated"]
        total_failed += d["failed"]
        total_skipped += d["skipped"]

        by_format = json.loads(d.get("by_format_json", "{}"))
        for k, v in by_format.items():
            by_format_total[k] = by_format_total.get(k, 0) + v

        by_source = json.loads(d.get("by_source_json", "{}"))
        for k, v in by_source.items():
            by_source_total[k] = by_source_total.get(k, 0) + v

        daily.append({
            "date": d["date"],
            "translated": d["translated"],
            "failed": d["failed"],
            "skipped": d["skipped"],
        })

    # Today's stats
    with _db_lock:
        today_row = db.execute(
            "SELECT * FROM daily_stats WHERE date=?", (date.today().isoformat(),)
        ).fetchone()
    today_translated = dict(today_row)["translated"] if today_row else 0

    return {
        "total_translated": total_translated,
        "total_failed": total_failed,
        "total_skipped": total_skipped,
        "today_translated": today_translated,
        "by_format": by_format_total,
        "by_source": by_source_total,
        "daily": daily,
    }


# ─── Config Operations ───────────────────────────────────────────────────────


def save_config_entry(key: str, value: str):
    """Save a config entry to the database."""
    now = datetime.utcnow().isoformat()
    db = get_db()
    with _db_lock:
        db.execute(
            """INSERT OR REPLACE INTO config_entries (key, value, updated_at)
               VALUES (?, ?, ?)""",
            (key, value, now),
        )
        db.commit()


def get_config_entry(key: str) -> Optional[str]:
    """Get a config entry from the database."""
    db = get_db()
    with _db_lock:
        row = db.execute("SELECT value FROM config_entries WHERE key=?", (key,)).fetchone()
    return row[0] if row else None


def get_all_config_entries() -> dict:
    """Get all config entries."""
    db = get_db()
    with _db_lock:
        rows = db.execute("SELECT key, value FROM config_entries").fetchall()
    return {row[0]: row[1] for row in rows}


# ─── Provider Cache Operations ───────────────────────────────────────────────


def cache_provider_results(provider_name: str, query_hash: str, results_json: str, ttl_hours: int = 6):
    """Cache provider search results."""
    now = datetime.utcnow()
    expires = now + __import__("datetime").timedelta(hours=ttl_hours)
    db = get_db()
    with _db_lock:
        db.execute(
            """INSERT INTO provider_cache (provider_name, query_hash, results_json, cached_at, expires_at)
               VALUES (?, ?, ?, ?, ?)""",
            (provider_name, query_hash, results_json, now.isoformat(), expires.isoformat()),
        )
        db.commit()


def get_cached_results(provider_name: str, query_hash: str) -> Optional[str]:
    """Get cached provider results if not expired."""
    now = datetime.utcnow().isoformat()
    db = get_db()
    with _db_lock:
        row = db.execute(
            """SELECT results_json FROM provider_cache
               WHERE provider_name=? AND query_hash=? AND expires_at > ?
               ORDER BY cached_at DESC LIMIT 1""",
            (provider_name, query_hash, now),
        ).fetchone()
    return row[0] if row else None


def cleanup_expired_cache():
    """Remove expired cache entries."""
    now = datetime.utcnow().isoformat()
    db = get_db()
    with _db_lock:
        db.execute("DELETE FROM provider_cache WHERE expires_at < ?", (now,))
        db.commit()


def get_provider_cache_stats() -> dict:
    """Get aggregated cache stats per provider (total entries, active/expired)."""
    now = datetime.utcnow().isoformat()
    db = get_db()
    with _db_lock:
        rows = db.execute(
            """SELECT provider_name, COUNT(*) as total,
                      SUM(CASE WHEN expires_at > ? THEN 1 ELSE 0 END) as active
               FROM provider_cache GROUP BY provider_name""",
            (now,),
        ).fetchall()
    return {row[0]: {"total": row[1], "active": row[2]} for row in rows}


def get_provider_download_stats() -> dict:
    """Get download counts per provider, broken down by format."""
    db = get_db()
    with _db_lock:
        rows = db.execute(
            """SELECT provider_name, format, COUNT(*) as count
               FROM subtitle_downloads GROUP BY provider_name, format"""
        ).fetchall()

    stats: dict = {}
    for row in rows:
        name = row[0]
        fmt = row[1] or "unknown"
        count = row[2]
        if name not in stats:
            stats[name] = {"total": 0, "by_format": {}}
        stats[name]["total"] += count
        stats[name]["by_format"][fmt] = count
    return stats


def clear_provider_cache(provider_name: str = None):
    """Clear provider cache. If provider_name is given, only clear that provider."""
    db = get_db()
    with _db_lock:
        if provider_name:
            db.execute("DELETE FROM provider_cache WHERE provider_name=?", (provider_name,))
        else:
            db.execute("DELETE FROM provider_cache")
        db.commit()


def record_subtitle_download(provider_name: str, subtitle_id: str, language: str,
                              fmt: str, file_path: str, score: int):
    """Record a subtitle download for history tracking."""
    now = datetime.utcnow().isoformat()
    db = get_db()
    with _db_lock:
        db.execute(
            """INSERT INTO subtitle_downloads
               (provider_name, subtitle_id, language, format, file_path, score, downloaded_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (provider_name, subtitle_id, language, fmt, file_path, score, now),
        )
        db.commit()


# ─── Wanted Operations ──────────────────────────────────────────────────────


def upsert_wanted_item(item_type: str, file_path: str, title: str = "",
                       season_episode: str = "", existing_sub: str = "",
                       missing_languages: list = None,
                       sonarr_series_id: int = None,
                       sonarr_episode_id: int = None,
                       radarr_movie_id: int = None,
                       upgrade_candidate: bool = False,
                       current_score: int = 0,
                       target_language: str = "") -> int:
    """Insert or update a wanted item (matched on file_path + target_language).

    Returns the row id.
    """
    now = datetime.utcnow().isoformat()
    langs_json = json.dumps(missing_languages or [])
    upgrade_int = 1 if upgrade_candidate else 0
    db = get_db()

    with _db_lock:
        # Match on file_path + target_language for multi-language support
        if target_language:
            existing = db.execute(
                "SELECT id, status FROM wanted_items WHERE file_path=? AND target_language=?",
                (file_path, target_language),
            ).fetchone()
        else:
            existing = db.execute(
                "SELECT id, status FROM wanted_items WHERE file_path=? AND (target_language='' OR target_language IS NULL)",
                (file_path,),
            ).fetchone()

        if existing:
            row_id = existing[0]
            # Don't overwrite 'ignored' status
            if existing[1] == "ignored":
                db.execute(
                    """UPDATE wanted_items SET title=?, season_episode=?, existing_sub=?,
                       missing_languages=?, sonarr_series_id=?, sonarr_episode_id=?,
                       radarr_movie_id=?, upgrade_candidate=?, current_score=?,
                       target_language=?, updated_at=?
                       WHERE id=?""",
                    (title, season_episode, existing_sub, langs_json,
                     sonarr_series_id, sonarr_episode_id, radarr_movie_id,
                     upgrade_int, current_score, target_language, now, row_id),
                )
            else:
                db.execute(
                    """UPDATE wanted_items SET item_type=?, title=?, season_episode=?,
                       existing_sub=?, missing_languages=?, status='wanted',
                       sonarr_series_id=?, sonarr_episode_id=?, radarr_movie_id=?,
                       upgrade_candidate=?, current_score=?,
                       target_language=?, updated_at=?
                       WHERE id=?""",
                    (item_type, title, season_episode, existing_sub, langs_json,
                     sonarr_series_id, sonarr_episode_id, radarr_movie_id,
                     upgrade_int, current_score, target_language, now, row_id),
                )
        else:
            cursor = db.execute(
                """INSERT INTO wanted_items
                   (item_type, file_path, title, season_episode, existing_sub,
                    missing_languages, sonarr_series_id, sonarr_episode_id,
                    radarr_movie_id, upgrade_candidate, current_score,
                    target_language, status, added_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'wanted', ?, ?)""",
                (item_type, file_path, title, season_episode, existing_sub,
                 langs_json, sonarr_series_id, sonarr_episode_id,
                 radarr_movie_id, upgrade_int, current_score,
                 target_language, now, now),
            )
            row_id = cursor.lastrowid
        db.commit()

    return row_id


def get_wanted_items(page: int = 1, per_page: int = 50,
                     item_type: str = None, status: str = None,
                     series_id: int = None) -> dict:
    """Get paginated wanted items with optional filters."""
    db = get_db()
    offset = (page - 1) * per_page

    conditions = []
    params = []
    if item_type:
        conditions.append("item_type=?")
        params.append(item_type)
    if status:
        conditions.append("status=?")
        params.append(status)
    if series_id is not None:
        conditions.append("sonarr_series_id=?")
        params.append(series_id)

    where = " WHERE " + " AND ".join(conditions) if conditions else ""

    with _db_lock:
        count = db.execute(
            f"SELECT COUNT(*) FROM wanted_items{where}", params
        ).fetchone()[0]
        rows = db.execute(
            f"SELECT * FROM wanted_items{where} ORDER BY added_at DESC LIMIT ? OFFSET ?",
            params + [per_page, offset],
        ).fetchall()

    total_pages = max(1, (count + per_page - 1) // per_page)
    return {
        "data": [_row_to_wanted(r) for r in rows],
        "page": page,
        "per_page": per_page,
        "total": count,
        "total_pages": total_pages,
    }


def get_wanted_item(item_id: int) -> Optional[dict]:
    """Get a single wanted item by ID."""
    db = get_db()
    with _db_lock:
        row = db.execute("SELECT * FROM wanted_items WHERE id=?", (item_id,)).fetchone()
    if not row:
        return None
    return _row_to_wanted(row)


def update_wanted_status(item_id: int, status: str, error: str = ""):
    """Update a wanted item's status."""
    now = datetime.utcnow().isoformat()
    db = get_db()
    with _db_lock:
        db.execute(
            "UPDATE wanted_items SET status=?, error=?, updated_at=? WHERE id=?",
            (status, error, now, item_id),
        )
        db.commit()


def update_wanted_search(item_id: int):
    """Increment search_count and set last_search_at."""
    now = datetime.utcnow().isoformat()
    db = get_db()
    with _db_lock:
        db.execute(
            "UPDATE wanted_items SET search_count=search_count+1, last_search_at=?, updated_at=? WHERE id=?",
            (now, now, item_id),
        )
        db.commit()


def delete_wanted_items(file_paths: list):
    """Delete wanted items by file paths (batch)."""
    if not file_paths:
        return
    db = get_db()
    placeholders = ",".join("?" for _ in file_paths)
    with _db_lock:
        db.execute(
            f"DELETE FROM wanted_items WHERE file_path IN ({placeholders})",
            file_paths,
        )
        db.commit()


def delete_wanted_item(item_id: int):
    """Delete a single wanted item."""
    db = get_db()
    with _db_lock:
        db.execute("DELETE FROM wanted_items WHERE id=?", (item_id,))
        db.commit()


def get_wanted_count(status: str = None) -> int:
    """Get count of wanted items with optional status filter."""
    db = get_db()
    with _db_lock:
        if status:
            row = db.execute(
                "SELECT COUNT(*) FROM wanted_items WHERE status=?", (status,)
            ).fetchone()
        else:
            row = db.execute("SELECT COUNT(*) FROM wanted_items").fetchone()
    return row[0]


def get_wanted_summary() -> dict:
    """Get aggregated wanted counts by type, status, and existing_sub."""
    db = get_db()
    with _db_lock:
        total = db.execute("SELECT COUNT(*) FROM wanted_items").fetchone()[0]

        by_type = {}
        for row in db.execute(
            "SELECT item_type, COUNT(*) FROM wanted_items GROUP BY item_type"
        ).fetchall():
            by_type[row[0]] = row[1]

        by_status = {}
        for row in db.execute(
            "SELECT status, COUNT(*) FROM wanted_items GROUP BY status"
        ).fetchall():
            by_status[row[0]] = row[1]

        by_existing = {}
        for row in db.execute(
            "SELECT existing_sub, COUNT(*) FROM wanted_items GROUP BY existing_sub"
        ).fetchall():
            key = row[0] if row[0] else "none"
            by_existing[key] = row[1]

        upgradeable = db.execute(
            "SELECT COUNT(*) FROM wanted_items WHERE upgrade_candidate=1"
        ).fetchone()[0]

    return {
        "total": total,
        "by_type": by_type,
        "by_status": by_status,
        "by_existing": by_existing,
        "upgradeable": upgradeable,
    }


def get_all_wanted_file_paths() -> set:
    """Get all file paths currently in the wanted table (for cleanup)."""
    db = get_db()
    with _db_lock:
        rows = db.execute("SELECT file_path FROM wanted_items").fetchall()
    return {row[0] for row in rows}


def get_wanted_items_for_cleanup() -> list:
    """Get wanted items with file_path, target_language, and id for cleanup."""
    db = get_db()
    with _db_lock:
        rows = db.execute(
            "SELECT id, file_path, target_language FROM wanted_items"
        ).fetchall()
    return [{"id": r[0], "file_path": r[1], "target_language": r[2] or ""} for r in rows]


def delete_wanted_items_by_ids(item_ids: list):
    """Delete wanted items by their IDs (batch)."""
    if not item_ids:
        return
    db = get_db()
    placeholders = ",".join("?" for _ in item_ids)
    with _db_lock:
        db.execute(
            f"DELETE FROM wanted_items WHERE id IN ({placeholders})",
            item_ids,
        )
        db.commit()


def get_wanted_item_by_path(file_path: str) -> Optional[dict]:
    """Get a wanted item by file path."""
    db = get_db()
    with _db_lock:
        row = db.execute(
            "SELECT * FROM wanted_items WHERE file_path=?", (file_path,)
        ).fetchone()
    if not row:
        return None
    return _row_to_wanted(row)


def get_upgradeable_count() -> int:
    """Get count of items marked as upgrade candidates."""
    db = get_db()
    with _db_lock:
        row = db.execute(
            "SELECT COUNT(*) FROM wanted_items WHERE upgrade_candidate=1"
        ).fetchone()
    return row[0]


def _row_to_wanted(row) -> dict:
    """Convert a database row to a wanted item dict."""
    d = dict(row)
    if d.get("missing_languages"):
        try:
            d["missing_languages"] = json.loads(d["missing_languages"])
        except json.JSONDecodeError:
            d["missing_languages"] = []
    else:
        d["missing_languages"] = []
    return d


# ─── Upgrade History Operations ──────────────────────────────────────────────


def record_upgrade(file_path: str, old_format: str, old_score: int,
                   new_format: str, new_score: int,
                   provider_name: str = "", upgrade_reason: str = ""):
    """Record a subtitle upgrade in history."""
    now = datetime.utcnow().isoformat()
    db = get_db()
    with _db_lock:
        db.execute(
            """INSERT INTO upgrade_history
               (file_path, old_format, old_score, new_format, new_score,
                provider_name, upgrade_reason, upgraded_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (file_path, old_format, old_score, new_format, new_score,
             provider_name, upgrade_reason, now),
        )
        db.commit()


def get_upgrade_history(limit: int = 50) -> list:
    """Get recent upgrade history entries."""
    db = get_db()
    with _db_lock:
        rows = db.execute(
            "SELECT * FROM upgrade_history ORDER BY upgraded_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_upgrade_stats() -> dict:
    """Get aggregated upgrade statistics."""
    db = get_db()
    with _db_lock:
        total = db.execute("SELECT COUNT(*) FROM upgrade_history").fetchone()[0]
        srt_to_ass = db.execute(
            "SELECT COUNT(*) FROM upgrade_history WHERE old_format='srt' AND new_format='ass'"
        ).fetchone()[0]
    return {"total": total, "srt_to_ass": srt_to_ass}


# ─── Translation Config History Operations ────────────────────────────────────


def record_translation_config(config_hash: str, ollama_model: str,
                               prompt_template: str, target_language: str):
    """Record or update a translation config hash."""
    now = datetime.utcnow().isoformat()
    db = get_db()
    with _db_lock:
        existing = db.execute(
            "SELECT id FROM translation_config_history WHERE config_hash=?",
            (config_hash,),
        ).fetchone()
        if existing:
            db.execute(
                "UPDATE translation_config_history SET last_used_at=? WHERE config_hash=?",
                (now, config_hash),
            )
        else:
            db.execute(
                """INSERT INTO translation_config_history
                   (config_hash, ollama_model, prompt_template, target_language,
                    first_used_at, last_used_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (config_hash, ollama_model, prompt_template, target_language, now, now),
            )
        db.commit()


def get_outdated_jobs_count(current_hash: str) -> int:
    """Get count of completed jobs with a different config hash."""
    db = get_db()
    with _db_lock:
        row = db.execute(
            """SELECT COUNT(*) FROM jobs
               WHERE status='completed' AND config_hash != '' AND config_hash != ?""",
            (current_hash,),
        ).fetchone()
    return row[0]


def get_outdated_jobs(current_hash: str, limit: int = 100) -> list:
    """Get completed jobs with a different config hash (candidates for re-translation)."""
    db = get_db()
    with _db_lock:
        rows = db.execute(
            """SELECT * FROM jobs
               WHERE status='completed' AND config_hash != '' AND config_hash != ?
               ORDER BY completed_at DESC LIMIT ?""",
            (current_hash, limit),
        ).fetchall()
    return [_row_to_job(r) for r in rows]


# ─── Language Profile Operations ──────────────────────────────────────────────


def _row_to_profile(row) -> dict:
    """Convert a database row to a language profile dict."""
    d = dict(row)
    d["is_default"] = bool(d.get("is_default", 0))
    try:
        d["target_languages"] = json.loads(d.get("target_languages_json", "[]"))
    except json.JSONDecodeError:
        d["target_languages"] = []
    del d["target_languages_json"]
    try:
        d["target_language_names"] = json.loads(d.get("target_language_names_json", "[]"))
    except json.JSONDecodeError:
        d["target_language_names"] = []
    del d["target_language_names_json"]
    return d


def create_language_profile(name: str, source_lang: str, source_name: str,
                             target_langs: list[str], target_names: list[str]) -> int:
    """Create a new language profile. Returns the profile ID."""
    now = datetime.utcnow().isoformat()
    db = get_db()
    with _db_lock:
        cursor = db.execute(
            """INSERT INTO language_profiles
               (name, source_language, source_language_name,
                target_languages_json, target_language_names_json,
                is_default, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, 0, ?, ?)""",
            (name, source_lang, source_name,
             json.dumps(target_langs), json.dumps(target_names),
             now, now),
        )
        profile_id = cursor.lastrowid
        db.commit()
    return profile_id


def get_language_profile(profile_id: int) -> Optional[dict]:
    """Get a language profile by ID."""
    db = get_db()
    with _db_lock:
        row = db.execute(
            "SELECT * FROM language_profiles WHERE id=?", (profile_id,)
        ).fetchone()
    if not row:
        return None
    return _row_to_profile(row)


def get_all_language_profiles() -> list[dict]:
    """Get all language profiles, default first."""
    db = get_db()
    with _db_lock:
        rows = db.execute(
            "SELECT * FROM language_profiles ORDER BY is_default DESC, name ASC"
        ).fetchall()
    return [_row_to_profile(r) for r in rows]


def update_language_profile(profile_id: int, **fields):
    """Update a language profile's fields."""
    now = datetime.utcnow().isoformat()
    db = get_db()

    allowed = {"name", "source_language", "source_language_name",
               "target_languages", "target_language_names"}
    updates = []
    params = []

    for key, value in fields.items():
        if key not in allowed:
            continue
        if key == "target_languages":
            updates.append("target_languages_json=?")
            params.append(json.dumps(value))
        elif key == "target_language_names":
            updates.append("target_language_names_json=?")
            params.append(json.dumps(value))
        else:
            updates.append(f"{key}=?")
            params.append(value)

    if not updates:
        return

    updates.append("updated_at=?")
    params.append(now)
    params.append(profile_id)

    with _db_lock:
        db.execute(
            f"UPDATE language_profiles SET {', '.join(updates)} WHERE id=?",
            params,
        )
        db.commit()


def delete_language_profile(profile_id: int) -> bool:
    """Delete a language profile (cannot delete default). Returns True if deleted."""
    db = get_db()
    with _db_lock:
        row = db.execute(
            "SELECT is_default FROM language_profiles WHERE id=?", (profile_id,)
        ).fetchone()
        if not row:
            return False
        if row[0]:
            return False  # Cannot delete default profile

        db.execute("DELETE FROM language_profiles WHERE id=?", (profile_id,))
        # Assignments using this profile are cascaded by FK
        db.commit()
    return True


def get_default_profile() -> dict:
    """Get the default language profile."""
    db = get_db()
    with _db_lock:
        row = db.execute(
            "SELECT * FROM language_profiles WHERE is_default=1"
        ).fetchone()
    if not row:
        # Fallback: return first profile
        with _db_lock:
            row = db.execute(
                "SELECT * FROM language_profiles ORDER BY id ASC LIMIT 1"
            ).fetchone()
    if not row:
        # No profiles at all — return synthetic default from config
        s = get_settings()
        return {
            "id": 0,
            "name": "Default",
            "source_language": s.source_language,
            "source_language_name": s.source_language_name,
            "target_languages": [s.target_language],
            "target_language_names": [s.target_language_name],
            "is_default": True,
        }
    return _row_to_profile(row)


def get_series_profile(sonarr_series_id: int) -> dict:
    """Get the language profile assigned to a series. Falls back to default."""
    db = get_db()
    with _db_lock:
        row = db.execute(
            """SELECT lp.* FROM language_profiles lp
               JOIN series_language_profiles slp ON slp.profile_id = lp.id
               WHERE slp.sonarr_series_id=?""",
            (sonarr_series_id,),
        ).fetchone()
    if row:
        return _row_to_profile(row)
    return get_default_profile()


def get_movie_profile(radarr_movie_id: int) -> dict:
    """Get the language profile assigned to a movie. Falls back to default."""
    db = get_db()
    with _db_lock:
        row = db.execute(
            """SELECT lp.* FROM language_profiles lp
               JOIN movie_language_profiles mlp ON mlp.profile_id = lp.id
               WHERE mlp.radarr_movie_id=?""",
            (radarr_movie_id,),
        ).fetchone()
    if row:
        return _row_to_profile(row)
    return get_default_profile()


def assign_series_profile(sonarr_series_id: int, profile_id: int):
    """Assign a language profile to a series."""
    db = get_db()
    with _db_lock:
        db.execute(
            """INSERT OR REPLACE INTO series_language_profiles
               (sonarr_series_id, profile_id) VALUES (?, ?)""",
            (sonarr_series_id, profile_id),
        )
        db.commit()


def assign_movie_profile(radarr_movie_id: int, profile_id: int):
    """Assign a language profile to a movie."""
    db = get_db()
    with _db_lock:
        db.execute(
            """INSERT OR REPLACE INTO movie_language_profiles
               (radarr_movie_id, profile_id) VALUES (?, ?)""",
            (radarr_movie_id, profile_id),
        )
        db.commit()


def get_series_profile_assignments() -> dict[int, int]:
    """Get all series -> profile_id assignments."""
    db = get_db()
    with _db_lock:
        rows = db.execute("SELECT sonarr_series_id, profile_id FROM series_language_profiles").fetchall()
    return {row[0]: row[1] for row in rows}


def get_movie_profile_assignments() -> dict[int, int]:
    """Get all movie -> profile_id assignments."""
    db = get_db()
    with _db_lock:
        rows = db.execute("SELECT radarr_movie_id, profile_id FROM movie_language_profiles").fetchall()
    return {row[0]: row[1] for row in rows}
