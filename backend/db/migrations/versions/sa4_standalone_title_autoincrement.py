"""Standalone series/movie ids are never reused on SQLite (AUTOINCREMENT).

``standalone_series`` and ``standalone_movies`` were created without
AUTOINCREMENT, so SQLite handed the id of a deleted title (the highest one)
to the next new title. The id is also the owner key (``-id``) of the title's
profile, settings, fansub and glossary rows (docs/specs/standalone-ids.md),
so the new title inherited a deleted title's settings, including the
foreign-track cleanup switch. Found by the 1.18.0-rc.2 end-to-end test.

SQLite can only add AUTOINCREMENT by rebuilding the table: create the new
table, copy the rows with their ids, drop the old one, rename, recreate the
indexes. ``sqlite_sequence`` is then seeded with the highest id that was ever
handed out and is still referenced anywhere: the highest live id, or the
highest standalone id an owner-keyed row, a claim, a wanted row, an episode
row or an automation queue row still names. A seed never lowers an existing
sequence value.

Idempotent: a table that already has AUTOINCREMENT is not rebuilt (only the
seed is checked). PostgreSQL: no-op, its sequences never reuse ids.
Untracked databases get the same function from ``db/untracked_data_repairs``.

Revision ID: sa4_standalone_title_autoincrement
Revises: sa3_automation_queue_series_key
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op

revision = "sa4_standalone_title_autoincrement"
down_revision = "sa3_automation_queue_series_key"
branch_labels = None
depends_on = None

logger = logging.getLogger(__name__)


def _ts() -> sa.DateTime:
    return sa.DateTime(timezone=True)


def _series_table(name: str, metadata: sa.MetaData) -> sa.Table:
    """``standalone_series`` as of this revision (snapshot, not the live model)."""
    return sa.Table(
        name,
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("folder_path", sa.Text(), nullable=False, unique=True),
        sa.Column("tmdb_id", sa.Integer(), nullable=True),
        sa.Column("tvdb_id", sa.Integer(), nullable=True),
        sa.Column("anilist_id", sa.Integer(), nullable=True),
        sa.Column("imdb_id", sa.Text(), nullable=True),
        sa.Column("poster_url", sa.Text(), nullable=True),
        sa.Column("is_anime", sa.Integer(), nullable=True),
        sa.Column("episode_count", sa.Integer(), nullable=True),
        sa.Column("season_count", sa.Integer(), nullable=True),
        sa.Column("metadata_source", sa.Text(), nullable=True),
        sa.Column("created_at", _ts(), nullable=False),
        sa.Column("updated_at", _ts(), nullable=False),
        sqlite_autoincrement=True,
    )


def _movies_table(name: str, metadata: sa.MetaData) -> sa.Table:
    """``standalone_movies`` as of this revision (snapshot, not the live model)."""
    return sa.Table(
        name,
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("file_path", sa.Text(), nullable=False, unique=True),
        sa.Column("tmdb_id", sa.Integer(), nullable=True),
        sa.Column("imdb_id", sa.Text(), nullable=True),
        sa.Column("poster_url", sa.Text(), nullable=True),
        sa.Column("metadata_source", sa.Text(), nullable=True),
        sa.Column("created_at", _ts(), nullable=False),
        sa.Column("updated_at", _ts(), nullable=False),
        sqlite_autoincrement=True,
    )


# table -> (snapshot factory, [(index name, column)])
_TABLES = {
    "standalone_series": (
        _series_table,
        [
            ("idx_standalone_series_tmdb", "tmdb_id"),
            ("idx_standalone_series_anilist", "anilist_id"),
        ],
    ),
    "standalone_movies": (_movies_table, [("idx_standalone_movies_tmdb", "tmdb_id")]),
}

# Where a standalone id may still be referenced: (table, column, sign, extra
# condition). sign -1 = the column holds the owner key (-id), +1 = the row id.
# Fixed SQL, no input.
_REFERENCES = {
    "standalone_series": (
        ("series_language_profiles", "sonarr_series_id", -1, None),
        ("series_settings", "sonarr_series_id", -1, None),
        ("fansub_preferences", "sonarr_series_id", -1, None),
        ("glossary_entries", "series_id", -1, None),
        ("subtitle_automation_queue", "series_key", -1, None),
        ("standalone_legacy_claims", "standalone_id", 1, "kind = 'series'"),
        ("wanted_items", "standalone_series_id", 1, None),
        ("standalone_episodes", "standalone_series_id", 1, None),
    ),
    "standalone_movies": (
        ("movie_language_profiles", "radarr_movie_id", -1, None),
        ("movie_settings", "radarr_movie_id", -1, None),
        ("subtitle_automation_queue", "radarr_movie_id", -1, None),
        ("standalone_legacy_claims", "standalone_id", 1, "kind = 'movie'"),
        ("wanted_items", "standalone_movie_id", 1, None),
    ),
}


def _table_sql(conn, table: str) -> str | None:
    return conn.execute(
        sa.text("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = :t"), {"t": table}
    ).scalar()


def _columns(conn, table: str) -> list[str]:
    return [r[1] for r in conn.execute(sa.text(f'PRAGMA table_info("{table}")'))]


def _rebuild(conn, table: str) -> None:
    factory, indexes = _TABLES[table]
    tmp = f"_sa4_new_{table}"
    conn.execute(sa.text(f'DROP TABLE IF EXISTS "{tmp}"'))
    new = factory(tmp, sa.MetaData())
    new.create(conn)
    shared = [c for c in _columns(conn, table) if c in new.c]
    cols = ", ".join(f'"{c}"' for c in shared)
    conn.execute(sa.text(f'INSERT INTO "{tmp}" ({cols}) SELECT {cols} FROM "{table}"'))  # noqa: S608 — names from PRAGMA ∩ snapshot
    conn.execute(sa.text(f'DROP TABLE "{table}"'))
    conn.execute(sa.text(f'ALTER TABLE "{tmp}" RENAME TO "{table}"'))
    for name, column in indexes:
        conn.execute(sa.text(f'CREATE INDEX IF NOT EXISTS "{name}" ON "{table}" ("{column}")'))


def highest_referenced_id(conn, table: str) -> int:
    """The highest standalone id of ``table`` that is live or still referenced."""
    highest = conn.execute(sa.text(f'SELECT MAX(id) FROM "{table}"')).scalar() or 0  # noqa: S608 — fixed table
    for ref_table, column, sign, extra in _REFERENCES[table]:
        if _table_sql(conn, ref_table) is None or column not in _columns(conn, ref_table):
            continue
        cond = f'"{column}" < 0' if sign < 0 else f'"{column}" > 0'
        if extra:
            cond = f"{cond} AND {extra}"
        agg = f'MIN("{column}")' if sign < 0 else f'MAX("{column}")'
        value = conn.execute(sa.text(f'SELECT {agg} FROM "{ref_table}" WHERE {cond}')).scalar()  # noqa: S608 — fixed SQL
        if value is not None:
            highest = max(highest, abs(int(value)))
    return int(highest)


def _seed_sequence(conn, table: str) -> None:
    highest = highest_referenced_id(conn, table)
    if highest <= 0:
        return
    current = conn.execute(
        sa.text("SELECT seq FROM sqlite_sequence WHERE name = :t"), {"t": table}
    ).first()
    if current is None:
        conn.execute(
            sa.text("INSERT INTO sqlite_sequence (name, seq) VALUES (:t, :s)"),
            {"t": table, "s": highest},
        )
    elif (current[0] or 0) < highest:
        conn.execute(
            sa.text("UPDATE sqlite_sequence SET seq = :s WHERE name = :t"),
            {"t": table, "s": highest},
        )


def ensure_title_autoincrement(conn) -> int:
    """Rebuild the two title tables with AUTOINCREMENT on SQLite; seed the sequence.

    Returns the number of tables rebuilt (0 on PostgreSQL or when already done).
    """
    if conn.dialect.name != "sqlite":
        return 0
    rebuilt = 0
    for table in _TABLES:
        sql = _table_sql(conn, table)
        if sql is None:
            continue
        if "AUTOINCREMENT" not in sql.upper():
            _rebuild(conn, table)
            rebuilt += 1
        _seed_sequence(conn, table)
    if rebuilt:
        logger.info("Standalone ids: rebuilt %d table(s) so deleted ids are never reused", rebuilt)
    return rebuilt


def upgrade() -> None:
    ensure_title_autoincrement(op.get_bind())


def downgrade() -> None:
    # AUTOINCREMENT is harmless for an older build (it only stops id reuse),
    # and rebuilding the tables back would bring the reuse back. Kept.
    pass
