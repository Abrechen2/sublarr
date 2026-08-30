r"""Record WHAT a provider failure was, not just that there was one.

``healthy: false`` is not something anyone can act on. A rejected key, a host
whose domain no longer resolves and a rate limit need three different
responses, and the panel showed one shape for all of them (#201).

``last_failure_kind`` holds the classified cause of the most recent failure —
auth / network / rate_limit / timeout / other — so the status can say
"Credentials rejected" or "Host unreachable" instead of counting failures.

Nullable with no backfill on purpose: the classification did not exist for
past failures, and inventing a cause for them would put a confident wrong
label on history. Existing rows simply keep reporting the generic reason
until their provider fails again.

Revision ID: i201_failure_kind
Revises: i198_reset_counters
"""

import sqlalchemy as sa
from alembic import op

revision = "i201_failure_kind"
down_revision = "i198_reset_counters"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "provider_stats" not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_columns("provider_stats")}
    if "last_failure_kind" not in existing:
        op.add_column(
            "provider_stats", sa.Column("last_failure_kind", sa.String(16), nullable=True)
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "provider_stats" not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_columns("provider_stats")}
    if "last_failure_kind" in existing:
        op.drop_column("provider_stats", "last_failure_kind")
