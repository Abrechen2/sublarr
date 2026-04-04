"""add schedule to cleanup_rules

Revision ID: f0e1d2c3b4a5
Revises: b3c2a1d4e5f6
Create Date: 2026-04-04
"""

import sqlalchemy as sa
from alembic import op

revision = "f0e1d2c3b4a5"
down_revision = "b3c2a1d4e5f6"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("cleanup_rules") as batch_op:
        batch_op.add_column(
            sa.Column("schedule", sa.String(20), nullable=False, server_default="manual")
        )


def downgrade():
    with op.batch_alter_table("cleanup_rules") as batch_op:
        batch_op.drop_column("schedule")
