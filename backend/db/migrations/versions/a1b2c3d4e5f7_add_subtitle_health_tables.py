"""Add subtitle_health_findings + subtitle_health_fixes tables.

Revision ID: a1b2c3d4e5f7
Revises: f3a4b5c6d7e8
Create Date: 2026-06-21
"""

import sqlalchemy as sa
from alembic import op

revision = "a1b2c3d4e5f7"
down_revision = "f3a4b5c6d7e8"
branch_labels = None
depends_on = None


def upgrade():
    insp = sa.inspect(op.get_bind())
    if not insp.has_table("subtitle_health_findings"):
        op.create_table(
            "subtitle_health_findings",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("episode_id", sa.Integer(), nullable=True),
            sa.Column("target_kind", sa.Text(), nullable=False),
            sa.Column("target_path", sa.Text(), nullable=False),
            sa.Column("stream_index", sa.Integer(), nullable=True),
            sa.Column("lang", sa.Text(), nullable=False, server_default="und"),
            sa.Column("issue_type", sa.Text(), nullable=False),
            sa.Column("severity", sa.Text(), nullable=False),
            sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("snippets_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("raw_hash", sa.Text(), nullable=False, server_default=""),
            sa.Column("status", sa.Text(), nullable=False, server_default="open"),
            sa.Column("scanner_version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index(
            "ix_subtitle_health_findings_episode_id",
            "subtitle_health_findings",
            ["episode_id"],
        )
        op.create_index(
            "ix_subtitle_health_findings_target_path",
            "subtitle_health_findings",
            ["target_path"],
        )
    if not insp.has_table("subtitle_health_fixes"):
        op.create_table(
            "subtitle_health_fixes",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("finding_id", sa.Integer(), nullable=True),
            sa.Column("fixer", sa.Text(), nullable=False),
            sa.Column("action", sa.Text(), nullable=False),
            sa.Column("target_path", sa.Text(), nullable=False),
            sa.Column("trashed_original_path", sa.Text(), nullable=True),
            sa.Column("original_hash", sa.Text(), nullable=False, server_default=""),
            sa.Column("fixed_hash", sa.Text(), nullable=False, server_default=""),
            sa.Column("fixer_version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("reversible", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("applied_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index(
            "ix_subtitle_health_fixes_finding_id",
            "subtitle_health_fixes",
            ["finding_id"],
        )


def downgrade():
    insp = sa.inspect(op.get_bind())
    if insp.has_table("subtitle_health_fixes"):
        op.drop_table("subtitle_health_fixes")
    if insp.has_table("subtitle_health_findings"):
        op.drop_table("subtitle_health_findings")
