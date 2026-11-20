"""Accepting a low-score subtitle persists (#255).

The episode Accept button only set a wanted row to 'ignored', while the yellow
low-score state is computed from subtitle_downloads.score — so the warning
never went away, and without a wanted row the click did nothing at all.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

_FP = "/media/standalone/accept/ep1.mkv"


class _S:
    cleanup_foreign_tracks_default = False
    target_language = "de"
    target_language_name = "German"
    source_language = "en"
    source_language_name = "English"
    upgrade_enabled = True
    upgrade_window_days = 7
    upgrade_scan_interval_hours = 24


_SERIES = {
    "id": 77,
    "title": "Accept Test",
    "year": 2024,
    "folder_path": "/media/standalone/accept",
    "status": "continuing",
    "season_count": 1,
    "poster_url": None,
}


def _seed(app, *, status="completed", age_days=0, score=40):
    from db.models.core import WantedItem
    from db.models.providers import SubtitleDownload
    from extensions import db

    now = datetime.now(UTC)
    with app.app_context():
        db.session.add(
            WantedItem(
                item_type="episode",
                file_path=_FP,
                target_language="de",
                standalone_series_id=77,
                season_episode="S01E01",
                title="Episode 1",
                status=status,
                existing_sub="srt",
                added_at=now,
                updated_at=now,
            )
        )
        db.session.add(
            SubtitleDownload(
                file_path=_FP,
                language="de",
                format="srt",
                score=score,
                provider_name="opensubtitles",
                subtitle_id="osub-1",
                downloaded_at=now - timedelta(days=age_days),
            )
        )
        db.session.commit()


@pytest.fixture
def standalone(client, monkeypatch):
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: None)
    monkeypatch.setattr("config.get_settings", lambda: _S())
    return client


def _episode(client):
    with patch("db.standalone.get_standalone_series", return_value=_SERIES):
        resp = client.get("/api/v1/library/series/77")
    assert resp.status_code == 200
    return resp.get_json()["episodes"][0]


def test_accept_is_reported_on_the_episode_and_keeps_the_score(standalone):
    _seed(standalone.application, status="wanted")
    assert _episode(standalone)["subtitle_quality_accepted"]["de"] is False

    resp = standalone.post("/api/v1/library/subtitle-quality/accept", json={"file_path": _FP})

    assert resp.status_code == 200
    assert resp.get_json()["accepted"] == 1
    ep = _episode(standalone)
    assert ep["subtitle_quality_accepted"]["de"] is True
    assert ep["subtitle_scores"]["de"] == 40


def test_accept_without_a_wanted_row_still_persists(standalone):
    from db.models.core import WantedItem
    from extensions import db

    _seed(standalone.application)
    with standalone.application.app_context():
        db.session.query(WantedItem).delete()
        db.session.commit()

    resp = standalone.post("/api/v1/library/subtitle-quality/accept", json={"file_path": _FP})

    assert resp.status_code == 200
    assert resp.get_json()["accepted"] == 1


def test_accept_ignores_the_wanted_row_of_that_language(standalone):
    from db.wanted import get_wanted_items_by_path

    _seed(standalone.application, status="wanted")
    standalone.post(
        "/api/v1/library/subtitle-quality/accept", json={"file_path": _FP, "language": "de"}
    )
    with standalone.application.app_context():
        assert [i["status"] for i in get_wanted_items_by_path(_FP)] == ["ignored"]


def test_a_newer_download_is_not_accepted(standalone):
    from db.models.providers import SubtitleDownload
    from extensions import db

    _seed(standalone.application, age_days=1)
    standalone.post("/api/v1/library/subtitle-quality/accept", json={"file_path": _FP})
    with standalone.application.app_context():
        db.session.add(
            SubtitleDownload(
                file_path=_FP,
                language="de",
                format="srt",
                score=30,
                provider_name="podnapisi",
                subtitle_id="p-2",
                downloaded_at=datetime.now(UTC),
            )
        )
        db.session.commit()
    assert _episode(standalone)["subtitle_quality_accepted"]["de"] is False


@pytest.mark.parametrize(
    "body", [{}, {"file_path": ""}, {"file_path": 5}, {"file_path": _FP, "language": 3}]
)
def test_accept_rejects_bad_input(standalone, body):
    resp = standalone.post("/api/v1/library/subtitle-quality/accept", json=body)
    assert resp.status_code == 400


def test_upgrade_scan_leaves_accepted_subtitles_alone(standalone):
    from upgrade_scheduler import _execute_scan

    _seed(standalone.application, age_days=30)
    standalone.post("/api/v1/library/subtitle-quality/accept", json={"file_path": _FP})
    with standalone.application.app_context(), patch("config.get_settings", return_value=_S()):
        assert _execute_scan()["queued"] == 0


def test_upgrade_scan_still_queues_unaccepted_subtitles(standalone):
    """Positive control for the test above."""
    from upgrade_scheduler import _execute_scan

    _seed(standalone.application, age_days=30)
    with standalone.application.app_context(), patch("config.get_settings", return_value=_S()):
        assert _execute_scan()["queued"] == 1


def test_accepted_items_leave_the_low_score_counts(standalone):
    from db.models.core import WantedItem
    from db.repositories.jobs import JobRepository
    from db.repositories.wanted import WantedRepository
    from extensions import db

    _seed(standalone.application, status="wanted")
    app = standalone.application
    with app.app_context():
        db.session.query(WantedItem).update({"upgrade_candidate": 1})
        db.session.commit()
        assert JobRepository().get_stats_summary()["low_score_count"] == 1
        assert WantedRepository().get_upgradeable_count() == 1

    standalone.post("/api/v1/library/subtitle-quality/accept", json={"file_path": _FP})

    with app.app_context():
        assert JobRepository().get_stats_summary()["low_score_count"] == 0
        assert WantedRepository().get_upgradeable_count() == 0
        assert WantedRepository().get_wanted_summary()["upgradeable"] == 0
