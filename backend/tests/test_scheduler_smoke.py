"""Phase 1 smoke test — full bootstrap_scheduler stack."""

import time


def test_full_bootstrap_and_history_write(monkeypatch, tmp_path):
    """bootstrap_scheduler registers scheduler_history_cleanup; run-now it
    and verify a row is written."""
    monkeypatch.setenv("SUBLARR_SCHEDULER_ROLE", "primary")
    monkeypatch.setenv("SUBLARR_DB_PATH", str(tmp_path / "app.db"))

    from config import reload_settings
    reload_settings()
    from app import create_app

    app = create_app(testing=True)
    from extensions import db as sa_db
    with app.app_context():
        sa_db.create_all()

    # testing=True skips _start_schedulers; call bootstrap_scheduler directly
    # to exercise the full Phase 1 stack end-to-end.
    from services.scheduler import bootstrap_scheduler

    bootstrap_scheduler(app)

    try:
        from db.models.scheduler import JobRun
        from extensions import db

        scheduler = app.extensions.get("scheduler")
        assert scheduler is not None
        assert scheduler.running is True

        with app.app_context():
            db.session.query(JobRun).delete()
            db.session.commit()

        oneshot_id = scheduler.run_now("scheduler_history_cleanup")
        assert oneshot_id.startswith("scheduler_history_cleanup_oneshot_")

        # Wait up to 5s for the one-shot to execute
        deadline = time.monotonic() + 5
        n = 0
        while time.monotonic() < deadline:
            with app.app_context():
                n = db.session.query(JobRun).count()
            if n > 0:
                break
            time.sleep(0.1)

        with app.app_context():
            rows = db.session.query(JobRun).all()
        assert len(rows) >= 1
        assert rows[0].job_id == "scheduler_history_cleanup"
        assert rows[0].triggered_by == "manual"
    finally:
        if app.extensions.get("scheduler"):
            app.extensions["scheduler"].shutdown(timeout_s=2)
