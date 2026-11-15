"""Add glossary_entries.target_language.

A global glossary applied to every translation regardless of its target, so
an en → de term list would also reach a translation into French. NULL keeps
the old meaning (every target language) for all existing entries.

Revision ID: gtl1_glossary_target_language
Revises: sdp1_subtitle_downloads_path_idx
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "gtl1_glossary_target_language"
down_revision = "sdp1_subtitle_downloads_path_idx"
branch_labels = None
depends_on = None


def _columns() -> set[str]:
    return {c["name"] for c in inspect(op.get_bind()).get_columns("glossary_entries")}


def upgrade() -> None:
    if "target_language" not in _columns():
        with op.batch_alter_table("glossary_entries") as batch:
            batch.add_column(sa.Column("target_language", sa.Text(), nullable=True))


def downgrade() -> None:
    if "target_language" in _columns():
        with op.batch_alter_table("glossary_entries") as batch:
            batch.drop_column("target_language")
