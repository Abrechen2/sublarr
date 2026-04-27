"""Status API tests for subtitle-automation (Phase 7 backend).

GET /api/v1/wanted/automation/status   → shape test
POST /api/v1/wanted/automation/run-now → triggers a drain and returns state
"""

import pytest


@pytest.fixture
def api(client):
    return client


class TestStatusEndpoint:
    def test_shape_with_empty_queue(self, api):
        r = api.get("/api/v1/wanted/automation/status")
        assert r.status_code == 200
        payload = r.get_json()
        assert set(payload.keys()) >= {
            "enabled",
            "queue_size",
            "queue",
            "last_run_at",
            "last_run_status",
            "last_error",
        }
        assert payload["queue"] == {
            "pending": 0,
            "running": 0,
            "failed": 0,
            "done": 0,
        }
        assert payload["queue_size"] == 0

    def test_reflects_pending_rows(self, api):
        """Enqueue via the same Flask test-client app context, then GET."""
        from db.repositories.subtitle_automation_queue import (
            SubtitleAutomationQueueRepository,
        )

        with api.application.app_context():
            repo = SubtitleAutomationQueueRepository()
            repo.enqueue(wanted_item_id=2001, file_path="/m/a.mkv", target_language="ger")
            repo.enqueue(wanted_item_id=2002, file_path="/m/b.mkv", target_language="ger")
        r = api.get("/api/v1/wanted/automation/status")
        payload = r.get_json()
        assert payload["queue"]["pending"] == 2
        assert payload["queue_size"] == 2

    def test_enabled_flag_follows_settings(self, api):
        r = api.get("/api/v1/wanted/automation/status")
        payload = r.get_json()
        # Default master toggle is False (opt-in).
        assert payload["enabled"] is False


class TestRunNowEndpoint:
    def test_returns_202_with_status_field(self, api):
        r = api.post("/api/v1/wanted/automation/run-now")
        assert r.status_code in (200, 202)
        payload = r.get_json()
        assert "status" in payload
        assert payload["status"] in ("queued", "running", "disabled")

    def test_disabled_when_master_toggle_off(self, api):
        """When master toggle is off, run-now is a visible no-op, not a 500."""
        r = api.post("/api/v1/wanted/automation/run-now")
        payload = r.get_json()
        assert payload["status"] == "disabled"
