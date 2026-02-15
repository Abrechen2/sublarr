"""Scoring weights and provider modifier database operations.

CRUD operations for scoring_weights and provider_score_modifiers tables.
Follows the same _db_lock pattern used throughout the db package.
"""

import logging
from datetime import datetime
from typing import Optional

from db import get_db, _db_lock

logger = logging.getLogger(__name__)

# Default weights used when no DB overrides exist (same as providers/base.py)
_DEFAULT_EPISODE_WEIGHTS = {
    "hash": 359,
    "series": 180,
    "year": 90,
    "season": 30,
    "episode": 30,
    "release_group": 14,
    "source": 7,
    "audio_codec": 3,
    "resolution": 2,
    "hearing_impaired": 1,
    "format_bonus": 50,
}

_DEFAULT_MOVIE_WEIGHTS = {
    "hash": 119,
    "title": 60,
    "year": 30,
    "release_group": 13,
    "source": 7,
    "audio_codec": 3,
    "resolution": 2,
    "hearing_impaired": 1,
    "format_bonus": 50,
}


# ---- Scoring weights CRUD -----------------------------------------------------

def get_scoring_weights(score_type: str) -> dict:
    """Get scoring weight overrides for a given type.

    Returns only the DB overrides (not merged with defaults). The caller
    is responsible for merging with default weights if needed.

    Args:
        score_type: 'episode' or 'movie'

    Returns:
        Dict mapping weight_key -> weight_value. Empty if no overrides.
    """
    db = get_db()
    with _db_lock:
        rows = db.execute(
            "SELECT weight_key, weight_value FROM scoring_weights WHERE score_type=?",
            (score_type,),
        ).fetchall()
    return {row["weight_key"]: row["weight_value"] for row in rows}


def set_scoring_weights(score_type: str, weights_dict: dict) -> None:
    """Set scoring weight overrides for a given type.

    Uses INSERT OR REPLACE for each key-value pair.

    Args:
        score_type: 'episode' or 'movie'
        weights_dict: Mapping of weight_key -> weight_value (int)
    """
    now = datetime.utcnow().isoformat()
    db = get_db()
    with _db_lock:
        for key, value in weights_dict.items():
            db.execute(
                """INSERT OR REPLACE INTO scoring_weights
                   (score_type, weight_key, weight_value, updated_at)
                   VALUES (?, ?, ?, ?)""",
                (score_type, key, int(value), now),
            )
        db.commit()


def get_all_scoring_weights() -> dict:
    """Get all scoring weights with defaults filled in.

    Returns a dict with keys 'episode' and 'movie', each containing
    the full weight dict (defaults merged with DB overrides).

    Returns:
        {'episode': {...}, 'movie': {...}}
    """
    episode_overrides = get_scoring_weights("episode")
    movie_overrides = get_scoring_weights("movie")

    return {
        "episode": {**_DEFAULT_EPISODE_WEIGHTS, **episode_overrides},
        "movie": {**_DEFAULT_MOVIE_WEIGHTS, **movie_overrides},
    }


def reset_scoring_weights(score_type: str = None) -> None:
    """Delete scoring weight overrides.

    Args:
        score_type: If provided, delete only for this type.
                    If None, delete all overrides.
    """
    db = get_db()
    with _db_lock:
        if score_type:
            db.execute(
                "DELETE FROM scoring_weights WHERE score_type=?",
                (score_type,),
            )
        else:
            db.execute("DELETE FROM scoring_weights")
        db.commit()


# ---- Provider score modifiers CRUD ---------------------------------------------

def get_provider_modifier(provider_name: str) -> int:
    """Get the score modifier for a provider.

    Args:
        provider_name: Provider name (e.g. 'opensubtitles')

    Returns:
        Integer modifier (positive = bonus, negative = penalty). 0 if not set.
    """
    db = get_db()
    with _db_lock:
        row = db.execute(
            "SELECT modifier FROM provider_score_modifiers WHERE provider_name=?",
            (provider_name,),
        ).fetchone()
    if row is None:
        return 0
    return row["modifier"]


def get_all_provider_modifiers() -> dict:
    """Get all provider score modifiers.

    Returns:
        Dict mapping provider_name -> modifier (int)
    """
    db = get_db()
    with _db_lock:
        rows = db.execute(
            "SELECT provider_name, modifier FROM provider_score_modifiers ORDER BY provider_name"
        ).fetchall()
    return {row["provider_name"]: row["modifier"] for row in rows}


def set_provider_modifier(provider_name: str, modifier: int) -> None:
    """Set or update the score modifier for a provider.

    Args:
        provider_name: Provider name
        modifier: Integer modifier (positive = bonus, negative = penalty)
    """
    now = datetime.utcnow().isoformat()
    db = get_db()
    with _db_lock:
        db.execute(
            """INSERT OR REPLACE INTO provider_score_modifiers
               (provider_name, modifier, updated_at)
               VALUES (?, ?, ?)""",
            (provider_name, int(modifier), now),
        )
        db.commit()


def delete_provider_modifier(provider_name: str) -> None:
    """Delete the score modifier for a provider.

    Args:
        provider_name: Provider name to remove modifier for
    """
    db = get_db()
    with _db_lock:
        db.execute(
            "DELETE FROM provider_score_modifiers WHERE provider_name=?",
            (provider_name,),
        )
        db.commit()
