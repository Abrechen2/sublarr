"""make glossary series_id nullable for global glossary support

Revision ID: e4f5a6b7c8d9
Revises: fa890ea72dab
Create Date: 2026-02-21

Allows glossary_entries.series_id to be NULL, enabling global glossary
entries that apply to all series. Per-series entries (series_id set)
override global entries with the same source_term during translation.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "e4f5a6b7c8d9"
down_revision = "fa890ea72dab"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("glossary_entries") as batch_op:
        batch_op.alter_column(
            "series_id",
            existing_type=sa.Integer(),
            nullable=True,
        )


def downgrade():
    # Backfill NULL series_id before making NOT NULL
    op.execute("UPDATE glossary_entries SET series_id = 0 WHERE series_id IS NULL")
    with op.batch_alter_table("glossary_entries") as batch_op:
        batch_op.alter_column(
            "series_id",
            existing_type=sa.Integer(),
            nullable=False,
        )
