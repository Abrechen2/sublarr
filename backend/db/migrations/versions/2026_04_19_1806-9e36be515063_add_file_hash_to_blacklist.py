"""add file_hash column to blacklist_entries

Revision ID: 9e36be515063
Revises: 7e085763f714
Create Date: 2026-04-19 18:06:00

Plan B Phase 3 — Granular blacklist.

Adds a nullable VARCHAR(64) file_hash column to blacklist_entries so
Sublarr can suppress retries for "any subtitle with hash H from provider
Y" in addition to the existing (provider, subtitle_id) dimension. The
new partial UNIQUE index `idx_blacklist_provider_hash` enforces
no-duplicates for hash-based entries while allowing multiple NULLs for
traditional subtitle_id-based entries.
"""

from alembic import op
import sqlalchemy as sa


revision = "9e36be515063"
down_revision = "7e085763f714"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "blacklist_entries",
        sa.Column("file_hash", sa.String(length=64), nullable=True),
    )
    # Partial UNIQUE: enforce no duplicates for hash-based entries,
    # allow multiple NULLs (traditional subtitle_id-based entries).
    op.create_index(
        "idx_blacklist_provider_hash",
        "blacklist_entries",
        ["provider_name", "file_hash"],
        unique=True,
        postgresql_where=sa.text("file_hash IS NOT NULL"),
        sqlite_where=sa.text("file_hash IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_blacklist_provider_hash", table_name="blacklist_entries")
    op.drop_column("blacklist_entries", "file_hash")
