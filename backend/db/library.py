"""Download history and upgrade tracking database operations."""

import logging
from datetime import datetime

from db import get_db, _db_lock

logger = logging.getLogger(__name__)


def get_download_history(page: int = 1, per_page: int = 50,
                         provider: str = None, language: str = None) -> dict:
    """Get paginated download history with optional filters."""
    db = get_db()
    offset = (page - 1) * per_page

    conditions = []
    params = []
    if provider:
        conditions.append("provider_name=?")
        params.append(provider)
    if language:
        conditions.append("language=?")
        params.append(language)

    where = " WHERE " + " AND ".join(conditions) if conditions else ""

    with _db_lock:
        count = db.execute(
            f"SELECT COUNT(*) FROM subtitle_downloads{where}", params
        ).fetchone()[0]
        rows = db.execute(
            f"SELECT * FROM subtitle_downloads{where} ORDER BY downloaded_at DESC LIMIT ? OFFSET ?",
            params + [per_page, offset],
        ).fetchall()

    total_pages = max(1, (count + per_page - 1) // per_page)
    return {
        "data": [dict(r) for r in rows],
        "page": page,
        "per_page": per_page,
        "total": count,
        "total_pages": total_pages,
    }


def get_download_stats() -> dict:
    """Get aggregated download statistics."""
    db = get_db()
    with _db_lock:
        total = db.execute("SELECT COUNT(*) FROM subtitle_downloads").fetchone()[0]

        by_provider = {}
        for row in db.execute(
            "SELECT provider_name, COUNT(*) FROM subtitle_downloads GROUP BY provider_name"
        ).fetchall():
            by_provider[row[0]] = row[1]

        by_format = {}
        for row in db.execute(
            "SELECT format, COUNT(*) FROM subtitle_downloads GROUP BY format"
        ).fetchall():
            by_format[row[0] or "unknown"] = row[1]

        by_language = {}
        for row in db.execute(
            "SELECT language, COUNT(*) FROM subtitle_downloads GROUP BY language"
        ).fetchall():
            by_language[row[0] or "unknown"] = row[1]

        last_24h = db.execute(
            "SELECT COUNT(*) FROM subtitle_downloads WHERE downloaded_at > datetime('now', '-1 day')"
        ).fetchone()[0]

        last_7d = db.execute(
            "SELECT COUNT(*) FROM subtitle_downloads WHERE downloaded_at > datetime('now', '-7 days')"
        ).fetchone()[0]

    return {
        "total_downloads": total,
        "by_provider": by_provider,
        "by_format": by_format,
        "by_language": by_language,
        "last_24h": last_24h,
        "last_7d": last_7d,
    }


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
