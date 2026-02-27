"""add_translation_memory

Revision ID: e3f4a5b6c7d8
Revises:
Create Date: 2026-02-22

Adds the translation_memory table for persistent translation caching.
Lines are keyed by (source_lang, target_lang, text_hash) where text_hash
is the SHA-256 of the normalized source text. This enables exact-match
lookups in O(1) via index while preserving the normalized text for
optional fuzzy/similarity-based matching.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "e3f4a5b6c7d8"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "translation_memory",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_lang", sa.Text(), nullable=False),
        sa.Column("target_lang", sa.Text(), nullable=False),
        sa.Column("source_text_normalized", sa.Text(), nullable=False),
        sa.Column("text_hash", sa.Text(), nullable=False),
        sa.Column("translated_text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_lang", "target_lang", "text_hash", name="uq_tm_lang_hash"),
    )
    # Fast exact-match lookup by (source_lang, target_lang, text_hash)
    op.create_index(
        "idx_tm_lang_hash",
        "translation_memory",
        ["source_lang", "target_lang", "text_hash"],
    )
    # Language-pair scan for similarity matching
    op.create_index(
        "idx_tm_lang_pair",
        "translation_memory",
        ["source_lang", "target_lang"],
    )


def downgrade():
    op.drop_index("idx_tm_lang_pair", table_name="translation_memory")
    op.drop_index("idx_tm_lang_hash", table_name="translation_memory")
    op.drop_table("translation_memory")
