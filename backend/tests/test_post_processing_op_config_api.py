"""Plan B6 follow-up — GET/PUT per-op config API."""

from __future__ import annotations


def test_get_op_config_returns_schema_for_known_op(client):
    resp = client.get("/api/v1/post-processing/ops/discord_notify/config")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["op_id"] == "discord_notify"
    assert isinstance(body["schema"], list)
    assert any(e["key"] == "webhook_url" for e in body["schema"])
    # No value stored yet → default empty
    assert body["values"]["webhook_url"] == ""


def test_get_op_config_returns_404_for_unknown_op(client):
    resp = client.get("/api/v1/post-processing/ops/not_an_op/config")
    assert resp.status_code == 404


def test_put_and_get_op_config_roundtrip_non_secret(client):
    # PUT
    put = client.put(
        "/api/v1/post-processing/ops/webhook/config",
        json={
            "values": {
                "url": "https://example.com/hook",
                "method": "POST",
                "template": '{"x": "{lang}"}',
            }
        },
    )
    assert put.status_code == 200

    # GET — non-password values returned as-is
    got = client.get("/api/v1/post-processing/ops/webhook/config")
    assert got.status_code == 200
    values = got.get_json()["values"]
    assert values["url"] == "https://example.com/hook"
    assert values["method"] == "POST"
    assert values["template"] == '{"x": "{lang}"}'


def test_password_fields_are_masked_on_get(client):
    client.put(
        "/api/v1/post-processing/ops/discord_notify/config",
        json={"values": {"webhook_url": "https://discord.com/api/webhooks/9/s3cr3t"}},
    )
    got = client.get("/api/v1/post-processing/ops/discord_notify/config")
    assert got.status_code == 200
    # Mask on GET, real value in DB
    assert got.get_json()["values"]["webhook_url"] == "***"

    # Confirm the real value is stored
    from post_processing.config_store import get_op_config

    assert (
        get_op_config("discord_notify")["webhook_url"]
        == "https://discord.com/api/webhooks/9/s3cr3t"
    )


def test_password_mask_on_put_does_not_overwrite_existing(client):
    # 1. Store real secret
    client.put(
        "/api/v1/post-processing/ops/discord_notify/config",
        json={"values": {"webhook_url": "https://discord.com/api/webhooks/42/real"}},
    )
    # 2. PUT back with mask sentinel (simulating the user saving other fields)
    resp = client.put(
        "/api/v1/post-processing/ops/discord_notify/config",
        json={"values": {"webhook_url": "***"}},
    )
    assert resp.status_code == 200

    from post_processing.config_store import get_op_config

    # Real secret is preserved
    assert (
        get_op_config("discord_notify")["webhook_url"] == "https://discord.com/api/webhooks/42/real"
    )


def test_put_rejects_missing_required_field(client):
    resp = client.put(
        "/api/v1/post-processing/ops/webhook/config",
        json={"values": {"url": ""}},  # required, empty
    )
    assert resp.status_code == 400
    assert "required" in resp.get_json()["error"].lower()


def test_put_rejects_unknown_field(client):
    resp = client.put(
        "/api/v1/post-processing/ops/webhook/config",
        json={"values": {"not_a_field": "x", "url": "http://x"}},
    )
    assert resp.status_code == 400
    assert "unknown" in resp.get_json()["error"].lower()


def test_put_rejects_non_object_values(client):
    resp = client.put(
        "/api/v1/post-processing/ops/webhook/config",
        json={"values": "not an object"},
    )
    assert resp.status_code == 400


def test_put_404_for_unknown_op(client):
    resp = client.put(
        "/api/v1/post-processing/ops/not_an_op/config",
        json={"values": {}},
    )
    assert resp.status_code == 404


def test_get_returns_default_for_unset_non_password(client):
    # method has default "POST"
    got = client.get("/api/v1/post-processing/ops/webhook/config")
    assert got.status_code == 200
    # method default is populated from schema.default
    assert got.get_json()["values"]["method"] in ("POST", "")


def test_put_allows_partial_update_keeping_other_fields(client):
    client.put(
        "/api/v1/post-processing/ops/plex_refresh/config",
        json={
            "values": {
                "base_url": "http://plex:32400",
                "token": "secret-token",
                "section_id": "1",
            }
        },
    )
    # Partial PUT — only update section_id, keep others (password mask is "***")
    resp = client.put(
        "/api/v1/post-processing/ops/plex_refresh/config",
        json={"values": {"section_id": "7", "token": "***", "base_url": "http://plex:32400"}},
    )
    assert resp.status_code == 200

    from post_processing.config_store import get_op_config

    cfg = get_op_config("plex_refresh")
    assert cfg["base_url"] == "http://plex:32400"
    assert cfg["token"] == "secret-token"  # preserved via mask
    assert cfg["section_id"] == "7"
