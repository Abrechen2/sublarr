"""Plan B6 follow-up — pipeline injects config onto op instance before execute()."""

from __future__ import annotations

from unittest.mock import patch


def test_configure_op_instance_populates_attrs(app_ctx):
    from post_processing.config_store import set_op_config
    from post_processing.ops.discord_notify import DiscordNotifyOp
    from post_processing.pipeline import _configure_op_instance

    set_op_config(
        "discord_notify",
        {"webhook_url": "https://discord.com/api/webhooks/1/abc"},
    )
    inst = DiscordNotifyOp()
    assert inst.webhook_url == ""  # class default
    _configure_op_instance(inst)
    assert inst.webhook_url == "https://discord.com/api/webhooks/1/abc"


def test_configure_op_instance_leaves_defaults_when_unset(app_ctx):
    from post_processing.ops.webhook import WebhookOp
    from post_processing.pipeline import _configure_op_instance

    inst = WebhookOp()
    _configure_op_instance(inst)
    # Nothing configured → class defaults preserved
    assert inst.url == ""
    assert inst.method == "POST"


def test_pipeline_injects_config_before_execute(app_ctx, tmp_path):
    """End-to-end: store config, run pipeline, op sees configured values."""
    from post_processing.config_store import set_op_config, set_trigger_ops
    from post_processing.pipeline import PostProcessingPipeline

    set_op_config(
        "discord_notify",
        {"webhook_url": "https://discord.com/api/webhooks/9/xyz"},
    )
    set_trigger_ops("after_download", ["discord_notify"])

    captured: dict = {}

    def _fake_post(url, *args, **kwargs):
        captured["url"] = url
        captured["json"] = kwargs.get("json")

        class _R:
            status_code = 204
            text = ""

        return _R()

    with patch("post_processing.ops.discord_notify.requests.post", side_effect=_fake_post):
        pipe = PostProcessingPipeline()
        results = pipe.run(
            trigger="after_download",
            op_ids=["discord_notify"],
            context={
                "subtitle_path": str(tmp_path / "s.srt"),
                "video_path": str(tmp_path / "v.mkv"),
                "lang": "en",
                "score": 100,
                "trigger": "after_download",
            },
        )

    assert len(results) == 1
    assert results[0].ok, results[0].message
    assert captured["url"] == "https://discord.com/api/webhooks/9/xyz"
    assert "content" in captured["json"]


def test_pipeline_injects_config_for_plex_refresh(app_ctx):
    """Plex op sees base_url + token after injection, no need for manual setattr."""
    from post_processing.config_store import set_op_config
    from post_processing.ops.media_server_refresh import PlexRefreshOp
    from post_processing.pipeline import _configure_op_instance

    set_op_config(
        "plex_refresh",
        {"base_url": "http://plex:32400", "token": "tok-xyz", "section_id": "3"},
    )
    inst = PlexRefreshOp()
    _configure_op_instance(inst)
    assert inst.base_url == "http://plex:32400"
    assert inst.token == "tok-xyz"
    assert inst.section_id == "3"


def test_pipeline_wiring_does_not_leak_across_ops(app_ctx):
    """Configuring plex_refresh must not leak into emby_refresh."""
    from post_processing.config_store import set_op_config
    from post_processing.ops.media_server_refresh import EmbyRefreshOp, PlexRefreshOp
    from post_processing.pipeline import _configure_op_instance

    set_op_config("plex_refresh", {"base_url": "http://plex", "token": "t"})
    plex = PlexRefreshOp()
    emby = EmbyRefreshOp()
    _configure_op_instance(plex)
    _configure_op_instance(emby)
    assert plex.base_url == "http://plex"
    # Emby has no config in DB → defaults
    assert emby.base_url == ""
    assert emby.api_key == ""
