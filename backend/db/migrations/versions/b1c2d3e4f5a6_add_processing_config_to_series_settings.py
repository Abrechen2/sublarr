"""add processing_config column to series_settings

Revision ID: b1c2d3e4f5a6
Revises: f1a2b3c4d5e6
Create Date: 2026-03-19

Adds a nullable JSON text column to series_settings that stores per-series
subtitle processing pipeline overrides (hi_removal, common_fixes,
credit_removal toggles). NULL means "use global defaults".
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "b1c2d3e4f5a6"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("series_settings") as batch_op:
        batch_op.add_column(
            sa.Column(
                "processing_config",
                sa.Text(),
                nullable=True,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("series_settings") as batch_op:
        batch_op.drop_column("processing_config")
