"""Tests for /api/v1/providers/<name>/keys (Phase 4a)."""

from __future__ import annotations

from unittest.mock import patch


def test_list_keys_empty(client):
    resp = client.get("/api/v1/providers/opensubtitles/keys")
    assert resp.status_code == 200
    assert resp.get_json() == {"keys": []}


def test_add_key_and_list(client):
    payload = {"label": "primary", "api_key": "k", "tier": "vip"}
    resp = client.post("/api/v1/providers/opensubtitles/keys", json=payload)
    assert resp.status_code == 201
    created = resp.get_json()
    assert created["label"] == "primary"
    assert created["tier"] == "vip"
    assert "id" in created

    resp = client.get("/api/v1/providers/opensubtitles/keys")
    assert len(resp.get_json()["keys"]) == 1


def test_add_missing_fields_400(client):
    resp = client.post("/api/v1/providers/opensubtitles/keys", json={"label": "p"})
    assert resp.status_code == 400


def test_add_duplicate_label_conflict(client):
    client.post(
        "/api/v1/providers/opensubtitles/keys",
        json={"label": "primary", "api_key": "k", "tier": "free"},
    )
    resp = client.post(
        "/api/v1/providers/opensubtitles/keys",
        json={"label": "primary", "api_key": "k2", "tier": "free"},
    )
    assert resp.status_code == 409


def test_patch_key_updates_fields(client):
    r = client.post(
        "/api/v1/providers/opensubtitles/keys",
        json={"label": "primary", "api_key": "k", "tier": "free"},
    )
    kid = r.get_json()["id"]
    resp = client.patch(
        f"/api/v1/providers/opensubtitles/keys/{kid}",
        json={"tier": "vip", "enabled": False},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["tier"] == "vip"
    assert body["enabled"] is False


def test_patch_unknown_id_returns_404(client):
    resp = client.patch(
        "/api/v1/providers/opensubtitles/keys/99999",
        json={"tier": "vip"},
    )
    assert resp.status_code == 404


def test_delete_key(client):
    r = client.post(
        "/api/v1/providers/opensubtitles/keys",
        json={"label": "primary", "api_key": "k", "tier": "free"},
    )
    kid = r.get_json()["id"]
    resp = client.delete(f"/api/v1/providers/opensubtitles/keys/{kid}")
    assert resp.status_code == 204
    resp = client.get("/api/v1/providers/opensubtitles/keys")
    assert resp.get_json()["keys"] == []


def test_test_connection_ok(client):
    with patch(
        "routes.providers_keys._probe_provider",
        return_value={"ok": True, "message": "Test OK"},
    ):
        resp = client.post(
            "/api/v1/providers/opensubtitles/keys/test-connection",
            json={"api_key": "k"},
        )
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True


def test_test_connection_failure_returns_400(client):
    with patch(
        "routes.providers_keys._probe_provider",
        return_value={"ok": False, "message": "HTTP 401"},
    ):
        resp = client.post(
            "/api/v1/providers/opensubtitles/keys/test-connection",
            json={"api_key": "bad"},
        )
    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False
