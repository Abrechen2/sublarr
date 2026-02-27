"""add_wanted_composite_index

Revision ID: b3c2a1d4e5f6
Revises: fa890ea72dab
Create Date: 2026-02-20

Add composite index (status, item_type) on wanted_items for the most common
multi-filter query pattern used by get_wanted_items(). Replaces two separate
single-column index scans with a single composite index scan.
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "b3c2a1d4e5f6"
down_revision = "fa890ea72dab"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("idx_wanted_composite", "wanted_items", ["status", "item_type"])


def downgrade():
    op.drop_index("idx_wanted_composite", table_name="wanted_items")
