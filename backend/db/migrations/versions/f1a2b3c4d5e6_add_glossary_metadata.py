"""add term_type, confidence, approved columns to glossary_entries

Revision ID: f1a2b3c4d5e6
Revises: e4f5a6b7c8d9
Create Date: 2026-03-14

Adds three metadata columns to glossary_entries to support the AI Glossary
Builder feature:
- term_type: categorise entries as 'character', 'place', or 'other'
- confidence: float 0-1 set by LLM extractor; NULL for manual entries
- approved: SQLite boolean (0=pending AI suggestion, 1=approved/manual)
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "f1a2b3c4d5e6"
down_revision = "e4f5a6b7c8d9"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("glossary_entries") as batch_op:
        batch_op.add_column(
            sa.Column(
                "term_type",
                sa.Text(),
                nullable=False,
                server_default="other",
            )
        )
        batch_op.add_column(
            sa.Column(
                "confidence",
                sa.Float(),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "approved",
                sa.Integer(),
                nullable=False,
                server_default="1",
            )
        )


def downgrade():
    with op.batch_alter_table("glossary_entries") as batch_op:
        batch_op.drop_column("approved")
        batch_op.drop_column("confidence")
        batch_op.drop_column("term_type")
