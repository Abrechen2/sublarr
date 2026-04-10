"""Add forced_scoring column to language_profiles

Revision ID: c4d5e6f7a8b9
Revises: b9c8d7e6f5a4
Create Date: 2026-04-09
"""

import sqlalchemy as sa
from alembic import op

revision = "c4d5e6f7a8b9"
down_revision = "b9c8d7e6f5a4"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("language_profiles") as batch_op:
        batch_op.add_column(
            sa.Column("forced_scoring", sa.Text(), nullable=True, server_default="include")
        )


def downgrade():
    with op.batch_alter_table("language_profiles") as batch_op:
        batch_op.drop_column("forced_scoring")
