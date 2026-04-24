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


# ---------------------------------------------------------------------------
# 0.71.1 follow-up #1 — cleanup_foreign_tracks three-state override
# ---------------------------------------------------------------------------


def test_patch_cleanup_foreign_tracks_set_true(client):
    resp = client.patch(
        "/api/v1/series/202/settings",
        json={"cleanup_foreign_tracks": True},
    )
    assert resp.status_code == 200
    assert resp.get_json()["cleanup_foreign_tracks"] is True


def test_patch_cleanup_foreign_tracks_set_false(client):
    resp = client.patch(
        "/api/v1/series/203/settings",
        json={"cleanup_foreign_tracks": False},
    )
    assert resp.status_code == 200
    assert resp.get_json()["cleanup_foreign_tracks"] is False


def test_patch_cleanup_foreign_tracks_clear_with_null(client):
    client.patch("/api/v1/series/204/settings", json={"cleanup_foreign_tracks": True})
    resp = client.patch("/api/v1/series/204/settings", json={"cleanup_foreign_tracks": None})
    assert resp.status_code == 200
    assert resp.get_json()["cleanup_foreign_tracks"] is None


def test_patch_cleanup_foreign_tracks_invalid_type_rejected(client):
    resp = client.patch(
        "/api/v1/series/205/settings",
        json={"cleanup_foreign_tracks": "yes"},
    )
    assert resp.status_code == 400


def test_patch_cleanup_and_priority_together(client):
    resp = client.patch(
        "/api/v1/series/206/settings",
        json={"priority_override": "premium", "cleanup_foreign_tracks": True},
    )
    body = resp.get_json()
    assert resp.status_code == 200
    assert body["priority_override"] == "premium"
    assert body["cleanup_foreign_tracks"] is True


def test_patch_response_always_includes_cleanup_field(client):
    """Even on empty PATCH, the response must include cleanup_foreign_tracks (null default)."""
    resp = client.patch("/api/v1/series/207/settings", json={})
    body = resp.get_json()
    assert resp.status_code == 200
    assert "cleanup_foreign_tracks" in body
    assert body["cleanup_foreign_tracks"] is None
