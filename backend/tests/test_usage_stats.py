"""Tests for services.usage_stats — opt-in anonymous usage statistics.

Covers consent tri-state, anonymous install id, the payload builder (fields +
no-PII guarantee + buckets), and the consent-gated best-effort ping tick.
"""

from unittest.mock import patch

import pytest

from services import usage_stats


class TestConsent:
    def test_default_consent_is_unset(self, app_ctx):
        assert usage_stats.get_consent() == "unset"

    def test_set_and_get_consent_roundtrips(self, app_ctx):
        usage_stats.set_consent("granted")
        assert usage_stats.get_consent() == "granted"
        usage_stats.set_consent("denied")
        assert usage_stats.get_consent() == "denied"

    def test_set_consent_rejects_invalid(self, app_ctx):
        with pytest.raises(ValueError):
            usage_stats.set_consent("maybe")


class TestInstallId:
    def test_install_id_is_stable(self, app_ctx):
        first = usage_stats.get_or_create_install_id()
        second = usage_stats.get_or_create_install_id()
        assert first == second
        assert len(first) == 32  # uuid4().hex


class TestPayload:
    def test_bucket_boundaries(self):
        b = usage_stats.bucket_library_size
        assert b(0) == "<100"
        assert b(99) == "<100"
        assert b(100) == "100-1k"
        assert b(999) == "100-1k"
        assert b(1000) == "1k-10k"
        assert b(9999) == "1k-10k"
        assert b(10000) == "10k+"

    def test_payload_has_only_allowed_keys(self, app_ctx):
        payload = usage_stats.build_usage_payload()
        assert set(payload) == {
            "install_id",
            "version",
            "arch",
            "db_backend",
            "providers_enabled",
            "library_size_bucket",
            "reported_at",
            "features",
            "env",
            "scale",
            "auto_disabled_count",
        }

    def test_payload_contains_no_pii(self, app_ctx):
        payload = usage_stats.build_usage_payload()
        blob = str(payload).lower()
        assert "/media" not in blob and "\\" not in blob
        assert isinstance(payload["providers_enabled"], list)

    def test_payload_nested_groups_contain_no_pii(self, app_ctx):
        """The features/env/scale groups must carry only enums/bools/buckets —
        no path separators, URLs, or credential-looking substrings."""
        payload = usage_stats.build_usage_payload()
        blob = str(
            {k: payload[k] for k in ("features", "env", "scale", "auto_disabled_count")}
        ).lower()
        for forbidden in ("/media", "\\", "http", "://", "api_key", "password", "token"):
            assert forbidden not in blob, f"nested groups leaked {forbidden!r}"


class TestFeaturesGroup:
    _EXPECTED = {
        "translation_enabled",
        "translation_backend",
        "media_server_type",
        "sonarr_connected",
        "radarr_connected",
        "standalone_mode",
        "redis_used",
    }

    def test_features_has_expected_keys(self, app_ctx):
        features = usage_stats.build_usage_payload()["features"]
        assert set(features) == self._EXPECTED

    def test_features_types(self, app_ctx):
        features = usage_stats.build_usage_payload()["features"]
        for key in (
            "translation_enabled",
            "sonarr_connected",
            "radarr_connected",
            "standalone_mode",
            "redis_used",
        ):
            assert isinstance(features[key], bool)
        assert features["translation_backend"] in {"ollama", "openai", "none"}
        assert features["media_server_type"] in {
            "jellyfin",
            "emby",
            "plex",
            "kodi",
            "multiple",
            "none",
        }

    def test_translation_backend_none_when_disabled(self):
        from types import SimpleNamespace

        s = SimpleNamespace(translation_enabled=False, translation_default_backend="ollama")
        assert usage_stats._translation_backend_type(s) == "none"

    def test_translation_backend_ollama(self):
        from types import SimpleNamespace

        s = SimpleNamespace(translation_enabled=True, translation_default_backend="ollama")
        assert usage_stats._translation_backend_type(s) == "ollama"

    def test_translation_backend_external_maps_to_openai(self):
        from types import SimpleNamespace

        s = SimpleNamespace(translation_enabled=True, translation_default_backend="deepl")
        assert usage_stats._translation_backend_type(s) == "openai"

    def test_media_server_type_single(self):
        from types import SimpleNamespace

        s = SimpleNamespace(
            media_servers_json='[{"type": "plex", "name": "x", "url": "http://h"}]',
            jellyfin_url="",
        )
        assert usage_stats._media_server_type(s) == "plex"

    def test_media_server_type_multiple(self):
        from types import SimpleNamespace

        s = SimpleNamespace(
            media_servers_json='[{"type": "plex"}, {"type": "kodi"}]',
            jellyfin_url="",
        )
        assert usage_stats._media_server_type(s) == "multiple"

    def test_media_server_type_legacy_jellyfin(self):
        from types import SimpleNamespace

        s = SimpleNamespace(media_servers_json="", jellyfin_url="http://host:8096")
        assert usage_stats._media_server_type(s) == "jellyfin"

    def test_media_server_type_none(self):
        from types import SimpleNamespace

        s = SimpleNamespace(media_servers_json="", jellyfin_url="")
        assert usage_stats._media_server_type(s) == "none"


