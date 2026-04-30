"""Regression tests for export_formats secret masking.

Audit 2026-04-30 found that `_export_json_format` only masked keys whose
name matched a small keyword set. That missed:

- `notification_urls_json` — Apprise URLs carry tokens in the URL itself
  (discord://…/token, slack://…/secret, tgram://bot_token/…)
- `database_url` — PostgreSQL DSNs commonly include a password
- `redis_url` — Redis URLs include a password
- `sonarr_instances_json` / `radarr_instances_json` / `media_servers_json`
  — JSON blobs containing nested API keys

The fix replaces the keyword-only heuristic with the central
`_mask_config_secrets()` helper, mirroring `Settings.get_safe_config()`.
This file pins the contract so the export pipeline cannot drift.
"""

from __future__ import annotations

import json

import pytest

from export_formats import _mask_config_secrets, _mask_secret


class TestMaskSecret:
    """Tiny helper used to mask individual values."""

    def test_short_value_fully_redacted(self):
        assert _mask_secret("abc") == "***"

    def test_eight_chars_fully_redacted(self):
        assert _mask_secret("abcdefgh") == "***"

    def test_long_value_keeps_4_chars_each_side(self):
        assert _mask_secret("abcdefghij") == "abcd***ghij"

    def test_empty_value_stays_empty(self):
        assert _mask_secret("") == ""


class TestMaskConfigSecrets:
    """The Tier-0 regression: notification URLs, DSNs, and JSON blobs."""

    def test_notification_urls_json_is_masked(self):
        """Apprise URLs include tokens in the URL itself."""
        cfg = {
            "notification_urls_json": json.dumps(
                [
                    "discord://1234/abcdef-very-secret-token",
                    "tgram://botid:12345/chatid",
                ]
            )
        }
        masked = _mask_config_secrets(cfg)
        assert "discord" not in masked["notification_urls_json"]
        assert "abcdef" not in masked["notification_urls_json"]
        assert "tgram" not in masked["notification_urls_json"]
        assert masked["notification_urls_json"] == "***configured***"

    def test_empty_notification_urls_json_left_alone(self):
        """Don't replace an empty string with a marker — that's misleading."""
        cfg = {"notification_urls_json": ""}
        masked = _mask_config_secrets(cfg)
        assert masked["notification_urls_json"] == ""

    def test_database_url_is_masked(self):
        """PostgreSQL DSN: postgresql://user:password@host/db."""
        cfg = {"database_url": "postgresql://app:supersecret@db.example.com/sublarr"}
        masked = _mask_config_secrets(cfg)
        assert "supersecret" not in masked["database_url"]
        assert masked["database_url"] != "postgresql://app:supersecret@db.example.com/sublarr"

    def test_redis_url_is_masked(self):
        cfg = {"redis_url": "redis://default:redispassword@localhost:6379/0"}
        masked = _mask_config_secrets(cfg)
        assert "redispassword" not in masked["redis_url"]

    def test_sonarr_instances_json_nested_api_keys_masked(self):
        """The JSON blob has API keys nested inside list-of-dicts."""
        instances = [
            {"name": "Main", "url": "http://sonarr:8989", "api_key": "REAL_API_KEY_VALUE"},
            {"name": "4K", "url": "http://sonarr-4k:8989", "api_key": "ANOTHER_KEY_HERE"},
        ]
        cfg = {"sonarr_instances_json": json.dumps(instances)}
        masked = _mask_config_secrets(cfg)
        decoded = json.loads(masked["sonarr_instances_json"])
        # URLs and names preserved
        assert decoded[0]["name"] == "Main"
        assert decoded[0]["url"] == "http://sonarr:8989"
        # API keys masked
        assert decoded[0]["api_key"] != "REAL_API_KEY_VALUE"
        assert "REAL_API" not in decoded[0]["api_key"]
        assert decoded[1]["api_key"] != "ANOTHER_KEY_HERE"

    def test_radarr_instances_json_nested_keys_masked(self):
        instances = [{"name": "Movies", "url": "http://r:7878", "api_key": "rdrkey12345678"}]
        cfg = {"radarr_instances_json": json.dumps(instances)}
        masked = _mask_config_secrets(cfg)
        decoded = json.loads(masked["radarr_instances_json"])
        assert decoded[0]["api_key"] != "rdrkey12345678"

    def test_media_servers_json_nested_keys_masked(self):
        instances = [{"name": "Plex", "type": "plex", "token": "Plex_Token_Value_xyz"}]
        cfg = {"media_servers_json": json.dumps(instances)}
        masked = _mask_config_secrets(cfg)
        decoded = json.loads(masked["media_servers_json"])
        assert decoded[0]["token"] != "Plex_Token_Value_xyz"

    def test_malformed_json_blob_is_safely_marked(self):
        """If a JSON blob is malformed, fall back to an opaque marker rather
        than leaking the raw bytes (which may still be partially valid)."""
        cfg = {"sonarr_instances_json": "{not valid JSON, has secret_token=ABC"}
        masked = _mask_config_secrets(cfg)
        assert "ABC" not in masked["sonarr_instances_json"]
        assert masked["sonarr_instances_json"] == "***configured***"

    def test_keyword_based_masking_still_applies(self):
        """Existing rule (api_key / password / token / secret in name) survives."""
        cfg = {
            "sonarr_api_key": "abcd1234sonarr",
            "user_password": "p@ssw0rd",
            "discord_token": "discord-token",
            "session_secret": "session-secret",
            "license_key": "license-key-value",  # 'key' as standalone part
        }
        masked = _mask_config_secrets(cfg)
        for k in cfg:
            assert masked[k] != cfg[k], f"{k} was not masked"

    def test_non_credential_values_preserved(self):
        cfg = {
            "media_path": "/media",
            "max_concurrent_searches": 4,
            "wanted_scan_interval_hours": 6,
            "log_level": "INFO",
        }
        masked = _mask_config_secrets(cfg)
        assert masked == cfg

    def test_does_not_mutate_input_dict(self):
        cfg = {"sonarr_api_key": "real_key_value_1234"}
        original = dict(cfg)
        _mask_config_secrets(cfg)
        assert cfg == original


