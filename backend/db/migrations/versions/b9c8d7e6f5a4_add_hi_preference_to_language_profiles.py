"""Add hi_preference column to language_profiles

Revision ID: b9c8d7e6f5a4
Revises: 9852305585cd
Create Date: 2026-04-09
"""

import sqlalchemy as sa
from alembic import op

revision = "b9c8d7e6f5a4"
down_revision = "9852305585cd"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("language_profiles") as batch_op:
        batch_op.add_column(
            sa.Column("hi_preference", sa.Text(), nullable=True, server_default="include")
        )


def downgrade():
    with op.batch_alter_table("language_profiles") as batch_op:
        batch_op.drop_column("hi_preference")
