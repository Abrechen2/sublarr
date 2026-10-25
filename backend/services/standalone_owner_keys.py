"""Move pre-1.18 standalone rows to their owner key — once per database.

Before 1.18.0 the standalone pages wrote a title's profile assignment,
settings, glossary entries and fansub preferences under its positive row id
whenever no Sonarr (series) or Radarr (movie) client was configured. Since
1.18.0 those rows live under the negated id (docs/specs/standalone-ids.md),
so that standalone series 3 and Sonarr series 3 never share a row.

Whether a positive key belongs to the arr or to a standalone title cannot be
read from the row: it depended on the configuration at the time of the write.
So the move only happens when the answer is unambiguous — the arr is not
configured now **and** the data shows no trace of it (no wanted row with its
id, no Sonarr search-index row). Otherwise nothing is moved and the
standalone titles start on inherited defaults; no row is deleted or changed
besides its key either way, and a row whose owner key already exists stays.

Runs at startup after the settings overlay is loaded (the "arr configured"
rule needs the effective configuration, which Alembic's env.py does not
have), for tracked and untracked databases. The marker row in
``untracked_data_repairs`` is written in the same transaction, before the
moves, so a second concurrent starter fails on its primary key and rolls back,
and a failed move leaves no marker and is retried on the next start.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime

import sqlalchemy as sa

logger = logging.getLogger(__name__)

MARKER = "sa2_standalone_owner_keys"

# (table, key column) — fixed names, never user input.
_SERIES_TABLES = (
    ("series_language_profiles", "sonarr_series_id"),
    ("series_settings", "sonarr_series_id"),
    ("fansub_preferences", "sonarr_series_id"),
    ("glossary_entries", "series_id"),
)
_MOVIE_TABLES = (
    ("movie_language_profiles", "radarr_movie_id"),
    ("movie_settings", "radarr_movie_id"),
)


def _tables(conn) -> set[str]:
    return set(sa.inspect(conn).get_table_names())


def _has_rows(conn, sql: str) -> bool:
    return conn.execute(sa.text(sql)).first() is not None


def _sonarr_history(conn, tables: set[str]) -> bool:
    if "wanted_items" in tables and _has_rows(
        conn, "SELECT 1 FROM wanted_items WHERE sonarr_series_id IS NOT NULL"
    ):
        return True
    if "search_series" in tables:
        try:
            return _has_rows(conn, "SELECT 1 FROM search_series")
        except Exception:  # noqa: BLE001 — FTS table unreadable: assume history
            logger.debug("search_series unreadable", exc_info=True)
            return True
    return False


def _radarr_history(conn, tables: set[str]) -> bool:
    return "wanted_items" in tables and _has_rows(
        conn, "SELECT 1 FROM wanted_items WHERE radarr_movie_id IS NOT NULL"
    )


def _move_keys(conn, tables: set[str], specs, owner_ids: list[int]) -> int:
    moved = 0
    for table, col in specs:
        if table not in tables:
            continue
        for owner_id in owner_ids:
            taken = conn.execute(
                sa.text(f"SELECT 1 FROM {table} WHERE {col} = :key"),  # noqa: S608 — fixed names
                {"key": -owner_id},
            ).first()
            if taken:
                # An owner-key row exists already (unique tables would collide;
                # for the glossary, two sets would be mixed): keep the old row.
                continue
            result = conn.execute(
                sa.text(f"UPDATE {table} SET {col} = :new WHERE {col} = :old"),  # noqa: S608
                {"new": -owner_id, "old": owner_id},
            )
            moved += result.rowcount or 0
    return moved


def _belongs_to(target: str, video: str) -> bool:
    if os.path.normpath(target) == os.path.normpath(video):
        return True
    stem = os.path.splitext(os.path.basename(video))[0]
    return os.path.dirname(target) == os.path.dirname(video) and os.path.basename(
        target
    ).startswith(stem + ".")


def _rekey_findings(conn, tables: set[str]) -> int:
    """Findings keyed by a standalone wanted row id -> that episode's negative id."""
    if not {"subtitle_health_findings", "wanted_items", "standalone_episodes"} <= tables:
        return 0
    rows = conn.execute(
        sa.text(
            "SELECT f.id, f.target_path, w.file_path, e.id "
            "FROM subtitle_health_findings f "
            "JOIN wanted_items w ON w.id = f.episode_id AND w.standalone_series_id IS NOT NULL "
            "JOIN standalone_episodes e ON e.file_path = w.file_path "
            "WHERE f.episode_id > 0"
        )
    ).fetchall()
    moved = 0
    for finding_id, target, video, episode_row_id in rows:
        if not target or not video or not _belongs_to(target, video):
            continue
        conn.execute(
            sa.text("UPDATE subtitle_health_findings SET episode_id = :e WHERE id = :id"),
            {"e": -int(episode_row_id), "id": finding_id},
        )
        moved += 1
    return moved


