"""phase 1 scheduler foundation: budget tables, wanted_items state machine, reset frozen items

Revision ID: b1u2d3g4e5t6
Revises: h1i2j3k4l5m6
Create Date: 2026-04-16

Adds the infrastructure for the API-Budget Scheduler feature (V1 blocker):

1. New tables:
   - ``provider_budget_usage`` — sliding-window call counters per provider
   - ``provider_learned_limits`` — adaptive limit tuning from observed 429s

2. ``wanted_items`` additions:
   - ``priority`` (premium | standard | backlog)
   - ``failure_kind`` (no_result | no_result_slow | provider_error | NULL)
   - ``error_count`` + ``last_error_at`` — track provider-side failures
     separately from ``search_count`` so transient errors do not burn retries

3. Indexes:
   - ``ix_wanted_fair_rotation`` — powers the fair-rotation scheduler query
   - ``ix_wanted_retry_after`` — partial index for pending retries

4. Data migration:
   - Reset every item stuck on ``error = 'Max search attempts reached'`` — the
     old freeze semantics are removed entirely in Phase 1; they are replaced by
     a slow-mode retry (one attempt per 30 days, see wanted_search_runner).
   - Seed ``priority`` based on item age so downstream scheduling can weight
     premium (< 7 days old) and backlog (> 180 days + prior failures).

Dialect notes:
- ``INTERVAL '...'`` is Postgres-only, so all time arithmetic runs in Python
  and is passed in as bound parameters.
- ``NULLS FIRST`` inside CREATE INDEX is supported by both Postgres and the
  SQLite version bundled with Python 3.12+, but it is fragile with
  ``render_as_batch=True``. We therefore apply the expression index only on
  Postgres; SQLite gets a simpler index that still satisfies the query planner
  for dev/test workloads.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "b1u2d3g4e5t6"
down_revision = "h1i2j3k4l5m6"
branch_labels = None
depends_on = None


def _is_postgres() -> bool:
    return op.get_context().dialect.name == "postgresql"


def upgrade() -> None:
    # ── New table: provider_budget_usage ───────────────────────────────────
    op.create_table(
        "provider_budget_usage",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("provider_name", sa.String(length=50), nullable=False),
        sa.Column("window_type", sa.String(length=10), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("calls_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("calls_limit", sa.Integer(), nullable=False),
        sa.UniqueConstraint(
            "provider_name", "window_type", "window_start", name="uq_budget_window"
        ),
    )
    op.create_index(
        "ix_budget_provider_window",
        "provider_budget_usage",
        ["provider_name", "window_type", "window_start"],
    )

    # ── New table: provider_learned_limits ─────────────────────────────────
    op.create_table(
        "provider_learned_limits",
        sa.Column("provider_name", sa.String(length=50), nullable=False),
        sa.Column("window_type", sa.String(length=10), nullable=False),
        sa.Column("configured_limit", sa.Integer(), nullable=False),
        sa.Column("observed_limit", sa.Integer(), nullable=True),
        sa.Column(
            "adjustment_factor", sa.Float(), nullable=False, server_default="1.0"
        ),
        sa.Column("last_429_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "consecutive_good_days",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("provider_name", "window_type"),
    )

    # ── wanted_items additions ─────────────────────────────────────────────
    with op.batch_alter_table("wanted_items") as batch:
        batch.add_column(
            sa.Column(
                "priority",
                sa.String(length=20),
                nullable=False,
                server_default="standard",
            )
        )
        batch.add_column(sa.Column("failure_kind", sa.String(length=20), nullable=True))
        batch.add_column(
            sa.Column(
                "error_count", sa.Integer(), nullable=False, server_default="0"
            )
        )
        batch.add_column(
            sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch.create_check_constraint(
            "ck_wanted_priority",
            "priority IN ('premium', 'standard', 'backlog')",
        )

    # ── Indexes ────────────────────────────────────────────────────────────
    if _is_postgres():
        op.execute(
            "CREATE INDEX ix_wanted_fair_rotation ON wanted_items "
            "(status, last_search_at NULLS FIRST, search_count)"
        )
        op.execute(
            "CREATE INDEX ix_wanted_retry_after ON wanted_items (status, retry_after) "
            "WHERE retry_after IS NOT NULL"
        )
    else:
        # SQLite: skip NULLS FIRST and partial-index syntax; plain indexes still
        # satisfy the planner for dev/test workloads.
        op.create_index(
            "ix_wanted_fair_rotation",
            "wanted_items",
            ["status", "last_search_at", "search_count"],
        )
        op.create_index(
            "ix_wanted_retry_after",
            "wanted_items",
            ["status", "retry_after"],
        )

    # ── Data migration ─────────────────────────────────────────────────────
    # 1. Reset every item that was permanently frozen by the old flow.
    op.execute(
        sa.text(
            "UPDATE wanted_items SET search_count = 0, error = NULL, retry_after = NULL "
            "WHERE error = :marker"
        ).bindparams(marker="Max search attempts reached")
    )

    # 2. Seed priority tiers based on age + history — computed in Python to stay
    #    dialect-agnostic.
    now = datetime.now(timezone.utc)
    premium_cutoff = now - timedelta(days=7)
    backlog_cutoff = now - timedelta(days=180)

    op.execute(
        sa.text(
            "UPDATE wanted_items SET priority = 'premium' "
            "WHERE added_at >= :cutoff"
        ).bindparams(cutoff=premium_cutoff)
    )
    op.execute(
        sa.text(
            "UPDATE wanted_items SET priority = 'backlog' "
            "WHERE search_count >= 3 AND added_at < :cutoff"
        ).bindparams(cutoff=backlog_cutoff)
    )


def downgrade() -> None:
    op.drop_index("ix_wanted_retry_after", table_name="wanted_items")
    op.drop_index("ix_wanted_fair_rotation", table_name="wanted_items")

    with op.batch_alter_table("wanted_items") as batch:
        batch.drop_constraint("ck_wanted_priority", type_="check")
        batch.drop_column("last_error_at")
        batch.drop_column("error_count")
        batch.drop_column("failure_kind")
        batch.drop_column("priority")

    op.drop_table("provider_learned_limits")
    op.drop_index("ix_budget_provider_window", table_name="provider_budget_usage")
    op.drop_table("provider_budget_usage")
