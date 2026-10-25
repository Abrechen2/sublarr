"""The series health scan job runs inside the app context.

``POST /library/series/<id>/health/scan`` hands its job to the background
pool, whose threads have no Flask context. For a standalone series the job
looks the series up in the database first, so it died with "Working outside
of application context" and never sent ``subtitle_health_complete``
(1.18.0-rc.2 end-to-end test, F2).
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from unittest.mock import patch

import pytest


class _Result:
    issues: list = []

    def to_dict(self):
        return {"issues": []}


@pytest.fixture
def no_sonarr(monkeypatch):
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: None)
    monkeypatch.setattr(
        "services.subtitle_health.series_scan.get_sonarr_client", lambda *a, **kw: None
    )


def _standalone_series(client, tmp_path) -> int:
    from db.models.standalone import StandaloneSeries
    from extensions import db

    folder = tmp_path / "My Show (2020)"
    season = folder / "Season 1"
    season.mkdir(parents=True)
    (season / "My Show - S01E01 [1080p].mkv").write_bytes(b"\x00")
    now = datetime.now(UTC)
    with client.application.app_context():
        row = StandaloneSeries(
            title="My Show", folder_path=str(folder), created_at=now, updated_at=now
        )
        db.session.add(row)
        db.session.commit()
        return row.id


def _run_in_fresh_thread(fn) -> BaseException | None:
    """Run ``fn`` like the pool does: a thread with no Flask context."""
    errors: list[BaseException] = []

    def _target():
        try:
            fn()
        except BaseException as exc:  # noqa: BLE001 — reported to the test
            errors.append(exc)

    thread = threading.Thread(target=_target)
    thread.start()
    thread.join(timeout=30)
    return errors[0] if errors else None


def test_standalone_series_scan_job_has_an_app_context(client, no_sonarr, tmp_path):
    from flask import has_app_context

    sid = _standalone_series(client, tmp_path)
    contexts: list[bool] = []

    def _scan(**_kw):
        contexts.append(has_app_context())
        return _Result()

    with patch("routes.tracks.submit_background") as bg:
        resp = client.post(f"/api/v1/library/series/{-sid}/health/scan")
    assert resp.status_code == 202
    job = bg.call_args.args[0]
    job_args = bg.call_args.args[1:]

    with (
        patch("services.subtitle_health.series_scan.scan_episode", side_effect=_scan),
        patch("routes.tracks.emit_event") as emitted,
    ):
        error = _run_in_fresh_thread(lambda: job(*job_args))

    assert error is None, repr(error)
    assert contexts == [True]
    complete = [c for c in emitted.call_args_list if c.args[0] == "subtitle_health_complete"]
    assert len(complete) == 1
    assert complete[0].args[1]["episodes_scanned"] == 1


def test_sonarr_series_scan_job_has_an_app_context(client, tmp_path, monkeypatch):
    """Same job for a Sonarr series: without a context the findings were not saved."""
    from flask import has_app_context

    video = tmp_path / "Show - S01E01.mkv"
    video.write_bytes(b"\x00")

    class _Sonarr:
        def get_episodes(self, _series_id):
            return [{"id": 501}]

        def get_episode_file_path(self, _ep_id):
            return str(video)

    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: _Sonarr())
    monkeypatch.setattr(
        "services.subtitle_health.series_scan.get_sonarr_client", lambda *a, **kw: _Sonarr()
    )
    contexts: list[bool] = []

    def _scan(**_kw):
        contexts.append(has_app_context())
        return _Result()

    with patch("routes.tracks.submit_background") as bg:
        resp = client.post("/api/v1/library/series/12/health/scan")
    assert resp.status_code == 202
    job = bg.call_args.args[0]

    with (
        patch("services.subtitle_health.series_scan.scan_episode", side_effect=_scan),
        patch("routes.tracks.emit_event"),
    ):
        error = _run_in_fresh_thread(job)

    assert error is None, repr(error)
    assert contexts == [True]
