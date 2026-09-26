"""The foreign-track sweep's pace is configurable from the UI (1.15.0-rc.5).

Prod 2026-09-26: ~1.6 GB/min, 5 566 files / 38.5 TiB queued — at the default
(every 6 h, 30 min per run) that is months. The owner asked for the pace to be
"einstellbar": a per-run budget and a schedule (6 h / hourly / only at night).

Three things have to hold for that:
- the budget is bounded where config is saved, because ``reload_settings``
  applies DB overrides with ``model_copy`` and never re-validates, so a
  ``Field(ge=, le=)`` alone would not stop a bad value from the UI;
- the scheduler's timeout stays at least twice the largest allowed budget,
  or a legitimate long run would be booked as ``timeout`` and asked to stop;
- the three schedule presets the UI sends are accepted by the scheduler
  PATCH, and the nightly one fires in the operator's own time zone rather
  than in UTC (the container runs UTC, so "01:00" would be 03:00 in CEST).
"""

from datetime import datetime

import pytest

BUDGET_MIN_S = 300
BUDGET_MAX_S = 3600


class TestBudgetBounds:
    def test_settings_field_declares_the_bounds(self):
        from config_settings import UISettings

        meta = UISettings.model_fields["foreign_track_sweep_budget_s"].metadata
        ge = next(m.ge for m in meta if hasattr(m, "ge"))
        le = next(m.le for m in meta if hasattr(m, "le"))
        assert (ge, le) == (BUDGET_MIN_S, BUDGET_MAX_S)

    @pytest.mark.parametrize("value", [0, 60, 299, 3601, 14400, -5, "abc", True, 12.5, None])
    def test_out_of_range_budget_is_rejected_before_anything_is_saved(self, client, value):
        from db.config import get_config_entry

        with client.application.app_context():
            before = get_config_entry("foreign_track_sweep_enabled")
        response = client.put(
            "/api/v1/config",
            json={"foreign_track_sweep_enabled": True, "foreign_track_sweep_budget_s": value},
        )
        assert response.status_code == 400, response.get_json()
        assert "foreign_track_sweep_budget_s" in response.get_json()["error"]
        with client.application.app_context():
            assert get_config_entry("foreign_track_sweep_enabled") == before

    @pytest.mark.parametrize("value", [300, 1800, 3600, "900"])
    def test_in_range_budget_roundtrips(self, client, value):
        response = client.put("/api/v1/config", json={"foreign_track_sweep_budget_s": value})
        assert response.status_code == 200, response.get_json()
        assert response.get_json()["config"]["foreign_track_sweep_budget_s"] == int(value)


def test_sweep_timeout_covers_twice_the_largest_allowed_budget():
    from services.scheduler import _build_default_jobs

    spec = next(j for j in _build_default_jobs() if j.id == "foreign_track_sweep")
    assert spec.timeout_s >= 2 * BUDGET_MAX_S


# ── Scheduler presets ──────────────────────────────────────────────────────


@pytest.fixture
def sched_app(tmp_path, monkeypatch):
    monkeypatch.setenv("SUBLARR_DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.setenv("SUBLARR_SCHEDULER_ROLE", "primary")
    monkeypatch.setenv("SUBLARR_API_KEY", "")
    from config import reload_settings

    reload_settings()
    from app import create_app

    app = create_app(testing=True)
    from extensions import db as sa_db

    with app.app_context():
        sa_db.create_all()
    yield app
    scheduler = app.extensions.get("scheduler")
    if scheduler and scheduler.running:
        scheduler.shutdown(timeout_s=2)


@pytest.fixture
def sched_client(sched_app):
    from services.scheduler import bootstrap_scheduler

    with sched_app.app_context():
        if sched_app.extensions.get("scheduler") is None:
            bootstrap_scheduler(sched_app)
    return sched_app.test_client()


_JOB = "/api/v1/scheduler/jobs/foreign_track_sweep"


@pytest.mark.parametrize(
    "trigger,expected",
    [
        ({"type": "interval", "hours": 6}, {"type": "interval", "seconds": 21600}),
        ({"type": "interval", "hours": 1}, {"type": "interval", "seconds": 3600}),
    ],
)
def test_interval_presets_are_accepted(sched_client, trigger, expected):
    r = sched_client.patch(_JOB, json={"trigger": trigger})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["trigger"] == expected


def test_nightly_preset_fires_in_the_given_time_zone(sched_client):
    r = sched_client.patch(
        _JOB,
        json={
            "trigger": {
                "type": "cron",
                "hour": "1-6",
                "minute": "0",
                "timezone": "Europe/Berlin",
            }
        },
    )
    assert r.status_code == 200, r.get_json()
    data = r.get_json()
    assert data["trigger"] == {
        "type": "cron",
        "hour": "1-6",
        "minute": "0",
        "timezone": "Europe/Berlin",
    }
    # The next fire is at a Berlin wall-clock hour between 01 and 06, not UTC.
    nxt = datetime.fromisoformat(data["next_run_time"])
    from zoneinfo import ZoneInfo

    local = nxt.astimezone(ZoneInfo("Europe/Berlin"))
    assert 1 <= local.hour <= 6 and local.minute == 0


def test_cron_without_time_zone_stays_utc(sched_client):
    r = sched_client.patch(_JOB, json={"trigger": {"type": "cron", "hour": "3", "minute": "0"}})
    assert r.status_code == 200
    assert r.get_json()["trigger"]["timezone"] == "UTC"


@pytest.mark.parametrize("tz", ["Mars/Olympus", "../../etc/passwd", "", "x" * 200])
def test_unknown_time_zone_is_a_400(sched_client, tz):
    r = sched_client.patch(
        _JOB, json={"trigger": {"type": "cron", "hour": "1-6", "minute": "0", "timezone": tz}}
    )
    assert r.status_code == 400
    assert r.get_json()["error_type"] == "ValidationError"


def test_reset_default_restores_the_six_hour_default(sched_client):
    sched_client.patch(_JOB, json={"trigger": {"type": "interval", "hours": 1}})
    r = sched_client.post(f"{_JOB}/reset-default")
    assert r.status_code == 200
    data = r.get_json()
    assert data["trigger"] == {"type": "interval", "seconds": 21600}
    assert data["trigger_is_default"] is True
