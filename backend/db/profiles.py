"""Language profile database operations."""

import json
import logging
from datetime import datetime
from typing import Optional

from config import get_settings
from db import get_db, _db_lock

logger = logging.getLogger(__name__)


def _row_to_profile(row) -> dict:
    """Convert a database row to a language profile dict."""
    d = dict(row)
    d["is_default"] = bool(d.get("is_default", 0))
    try:
        d["target_languages"] = json.loads(d.get("target_languages_json", "[]"))
    except json.JSONDecodeError:
        d["target_languages"] = []
    if "target_languages_json" in d:
        del d["target_languages_json"]
    try:
        d["target_language_names"] = json.loads(d.get("target_language_names_json", "[]"))
    except json.JSONDecodeError:
        d["target_language_names"] = []
    if "target_language_names_json" in d:
        del d["target_language_names_json"]

    # Translation backend fields (added in Phase 2)
    d["translation_backend"] = d.get("translation_backend", "ollama")
    try:
        d["fallback_chain"] = json.loads(d.get("fallback_chain_json", '["ollama"]'))
    except (json.JSONDecodeError, TypeError):
        d["fallback_chain"] = ["ollama"]
    if "fallback_chain_json" in d:
        del d["fallback_chain_json"]

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
               "target_languages", "target_language_names",
               "translation_backend", "fallback_chain"}
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
        elif key == "fallback_chain":
            updates.append("fallback_chain_json=?")
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


def get_series_profile_map() -> dict:
    """Get all series -> {profile_id, profile_name} map for library enrichment."""
    db = get_db()
    with _db_lock:
        rows = db.execute(
            """SELECT slp.sonarr_series_id, lp.id, lp.name
               FROM series_language_profiles slp
               JOIN language_profiles lp ON slp.profile_id = lp.id"""
        ).fetchall()
    return {row[0]: {"profile_id": row[1], "profile_name": row[2]} for row in rows}


def get_series_missing_counts() -> dict:
    """Get wanted item counts per series: {series_id: count}."""
    db = get_db()
    with _db_lock:
        rows = db.execute(
            """SELECT sonarr_series_id, COUNT(*) as cnt
               FROM wanted_items
               WHERE sonarr_series_id IS NOT NULL AND status='wanted'
               GROUP BY sonarr_series_id"""
        ).fetchall()
    return {row[0]: row[1] for row in rows}
