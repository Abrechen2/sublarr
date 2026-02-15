"""Wanted items database operations."""

import json
import logging
from datetime import datetime
from typing import Optional

from db import get_db, _db_lock

logger = logging.getLogger(__name__)


def upsert_wanted_item(item_type: str, file_path: str, title: str = "",
                       season_episode: str = "", existing_sub: str = "",
                       missing_languages: list = None,
                       sonarr_series_id: int = None,
                       sonarr_episode_id: int = None,
                       radarr_movie_id: int = None,
                       upgrade_candidate: bool = False,
                       current_score: int = 0,
                       target_language: str = "",
                       instance_name: str = "") -> int:
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
                       target_language=?, instance_name=?, updated_at=?
                       WHERE id=?""",
                    (title, season_episode, existing_sub, langs_json,
                     sonarr_series_id, sonarr_episode_id, radarr_movie_id,
                     upgrade_int, current_score, target_language, instance_name, now, row_id),
                )
            else:
                db.execute(
                    """UPDATE wanted_items SET item_type=?, title=?, season_episode=?,
                       existing_sub=?, missing_languages=?, status='wanted',
                       sonarr_series_id=?, sonarr_episode_id=?, radarr_movie_id=?,
                       upgrade_candidate=?, current_score=?,
                       target_language=?, instance_name=?, updated_at=?
                       WHERE id=?""",
                    (item_type, title, season_episode, existing_sub, langs_json,
                     sonarr_series_id, sonarr_episode_id, radarr_movie_id,
                     upgrade_int, current_score, target_language, instance_name, now, row_id),
                )
        else:
            cursor = db.execute(
                """INSERT INTO wanted_items
                   (item_type, file_path, title, season_episode, existing_sub,
                    missing_languages, sonarr_series_id, sonarr_episode_id,
                    radarr_movie_id, upgrade_candidate, current_score,
                    target_language, instance_name, status, added_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'wanted', ?, ?)""",
                (item_type, file_path, title, season_episode, existing_sub,
                 langs_json, sonarr_series_id, sonarr_episode_id,
                 radarr_movie_id, upgrade_int, current_score,
                 target_language, instance_name, now, now),
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


def find_wanted_by_episode(sonarr_episode_id: int, target_language: str = "") -> Optional[dict]:
    """Find a wanted item for a specific episode + language."""
    db = get_db()
    with _db_lock:
        if target_language:
            row = db.execute(
                "SELECT * FROM wanted_items WHERE sonarr_episode_id=? AND target_language=? LIMIT 1",
                (sonarr_episode_id, target_language),
            ).fetchone()
        else:
            row = db.execute(
                "SELECT * FROM wanted_items WHERE sonarr_episode_id=? LIMIT 1",
                (sonarr_episode_id,),
            ).fetchone()
    if not row:
        return None
    return _row_to_wanted(row)


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
