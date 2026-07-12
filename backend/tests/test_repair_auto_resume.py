"""A quota-interrupted repair run must finish itself — nobody restarts it by hand.

The sharp run over a damaged library spans several provider-quota days. When a
run stops on quota exhaustion it persists a pending resume (language + when the
allowance returns), and the ``repair_resume`` scheduler tick starts the next
pass once that moment has passed — repeating until a pass completes cleanly.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from services.repair import job, resume
from services.repair.runner import QuotaExhaustedError


@pytest.fixture(autouse=True)
def _fresh_state(app_ctx):
    """Each test starts with no pending resume and a clean in-memory job state."""
    resume.clear_resume()
    job._state = job.RepairState()
    yield
    resume.clear_resume()
    job._state = job.RepairState()


# --- parsing the provider's reset timestamp ---------------------------------


def test_parse_reset_time_accepts_iso_with_z_suffix():
    parsed = resume.parse_reset_time("2026-07-13T00:00:00.000Z")
    assert parsed == datetime(2026, 7, 13, 0, 0, tzinfo=UTC)


def test_parse_reset_time_rejects_garbage():
    assert resume.parse_reset_time("unknown") is None
    assert resume.parse_reset_time("") is None
    assert resume.parse_reset_time(None) is None


# --- persisting the pending resume ------------------------------------------


def test_schedule_resume_waits_for_reset_plus_buffer():
    now = datetime(2026, 7, 12, 6, 0, tzinfo=UTC)
    reset = datetime(2026, 7, 13, 0, 0, tzinfo=UTC)

    resume_at = resume.schedule_resume(language="de", reset_at=reset, now=now)

    assert resume_at > reset  # never fire before the allowance is back
    assert resume_at - reset <= timedelta(minutes=15)
    pending = resume.pending_resume()
    assert pending is not None
    assert pending["language"] == "de"
    assert pending["resume_at"] == resume_at


def test_schedule_resume_without_reset_time_waits_for_next_utc_midnight():
    now = datetime(2026, 7, 12, 6, 0, tzinfo=UTC)

    resume_at = resume.schedule_resume(language="de", reset_at=None, now=now)

    assert resume_at > now
    assert resume_at.date() == datetime(2026, 7, 13, tzinfo=UTC).date()
    assert resume_at.hour == 0  # OpenSubtitles resets at midnight UTC


def test_schedule_resume_never_schedules_into_the_past():
    now = datetime(2026, 7, 12, 6, 0, tzinfo=UTC)
    stale_reset = now - timedelta(hours=2)  # provider clock said "already reset"

    resume_at = resume.schedule_resume(language="de", reset_at=stale_reset, now=now)

    assert resume_at > now  # otherwise the tick would hammer the provider in a loop


def test_pending_resume_none_after_clear():
    resume.schedule_resume(language="de", reset_at=None)
    resume.clear_resume()
    assert resume.pending_resume() is None


def test_corrupt_persisted_state_reads_as_none():
    from db.config import save_config_entry

    save_config_entry(resume.RESUME_KEY, "{not json")
    assert resume.pending_resume() is None


# --- the scheduler tick ------------------------------------------------------


def test_tick_is_a_noop_when_nothing_is_pending():
    with patch.object(job, "start") as start:
        resume.repair_resume_tick()
    start.assert_not_called()


def test_tick_waits_until_the_resume_moment():
    resume.schedule_resume(language="de", reset_at=datetime.now(UTC) + timedelta(hours=6))
    with patch.object(job, "start") as start:
        resume.repair_resume_tick()
    start.assert_not_called()


def test_tick_starts_a_sharp_run_once_due():
    past = datetime.now(UTC) - timedelta(hours=2)
    resume.schedule_resume(language="de", reset_at=past, now=past - timedelta(hours=1))

    with patch.object(job, "start", return_value=True) as start:
        resume.repair_resume_tick()

    start.assert_called_once()
    _, kwargs = start.call_args
    assert kwargs["language"] == "de"
    assert kwargs["dry_run"] is False


def test_tick_does_not_interrupt_a_running_pass():
    past = datetime.now(UTC) - timedelta(hours=2)
    resume.schedule_resume(language="de", reset_at=past, now=past - timedelta(hours=1))

    with (
        patch.object(job, "is_running", return_value=True),
        patch.object(job, "start") as start,
    ):
        resume.repair_resume_tick()

    start.assert_not_called()


def test_tick_leaves_the_pending_entry_for_the_run_to_claim():
    """start() may race a manual run; the pending entry survives until a sharp
    run actually begins (which clears it itself)."""
    past = datetime.now(UTC) - timedelta(hours=2)
    resume.schedule_resume(language="de", reset_at=past, now=past - timedelta(hours=1))

    with patch.object(job, "start", return_value=False):
        resume.repair_resume_tick()

    assert resume.pending_resume() is not None


# --- the job persists / clears the pending resume ---------------------------


def _run_execute(*, dry_run: bool, outcomes):
    """Drive job._execute with a canned scan + repair_one behaviour."""

    from types import SimpleNamespace

    class _Report:
        repairable = len(outcomes)
        candidates = [SimpleNamespace(file_path=f"/x/{i}.de.srt") for i in range(len(outcomes))]

    def _repair_one(candidate, *, dry_run):
        result = outcomes.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    with (
        patch("services.repair.scanner.scan", return_value=_Report()),
        patch("services.repair.runner.repair_one", side_effect=_repair_one),
    ):
        job._execute(language="de", dry_run=dry_run, limit=None)


def test_quota_stop_on_a_sharp_run_schedules_the_resume():
    reset = datetime.now(UTC) + timedelta(hours=10)
    _run_execute(
        dry_run=False,
        outcomes=[QuotaExhaustedError("quota", reset_at=reset)],
    )

    pending = resume.pending_resume()
    assert pending is not None
    assert pending["language"] == "de"
    assert pending["resume_at"] > reset
    assert job._state.resume_at is not None  # surfaced to the UI


def test_quota_stop_on_a_dry_run_schedules_nothing():
    _run_execute(dry_run=True, outcomes=[QuotaExhaustedError("quota")])
    assert resume.pending_resume() is None
    assert job._state.resume_at is None


def test_a_sharp_run_claims_the_pending_resume_when_it_starts():
    resume.schedule_resume(language="de", reset_at=None)
    _run_execute(dry_run=False, outcomes=[])  # completes without quota trouble
    assert resume.pending_resume() is None


def test_a_dry_run_does_not_claim_the_pending_resume():
    resume.schedule_resume(language="de", reset_at=None)
    _run_execute(dry_run=True, outcomes=[])
    assert resume.pending_resume() is not None
