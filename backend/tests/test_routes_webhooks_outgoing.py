"""Tests for routes/webhooks.py -- Sonarr, Radarr, and Jellyfin webhook endpoints."""

import os
import sys
import tempfile
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_TEMP_DIR = os.path.realpath(tempfile.gettempdir())


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def client(temp_db):
    from app import create_app

    app = create_app(testing=True)
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _settings_mock(**overrides):
    """Build a settings mock with sensible defaults."""
    defaults = {
        "api_key": "test-api-key",
        "media_path": _TEMP_DIR,
        "webhook_delay_minutes": 0,
        "webhook_auto_scan": False,
        "webhook_auto_search": False,
        "webhook_auto_translate": False,
        "jellyfin_play_translate_enabled": False,
    }
    defaults.update(overrides)
    mock = MagicMock()
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


# ---------------------------------------------------------------------------
# TestSonarrWebhook — POST /api/v1/webhook/sonarr
# ---------------------------------------------------------------------------


class TestSonarrWebhook:
    def test_401_when_no_api_key(self, client):
        with patch("config.get_settings", return_value=_settings_mock()):
            resp = client.post(
                "/api/v1/webhook/sonarr",
                json={"eventType": "Test"},
            )
        assert resp.status_code == 401

    def test_401_when_wrong_api_key(self, client):
        with patch("config.get_settings", return_value=_settings_mock()):
            resp = client.post(
                "/api/v1/webhook/sonarr",
                json={"eventType": "Test"},
                headers={"X-Api-Key": "wrong-key"},
            )
        assert resp.status_code == 401

    def test_200_on_test_event(self, client):
        with patch("config.get_settings", return_value=_settings_mock()):
            resp = client.post(
                "/api/v1/webhook/sonarr",
                json={"eventType": "Test"},
                headers={"X-Api-Key": "test-api-key"},
            )
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "ok"

    def test_200_on_unknown_event_type(self, client):
        with patch("config.get_settings", return_value=_settings_mock()):
            resp = client.post(
                "/api/v1/webhook/sonarr",
                json={"eventType": "Rename"},
                headers={"X-Api-Key": "test-api-key"},
            )
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "ignored"

    def test_download_without_a_file_path_is_ignored_not_rejected(self, client):
        """Was a 400 until 2026-08-15. Sonarr fires a Download event for every
        completed download, including ones whose import produced no file, and
        rejecting those made it mark the notification broken. Full reasoning
        and the surrounding cases live in
        tests/test_webhook_no_file_path_is_ignored.py.
        """
        with patch("config.get_settings", return_value=_settings_mock()):
            resp = client.post(
                "/api/v1/webhook/sonarr",
                json={
                    "eventType": "Download",
                    "series": {"id": 1, "title": "Test"},
                    "episodeFile": {},
                },
                headers={"X-Api-Key": "test-api-key"},
            )
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "ignored"
        assert "file path" in resp.get_json()["reason"].lower()

    def test_400_when_path_outside_media(self, client):
        with (
            patch("config.get_settings", return_value=_settings_mock()),
            patch("config.map_path", return_value="/etc/passwd"),
        ):
            resp = client.post(
                "/api/v1/webhook/sonarr",
                json={
                    "eventType": "Download",
                    "series": {"id": 1, "title": "Test"},
                    "episodeFile": {"path": "/etc/passwd"},
                },
                headers={"X-Api-Key": "test-api-key"},
            )
        assert resp.status_code == 400
        assert "media_path" in resp.get_json()["error"]

    def test_202_on_download_event(self, client, tmp_path):
        file_path = os.path.join(_TEMP_DIR, "show", "ep01.mkv")
        settings = _settings_mock()
        with (
            patch("config.get_settings", return_value=settings),
            patch("config.map_path", return_value=file_path),
            patch("routes.webhooks._webhook_auto_pipeline"),
        ):
            resp = client.post(
                "/api/v1/webhook/sonarr",
                json={
                    "eventType": "Download",
                    "series": {"id": 1, "title": "My Show"},
                    "episodeFile": {"path": file_path},
                },
                headers={"X-Api-Key": "test-api-key"},
            )
        assert resp.status_code == 202
        data = resp.get_json()
        assert data["status"] == "queued"
        assert "file_path" in data


