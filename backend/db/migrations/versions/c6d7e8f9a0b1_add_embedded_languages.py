"""Add embedded_languages column to wanted_items.

Revision ID: c6d7e8f9a0b1
Revises: b5c6d7e8f9a0
Create Date: 2026-04-04

"""

import sqlalchemy as sa
from alembic import op

revision = "c6d7e8f9a0b1"
down_revision = "b5c6d7e8f9a0"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("wanted_items") as batch_op:
        batch_op.add_column(
            sa.Column("embedded_languages", sa.Text(), nullable=True, server_default="[]")
        )


def downgrade():
    with op.batch_alter_table("wanted_items") as batch_op:
        batch_op.drop_column("embedded_languages")
