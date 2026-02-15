"""Whisper job database operations.

CRUD operations for the whisper_jobs table, following the same _db_lock
pattern used throughout the db package.
"""

import logging
from datetime import datetime
from typing import Optional

from db import get_db, _db_lock

logger = logging.getLogger(__name__)


def _row_to_job(row) -> dict:
    """Convert a sqlite3.Row to a whisper job dict."""
    if row is None:
        return None
    return dict(row)


def create_whisper_job(job_id: str, file_path: str, language: str = "") -> dict:
    """Create a new whisper job in the database.

    Args:
        job_id: Unique job identifier
        file_path: Path to the media file
        language: Target language code

    Returns:
        Dict representing the created job
    """
    now = datetime.utcnow().isoformat()
    db = get_db()
    with _db_lock:
        db.execute(
            """INSERT INTO whisper_jobs
               (id, file_path, language, status, progress, created_at)
               VALUES (?, ?, ?, 'queued', 0.0, ?)""",
            (job_id, file_path, language, now),
        )
        db.commit()

    return {
        "id": job_id,
        "file_path": file_path,
        "language": language,
        "status": "queued",
        "progress": 0.0,
        "created_at": now,
    }


def update_whisper_job(job_id: str, **kwargs) -> None:
    """Update a whisper job with arbitrary column values.

    Args:
        job_id: Job to update
        **kwargs: Column name-value pairs to update
    """
    if not kwargs:
        return

    columns = []
    values = []
    for key, value in kwargs.items():
        columns.append(f"{key}=?")
        values.append(value)
    values.append(job_id)

    sql = f"UPDATE whisper_jobs SET {', '.join(columns)} WHERE id=?"

    db = get_db()
    with _db_lock:
        db.execute(sql, values)
        db.commit()


def get_whisper_job(job_id: str) -> Optional[dict]:
    """Get a whisper job by ID.

    Args:
        job_id: Job identifier

    Returns:
        Job dict or None if not found
    """
    db = get_db()
    with _db_lock:
        row = db.execute("SELECT * FROM whisper_jobs WHERE id=?", (job_id,)).fetchone()
    return _row_to_job(row)


def get_whisper_jobs(status: str = None, limit: int = 50) -> list[dict]:
    """Get whisper jobs, optionally filtered by status.

    Args:
        status: Optional status filter
        limit: Maximum number of results (default 50)

    Returns:
        List of job dicts, ordered by created_at descending
    """
    db = get_db()
    with _db_lock:
        if status:
            rows = db.execute(
                "SELECT * FROM whisper_jobs WHERE status=? ORDER BY created_at DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT * FROM whisper_jobs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return [_row_to_job(r) for r in rows]


def delete_whisper_job(job_id: str) -> bool:
    """Delete a whisper job.

    Args:
        job_id: Job to delete

    Returns:
        True if a row was deleted
    """
    db = get_db()
    with _db_lock:
        cursor = db.execute("DELETE FROM whisper_jobs WHERE id=?", (job_id,))
        db.commit()
    return cursor.rowcount > 0


def get_whisper_stats() -> dict:
    """Get aggregate whisper job statistics.

    Returns:
        Dict with total count, counts by status, and average processing time
    """
    db = get_db()
    with _db_lock:
        # Total count
        total = db.execute("SELECT COUNT(*) FROM whisper_jobs").fetchone()[0]

        # Counts by status
        status_rows = db.execute(
            "SELECT status, COUNT(*) as cnt FROM whisper_jobs GROUP BY status"
        ).fetchall()
        by_status = {row[0]: row[1] for row in status_rows}

        # Average processing time (completed jobs only)
        avg_row = db.execute(
            "SELECT AVG(processing_time_ms) FROM whisper_jobs WHERE status='completed' AND processing_time_ms > 0"
        ).fetchone()
        avg_processing_time = avg_row[0] if avg_row[0] is not None else 0.0

    return {
        "total": total,
        "by_status": by_status,
        "avg_processing_time_ms": round(avg_processing_time, 1),
    }
