"""Add fansub_preferences table.

Revision ID: c3d4e5f6a7b8
Revises: e4f5a6b7c8d9
Create Date: 2026-03-13
"""

import sqlalchemy as sa
from alembic import op

revision = "c3d4e5f6a7b8"
down_revision = "e4f5a6b7c8d9"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "fansub_preferences",
        sa.Column("sonarr_series_id", sa.Integer(), nullable=False),
        sa.Column("preferred_groups_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("excluded_groups_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("bonus", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("sonarr_series_id"),
    )


def downgrade():
    op.drop_table("fansub_preferences")
