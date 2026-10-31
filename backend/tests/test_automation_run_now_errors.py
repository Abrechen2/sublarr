"""A failed manual drain is reported as a failure (#61 A28: it said "queued")."""

from unittest.mock import patch


def test_a_drain_that_raises_answers_with_an_error(client):
    with (
        patch("routes.wanted.automation._is_master_toggle_on", return_value=True),
        patch(
            "services.subtitle_automation_runner.SubtitleAutomationRunner.drain",
            side_effect=RuntimeError("database is locked"),
        ),
    ):
        response = client.post("/api/v1/wanted/automation/run-now")

    assert response.status_code == 500
    assert "database is locked" in response.get_json()["error"]


def test_a_drain_that_runs_still_reports_its_count(client):
    with (
        patch("routes.wanted.automation._is_master_toggle_on", return_value=True),
        patch("services.subtitle_automation_runner.SubtitleAutomationRunner.drain", return_value=3),
    ):
        response = client.post("/api/v1/wanted/automation/run-now")

    assert response.status_code == 200
    assert response.get_json() == {"status": "queued", "processed": 3}
