"""Add user_modified_subtitles — hand-edited marker for the editor trust guard.

Editor saves mark the file; the upgrade automation refuses to replace marked
files while ``upgrade_protect_user_modified`` is enabled.

Revision ID: f6a7b8c9d0e1
Revises: e7a1b2c3d4f5
Create Date: 2026-07-30 12:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "f6a7b8c9d0e1"
down_revision = "e7a1b2c3d4f5"
branch_labels = None
depends_on = None

TABLE = "user_modified_subtitles"


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if insp.has_table(TABLE):
        return
    op.create_table(
        TABLE,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("marked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.Text(), nullable=False, server_default="editor"),
    )
    op.create_index("idx_user_modified_path", TABLE, ["file_path"], unique=True)


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if insp.has_table(TABLE):
        op.drop_index("idx_user_modified_path", table_name=TABLE)
        op.drop_table(TABLE)
