"""Tests for routes/integrations.py -- Bazarr mapping, compat check, health, export."""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# 1. Bazarr Mapping Report
# ---------------------------------------------------------------------------


class TestBazarrMappingReport:
    """POST /api/v1/integrations/bazarr/mapping-report"""

    def test_missing_db_path_returns_400(self, client):
        rv = client.post(
            "/api/v1/integrations/bazarr/mapping-report",
            json={},
            content_type="application/json",
        )
        assert rv.status_code == 400
        assert "db_path" in rv.get_json()["error"]

    def test_empty_db_path_returns_400(self, client):
        rv = client.post(
            "/api/v1/integrations/bazarr/mapping-report",
            json={"db_path": ""},
            content_type="application/json",
        )
        assert rv.status_code == 400
        assert "db_path" in rv.get_json()["error"]

    def test_unsafe_path_returns_403(self, client):
        """Paths outside /config and media_path are rejected."""
        with patch("routes.integrations.is_safe_path", return_value=False):
            rv = client.post(
                "/api/v1/integrations/bazarr/mapping-report",
                json={"db_path": "/etc/passwd"},
                content_type="application/json",
            )
        assert rv.status_code == 403
        assert "db_path must be under" in rv.get_json()["error"]

    def test_file_not_found_returns_400(self, client):
        """Valid path but file does not exist."""
        with patch("routes.integrations.is_safe_path", return_value=True):
            rv = client.post(
                "/api/v1/integrations/bazarr/mapping-report",
                json={"db_path": "/config/nonexistent.db"},
                content_type="application/json",
            )
        assert rv.status_code == 400
        assert "File not found" in rv.get_json()["error"]

    def test_successful_mapping_report(self, client, tmp_path):
        """Happy path -- file exists, generate_mapping_report returns data."""
        db_file = tmp_path / "bazarr.db"
        db_file.write_text("fake-db")
        db_path_str = str(db_file)

        fake_report = {"series": 10, "movies": 5, "mappings": []}

        with (
            patch("routes.integrations.is_safe_path", return_value=True),
            patch("os.path.isfile", return_value=True),
            patch("bazarr_migrator.generate_mapping_report", return_value=fake_report),
        ):
            rv = client.post(
                "/api/v1/integrations/bazarr/mapping-report",
                json={"db_path": db_path_str},
                content_type="application/json",
            )

        assert rv.status_code == 200
        data = rv.get_json()
        assert data["series"] == 10
        assert data["movies"] == 5

    def test_mapping_report_exception_returns_500(self, client):
        """Exception in generate_mapping_report is caught."""
        with (
            patch("routes.integrations.is_safe_path", return_value=True),
            patch("os.path.isfile", return_value=True),
            patch(
                "bazarr_migrator.generate_mapping_report",
                side_effect=RuntimeError("corrupt DB"),
            ),
        ):
            rv = client.post(
                "/api/v1/integrations/bazarr/mapping-report",
                json={"db_path": "/config/bazarr.db"},
                content_type="application/json",
            )

        assert rv.status_code == 500
        assert "Mapping report failed" in rv.get_json()["error"]

    def test_no_json_body_returns_400(self, client):
        """Sending no JSON body should still return 400 for missing db_path."""
        rv = client.post(
            "/api/v1/integrations/bazarr/mapping-report",
            content_type="application/json",
        )
        assert rv.status_code == 400

    def test_safe_path_checked_for_config_dir_and_media_path(self, client):
        """is_safe_path is called with both config_dir and media_path."""
        call_args = []

        def tracking_is_safe_path(path, base):
            call_args.append((path, base))
            return False  # reject both

        with patch("routes.integrations.is_safe_path", side_effect=tracking_is_safe_path):
            rv = client.post(
                "/api/v1/integrations/bazarr/mapping-report",
                json={"db_path": "/some/path.db"},
                content_type="application/json",
            )

        assert rv.status_code == 403
        # Called at least twice -- once for config_dir, once for media_path
        assert len(call_args) == 2


# ---------------------------------------------------------------------------
# 2. Compatibility Check (Batch)
# ---------------------------------------------------------------------------