# ---------------------------------------------------------------------------
# TestRadarrWebhook — POST /api/v1/webhook/radarr
# ---------------------------------------------------------------------------


class TestRadarrWebhook:
    def test_401_without_api_key(self, client):
        with patch("config.get_settings", return_value=_settings_mock()):
            resp = client.post(
                "/api/v1/webhook/radarr",
                json={"eventType": "Test"},
            )
        assert resp.status_code == 401

    def test_200_on_test_event(self, client):
        with patch("config.get_settings", return_value=_settings_mock()):
            resp = client.post(
                "/api/v1/webhook/radarr",
                json={"eventType": "Test"},
                headers={"X-Api-Key": "test-api-key"},
            )
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "ok"

    def test_200_on_unknown_event(self, client):
        with patch("config.get_settings", return_value=_settings_mock()):
            resp = client.post(
                "/api/v1/webhook/radarr",
                json={"eventType": "Rename"},
                headers={"X-Api-Key": "test-api-key"},
            )
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "ignored"

    def test_download_no_file_path_is_ignored_not_rejected(self, client):
        """Matches the Sonarr handler, and the MovieFileDelete branch that
        already answered 200/ignored for the same situation.
        """
        with patch("config.get_settings", return_value=_settings_mock()):
            resp = client.post(
                "/api/v1/webhook/radarr",
                json={
                    "eventType": "Download",
                    "movie": {"id": 1, "title": "Film"},
                    "movieFile": {},
                },
                headers={"X-Api-Key": "test-api-key"},
            )
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "ignored"

    def test_202_on_download_event(self, client):
        file_path = os.path.join(_TEMP_DIR, "movies", "film.mkv")
        settings = _settings_mock()
        with (
            patch("config.get_settings", return_value=settings),
            patch("config.map_path", return_value=file_path),
            patch("routes.webhooks._webhook_auto_pipeline"),
        ):
            resp = client.post(
                "/api/v1/webhook/radarr",
                json={
                    "eventType": "Download",
                    "movie": {"id": 1, "title": "Film"},
                    "movieFile": {"path": file_path},
                },
                headers={"X-Api-Key": "test-api-key"},
            )
        assert resp.status_code == 202
        assert resp.get_json()["status"] == "queued"

    def test_movie_file_delete_event(self, client):
        file_path = os.path.join(_TEMP_DIR, "movies", "old.mkv")
        with (
            patch("config.get_settings", return_value=_settings_mock()),
            patch("config.map_path", return_value=file_path),
            patch("db.wanted.delete_wanted_items", return_value=2),
        ):
            resp = client.post(
                "/api/v1/webhook/radarr",
                json={
                    "eventType": "MovieFileDelete",
                    "movie": {"id": 1, "title": "Old Film"},
                    "movieFile": {"path": file_path},
                },
                headers={"X-Api-Key": "test-api-key"},
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "deleted"
        assert data["wanted_items_removed"] == 2

    def test_movie_file_delete_no_path(self, client):
        with patch("config.get_settings", return_value=_settings_mock()):
            resp = client.post(
                "/api/v1/webhook/radarr",
                json={
                    "eventType": "MovieFileDelete",
                    "movie": {"id": 1, "title": "Film"},
                    "movieFile": {},
                },
                headers={"X-Api-Key": "test-api-key"},
            )
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "ignored"

    def test_movie_file_delete_path_outside_media(self, client):
        with (
            patch("config.get_settings", return_value=_settings_mock()),
            patch("config.map_path", return_value="/etc/shadow"),
        ):
            resp = client.post(
                "/api/v1/webhook/radarr",
                json={
                    "eventType": "MovieFileDelete",
                    "movie": {"id": 1, "title": "Film"},
                    "movieFile": {"path": "/etc/shadow"},
                },
                headers={"X-Api-Key": "test-api-key"},
            )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# TestJellyfinWebhook — POST /api/v1/webhook/jellyfin
# ---------------------------------------------------------------------------


class TestJellyfinWebhook:
    def test_401_without_api_key(self, client):
        with patch("config.get_settings", return_value=_settings_mock()):
            resp = client.post(
                "/api/v1/webhook/jellyfin",
                json={"NotificationType": "Test"},
            )
        assert resp.status_code == 401

    def test_200_disabled_by_default(self, client):
        settings = _settings_mock(jellyfin_play_translate_enabled=False)
        with patch("config.get_settings", return_value=settings):
            resp = client.post(
                "/api/v1/webhook/jellyfin",
                json={"NotificationType": "PlaybackStart"},
                headers={"X-Api-Key": "test-api-key"},
            )
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "disabled"

    def test_200_on_test_event(self, client):
        settings = _settings_mock(jellyfin_play_translate_enabled=True)
        with patch("config.get_settings", return_value=settings):
            resp = client.post(
                "/api/v1/webhook/jellyfin",
                json={"NotificationType": "Test"},
                headers={"X-Api-Key": "test-api-key"},
            )
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "ok"

    def test_200_ignored_event_type(self, client):
        settings = _settings_mock(jellyfin_play_translate_enabled=True)
        with patch("config.get_settings", return_value=settings):
            resp = client.post(
                "/api/v1/webhook/jellyfin",
                json={"NotificationType": "SessionStart"},
                headers={"X-Api-Key": "test-api-key"},
            )
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "ignored"

    def test_400_no_item_id(self, client):
        settings = _settings_mock(jellyfin_play_translate_enabled=True)
        with patch("config.get_settings", return_value=settings):
            resp = client.post(
                "/api/v1/webhook/jellyfin",
                json={"NotificationType": "PlaybackStart", "ItemId": ""},
                headers={"X-Api-Key": "test-api-key"},
            )
        assert resp.status_code == 400

    def test_404_when_path_not_resolved(self, client):
        settings = _settings_mock(jellyfin_play_translate_enabled=True)
        mock_manager = MagicMock()
        mock_manager.get_item_path_from_jellyfin.return_value = None
        with (
            patch("config.get_settings", return_value=settings),
            patch("mediaserver.get_media_server_manager", return_value=mock_manager),
        ):
            resp = client.post(
                "/api/v1/webhook/jellyfin",
                json={
                    "NotificationType": "PlaybackStart",
                    "ItemId": "abc123",
                    "Name": "Episode",
                },
                headers={"X-Api-Key": "test-api-key"},
            )
        assert resp.status_code == 404

    def test_403_when_path_outside_media(self, client):
        settings = _settings_mock(jellyfin_play_translate_enabled=True)
        mock_manager = MagicMock()
        mock_manager.get_item_path_from_jellyfin.return_value = "/etc/passwd"
        with (
            patch("config.get_settings", return_value=settings),
            patch("mediaserver.get_media_server_manager", return_value=mock_manager),
        ):
            resp = client.post(
                "/api/v1/webhook/jellyfin",
                json={
                    "NotificationType": "PlaybackStart",
                    "ItemId": "abc123",
                    "Name": "Episode",
                },
                headers={"X-Api-Key": "test-api-key"},
            )
        assert resp.status_code == 403

    def test_202_on_playback_start(self, client):
        file_path = os.path.join(_TEMP_DIR, "anime", "ep01.mkv")
        settings = _settings_mock(jellyfin_play_translate_enabled=True)
        mock_manager = MagicMock()
        mock_manager.get_item_path_from_jellyfin.return_value = file_path
        with (
            patch("config.get_settings", return_value=settings),
            patch("mediaserver.get_media_server_manager", return_value=mock_manager),
            patch("routes.webhooks._webhook_auto_pipeline"),
        ):
            resp = client.post(
                "/api/v1/webhook/jellyfin",
                json={
                    "NotificationType": "PlaybackStart",
                    "ItemId": "abc123",
                    "Name": "Episode 1",
                    "SeriesName": "My Anime",
                },
                headers={"X-Api-Key": "test-api-key"},
            )
        assert resp.status_code == 202
        data = resp.get_json()
        assert data["status"] == "queued"
        assert data["title"] == "My Anime — Episode 1"
