"""Tests for routes/api_keys.py — API key management endpoints."""

from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# TestMaskValue — pure function, no HTTP
# ---------------------------------------------------------------------------


class TestMaskValue:
    """Tests for the _mask_value() helper."""

    def setup_method(self):
        from routes.api_keys import _mask_value

        self._mask_value = _mask_value

    def test_empty_string_returns_empty(self):
        assert self._mask_value("") == ""

    def test_none_returns_empty(self):
        assert self._mask_value(None) == ""

    def test_short_value_returns_stars(self):
        # Values ≤8 chars → "***"
        assert self._mask_value("abc") == "***"
        assert self._mask_value("12345678") == "***"

    def test_long_value_shows_prefix_and_suffix(self):
        # >8 chars → first4 + "***" + last4
        result = self._mask_value("abcdefghij")
        assert result == "abcd***ghij"

    def test_exactly_9_chars_is_masked(self):
        result = self._mask_value("123456789")
        assert result == "1234***6789"


# ---------------------------------------------------------------------------
# TestListServices — GET /api/v1/api-keys/
# ---------------------------------------------------------------------------


class TestListServices:
    """Tests for GET /api/v1/api-keys/ (list_services endpoint)."""

    def test_returns_all_registered_services(self, client):
        with patch("db.config.get_config_entry", return_value=""):
            resp = client.get("/api/v1/api-keys/")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "services" in data
        service_names = [s["service"] for s in data["services"]]
        assert "sublarr" in service_names
        assert "sonarr" in service_names
        assert "opensubtitles" in service_names

    def test_status_missing_when_no_key_configured(self, client):
        with patch("db.config.get_config_entry", return_value=""):
            resp = client.get("/api/v1/api-keys/")
        data = resp.get_json()
        sublarr_service = next(s for s in data["services"] if s["service"] == "sublarr")
        assert sublarr_service["status"] == "missing"

    def test_status_configured_when_key_is_set(self, client):
        def mock_get_config_entry(key):
            if key == "api_key":
                return "supersecretkey123456"
            return ""

        with patch("db.config.get_config_entry", side_effect=mock_get_config_entry):
            resp = client.get("/api/v1/api-keys/")
        data = resp.get_json()
        sublarr_service = next(s for s in data["services"] if s["service"] == "sublarr")
        assert sublarr_service["status"] == "configured"

    def test_key_values_are_masked(self, client):
        def mock_get_config_entry(key):
            if key == "api_key":
                return "supersecretkey123456"
            return ""

        with patch("db.config.get_config_entry", side_effect=mock_get_config_entry):
            resp = client.get("/api/v1/api-keys/")
        data = resp.get_json()
        sublarr_service = next(s for s in data["services"] if s["service"] == "sublarr")
        key_info = sublarr_service["keys"][0]
        # Should NOT contain the raw secret
        assert "supersecretkey123456" not in key_info["masked_value"]
        # Should contain "***"
        assert "***" in key_info["masked_value"]


# ---------------------------------------------------------------------------
# TestGetService — GET /api/v1/api-keys/<service>
# ---------------------------------------------------------------------------


class TestGetService:
    """Tests for GET /api/v1/api-keys/<service> (get_service endpoint)."""

    def test_known_service_returns_200(self, client):
        with patch("db.config.get_config_entry", return_value=""):
            resp = client.get("/api/v1/api-keys/sonarr")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["service"] == "sonarr"
        assert "label" in data

    def test_unknown_service_returns_404(self, client):
        resp = client.get("/api/v1/api-keys/nonexistent_service")
        assert resp.status_code == 404
        data = resp.get_json()
        assert "error" in data

    def test_testable_service_shows_testable_true(self, client):
        with patch("db.config.get_config_entry", return_value=""):
            resp = client.get("/api/v1/api-keys/sonarr")
        data = resp.get_json()
        assert data["testable"] is True

    def test_non_testable_service_shows_testable_false(self, client):
        with patch("db.config.get_config_entry", return_value=""):
            resp = client.get("/api/v1/api-keys/tmdb")
        data = resp.get_json()
        assert data["testable"] is False

    def test_response_contains_label(self, client):
        with patch("db.config.get_config_entry", return_value=""):
            resp = client.get("/api/v1/api-keys/sonarr")
        data = resp.get_json()
        assert data["label"] == "Sonarr"


# ---------------------------------------------------------------------------
# TestUpdateServiceKeys — PUT /api/v1/api-keys/<service>
# ---------------------------------------------------------------------------