class TestCompatCheckBatch:
    """POST /api/v1/integrations/compat-check"""

    def test_missing_subtitle_paths_returns_400(self, client):
        rv = client.post(
            "/api/v1/integrations/compat-check",
            json={"video_path": "/media/video.mkv"},
            content_type="application/json",
        )
        assert rv.status_code == 400
        assert "subtitle_paths" in rv.get_json()["error"]

    def test_empty_subtitle_paths_returns_400(self, client):
        rv = client.post(
            "/api/v1/integrations/compat-check",
            json={"subtitle_paths": [], "video_path": "/media/video.mkv"},
            content_type="application/json",
        )
        assert rv.status_code == 400
        assert "subtitle_paths" in rv.get_json()["error"]

    def test_missing_video_path_returns_400(self, client):
        rv = client.post(
            "/api/v1/integrations/compat-check",
            json={"subtitle_paths": ["/sub.srt"]},
            content_type="application/json",
        )
        assert rv.status_code == 400
        assert "video_path" in rv.get_json()["error"]

    def test_invalid_target_returns_400(self, client):
        rv = client.post(
            "/api/v1/integrations/compat-check",
            json={
                "subtitle_paths": ["/sub.srt"],
                "video_path": "/media/video.mkv",
                "target": "vlc",
            },
            content_type="application/json",
        )
        assert rv.status_code == 400
        assert "target" in rv.get_json()["error"]

    def test_successful_batch_check_plex(self, client):
        fake_result = {"compatible": True, "issues": []}
        with patch(
            "compat_checker.batch_check_compatibility", return_value=fake_result
        ):
            rv = client.post(
                "/api/v1/integrations/compat-check",
                json={
                    "subtitle_paths": ["/sub1.srt", "/sub2.ass"],
                    "video_path": "/media/video.mkv",
                    "target": "plex",
                },
                content_type="application/json",
            )

        assert rv.status_code == 200
        data = rv.get_json()
        assert data["compatible"] is True

    def test_successful_batch_check_kodi(self, client):
        fake_result = {"compatible": False, "issues": ["codec unsupported"]}
        with patch(
            "compat_checker.batch_check_compatibility", return_value=fake_result
        ):
            rv = client.post(
                "/api/v1/integrations/compat-check",
                json={
                    "subtitle_paths": ["/sub.srt"],
                    "video_path": "/media/video.mkv",
                    "target": "kodi",
                },
                content_type="application/json",
            )

        assert rv.status_code == 200
        data = rv.get_json()
        assert data["compatible"] is False

    def test_default_target_is_plex(self, client):
        """When no target given, defaults to plex."""
        with patch(
            "compat_checker.batch_check_compatibility", return_value={}
        ) as mock_fn:
            rv = client.post(
                "/api/v1/integrations/compat-check",
                json={
                    "subtitle_paths": ["/sub.srt"],
                    "video_path": "/media/video.mkv",
                },
                content_type="application/json",
            )

        assert rv.status_code == 200
        mock_fn.assert_called_once_with(["/sub.srt"], "/media/video.mkv", "plex")

    def test_batch_check_exception_returns_500(self, client):
        with patch(
            "compat_checker.batch_check_compatibility",
            side_effect=RuntimeError("codec error"),
        ):
            rv = client.post(
                "/api/v1/integrations/compat-check",
                json={
                    "subtitle_paths": ["/sub.srt"],
                    "video_path": "/media/video.mkv",
                },
                content_type="application/json",
            )

        assert rv.status_code == 500
        assert "Compatibility check failed" in rv.get_json()["error"]


# ---------------------------------------------------------------------------
# 3. Compatibility Check (Single)
# ---------------------------------------------------------------------------


