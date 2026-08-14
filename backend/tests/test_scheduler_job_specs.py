"""Sanity checks on the default JobSpec registry.

A job whose timeout is shorter than one unit of its work reports a timeout
on every run that does real work, which makes the history useless — you
cannot tell a genuinely stuck job from a busy one.
"""

from __future__ import annotations

import pytest


def _spec(job_id: str):
    from services.scheduler import _build_default_jobs

    return next(j for j in _build_default_jobs() if j.id == job_id)


class TestTimeoutsExceedOneUnitOfWork:
    def test_automation_timeout_exceeds_one_item(self):
        """Measured on production over the 7 days to 2026-08-14:
        4536 ok runs (max 582s, right up against the 600s budget), plus 41
        `timeout` and 11 `timeout_abandoned` rows clustered at 610-668s —
        runs killed while doing exactly the work they were asked to do.
        The job also inherits sidecar translation, whose single item measured
        ~870s, so 600s could not fit one unit of its new work either.
        """
        assert _spec("subtitle_automation").timeout_s >= 1800

    @pytest.mark.parametrize("job_id", ["wanted_search", "subtitle_automation"])
    def test_long_running_jobs_have_a_timeout_at_all(self, job_id):
        spec = _spec(job_id)
        assert isinstance(spec.timeout_s, int) and spec.timeout_s > 0


class TestTimeoutIsNotPersisted:
    def test_timeout_comes_from_code_not_the_jobstore(self):
        """A changed timeout must reach existing installs on upgrade.

        The JobStore persists trigger and next_run_time; ``_tick_wrapper``
        reads ``timeout_s`` off the code-built JobSpec at fire time. If a
        refactor ever moved the timeout into the persisted row, every
        existing install would silently keep the old value and the release
        notes ("applies as soon as you update") would become a lie.
        """
        import inspect

        from services.scheduler import ticks

        source = inspect.getsource(ticks._tick_wrapper)
        assert "spec.timeout_s" in source, (
            "the tick wrapper no longer reads the timeout from the code-built "
            "JobSpec — check whether it is now persisted per install"
        )


class TestRegistryIsWellFormed:
    def test_job_ids_are_unique(self):
        from services.scheduler import _build_default_jobs

        ids = [j.id for j in _build_default_jobs()]
        assert len(ids) == len(set(ids)), f"duplicate job ids: {ids}"