class TestUpdateServiceKeys:
    """Tests for PUT /api/v1/api-keys/<service> (update_service_keys endpoint)."""

    def test_unknown_service_returns_404(self, client):
        resp = client.put(
            "/api/v1/api-keys/nonexistent_service",
            json={"some_key": "some_value"},
        )
        assert resp.status_code == 404
        data = resp.get_json()
        assert "error" in data

    def test_empty_body_returns_400(self, client):
        resp = client.put(
            "/api/v1/api-keys/sonarr",
            json={},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert "error" in data
        assert "No key data" in data["error"]

    def test_valid_update_returns_200_with_status(self, client):
        with (
            patch("db.config.save_config_entry"),
            patch("db.config.get_config_entry", return_value="newvalue12345678"),
            patch("db.config.get_all_config_entries", return_value={}),
            patch("config.reload_settings"),
            patch("routes.api_keys._invalidate_for_service"),
        ):
            resp = client.put(
                "/api/v1/api-keys/sonarr",
                json={"sonarr_api_key": "mynewsecretapikey"},
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "updated"
        assert "updated_keys" in data

    def test_valid_update_calls_save_config_entry(self, client):
        with (
            patch("db.config.save_config_entry") as mock_save,
            patch("db.config.get_config_entry", return_value="newvalue12345678"),
            patch("db.config.get_all_config_entries", return_value={}),
            patch("config.reload_settings"),
            patch("routes.api_keys._invalidate_for_service"),
        ):
            client.put(
                "/api/v1/api-keys/sonarr",
                json={"sonarr_api_key": "mynewsecretapikey"},
            )
            mock_save.assert_called_once_with("sonarr_api_key", "mynewsecretapikey")

    def test_masked_value_not_saved(self, client):
        with (
            patch("db.config.save_config_entry") as mock_save,
            patch("db.config.get_config_entry", return_value=""),
            patch("db.config.get_all_config_entries", return_value={}),
            patch("config.reload_settings"),
            patch("routes.api_keys._invalidate_for_service"),
        ):
            client.put(
                "/api/v1/api-keys/sonarr",
                json={"sonarr_api_key": "abcd***efgh"},  # masked value
            )
        # save should NOT be called for masked values
        mock_save.assert_not_called()

    def test_updated_keys_list_in_response(self, client):
        with (
            patch("db.config.save_config_entry"),
            patch("db.config.get_config_entry", return_value="newvalue12345678"),
            patch("db.config.get_all_config_entries", return_value={}),
            patch("config.reload_settings"),
            patch("routes.api_keys._invalidate_for_service"),
        ):
            resp = client.put(
                "/api/v1/api-keys/sonarr",
                json={"sonarr_api_key": "mynewsecretapikey"},
            )
        data = resp.get_json()
        assert "sonarr_api_key" in data["updated_keys"]


# ---------------------------------------------------------------------------
# TestTestService — POST /api/v1/api-keys/<service>/test
# ---------------------------------------------------------------------------


class TestTestService:
    """Tests for POST /api/v1/api-keys/<service>/test (test_service endpoint)."""

    def test_unknown_service_returns_404(self, client):
        resp = client.post("/api/v1/api-keys/nonexistent_service/test")
        assert resp.status_code == 404
        data = resp.get_json()
        assert "error" in data

    def test_non_testable_service_returns_400(self, client):
        # tmdb has test_fn=None
        resp = client.post("/api/v1/api-keys/tmdb/test")
        assert resp.status_code == 400
        data = resp.get_json()
        assert "error" in data
        assert "does not support connection testing" in data["error"]

    def test_testable_service_with_mock_returns_200(self, client):
        mock_result = {"success": True, "message": "Sonarr connection OK"}
        with (
            patch("routes.api_keys._test_sonarr", return_value=mock_result) as mock_fn,
            patch.dict("routes.api_keys._TEST_DISPATCH", {"_test_sonarr": mock_fn}),
        ):
            resp = client.post("/api/v1/api-keys/sonarr/test")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "success" in data
        assert "message" in data
        assert data["success"] is True

    def test_testable_service_failed_connection_returns_200_with_success_false(self, client):
        mock_result = {"success": False, "message": "Connection refused"}
        with (
            patch(
                "routes.api_keys._test_sonarr",
                return_value=mock_result,
            ) as mock_fn,
            patch.dict(
                "routes.api_keys._TEST_DISPATCH",
                {"_test_sonarr": mock_fn},
            ),
        ):
            resp = client.post("/api/v1/api-keys/sonarr/test")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is False
        assert "message" in data

    def test_provider_test_passes_service_name(self, client):
        """For _test_provider services, the service name must be passed as argument."""
        mock_result = {"success": True, "message": "Provider OK"}
        captured_args = []

        def capturing_test_provider(service_name):
            captured_args.append(service_name)
            return mock_result

        with patch.dict(
            "routes.api_keys._TEST_DISPATCH",
            {"_test_provider": capturing_test_provider},
        ):
            resp = client.post("/api/v1/api-keys/opensubtitles/test")
        assert resp.status_code == 200
        assert captured_args == ["opensubtitles"]
