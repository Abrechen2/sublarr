"""Tests for Jellyfin play-start webhook and path lookup.

Run:
    pytest tests/test_jellyfin_play_webhook.py -v
"""

from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# JellyfinEmbyServer.get_item_path_by_id
# ---------------------------------------------------------------------------


class TestGetItemPathById:
    """Unit tests for the Jellyfin item-path lookup method."""

    def _make_server(self):
        from mediaserver.jellyfin import JellyfinEmbyServer

        return JellyfinEmbyServer(url="http://jf:8096", api_key="key123")

    def test_returns_path_on_success(self):
        server = self._make_server()
        server._get = MagicMock(return_value={"Id": "abc", "Path": "/media/show/ep01.mkv"})

        result = server.get_item_path_by_id("abc")

        assert result == "/media/show/ep01.mkv"
        server._get.assert_called_once_with("/Items/abc", params={"Fields": "Path"})

    def test_returns_none_when_api_fails(self):
        server = self._make_server()
        server._get = MagicMock(return_value=None)

        result = server.get_item_path_by_id("abc")

        assert result is None

    def test_returns_none_when_path_missing(self):
        server = self._make_server()
        server._get = MagicMock(return_value={"Id": "abc"})

        result = server.get_item_path_by_id("abc")

        assert result is None


# ---------------------------------------------------------------------------
# MediaServerManager.get_item_path_from_jellyfin
# ---------------------------------------------------------------------------


class TestGetItemPathFromJellyfin:
    """Unit tests for the manager-level path resolution."""

    def _make_manager_with_instance(self, instance):
        from mediaserver import MediaServerManager

        mgr = MediaServerManager()
        mgr._instances = {"jellyfin_0": instance}
        mgr._instance_enabled = {"jellyfin_0": True}
        return mgr

    def test_returns_path_from_first_jellyfin_instance(self):
        from mediaserver.jellyfin import JellyfinEmbyServer

        inst = MagicMock(spec=JellyfinEmbyServer)
        inst.get_item_path_by_id.return_value = "/media/ep.mkv"

        mgr = self._make_manager_with_instance(inst)
        result = mgr.get_item_path_from_jellyfin("item123")

        assert result == "/media/ep.mkv"
        inst.get_item_path_by_id.assert_called_once_with("item123")

    def test_skips_disabled_instances(self):
        from mediaserver.jellyfin import JellyfinEmbyServer

        inst = MagicMock(spec=JellyfinEmbyServer)
        inst.get_item_path_by_id.return_value = "/media/ep.mkv"

        from mediaserver import MediaServerManager

        mgr = MediaServerManager()
        mgr._instances = {"jellyfin_0": inst}
        mgr._instance_enabled = {"jellyfin_0": False}

        result = mgr.get_item_path_from_jellyfin("item123")

        assert result is None
        inst.get_item_path_by_id.assert_not_called()

    def test_returns_none_when_no_instances(self):
        from mediaserver import MediaServerManager

        mgr = MediaServerManager()
        # Prevent load_instances from hitting DB
        mgr._instances = {"jellyfin_0": MagicMock()}  # non-Jellyfin type
        mgr._instance_enabled = {"jellyfin_0": True}

        result = mgr.get_item_path_from_jellyfin("item123")

        assert result is None


# ---------------------------------------------------------------------------
# POST /api/v1/webhook/jellyfin
# ---------------------------------------------------------------------------


@pytest.fixture()
def app():
    """Minimal Flask app with the webhooks blueprint."""
    import os

    os.environ.setdefault("SUBLARR_MEDIA_PATH", "/media")
    os.environ["SUBLARR_DB_PATH"] = ":memory:"

    from config import reload_settings

    reload_settings()
    from app import create_app

    application = create_app(testing=True)
    application.config["TESTING"] = True
    return application


@pytest.fixture()
def client(app):
    return app.test_client()


