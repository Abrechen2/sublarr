"""Tests for the shared media-server refresh helper."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch


def test_notify_empty_path_is_noop():
    from services.media_server_notify import notify_media_servers

    with patch("mediaserver.get_media_server_manager") as gm:
        notify_media_servers("")
    gm.assert_not_called()


def test_notify_calls_refresh_all():
    from services.media_server_notify import notify_media_servers

    manager = MagicMock()
    manager.refresh_all.return_value = [
        SimpleNamespace(success=True, message="ok"),
    ]
    with patch("mediaserver.get_media_server_manager", return_value=manager):
        notify_media_servers("/media/show/ep.mkv", "episode")

    manager.refresh_all.assert_called_once_with("/media/show/ep.mkv", "episode")


def test_notify_swallows_exceptions():
    from services.media_server_notify import notify_media_servers

    with patch("mediaserver.get_media_server_manager", side_effect=RuntimeError("boom")):
        # Must not raise — refresh is best-effort.
        notify_media_servers("/media/show/ep.mkv")
