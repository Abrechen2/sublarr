r"""Reset the provider search counters so ``result_rate`` stops lying.

``provider_stats.successful_searches`` is the numerator of ``result_rate``,
but until this release the search coordinator incremented it whenever the
provider call merely returned. Every row therefore holds a count of "calls
that did not raise" under a name that means "searches that found something".

Fixing the write path alone leaves the change inert on any install that has
run before. Two reasons, and the second is the decisive one:

* The ratio would mix two meanings for months — old inflated counts over a
  denominator that keeps growing honestly.
* The new "answered plenty, delivered nothing" health verdict clears itself
  the moment ``successful_searches > 0``. On an existing install every
  provider carries a large historical value, so the verdict would never fire
  for exactly the people who reported the problem.

So the counters that feed the two rates are zeroed and start over with their
real meaning. Nothing is thrown away: the pre-reset rows are copied to
``provider_stats_pre_i198`` first, the same way ``provider_stats_pre_1132``
preserved the 1.13.2 baseline, so the before/after is still provable later.

What is deliberately NOT reset: ``consecutive_failures``, ``auto_disabled``,
``disabled_until`` and the ``last_*`` timestamps. Those describe the provider's
current state rather than its history, and clearing them would re-enable
providers that are auto-disabled for good reason.

Revision ID: i198_reset_counters
Revises: tm2_drop_same_lang
"""

import sqlalchemy as sa
from alembic import op

revision = "i198_reset_counters"
down_revision = "tm2_drop_same_lang"
branch_labels = None
depends_on = None

BASELINE_TABLE = "provider_stats_pre_i198"

#: The four counters that feed download_rate and result_rate. They share a
#: denominator, so resetting one without the others would produce a ratio
#: worse than the one being fixed.
_COUNTERS = (
    "total_searches",
    "successful_searches",
    "successful_downloads",
    "failed_downloads",
)


def reset_search_counters(conn) -> int:
    """Snapshot then zero the counters on ``conn``; return rows affected.

    Split out from ``upgrade`` so a test can run it against a real database —
    a migration that is only ever read is a migration nobody has run.
    """
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()
    if "provider_stats" not in tables:
        return 0

    if BASELINE_TABLE not in tables:
        conn.execute(sa.text(f"CREATE TABLE {BASELINE_TABLE} AS SELECT * FROM provider_stats"))

    assignments = ", ".join(f"{c} = 0" for c in _COUNTERS)
    result = conn.execute(sa.text(f"UPDATE provider_stats SET {assignments}"))
    return result.rowcount or 0


def upgrade() -> None:
    conn = op.get_bind()
    rows = reset_search_counters(conn)
    if rows:
        print(f"i198: reset search counters on {rows} provider rows (baseline in {BASELINE_TABLE})")


def downgrade() -> None:
    """Restore the counters from the baseline snapshot, if it is still there."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if BASELINE_TABLE not in inspector.get_table_names():
        return
    for counter in _COUNTERS:
        conn.execute(
            sa.text(
                f"UPDATE provider_stats SET {counter} = ("
                f"  SELECT b.{counter} FROM {BASELINE_TABLE} b"
                "   WHERE b.provider_name = provider_stats.provider_name"
                ") WHERE provider_name IN ("
                f"  SELECT provider_name FROM {BASELINE_TABLE}"
                ")"
            )
        )
