"""Record the quality pass's verdict on a translation-memory row.

The per-line quality pass asks the model to score every line of a file and
retranslates the weak ones. None of that reached the memory: batches are stored
the moment they verify, which is *before* the pass runs, and the improvements
were never written back. So a cache hit returned the unchecked line and the
pass scored it again — one model round trip per line, on every reuse, for text
it had already judged. On a 600-line file served entirely from memory that is
600 calls producing no new translation.

This column holds the score the pass gave the row's current ``translated_text``.
NULL means "not checked yet", which is what every existing row is: those are
scored once more on their next use and then carry their verdict.

Data: adds a nullable column, rewrites nothing. No upgrade note needed.

Revision ID: tm5_quality_score
Revises: tm4_wrong_direction
Create Date: 2026-09-18
"""

import sqlalchemy as sa
from alembic import op

revision = "tm5_quality_score"
down_revision = "tm4_wrong_direction"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("translation_memory")}
    if "quality_score" not in columns:
        op.add_column("translation_memory", sa.Column("quality_score", sa.Integer(), nullable=True))


def downgrade() -> None:
    columns = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("translation_memory")}
    if "quality_score" in columns:
        op.drop_column("translation_memory", "quality_score")
