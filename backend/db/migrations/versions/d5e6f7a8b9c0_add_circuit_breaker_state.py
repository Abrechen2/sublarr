"""Add circuit_breaker_states table.

Revision ID: d5e6f7a8b9c0
Revises: c0d1e2f3a4b5
Create Date: 2026-04-02
"""

import sqlalchemy as sa
from alembic import op

revision = "d5e6f7a8b9c0"
down_revision = "c0d1e2f3a4b5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "circuit_breaker_states",
        sa.Column("name", sa.Text, primary_key=True),
        sa.Column("state", sa.Text, nullable=False, server_default="closed"),
        sa.Column("failure_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_failure_epoch", sa.Float, nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_cb_state_updated", "circuit_breaker_states", ["updated_at"])


def downgrade() -> None:
    op.drop_index("idx_cb_state_updated", table_name="circuit_breaker_states")
    op.drop_table("circuit_breaker_states")
