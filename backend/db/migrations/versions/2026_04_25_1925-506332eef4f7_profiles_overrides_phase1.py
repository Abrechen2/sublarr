"""profiles_overrides_phase1

Revision ID: 506332eef4f7
Revises: a1b1c1d1e1f1
Create Date: 2026-04-25 19:25:59.532576+00:00

Adds 8 per-series override columns to series_settings and creates the
movie_settings table for per-movie subtitle preferences.  All DDL is
guarded with inspector-based IF-NOT-EXISTS checks so the migration is
safe to re-run on databases that were partially migrated or bootstrapped
via create_all().
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "506332eef4f7"
down_revision = "a1b1c1d1e1f1"
branch_labels = None
depends_on = None


_NEW_SERIES_OVERRIDE_COLS = (
    "forced_preference_override",
    "hi_preference_override",
    "forced_scoring_override",
    "target_languages_override",
    "cutoff_language_override",
    "must_contain_override",
    "must_not_contain_override",
    "audio_exclude_languages_override",
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing_series_cols = {c["name"] for c in inspector.get_columns("series_settings")}
    for col in _NEW_SERIES_OVERRIDE_COLS:
        if col not in existing_series_cols:
            op.add_column("series_settings", sa.Column(col, sa.Text(), nullable=True))

    if "movie_settings" not in inspector.get_table_names():
        op.create_table(
            "movie_settings",
            sa.Column("radarr_movie_id", sa.Integer, primary_key=True),
            sa.Column("preferred_audio_track_index", sa.Integer, nullable=True),
            sa.Column("cleanup_foreign_tracks", sa.Boolean, nullable=True),
            sa.Column("priority_override", sa.String(20), nullable=True),
            sa.Column(
                "min_attempts_per_day",
                sa.Integer,
                nullable=False,
                server_default="0",
            ),
            sa.Column("forced_preference_override", sa.Text, nullable=True),
            sa.Column("hi_preference_override", sa.Text, nullable=True),
            sa.Column("forced_scoring_override", sa.Text, nullable=True),
            sa.Column("target_languages_override", sa.Text, nullable=True),
            sa.Column("cutoff_language_override", sa.Text, nullable=True),
            sa.Column("must_contain_override", sa.Text, nullable=True),
            sa.Column("must_not_contain_override", sa.Text, nullable=True),
            sa.Column("audio_exclude_languages_override", sa.Text, nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_movie_settings_updated", "movie_settings", ["updated_at"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "movie_settings" in inspector.get_table_names():
        # Index may not exist if upgrade() ran on a DB that already had the
        # table (idempotent guard skipped index creation) — drop only if present.
        existing_indexes = {ix["name"] for ix in inspector.get_indexes("movie_settings")}
        if "ix_movie_settings_updated" in existing_indexes:
            op.drop_index("ix_movie_settings_updated", table_name="movie_settings")
        op.drop_table("movie_settings")

    existing_series_cols = {c["name"] for c in inspector.get_columns("series_settings")}
    for col in _NEW_SERIES_OVERRIDE_COLS:
        if col in existing_series_cols:
            op.drop_column("series_settings", col)