class TestEnvGroup:
    def test_env_has_expected_keys(self, app_ctx):
        env = usage_stats.build_usage_payload()["env"]
        assert set(env) == {"interface_language", "auth_type", "update_channel"}

    def test_env_types(self, app_ctx):
        env = usage_stats.build_usage_payload()["env"]
        assert isinstance(env["interface_language"], str)
        assert env["auth_type"] in {"none", "ui", "proxy"}
        assert env["update_channel"] in {"stable", "rc", "beta"}

    def test_auth_type_proxy_wins(self):
        from types import SimpleNamespace

        s = SimpleNamespace(proxy_auth_enabled=True, api_key="secret")
        assert usage_stats._auth_type(s) == "proxy"

    def test_auth_type_ui_when_api_key(self):
        from types import SimpleNamespace

        s = SimpleNamespace(proxy_auth_enabled=False, api_key="secret")
        assert usage_stats._auth_type(s) == "ui"

    def test_auth_type_none(self):
        from types import SimpleNamespace

        s = SimpleNamespace(proxy_auth_enabled=False, api_key="")
        assert usage_stats._auth_type(s) == "none"

    def test_update_channel_stable(self):
        assert usage_stats._update_channel("1.9.4") == "stable"

    def test_update_channel_rc(self):
        assert usage_stats._update_channel("1.6.5-rc.2") == "rc"

    def test_update_channel_beta(self):
        assert usage_stats._update_channel("0.55.0-beta") == "beta"


class TestScaleGroup:
    def test_scale_has_expected_keys_and_buckets(self, app_ctx):
        scale = usage_stats.build_usage_payload()["scale"]
        assert set(scale) == {
            "series_bucket",
            "movies_bucket",
            "downloads_bucket",
            "translation_jobs_bucket",
        }
        valid = {"<100", "100-1k", "1k-10k", "10k+"}
        for value in scale.values():
            assert value in valid

    def test_auto_disabled_count_is_non_negative_int(self, app_ctx):
        count = usage_stats.build_usage_payload()["auto_disabled_count"]
        assert isinstance(count, int)
        assert count >= 0


