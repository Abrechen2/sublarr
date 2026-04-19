"""Plan B6 — HTTP ops tests (webhook + discord_notify)."""

from unittest.mock import patch


def test_webhook_op_posts_to_url():
    from post_processing.ops.webhook import WebhookOp

    op = WebhookOp()
    op.url = "http://example.com/hook"  # injected via op config in real usage
    op.method = "POST"
    op.template = '{"file": "{subtitle_path}", "lang": "{lang}"}'

    with patch("post_processing.ops.webhook.requests.request") as mock_req:
        mock_req.return_value.status_code = 200
        mock_req.return_value.text = "ok"

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
    mock_req.assert_called_once()
    # Body was substituted
    _, kwargs = mock_req.call_args
    body_repr = str(kwargs.get("json") or kwargs.get("data") or "")
    assert "/m/s.srt" in body_repr


def test_webhook_op_rejects_file_url():
    """SSRF protection — webhook must use validate_service_url (blocks file://)."""
    from post_processing.ops.webhook import WebhookOp

    op = WebhookOp()
    op.url = "file:///etc/passwd"
    op.method = "GET"
    op.template = ""

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
    assert (
        "ssrf" in result.message.lower()
        or "scheme" in result.message.lower()
        or "invalid" in result.message.lower()
        or "rejected" in result.message.lower()
    )


def test_webhook_op_missing_url():
    """No url configured = fail-closed."""
    from post_processing.ops.webhook import WebhookOp

    op = WebhookOp()
    # Leave url empty
    result = op.execute(
        {
            "subtitle_path": "/m/s.srt",
            "video_path": "/m/v.mkv",
            "lang": "en",
            "score": 0,
            "trigger": "after_download",
        }
    )
    assert result.ok is False
    assert "url" in result.message.lower()


def test_discord_notify_op_uses_discord_format():
    from post_processing.ops.discord_notify import DiscordNotifyOp

    op = DiscordNotifyOp()
    op.webhook_url = "https://discord.com/api/webhooks/123/abc"

    with patch("post_processing.ops.discord_notify.requests.post") as mock_post:
        mock_post.return_value.status_code = 204
        mock_post.return_value.text = ""

        result = op.execute(
            {
                "subtitle_path": "/m/S01E01.en.srt",
                "video_path": "/m/S01E01.mkv",
                "lang": "en",
                "score": 120,
                "trigger": "after_download",
            }
        )

    assert result.ok
    _, kwargs = mock_post.call_args
    payload = kwargs.get("json", {})
    assert "content" in payload or "embeds" in payload


def test_discord_notify_op_rejects_non_discord_url():
    from post_processing.ops.discord_notify import DiscordNotifyOp

    op = DiscordNotifyOp()
    op.webhook_url = "https://evil.example.com/hook"
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
    assert "discord" in result.message.lower() or "invalid" in result.message.lower()
