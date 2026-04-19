"""Plan B6 — media server refresh ops."""

from unittest.mock import patch


def test_plex_refresh_posts_to_plex():
    from post_processing.ops.media_server_refresh import PlexRefreshOp

    op = PlexRefreshOp()
    op.base_url = "http://plex:32400"
    op.token = "abc123"

    with patch("post_processing.ops.media_server_refresh.requests.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.text = "<xml/>"
        result = op.execute(
            {
                "subtitle_path": "/m/s.srt",
                "video_path": "/m/v.mkv",
                "lang": "en",
                "score": 100,
                "trigger": "after_download",
            }
        )

    assert result.ok
    mock_get.assert_called_once()
    call_args = mock_get.call_args
    headers = call_args.kwargs.get("headers") or {}
    assert headers.get("X-Plex-Token") == "abc123"


def test_plex_refresh_missing_config():
    from post_processing.ops.media_server_refresh import PlexRefreshOp

    op = PlexRefreshOp()
    result = op.execute(
        {
            "subtitle_path": "/m/s.srt",
            "video_path": "/m/v.mkv",
            "lang": "en",
            "score": 100,
            "trigger": "after_download",
        }
    )
    assert result.ok is False
    assert "plex" in result.message.lower() or "configured" in result.message.lower()


def test_emby_refresh_posts_to_emby():
    from post_processing.ops.media_server_refresh import EmbyRefreshOp

    op = EmbyRefreshOp()
    op.base_url = "http://emby:8096"
    op.api_key = "xyz789"

    with patch("post_processing.ops.media_server_refresh.requests.post") as mock_post:
        mock_post.return_value.status_code = 204
        mock_post.return_value.text = ""
        result = op.execute(
            {
                "subtitle_path": "/m/s.srt",
                "video_path": "/m/v.mkv",
                "lang": "en",
                "score": 100,
                "trigger": "after_download",
            }
        )

    assert result.ok
    mock_post.assert_called_once()
    call_args = mock_post.call_args
    assert "api_key" in (call_args.kwargs.get("params") or {})


def test_jellyfin_refresh_posts_to_jellyfin():
    from post_processing.ops.media_server_refresh import JellyfinRefreshOp

    op = JellyfinRefreshOp()
    op.base_url = "http://jellyfin:8096"
    op.api_key = "jelly-xyz"

    with patch("post_processing.ops.media_server_refresh.requests.post") as mock_post:
        mock_post.return_value.status_code = 204
        mock_post.return_value.text = ""
        result = op.execute(
            {
                "subtitle_path": "/m/s.srt",
                "video_path": "/m/v.mkv",
                "lang": "en",
                "score": 100,
                "trigger": "after_download",
            }
        )

    assert result.ok
    mock_post.assert_called_once()
    headers = mock_post.call_args.kwargs.get("headers") or {}
    assert headers.get("X-MediaBrowser-Token") == "jelly-xyz"


def test_media_refresh_handles_http_error():
    from post_processing.ops.media_server_refresh import PlexRefreshOp

    op = PlexRefreshOp()
    op.base_url = "http://plex:32400"
    op.token = "abc123"
    with patch("post_processing.ops.media_server_refresh.requests.get") as mock_get:
        mock_get.return_value.status_code = 500
        mock_get.return_value.text = "err"
        result = op.execute(
            {
                "subtitle_path": "",
                "video_path": "",
                "lang": "en",
                "score": 0,
                "trigger": "after_download",
            }
        )
    assert result.ok is False
    assert "500" in result.message
