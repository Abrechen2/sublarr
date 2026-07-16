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
        }

    def test_payload_contains_no_pii(self, app_ctx):
        payload = usage_stats.build_usage_payload()
        blob = str(payload).lower()
        assert "/media" not in blob and "\\" not in blob
        assert isinstance(payload["providers_enabled"], list)

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

        monkeypatch.setattr(
            config, "get_settings", lambda: SimpleNamespace(providers_enabled="")
        )
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
