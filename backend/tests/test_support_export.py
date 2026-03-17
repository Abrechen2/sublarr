"""Tests for support export anonymization and diagnostic builder."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestAnonymize:
    """Test the _anonymize() helper function."""

    def _fn(self, *args, **kwargs):
        from routes.system import _anonymize
        return _anonymize(*args, **kwargs)

    def test_private_ip_192_168(self):
        assert self._fn("Connected to 192.168.178.194") == "Connected to 192.168.xxx.xxx"

    def test_private_ip_10_x(self):
        assert self._fn("Host: 10.0.0.1") == "Host: 10.0.xxx.xxx"

    def test_private_ip_172_16(self):
        assert self._fn("Addr: 172.16.5.20") == "Addr: 172.16.xxx.xxx"

    def test_public_ip_fully_redacted(self):
        assert self._fn("Remote: 85.214.132.17") == "Remote: xxx.xxx.xxx.xxx"

    def test_localhost_preserved(self):
        line = "Listening on 127.0.0.1:5765"
        assert self._fn(line) == line

    def test_api_key_redacted(self):
        line = 'api_key: "3bdcc724abcdef1234567890abcdef12"'
        result = self._fn(line)
        assert "3bdcc724" not in result
        assert "***REDACTED***" in result

    def test_path_keeps_filename_only(self):
        line = "Subtitle for /media/Anime/86 Eighty Six/S01E01.mkv"
        result = self._fn(line)
        assert "86 Eighty Six" not in result
        assert "S01E01.mkv" in result

    def test_email_redacted(self):
        line = "User: somebody@example.com logged in"
        result = self._fn(line)
        assert "***USER***" in result
        assert "somebody@example.com" not in result

    def test_hostname_parameter_redacted(self):
        """Pass hostname explicitly — simulates what export time does."""
        result = self._fn("Request from my-server", hostname="my-server")
        assert "***HOST***" in result
        assert "my-server" not in result

    def test_unix_home_path_shortened(self):
        line = "Config at /home/dennis/sublarr/config.db"
        result = self._fn(line)
        assert "/home/dennis" not in result
        assert "~/sublarr/config.db" in result

    def test_root_path_shortened(self):
        line = "Config at /root/.bashrc"
        result = self._fn(line)
        assert "/root" not in result
        assert "~/.bashrc" in result


class TestBuildDiagnostic:
    """Test the _build_diagnostic() shared helper."""

    def _call(self):
        from routes.system import _build_diagnostic
        return _build_diagnostic()

    def test_returns_version(self):
        result = self._call()
        assert "version" in result
        assert isinstance(result["version"], str)

    def test_wanted_counts_present(self):
        result = self._call()
        # Either wanted dict exists, or db_stats_error is set — both are valid
        assert "wanted" in result or result.get("db_stats_error") == "unavailable"

    def test_translations_present(self):
        result = self._call()
        assert "translations" in result or result.get("db_stats_error") == "unavailable"

    def test_top_errors_is_list(self):
        result = self._call()
        assert isinstance(result.get("top_errors", []), list)

    def test_provider_status_is_list(self):
        result = self._call()
        assert isinstance(result.get("provider_status", []), list)
        for p in result.get("provider_status", []):
            assert "name" in p
            assert "active" in p

    def test_memory_mb_present(self):
        result = self._call()
        assert "memory_mb" in result  # may be None if psutil absent

    def test_db_error_handled_gracefully(self):
        from unittest.mock import patch, MagicMock
        from routes.system import _build_diagnostic
        # Simulate DB failure by patching _db_lock so __enter__ raises
        mock_lock = MagicMock()
        mock_lock.__enter__ = MagicMock(side_effect=Exception("locked"))
        mock_lock.__exit__ = MagicMock(return_value=False)
        with patch("routes.system._db_lock", mock_lock):
            result = _build_diagnostic()
        assert "db_stats_error" in result
