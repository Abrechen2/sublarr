"""Move pre-1.18 standalone rows to their owner key — once per database.

Before 1.18.0 the standalone pages wrote a title's profile assignment,
settings, glossary entries and fansub preferences under its positive row id
whenever no Sonarr (series) or Radarr (movie) client was configured. Since
1.18.0 those rows live under the negated id (docs/specs/standalone-ids.md),
so that standalone series 3 and Sonarr series 3 never share a row.

Whether a positive key belongs to the arr or to a standalone title cannot be
read from the row: it depended on the configuration at the time of the write.
So a side is moved only with affirmative evidence that the install never used
that arr — all of:

* the arr is not configured now;
* no arr URL / instance list was ever stored in ``config_entries``;
* no durable row carries an arr id (translation job contexts, the
  automation queue);
* no durable history row (downloads, upgrades, blacklist, translation jobs,
  sidecar origins, health findings) names a file outside the standalone
  titles.

Wanted rows and the search index are no evidence that the arr was unused: a
successful download deletes wanted rows, and startup rebuilds the search
index from them before this runs. A wanted row that still carries an arr id
only adds a reason to keep (it can never cause a move).

Otherwise that side's rows stay exactly where they are (nothing copied or
deleted) and one warning says how many were kept and why, so the user can
reassign the settings on the Library page. A row whose owner key already
exists stays as well.

Runs at startup after the settings overlay is loaded (the "arr configured"
rule needs the effective configuration, which Alembic's env.py does not
have), for tracked and untracked databases. The marker row in
``untracked_data_repairs`` is written in the same transaction, before the
moves, so a second concurrent starter fails on its primary key and rolls back,
and a failed move leaves no marker and is retried on the next start. A kept
(ambiguous) result also writes the marker: evidence that disappears later
(pruned history) must not move the rows silently on a later start.
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

# Config keys whose non-empty value means the arr was set up at some point.
# A cleared field ("" / "[]") is no evidence.
_SONARR_CONFIG_KEYS = ("sonarr_url", "sonarr_instances_json")
_RADARR_CONFIG_KEYS = ("radarr_url", "radarr_instances_json")

# Durable history that records a media or subtitle path: (table, path column).
_PATH_HISTORY = (
    ("subtitle_downloads", "file_path"),
    ("upgrade_history", "file_path"),
    ("blacklist_entries", "file_path"),
    ("jobs", "file_path"),
    ("sidecar_origins", "video_path"),
    ("subtitle_health_findings", "target_path"),
)


def _tables(conn) -> set[str]:
    return set(sa.inspect(conn).get_table_names())


def _has_rows(conn, sql: str) -> bool:
    return conn.execute(sa.text(sql)).first() is not None


def _config_evidence(conn, tables: set[str], keys: tuple[str, ...]) -> str | None:
    if "config_entries" not in tables:
        return None
    for key in keys:
        value = conn.execute(
            sa.text("SELECT value FROM config_entries WHERE key = :k"), {"k": key}
        ).scalar()
        if value is not None and value.strip() not in ("", "[]"):
            return f"config_entries.{key} is set"
    return None


def _sonarr_id_evidence(conn, tables: set[str]) -> str | None:
    if "wanted_items" in tables and _has_rows(
        conn,
        "SELECT 1 FROM wanted_items "
        "WHERE sonarr_series_id IS NOT NULL OR sonarr_episode_id IS NOT NULL",
    ):
        return "wanted_items rows with a Sonarr id"
    if "jobs" in tables and _has_rows(
        conn, "SELECT 1 FROM jobs WHERE bazarr_context_json LIKE '%\"sonarr_%'"
    ):
        return "translation jobs with a Sonarr id"
    # search_series is deliberately not consulted: startup rebuilds it from
    # wanted_items before this move runs, so it says nothing wanted_items
    # does not.
    return None


def _radarr_id_evidence(conn, tables: set[str]) -> str | None:
    if "wanted_items" in tables and _has_rows(
        conn, "SELECT 1 FROM wanted_items WHERE radarr_movie_id IS NOT NULL"
    ):
        return "wanted_items rows with a Radarr id"
    if "jobs" in tables and _has_rows(
        conn, "SELECT 1 FROM jobs WHERE bazarr_context_json LIKE '%\"radarr_%'"
    ):
        return "translation jobs with a Radarr id"
    if "subtitle_automation_queue" in tables and _has_rows(
        conn, "SELECT 1 FROM subtitle_automation_queue WHERE radarr_movie_id IS NOT NULL"
    ):
        return "automation queue rows with a Radarr id"
    return None


def _norm(path: str) -> str:
    return os.path.normpath(path.replace("\\", "/"))


class _StandaloneFiles:
    """Answers "does this recorded path belong to a known standalone title?"."""

    def __init__(self, conn, tables: set[str]):
        self.folders: list[str] = []
        self.files: set[str] = set()
        self.movies: list[tuple[str, str]] = []  # (directory, stem + ".")
        if "standalone_series" in tables:
            for (folder,) in conn.execute(sa.text("SELECT folder_path FROM standalone_series")):
                if folder:
                    self.folders.append(_norm(folder).rstrip("/") + "/")
        if "standalone_movies" in tables:
            for (path,) in conn.execute(sa.text("SELECT file_path FROM standalone_movies")):
                if path:
                    path = _norm(path)
                    self.files.add(path)
                    stem = os.path.splitext(os.path.basename(path))[0]
                    self.movies.append((os.path.dirname(path), stem + "."))

    def owns(self, path: str) -> bool:
        path = _norm(path)
        if path in self.files or any(path.startswith(f) for f in self.folders):
            return True
        directory, name = os.path.dirname(path), os.path.basename(path)
        return any(directory == d and name.startswith(s) for d, s in self.movies)


def _foreign_path_evidence(conn, tables: set[str]) -> str | None:
    """A history row for a file outside every standalone title.

    Such a file came through Sonarr or Radarr; which of the two cannot be told
    from the path, so this counts against both sides.
    """
    owned = _StandaloneFiles(conn, tables)
    for table, col in _PATH_HISTORY:
        if table not in tables:
            continue
        rows = conn.execute(
            sa.text(f"SELECT DISTINCT {col} FROM {table} WHERE {col} IS NOT NULL")  # noqa: S608
        )
        for (path,) in rows:
            if path and not owned.owns(path):
                return f"{table} rows for files outside the standalone titles"
    return None


def _ids(conn, tables: set[str], table: str) -> list[int]:
    if table not in tables:
        return []
    return [r[0] for r in conn.execute(sa.text(f"SELECT id FROM {table}"))]  # noqa: S608


def _count_candidates(conn, tables: set[str], specs, owner_ids: list[int]) -> int:
    """Positive-key rows the move would have rewritten (reported as kept)."""
    ids = set(owner_ids)
    kept = 0
    for table, col in specs:
        if table not in tables or not ids:
            continue
        for (key,) in conn.execute(
            sa.text(f"SELECT {col} FROM {table} WHERE {col} > 0")  # noqa: S608 — fixed names
        ):
            kept += key in ids
    return kept


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


def _arr_evidence(conn, tables: set[str], *, configured: bool, name: str, keys, id_check, shared):
    """Why this side may have been the arr's, or ``None`` when it never was."""
    if configured:
        return f"{name} is configured"
    return _config_evidence(conn, tables, keys) or id_check(conn, tables) or shared


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

    kept: list[str] = []
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
        series_ids = _ids(conn, tables, "standalone_series")
        movie_ids = _ids(conn, tables, "standalone_movies")
        shared = _foreign_path_evidence(conn, tables) if series_ids or movie_ids else None

        if series_ids:
            reason = _arr_evidence(
                conn,
                tables,
                configured=sonarr_configured,
                name="Sonarr",
                keys=_SONARR_CONFIG_KEYS,
                id_check=_sonarr_id_evidence,
                shared=shared,
            )
            if reason:
                n = _count_candidates(conn, tables, _SERIES_TABLES, series_ids)
                if n:
                    kept.append(f"{n} series row(s) ({reason})")
            else:
                counts["series"] = _move_keys(conn, tables, _SERIES_TABLES, series_ids)
                counts["findings"] = _rekey_findings(conn, tables)

        if movie_ids:
            reason = _arr_evidence(
                conn,
                tables,
                configured=radarr_configured,
                name="Radarr",
                keys=_RADARR_CONFIG_KEYS,
                id_check=_radarr_id_evidence,
                shared=shared,
            )
            if reason:
                n = _count_candidates(conn, tables, _MOVIE_TABLES, movie_ids)
                if n:
                    kept.append(f"{n} movie row(s) ({reason})")
            else:
                counts["movies"] = _move_keys(conn, tables, _MOVIE_TABLES, movie_ids)

        conn.execute(
            sa.text(f"UPDATE {MARKER_TABLE} SET affected = :n WHERE revision = :r"),  # noqa: S608
            {"n": sum(counts.values()), "r": MARKER},
        )
    if kept:
        logger.warning(
            "Standalone owner keys: kept %s on their old ids because they may belong to "
            "Sonarr/Radarr; the matching standalone titles start on inherited settings. "
            "Reassign profiles and settings for those titles on the Library page if needed.",
            " and ".join(kept),
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
