"""A job that stops when asked must be recorded as having stopped.

`timeout_abandoned` exists to mean something specific and alarming: the run
ignored the stop request and is *still running* — one sweep was still reading
a library sixteen hours after that line was logged. It only carries that
meaning if a job which does stop is not also labelled with it.

The grace was `max(1, min(60, timeout_s // 10))`. The `min(60, …)` cap
defeated the proportional term for every long job, and prod on 2026-08-15
measured three wind-downs past it, all of them cooperative:

    wanted_search        cancel 09:58:02 → last work 09:58:33     (31s)
    wanted_search        cancel 08:23:54 → last work 08:26:49    (175s)
    subtitle_automation  cancel 10:07:51 → "stopping as asked"   (197s)

The drain even logs `stopping as asked after 2 item(s)` — it announces the
cooperation it was being accused of skipping. A wind-down is a property of
the work (one in-flight item finishing its post-processing), not of the
timeout it happens to sit under, so jobs may now declare their own.
"""

import time

import pytest
from apscheduler.triggers.interval import IntervalTrigger

from services.scheduler import JobSpec, _tick_wrapper


@pytest.fixture
def flask_app(tmp_path, monkeypatch):
    monkeypatch.setenv("SUBLARR_DB_PATH", str(tmp_path / "app.db"))
    from config import reload_settings

    reload_settings()
    from app import create_app

    app = create_app(testing=True)
    from extensions import db as sa_db

    with app.app_context():
        sa_db.create_all()
    yield app


@pytest.fixture
def db_session(flask_app):
    from extensions import db

    with flask_app.app_context():
        yield db.session
        db.session.rollback()


def _spec(**kw) -> JobSpec:
    return JobSpec(
        id=kw.pop("id", "grace_probe"),
        func=kw.pop("func", lambda: None),
        default_trigger=IntervalTrigger(hours=1),
        **kw,
    )


class TestCancelGraceDeclaration:
    def test_defaults_to_the_proportional_formula(self):
        """Unset means unchanged behaviour for every existing job."""
        assert _spec(timeout_s=300).effective_cancel_grace_s == 30
        assert _spec(timeout_s=60).effective_cancel_grace_s == 6

    def test_default_is_still_capped_at_60(self):
        """The cap stays for jobs that have not measured themselves."""
        assert _spec(timeout_s=1800).effective_cancel_grace_s == 60

    def test_never_below_one_second(self):
        assert _spec(timeout_s=1).effective_cancel_grace_s == 1

    def test_declared_value_wins(self):
        assert _spec(timeout_s=1800, cancel_grace_s=300).effective_cancel_grace_s == 300

    def test_declared_value_must_be_positive(self):
        with pytest.raises(ValueError, match="cancel_grace_s"):
            _spec(timeout_s=1800, cancel_grace_s=0)


class TestRealJobsDeclareMeasuredGraces:
    """The two jobs prod caught mislabelling must carry a measured value."""

    def test_wanted_search_and_automation_declare_a_grace(self):
        from services.scheduler import _build_default_jobs

        by_id = {s.id: s for s in _build_default_jobs()}

        # 175s was the longest wind-down measured; the value must clear it
        # with room, or the label goes back to lying on a slower day.
        assert by_id["wanted_search"].effective_cancel_grace_s >= 300

        # One in-flight translation is the drain's unit of work, and the
        # queue's own timings show those running up to ~16 minutes.
        assert by_id["subtitle_automation"].effective_cancel_grace_s >= 900

    def test_other_jobs_are_left_on_the_default(self):
        """No blanket raise — only the jobs with evidence behind them."""
        from services.scheduler import _build_default_jobs

        by_id = {s.id: s for s in _build_default_jobs()}
        assert by_id["scheduler_history_cleanup"].effective_cancel_grace_s == 6


class TestWrapperUsesTheDeclaredGrace:
    """The end-to-end point: a cooperative stop must not read as abandoned."""

    def test_job_stopping_inside_declared_grace_is_not_abandoned(self, flask_app, db_session):
        """Overruns a 1s timeout, then needs ~3s more to leave.

        The default formula would have granted 1s and called it abandoned;
        the declared 10s covers it, so the row must say the run stopped.
        """
        from db.models.scheduler import JobRun

        spec = _spec(
            id="grace_cooperative",
            func=lambda: time.sleep(3),
            timeout_s=1,
            cancel_grace_s=10,
        )
        _tick_wrapper(flask_app, spec, triggered_by="schedule")()

        row = db_session.query(JobRun).filter_by(job_id="grace_cooperative").one()
        assert row.status == "timeout", f"expected a clean timeout, got {row.status!r}"

    def test_without_the_declaration_the_same_job_is_abandoned(self, flask_app, db_session):
        """Guards the test above: it must be the grace doing the work.

        Same job, same timing, no declared grace — this is the label prod was
        producing, so it has to still be reachable.
        """
        from db.models.scheduler import JobRun

        spec = _spec(
            id="grace_default",
            func=lambda: time.sleep(3),
            timeout_s=1,
        )
        _tick_wrapper(flask_app, spec, triggered_by="schedule")()

        row = db_session.query(JobRun).filter_by(job_id="grace_default").one()
        assert row.status == "timeout_abandoned"
