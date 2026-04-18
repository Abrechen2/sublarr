"""JobSpec dataclass validation."""

import pytest
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from services.scheduler import JobSpec


def _noop():
    pass


def test_jobspec_minimum_fields():
    spec = JobSpec(
        id="x",
        func=_noop,
        default_trigger=IntervalTrigger(seconds=60),
    )
    assert spec.id == "x"
    assert spec.timeout_s == 300
    assert spec.max_instances == 1
    assert spec.coalesce is True
    assert spec.misfire_grace_time is None
    assert spec.description == ""


def test_jobspec_rejects_empty_id():
    with pytest.raises(ValueError, match="id must be non-empty"):
        JobSpec(id="", func=_noop, default_trigger=IntervalTrigger(seconds=60))


def test_jobspec_rejects_invalid_timeout():
    with pytest.raises(ValueError, match="timeout_s"):
        JobSpec(
            id="x",
            func=_noop,
            default_trigger=IntervalTrigger(seconds=60),
            timeout_s=0,
        )


def test_jobspec_rejects_non_callable_func():
    with pytest.raises(TypeError, match="callable"):
        JobSpec(
            id="x",
            func="not callable",
            default_trigger=IntervalTrigger(seconds=60),
        )


def test_jobspec_accepts_cron_trigger():
    spec = JobSpec(
        id="x",
        func=_noop,
        default_trigger=CronTrigger(hour=3, minute=0),
    )
    assert isinstance(spec.default_trigger, CronTrigger)


def test_jobspec_is_immutable():
    spec = JobSpec(id="x", func=_noop, default_trigger=IntervalTrigger(seconds=60))
    with pytest.raises((AttributeError, TypeError)):
        spec.id = "changed"


def test_compute_default_misfire_grace_time_interval():
    from services.scheduler import compute_default_misfire_grace_time

    assert compute_default_misfire_grace_time(IntervalTrigger(seconds=120)) == 60
    assert compute_default_misfire_grace_time(IntervalTrigger(minutes=10)) == 300


def test_compute_default_misfire_grace_time_cron():
    from services.scheduler import compute_default_misfire_grace_time

    assert compute_default_misfire_grace_time(CronTrigger(hour=3, minute=0)) == 60
