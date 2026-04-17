"""Tests for PATCH /api/v1/series/<id>/settings (Phase 4a)."""

from __future__ import annotations


def test_patch_creates_settings_row_if_missing(client):
    resp = client.patch(
        "/api/v1/series/101/settings",
        json={"priority_override": "premium", "min_attempts_per_day": 3},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["sonarr_series_id"] == 101
    assert body["priority_override"] == "premium"
    assert body["min_attempts_per_day"] == 3


def test_patch_updates_existing_row(client):
    client.patch(
        "/api/v1/series/101/settings",
        json={"priority_override": "premium"},
    )
    resp = client.patch(
        "/api/v1/series/101/settings",
        json={"priority_override": "backlog", "min_attempts_per_day": 7},
    )
    body = resp.get_json()
    assert body["priority_override"] == "backlog"
    assert body["min_attempts_per_day"] == 7


def test_patch_clear_override_with_null(client):
    client.patch(
        "/api/v1/series/101/settings",
        json={"priority_override": "premium"},
    )
    resp = client.patch(
        "/api/v1/series/101/settings",
        json={"priority_override": None},
    )
    assert resp.status_code == 200
    assert resp.get_json()["priority_override"] is None


def test_patch_invalid_priority_rejected(client):
    resp = client.patch(
        "/api/v1/series/101/settings",
        json={"priority_override": "bogus"},
    )
    assert resp.status_code == 400


def test_patch_min_attempts_negative_rejected(client):
    resp = client.patch(
        "/api/v1/series/101/settings",
        json={"min_attempts_per_day": -5},
    )
    assert resp.status_code == 400


def test_patch_min_attempts_above_max_rejected(client):
    resp = client.patch(
        "/api/v1/series/101/settings",
        json={"min_attempts_per_day": 51},
    )
    assert resp.status_code == 400


def test_patch_empty_body_is_noop_returns_current_state(client):
    resp = client.patch("/api/v1/series/101/settings", json={})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["priority_override"] is None
    assert body["min_attempts_per_day"] == 0
