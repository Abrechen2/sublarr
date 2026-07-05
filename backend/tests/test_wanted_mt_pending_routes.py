"""HTTP tests for the pending-original approve/reject API (feature #8b Phase 2
Task 3) — routes/wanted/mt_pending.py.

Covers:
- ``GET /api/v1/wanted/mt-pending`` — lists only items with
  ``mt_pending_original`` set, JSON payload parsed into the response.
- ``POST /api/v1/wanted/<id>/mt-pending/approve`` — installs the stored
  original (reusing ``services.mt_reseek._replace_original``) and clears the
  pending marker. A mocked-``_replace_original`` test covers the route wiring;
  a real end-to-end test (mirrors ``TestAutoReplaceIntegration`` in
  ``test_mt_reseek.py``) covers the underlying action actually firing.
- ``POST /api/v1/wanted/<id>/mt-pending/reject`` — clears the pending marker
  AND pins the item (``mt_pinned=1``) so ``mt_reseek`` never re-notifies for
  the same MT.
- 404 for an unknown item id on both actions; 400 for an item that exists but
  has no pending original (see routes/wanted/mt_pending.py module docstring
  for the 404-vs-400 rationale).
"""

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from db.models.core import WantedItem
from extensions import db


def _make_wanted_item(**kwargs) -> WantedItem:
    """Insert a minimal WantedItem; returns the persisted row."""
    now = datetime(2026, 7, 5, tzinfo=UTC)
    defaults = dict(
        item_type="episode",
        file_path=f"/media/mtpending_{id(kwargs):x}.mkv",
        title="Test",
        season_episode="S01E01",
        existing_sub="",
        missing_languages="[]",
        embedded_languages="[]",
        target_language="de",
        subtitle_type="full",
        status="wanted",
        added_at=now,
        updated_at=now,
    )
    defaults.update(kwargs)
    item = WantedItem(**defaults)
    db.session.add(item)
    db.session.commit()
    return item


def _pending_payload(**overrides) -> str:
    base = {
        "provider": "acme",
        "score": 42,
        "output_path": "/media/ep.de.ass",
        "format": "ass",
        "found_at": "2026-07-05T00:00:00+00:00",
    }
    base.update(overrides)
    return json.dumps(base)


@pytest.fixture
def app_and_client(temp_db):
    """Provide both Flask app and test client sharing the same DB."""
    from app import create_app

    app = create_app(testing=True)
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    with app.test_client() as client:
        yield app, client


# ---------------------------------------------------------------------------
# GET /api/v1/wanted/mt-pending
# ---------------------------------------------------------------------------


def test_list_mt_pending_returns_only_items_with_pending(app_and_client):
    app, client = app_and_client
    with app.app_context():
        pending = _make_wanted_item(
            file_path="/media/pending.mkv",
            status="provisional",
            mt_pending_original=_pending_payload(provider="acme", score=55),
        )
        _make_wanted_item(file_path="/media/no_pending.mkv", status="provisional")
        _make_wanted_item(file_path="/media/wanted.mkv", status="wanted")
        pending_id = pending.id

    resp = client.get("/api/v1/wanted/mt-pending")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total"] == 1
    assert len(data["data"]) == 1

    row = data["data"][0]
    assert row["id"] == pending_id
    # The JSON payload is parsed into structured fields, not left as a string.
    assert isinstance(row["mt_pending_original"], dict)
    assert row["mt_pending_original"]["provider"] == "acme"
    assert row["mt_pending_original"]["score"] == 55
    assert row["mt_pending_original"]["output_path"] == "/media/ep.de.ass"
    assert row["mt_pending_original"]["format"] == "ass"
    assert "found_at" in row["mt_pending_original"]


def test_list_mt_pending_empty(client):
    resp = client.get("/api/v1/wanted/mt-pending")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total"] == 0
    assert data["data"] == []


# ---------------------------------------------------------------------------
# POST /api/v1/wanted/<id>/mt-pending/approve
# ---------------------------------------------------------------------------


def test_approve_calls_replace_original_and_clears_pending(app_and_client, monkeypatch):
    app, client = app_and_client
    with app.app_context():
        item = _make_wanted_item(
            status="provisional",
            mt_pending_original=_pending_payload(
                provider="acme", score=42, output_path="/media/ep.de.ass"
            ),
        )
        item_id = item.id

    calls = []
    monkeypatch.setattr(
        "services.mt_reseek._replace_original",
        lambda itm, payload: calls.append((itm, payload)),
    )

    resp = client.post(f"/api/v1/wanted/{item_id}/mt-pending/approve")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "approved"

    assert len(calls) == 1
    called_item, called_payload = calls[0]
    assert called_item["id"] == item_id
    assert called_payload["provider"] == "acme"
    assert called_payload["score"] == 42
    assert called_payload["output_path"] == "/media/ep.de.ass"

    with app.app_context():
        from db.wanted import get_wanted_item

        refreshed = get_wanted_item(item_id)
        assert refreshed["mt_pending_original"] is None


def test_approve_404_unknown_item(client):
    resp = client.post("/api/v1/wanted/999999/mt-pending/approve")
    assert resp.status_code == 404
    assert "error" in resp.get_json()


