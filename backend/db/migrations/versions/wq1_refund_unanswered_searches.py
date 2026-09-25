"""Give back search attempts that no provider answered.

Two writers charged ``wanted_items.search_count`` without any provider having
been asked — both closed in the same release:

- ``services.wanted_search_outcome.record_search_outcome(kind="no_result")``
  booked a search in which every provider was skipped as rate-limited, over
  budget or auto-disabled as a genuine miss. Now such a search is booked as
  ``provider_error`` (``provider_reach``), which never charges the count.
- ``wanted_search.process._check_max_search_attempts`` booked another
  ``no_result`` for every item at the attempt cap — including slow-mode items
  whose 30-day window had elapsed — and skipped the search. Now it only parks
  items at the cap that carry no retry marker.

Measured on the reference install on 2026-09-25: 3 229 of 3 601 slow-mode items
had an unanswered last search; 105 of the 107 items at ``search_count=4`` had
been bumped by the gate more than a day after their last real search.

What this rewrites, for ``status='wanted'`` rows with ``failure_kind`` in
(``no_result``, ``no_result_slow``):

1. ``search_count`` above the attempt cap is lowered to the cap. Every count
   above it came from the gate, which stopped all searching at the cap.
2. When the row's last decision log shows no provider answered (no ``ok``
   provider, no cache hit, at least one transient skip or failure), one more
   attempt is refunded. Rows without a decision log are left as they are.
3. A row whose count dropped below the cap goes back to ``no_result``; every
   changed row becomes due again, spread over the next 7 days (``id % 168``
   hours) so the whole cohort does not hit the providers in one tick.

Rows are only rewritten, never deleted. A later genuine miss re-charges the
count normally. Not reversible: the old counts are not kept. Not idempotent
either — a second run would refund again — so it relies on running once:
Alembic records the revision, and ``untracked_data_repairs`` writes its
marker in the same transaction as the repair.

Forced items were charged the same way, but they never had a decision log
(the forced branch ran before it started), so they cannot be told apart and
are left as they are. The writer is closed for them in the same release.

Revision ID: wq1_refund_unanswered
Revises: tm5_quality_score
"""

import json
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from alembic import op

revision = "wq1_refund_unanswered"
down_revision = "tm5_quality_score"
branch_labels = None
depends_on = None

_DEFAULT_MAX_ATTEMPTS = 3
_SPREAD_HOURS = 168

# Frozen copy of provider_reach.TRANSIENT_REASONS at the time of writing.
_TRANSIENT = frozenset(
    {
        "rate_limited",
        "budget_exhausted",
        "pool_cooling",
        "auto_disabled",
        "circuit_open",
        "timeout",
        "error",
    }
)

_wanted = sa.table(
    "wanted_items",
    sa.column("id", sa.Integer),
    sa.column("search_count", sa.Integer),
    sa.column("failure_kind", sa.String),
    sa.column("retry_after", sa.DateTime(timezone=True)),
)


def configured_max_attempts(conn) -> int:
    """``wanted_max_search_attempts`` as the app resolves it.

    A UI-only setting: ``config_entries`` then the default. The
    ``SUBLARR_WANTED_MAX_SEARCH_ATTEMPTS`` env var is ignored at runtime and
    must be ignored here too.
    """
    inspector = sa.inspect(conn)
    raw = None
    if "config_entries" in inspector.get_table_names():
        raw = conn.execute(
            sa.text("SELECT value FROM config_entries WHERE key = 'wanted_max_search_attempts'")
        ).scalar()
    try:
        value = int(str(raw).strip().strip('"'))
    except (TypeError, ValueError):
        return _DEFAULT_MAX_ATTEMPTS
    return value if value > 0 else _DEFAULT_MAX_ATTEMPTS


def was_unanswered(log_json: str | None) -> bool:
    """True when the decision log shows searches nobody answered."""
    if not log_json:
        return False
    try:
        log = json.loads(log_json)
    except (TypeError, ValueError):
        return False
    if not isinstance(log, dict):
        return False
    transient = False
    for search in log.get("searches") or []:
        if search.get("cache_hit"):
            return False
        if search.get("unfinished_providers"):
            transient = True
        for provider in search.get("providers") or []:
            status = provider.get("status")
            if status == "ok":
                return False
            if status in _TRANSIENT or provider.get("reason") in _TRANSIENT:
                transient = True
    return transient


def refund_unanswered(conn, max_attempts: int, now: datetime | None = None) -> int:
    """Rewrite affected rows; return how many changed. Split out for tests."""
    if "wanted_items" not in sa.inspect(conn).get_table_names():
        return 0
    now = now or datetime.now(UTC)
    rows = conn.execute(
        sa.text(
            "SELECT id, search_count, failure_kind, last_decision_log_json FROM wanted_items "
            "WHERE status = 'wanted' AND failure_kind IN ('no_result', 'no_result_slow')"
        )
    ).fetchall()
    changed = 0
    for row_id, count, kind, log_json in rows:
        count = count or 0
        new_count = min(count, max_attempts)
        if was_unanswered(log_json):
            new_count = max(new_count - 1, 0)
        if new_count == count:
            continue
        new_kind = kind if new_count >= max_attempts else "no_result"
        conn.execute(
            _wanted.update()
            .where(_wanted.c.id == row_id)
            .values(
                search_count=new_count,
                failure_kind=new_kind,
                retry_after=now + timedelta(hours=row_id % _SPREAD_HOURS),
            )
        )
        changed += 1
    return changed


def upgrade() -> None:
    conn = op.get_bind()
    changed = refund_unanswered(conn, configured_max_attempts(conn))
    if changed:
        print(f"wq1_refund_unanswered: refunded unanswered search attempts on {changed} items")


def downgrade() -> None:
    """Not reversible — the previous counts are not kept."""