class TestCompatCheckSingle:
    """POST /api/v1/integrations/compat-check/single"""

    def test_missing_subtitle_path_returns_400(self, client):
        rv = client.post(
            "/api/v1/integrations/compat-check/single",
            json={"video_path": "/media/video.mkv"},
            content_type="application/json",
        )
        assert rv.status_code == 400
        assert "subtitle_path" in rv.get_json()["error"]

    def test_missing_video_path_returns_400(self, client):
        rv = client.post(
            "/api/v1/integrations/compat-check/single",
            json={"subtitle_path": "/sub.srt"},
            content_type="application/json",
        )
        assert rv.status_code == 400
        assert "video_path" in rv.get_json()["error"]

    def test_invalid_target_returns_400(self, client):
        rv = client.post(
            "/api/v1/integrations/compat-check/single",
            json={
                "subtitle_path": "/sub.srt",
                "video_path": "/media/video.mkv",
                "target": "emby",
            },
            content_type="application/json",
        )
        assert rv.status_code == 400
        assert "target" in rv.get_json()["error"]

    def test_single_plex_check(self, client):
        fake_result = {"compatible": True, "format": "srt"}
        with patch(
            "compat_checker.check_plex_compatibility", return_value=fake_result
        ):
            rv = client.post(
                "/api/v1/integrations/compat-check/single",
                json={
                    "subtitle_path": "/sub.srt",
                    "video_path": "/media/video.mkv",
                    "target": "plex",
                },
                content_type="application/json",
            )

        assert rv.status_code == 200
        assert rv.get_json()["compatible"] is True

    def test_single_kodi_check(self, client):
        fake_result = {"compatible": True, "format": "ass"}
        with patch(
            "compat_checker.check_kodi_compatibility", return_value=fake_result
        ):
            rv = client.post(
                "/api/v1/integrations/compat-check/single",
                json={
                    "subtitle_path": "/sub.ass",
                    "video_path": "/media/video.mkv",
                    "target": "kodi",
                },
                content_type="application/json",
            )

        assert rv.status_code == 200
        assert rv.get_json()["compatible"] is True

    def test_single_check_default_target_plex(self, client):
        """Default target is plex -- check_plex_compatibility is called."""
        with patch(
            "compat_checker.check_plex_compatibility", return_value={}
        ) as mock_plex:
            rv = client.post(
                "/api/v1/integrations/compat-check/single",
                json={
                    "subtitle_path": "/sub.srt",
                    "video_path": "/media/video.mkv",
                },
                content_type="application/json",
            )

        assert rv.status_code == 200
        mock_plex.assert_called_once_with("/sub.srt", "/media/video.mkv")

    def test_single_check_exception_returns_500(self, client):
        with patch(
            "compat_checker.check_plex_compatibility",
            side_effect=RuntimeError("file error"),
        ):
            rv = client.post(
                "/api/v1/integrations/compat-check/single",
                json={
                    "subtitle_path": "/sub.srt",
                    "video_path": "/media/video.mkv",
                    "target": "plex",
                },
                content_type="application/json",
            )

        assert rv.status_code == 500
        assert "Compatibility check failed" in rv.get_json()["error"]


# ---------------------------------------------------------------------------
# 4. Extended Health: Sonarr
# ---------------------------------------------------------------------------


