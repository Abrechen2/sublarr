"""Unit tests for bazarr_migrator.py — config parsing, DB reading, transformation."""

import json
import os
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, call, patch

# ---------------------------------------------------------------------------
# parse_bazarr_config — config parsing
# ---------------------------------------------------------------------------


def test_parse_empty_config():
    from bazarr_migrator import parse_bazarr_config

    result = parse_bazarr_config("", "config.yaml")
    assert result["sonarr"] == {}
    assert result["radarr"] == {}
    assert result["general"] == {}
    assert len(result["warnings"]) > 0


def test_parse_yaml_config():
    from bazarr_migrator import parse_bazarr_config

    yaml_content = """
sonarr:
  ip: "192.168.1.10"
  port: "8989"
  apikey: "sonarr-key-abc"
radarr:
  ip: "192.168.1.10"
  port: "7878"
  apikey: "radarr-key-xyz"
general:
  serie_default_language: "en"
"""
    result = parse_bazarr_config(yaml_content, "config.yaml")
    assert result["sonarr"]["url"] == "192.168.1.10"
    assert result["sonarr"]["api_key"] == "sonarr-key-abc"
    assert result["radarr"]["api_key"] == "radarr-key-xyz"
    assert result["general"]["source_language"] == "en"


def test_parse_ini_config():
    from bazarr_migrator import parse_bazarr_config

    ini_content = """
[sonarr]
ip = 10.0.0.1
port = 8989
apikey = sonarr-ini-key

[radarr]
ip = 10.0.0.1
port = 7878
apikey = radarr-ini-key

[general]
serie_default_language = en
"""
    result = parse_bazarr_config(ini_content, "config.ini")
    assert result["sonarr"]["url"] == "10.0.0.1"
    assert result["sonarr"]["api_key"] == "sonarr-ini-key"
    assert result["radarr"]["api_key"] == "radarr-ini-key"


def test_parse_config_missing_sonarr_section():
    from bazarr_migrator import parse_bazarr_config

    yaml_content = """
general:
  serie_default_language: "en"
"""
    result = parse_bazarr_config(yaml_content, "config.yaml")
    # When sonarr section is absent the dict has empty-string values
    assert result["sonarr"].get("api_key", "") == ""
    assert result["sonarr"].get("url", "") == ""


def test_parse_config_missing_radarr_section():
    from bazarr_migrator import parse_bazarr_config

    yaml_content = """
sonarr:
  ip: "10.0.0.1"
  apikey: "key"
"""
    result = parse_bazarr_config(yaml_content, "config.yaml")
    # radarr section absent → radarr dict should be empty or have empty values
    assert result["radarr"].get("api_key", "") == ""


def test_parse_config_opensubtitles_credentials():
    from bazarr_migrator import parse_bazarr_config

    yaml_content = """
opensubtitles:
  username: "myuser"
  password: "mypass"
  apikey: "oskey"
general:
  serie_default_language: "en"
"""
    result = parse_bazarr_config(yaml_content, "config.yaml")
    assert result["general"]["opensubtitles_username"] == "myuser"
    assert result["general"]["opensubtitles_api_key"] == "oskey"


def test_parse_config_unknown_extension_tries_yaml():
    from bazarr_migrator import parse_bazarr_config

    yaml_content = """
sonarr:
  apikey: "key"
"""
    # Unknown extension → tries YAML first
    result = parse_bazarr_config(yaml_content, "config.txt")
    assert result["sonarr"]["api_key"] == "key"


def test_parse_config_raw_preserved():
    from bazarr_migrator import parse_bazarr_config

    yaml_content = """
sonarr:
  ip: "10.0.0.1"
"""
    result = parse_bazarr_config(yaml_content, "config.yaml")
    assert "raw" in result
    assert isinstance(result["raw"], dict)


# ---------------------------------------------------------------------------
# _normalize_config — internal normalization
# ---------------------------------------------------------------------------


def test_normalize_config_handles_case_variants():
    from bazarr_migrator import _normalize_config

    data = {
        "Sonarr": {"ip": "host", "apikey": "key"},
        "Radarr": {"ip": "host2", "apikey": "key2"},
        "General": {"serie_default_language": "en"},
    }
    result = _normalize_config(data, [])
    assert result["sonarr"]["url"] == "host"
    assert result["radarr"]["url"] == "host2"
    assert result["general"]["source_language"] == "en"


def test_normalize_config_url_with_port():
    from bazarr_migrator import parse_bazarr_config

    yaml_content = """
sonarr:
  ip: "192.168.1.1"
  port: "8989"
  apikey: "abc"
"""
    result = parse_bazarr_config(yaml_content, "config.yaml")
    # Port should be stored separately, not concatenated in url by parse
    assert result["sonarr"]["port"] == "8989"


# ---------------------------------------------------------------------------
# _validate_table_name — SQL injection prevention
# ---------------------------------------------------------------------------


def test_validate_table_name_valid():
    from bazarr_migrator import _validate_table_name

    # Should not raise
    _validate_table_name("table_shows")
    _validate_table_name("my_table123")
    _validate_table_name("TableName")