class TestJellyfinWebhookRoute:
    """Integration tests for the /webhook/jellyfin endpoint."""

    _TEST_API_KEY = "test-webhook-key"
    _AUTH_HEADERS = {"X-Api-Key": _TEST_API_KEY}

    def test_returns_disabled_when_feature_off(self, client):
        with patch("config.get_settings") as mock_settings:
            s = MagicMock()
            s.jellyfin_play_translate_enabled = False
            s.api_key = self._TEST_API_KEY
            mock_settings.return_value = s

            resp = client.post(
                "/api/v1/webhook/jellyfin",
                json={"NotificationType": "PlaybackStart", "ItemId": "abc"},
                headers=self._AUTH_HEADERS,
            )

        assert resp.status_code == 200
        assert resp.get_json()["status"] == "disabled"

    def test_acknowledges_test_event(self, client):
        with patch("config.get_settings") as mock_settings:
            s = MagicMock()
            s.jellyfin_play_translate_enabled = True
            s.api_key = self._TEST_API_KEY
            mock_settings.return_value = s

            resp = client.post(
                "/api/v1/webhook/jellyfin",
                json={"NotificationType": "Test"},
                headers=self._AUTH_HEADERS,
            )

        assert resp.status_code == 200
        assert resp.get_json()["status"] == "ok"

    def test_ignores_non_playback_events(self, client):
        with patch("config.get_settings") as mock_settings:
            s = MagicMock()
            s.jellyfin_play_translate_enabled = True
            s.api_key = self._TEST_API_KEY
            mock_settings.return_value = s

            resp = client.post(
                "/api/v1/webhook/jellyfin",
                json={"NotificationType": "PlaybackStop", "ItemId": "abc"},
                headers=self._AUTH_HEADERS,
            )

        assert resp.status_code == 200
        assert resp.get_json()["status"] == "ignored"

    def test_returns_400_when_item_id_missing(self, client):
        with patch("config.get_settings") as mock_settings:
            s = MagicMock()
            s.jellyfin_play_translate_enabled = True
            s.api_key = self._TEST_API_KEY
            mock_settings.return_value = s

            resp = client.post(
                "/api/v1/webhook/jellyfin",
                json={"NotificationType": "PlaybackStart"},
                headers=self._AUTH_HEADERS,
            )

        assert resp.status_code == 400

    def test_returns_404_when_path_unresolvable(self, client):
        with (
            patch("config.get_settings") as mock_settings,
            patch("mediaserver.get_media_server_manager") as mock_mgr,
        ):
            s = MagicMock()
            s.jellyfin_play_translate_enabled = True
            s.api_key = self._TEST_API_KEY
            mock_settings.return_value = s

            mgr = MagicMock()
            mgr.get_item_path_from_jellyfin.return_value = None
            mock_mgr.return_value = mgr

            resp = client.post(
                "/api/v1/webhook/jellyfin",
                json={"NotificationType": "PlaybackStart", "ItemId": "abc123"},
                headers=self._AUTH_HEADERS,
            )

        assert resp.status_code == 404

    def test_queues_pipeline_on_valid_event(self, client):
        with (
            patch("config.get_settings") as mock_settings,
            patch("mediaserver.get_media_server_manager") as mock_mgr,
            patch("security_utils.is_safe_path", return_value=True),
            # Patch the spawn helper directly — avoids colliding with flask-limiter's
            # internal use of threading.Timer (subclass of Thread) when the per-route
            # rate limit fires its in-memory expiry timer.
            patch("routes.webhooks.jellyfin._spawn_pipeline") as mock_spawn,
        ):
            s = MagicMock()
            s.jellyfin_play_translate_enabled = True
            s.api_key = self._TEST_API_KEY
            s.media_path = "/media"
            mock_settings.return_value = s

            mgr = MagicMock()
            mgr.get_item_path_from_jellyfin.return_value = "/media/show/ep01.mkv"
            mock_mgr.return_value = mgr

            resp = client.post(
                "/api/v1/webhook/jellyfin",
                json={
                    "NotificationType": "PlaybackStart",
                    "ItemId": "abc123",
                    "Name": "Episode 1",
                    "SeriesName": "My Show",
                },
                headers=self._AUTH_HEADERS,
            )

        assert resp.status_code == 202
        data = resp.get_json()
        assert data["status"] == "queued"
        assert data["file_path"] == "/media/show/ep01.mkv"
        assert "My Show" in data["title"]
        # _spawn_pipeline was invoked exactly once with the resolved path/title.
        mock_spawn.assert_called_once()
        spawn_args, _ = mock_spawn.call_args
        assert spawn_args[0] == "/media/show/ep01.mkv"
        assert "My Show" in spawn_args[1]

    def test_rejects_request_without_api_key(self, client):
        """Webhook must return 401 when no API key header is provided."""
        with patch("config.get_settings") as mock_settings:
            s = MagicMock()
            s.jellyfin_play_translate_enabled = True
            s.api_key = self._TEST_API_KEY
            mock_settings.return_value = s

            resp = client.post(
                "/api/v1/webhook/jellyfin",
                json={"NotificationType": "Test"},
            )

        assert resp.status_code == 401

    def test_rejects_request_when_no_key_configured(self, client):
        """Webhook must return 401 when api_key is not configured (empty)."""
        with patch("config.get_settings") as mock_settings:
            s = MagicMock()
            s.jellyfin_play_translate_enabled = True
            s.api_key = ""
            mock_settings.return_value = s

            resp = client.post(
                "/api/v1/webhook/jellyfin",
                json={"NotificationType": "Test"},
            )

        assert resp.status_code == 401
