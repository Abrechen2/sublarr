"""Merge hi_preference and forced_scoring branches into main

Revision ID: merge_hi_pref_forced_scoring
Revises: e4f5a6b7c8d9, c4d5e6f7a8b9
Create Date: 2026-04-10

Resolves the duplicate b2c3d4e5f6a7 revision ID that caused Alembic
auto-upgrade to fail. The hi_preference migration was renamed to
b9c8d7e6f5a4 and forced_scoring updated to follow it. This merge
connects those two new migrations to the main branch head.
"""

revision = "merge_hi_pref_forced_scoring"
down_revision = ("e4f5a6b7c8d9", "c4d5e6f7a8b9")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
