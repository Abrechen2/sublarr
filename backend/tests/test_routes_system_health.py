"""HTTP tests for routes/system/health.py — /health, /update, /health/detailed."""

import time
from unittest.mock import MagicMock, patch

import pytest

# ───────────────────────────────────────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────────────────────────────────────


def _reset_update_cache():
    """Clear the module-level update cache between tests."""
    from routes.system import health as _mod

    _mod._update_cache = {"result": None, "checked_at": None}


@pytest.fixture(autouse=True)
def _clear_cache():
    """Ensure each test starts with a fresh update cache."""
    _reset_update_cache()
    yield
    _reset_update_cache()


# ───────────────────────────────────────────────────────────────────────────────
# _is_newer_version (pure unit tests — no Flask context needed)
# ───────────────────────────────────────────────────────────────────────────────


class TestIsNewerVersion:
    """Tests for the version comparison helper."""

    @staticmethod
    def _fn(tag, current):
        from routes.system.health import _is_newer_version

        return _is_newer_version(tag, current)

    def test_newer_patch(self):
        assert self._fn("v1.2.4", "1.2.3") is True

    def test_newer_minor(self):
        assert self._fn("v2.0.0", "1.9.9") is True

    def test_same_version(self):
        assert self._fn("1.2.3", "1.2.3") is False

    def test_older_version(self):
        assert self._fn("1.0.0", "1.2.3") is False

    def test_strips_beta_suffix(self):
        assert self._fn("2.0.0-beta", "1.0.0") is True

    def test_both_have_prefix_suffix(self):
        assert self._fn("v1.0.1-rc1", "v1.0.0-beta") is True

    def test_invalid_tag_returns_false(self):
        assert self._fn("not-a-version", "1.0.0") is False

    def test_invalid_current_uses_zero(self):
        # "not-a-version" parses to (0,0,0) so any valid tag > 0.0.0 is newer
        assert self._fn("0.0.1", "not-a-version") is True


# ───────────────────────────────────────────────────────────────────────────────
# GET /api/v1/health
# ───────────────────────────────────────────────────────────────────────────────


