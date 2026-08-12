"""Every status the scheduler writes must fit the column that stores it.

This exists because `timeout_abandoned` (17 chars) was added against a
VARCHAR(16). SQLite ignores declared lengths, so the whole test suite, CI and
the SQLite beta instance wrote it without complaint; PostgreSQL raised
StringDataRightTruncation and the row was dropped. The status that flags a
runaway job became the one status that never reached history, and the absence
read as "this never happens".

A length assertion is dialect-independent, so it fails on SQLite too — which is
the only way this class of bug gets caught before an RC.
"""

import pytest

from db.models.scheduler import JobRun

# Every value the scheduler assigns to `status`. Add to this list when a new
# outcome is introduced; the test then tells you whether the column has room.
KNOWN_STATUSES = (
    "ok",
    "error",
    "timeout",
    "timeout_abandoned",
    "skipped_overlap",
    "missed",
    "running",
)

# Values assigned to `triggered_by`.
KNOWN_TRIGGERS = ("schedule", "manual")


def _column_length(name: str) -> int:
    column = JobRun.__table__.columns[name]
    length = column.type.length
    assert length is not None, f"{name} has no declared length to check against"
    return length


@pytest.mark.parametrize("status", KNOWN_STATUSES)
def test_status_fits_its_column(status: str) -> None:
    limit = _column_length("status")
    assert len(status) <= limit, (
        f"status {status!r} is {len(status)} chars but the column holds {limit}. "
        "PostgreSQL will refuse the row and the run disappears from history."
    )


@pytest.mark.parametrize("trigger", KNOWN_TRIGGERS)
def test_triggered_by_fits_its_column(trigger: str) -> None:
    limit = _column_length("triggered_by")
    assert len(trigger) <= limit, (
        f"triggered_by {trigger!r} is {len(trigger)} chars but the column holds {limit}."
    )


def test_status_column_has_headroom_for_another_outcome() -> None:
    """A column sized to the longest current value invites the next migration."""
    longest = max(len(s) for s in KNOWN_STATUSES)
    assert _column_length("status") >= longest + 8