class TestHealthSonarr:
    """GET /api/v1/integrations/health/sonarr"""

    def test_no_instances_configured(self, client):
        with patch("config.get_sonarr_instances", return_value=[]):
            rv = client.get("/api/v1/integrations/health/sonarr")

        assert rv.status_code == 200
        data = rv.get_json()
        assert data["instances"] == []
        assert "No Sonarr instances configured" in data["message"]

    def test_single_healthy_instance(self, client):
        instances = [{"name": "Main", "url": "http://sonarr:8989", "api_key": "abc"}]
        mock_client = MagicMock()
        mock_client.extended_health_check.return_value = {
            "connection": {"healthy": True, "message": "OK"}
        }

        with (
            patch("config.get_sonarr_instances", return_value=instances),
            patch("sonarr_client.SonarrClient", return_value=mock_client),
        ):
            rv = client.get("/api/v1/integrations/health/sonarr")

        assert rv.status_code == 200
        data = rv.get_json()
        assert len(data["instances"]) == 1
        assert data["instances"][0]["name"] == "Main"
        assert data["instances"][0]["connection"]["healthy"] is True

    def test_instance_with_exception(self, client):
        instances = [{"name": "Broken", "url": "http://bad:8989", "api_key": "x"}]
        mock_client = MagicMock()
        mock_client.extended_health_check.side_effect = ConnectionError("refused")

        with (
            patch("config.get_sonarr_instances", return_value=instances),
            patch("sonarr_client.SonarrClient", return_value=mock_client),
        ):
            rv = client.get("/api/v1/integrations/health/sonarr")

        assert rv.status_code == 200
        data = rv.get_json()
        inst = data["instances"][0]
        assert inst["name"] == "Broken"
        assert inst["connection"]["healthy"] is False
        assert "refused" in inst["connection"]["message"]

    def test_multiple_instances(self, client):
        instances = [
            {"name": "Sonarr1", "url": "http://s1:8989", "api_key": "a"},
            {"name": "Sonarr2", "url": "http://s2:8989", "api_key": "b"},
        ]
        mock_client = MagicMock()
        mock_client.extended_health_check.return_value = {
            "connection": {"healthy": True, "message": "OK"}
        }

        with (
            patch("config.get_sonarr_instances", return_value=instances),
            patch("sonarr_client.SonarrClient", return_value=mock_client),
        ):
            rv = client.get("/api/v1/integrations/health/sonarr")

        assert rv.status_code == 200
        assert len(rv.get_json()["instances"]) == 2

    def test_unnamed_instance_defaults_to_unnamed(self, client):
        instances = [{"url": "http://s:8989", "api_key": "a"}]
        mock_client = MagicMock()
        mock_client.extended_health_check.return_value = {
            "connection": {"healthy": True, "message": "OK"}
        }

        with (
            patch("config.get_sonarr_instances", return_value=instances),
            patch("sonarr_client.SonarrClient", return_value=mock_client),
        ):
            rv = client.get("/api/v1/integrations/health/sonarr")

        assert rv.get_json()["instances"][0]["name"] == "Unnamed"

    def test_top_level_exception_returns_500(self, client):
        with patch(
            "config.get_sonarr_instances",
            side_effect=RuntimeError("config broken"),
        ):
            rv = client.get("/api/v1/integrations/health/sonarr")

        assert rv.status_code == 500
        assert "Sonarr health check failed" in rv.get_json()["error"]


# ---------------------------------------------------------------------------
# 5. Extended Health: Radarr
# ---------------------------------------------------------------------------


class TestHealthRadarr:
    """GET /api/v1/integrations/health/radarr"""

    def test_no_instances_configured(self, client):
        with patch("config.get_radarr_instances", return_value=[]):
            rv = client.get("/api/v1/integrations/health/radarr")

        assert rv.status_code == 200
        data = rv.get_json()
        assert data["instances"] == []
        assert "No Radarr instances configured" in data["message"]

    def test_single_healthy_instance(self, client):
        instances = [{"name": "Movies", "url": "http://radarr:7878", "api_key": "key"}]
        mock_client = MagicMock()
        mock_client.extended_health_check.return_value = {
            "connection": {"healthy": True, "message": "OK"}
        }

        with (
            patch("config.get_radarr_instances", return_value=instances),
            patch("radarr_client.RadarrClient", return_value=mock_client),
        ):
            rv = client.get("/api/v1/integrations/health/radarr")

        assert rv.status_code == 200
        data = rv.get_json()
        assert len(data["instances"]) == 1
        assert data["instances"][0]["connection"]["healthy"] is True

    def test_instance_with_exception(self, client):
        instances = [{"name": "Bad", "url": "http://bad:7878", "api_key": "x"}]
        mock_client = MagicMock()
        mock_client.extended_health_check.side_effect = TimeoutError("timeout")

        with (
            patch("config.get_radarr_instances", return_value=instances),
            patch("radarr_client.RadarrClient", return_value=mock_client),
        ):
            rv = client.get("/api/v1/integrations/health/radarr")

        assert rv.status_code == 200
        inst = rv.get_json()["instances"][0]
        assert inst["connection"]["healthy"] is False
        assert "timeout" in inst["connection"]["message"]

    def test_top_level_exception_returns_500(self, client):
        with patch(
            "config.get_radarr_instances",
            side_effect=RuntimeError("config error"),
        ):
            rv = client.get("/api/v1/integrations/health/radarr")

        assert rv.status_code == 500
        assert "Radarr health check failed" in rv.get_json()["error"]


# ---------------------------------------------------------------------------
# 6. Extended Health: Jellyfin
# ---------------------------------------------------------------------------