class TestHealthEndpoint:
    """Basic health endpoint — unauthenticated probe and authenticated detail."""

    @patch("routes.system.health._health_check_ollama", return_value=({"ollama": "ok"}, None))
    @patch(
        "routes.system.health._health_check_providers",
        return_value=({"providers": "healthy"}, None),
    )
    @patch(
        "routes.system.health._health_check_sonarr",
        return_value=({"sonarr": "not configured"}, None),
    )
    @patch(
        "routes.system.health._health_check_radarr",
        return_value=({"radarr": "not configured"}, None),
    )
    @patch(
        "routes.system.health._health_check_media_servers",
        return_value=({"media_servers": "none configured"}, None),
    )
    def test_health_returns_200_when_all_ok(self, _ms, _rad, _son, _prov, _oll, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "healthy"

    @patch("routes.system.health._health_check_ollama", return_value=({"ollama": "ok"}, None))
    @patch(
        "routes.system.health._health_check_providers",
        return_value=({"providers": "healthy"}, None),
    )
    @patch(
        "routes.system.health._health_check_sonarr",
        return_value=({"sonarr": "not configured"}, None),
    )
    @patch(
        "routes.system.health._health_check_radarr",
        return_value=({"radarr": "not configured"}, None),
    )
    @patch(
        "routes.system.health._health_check_media_servers",
        return_value=({"media_servers": "none configured"}, None),
    )
    def test_health_includes_version_and_services_when_no_api_key(
        self, _ms, _rad, _son, _prov, _oll, client
    ):
        """When SUBLARR_API_KEY is empty (test default), callers are treated as authenticated."""
        resp = client.get("/api/v1/health")
        data = resp.get_json()
        # No API key configured → treated as authenticated → version + services present
        assert "version" in data
        assert "services" in data

    @patch("routes.system.health._health_check_ollama", return_value=({"ollama": "error"}, False))
    @patch(
        "routes.system.health._health_check_providers",
        return_value=({"providers": "healthy"}, None),
    )
    @patch(
        "routes.system.health._health_check_sonarr",
        return_value=({"sonarr": "not configured"}, None),
    )
    @patch(
        "routes.system.health._health_check_radarr",
        return_value=({"radarr": "not configured"}, None),
    )
    @patch(
        "routes.system.health._health_check_media_servers",
        return_value=({"media_servers": "none configured"}, None),
    )
    def test_health_returns_503_when_required_service_down(
        self, _ms, _rad, _son, _prov, _oll, client
    ):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 503
        data = resp.get_json()
        assert data["status"] == "unhealthy"

    @patch(
        "routes.system.health._health_check_ollama",
        side_effect=RuntimeError("boom"),
    )
    @patch(
        "routes.system.health._health_check_providers",
        return_value=({"providers": "healthy"}, None),
    )
    @patch(
        "routes.system.health._health_check_sonarr",
        return_value=({"sonarr": "not configured"}, None),
    )
    @patch(
        "routes.system.health._health_check_radarr",
        return_value=({"radarr": "not configured"}, None),
    )
    @patch(
        "routes.system.health._health_check_media_servers",
        return_value=({"media_servers": "none configured"}, None),
    )
    def test_health_handles_check_exception_gracefully(self, _ms, _rad, _son, _prov, _oll, client):
        """If a health check callable raises, the endpoint should still respond."""
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200  # exception → treated as error entry, not crash
        data = resp.get_json()
        assert data["status"] in ("healthy", "unhealthy")

    @patch(
        "routes.system.health._health_check_providers",
        return_value=({"providers": "healthy"}, None),
    )
    @patch(
        "routes.system.health._health_check_sonarr",
        return_value=({"sonarr": "not configured"}, None),
    )
    @patch(
        "routes.system.health._health_check_radarr",
        return_value=({"radarr": "not configured"}, None),
    )
    @patch(
        "routes.system.health._health_check_media_servers",
        return_value=({"media_servers": "none configured"}, None),
    )
    def test_health_does_not_stall_on_hung_optional_check(
        self, _ms, _rad, _son, _prov, client, monkeypatch
    ):
        """A hung optional dependency must not stall the liveness probe.

        Regression for the prod incident where `ollama_url` pointed at an
        unreachable host: `_health_check_ollama` blocked ~10s, pushing /health
        past the 10s Docker healthcheck timeout and flapping the container to
        `unhealthy`. The gather is now budgeted; the straggler is reported as a
        `timeout` entry (informational — never fails the probe).
        """
        import routes.system.health as _mod

        def _hang():
            time.sleep(30)  # far beyond the liveness budget
            return ({"ollama": "ok"}, None)

        monkeypatch.setattr(_mod, "_health_check_ollama", _hang)
        monkeypatch.setattr(_mod, "_HEALTH_LIVENESS_BUDGET_S", 0.5)

        started = time.monotonic()
        resp = client.get("/api/v1/health")
        elapsed = time.monotonic() - started

        assert resp.status_code == 200  # hung optional check ≠ unhealthy
        assert elapsed < 5  # returned on the budget, not after the 30s hang
        data = resp.get_json()
        assert data["status"] == "healthy"
        assert data["services"]["ollama"] == "timeout"


# ───────────────────────────────────────────────────────────────────────────────
# Individual health-check helpers
# ───────────────────────────────────────────────────────────────────────────────


class TestHealthCheckOllama:
    @patch(
        "ollama_client.check_ollama_health",
        return_value=(True, "model loaded"),
    )
    def test_returns_message(self, _mock):
        from routes.system.health import _health_check_ollama

        result, overall = _health_check_ollama()
        assert result == {"ollama": "model loaded"}
        assert overall is None  # informational only


class TestHealthCheckProviders:
    def test_no_providers(self, app_ctx):
        manager = MagicMock()
        manager.get_provider_status.return_value = []
        with patch("providers.get_provider_manager", return_value=manager):
            from routes.system.health import _health_check_providers

            result, overall = _health_check_providers()
            assert result == {"providers": "healthy"}
            assert overall is None

    def test_all_providers_healthy(self, app_ctx):
        manager = MagicMock()
        manager.get_provider_status.return_value = [
            {"name": "a", "enabled": True, "healthy": True},
            {"name": "b", "enabled": True, "healthy": True},
        ]
        with patch("providers.get_provider_manager", return_value=manager):
            from routes.system.health import _health_check_providers

            result, overall = _health_check_providers()
            assert "healthy (2/2 active)" in result["providers"]

    def test_mixed_providers(self, app_ctx):
        manager = MagicMock()
        manager.get_provider_status.return_value = [
            {"name": "a", "enabled": True, "healthy": True},
            {"name": "b", "enabled": True, "healthy": False},
        ]
        with patch("providers.get_provider_manager", return_value=manager):
            from routes.system.health import _health_check_providers

            result, overall = _health_check_providers()
            assert "degraded (1/2 active)" in result["providers"]

    def test_all_providers_error(self, app_ctx):
        manager = MagicMock()
        manager.get_provider_status.return_value = [
            {"name": "a", "enabled": True, "healthy": False},
        ]
        with patch("providers.get_provider_manager", return_value=manager):
            from routes.system.health import _health_check_providers

            result, overall = _health_check_providers()
            assert "error (0/1 active)" in result["providers"]

    def test_exception_returns_error(self, app_ctx):
        with patch(
            "providers.get_provider_manager",
            side_effect=RuntimeError("fail"),
        ):
            from routes.system.health import _health_check_providers

            result, overall = _health_check_providers()
            assert result == {"providers": "error"}


class TestHealthCheckSonarr:
    def test_healthy_sonarr(self):
        mock_client = MagicMock()
        mock_client.health_check.return_value = (True, "connected")
        with patch(
            "sonarr_client.get_sonarr_client",
            return_value=mock_client,
        ):
            from routes.system.health import _health_check_sonarr

            result, overall = _health_check_sonarr()
            assert result == {"sonarr": "connected"}

    def test_unhealthy_sonarr(self):
        mock_client = MagicMock()
        mock_client.health_check.return_value = (False, "timeout")
        with patch(
            "sonarr_client.get_sonarr_client",
            return_value=mock_client,
        ):
            from routes.system.health import _health_check_sonarr

            result, overall = _health_check_sonarr()
            assert result == {"sonarr": "unhealthy: timeout"}

    def test_not_configured(self):
        with patch(
            "sonarr_client.get_sonarr_client",
            return_value=None,
        ):
            from routes.system.health import _health_check_sonarr

            result, overall = _health_check_sonarr()
            assert result == {"sonarr": "not configured"}

    def test_exception_returns_error(self):
        with patch(
            "sonarr_client.get_sonarr_client",
            side_effect=RuntimeError("fail"),
        ):
            from routes.system.health import _health_check_sonarr

            result, overall = _health_check_sonarr()
            assert result == {"sonarr": "error"}


class TestHealthCheckRadarr:
    def test_healthy_radarr(self):
        mock_client = MagicMock()
        mock_client.health_check.return_value = (True, "connected")
        with patch(
            "radarr_client.get_radarr_client",
            return_value=mock_client,
        ):
            from routes.system.health import _health_check_radarr

            result, overall = _health_check_radarr()
            assert result == {"radarr": "connected"}

    def test_unhealthy_radarr(self):
        mock_client = MagicMock()
        mock_client.health_check.return_value = (False, "refused")
        with patch(
            "radarr_client.get_radarr_client",
            return_value=mock_client,
        ):
            from routes.system.health import _health_check_radarr

            result, overall = _health_check_radarr()
            assert result == {"radarr": "unhealthy: refused"}

    def test_not_configured(self):
        with patch(
            "radarr_client.get_radarr_client",
            return_value=None,
        ):
            from routes.system.health import _health_check_radarr

            result, overall = _health_check_radarr()
            assert result == {"radarr": "not configured"}


class TestHealthCheckMediaServers:
    def test_healthy_servers(self):
        manager = MagicMock()
        manager.health_check_all.return_value = [
            {"name": "plex", "healthy": True, "message": "ok"},
        ]
        with patch(
            "mediaserver.get_media_server_manager",
            return_value=manager,
        ):
            from routes.system.health import _health_check_media_servers

            result, overall = _health_check_media_servers()
            assert result["media_servers"] == "1/1 healthy"
            assert result["media_server:plex"] == "ok"

    def test_mixed_servers(self):
        manager = MagicMock()
        manager.health_check_all.return_value = [
            {"name": "plex", "healthy": True, "message": "ok"},
            {"name": "jellyfin", "healthy": False, "message": "timeout"},
        ]
        with patch(
            "mediaserver.get_media_server_manager",
            return_value=manager,
        ):
            from routes.system.health import _health_check_media_servers

            result, overall = _health_check_media_servers()
            assert result["media_servers"] == "1/2 healthy"
            assert result["media_server:jellyfin"] == "unhealthy: timeout"

    def test_none_configured(self):
        manager = MagicMock()
        manager.health_check_all.return_value = []
        with patch(
            "mediaserver.get_media_server_manager",
            return_value=manager,
        ):
            from routes.system.health import _health_check_media_servers

            result, overall = _health_check_media_servers()
            assert result == {"media_servers": "none configured"}

    def test_exception_returns_error(self):
        with patch(
            "mediaserver.get_media_server_manager",
            side_effect=RuntimeError("fail"),
        ):
            from routes.system.health import _health_check_media_servers

            result, overall = _health_check_media_servers()
            assert result == {"media_servers": "error"}


# ───────────────────────────────────────────────────────────────────────────────
# GET /api/v1/update
# ───────────────────────────────────────────────────────────────────────────────


class TestUpdateEndpoint:
    """Update check via GitHub releases."""

    @patch("requests.get")
    def test_update_available(self, mock_get, client):
        """When GitHub reports a newer version, available=True."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "tag_name": "v99.0.0",
            "html_url": "https://github.com/Abrechen2/sublarr/releases/tag/v99.0.0",
            "prerelease": False,
        }
        mock_get.return_value = mock_resp

        resp = client.get("/api/v1/update")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["available"] is True
        assert data["latest"] == "v99.0.0"
        assert data["url"] is not None

    @patch("requests.get")
    def test_no_update_available(self, mock_get, client):
        """When current version matches or exceeds GitHub, available=False."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "tag_name": "v0.0.1",
            "html_url": "https://github.com/Abrechen2/sublarr/releases/tag/v0.0.1",
            "prerelease": False,
        }
        mock_get.return_value = mock_resp

        resp = client.get("/api/v1/update")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["available"] is False

    @patch("requests.get")
    def test_github_api_error_returns_fallback(self, mock_get, client):
        """Non-200 from GitHub returns fallback (available=False)."""
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_get.return_value = mock_resp

        resp = client.get("/api/v1/update")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["available"] is False
        assert data["latest"] is None

    @patch("requests.get")
    def test_github_network_error_returns_fallback(self, mock_get, client):
        """Network exception returns fallback (available=False)."""
        mock_get.side_effect = ConnectionError("network down")

        resp = client.get("/api/v1/update")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["available"] is False

    @patch("requests.get")
    def test_prerelease_skipped(self, mock_get, client):
        """If latest release is a prerelease, return fallback."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "tag_name": "v99.0.0-rc1",
            "html_url": "https://github.com/Abrechen2/sublarr/releases/tag/v99.0.0-rc1",
            "prerelease": True,
        }
        mock_get.return_value = mock_resp

        resp = client.get("/api/v1/update")
        data = resp.get_json()
        assert data["available"] is False
        assert data["latest"] is None

    @patch("requests.get")
    def test_cache_is_used_on_second_call(self, mock_get, client):
        """Second call within TTL should not hit GitHub again."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "tag_name": "v99.0.0",
            "html_url": "https://github.com/example/releases/tag/v99.0.0",
            "prerelease": False,
        }
        mock_get.return_value = mock_resp

        # First call — hits GitHub
        client.get("/api/v1/update")
        assert mock_get.call_count == 1

        # Second call — should use cache
        resp2 = client.get("/api/v1/update")
        assert mock_get.call_count == 1
        data = resp2.get_json()
        assert data["available"] is True

    @patch("requests.get")
    def test_cache_expires_after_ttl(self, mock_get, client):
        """After TTL, the cache should be bypassed."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "tag_name": "v99.0.0",
            "html_url": "https://example.com",
            "prerelease": False,
        }
        mock_get.return_value = mock_resp

        # First call
        client.get("/api/v1/update")

        # Expire the cache by backdating checked_at
        from routes.system import health as _mod

        _mod._update_cache["checked_at"] = time.time() - 7 * 3600  # 7 hours ago

        # Second call — should hit GitHub again
        client.get("/api/v1/update")
        assert mock_get.call_count == 2


# ───────────────────────────────────────────────────────────────────────────────
# GET /api/v1/health/detailed
# ───────────────────────────────────────────────────────────────────────────────

# All imports in health_detailed() happen inside the function body via
# `from X import Y`, so we must patch at the SOURCE module, not at
# `routes.system.health`.

# Source module → attribute mapping for the detailed endpoint:
_DETAILED_PATCHES = {
    "database_health.get_health_report": None,
    "ollama_client.check_ollama_health": None,
    "providers.get_provider_manager": None,
    "mediaserver.get_media_server_manager": None,
    "translation.get_translation_manager": None,
    "db.config.get_config_entry": None,
    "config.get_sonarr_instances": None,
    "config.get_radarr_instances": None,
    "services.wanted_scanner.get_scanner": None,
}


def _make_detailed_patches(**overrides):
    """Build a list of (target, mock) tuples for ExitStack patching.

    Returns a list of `patch` context managers ready to enter.
    """
    defaults = {
        "database_health.get_health_report": MagicMock(
            return_value={
                "status": "healthy",
                "backend": "sqlite",
                "details": {
                    "integrity": {"message": "ok"},
                    "size_bytes": 1024,
                    "wal_mode": True,
                },
            }
        ),
        "ollama_client.check_ollama_health": MagicMock(
            return_value=(True, "model loaded"),
        ),
        "providers.get_provider_manager": MagicMock(
            return_value=MagicMock(_circuit_breakers={}),
        ),
        "mediaserver.get_media_server_manager": MagicMock(
            return_value=MagicMock(health_check_all=MagicMock(return_value=[])),
        ),
        "translation.get_translation_manager": MagicMock(
            return_value=MagicMock(get_all_backends=MagicMock(return_value=[])),
        ),
        "db.config.get_config_entry": MagicMock(return_value="false"),
        "config.get_sonarr_instances": MagicMock(return_value=[]),
        "config.get_radarr_instances": MagicMock(return_value=[]),
        "services.wanted_scanner.get_scanner": MagicMock(
            return_value=MagicMock(
                is_scanning=False,
                is_searching=False,
                last_scan_at=None,
                last_search_at=None,
            ),
        ),
    }
    defaults.update(overrides)
    return defaults


def _apply_patches(patch_dict):
    """Return a contextlib.ExitStack-like nesting of patch() calls."""
    from contextlib import ExitStack

    stack = ExitStack()
    for target, mock_obj in patch_dict.items():
        stack.enter_context(patch(target, mock_obj))
    return stack


class TestHealthDetailedEndpoint:
    """Detailed health check — authenticated, subsystem-level reporting."""

    def test_detailed_healthy(self, client):
        patches = _make_detailed_patches()
        with _apply_patches(patches):
            resp = client.get("/api/v1/health/detailed")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "healthy"
        assert "subsystems" in data
        subs = data["subsystems"]
        assert subs["database"]["healthy"] is True
        assert subs["ollama"]["healthy"] is True

    def test_detailed_db_unhealthy(self, client):
        patches = _make_detailed_patches(
            **{
                "database_health.get_health_report": MagicMock(
                    return_value={
                        "status": "unhealthy",
                        "backend": "sqlite",
                        "details": {
                            "integrity": {"message": "corruption detected"},
                            "size_bytes": 0,
                            "wal_mode": False,
                        },
                    }
                ),
            }
        )
        with _apply_patches(patches):
            resp = client.get("/api/v1/health/detailed")
        assert resp.status_code == 503
        data = resp.get_json()
        assert data["status"] == "degraded"
        assert data["subsystems"]["database"]["healthy"] is False

    def test_detailed_db_exception(self, client):
        patches = _make_detailed_patches(
            **{
                "database_health.get_health_report": MagicMock(
                    side_effect=RuntimeError("db gone"),
                ),
            }
        )
        with _apply_patches(patches):
            resp = client.get("/api/v1/health/detailed")
        assert resp.status_code == 503
        data = resp.get_json()
        assert data["subsystems"]["database"]["healthy"] is False
        assert "db gone" in data["subsystems"]["database"]["message"]

    def test_detailed_ollama_unhealthy(self, client):
        patches = _make_detailed_patches(
            **{
                "ollama_client.check_ollama_health": MagicMock(
                    return_value=(False, "connection refused"),
                ),
            }
        )
        with _apply_patches(patches):
            resp = client.get("/api/v1/health/detailed")
        assert resp.status_code == 503
        data = resp.get_json()
        assert data["subsystems"]["ollama"]["healthy"] is False

    def test_detailed_ollama_exception(self, client):
        patches = _make_detailed_patches(
            **{
                "ollama_client.check_ollama_health": MagicMock(
                    side_effect=RuntimeError("import fail"),
                ),
            }
        )
        with _apply_patches(patches):
            resp = client.get("/api/v1/health/detailed")
        data = resp.get_json()
        assert data["subsystems"]["ollama"]["healthy"] is False

    def test_detailed_providers_with_circuit_breakers(self, client):
        cb_mock = MagicMock()
        cb_mock.get_status.return_value = {"state": "closed", "failure_count": 0}
        manager_mock = MagicMock(_circuit_breakers={"opensubtitles": cb_mock})

        patches = _make_detailed_patches(
            **{
                "providers.get_provider_manager": MagicMock(return_value=manager_mock),
            }
        )
        with _apply_patches(patches):
            resp = client.get("/api/v1/health/detailed")
        data = resp.get_json()
        providers = data["subsystems"]["providers"]
        assert providers["healthy"] is True
        assert len(providers["details"]) == 1
        assert providers["details"][0]["circuit_breaker"] == "closed"

    def test_detailed_providers_open_breaker(self, client):
        cb_mock = MagicMock()
        cb_mock.get_status.return_value = {"state": "open", "failure_count": 5}
        manager_mock = MagicMock(_circuit_breakers={"opensubtitles": cb_mock})

        patches = _make_detailed_patches(
            **{
                "providers.get_provider_manager": MagicMock(return_value=manager_mock),
            }
        )
        with _apply_patches(patches):
            resp = client.get("/api/v1/health/detailed")
        data = resp.get_json()
        assert data["subsystems"]["providers"]["healthy"] is False

    def test_detailed_translation_backends_configured(self, client):
        backend_mock = MagicMock()
        backend_mock.health_check.return_value = (True, "ready")
        tm_mock = MagicMock()
        tm_mock.get_all_backends.return_value = [{"name": "ollama", "configured": True}]
        tm_mock.get_backend.return_value = backend_mock

        patches = _make_detailed_patches(
            **{
                "translation.get_translation_manager": MagicMock(return_value=tm_mock),
            }
        )
        with _apply_patches(patches):
            resp = client.get("/api/v1/health/detailed")
        data = resp.get_json()
        tb = data["subsystems"]["translation_backends"]
        assert tb["healthy"] is True
        assert tb["backends"]["ollama"]["healthy"] is True

    def test_detailed_translation_backends_not_configured(self, client):
        tm_mock = MagicMock()
        tm_mock.get_all_backends.return_value = [{"name": "deepl", "configured": False}]

        patches = _make_detailed_patches(
            **{
                "translation.get_translation_manager": MagicMock(return_value=tm_mock),
            }
        )
        with _apply_patches(patches):
            resp = client.get("/api/v1/health/detailed")
        data = resp.get_json()
        tb = data["subsystems"]["translation_backends"]
        assert tb["backends"]["deepl"]["message"] == "Not configured"

    def test_detailed_whisper_disabled(self, client):
        patches = _make_detailed_patches(
            **{
                "db.config.get_config_entry": MagicMock(return_value="false"),
            }
        )
        with _apply_patches(patches):
            resp = client.get("/api/v1/health/detailed")
        data = resp.get_json()
        wb = data["subsystems"]["whisper_backends"]
        assert wb["healthy"] is True
        assert wb["message"] == "Whisper disabled"

    def test_detailed_whisper_enabled_with_backend(self, client):
        active_backend = MagicMock()
        active_backend.name = "faster-whisper"
        active_backend.health_check.return_value = (True, "model loaded")
        wm_mock = MagicMock()
        wm_mock.get_active_backend.return_value = active_backend

        # Only return "true" for whisper_enabled; return None for everything
        # else (ui_auth uses get_config_entry too — "true" would trigger auth).
        def _config_entry_side_effect(key, *args, **kwargs):
            if key == "whisper_enabled":
                return "true"
            return None

        patches = _make_detailed_patches(
            **{
                "db.config.get_config_entry": MagicMock(side_effect=_config_entry_side_effect),
                "whisper.get_whisper_manager": MagicMock(return_value=wm_mock),
            }
        )
        with _apply_patches(patches):
            resp = client.get("/api/v1/health/detailed")
        data = resp.get_json()
        wb = data["subsystems"]["whisper_backends"]
        assert wb["healthy"] is True
        assert wb["active_backend"] == "faster-whisper"

    def test_detailed_whisper_enabled_no_active_backend(self, client):
        wm_mock = MagicMock()
        wm_mock.get_active_backend.return_value = None

        def _config_entry_side_effect(key, *args, **kwargs):
            if key == "whisper_enabled":
                return "true"
            return None

        patches = _make_detailed_patches(
            **{
                "db.config.get_config_entry": MagicMock(side_effect=_config_entry_side_effect),
                "whisper.get_whisper_manager": MagicMock(return_value=wm_mock),
            }
        )
        with _apply_patches(patches):
            resp = client.get("/api/v1/health/detailed")
        data = resp.get_json()
        wb = data["subsystems"]["whisper_backends"]
        assert wb["healthy"] is True
        assert wb["active_backend"] is None

    def test_detailed_arr_connectivity_healthy(self, client):
        sonarr_client = MagicMock()
        sonarr_client.health_check.return_value = (True, "ok")
        radarr_client = MagicMock()
        radarr_client.health_check.return_value = (True, "ok")

        patches = _make_detailed_patches(
            **{
                "config.get_sonarr_instances": MagicMock(
                    return_value=[{"name": "Default"}],
                ),
                "config.get_radarr_instances": MagicMock(
                    return_value=[{"name": "Default"}],
                ),
                "sonarr_client.get_sonarr_client": MagicMock(return_value=sonarr_client),
                "radarr_client.get_radarr_client": MagicMock(return_value=radarr_client),
            }
        )
        with _apply_patches(patches):
            resp = client.get("/api/v1/health/detailed")

        data = resp.get_json()
        arr = data["subsystems"]["arr_connectivity"]
        assert arr["healthy"] is True
        assert len(arr["sonarr"]) == 1
        assert len(arr["radarr"]) == 1

    def test_detailed_arr_no_instances(self, client):
        patches = _make_detailed_patches()
        with _apply_patches(patches):
            resp = client.get("/api/v1/health/detailed")
        data = resp.get_json()
        arr = data["subsystems"]["arr_connectivity"]
        assert arr["healthy"] is True
        assert arr["sonarr"] == []
        assert arr["radarr"] == []

    def test_detailed_scheduler(self, client):
        scanner_mock = MagicMock(
            is_scanning=True,
            is_searching=False,
            last_scan_at="2026-04-12T10:00:00",
            last_search_at=None,
        )

        patches = _make_detailed_patches(
            **{
                "services.wanted_scanner.get_scanner": MagicMock(
                    return_value=scanner_mock,
                ),
            }
        )
        with _apply_patches(patches):
            resp = client.get("/api/v1/health/detailed")
        data = resp.get_json()
        sched = data["subsystems"]["scheduler"]
        assert sched["healthy"] is True
        tasks = {t["name"]: t for t in sched["tasks"]}
        assert tasks["wanted_scan"]["running"] is True
        assert tasks["wanted_search"]["running"] is False
        assert "backup" in tasks

    def test_detailed_media_servers_configured(self, client):
        ms_manager = MagicMock()
        ms_manager.health_check_all.return_value = [
            {"type": "plex", "name": "My Plex", "healthy": True, "message": "ok"},
        ]

        patches = _make_detailed_patches(
            **{
                "mediaserver.get_media_server_manager": MagicMock(
                    return_value=ms_manager,
                ),
            }
        )
        with _apply_patches(patches):
            resp = client.get("/api/v1/health/detailed")
        data = resp.get_json()
        ms = data["subsystems"]["media_servers"]
        assert ms["healthy"] is True
        assert len(ms["instances"]) == 1

    def test_detailed_media_servers_unhealthy(self, client):
        ms_manager = MagicMock()
        ms_manager.health_check_all.return_value = [
            {"type": "jellyfin", "name": "J1", "healthy": False, "message": "timeout"},
        ]

        patches = _make_detailed_patches(
            **{
                "mediaserver.get_media_server_manager": MagicMock(
                    return_value=ms_manager,
                ),
            }
        )
        with _apply_patches(patches):
            resp = client.get("/api/v1/health/detailed")
        assert resp.status_code == 503
        data = resp.get_json()
        assert data["subsystems"]["media_servers"]["healthy"] is False


class TestHealthProviderCountRegression:
    """Phase 4a follow-up: dashboard 'Providers: degraded (10/22 active)' mismatch.

    `_health_check_providers` used to pass `len(provider_statuses)` as `total`,
    which counts every registered class (including plugins the user hasn't
    configured). The correct denominator is the count of *enabled* providers.
    """

    def test_counts_only_enabled_providers(self, monkeypatch):
        from routes.system import health as health_mod

        # 22 registered — 10 enabled, 10 healthy among enabled.
        statuses = [{"enabled": True, "healthy": True} for _ in range(10)] + [
            {"enabled": False, "healthy": False} for _ in range(12)
        ]
        mgr = type("M", (), {"get_provider_status": lambda self: statuses})()
        monkeypatch.setattr("providers.get_provider_manager", lambda: mgr)
        payload, err = health_mod._health_check_providers(app=None)
        assert err is None
        assert payload == {"providers": "healthy (10/10 active)"}

    def test_partially_degraded(self, monkeypatch):
        from routes.system import health as health_mod

        statuses = [
            {"enabled": True, "healthy": True},
            {"enabled": True, "healthy": False},
            {"enabled": False, "healthy": False},  # should be ignored
        ]
        mgr = type("M", (), {"get_provider_status": lambda self: statuses})()
        monkeypatch.setattr("providers.get_provider_manager", lambda: mgr)
        payload, _ = health_mod._health_check_providers(app=None)
        assert payload == {"providers": "degraded (1/2 active)"}

    def test_zero_enabled_returns_healthy(self, monkeypatch):
        from routes.system import health as health_mod

        statuses = [{"enabled": False, "healthy": False} for _ in range(5)]
        mgr = type("M", (), {"get_provider_status": lambda self: statuses})()
        monkeypatch.setattr("providers.get_provider_manager", lambda: mgr)
        payload, _ = health_mod._health_check_providers(app=None)
        assert payload == {"providers": "healthy"}
