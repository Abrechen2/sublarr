"""Tests for the usage-stats consent API (GET/POST /api/v1/usage-stats/consent)."""


def test_get_consent_defaults_unset(client):
    resp = client.get("/api/v1/usage-stats/consent")
    assert resp.status_code == 200
    assert resp.get_json()["consent"] == "unset"


def test_post_consent_sets_value(client):
    resp = client.post("/api/v1/usage-stats/consent", json={"consent": "denied"})
    assert resp.status_code == 200
    assert resp.get_json()["consent"] == "denied"
    assert client.get("/api/v1/usage-stats/consent").get_json()["consent"] == "denied"


def test_post_consent_rejects_invalid(client):
    resp = client.post("/api/v1/usage-stats/consent", json={"consent": "maybe"})
    assert resp.status_code == 400


def test_post_granted_fires_immediate_ping_in_app_context(client):
    """Granting consent must fire the immediate ping via a callable that pushes
    its own app context (submit_background's worker has none) — passing the bare
    tick silently failed with 'working outside of application context'."""
    from unittest.mock import patch

    # Run the submitted callable synchronously so the app-context wrapper is
    # actually exercised; the tick itself is mocked (no real network).
    with (
        patch("routes.system.usage_stats.submit_background", lambda fn, *a, **k: fn()),
        patch("routes.system.usage_stats.usage_stats_tick") as mock_tick,
    ):
        resp = client.post("/api/v1/usage-stats/consent", json={"consent": "granted"})

    assert resp.status_code == 200
    mock_tick.assert_called_once()
