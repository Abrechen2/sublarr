"""End-to-end tests for POST /api/v1/api-keys/import/bazarr.

Driven through the real route with a config.yaml shaped like Bazarr 1.4 writes
it (host, port, ssl and base_url as separate fields; both the legacy
``opensubtitles`` and the current ``opensubtitlescom`` section present) and a
bazarr.db with Bazarr's own table names.
"""

from __future__ import annotations

import io
import json
import sqlite3
import zipfile

BAZARR_CONFIG = """
general:
  use_sonarr: true
  use_radarr: true
sonarr:
  apikey: 0123456789abcdef0123456789abcdef
  base_url: /sonarr
  ip: 192.168.50.10
  port: 8989
  ssl: false
radarr:
  apikey: fedcba9876543210fedcba9876543210
  base_url: /
  ip: 192.168.50.11
  port: 7878
  ssl: true
opensubtitles:
  username: ''
  password: ''
opensubtitlescom:
  username: osuser
  password: ospass
"""

URL = "/api/v1/api-keys/import/bazarr"


def _bazarr_db_bytes(tmp_path) -> bytes:
    path = tmp_path / "bazarr.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE table_languages_profiles (
            profileId INTEGER PRIMARY KEY, name TEXT, items TEXT, cutoff INTEGER
        );
        CREATE TABLE table_blacklist (
            id INTEGER PRIMARY KEY, provider TEXT, subs_id TEXT,
            timestamp TEXT, language TEXT
        );
        """
    )
    conn.execute(
        "INSERT INTO table_languages_profiles (profileId, name, items) VALUES (?, ?, ?)",
        (1, "Deutsch", json.dumps([{"id": 1, "language": "de", "hi": "False"}])),
    )
    conn.execute(
        "INSERT INTO table_blacklist (provider, subs_id, timestamp, language) VALUES (?, ?, ?, ?)",
        ("opensubtitlescom", "987", "2025-01-01", "de"),
    )
    conn.commit()
    conn.close()
    return path.read_bytes()


def _post(client, payload: bytes, name: str, confirm: bool = False):
    data = {"file": (io.BytesIO(payload), name)}
    if confirm:
        data["confirm"] = "true"
    return client.post(URL, data=data, content_type="multipart/form-data")


def _entries(body) -> dict:
    return {e["key"]: e for e in body["config_entries"]}


def test_preview_builds_full_arr_urls_from_bazarr_fields(client):
    resp = _post(client, BAZARR_CONFIG.encode(), "config.yaml")
    assert resp.status_code == 200, resp.get_json()
    entries = _entries(resp.get_json())
    assert entries["sonarr_url"]["value"] == "http://192.168.50.10:8989/sonarr"
    assert entries["radarr_url"]["value"] == "https://192.168.50.11:7878"


def test_preview_prefers_the_current_opensubtitles_section(client):
    entries = _entries(_post(client, BAZARR_CONFIG.encode(), "config.yaml").get_json())
    assert entries["opensubtitles_username"]["value"] == "osuser"
    assert "opensubtitles_password" in entries
    assert "ospass" not in json.dumps(entries)


def test_preview_shows_what_each_entry_would_overwrite(client):
    with client.application.app_context():
        from db.config import save_config_entry

        save_config_entry("sonarr_url", "http://old-sonarr:8989")
        save_config_entry("sonarr_api_key", "oldsecretkey12345")

    entries = _entries(_post(client, BAZARR_CONFIG.encode(), "config.yaml").get_json())
    assert entries["sonarr_url"]["current_value"] == "http://old-sonarr:8989"
    assert entries["sonarr_api_key"]["current_value"] == "olds***"
    assert entries["radarr_url"]["current_value"] == ""


def test_a_bare_database_upload_is_read_as_a_database(client, tmp_path):
    resp = _post(client, _bazarr_db_bytes(tmp_path), "bazarr.db")
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["profiles"] == [{"name": "Deutsch", "languages": ["de"]}]
    assert body["blacklist_count"] == 1


def test_confirm_applies_and_the_running_settings_see_it(client, tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("config/config.yaml", BAZARR_CONFIG)
        zf.writestr("db/bazarr.db", _bazarr_db_bytes(tmp_path))

    resp = _post(client, buf.getvalue(), "bazarr-backup.zip", confirm=True)
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["status"] == "applied"
    assert body["profiles_imported"] == 1
    assert body["blacklist_imported"] == 1

    with client.application.app_context():
        from config import get_settings
        from db.config import get_config_entry

        assert get_config_entry("sonarr_url") == "http://192.168.50.10:8989/sonarr"
        assert get_config_entry("opensubtitles_username") == "osuser"
        assert get_settings().sonarr_url == "http://192.168.50.10:8989/sonarr"


def test_confirm_refuses_a_url_the_config_endpoint_would_refuse(client):
    loopback = BAZARR_CONFIG.replace("ip: 192.168.50.10", "ip: 127.0.0.1")
    resp = _post(client, loopback.encode(), "config.yaml", confirm=True)
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert any("sonarr_url" in w for w in body["warnings"])

    with client.application.app_context():
        from db.config import get_config_entry

        assert not get_config_entry("sonarr_url")
        assert not get_config_entry("sonarr_api_key")
        # The other half of the file is still imported.
        assert get_config_entry("radarr_url") == "https://192.168.50.11:7878"


def test_config_and_database_can_arrive_as_two_parts(client, tmp_path):
    data = {
        "file": [
            (io.BytesIO(BAZARR_CONFIG.encode()), "config.yaml"),
            (io.BytesIO(_bazarr_db_bytes(tmp_path)), "bazarr.db"),
        ]
    }
    resp = client.post(URL, data=data, content_type="multipart/form-data")
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert "sonarr_url" in _entries(body)
    assert body["blacklist_count"] == 1


def test_a_file_with_nothing_importable_is_refused(client):
    resp = _post(client, b"just some notes\nnothing here\n", "notes.txt")
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "No importable Bazarr settings found"


def test_two_config_files_are_merged_not_overwritten(client):
    sonarr_only = "sonarr:\n  ip: 192.168.50.10\n  port: 8989\n  apikey: aaaabbbbccccdddd\n"
    radarr_ini = "[radarr]\nip = 192.168.50.11\nport = 7878\napikey = eeeeffffgggghhhh\n"
    data = {
        "file": [
            (io.BytesIO(sonarr_only.encode()), "config.yaml"),
            (io.BytesIO(radarr_ini.encode()), "config.ini"),
        ]
    }
    resp = client.post(URL, data=data, content_type="multipart/form-data")
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert {"sonarr_url", "radarr_url"} <= set(_entries(body))
    assert any("config.ini" in w for w in body["warnings"])


def test_arr_url_brackets_a_bare_ipv6_host():
    from bazarr_data_mapper import arr_url

    assert arr_url({"url": "2001:db8::1", "port": 8989}) == "http://[2001:db8::1]:8989"
    assert arr_url({"url": "[2001:db8::1]:8989", "port": 8989}) == "http://[2001:db8::1]:8989"
    assert arr_url({"url": "sonarr:8989", "port": 8989}) == "http://sonarr:8989"
    assert arr_url({"url": "10.0.0.5", "port": "", "base_url": "/"}) == "http://10.0.0.5"
    assert arr_url({"url": "10.0.0.5", "port": 7878, "ssl": "False"}) == "http://10.0.0.5:7878"


def test_a_current_bazarr_database_raises_no_legacy_table_warnings(client, tmp_path):
    body = _post(client, _bazarr_db_bytes(tmp_path), "bazarr.db").get_json()
    assert not any("table_settings_" in w for w in body["warnings"])


def test_preview_already_says_which_address_will_be_skipped(client):
    loopback = BAZARR_CONFIG.replace("ip: 192.168.50.11", "ip: 127.0.0.1")
    body = _post(client, loopback.encode(), "config.yaml").get_json()
    assert any(w.startswith("radarr_url will not be imported") for w in body["warnings"])
    assert not any("sonarr_url" in w for w in body["warnings"])
