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
