"""Tests for batch processing routes and _batch_process_library filter."""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@pytest.fixture(autouse=True)
def reset_batch_running():
    """Reset the module-level _batch_running flag before each test.

    The flag is set to True in the background thread and cleared when done,
    but if a previous test left it True the next POST returns 409 instead of 202.
    """
    import routes.subtitle_processor as _mod

    _mod._batch_running = False
    yield
    _mod._batch_running = False


def test_batch_process_series_returns_202(client, temp_db):
    """POST /library/series/{id}/process returns 202 immediately."""
    resp = client.post("/api/v1/library/series/1/process")
    assert resp.status_code == 202
    assert resp.get_json()["status"] == "started"


def test_batch_process_all_returns_202(client, temp_db):
    """POST /library/process-all returns 202 immediately."""
    resp = client.post("/api/v1/library/process-all", json={"filter": "all"})
    assert resp.status_code == 202
    assert resp.get_json()["status"] == "started"


def test_batch_process_all_invalid_filter_returns_400(client, temp_db):
    """POST /library/process-all with unknown filter returns 400."""
    resp = client.post("/api/v1/library/process-all", json={"filter": "bad_filter"})
    assert resp.status_code == 400


def test_batch_process_conflict_returns_409(client, temp_db):
    """Second POST while batch is running returns 409."""
    import routes.subtitle_processor as _mod

    _mod._batch_running = True
    resp = client.post("/api/v1/library/process-all", json={"filter": "all"})
    assert resp.status_code == 409


def test_batch_process_unprocessed_filter(app_ctx, temp_db):
    """_batch_process_library with filter='unprocessed' skips series that already have processing_config set."""
    from routes.subtitle_processor import _batch_process_library

    mock_client = MagicMock()
    mock_client.get_series.return_value = [
        {"id": 101, "title": "SeriesA"},
        {"id": 102, "title": "SeriesB"},
    ]

    # Give series 102 a processing_config — it should be skipped
    from db.models.core import SeriesSettings
    from extensions import db as _db

    row = SeriesSettings(
        sonarr_series_id=102,
        processing_config=json.dumps({"hi_removal": True}),
        updated_at=_now(),
    )
    _db.session.add(row)
    _db.session.commit()

    processed_ids = []

    def mock_process(series_id):
        processed_ids.append(series_id)

    with (
        patch("sonarr_client.get_sonarr_client", return_value=mock_client),
        patch("routes.subtitle_processor._batch_process_series", side_effect=mock_process),
    ):
        _batch_process_library("unprocessed")

    assert 101 in processed_ids
    assert 102 not in processed_ids


def test_batch_process_all_filter_includes_all_series(app_ctx, temp_db):
    """_batch_process_library with filter='all' processes all series regardless of config."""
    from routes.subtitle_processor import _batch_process_library

    mock_client = MagicMock()
    mock_client.get_series.return_value = [
        {"id": 201, "title": "SeriesC"},
        {"id": 202, "title": "SeriesD"},
    ]

    # Give series 202 a processing_config — should still be processed with filter='all'
    from db.models.core import SeriesSettings
    from extensions import db as _db

    row = SeriesSettings(
        sonarr_series_id=202,
        processing_config=json.dumps({"hi_removal": False}),
        updated_at=_now(),
    )
    _db.session.add(row)
    _db.session.commit()

    processed_ids = []

    def mock_process(series_id):
        processed_ids.append(series_id)

    with (
        patch("sonarr_client.get_sonarr_client", return_value=mock_client),
        patch("routes.subtitle_processor._batch_process_series", side_effect=mock_process),
    ):
        _batch_process_library("all")

    assert 201 in processed_ids
    assert 202 in processed_ids


def test_batch_process_library_skips_series_without_id(app_ctx, temp_db):
    """_batch_process_library skips series entries that have no 'id' key."""
    from routes.subtitle_processor import _batch_process_library

    mock_client = MagicMock()
    mock_client.get_series.return_value = [
        {"title": "NoId"},  # missing 'id' key
        {"id": 301, "title": "HasId"},
    ]

    processed_ids = []

    def mock_process(series_id):
        processed_ids.append(series_id)

    with (
        patch("sonarr_client.get_sonarr_client", return_value=mock_client),
        patch("routes.subtitle_processor._batch_process_series", side_effect=mock_process),
    ):
        _batch_process_library("all")

    assert 301 in processed_ids
    assert len(processed_ids) == 1


def test_batch_process_library_returns_early_when_no_sonarr_client(app_ctx, temp_db):
    """_batch_process_library exits gracefully when Sonarr client is unavailable."""
    from routes.subtitle_processor import _batch_process_library

    processed_ids = []

    def mock_process(series_id):
        processed_ids.append(series_id)

    with (
        patch("sonarr_client.get_sonarr_client", return_value=None),
        patch("routes.subtitle_processor._batch_process_series", side_effect=mock_process),
    ):
        _batch_process_library("all")

    assert processed_ids == []


def test_batch_process_library_handles_sonarr_exception(app_ctx, temp_db):
    """_batch_process_library handles Sonarr get_series() exceptions without crashing."""
    from routes.subtitle_processor import _batch_process_library

    mock_client = MagicMock()
    mock_client.get_series.side_effect = ConnectionError("Sonarr unreachable")

    processed_ids = []

    def mock_process(series_id):
        processed_ids.append(series_id)

    with (
        patch("sonarr_client.get_sonarr_client", return_value=mock_client),
        patch("routes.subtitle_processor._batch_process_series", side_effect=mock_process),
    ):
        _batch_process_library("all")  # must not raise

    assert processed_ids == []