class TestHealthJellyfin:
    """GET /api/v1/integrations/health/jellyfin"""

    def test_no_jellyfin_configured(self, client):
        mock_manager = MagicMock()
        mock_manager._instances = {}

        with patch(
            "mediaserver.get_media_server_manager", return_value=mock_manager
        ):
            rv = client.get("/api/v1/integrations/health/jellyfin")

        assert rv.status_code == 200
        data = rv.get_json()
        assert data["connection"]["healthy"] is False
        assert "not configured" in data["connection"]["message"].lower()

    def test_jellyfin_healthy(self, client):
        mock_instance = MagicMock()
        type(mock_instance).name = "jellyfin"
        mock_instance.health_check.return_value = (True, "Connected")

        mock_manager = MagicMock()
        mock_manager._instances = {"jf1": mock_instance}

        with patch(
            "mediaserver.get_media_server_manager", return_value=mock_manager
        ):
            rv = client.get("/api/v1/integrations/health/jellyfin")

        assert rv.status_code == 200
        data = rv.get_json()
        assert data["connection"]["healthy"] is True
        assert data["connection"]["message"] == "Connected"

    def test_jellyfin_not_in_instances(self, client):
        """Non-jellyfin instances are filtered out."""
        mock_instance = MagicMock()
        type(mock_instance).name = "plex"

        mock_manager = MagicMock()
        mock_manager._instances = {"plex1": mock_instance}

        with patch(
            "mediaserver.get_media_server_manager", return_value=mock_manager
        ):
            rv = client.get("/api/v1/integrations/health/jellyfin")

        assert rv.status_code == 200
        assert rv.get_json()["connection"]["healthy"] is False

    def test_top_level_exception_returns_500(self, client):
        with patch(
            "mediaserver.get_media_server_manager",
            side_effect=RuntimeError("manager broken"),
        ):
            rv = client.get("/api/v1/integrations/health/jellyfin")

        assert rv.status_code == 500
        assert "Jellyfin health check failed" in rv.get_json()["error"]


# ---------------------------------------------------------------------------
# 7. Extended Health: Media Servers
# ---------------------------------------------------------------------------


