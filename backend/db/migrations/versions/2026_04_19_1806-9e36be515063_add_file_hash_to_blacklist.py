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

import sqlalchemy as sa
from alembic import op

revision = "9e36be515063"
down_revision = "7e085763f714"
branch_labels = None
depends_on = None


def _has_column(bind, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    return column in {c["name"] for c in insp.get_columns(table)}


def _has_index(bind, table: str, index: str) -> bool:
    insp = sa.inspect(bind)
    return index in {i["name"] for i in insp.get_indexes(table)}


def upgrade() -> None:
    bind = op.get_bind()
    # Idempotent: skip add_column when create_all() already materialised it
    # from the ORM model (common in test envs that run create_all + alembic).
    if not _has_column(bind, "blacklist_entries", "file_hash"):
        op.add_column(
            "blacklist_entries",
            sa.Column("file_hash", sa.String(length=64), nullable=True),
        )
    # Partial UNIQUE: enforce no duplicates for hash-based entries,
    # allow multiple NULLs (traditional subtitle_id-based entries).
    if not _has_index(bind, "blacklist_entries", "idx_blacklist_provider_hash"):
        op.create_index(
            "idx_blacklist_provider_hash",
            "blacklist_entries",
            ["provider_name", "file_hash"],
            unique=True,
            postgresql_where=sa.text("file_hash IS NOT NULL"),
            sqlite_where=sa.text("file_hash IS NOT NULL"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _has_index(bind, "blacklist_entries", "idx_blacklist_provider_hash"):
        op.drop_index("idx_blacklist_provider_hash", table_name="blacklist_entries")
    if _has_column(bind, "blacklist_entries", "file_hash"):
        op.drop_column("blacklist_entries", "file_hash")
