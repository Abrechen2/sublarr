"""Translation config history, glossary, and prompt preset database operations."""

import logging
from datetime import datetime
from typing import Optional

from db import get_db, _db_lock

logger = logging.getLogger(__name__)


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


# ─── Glossary Operations ──────────────────────────────────────────────────────


def add_glossary_entry(series_id: int, source_term: str, target_term: str, notes: str = "") -> int:
    """Add a new glossary entry for a series. Returns the entry ID."""
    now = datetime.utcnow().isoformat()
    db = get_db()
    with _db_lock:
        cursor = db.execute(
            """INSERT INTO glossary_entries (series_id, source_term, target_term, notes, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (series_id, source_term.strip(), target_term.strip(), notes.strip(), now, now),
        )
        db.commit()
        return cursor.lastrowid


def get_glossary_entries(series_id: int) -> list[dict]:
    """Get all glossary entries for a series."""
    db = get_db()
    with _db_lock:
        rows = db.execute(
            """SELECT * FROM glossary_entries
               WHERE series_id=?
               ORDER BY source_term ASC, created_at ASC""",
            (series_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_glossary_for_series(series_id: int) -> list[dict]:
    """Get glossary entries for a series, optimized for translation pipeline.

    Returns list of {source_term, target_term} dicts, limited to 15 most recent entries.
    """
    db = get_db()
    with _db_lock:
        rows = db.execute(
            """SELECT source_term, target_term FROM glossary_entries
               WHERE series_id=?
               ORDER BY updated_at DESC, created_at DESC
               LIMIT 15""",
            (series_id,),
        ).fetchall()
    return [{"source_term": r[0], "target_term": r[1]} for r in rows]


def get_glossary_entry(entry_id: int) -> Optional[dict]:
    """Get a single glossary entry by ID."""
    db = get_db()
    with _db_lock:
        row = db.execute(
            "SELECT * FROM glossary_entries WHERE id=?", (entry_id,)
        ).fetchone()
    if not row:
        return None
    return dict(row)


def update_glossary_entry(entry_id: int, source_term: str = None, target_term: str = None, notes: str = None) -> bool:
    """Update a glossary entry. Returns True if updated."""
    now = datetime.utcnow().isoformat()
    db = get_db()

    updates = []
    params = []

    if source_term is not None:
        updates.append("source_term=?")
        params.append(source_term.strip())
    if target_term is not None:
        updates.append("target_term=?")
        params.append(target_term.strip())
    if notes is not None:
        updates.append("notes=?")
        params.append(notes.strip())

    if not updates:
        return False

    updates.append("updated_at=?")
    params.append(now)
    params.append(entry_id)

    with _db_lock:
        cursor = db.execute(
            f"UPDATE glossary_entries SET {', '.join(updates)} WHERE id=?",
            params,
        )
        db.commit()
    return cursor.rowcount > 0


def delete_glossary_entry(entry_id: int) -> bool:
    """Delete a glossary entry. Returns True if deleted."""
    db = get_db()
    with _db_lock:
        cursor = db.execute("DELETE FROM glossary_entries WHERE id=?", (entry_id,))
        db.commit()
    return cursor.rowcount > 0


def delete_glossary_entries_for_series(series_id: int) -> int:
    """Delete all glossary entries for a series. Returns count deleted."""
    db = get_db()
    with _db_lock:
        cursor = db.execute("DELETE FROM glossary_entries WHERE series_id=?", (series_id,))
        db.commit()
    return cursor.rowcount


def search_glossary_terms(series_id: int, query: str) -> list[dict]:
    """Search glossary entries by source or target term (case-insensitive)."""
    db = get_db()
    search_pattern = f"%{query}%"
    with _db_lock:
        rows = db.execute(
            """SELECT * FROM glossary_entries
               WHERE series_id=? AND (source_term LIKE ? OR target_term LIKE ?)
               ORDER BY source_term ASC""",
            (series_id, search_pattern, search_pattern),
        ).fetchall()
    return [dict(r) for r in rows]


# ─── Prompt Presets Operations ──────────────────────────────────────────────


def add_prompt_preset(name: str, prompt_template: str, is_default: bool = False) -> int:
    """Add a new prompt preset. Returns the preset ID."""
    now = datetime.utcnow().isoformat()
    db = get_db()

    # If this is set as default, unset other defaults
    if is_default:
        with _db_lock:
            db.execute("UPDATE prompt_presets SET is_default=0 WHERE is_default=1")
            db.commit()

    with _db_lock:
        cursor = db.execute(
            """INSERT INTO prompt_presets (name, prompt_template, is_default, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            (name.strip(), prompt_template.strip(), 1 if is_default else 0, now, now),
        )
        db.commit()
        return cursor.lastrowid


def get_prompt_presets() -> list[dict]:
    """Get all prompt presets."""
    db = get_db()
    with _db_lock:
        rows = db.execute(
            """SELECT * FROM prompt_presets
               ORDER BY is_default DESC, name ASC"""
        ).fetchall()
    return [dict(r) for r in rows]


def get_prompt_preset(preset_id: int) -> Optional[dict]:
    """Get a single prompt preset by ID."""
    db = get_db()
    with _db_lock:
        row = db.execute(
            "SELECT * FROM prompt_presets WHERE id=?", (preset_id,)
        ).fetchone()
    if not row:
        return None
    return dict(row)


def get_default_prompt_preset() -> Optional[dict]:
    """Get the default prompt preset."""
    db = get_db()
    with _db_lock:
        row = db.execute(
            "SELECT * FROM prompt_presets WHERE is_default=1 LIMIT 1"
        ).fetchone()
    if not row:
        return None
    return dict(row)


def update_prompt_preset(preset_id: int, name: str = None, prompt_template: str = None, is_default: bool = None) -> bool:
    """Update a prompt preset. Returns True if updated."""
    now = datetime.utcnow().isoformat()
    db = get_db()

    # If setting as default, unset other defaults
    if is_default:
        with _db_lock:
            db.execute("UPDATE prompt_presets SET is_default=0 WHERE is_default=1 AND id!=?", (preset_id,))
            db.commit()

    updates = []
    params = []

    if name is not None:
        updates.append("name=?")
        params.append(name.strip())
    if prompt_template is not None:
        updates.append("prompt_template=?")
        params.append(prompt_template.strip())
    if is_default is not None:
        updates.append("is_default=?")
        params.append(1 if is_default else 0)

    if not updates:
        return False

    updates.append("updated_at=?")
    params.append(now)
    params.append(preset_id)

    with _db_lock:
        cursor = db.execute(
            f"UPDATE prompt_presets SET {', '.join(updates)} WHERE id=?",
            params,
        )
        db.commit()
    return cursor.rowcount > 0


def delete_prompt_preset(preset_id: int) -> bool:
    """Delete a prompt preset. Returns True if deleted. Cannot delete if it's the only preset."""
    db = get_db()
    with _db_lock:
        # Check if it's the only preset
        count = db.execute("SELECT COUNT(*) FROM prompt_presets").fetchone()[0]
        if count <= 1:
            return False

        cursor = db.execute("DELETE FROM prompt_presets WHERE id=?", (preset_id,))
        db.commit()
    return cursor.rowcount > 0