class TestHealthMediaServers:
    """GET /api/v1/integrations/health/mediaservers"""

    def test_no_instances(self, client):
        mock_manager = MagicMock()
        mock_manager._instances = {}
        mock_manager._instance_enabled = {}

        with patch(
            "mediaserver.get_media_server_manager", return_value=mock_manager
        ):
            rv = client.get("/api/v1/integrations/health/mediaservers")

        assert rv.status_code == 200
        assert rv.get_json()["instances"] == []

    def test_instance_with_extended_health_check(self, client):
        mock_instance = MagicMock()
        type(mock_instance).name = "jellyfin"
        mock_instance.config = {"name": "My Jellyfin"}
        mock_instance.extended_health_check.return_value = {
            "connection": {"healthy": True, "message": "OK"},
            "version": "10.8.0",
        }

        mock_manager = MagicMock()
        mock_manager._instances = {"jf1": mock_instance}
        mock_manager._instance_enabled = {"jf1": True}

        with patch(
            "mediaserver.get_media_server_manager", return_value=mock_manager
        ):
            rv = client.get("/api/v1/integrations/health/mediaservers")

        assert rv.status_code == 200
        data = rv.get_json()
        inst = data["instances"][0]
        assert inst["name"] == "My Jellyfin"
        assert inst["type"] == "jellyfin"
        assert inst["enabled"] is True
        assert inst["connection"]["healthy"] is True

    def test_instance_without_extended_health_check(self, client):
        """Falls back to basic health_check."""
        mock_instance = MagicMock(spec=["health_check", "config"])
        type(mock_instance).name = "plex"
        mock_instance.config = {"name": "My Plex"}
        mock_instance.health_check.return_value = (True, "Plex OK")
        # Ensure hasattr(instance, "extended_health_check") is False
        del mock_instance.extended_health_check

        mock_manager = MagicMock()
        mock_manager._instances = {"plex1": mock_instance}
        mock_manager._instance_enabled = {"plex1": True}

        with patch(
            "mediaserver.get_media_server_manager", return_value=mock_manager
        ):
            rv = client.get("/api/v1/integrations/health/mediaservers")

        assert rv.status_code == 200
        inst = rv.get_json()["instances"][0]
        assert inst["connection"]["healthy"] is True
        assert inst["connection"]["message"] == "Plex OK"

    def test_instance_extended_health_check_exception(self, client):
        mock_instance = MagicMock()
        type(mock_instance).name = "jellyfin"
        mock_instance.config = {"name": "Broken JF"}
        mock_instance.extended_health_check.side_effect = ConnectionError("refused")

        mock_manager = MagicMock()
        mock_manager._instances = {"jf1": mock_instance}
        mock_manager._instance_enabled = {"jf1": False}

        with patch(
            "mediaserver.get_media_server_manager", return_value=mock_manager
        ):
            rv = client.get("/api/v1/integrations/health/mediaservers")

        assert rv.status_code == 200
        inst = rv.get_json()["instances"][0]
        assert inst["enabled"] is False
        assert inst["connection"]["healthy"] is False

    def test_instance_basic_health_check_exception(self, client):
        """Falls back to basic health_check which raises."""
        mock_instance = MagicMock(spec=["health_check", "config"])
        type(mock_instance).name = "emby"
        mock_instance.config = {"name": "Emby"}
        mock_instance.health_check.side_effect = ConnectionError("no route")
        del mock_instance.extended_health_check

        mock_manager = MagicMock()
        mock_manager._instances = {"emby1": mock_instance}
        mock_manager._instance_enabled = {"emby1": True}

        with patch(
            "mediaserver.get_media_server_manager", return_value=mock_manager
        ):
            rv = client.get("/api/v1/integrations/health/mediaservers")

        assert rv.status_code == 200
        inst = rv.get_json()["instances"][0]
        assert inst["connection"]["healthy"] is False
        assert "no route" in inst["connection"]["message"]

    def test_instance_name_fallback_to_key(self, client):
        """If config has no name, falls back to instance key."""
        mock_instance = MagicMock()
        type(mock_instance).name = "plex"
        mock_instance.config = {}  # no name
        mock_instance.extended_health_check.return_value = {
            "connection": {"healthy": True, "message": "OK"}
        }

        mock_manager = MagicMock()
        mock_manager._instances = {"plex_main": mock_instance}
        mock_manager._instance_enabled = {"plex_main": True}

        with patch(
            "mediaserver.get_media_server_manager", return_value=mock_manager
        ):
            rv = client.get("/api/v1/integrations/health/mediaservers")

        assert rv.get_json()["instances"][0]["name"] == "plex_main"

    def test_top_level_exception_returns_500(self, client):
        with patch(
            "mediaserver.get_media_server_manager",
            side_effect=RuntimeError("crash"),
        ):
            rv = client.get("/api/v1/integrations/health/mediaservers")

        assert rv.status_code == 500
        assert "Media servers health check failed" in rv.get_json()["error"]


# ---------------------------------------------------------------------------
# 8. Export Config
# ---------------------------------------------------------------------------


