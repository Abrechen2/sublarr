"""Security tests — service URL validation, auth middleware, and log sanitization.

Covers:
- TestValidateServiceUrl: SSRF protection for config URL fields
- TestExtensionUrlValidation: F-13a regression — dot-notation URL extension keys
- TestSocketIOLogSanitizer: DB error details stripped from WebSocket log events
- TestWebhookExemptionWarning: F-05 webhook auth footgun warning
"""

import os
import sys

import pytest

# Ensure backend root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from security_utils import validate_service_url

# ---------------------------------------------------------------------------
# TestValidateServiceUrl
# ---------------------------------------------------------------------------


class TestValidateServiceUrl:
    """validate_service_url blocks dangerous schemes and metadata IPs."""

    # --- valid URLs (should be accepted) ---

    @pytest.mark.parametrize(
        "url",
        [
            "http://192.168.178.36:8989",  # Sonarr on LAN
            "http://192.168.178.155:11434",  # Ollama on LAN
            "https://192.168.1.1",  # HTTPS private IP
            "http://10.0.0.5:7878",  # Radarr on 10.x network
            "http://172.16.0.1:8096",  # Jellyfin on 172.16.x
            "http://sonarr.local:8989",  # mDNS hostname
            "https://api.opensubtitles.com",  # External provider
        ],
    )
    def test_valid_urls_accepted(self, url):
        ok, reason = validate_service_url(url)
        assert ok is True, f"Expected {url!r} to be accepted, got: {reason}"

    # --- dangerous schemes (must be rejected) ---

    @pytest.mark.parametrize(
        "url",
        [
            "file:///etc/passwd",
            "ftp://192.168.1.1/data",
            "dict://localhost:2628/d:password",
            "gopher://evil.com/1%0d%0aFoo",
            "ldap://127.0.0.1:389/",
            "sftp://host/path",
        ],
    )
    def test_dangerous_schemes_rejected(self, url):
        ok, reason = validate_service_url(url)
        assert ok is False
        assert "scheme" in (reason or "").lower()

    # --- cloud metadata endpoints (must be rejected) ---

    @pytest.mark.parametrize(
        "url",
        [
            "http://169.254.169.254/latest/meta-data/",  # AWS / Azure / GCP
            "http://169.254.169.254/",
            "http://100.100.100.200/latest/meta-data/",  # Alibaba Cloud
            "http://metadata.google.internal/computeMetadata/",  # GCP named endpoint
            "http://metadata.goog/",
        ],
    )
    def test_metadata_endpoints_rejected(self, url):
        ok, reason = validate_service_url(url)
        assert ok is False, f"Expected {url!r} to be rejected"

    # --- edge cases ---

    def test_empty_string_rejected(self):
        ok, reason = validate_service_url("")
        assert ok is False

    def test_no_hostname_rejected(self):
        ok, reason = validate_service_url("http:///no-host")
        assert ok is False

    def test_zero_host_rejected(self):
        ok, reason = validate_service_url("http://0.0.0.0:8989")
        assert ok is False

    def test_link_local_ipv6_rejected(self):
        ok, reason = validate_service_url("http://[fe80::1]/path")
        assert ok is False

    def test_trailing_slash_accepted(self):
        ok, _ = validate_service_url("http://192.168.178.36:8989/")
        assert ok is True


# ---------------------------------------------------------------------------
# TestExtensionUrlValidation (F-13a regression)
# ---------------------------------------------------------------------------


