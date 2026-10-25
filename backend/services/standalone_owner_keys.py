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
  titles, or a file inside one that was recorded before that title was
  created (the arr handled the same folder before it was imported as
  standalone).

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

# Durable history that records a media or subtitle path:
# (table, path column, timestamp column).
_PATH_HISTORY = (
    ("subtitle_downloads", "file_path", "downloaded_at"),
    ("upgrade_history", "file_path", "upgraded_at"),
    ("blacklist_entries", "file_path", "added_at"),
    ("jobs", "file_path", "created_at"),
    ("sidecar_origins", "video_path", "recorded_at"),
    ("subtitle_health_findings", "target_path", "detected_at"),
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


def _as_utc(value) -> datetime | None:
    """A DB timestamp (datetime, or ISO text on SQLite) as aware UTC; None if unreadable."""
    if isinstance(value, datetime):
        stamp = value
    else:
        try:
            stamp = datetime.fromisoformat(str(value))
        except (TypeError, ValueError):
            return None
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=UTC)


class _StandaloneFiles:
    """Which standalone title (if any) a recorded path belongs to, and since when.

    Lookups are dictionary hits per ancestor directory, so the cost is the
    path depth, not the library size.
    """

    def __init__(self, conn, tables: set[str]):
        self.folders: dict[str, datetime | None] = {}
        self.files: dict[str, datetime | None] = {}
        self.movies: dict[str, list[tuple[str, datetime | None]]] = {}  # dir -> (stem., since)
        if "standalone_series" in tables:
            for folder, created in conn.execute(
                sa.text("SELECT folder_path, created_at FROM standalone_series")
            ):
                if folder:
                    self.folders[_norm(folder).rstrip("/") or "/"] = _as_utc(created)
        if "standalone_movies" in tables:
            for path, created in conn.execute(
                sa.text("SELECT file_path, created_at FROM standalone_movies")
            ):
                if path:
                    path, since = _norm(path), _as_utc(created)
                    self.files[path] = since
                    stem = os.path.splitext(os.path.basename(path))[0]
                    self.movies.setdefault(os.path.dirname(path), []).append((stem + ".", since))

    def owner_since(self, path: str) -> tuple[bool, datetime | None]:
        """``(owned, owner's created_at)`` for a recorded path."""
        path = _norm(path)
        if path in self.files:
            return True, self.files[path]
        directory, name = os.path.dirname(path), os.path.basename(path)
        for stem, since in self.movies.get(directory, ()):
            if name.startswith(stem):
                return True, since
        current = directory
        while True:
            if current in self.folders:
                return True, self.folders[current]
            parent = os.path.dirname(current)
            if parent == current:
                return False, None
            current = parent


def _foreign_path_evidence(conn, tables: set[str]) -> str | None:
    """A history row the standalone titles cannot account for.

    That is a file outside every standalone title, or a file inside one but
    recorded before that title existed (Sonarr/Radarr handled the same folder
    before it was imported as standalone). Which arr cannot be told from a
    path, so this counts against both sides. An unreadable timestamp counts
    as evidence too.
    """
    owned = _StandaloneFiles(conn, tables)
    for table, col, ts in _PATH_HISTORY:
        if table not in tables:
            continue
        rows = conn.execute(
            sa.text(
                f"SELECT {col}, MIN({ts}) FROM {table} "  # noqa: S608 — fixed names
                f"WHERE {col} IS NOT NULL AND {col} != '' GROUP BY {col}"
            )
        )
        for path, first_seen in rows:
            is_owned, since = owned.owner_since(path)
            if not is_owned:
                return f"{table} rows for files outside the standalone titles"
            seen = _as_utc(first_seen)
            if since is None or seen is None or seen < since:
                return f"{table} rows older than the standalone title they belong to"
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
    """Why this side may have been the arr's, or ``None`` when it never was.

    ``shared`` is a callable: the history scan runs only when the cheap
    checks found nothing, and at most once for both sides.
    """
    if configured:
        return f"{name} is configured"
    return _config_evidence(conn, tables, keys) or id_check(conn, tables) or shared()


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
        history: list[str | None] = []

        def shared() -> str | None:
            if not history:
                history.append(_foreign_path_evidence(conn, tables))
            return history[0]

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