class TestExportConfig:
    """POST /api/v1/integrations/export"""

    def test_invalid_format_returns_400(self, client):
        rv = client.post(
            "/api/v1/integrations/export",
            json={"format": "yaml"},
            content_type="application/json",
        )
        assert rv.status_code == 400
        assert "Invalid format" in rv.get_json()["error"]

    def test_default_format_is_json(self, client):
        """When no format specified, defaults to json."""
        fake_config = {"settings": {"key": "value"}}
        with patch("export_manager.export_config", return_value=fake_config) as mock_fn:
            rv = client.post(
                "/api/v1/integrations/export",
                json={},
                content_type="application/json",
            )

        assert rv.status_code == 200
        mock_fn.assert_called_once_with("json", include_secrets=False)

    def test_export_json_format(self, client):
        fake_config = {"format": "json", "data": {}}
        with patch("export_manager.export_config", return_value=fake_config):
            rv = client.post(
                "/api/v1/integrations/export",
                json={"format": "json"},
                content_type="application/json",
            )

        assert rv.status_code == 200
        assert rv.get_json()["format"] == "json"

    def test_export_bazarr_format(self, client):
        fake_config = {"format": "bazarr", "data": {}}
        with patch("export_manager.export_config", return_value=fake_config):
            rv = client.post(
                "/api/v1/integrations/export",
                json={"format": "bazarr"},
                content_type="application/json",
            )

        assert rv.status_code == 200

    def test_export_plex_format(self, client):
        fake_config = {"format": "plex", "data": {}}
        with patch("export_manager.export_config", return_value=fake_config):
            rv = client.post(
                "/api/v1/integrations/export",
                json={"format": "plex"},
                content_type="application/json",
            )

        assert rv.status_code == 200

    def test_export_kodi_format(self, client):
        fake_config = {"format": "kodi", "data": {}}
        with patch("export_manager.export_config", return_value=fake_config):
            rv = client.post(
                "/api/v1/integrations/export",
                json={"format": "kodi"},
                content_type="application/json",
            )

        assert rv.status_code == 200

    def test_include_secrets_passed_through(self, client):
        with patch("export_manager.export_config", return_value={}) as mock_fn:
            client.post(
                "/api/v1/integrations/export",
                json={"format": "json", "include_secrets": True},
                content_type="application/json",
            )

        mock_fn.assert_called_once_with("json", include_secrets=True)

    def test_include_secrets_defaults_false(self, client):
        with patch("export_manager.export_config", return_value={}) as mock_fn:
            client.post(
                "/api/v1/integrations/export",
                json={"format": "json"},
                content_type="application/json",
            )

        mock_fn.assert_called_once_with("json", include_secrets=False)

    def test_export_exception_returns_500(self, client):
        with patch(
            "export_manager.export_config",
            side_effect=RuntimeError("export error"),
        ):
            rv = client.post(
                "/api/v1/integrations/export",
                json={"format": "json"},
                content_type="application/json",
            )

        assert rv.status_code == 500
        assert "Export failed" in rv.get_json()["error"]


# ---------------------------------------------------------------------------
# 9. Export ZIP
# ---------------------------------------------------------------------------


class TestExportZip:
    """POST /api/v1/integrations/export/zip"""

    def test_missing_formats_returns_400(self, client):
        rv = client.post(
            "/api/v1/integrations/export/zip",
            json={},
            content_type="application/json",
        )
        assert rv.status_code == 400
        assert "formats" in rv.get_json()["error"]

    def test_empty_formats_returns_400(self, client):
        rv = client.post(
            "/api/v1/integrations/export/zip",
            json={"formats": []},
            content_type="application/json",
        )
        assert rv.status_code == 400

    def test_invalid_format_in_list_returns_400(self, client):
        rv = client.post(
            "/api/v1/integrations/export/zip",
            json={"formats": ["json", "yaml"]},
            content_type="application/json",
        )
        assert rv.status_code == 400
        assert "yaml" in rv.get_json()["error"]

    def test_multiple_invalid_formats_returns_400(self, client):
        rv = client.post(
            "/api/v1/integrations/export/zip",
            json={"formats": ["xml", "toml"]},
            content_type="application/json",
        )
        assert rv.status_code == 400
        error_msg = rv.get_json()["error"]
        assert "toml" in error_msg
        assert "xml" in error_msg

    def test_successful_zip_export(self, client):
        fake_zip = b"PK\x03\x04fake-zip-content"
        with patch("export_manager.export_to_zip", return_value=fake_zip):
            rv = client.post(
                "/api/v1/integrations/export/zip",
                json={"formats": ["json", "bazarr"]},
                content_type="application/json",
            )

        assert rv.status_code == 200
        assert rv.content_type == "application/zip"
        assert rv.data == fake_zip
        assert "sublarr_export.zip" in rv.headers["Content-Disposition"]

    def test_include_secrets_passed_through(self, client):
        with patch(
            "export_manager.export_to_zip", return_value=b"zip"
        ) as mock_fn:
            client.post(
                "/api/v1/integrations/export/zip",
                json={"formats": ["json"], "include_secrets": True},
                content_type="application/json",
            )

        mock_fn.assert_called_once_with(["json"], include_secrets=True)

    def test_zip_export_exception_returns_500(self, client):
        with patch(
            "export_manager.export_to_zip",
            side_effect=RuntimeError("zip error"),
        ):
            rv = client.post(
                "/api/v1/integrations/export/zip",
                json={"formats": ["json"]},
                content_type="application/json",
            )

        assert rv.status_code == 500
        assert "ZIP export failed" in rv.get_json()["error"]


