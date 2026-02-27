"""add_anidb_absolute_mappings_and_series_settings

Revision ID: a1b2c3d4e5f6
Revises: fa890ea72dab
Create Date: 2026-02-22

Adds two tables for Phase 25 (AniDB Absolute Episode Order):
  - anidb_absolute_mappings: TVDB season/episode → AniDB absolute episode
  - series_settings: per-series flags (currently: absolute_order)
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f6"
down_revision = "fa890ea72dab"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "anidb_absolute_mappings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tvdb_id", sa.Integer(), nullable=False),
        sa.Column("season", sa.Integer(), nullable=False),
        sa.Column("episode", sa.Integer(), nullable=False),
        sa.Column("anidb_absolute_episode", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tvdb_id", "season", "episode",
            name="uq_anidb_absolute_tvdb_season_episode",
        ),
    )
    op.create_index("idx_anidb_absolute_tvdb", "anidb_absolute_mappings", ["tvdb_id"])

    op.create_table(
        "series_settings",
        sa.Column("sonarr_series_id", sa.Integer(), nullable=False),
        sa.Column("absolute_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("sonarr_series_id"),
    )


def downgrade():
    op.drop_index("idx_anidb_absolute_tvdb", table_name="anidb_absolute_mappings")
    op.drop_table("anidb_absolute_mappings")
    op.drop_table("series_settings")
