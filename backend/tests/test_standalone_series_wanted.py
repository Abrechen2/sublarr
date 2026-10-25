"""Series-scoped wanted queries in standalone mode.

Without Sonarr a ``series_id`` is a standalone series id, but the series
batch search ("Search all missing", Library multi-select) and the series
filter of the wanted list matched ``sonarr_series_id`` only — standalone rows
have it NULL, so the search answered "no_items" and the series page's
skip/accept buttons had nothing to act on.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest


def _add(client, *, file_path, standalone_series_id=None, sonarr_series_id=None, status="wanted"):
    from db.models.core import WantedItem
    from extensions import db

    now = datetime.now(UTC)
    with client.application.app_context():
        wi = WantedItem(
            item_type="episode",
            title=file_path,
            file_path=file_path,
            target_language="de",
            standalone_series_id=standalone_series_id,
            sonarr_series_id=sonarr_series_id,
            status=status,
            added_at=now,
            updated_at=now,
        )
        db.session.add(wi)
        db.session.commit()
        return wi.id


@pytest.fixture
def no_sonarr(monkeypatch):
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: None)


@pytest.fixture
def fake_sonarr(monkeypatch):
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: object())


@pytest.fixture(autouse=True)
def _reset_batch_state():
    yield
    from routes.batch_state import wanted_batch_lock, wanted_batch_state

    with wanted_batch_lock:
        wanted_batch_state["running"] = False


def _batch(client, body):
    with (
        patch("wanted_search.process_wanted_batch", return_value=iter(())),
        patch("routes.wanted.search.submit_background"),
    ):
        return client.post("/api/v1/wanted/batch-search", json=body)


def test_series_batch_search_standalone(client, no_sonarr):
    _add(client, file_path="/m/a/e1.mkv", standalone_series_id=3)
    _add(client, file_path="/m/a/e2.mkv", standalone_series_id=3, status="ignored")
    _add(client, file_path="/m/b/e1.mkv", standalone_series_id=4)
    resp = _batch(client, {"series_id": 3})
    assert resp.status_code == 202, resp.get_json()
    # Only the searchable (wanted/failed) row of series 3.
    assert resp.get_json()["total_items"] == 1


def test_multi_series_batch_search_standalone(client, no_sonarr):
    _add(client, file_path="/m/a/e1.mkv", standalone_series_id=3)
    _add(client, file_path="/m/b/e1.mkv", standalone_series_id=4)
    _add(client, file_path="/m/c/e1.mkv", standalone_series_id=5)
    resp = _batch(client, {"series_ids": [3, 4]})
    assert resp.status_code == 202, resp.get_json()
    assert resp.get_json()["total_items"] == 2


def test_series_batch_search_sonarr_mode_unchanged(client, fake_sonarr):
    _add(client, file_path="/m/s/e1.mkv", sonarr_series_id=3)
    _add(client, file_path="/m/a/e1.mkv", standalone_series_id=3)
    resp = _batch(client, {"series_id": 3})
    assert resp.status_code == 202
    assert resp.get_json()["total_items"] == 1


def test_wanted_list_series_filter_standalone(client, no_sonarr):
    a = _add(client, file_path="/m/a/e1.mkv", standalone_series_id=3)
    _add(client, file_path="/m/b/e1.mkv", standalone_series_id=4)
    resp = client.get("/api/v1/wanted", query_string={"series_id": 3})
    assert resp.status_code == 200
    assert [i["id"] for i in resp.get_json()["data"]] == [a]


def test_wanted_list_series_filter_sonarr_mode_unchanged(client, fake_sonarr):
    s = _add(client, file_path="/m/s/e1.mkv", sonarr_series_id=3)
    _add(client, file_path="/m/a/e1.mkv", standalone_series_id=3)
    resp = client.get("/api/v1/wanted", query_string={"series_id": 3})
    assert resp.status_code == 200
    assert [i["id"] for i in resp.get_json()["data"]] == [s]
