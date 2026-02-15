"""FFprobe cache, episode history, and AniDB mapping database operations."""

import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from db import get_db, _db_lock

logger = logging.getLogger(__name__)


def get_ffprobe_cache(file_path: str, mtime: float) -> Optional[dict]:
    """Get cached ffprobe data if file hasn't changed (mtime matches)."""
    db = get_db()
    with _db_lock:
        row = db.execute(
            "SELECT probe_data_json FROM ffprobe_cache WHERE file_path=? AND mtime=?",
            (file_path, mtime),
        ).fetchone()
    if row:
        try:
            return json.loads(row[0])
        except json.JSONDecodeError:
            return None
    return None


def set_ffprobe_cache(file_path: str, mtime: float, probe_data: dict):
    """Cache ffprobe data for a file."""
    now = datetime.utcnow().isoformat()
    probe_json = json.dumps(probe_data)
    db = get_db()
    with _db_lock:
        db.execute(
            """INSERT OR REPLACE INTO ffprobe_cache (file_path, mtime, probe_data_json, cached_at)
               VALUES (?, ?, ?, ?)""",
            (file_path, mtime, probe_json, now),
        )
        db.commit()


def clear_ffprobe_cache(file_path: str = None):
    """Clear ffprobe cache. If file_path is given, only clear that entry."""
    db = get_db()
    with _db_lock:
        if file_path:
            db.execute("DELETE FROM ffprobe_cache WHERE file_path=?", (file_path,))
        else:
            db.execute("DELETE FROM ffprobe_cache")
        db.commit()


def get_episode_history(file_path: str) -> list:
    """Get combined download + job history for a file path."""
    db = get_db()
    results = []

    # Get subtitle downloads matching the file path (directory-based match)
    # Match on the directory path since subtitle files share the base name
    base = file_path.rsplit('.', 1)[0] if '.' in file_path else file_path
    like_pattern = base + "%"

    with _db_lock:
        # Subtitle downloads
        dl_rows = db.execute(
            """SELECT 'download' as action, provider_name, subtitle_id, language,
                      format, file_path, score, downloaded_at as date
               FROM subtitle_downloads
               WHERE file_path LIKE ?
               ORDER BY downloaded_at DESC LIMIT 50""",
            (like_pattern,),
        ).fetchall()
        for r in dl_rows:
            results.append({
                "action": "download",
                "provider_name": r[1],
                "format": r[4],
                "score": r[6],
                "date": r[7],
                "status": "completed",
                "error": "",
            })

        # Translation jobs
        job_rows = db.execute(
            """SELECT 'translate' as action, file_path, source_format, status,
                      error, created_at as date, config_hash
               FROM jobs
               WHERE file_path LIKE ?
               ORDER BY created_at DESC LIMIT 50""",
            (like_pattern,),
        ).fetchall()
        for r in job_rows:
            results.append({
                "action": "translate",
                "provider_name": "",
                "format": r[2] or "",
                "score": 0,
                "date": r[5],
                "status": r[3],
                "error": r[4] or "",
            })

    # Sort combined results by date descending
    results.sort(key=lambda x: x["date"], reverse=True)
    return results[:50]


# ─── AniDB Mapping Operations ──────────────────────────────────────────────────


def get_anidb_mapping(tvdb_id: int) -> Optional[int]:
    """Get cached AniDB ID for a TVDB ID.

    Args:
        tvdb_id: TVDB series ID

    Returns:
        AniDB ID as int, or None if not found or expired
    """
    from config import get_settings
    settings = get_settings()

    db = get_db()
    with _db_lock:
        row = db.execute(
            "SELECT anidb_id, last_used FROM anidb_mappings WHERE tvdb_id=?",
            (tvdb_id,),
        ).fetchone()

    if not row:
        return None

    # Check if cache entry is still valid (within TTL)
    cache_ttl_days = settings.anidb_cache_ttl_days
    if cache_ttl_days > 0:
        try:
            last_used = datetime.fromisoformat(row[1])
            age_days = (datetime.utcnow() - last_used).days
            if age_days > cache_ttl_days:
                logger.debug("AniDB mapping for TVDB %d expired (age: %d days)", tvdb_id, age_days)
                return None
        except (ValueError, TypeError):
            # Invalid timestamp, treat as expired
            return None

    # Update last_used timestamp
    now = datetime.utcnow().isoformat()
    with _db_lock:
        db.execute(
            "UPDATE anidb_mappings SET last_used=? WHERE tvdb_id=?",
            (now, tvdb_id),
        )
        db.commit()

    return row[0]


def save_anidb_mapping(tvdb_id: int, anidb_id: int, series_title: str = ""):
    """Save or update an AniDB mapping in the cache.

    Args:
        tvdb_id: TVDB series ID
        anidb_id: AniDB series ID
        series_title: Optional series title for reference
    """
    now = datetime.utcnow().isoformat()
    db = get_db()
    with _db_lock:
        # Check if mapping already exists
        existing = db.execute(
            "SELECT anidb_id FROM anidb_mappings WHERE tvdb_id=?",
            (tvdb_id,),
        ).fetchone()

        if existing:
            # Update existing mapping
            db.execute(
                """UPDATE anidb_mappings
                   SET anidb_id=?, series_title=?, last_used=?
                   WHERE tvdb_id=?""",
                (anidb_id, series_title, now, tvdb_id),
            )
        else:
            # Insert new mapping
            db.execute(
                """INSERT INTO anidb_mappings (tvdb_id, anidb_id, series_title, created_at, last_used)
                   VALUES (?, ?, ?, ?, ?)""",
                (tvdb_id, anidb_id, series_title, now, now),
            )
        db.commit()
    logger.debug("Saved AniDB mapping: TVDB %d → AniDB %d", tvdb_id, anidb_id)


def cleanup_old_anidb_mappings(days: int = 90):
    """Remove AniDB mappings older than specified days.

    Args:
        days: Number of days to keep (default: 90)

    Returns:
        Number of mappings deleted
    """
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    db = get_db()
    with _db_lock:
        cursor = db.execute(
            "DELETE FROM anidb_mappings WHERE last_used < ?",
            (cutoff,),
        )
        db.commit()
    deleted = cursor.rowcount
    if deleted > 0:
        logger.info("Cleaned up %d old AniDB mappings (older than %d days)", deleted, days)
    return deleted


def get_anidb_mapping_stats() -> dict:
    """Get statistics about AniDB mappings cache.

    Returns:
        Dict with total mappings, oldest entry, newest entry
    """
    db = get_db()
    with _db_lock:
        total = db.execute("SELECT COUNT(*) FROM anidb_mappings").fetchone()[0]

        oldest = db.execute(
            "SELECT created_at FROM anidb_mappings ORDER BY created_at ASC LIMIT 1"
        ).fetchone()

        newest = db.execute(
            "SELECT created_at FROM anidb_mappings ORDER BY created_at DESC LIMIT 1"
        ).fetchone()

    return {
        "total_mappings": total,
        "oldest_entry": oldest[0] if oldest else None,
        "newest_entry": newest[0] if newest else None,
    }
