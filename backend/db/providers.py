"""Provider cache and statistics database operations."""

import logging
from datetime import datetime
from typing import Optional

from db import get_db, _db_lock

logger = logging.getLogger(__name__)


def cache_provider_results(provider_name: str, query_hash: str, results_json: str,
                          ttl_hours: int = 6, format_filter: str = None):
    """Cache provider search results.

    Args:
        provider_name: Name of the provider
        query_hash: Hash of the query (should include format_filter if applicable)
        results_json: JSON-encoded results
        ttl_hours: Time-to-live in hours (default: 6, configurable via settings)
        format_filter: Optional format filter for cache key differentiation
    """
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


def get_cached_results(provider_name: str, query_hash: str, format_filter: str = None) -> Optional[str]:
    """Get cached provider results if not expired.

    Args:
        provider_name: Name of the provider
        query_hash: Hash of the query (should include format_filter if applicable)
        format_filter: Optional format filter (for cache key matching)

    Returns:
        Cached results JSON string or None
    """
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


# ─── Provider Statistics Operations ─────────────────────────────────────────────


def update_provider_stats(provider_name: str, success: bool, score: int = 0):
    """Update provider statistics after a search/download attempt.

    Args:
        provider_name: Name of the provider
        success: True if download was successful, False otherwise
        score: Score of the downloaded subtitle (0 if failed)
    """
    now = datetime.utcnow().isoformat()
    db = get_db()
    with _db_lock:
        # Get existing stats or create new entry
        row = db.execute(
            "SELECT * FROM provider_stats WHERE provider_name=?", (provider_name,)
        ).fetchone()

        if row:
            # Update existing stats
            stats = dict(row)
            total_searches = stats["total_searches"] + 1
            successful_downloads = stats["successful_downloads"] + (1 if success else 0)
            failed_downloads = stats["failed_downloads"] + (0 if success else 1)
            consecutive_failures = 0 if success else (stats["consecutive_failures"] + 1)

            # Calculate new average score
            if success and score > 0:
                total_score = stats["avg_score"] * stats["successful_downloads"] + score
                avg_score = total_score / successful_downloads if successful_downloads > 0 else 0
            else:
                avg_score = stats["avg_score"]

            last_success_at = now if success else stats["last_success_at"]
            last_failure_at = now if not success else stats["last_failure_at"]

            db.execute(
                """UPDATE provider_stats SET
                   total_searches=?, successful_downloads=?, failed_downloads=?,
                   avg_score=?, last_success_at=?, last_failure_at=?,
                   consecutive_failures=?, updated_at=?
                   WHERE provider_name=?""",
                (total_searches, successful_downloads, failed_downloads,
                 avg_score, last_success_at, last_failure_at,
                 consecutive_failures, now, provider_name),
            )
        else:
            # Create new stats entry
            successful_downloads = 1 if success else 0
            failed_downloads = 0 if success else 1
            avg_score = score if success else 0
            consecutive_failures = 0 if success else 1

            db.execute(
                """INSERT INTO provider_stats
                   (provider_name, total_searches, successful_downloads, failed_downloads,
                    avg_score, last_success_at, last_failure_at, consecutive_failures, updated_at)
                   VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?)""",
                (provider_name, successful_downloads, failed_downloads,
                 avg_score, now if success else None, now if not success else None,
                 consecutive_failures, now),
            )
        db.commit()


def get_provider_stats(provider_name: str = None) -> dict:
    """Get provider statistics.

    Args:
        provider_name: Optional provider name to get stats for specific provider.
                      If None, returns stats for all providers.

    Returns:
        Dict with provider stats. If provider_name is None, returns dict keyed by provider_name.
    """
    db = get_db()
    with _db_lock:
        if provider_name:
            row = db.execute(
                "SELECT * FROM provider_stats WHERE provider_name=?", (provider_name,)
            ).fetchone()
            if not row:
                return {}
            return dict(row)
        else:
            rows = db.execute("SELECT * FROM provider_stats").fetchall()
            return {row["provider_name"]: dict(row) for row in rows}


def get_provider_success_rate(provider_name: str) -> float:
    """Get success rate for a provider (0.0 to 1.0).

    Args:
        provider_name: Name of the provider

    Returns:
        Success rate as float between 0.0 and 1.0, or 0.0 if no stats available
    """
    stats = get_provider_stats(provider_name)
    if not stats or stats.get("total_searches", 0) == 0:
        return 0.0

    total = stats["total_searches"]
    successful = stats.get("successful_downloads", 0)
    return successful / total if total > 0 else 0.0