# ---------------------------------------------------------------------------
# 10. Aggregated Health: All Services
# ---------------------------------------------------------------------------


class TestHealthAll:
    """GET /api/v1/integrations/health/all"""

    def test_all_services_empty(self, client):
        """When no services configured, returns empty collections."""
        with (
            patch("config.get_sonarr_instances", return_value=[]),
            patch("config.get_radarr_instances", return_value=[]),
            patch(
                "mediaserver.get_media_server_manager",
                return_value=self._empty_manager(),
            ),
        ):
            rv = client.get("/api/v1/integrations/health/all")

        assert rv.status_code == 200
        data = rv.get_json()
        assert data["sonarr"] == []
        assert data["radarr"] == []
        assert data["media_servers"] == []
        # jellyfin should indicate not configured
        assert data["jellyfin"]["connection"]["healthy"] is False

    def test_all_services_with_data(self, client):
        """Aggregated endpoint returns data from all services."""
        sonarr_instances = [
            {"name": "S1", "url": "http://s:8989", "api_key": "a"},
        ]
        radarr_instances = [
            {"name": "R1", "url": "http://r:7878", "api_key": "b"},
        ]

        mock_sonarr_client = MagicMock()
        mock_sonarr_client.extended_health_check.return_value = {
            "connection": {"healthy": True, "message": "OK"}
        }
        mock_radarr_client = MagicMock()
        mock_radarr_client.extended_health_check.return_value = {
            "connection": {"healthy": True, "message": "OK"}
        }

        mock_jf = MagicMock()
        type(mock_jf).name = "jellyfin"
        mock_jf.health_check.return_value = (True, "Connected")
        mock_jf.config = {"name": "JF"}

        mock_plex = MagicMock(spec=["health_check", "config"])
        type(mock_plex).name = "plex"
        mock_plex.health_check.return_value = (True, "OK")
        mock_plex.config = {"name": "Plex"}
        del mock_plex.extended_health_check

        manager = MagicMock()
        manager._instances = {"jf1": mock_jf, "plex1": mock_plex}
        manager._instance_enabled = {"jf1": True, "plex1": True}

        with (
            patch("config.get_sonarr_instances", return_value=sonarr_instances),
            patch("config.get_radarr_instances", return_value=radarr_instances),
            patch("sonarr_client.SonarrClient", return_value=mock_sonarr_client),
            patch("radarr_client.RadarrClient", return_value=mock_radarr_client),
            patch("mediaserver.get_media_server_manager", return_value=manager),
        ):
            rv = client.get("/api/v1/integrations/health/all")

        assert rv.status_code == 200
        data = rv.get_json()
        assert len(data["sonarr"]) == 1
        assert len(data["radarr"]) == 1
        assert data["jellyfin"]["connection"]["healthy"] is True
        assert len(data["media_servers"]) == 2

    def test_partial_failure_still_returns_other_results(self, client):
        """If sonarr config fails, other services still report."""
        radarr_instances = [
            {"name": "R1", "url": "http://r:7878", "api_key": "b"},
        ]
        mock_radarr_client = MagicMock()
        mock_radarr_client.extended_health_check.return_value = {
            "connection": {"healthy": True, "message": "OK"}
        }

        with (
            patch(
                "config.get_sonarr_instances",
                side_effect=RuntimeError("sonarr config error"),
            ),
            patch("config.get_radarr_instances", return_value=radarr_instances),
            patch("radarr_client.RadarrClient", return_value=mock_radarr_client),
            patch(
                "mediaserver.get_media_server_manager",
                return_value=self._empty_manager(),
            ),
        ):
            rv = client.get("/api/v1/integrations/health/all")

        assert rv.status_code == 200
        data = rv.get_json()
        # Sonarr failed gracefully -- returns empty
        assert data["sonarr"] == []
        # Radarr still worked
        assert len(data["radarr"]) == 1

    # -- helpers --

    @staticmethod
    def _empty_manager():
        manager = MagicMock()
        manager._instances = {}
        manager._instance_enabled = {}
        return manager
