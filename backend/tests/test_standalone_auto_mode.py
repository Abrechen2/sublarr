"""Tests for is_standalone_mode() auto-activation logic."""
from unittest.mock import patch, MagicMock


def _make_settings(standalone_enabled=False, sonarr_json="", radarr_json="",
                   sonarr_url="", sonarr_api_key="", radarr_url="", radarr_api_key=""):
    s = MagicMock()
    s.standalone_enabled = standalone_enabled
    s.sonarr_instances_json = sonarr_json
    s.radarr_instances_json = radarr_json
    s.sonarr_url = sonarr_url
    s.sonarr_api_key = sonarr_api_key
    s.radarr_url = radarr_url
    s.radarr_api_key = radarr_api_key
    s.path_mapping = ""
    return s


class TestIsStandaloneMode:
    def test_explicit_enabled_returns_true(self):
        from config import is_standalone_mode
        s = _make_settings(standalone_enabled=True)
        with patch("config.get_settings", return_value=s):
            assert is_standalone_mode() is True

    def test_no_arr_configured_auto_activates(self):
        from config import is_standalone_mode
        s = _make_settings()  # everything empty
        with patch("config.get_settings", return_value=s):
            assert is_standalone_mode() is True

    def test_sonarr_configured_no_auto(self):
        from config import is_standalone_mode
        s = _make_settings(
            sonarr_json='[{"id":"x","name":"S1","url":"http://host:8989","api_key":"k"}]'
        )
        with patch("config.get_settings", return_value=s):
            assert is_standalone_mode() is False

    def test_radarr_configured_no_auto(self):
        from config import is_standalone_mode
        s = _make_settings(
            radarr_json='[{"id":"x","name":"R1","url":"http://host:7878","api_key":"k"}]'
        )
        with patch("config.get_settings", return_value=s):
            assert is_standalone_mode() is False

    def test_legacy_sonarr_url_no_auto(self):
        from config import is_standalone_mode
        s = _make_settings(sonarr_url="http://host:8989", sonarr_api_key="key")
        with patch("config.get_settings", return_value=s):
            assert is_standalone_mode() is False

    def test_explicit_enabled_overrides_arr_configured(self):
        """standalone_enabled=True activates even when arr IS configured."""
        from config import is_standalone_mode
        s = _make_settings(
            standalone_enabled=True,
            sonarr_json='[{"id":"x","name":"S1","url":"http://host:8989","api_key":"k"}]'
        )
        with patch("config.get_settings", return_value=s):
            assert is_standalone_mode() is True

    def test_empty_instances_json_array_no_arr(self):
        from config import is_standalone_mode
        s = _make_settings(sonarr_json="[]", radarr_json="[]")
        with patch("config.get_settings", return_value=s):
            assert is_standalone_mode() is True

    def test_invalid_json_treated_as_no_arr(self):
        from config import is_standalone_mode
        s = _make_settings(sonarr_json="not-valid-json")
        with patch("config.get_settings", return_value=s):
            assert is_standalone_mode() is True
