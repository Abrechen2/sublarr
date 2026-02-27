"""Add retry_after column to wanted_items for adaptive backoff.

Revision ID: c7d8e9f0a1b2
Revises: b3c2a1d4e5f6
Create Date: 2026-02-20

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic
revision = "c7d8e9f0a1b2"
down_revision = "b3c2a1d4e5f6"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("wanted_items") as batch_op:
        batch_op.add_column(sa.Column("retry_after", sa.Text(), nullable=True))
    op.create_index("idx_wanted_retry_after", "wanted_items", ["retry_after"])


def downgrade():
    op.drop_index("idx_wanted_retry_after", table_name="wanted_items")
    with op.batch_alter_table("wanted_items") as batch_op:
        batch_op.drop_column("retry_after")
