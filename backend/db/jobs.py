"""Job and daily stats database operations."""

import json
import uuid
import logging
from datetime import datetime, date
from typing import Optional

from db import get_db, _db_lock

logger = logging.getLogger(__name__)


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