def test_approve_400_when_no_pending_original(app_and_client):
    app, client = app_and_client
    with app.app_context():
        item = _make_wanted_item(status="provisional")
        item_id = item.id

    resp = client.post(f"/api/v1/wanted/{item_id}/mt-pending/approve")
    assert resp.status_code == 400
    assert "error" in resp.get_json()


class TestApproveIntegration:
    """Real WantedItem + real MT sidecar on disk + real subtitle_downloads MT
    row, exercised through the HTTP route (not the reseek job) — the pending
    marker is set directly, mirroring what a prior notify-mode re-seek pass
    would have recorded. Only the provider-manager boundary is mocked,
    matching ``TestAutoReplaceIntegration`` in ``test_mt_reseek.py``."""

    def test_approve_installs_original_and_trashes_mt(self, app_and_client, monkeypatch, tmp_path):
        app, client = app_and_client
        with app.app_context():
            from config import get_settings
            from db.models.core import LanguageProfile, SeriesLanguageProfile
            from db.providers import record_subtitle_download
            from db.repositories.profiles import ProfileRepository
            from db.wanted import set_mt_pending_original

            mkv = tmp_path / "ep.mkv"
            mkv.touch()
            mt_path = tmp_path / "ep.de.ass"
            mt_path.write_bytes(b"MT-CONTENT")

            item = _make_wanted_item(file_path=str(mkv), status="provisional", sonarr_series_id=42)
            item_id = item.id
            record_subtitle_download(
                "translation",
                "mt:ep.de.ass",
                "de",
                "ass",
                str(mt_path),
                0,
                source="machine_translation",
                record_stats=False,
            )

            profile_id = ProfileRepository().create_profile(
                name="approve-integration-profile",
                source_lang="en",
                source_name="English",
                target_langs=["de"],
                target_names=["German"],
            )
            profile = db.session.get(LanguageProfile, profile_id)
            profile.mt_keep_seeking_original = 1
            profile.mt_on_original_found = "notify"
            profile.mt_min_original_score = 1
            db.session.add(SeriesLanguageProfile(sonarr_series_id=42, profile_id=profile_id))
            db.session.commit()

            set_mt_pending_original(
                item_id,
                _pending_payload(provider="acme", score=80, output_path=str(mt_path)),
            )

            monkeypatch.setattr(get_settings(), "media_path", str(tmp_path))

        real_result = MagicMock()
        real_result.provider_name = "realprovider"
        real_result.subtitle_id = "real123"
        real_result.language = "de"
        real_result.format.value = "ass"
        real_result.score = 80
        real_result.content = b"REAL-ORIGINAL-CONTENT"

        mock_mgr = MagicMock()
        mock_mgr.search.return_value = []
        mock_mgr.search_and_download_best.return_value = real_result

        def _fake_save(result, output_path, series_id=None):
            with open(output_path, "wb") as fh:
                fh.write(result.content)
            return output_path

        mock_mgr.save_subtitle.side_effect = _fake_save

        monkeypatch.setattr("wanted_search.process.get_provider_manager", lambda: mock_mgr)
        monkeypatch.setattr("nfo_export.maybe_write_nfo", lambda *a, **kw: None)
        monkeypatch.setattr("wanted_search.process._try_auto_sync", lambda *a, **kw: None)

        resp = client.post(f"/api/v1/wanted/{item_id}/mt-pending/approve")
        assert resp.status_code == 200

        assert mt_path.read_bytes() == b"REAL-ORIGINAL-CONTENT"
        trash_root = tmp_path / ".sublarr_trash"
        assert trash_root.is_dir()
        trashed_files = list(trash_root.rglob("ep.de.ass"))
        assert len(trashed_files) == 1
        assert trashed_files[0].read_bytes() == b"MT-CONTENT"

        with app.app_context():
            from db.wanted import get_wanted_item

            assert get_wanted_item(item_id) is None


# ---------------------------------------------------------------------------
# POST /api/v1/wanted/<id>/mt-pending/reject
# ---------------------------------------------------------------------------


def test_reject_clears_pending_and_pins_item(app_and_client):
    app, client = app_and_client
    with app.app_context():
        item = _make_wanted_item(
            status="provisional",
            mt_pending_original=_pending_payload(),
        )
        item_id = item.id
        assert item.mt_pinned in (0, None)

    resp = client.post(f"/api/v1/wanted/{item_id}/mt-pending/reject")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "rejected"

    with app.app_context():
        from db.wanted import get_wanted_item

        refreshed = get_wanted_item(item_id)
        assert refreshed["mt_pending_original"] is None
        assert refreshed["mt_pinned"] == 1


def test_reject_404_unknown_item(client):
    resp = client.post("/api/v1/wanted/999999/mt-pending/reject")
    assert resp.status_code == 404
    assert "error" in resp.get_json()


def test_reject_400_when_no_pending_original(app_and_client):
    app, client = app_and_client
    with app.app_context():
        item = _make_wanted_item(status="provisional")
        item_id = item.id

    resp = client.post(f"/api/v1/wanted/{item_id}/mt-pending/reject")
    assert resp.status_code == 400
    assert "error" in resp.get_json()