def test_validate_table_name_invalid():
    import pytest

    from bazarr_migrator import _validate_table_name

    with pytest.raises(ValueError):
        _validate_table_name("table; DROP TABLE users")

    with pytest.raises(ValueError):
        _validate_table_name("1invalid")  # starts with digit

    with pytest.raises(ValueError):
        _validate_table_name("")


def test_validate_table_name_rejects_spaces():
    import pytest

    from bazarr_migrator import _validate_table_name

    with pytest.raises(ValueError):
        _validate_table_name("table name")


# ---------------------------------------------------------------------------
# migrate_bazarr_db — DB reading with real SQLite
# ---------------------------------------------------------------------------


def _create_bazarr_db(path: str) -> None:
    """Create a minimal Bazarr-like SQLite database for testing."""
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS table_languages_profiles (
            profileId INTEGER PRIMARY KEY,
            name TEXT,
            items TEXT,
            cutoff INTEGER
        );
        CREATE TABLE IF NOT EXISTS table_blacklist (
            id INTEGER PRIMARY KEY,
            provider TEXT,
            subs_id TEXT,
            timestamp TEXT,
            language TEXT
        );
        CREATE TABLE IF NOT EXISTS table_settings_sonarr (
            ip TEXT,
            port TEXT,
            apikey TEXT
        );
        CREATE TABLE IF NOT EXISTS table_history (
            id INTEGER PRIMARY KEY,
            provider TEXT,
            score INTEGER,
            subs_id TEXT,
            video_path TEXT,
            language TEXT,
            timestamp TEXT
        );
        CREATE TABLE IF NOT EXISTS table_shows (
            id INTEGER PRIMARY KEY,
            title TEXT,
            path TEXT,
            profileId INTEGER,
            audio_language TEXT,
            sonarrSeriesId INTEGER
        );
    """)
    # Insert sample profile
    conn.execute(
        "INSERT INTO table_languages_profiles (profileId, name, items, cutoff) VALUES (?, ?, ?, ?)",
        (1, "German", json.dumps([{"language": "de", "hi": "False", "forced": "False"}]), None),
    )
    # Insert blacklist entry
    conn.execute(
        "INSERT INTO table_blacklist (provider, subs_id, timestamp, language) VALUES (?, ?, ?, ?)",
        ("opensubtitles", "12345", "2024-01-01", "de"),
    )
    # Insert history entry
    conn.execute(
        "INSERT INTO table_history (provider, score, subs_id, video_path, language, timestamp)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        ("animetosho", 80, "abc", "/media/ep.mkv", "de", "2024-01-01"),
    )
    # Insert show
    conn.execute(
        "INSERT INTO table_shows (title, path, profileId, audio_language, sonarrSeriesId)"
        " VALUES (?, ?, ?, ?, ?)",
        ("My Anime", "/media/anime", 1, "en", 101),
    )
    conn.commit()
    conn.close()


def test_migrate_db_profiles(temp_dir):
    from bazarr_migrator import migrate_bazarr_db

    db_path = os.path.join(temp_dir, "bazarr.db")
    _create_bazarr_db(db_path)

    result = migrate_bazarr_db(db_path)
    assert len(result["profiles"]) == 1
    profile = result["profiles"][0]
    assert profile["name"] == "German"
    assert len(profile["languages"]) == 1
    assert profile["languages"][0]["language"] == "de"


def test_migrate_db_blacklist(temp_dir):
    from bazarr_migrator import migrate_bazarr_db

    db_path = os.path.join(temp_dir, "bazarr.db")
    _create_bazarr_db(db_path)

    result = migrate_bazarr_db(db_path)
    assert len(result["blacklist"]) == 1
    entry = result["blacklist"][0]
    assert entry["provider"] == "opensubtitles"
    assert entry["subtitle_id"] == "12345"
    assert entry["language"] == "de"


def test_migrate_db_history(temp_dir):
    from bazarr_migrator import migrate_bazarr_db

    db_path = os.path.join(temp_dir, "bazarr.db")
    _create_bazarr_db(db_path)

    result = migrate_bazarr_db(db_path)
    assert len(result["history"]) == 1
    entry = result["history"][0]
    assert entry["provider"] == "animetosho"
    assert entry["language"] == "de"


def test_migrate_db_shows(temp_dir):
    from bazarr_migrator import migrate_bazarr_db

    db_path = os.path.join(temp_dir, "bazarr.db")
    _create_bazarr_db(db_path)

    result = migrate_bazarr_db(db_path)
    assert len(result["shows"]) == 1
    show = result["shows"][0]
    assert show["title"] == "My Anime"
    assert show["sonarrSeriesId"] == 101


def test_migrate_db_nonexistent_file():
    from bazarr_migrator import migrate_bazarr_db

    result = migrate_bazarr_db("/nonexistent/path/to/bazarr.db")
    assert len(result["warnings"]) > 0
    assert result["profiles"] == []
    assert result["blacklist"] == []


def test_migrate_db_missing_table(temp_dir):
    from bazarr_migrator import migrate_bazarr_db

    # Create empty DB (no tables)
    db_path = os.path.join(temp_dir, "empty.db")
    conn = sqlite3.connect(db_path)
    conn.close()

    result = migrate_bazarr_db(db_path)
    # Should have warnings about missing tables, not crash
    assert len(result["warnings"]) > 0


def test_migrate_db_profile_invalid_json(temp_dir):
    from bazarr_migrator import migrate_bazarr_db

    db_path = os.path.join(temp_dir, "bazarr_bad.db")
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE table_languages_profiles (profileId INTEGER, name TEXT, items TEXT, cutoff INTEGER)"
    )
    conn.execute("INSERT INTO table_languages_profiles VALUES (1, 'Test', 'not-valid-json', NULL)")
    conn.commit()
    conn.close()

    result = migrate_bazarr_db(db_path)
    # Profile should exist with empty languages (invalid JSON handled)
    assert len(result["profiles"]) == 1
    assert result["profiles"][0]["languages"] == []
    # Warning should mention the parse failure
    assert any("parse" in w.lower() or "language" in w.lower() for w in result["warnings"])


# ---------------------------------------------------------------------------
# preview_migration — transformation preview
# ---------------------------------------------------------------------------


def test_preview_migration_empty_inputs():
    from bazarr_migrator import preview_migration

    config_data = {"sonarr": {}, "radarr": {}, "general": {}, "raw": {}, "warnings": []}
    db_data = {
        "profiles": [],
        "blacklist": [],
        "history": [],
        "shows": [],
        "movies": [],
        "warnings": [],
        "sonarr_config": {},
        "radarr_config": {},
    }
    result = preview_migration(config_data, db_data)
    assert result["config_entries"] == []
    assert result["profiles"] == []
    assert result["blacklist_count"] == 0


def test_preview_migration_with_sonarr_config():
    from bazarr_migrator import preview_migration

    config_data = {
        "sonarr": {"url": "10.0.0.1", "port": "8989", "api_key": "mykey"},
        "radarr": {},
        "general": {},
        "raw": {},
        "warnings": [],
    }
    db_data = {
        "profiles": [],
        "blacklist": [],
        "history": [],
        "shows": [],
        "movies": [],
        "warnings": [],
        "sonarr_config": {},
        "radarr_config": {},
    }
    result = preview_migration(config_data, db_data)
    # sonarr_url and sonarr_api_key should appear in config_entries
    keys = [e["key"] for e in result["config_entries"]]
    assert "sonarr_url" in keys
    assert "sonarr_api_key" in keys


def test_preview_migration_masks_api_key():
    from bazarr_migrator import _mask_preview, preview_migration

    # _mask_preview should show first 4 chars + ***
    assert _mask_preview("abc123abc") == "abc1***"
    assert _mask_preview("ab") == "***"
    assert _mask_preview("") == "***"


def test_preview_migration_blacklist_count():
    from bazarr_migrator import preview_migration

    config_data = {"sonarr": {}, "radarr": {}, "general": {}, "raw": {}, "warnings": []}
    db_data = {
        "profiles": [],
        "blacklist": [
            {"provider": "p1", "subtitle_id": "1", "language": "de", "timestamp": "2024-01-01"}
        ]
        * 5,
        "history": [],
        "shows": [],
        "movies": [],
        "warnings": [],
        "sonarr_config": {},
        "radarr_config": {},
    }
    result = preview_migration(config_data, db_data)
    assert result["blacklist_count"] == 5


# ---------------------------------------------------------------------------
# map_bazarr_provider_settings — provider mapping
# ---------------------------------------------------------------------------


def test_map_provider_settings_opensubtitles():
    from bazarr_migrator import map_bazarr_provider_settings

    config_data = {
        "general": {
            "opensubtitles_api_key": "oskey123",
            "opensubtitles_username": "testuser",
            "opensubtitles_password": "testpass",
        }
    }
    result = map_bazarr_provider_settings(config_data)
    assert "OpenSubtitles" in result["provider_mappings"]
    assert result["provider_mappings"]["OpenSubtitles"]["api_key"] == "oskey123"
    assert result["settings_imported"] == 1


def test_map_provider_settings_empty():
    from bazarr_migrator import map_bazarr_provider_settings

    config_data = {"general": {}}
    result = map_bazarr_provider_settings(config_data)
    assert result["provider_mappings"] == {}
    assert result["settings_imported"] == 0


# ---------------------------------------------------------------------------
# generate_mapping_report — schema inventory
# ---------------------------------------------------------------------------


def test_generate_mapping_report_nonexistent():
    from bazarr_migrator import generate_mapping_report

    report = generate_mapping_report("/nonexistent/path.db")
    assert len(report["warnings"]) > 0
    assert report["tables_found"] == []


def test_generate_mapping_report_real_db(temp_dir):
    from bazarr_migrator import generate_mapping_report

    db_path = os.path.join(temp_dir, "bazarr.db")
    _create_bazarr_db(db_path)

    report = generate_mapping_report(db_path)
    assert "table_languages_profiles" in report["tables_found"]
    assert "table_blacklist" in report["tables_found"]
    assert report["migration_summary"]["profiles_count"] == 1
    assert report["migration_summary"]["blacklist_count"] == 1