class TestExportJsonFormatIntegration:
    """End-to-end: export_config(format='json', include_secrets=False) must
    not leak any of the previously-missed credential fields."""

    def test_export_json_masks_notification_urls(self, monkeypatch):
        from export_manager import export_config

        monkeypatch.setattr(
            "export_formats._get_config_entries",
            lambda warnings: {
                "notification_urls_json": json.dumps(["discord://1/secret_token_xyz_abcdef"]),
                "media_path": "/media",
            },
        )
        monkeypatch.setattr("export_formats._get_language_profiles", lambda warnings: [])
        monkeypatch.setattr(
            "export_formats._get_provider_stats_summary",
            lambda warnings: {"providers": []},
        )

        result = export_config("json", include_secrets=False)
        dumped = json.dumps(result["data"])
        assert "secret_token_xyz_abcdef" not in dumped
        assert "discord://" not in dumped

    def test_export_json_with_include_secrets_true_passes_raw(self, monkeypatch):
        from export_manager import export_config

        raw = {
            "notification_urls_json": json.dumps(["discord://1/visible_token"]),
            "sonarr_api_key": "raw_sonarr_key_1234",
        }
        monkeypatch.setattr("export_formats._get_config_entries", lambda warnings: dict(raw))
        monkeypatch.setattr("export_formats._get_language_profiles", lambda warnings: [])
        monkeypatch.setattr(
            "export_formats._get_provider_stats_summary",
            lambda warnings: {"providers": []},
        )

        result = export_config("json", include_secrets=True)
        config = result["data"]["config_entries"]
        # Explicit opt-in returns raw values
        assert "visible_token" in config["notification_urls_json"]
        assert config["sonarr_api_key"] == "raw_sonarr_key_1234"

    def test_export_json_masks_database_url(self, monkeypatch):
        from export_manager import export_config

        monkeypatch.setattr(
            "export_formats._get_config_entries",
            lambda warnings: {
                "database_url": "postgresql://app:dbpassword@db/sublarr",
            },
        )
        monkeypatch.setattr("export_formats._get_language_profiles", lambda warnings: [])
        monkeypatch.setattr(
            "export_formats._get_provider_stats_summary",
            lambda warnings: {"providers": []},
        )

        result = export_config("json", include_secrets=False)
        config = result["data"]["config_entries"]
        assert "dbpassword" not in config["database_url"]
