"""add decision log columns

- subtitle_downloads.decision_log_json: JSON snapshot of the selection
  pipeline recorded when the download happened ("why was this chosen?")
- wanted_items.last_decision_log_json: snapshot of the most recent search
  for items where nothing was downloaded ("why was nothing found?")

Revision ID: a7d3c9e1f5b2
Revises: eeb79287c3b6
Create Date: 2026-07-30

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "a7d3c9e1f5b2"
down_revision = "eeb79287c3b6"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    """Existing columns of ``table`` (empty if absent).

    Idempotent guard: the schema is also created straight from the models via
    create_all() on fresh installs, so the columns can already exist.
    """
    insp = sa.inspect(op.get_bind())
    if not insp.has_table(table):
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def upgrade():
    if "decision_log_json" not in _columns("subtitle_downloads"):
        with op.batch_alter_table("subtitle_downloads") as batch_op:
            batch_op.add_column(sa.Column("decision_log_json", sa.Text(), nullable=True))
    if "last_decision_log_json" not in _columns("wanted_items"):
        with op.batch_alter_table("wanted_items") as batch_op:
            batch_op.add_column(sa.Column("last_decision_log_json", sa.Text(), nullable=True))


def downgrade():
    if "decision_log_json" in _columns("subtitle_downloads"):
        with op.batch_alter_table("subtitle_downloads") as batch_op:
            batch_op.drop_column("decision_log_json")
    if "last_decision_log_json" in _columns("wanted_items"):
        with op.batch_alter_table("wanted_items") as batch_op:
            batch_op.drop_column("last_decision_log_json")
