"""add score_breakdown column to subtitle_downloads

Revision ID: b2c3d4e5f6a8
Revises: e7a1b2c3d4f5
Create Date: 2026-07-30

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "b2c3d4e5f6a8"
down_revision = "e7a1b2c3d4f5"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("subtitle_downloads") as batch_op:
        batch_op.add_column(sa.Column("score_breakdown", sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table("subtitle_downloads") as batch_op:
        batch_op.drop_column("score_breakdown")
