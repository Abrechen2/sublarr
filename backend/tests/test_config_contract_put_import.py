"""PUT /config and the config import follow one set of rules — against the real app.

Audit #61, reproduced on the audit commit and fixed here:
A03 boot fields were accepted and then ignored; A05 a fresh export could not
be imported (its own loopback Ollama default); A06 a refused key left the
earlier keys saved; A07 the import accepted values PUT refuses; A08 hub.* keys
were missing from the export; A35 a masked media_servers_json was saved with
its masks.
"""

import json

import pytest


def _get(client):
    return client.get("/api/v1/config").get_json()


@pytest.mark.parametrize("key", ["port", "media_path", "db_path"])
def test_an_environment_setting_is_refused_with_a_reason(client, key):
    response = client.put("/api/v1/config", json={key: "4321"})

    assert response.status_code == 400
    assert "environment" in response.get_json()["error"]


def test_a_refused_key_saves_nothing(client):
    before = _get(client)["target_language"]

    for payload in (
        {"target_language": "fr", "zz_unknown": "x"},
        {"zz_unknown": "x", "target_language": "fr"},
    ):
        response = client.put("/api/v1/config", json=payload)
        assert response.status_code == 400

    with client.application.app_context():
        from db.config import get_config_entry

        assert get_config_entry("target_language") in (None, before)
    assert _get(client)["target_language"] == before


def test_every_error_is_reported_at_once(client):
    response = client.put("/api/v1/config", json={"zz_a": 1, "items_per_page": 1})

    assert {e["key"] for e in response.get_json()["errors"]} == {"zz_a", "items_per_page"}


def test_a_local_ollama_is_allowed_other_local_services_are_not(client):
    assert (
        client.put("/api/v1/config", json={"ollama_url": "http://127.0.0.1:11434"}).status_code
        == 200
    )
    assert (
        client.put("/api/v1/config", json={"sonarr_url": "http://127.0.0.1:8989"}).status_code
        == 400
    )
    assert (
        client.put("/api/v1/config", json={"ollama_url": "http://169.254.169.254/"}).status_code
        == 400
    )


def test_a_fresh_export_imports_back_unchanged(client):
    exported = client.get("/api/v1/config/export").get_json()

    response = client.post("/api/v1/config/import", json=exported)

    body = response.get_json()
    assert response.status_code == 200, body
    assert body["skipped_invalid"] == []


@pytest.mark.parametrize(
    ("key", "value"),
    [("items_per_page", 1), ("auto_sync_engine", "nope"), ("translation_quality_max_retries", 99)],
)
def test_the_import_refuses_what_put_refuses(client, key, value):
    assert client.put("/api/v1/config", json={key: value}).status_code == 400

    body = client.post("/api/v1/config/import", json={key: value}).get_json()

    assert [e["key"] for e in body["skipped_invalid"]] == [key]
    assert key not in body["imported_keys"]


def test_hub_settings_travel_with_a_backup(client):
    assert client.put("/api/v1/config", json={"hub.audit.flag": "on"}).status_code == 200

    exported = client.get("/api/v1/config/export").get_json()

    assert exported["hub.audit.flag"] == "on"
    assert "port" not in exported


def test_a_list_setting_keeps_its_type_through_put_and_reload(client):
    response = client.put(
        "/api/v1/config", json={"cleanup_foreign_tracks_keep_languages": ["de", "en"]}
    )
    assert response.status_code == 200, response.get_json()

    from config import get_settings

    assert get_settings().cleanup_foreign_tracks_keep_languages == ["de", "en"]
    with client.application.app_context():
        from db.config import get_config_entry

        assert json.loads(get_config_entry("cleanup_foreign_tracks_keep_languages")) == ["de", "en"]


def test_a_masked_media_server_blob_keeps_its_secrets(client):
    # As stored on prod: media-server entries have no id.
    servers = [
        {"type": "emby", "name": "Home", "url": "http://192.168.10.5:8096", "api_key": "real"}
    ]
    assert (
        client.put("/api/v1/config", json={"media_servers_json": json.dumps(servers)}).status_code
        == 200
    )
    masked = _get(client)["media_servers_json"]
    assert "real" not in masked

    assert client.put("/api/v1/config", json={"media_servers_json": masked}).status_code == 200

    with client.application.app_context():
        from db.config import get_config_entry

        assert json.loads(get_config_entry("media_servers_json"))[0]["api_key"] == "real"


def test_an_instance_without_an_id_never_borrows_a_secret(client):
    stored = [{"id": "a1", "url": "http://192.168.10.5:8989", "api_key": "real"}]
    client.put("/api/v1/config", json={"sonarr_instances_json": json.dumps(stored)})

    new = [{"url": "http://192.168.10.6:8989", "api_key": "***configured***"}]
    assert (
        client.put("/api/v1/config", json={"sonarr_instances_json": json.dumps(new)}).status_code
        == 200
    )

    with client.application.app_context():
        from db.config import get_config_entry

        assert "api_key" not in json.loads(get_config_entry("sonarr_instances_json"))[0]


def test_a_changed_address_never_receives_the_stored_secret(client):
    """Security review of #61: URL changed + mask kept sent the key to the new host."""
    stored = [{"id": "a1", "url": "http://192.168.10.5:8989", "api_key": "real"}]
    client.put("/api/v1/config", json={"sonarr_instances_json": json.dumps(stored)})

    moved = [{"id": "a1", "url": "http://192.168.10.66:8989", "api_key": "***configured***"}]
    assert (
        client.put("/api/v1/config", json={"sonarr_instances_json": json.dumps(moved)}).status_code
        == 200
    )

    with client.application.app_context():
        from db.config import get_config_entry

        assert "api_key" not in json.loads(get_config_entry("sonarr_instances_json"))[0]


def test_the_export_masks_hub_secrets_like_get(client):
    from unittest.mock import patch

    with client.application.app_context():
        from db.config import save_config_entry

        save_config_entry("hub.demo.token", "s3cret")
        save_config_entry("hub.demo.flag", "on")
    with patch("providers.hub.secret_config_keys", return_value={"hub.demo.token"}):
        exported = client.get("/api/v1/config/export").get_json()
        shown = _get(client)

    assert exported["hub.demo.token"] == "***configured***"
    assert exported["hub.demo.flag"] == "on"
    assert {k: v for k, v in exported.items() if k.startswith("hub.")} == {
        k: v for k, v in shown.items() if k.startswith("hub.")
    }


@pytest.mark.parametrize(
    "key", ["plugin.x.command", "post_processing.op.script", "translation.foo"]
)
def test_an_import_does_not_write_other_namespaces(client, key):
    body = client.post("/api/v1/config/import", json={key: "rm -rf /"}).get_json()

    assert key not in body["imported_keys"]
    assert [e["key"] for e in body["skipped_invalid"]] == [key]
