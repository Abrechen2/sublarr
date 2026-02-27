"""add source column to subtitle_downloads

Revision ID: f7a8b9c0d1e2
Revises: fa890ea72dab
Create Date: 2026-02-22

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "f7a8b9c0d1e2"
down_revision = "fa890ea72dab"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("subtitle_downloads") as batch_op:
        batch_op.add_column(
            sa.Column(
                "source",
                sa.Text(),
                nullable=True,
                server_default="provider",
            )
        )


def downgrade():
    with op.batch_alter_table("subtitle_downloads") as batch_op:
        batch_op.drop_column("source")
