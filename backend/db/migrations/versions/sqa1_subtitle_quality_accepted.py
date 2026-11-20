"""Add subtitle_downloads.quality_accepted.

The episode Accept button ("I'm ok with this quality") had nothing to store
its decision in, so the low-score warning came straight back (#255). The flag
sits on the download rows of a file and language; a newer download starts
unaccepted again.

Revision ID: sqa1_subtitle_quality_accepted
Revises: gtl1_glossary_target_language
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "sqa1_subtitle_quality_accepted"
down_revision = "gtl1_glossary_target_language"
branch_labels = None
depends_on = None


def _columns() -> set[str]:
    return {c["name"] for c in inspect(op.get_bind()).get_columns("subtitle_downloads")}


def upgrade() -> None:
    if "quality_accepted" not in _columns():
        with op.batch_alter_table("subtitle_downloads") as batch:
            batch.add_column(sa.Column("quality_accepted", sa.Integer(), nullable=True))


def downgrade() -> None:
    if "quality_accepted" in _columns():
        with op.batch_alter_table("subtitle_downloads") as batch:
            batch.drop_column("quality_accepted")
