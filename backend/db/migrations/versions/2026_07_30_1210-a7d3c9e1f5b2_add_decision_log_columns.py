"""add decision log columns

- subtitle_downloads.decision_log_json: JSON snapshot of the selection
  pipeline recorded when the download happened ("why was this chosen?")
- wanted_items.last_decision_log_json: snapshot of the most recent search
  for items where nothing was downloaded ("why was nothing found?")

Revision ID: a7d3c9e1f5b2
Revises: merge_pre_decision_log
Create Date: 2026-07-30

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "a7d3c9e1f5b2"
down_revision = "merge_pre_decision_log"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("subtitle_downloads") as batch_op:
        batch_op.add_column(sa.Column("decision_log_json", sa.Text(), nullable=True))
    with op.batch_alter_table("wanted_items") as batch_op:
        batch_op.add_column(sa.Column("last_decision_log_json", sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table("subtitle_downloads") as batch_op:
        batch_op.drop_column("decision_log_json")
    with op.batch_alter_table("wanted_items") as batch_op:
        batch_op.drop_column("last_decision_log_json")