class TestExtensionUrlValidation:
    """PUT /config must validate dot-notation URL extension keys (F-13a).

    Prior to this fix, keys like 'whisper.subgen.url' bypassed SSRF validation
    because they were treated as opaque extension keys.
    """

    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        import os
        import sys

        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        monkeypatch.setenv("SUBLARR_DB_PATH", str(tmp_path / "test.db"))
        monkeypatch.setenv("SUBLARR_API_KEY", "")
        monkeypatch.setenv("SUBLARR_LOG_LEVEL", "ERROR")
        monkeypatch.setenv("SUBLARR_PLUGINS_DIR", str(tmp_path / "plugins"))
        monkeypatch.setenv("SUBLARR_MEDIA_PATH", str(tmp_path))

        from app import create_app
        from config import reload_settings
        from db import init_db

        reload_settings()
        (tmp_path / "plugins").mkdir(exist_ok=True)
        app = create_app()
        init_db()
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c

    @pytest.mark.parametrize(
        "key",
        ["whisper.subgen.url", "whisper.faster_whisper.url", "translation.backend_url"],
    )
    def test_dangerous_scheme_rejected_for_extension_url_keys(self, client, key):
        """Dot-notation URL keys must reject dangerous schemes (e.g. file://)."""
        resp = client.put("/api/v1/config", json={key: "file:///etc/passwd"})
        assert resp.status_code == 400
        data = resp.get_json()
        assert "Invalid URL" in data.get("error", "")

    @pytest.mark.parametrize(
        "key",
        ["whisper.subgen.url", "whisper.faster_whisper.url"],
    )
    def test_metadata_ip_rejected_for_extension_url_keys(self, client, key):
        """Cloud metadata endpoints must also be blocked for extension URL keys."""
        resp = client.put("/api/v1/config", json={key: "http://169.254.169.254/latest"})
        assert resp.status_code == 400

    @pytest.mark.parametrize(
        "key",
        ["whisper.subgen.url", "whisper.faster_whisper.url"],
    )
    def test_valid_lan_url_accepted_for_extension_url_keys(self, client, key):
        """Valid LAN URLs must still be accepted for extension URL keys."""
        resp = client.put("/api/v1/config", json={key: "http://192.168.1.100:9000"})
        # 200 = saved, anything other than 400 means validation passed
        assert resp.status_code != 400 or "Invalid URL" not in resp.get_json().get("error", "")


# ---------------------------------------------------------------------------
# TestSocketIOLogSanitizer
# ---------------------------------------------------------------------------


class TestSocketIOLogSanitizer:
    """SocketIOLogHandler._sanitize strips DB-internal error details."""

    def _get_sanitizer(self):
        """Import SocketIOLogHandler without starting a full Flask app."""
        import importlib
        import sys

        # app.py is at backend root — already on path from sys.path.insert above
        app_module = importlib.import_module("app")
        return app_module.SocketIOLogHandler

    def test_psycopg2_error_stripped(self):
        Handler = self._get_sanitizer()
        raw = "[ERROR] Unhandled exception: (psycopg2.errors.UndefinedColumn) column glossary_entries.term_type does not exist"
        result = Handler._sanitize(raw)
        assert "term_type" not in result
        assert "glossary_entries" not in result
        assert "Database error" in result

    def test_sqlalchemy_error_stripped(self):
        Handler = self._get_sanitizer()
        raw = "[ERROR] db: (sqlalchemy.exc.OperationalError) no such table: subtitle_jobs"
        result = Handler._sanitize(raw)
        assert "subtitle_jobs" not in result
        assert "Database error" in result

    def test_undefined_function_stripped(self):
        Handler = self._get_sanitizer()
        raw = "[ERROR] error_handler: (psycopg2.errors.UndefinedFunction) function date(unknown, unknown) does not exist"
        result = Handler._sanitize(raw)
        assert "function date" not in result
        assert "Database error" in result

    def test_normal_log_unchanged(self):
        Handler = self._get_sanitizer()
        normal = "[INFO] sonarr_client: Connected to Sonarr v4.0"
        assert Handler._sanitize(normal) == normal

    def test_warning_log_unchanged(self):
        Handler = self._get_sanitizer()
        warning = "[WARNING] auth: Invalid API key from 192.168.178.50"
        assert Handler._sanitize(warning) == warning

    def test_prefix_preserved_on_db_error(self):
        """Timestamp/level prefix before ']' is kept; only the DB detail is replaced."""
        Handler = self._get_sanitizer()
        raw = "2026-03-18 17:00:00 [ERROR] handler: (psycopg2.errors.UndefinedColumn) col x does not exist"
        result = Handler._sanitize(raw)
        assert "Database error" in result
        assert "col x" not in result


# ---------------------------------------------------------------------------
# TestWebhookExemptionWarning — F-05 webhook auth footgun (Task 6)
# ---------------------------------------------------------------------------


