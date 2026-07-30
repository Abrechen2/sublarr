"""add custom_scoring_rules — user-defined regex scoring rules

Sonarr-style release-profile conditions: each row holds a regex that is
matched case-insensitively against a candidate's release_info during
penalty-pipeline scoring; a hit adds the signed weight to the score.

Guarded with has_table: the schema is also created straight from the models
via create_all() (fresh installs, the test harness), so the migration must
be a no-op when the table is already there.

Revision ID: f8c9d0e1a2b3
Revises: e7a1b2c3d4f5
Create Date: 2026-07-30
"""

import sqlalchemy as sa
from alembic import op

revision = "f8c9d0e1a2b3"
down_revision = "e7a1b2c3d4f5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table("custom_scoring_rules"):
        return

    op.create_table(
        "custom_scoring_rules",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("pattern", sa.Text(), nullable=False),
        sa.Column("weight", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table("custom_scoring_rules"):
        op.drop_table("custom_scoring_rules")
