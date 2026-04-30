"""Regression tests for the 2026-04-30 Health / Diagnostics audit.

Pins:
- /api/v1/health rate-limited at 60/minute (was unlimited; auth-exempt
  endpoint that triggers 5 outbound probes per call to internal
  Sonarr/Radarr/Plex/Jellyfin/Ollama, so unbounded calls = DoS
  amplification vector against internal services).
- /api/v1/update rate-limited at 10/minute (was unlimited; outbound
  GitHub call when cache expires).
- /api/v1/health hides ``services`` (which can leak internal URLs in
  error messages like "Cannot connect to Sonarr at
  http://192.168.1.10:8989") from unauthenticated callers when ANY
  auth is configured. Pre-fix the gate ignored ui_auth_enabled — the
  same auth-layer-composition bug as /auth/bootstrap (commit 31fd83e7).
"""

from __future__ import annotations

from unittest.mock import patch

# ---------------------------------------------------------------------------
# auth-layer composition: services hidden when ui_auth is on but api_key empty
# ---------------------------------------------------------------------------


class TestHealthAuthLayerComposition:
    """When api_key is unset BUT ui_auth_enabled=True, an unauthenticated
    caller used to be treated as authenticated (because the legacy gate
    only checked api_key) — and saw version + services in the response.
    services can include "Cannot connect to Sonarr at <internal-url>"
    when the upstream is down, which leaks internal topology to anyone
    who can hit /health (init_auth makes /health a public endpoint)."""

    @patch(
        "routes.system.health._health_check_ollama",
        return_value=({"ollama": "ok"}, None),
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
    def test_ui_auth_enabled_no_api_key_hides_services(self, _ms, _rad, _son, _prov, _oll, client):
        """ui_auth_enabled=True + api_key="" + unauthenticated request →
        services must be hidden (was leaking pre-fix)."""
        with patch("ui_auth.is_ui_auth_enabled", return_value=True):
            resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "healthy"
        # Pre-fix BOTH of these would be present.
        assert "services" not in data, data
        assert "version" not in data, data

    @patch(
        "routes.system.health._health_check_ollama",
        return_value=({"ollama": "ok"}, None),
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
    def test_ui_auth_enabled_with_session_exposes_services(
        self, _ms, _rad, _son, _prov, _oll, client
    ):
        """ui_auth_enabled=True + valid session → services exposed (the UI
        dashboard needs them)."""
        with client.session_transaction() as sess:
            sess["ui_authenticated"] = True
        with patch("ui_auth.is_ui_auth_enabled", return_value=True):
            resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "services" in data
        assert "version" in data

    @patch(
        "routes.system.health._health_check_ollama",
        return_value=({"ollama": "ok"}, None),
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
    def test_no_auth_at_all_still_exposes_services(self, _ms, _rad, _son, _prov, _oll, client):
        """The truly-open deployment (no api_key, no UI auth) keeps the
        original "API is open anyway" semantic — version + services
        exposed. Existing test_health_includes_version_and_services_when_no_api_key
        already covers this; pin it explicitly under the new gate too."""
        with patch("ui_auth.is_ui_auth_enabled", return_value=False):
            resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "services" in data
        assert "version" in data


# ---------------------------------------------------------------------------
# Rate limit registration on /health and /update
# ---------------------------------------------------------------------------


class TestHealthRateLimits:
    """Defense-in-depth: /health and /update are auth-exempt and trigger
    outbound side effects (5 internal probes for /health, GitHub API for
    /update). Without rate limits, an attacker can amplify the outbound
    load. Pin the @limiter.limit decorations so they cannot regress."""

    def _decorated_limits_for(self, view_qualname: str):
        """Look up the flask-limiter decorated limits for a view function by
        its callable qualname. flask-limiter stores limits under
        ``module.function.function`` (function name appended), so the
        caller passes ``routes.system.health.health`` and we expand it."""
        from extensions import limiter

        # flask-limiter's internal key format is
        # f"{module_path}.{func_name}.{func_name}".
        key = f"{view_qualname}.{view_qualname.rsplit('.', 1)[-1]}"
        return list(limiter.limit_manager.decorated_limits(key))

    def test_health_endpoint_has_rate_limit_registered(self, client):
        from unittest.mock import patch

        # Disable all probes so the call is cheap; we only care about
        # whether the @limiter.limit decorator is wired up. We verify by
        # introspecting the limiter manager rather than firing 60+ HTTP
        # requests, which would make this test slow and brittle.
        limits = self._decorated_limits_for("routes.system.health.health")
        assert limits, "expected at least one rate limit registered on /health"
        # Prove the *value* is the audit-fix value, not just "any limit".
        rendered = " ".join(str(rl.limit) for rl in limits)
        assert "60" in rendered, rendered

        # Bonus integration smoke: a single call still returns 200, i.e.
        # the limit is wide enough that test runs don't trip it.
        with (
            patch(
                "routes.system.health._health_check_ollama",
                return_value=({"ollama": "ok"}, None),
            ),
            patch(
                "routes.system.health._health_check_providers",
                return_value=({"providers": "healthy"}, None),
            ),
            patch(
                "routes.system.health._health_check_sonarr",
                return_value=({"sonarr": "n/a"}, None),
            ),
            patch(
                "routes.system.health._health_check_radarr",
                return_value=({"radarr": "n/a"}, None),
            ),
            patch(
                "routes.system.health._health_check_media_servers",
                return_value=({"media_servers": "n/a"}, None),
            ),
        ):
            resp = client.get("/api/v1/health")
        assert resp.status_code == 200

    def test_update_endpoint_has_rate_limit_registered(self, client):
        limits = self._decorated_limits_for("routes.system.health.check_update")
        assert limits, "expected at least one rate limit registered on /update"
        rendered = " ".join(str(rl.limit) for rl in limits)
        assert "10" in rendered, rendered
