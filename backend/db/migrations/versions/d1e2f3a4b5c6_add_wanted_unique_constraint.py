"""Add UNIQUE constraint on wanted_items (file_path, target_language, subtitle_type).

Deduplicates existing rows first (keeps highest ID per group), then adds
the constraint to prevent future race-condition duplicates.

Revision ID: d1e2f3a4b5c6
Revises: c7d8e9f0a1b2
Create Date: 2026-02-21

"""
from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic
revision = "d1e2f3a4b5c6"
down_revision = "c7d8e9f0a1b2"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    # Step 1: Remove duplicate rows, keeping the highest ID per (file_path, target_language, subtitle_type).
    # This handles pre-existing duplicates from the race-condition bug.
    conn.execute(text("""
        DELETE FROM wanted_items
        WHERE id NOT IN (
            SELECT MAX(id)
            FROM wanted_items
            GROUP BY file_path,
                     COALESCE(target_language, ''),
                     COALESCE(subtitle_type, 'full')
        )
    """))

    # Step 2: Add the unique constraint via batch_alter (required for SQLite).
    with op.batch_alter_table("wanted_items") as batch_op:
        batch_op.create_unique_constraint(
            "uq_wanted_file_lang_type",
            ["file_path", "target_language", "subtitle_type"],
        )


def downgrade():
    with op.batch_alter_table("wanted_items") as batch_op:
        batch_op.drop_constraint("uq_wanted_file_lang_type", type_="unique")