class TestForget:
    def test_forget_url_from_ping_endpoint(self):
        assert (
            usage_stats._forget_url("https://stats.sublarr.de/v1/ping")
            == "https://stats.sublarr.de/v1/forget"
        )

    def test_forget_url_from_bare_base(self):
        assert usage_stats._forget_url("https://x") == "https://x/v1/forget"

    def test_forget_noop_when_endpoint_empty(self, app_ctx):
        with patch("services.usage_stats.requests.post") as mock_post:
            assert usage_stats.forget_install("") is False
        mock_post.assert_not_called()

    def test_forget_posts_install_id(self, app_ctx):
        install_id = usage_stats.get_or_create_install_id()

        class _Resp:
            status_code = 204

        with patch("services.usage_stats.requests.post", return_value=_Resp()) as mock_post:
            assert usage_stats.forget_install("https://stats.sublarr.de/v1/ping") is True

        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "https://stats.sublarr.de/v1/forget"
        assert kwargs["json"] == {"install_id": install_id}

    def test_forget_swallows_errors(self, app_ctx):
        with patch("services.usage_stats.requests.post", side_effect=OSError("boom")):
            assert usage_stats.forget_install("https://x/v1/ping") is False

    def test_arch_is_normalised(self, app_ctx):
        assert usage_stats.detect_arch() == usage_stats.detect_arch()

    def test_db_backend_detect(self, app_ctx):
        assert usage_stats.detect_db_backend() in {"sqlite", "postgres"}

    def test_enabled_providers_explicit_list(self, monkeypatch):
        from types import SimpleNamespace

        import config

        monkeypatch.setattr(
            config, "get_settings", lambda: SimpleNamespace(providers_enabled="addic7ed, subdl")
        )
        assert usage_stats._enabled_providers() == ["addic7ed", "subdl"]

    def test_enabled_providers_empty_resolves_to_all_registered(self, monkeypatch):
        """Empty providers_enabled means 'all registered' — must NOT report []."""
        from types import SimpleNamespace

        import config

        monkeypatch.setattr(config, "get_settings", lambda: SimpleNamespace(providers_enabled=""))
        from providers.registry import _PROVIDER_CLASSES

        result = usage_stats._enabled_providers()
        assert result == sorted(_PROVIDER_CLASSES.keys())
        assert len(result) > 5, "registry should expose the full provider set, not empty"


class TestTick:
    def test_tick_noop_when_not_granted(self, app_ctx):
        usage_stats.set_consent("denied")
        with patch("services.usage_stats.send_ping") as mock_send:
            usage_stats.usage_stats_tick()
        mock_send.assert_not_called()

    def test_tick_noop_when_endpoint_empty(self, app_ctx, monkeypatch):
        usage_stats.set_consent("granted")
        monkeypatch.setattr(usage_stats, "get_stats_endpoint", lambda: "")
        with patch("services.usage_stats.send_ping") as mock_send:
            usage_stats.usage_stats_tick()
        mock_send.assert_not_called()

    def test_tick_sends_when_granted(self, app_ctx, monkeypatch):
        usage_stats.set_consent("granted")
        monkeypatch.setattr(usage_stats, "get_stats_endpoint", lambda: "https://x/v1/ping")
        with patch("services.usage_stats.send_ping", return_value=True) as mock_send:
            usage_stats.usage_stats_tick()
        assert mock_send.call_count == 1

    def test_send_ping_swallows_errors(self):
        with patch("services.usage_stats.requests.post", side_effect=OSError("boom")):
            assert usage_stats.send_ping({"a": 1}, "https://x/v1/ping") is False


class TestConsentWithdrawalFiresForget:
    def test_denied_triggers_forget_post(self, client):
        """Setting consent -> denied must fire one best-effort forget POST.

        submit_background is run synchronously so the app-context wrapper is
        exercised; the underlying HTTP POST is mocked (no real network)."""

        class _Resp:
            status_code = 204

        with (
            patch(
                "routes.system.usage_stats.submit_background",
                lambda fn, *a, **k: fn(),
            ),
            patch(
                "routes.system.usage_stats.get_stats_endpoint",
                lambda: "https://stats.sublarr.de/v1/ping",
            ),
            patch("services.usage_stats.requests.post", return_value=_Resp()) as mock_post,
        ):
            resp = client.post("/api/v1/usage-stats/consent", json={"consent": "denied"})

        assert resp.status_code == 200
        assert resp.get_json()["consent"] == "denied"
        mock_post.assert_called_once()
        assert mock_post.call_args[0][0] == "https://stats.sublarr.de/v1/forget"

    def test_granted_does_not_trigger_forget(self, client):
        """The granted path must NOT fire a forget."""
        with (
            patch(
                "routes.system.usage_stats.submit_background",
                lambda fn, *a, **k: fn(),
            ),
            patch("routes.system.usage_stats.usage_stats_tick"),
            patch("services.usage_stats.forget_install") as mock_forget,
        ):
            resp = client.post("/api/v1/usage-stats/consent", json={"consent": "granted"})

        assert resp.status_code == 200
        mock_forget.assert_not_called()
