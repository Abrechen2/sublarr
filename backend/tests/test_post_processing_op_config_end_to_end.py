"""Plan B6 follow-up — end-to-end integration: API PUT → pipeline run → op gets config."""

from __future__ import annotations

from unittest.mock import patch


def test_api_put_config_is_consumed_by_pipeline(client, tmp_path):
    """Operator configures discord_notify via the PUT endpoint, then the
    pipeline runs with the after_download trigger and the op receives
    the configured webhook URL at execute() time.
    """
    # 1. Configure the trigger to include discord_notify
    cfg_resp = client.put(
        "/api/v1/post-processing/config/after_download",
        json={"op_ids": ["discord_notify"]},
    )
    assert cfg_resp.status_code == 200

    # 2. Configure discord_notify with a webhook URL
    put = client.put(
        "/api/v1/post-processing/ops/discord_notify/config",
        json={"values": {"webhook_url": "https://discord.com/api/webhooks/77/real-secret"}},
    )
    assert put.status_code == 200

    # 3. The GET response masks the password (no plaintext leaked)
    got = client.get("/api/v1/post-processing/ops/discord_notify/config")
    assert got.status_code == 200
    assert got.get_json()["values"]["webhook_url"] == "***"

    # 4. Run the pipeline — the op must see the real stored URL
    captured: dict = {}

    def _fake_post(url, *args, **kwargs):
        captured["url"] = url
        captured["json"] = kwargs.get("json")

        class _R:
            status_code = 204
            text = ""

        return _R()

    from post_processing.pipeline import PostProcessingPipeline

    with patch("post_processing.ops.discord_notify.requests.post", side_effect=_fake_post):
        pipe = PostProcessingPipeline()
        results = pipe.run(
            trigger="after_download",
            op_ids=["discord_notify"],
            context={
                "subtitle_path": str(tmp_path / "ep1.en.srt"),
                "video_path": str(tmp_path / "ep1.mkv"),
                "lang": "en",
                "score": 120,
                "trigger": "after_download",
            },
        )

    assert len(results) == 1
    assert results[0].ok, results[0].message
    assert captured["url"] == "https://discord.com/api/webhooks/77/real-secret"


def test_api_config_defaults_cause_op_to_fail_closed(client, tmp_path):
    """Without a stored URL, DiscordNotifyOp's own execute() returns ok=False.

    This is what caused the original B6 follow-up bug: the pipeline ran ops
    with class-default empty strings. With config wiring, the op still
    fails closed — but for the correct reason (operator has not configured
    the op yet), not for a code bug.
    """
    from post_processing.pipeline import PostProcessingPipeline

    pipe = PostProcessingPipeline()
    results = pipe.run(
        trigger="after_download",
        op_ids=["discord_notify"],
        context={
            "subtitle_path": str(tmp_path / "x.srt"),
            "video_path": str(tmp_path / "x.mkv"),
            "lang": "en",
            "score": 0,
            "trigger": "after_download",
        },
    )
    assert len(results) == 1
    assert results[0].ok is False
    assert "webhook_url" in results[0].message.lower() or "webhook" in results[0].message.lower()
