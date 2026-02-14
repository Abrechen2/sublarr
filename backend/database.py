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
        _connection.commit()
        logger.info("Database initialized at %s", settings.db_path)
        return _connection


def close_db():
    """Close the database connection."""
    global _connection
    if _connection:
        _connection.close()
        _connection = None


# ─── Job Operations ───────────────────────────────────────────────────────────


def create_job(file_path: str, force: bool = False, bazarr_context: dict = None) -> dict:
    """Create a new translation job in the database."""
    job_id = str(uuid.uuid4())[:8]
    now = datetime.utcnow().isoformat()
    bazarr_json = json.dumps(bazarr_context) if bazarr_context else ""

    db = get_db()
    with _db_lock:
        db.execute(
            """INSERT INTO jobs (id, file_path, status, force, bazarr_context_json, created_at)
               VALUES (?, ?, 'queued', ?, ?, ?)""",
            (job_id, file_path, int(force), bazarr_json, now),
        )
        db.commit()

    return {
        "id": job_id,
        "file_path": file_path,
        "status": "queued",
        "force": force,
        "bazarr_context": bazarr_context,
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
    if result and result.get("stats"):
        source_format = result["stats"].get("format", "")

    db = get_db()
    with _db_lock:
        db.execute(
            """UPDATE jobs SET status=?, stats_json=?, output_path=?,
               source_format=?, error=?, completed_at=?
               WHERE id=?""",
            (status, stats_json, output_path, source_format, error or "", now, job_id),
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
            d["bazarr_context"] = json.loads(d["bazarr_context_json"])
        except json.JSONDecodeError:
            d["bazarr_context"] = None
    else:
        d["bazarr_context"] = None
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
                       radarr_movie_id: int = None) -> int:
    """Insert or update a wanted item (matched on file_path).

    Returns the row id.
    """
    now = datetime.utcnow().isoformat()
    langs_json = json.dumps(missing_languages or [])
    db = get_db()

    with _db_lock:
        existing = db.execute(
            "SELECT id, status FROM wanted_items WHERE file_path=?", (file_path,)
        ).fetchone()

        if existing:
            row_id = existing[0]
            # Don't overwrite 'ignored' status
            if existing[1] == "ignored":
                db.execute(
                    """UPDATE wanted_items SET title=?, season_episode=?, existing_sub=?,
                       missing_languages=?, sonarr_series_id=?, sonarr_episode_id=?,
                       radarr_movie_id=?, updated_at=?
                       WHERE id=?""",
                    (title, season_episode, existing_sub, langs_json,
                     sonarr_series_id, sonarr_episode_id, radarr_movie_id,
                     now, row_id),
                )
            else:
                db.execute(
                    """UPDATE wanted_items SET item_type=?, title=?, season_episode=?,
                       existing_sub=?, missing_languages=?, status='wanted',
                       sonarr_series_id=?, sonarr_episode_id=?, radarr_movie_id=?,
                       updated_at=?
                       WHERE id=?""",
                    (item_type, title, season_episode, existing_sub, langs_json,
                     sonarr_series_id, sonarr_episode_id, radarr_movie_id,
                     now, row_id),
                )
        else:
            cursor = db.execute(
                """INSERT INTO wanted_items
                   (item_type, file_path, title, season_episode, existing_sub,
                    missing_languages, sonarr_series_id, sonarr_episode_id,
                    radarr_movie_id, status, added_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'wanted', ?, ?)""",
                (item_type, file_path, title, season_episode, existing_sub,
                 langs_json, sonarr_series_id, sonarr_episode_id,
                 radarr_movie_id, now, now),
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

    return {
        "total": total,
        "by_type": by_type,
        "by_status": by_status,
        "by_existing": by_existing,
    }


def get_all_wanted_file_paths() -> set:
    """Get all file paths currently in the wanted table (for cleanup)."""
    db = get_db()
    with _db_lock:
        rows = db.execute("SELECT file_path FROM wanted_items").fetchall()
    return {row[0] for row in rows}


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
