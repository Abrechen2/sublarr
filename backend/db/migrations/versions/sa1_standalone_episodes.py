"""Standalone episodes: a stable id per standalone episode file.

Creates ``standalone_episodes`` and backfills it from the standalone episode
rows in ``wanted_items`` (one row per file; the lowest standalone series id
wins when two rows disagree). Episodes without a wanted row get theirs from
the next standalone scan or the first series detail view. See
docs/specs/standalone-ids.md.

The backfill is plain SQL with bound parameters (no ``INSERT OR IGNORE`` /
``ON CONFLICT``), skips paths that already have a row and is therefore safe
to run twice, on SQLite and PostgreSQL. Untracked databases get the table from
``create_all()`` and the backfill from ``db.untracked_data_repairs``.

Revision ID: sa1_standalone_episodes
Revises: tvp1_track_variant_policy
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision = "sa1_standalone_episodes"
down_revision = "tvp1_track_variant_policy"
branch_labels = None
depends_on = None

_TABLE = "standalone_episodes"
_SERIES_INDEX = "idx_standalone_episodes_series"
_SE_RE = re.compile(r"^S(\d+)E(\d+)", re.IGNORECASE)
_E_RE = re.compile(r"^E(\d+)", re.IGNORECASE)


def _parse_season_episode(value: str | None) -> tuple[int | None, int | None]:
    text = (value or "").strip()
    match = _SE_RE.match(text)
    if match:
        return int(match.group(1)), int(match.group(2))
    match = _E_RE.match(text)
    if match:
        return None, int(match.group(1))
    return None, None


def backfill_episodes(conn) -> int:
    """Insert one ``standalone_episodes`` row per standalone episode file.

    Returns the number of rows inserted. Paths that already have a row are
    left alone, so a second run inserts nothing.
    """
    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names())
    if not {_TABLE, "wanted_items", "standalone_series"} <= tables:
        return 0

    rows = conn.execute(
        sa.text(
            "SELECT w.file_path, MIN(w.standalone_series_id), MIN(w.season_episode) "
            "FROM wanted_items w "
            "JOIN standalone_series s ON s.id = w.standalone_series_id "
            "WHERE w.item_type = 'episode' AND w.file_path IS NOT NULL AND w.file_path <> '' "
            "GROUP BY w.file_path"
        )
    ).fetchall()
    if not rows:
        return 0

    existing = {r[0] for r in conn.execute(sa.text(f"SELECT file_path FROM {_TABLE}"))}
    now = datetime.now(UTC)
    inserted = 0
    for file_path, series_id, season_episode in rows:
        if file_path in existing:
            continue
        season, episode = _parse_season_episode(season_episode)
        conn.execute(
            sa.text(
                f"INSERT INTO {_TABLE} "
                "(standalone_series_id, file_path, season, episode, created_at, updated_at) "
                "VALUES (:sid, :fp, :season, :episode, :now, :now)"
            ),
            {
                "sid": series_id,
                "fp": file_path,
                "season": season,
                "episode": episode,
                "now": now,
            },
        )
        existing.add(file_path)
        inserted += 1
    return inserted


def upgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(_TABLE):
        op.create_table(
            _TABLE,
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("standalone_series_id", sa.Integer(), nullable=False),
            sa.Column("file_path", sa.Text(), nullable=False, unique=True),
            sa.Column("season", sa.Integer(), nullable=True),
            sa.Column("episode", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sqlite_autoincrement=True,
        )
        op.create_index(_SERIES_INDEX, _TABLE, ["standalone_series_id"])
    backfill_episodes(bind)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    # Findings keyed by a negative (standalone episode) id would point at ids a
    # later upgrade hands out again.
    if inspector.has_table("subtitle_health_findings"):
        bind.execute(sa.text("DELETE FROM subtitle_health_findings WHERE episode_id < 0"))
    if inspector.has_table(_TABLE):
        if _SERIES_INDEX in {i["name"] for i in inspector.get_indexes(_TABLE)}:
            op.drop_index(_SERIES_INDEX, table_name=_TABLE)
        op.drop_table(_TABLE)