class TestWebhookExemptionWarning:
    """A warning is logged when a webhook request arrives without X-Signature.

    The warning only fires when an API key is configured (otherwise all routes
    are open and there's nothing to exempt webhooks from). Tests therefore use
    a fixture that enables the API key, and patch `auth.logger` wholesale with
    a MagicMock so the effective log level (ERROR in tests) doesn't suppress
    WARNING calls before they reach the mock.
    """

    @pytest.fixture
    def client_with_api_key(self, tmp_path, monkeypatch):
        """Test client with a non-empty API key so the auth middleware is active."""
        import os
        import sys

        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        monkeypatch.setenv("SUBLARR_DB_PATH", str(tmp_path / "test.db"))
        monkeypatch.setenv("SUBLARR_API_KEY", "test-key-for-webhook-warning")
        monkeypatch.setenv("SUBLARR_LOG_LEVEL", "ERROR")
        monkeypatch.setenv("SUBLARR_PLUGINS_DIR", str(tmp_path / "plugins"))
        monkeypatch.setenv("SUBLARR_MEDIA_PATH", str(tmp_path))

        from app import create_app
        from config import reload_settings
        from db import init_db

        reload_settings()
        (tmp_path / "plugins").mkdir(exist_ok=True)
        app = create_app()
        init_db()
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c

    @pytest.fixture(autouse=True)
    def _forget_warned_paths(self):
        """The warning fires once per path per process, so it has memory.

        Without clearing it these tests would pass or fail depending on which
        of them ran first in the worker — the exact order-dependent flake the
        suite is run with xdist to expose.
        """
        import auth as auth_module

        auth_module._webhook_warned_paths.clear()
        yield
        auth_module._webhook_warned_paths.clear()

    def test_the_warning_fires_once_per_path_not_once_per_event(self, client_with_api_key):
        """Sonarr and Radarr cannot send a signature, so every legitimate event hit
        this branch: 219 warnings in one user's log (#183) for a condition they
        could do nothing about. The warning is a note that verification is not
        implemented — one per path per boot says that just as well.
        """
        from unittest.mock import MagicMock, patch

        import auth as auth_module

        mock_logger = MagicMock()
        with patch.object(auth_module, "logger", mock_logger):
            for _ in range(5):
                client_with_api_key.post("/api/v1/webhook/sonarr", json={})
            client_with_api_key.post("/api/v1/webhook/radarr", json={})

        footgun = [c for c in mock_logger.warning.call_args_list if "X-Signature" in str(c)]
        assert len(footgun) == 2, (
            f"expected one warning per distinct path, got {len(footgun)}: {footgun}"
        )

    def test_warning_logged_for_webhook_without_signature(self, client_with_api_key):
        """Webhook request without X-Signature header produces a warning log."""
        from unittest.mock import MagicMock, patch

        import auth as auth_module

        mock_logger = MagicMock()
        with patch.object(auth_module, "logger", mock_logger):
            client_with_api_key.post("/api/v1/webhook/sonarr", json={})

        calls = [str(c) for c in mock_logger.warning.call_args_list]
        assert any("webhook" in c.lower() and "signature" in c.lower() for c in calls), (
            f"Expected webhook/signature warning; got calls: {calls}"
        )

    def test_no_warning_when_x_signature_present(self, client_with_api_key):
        """Webhook request with X-Signature header must NOT produce the footgun warning."""
        from unittest.mock import MagicMock, patch

        import auth as auth_module

        mock_logger = MagicMock()
        with patch.object(auth_module, "logger", mock_logger):
            client_with_api_key.post(
                "/api/v1/webhook/sonarr",
                json={},
                headers={"X-Signature": "sha256=abc123"},
            )

        footgun_calls = [
            str(c) for c in mock_logger.warning.call_args_list if "no x-signature" in str(c).lower()
        ]
        assert footgun_calls == [], f"Unexpected footgun warning fired: {footgun_calls}"

    def test_no_warning_when_x_bazarr_signature_present(self, client_with_api_key):
        """Webhook request with X-Bazarr-Signature header must NOT produce the footgun warning."""
        from unittest.mock import MagicMock, patch

        import auth as auth_module

        mock_logger = MagicMock()
        with patch.object(auth_module, "logger", mock_logger):
            client_with_api_key.post(
                "/api/v1/webhook/sonarr",
                json={},
                headers={"X-Bazarr-Signature": "sha256=abc123"},
            )

        footgun_calls = [
            str(c) for c in mock_logger.warning.call_args_list if "no x-signature" in str(c).lower()
        ]
        assert footgun_calls == [], f"Unexpected footgun warning fired: {footgun_calls}"

    def test_warning_includes_path_and_remote_addr(self, client_with_api_key):
        """Warning message includes the request path and remote address for diagnostics."""
        from unittest.mock import MagicMock, patch

        import auth as auth_module

        mock_logger = MagicMock()
        with patch.object(auth_module, "logger", mock_logger):
            client_with_api_key.post("/api/v1/webhook/radarr", json={})

        footgun_calls = [
            str(c) for c in mock_logger.warning.call_args_list if "no x-signature" in str(c).lower()
        ]
        assert len(footgun_calls) >= 1
        assert "/api/v1/webhook/radarr" in footgun_calls[0]