def migrate_legacy_owner_keys(
    engine, *, sonarr_configured: bool, radarr_configured: bool
) -> dict[str, int] | None:
    """Apply the move once; ``None`` when it already ran, else the counts."""
    from db.untracked_data_repairs import MARKER_TABLE, _ensure_marker_table

    _ensure_marker_table(engine)
    with engine.connect() as conn:
        done = conn.execute(
            sa.text(f"SELECT 1 FROM {MARKER_TABLE} WHERE revision = :r"),  # noqa: S608
            {"r": MARKER},
        ).first()
    if done:
        return None

    with engine.begin() as conn:
        conn.execute(
            sa.text(
                f"INSERT INTO {MARKER_TABLE} (revision, applied_at, affected) "  # noqa: S608
                "VALUES (:r, :at, 0)"
            ),
            {"r": MARKER, "at": datetime.now(UTC).isoformat()},
        )
        tables = _tables(conn)
        counts = {"series": 0, "movies": 0, "findings": 0}

        if "standalone_series" in tables:
            if sonarr_configured or _sonarr_history(conn, tables):
                logger.info(
                    "Standalone owner keys: Sonarr is or was in use — series rows stay on "
                    "their ids; standalone series start on inherited settings"
                )
            else:
                ids = [r[0] for r in conn.execute(sa.text("SELECT id FROM standalone_series"))]
                counts["series"] = _move_keys(conn, tables, _SERIES_TABLES, ids)
                counts["findings"] = _rekey_findings(conn, tables)

        if "standalone_movies" in tables:
            if radarr_configured or _radarr_history(conn, tables):
                logger.info(
                    "Standalone owner keys: Radarr is or was in use — movie rows stay on "
                    "their ids; standalone movies start on inherited settings"
                )
            else:
                ids = [r[0] for r in conn.execute(sa.text("SELECT id FROM standalone_movies"))]
                counts["movies"] = _move_keys(conn, tables, _MOVIE_TABLES, ids)

        conn.execute(
            sa.text(f"UPDATE {MARKER_TABLE} SET affected = :n WHERE revision = :r"),  # noqa: S608
            {"n": sum(counts.values()), "r": MARKER},
        )
    logger.info(
        "Standalone owner keys: moved %d series row(s), %d movie row(s), %d health finding(s)",
        counts["series"],
        counts["movies"],
        counts["findings"],
    )
    return counts


def run_at_startup(engine) -> None:
    """Startup hook: never blocks startup; a failure is retried next start."""
    try:
        from config_instances import get_radarr_instances, get_sonarr_instances

        migrate_legacy_owner_keys(
            engine,
            sonarr_configured=bool(get_sonarr_instances()),
            radarr_configured=bool(get_radarr_instances()),
        )
    except Exception:
        logger.warning("Standalone owner-key move failed; will retry on next start", exc_info=True)
