"""Tests for /api/v1/system/setup/{status,complete,reset}."""

from __future__ import annotations

from unittest.mock import patch


def test_status_returns_defaults_on_fresh_install(client):
    resp = client.get("/api/v1/system/setup/status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["wizard_completed"] is False
    assert data["benchmark"]["cpu_count"] >= 1
    assert data["benchmark"]["ram_gb"] > 0
    assert data["benchmark"]["recommended_profile"] in ("light", "balanced", "aggressive")


def test_status_respects_completed_flag(client):
    # Route handlers have an app context; use one call each to set/reset.
    client.post("/api/v1/system/setup/complete", json={"profile": "balanced"})
    try:
        resp = client.get("/api/v1/system/setup/status")
        assert resp.get_json()["wizard_completed"] is True
    finally:
        client.post("/api/v1/system/setup/reset")


def test_complete_applies_profile_and_sets_flag(client):
    resp = client.post("/api/v1/system/setup/complete", json={"profile": "light"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["profile"] == "light"
    assert data["applied"]["wanted_search_max_items_per_run"] == 100

    # Confirm the flag persisted
    status = client.get("/api/v1/system/setup/status").get_json()
    assert status["wizard_completed"] is True


def test_complete_rejects_unknown_profile(client):
    resp = client.post("/api/v1/system/setup/complete", json={"profile": "turbo"})
    assert resp.status_code == 400
    assert "unknown scheduler profile" in resp.get_json()["error"]


def test_complete_custom_profile_applies_no_settings(client):
    resp = client.post("/api/v1/system/setup/complete", json={"profile": "custom"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["profile"] == "custom"
    assert data["applied"] == {}  # custom is a no-op on settings


def test_reset_clears_completed_flag(client):
    # Arrange: complete
    client.post("/api/v1/system/setup/complete", json={"profile": "balanced"})
    assert client.get("/api/v1/system/setup/status").get_json()["wizard_completed"] is True

    # Act: reset
    resp = client.post("/api/v1/system/setup/reset")
    assert resp.status_code == 200
    assert resp.get_json() == {"ok": True}

    # Assert: flag is false again
    assert client.get("/api/v1/system/setup/status").get_json()["wizard_completed"] is False


def test_hardware_detection_recommends_light_on_low_specs(client):
    with (
        patch("routes.system.setup._detect_cpu_count", return_value=2),
        patch("routes.system.setup._detect_ram_gb", return_value=2.0),
    ):
        data = client.get("/api/v1/system/setup/status").get_json()
    assert data["benchmark"]["recommended_profile"] == "light"
    assert data["benchmark"]["cpu_count"] == 2


def test_hardware_detection_recommends_aggressive_on_high_specs(client):
    with (
        patch("routes.system.setup._detect_cpu_count", return_value=16),
        patch("routes.system.setup._detect_ram_gb", return_value=32.0),
    ):
        data = client.get("/api/v1/system/setup/status").get_json()
    assert data["benchmark"]["recommended_profile"] == "aggressive"
