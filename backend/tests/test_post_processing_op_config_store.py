"""Plan B6 follow-up — per-op config_store helpers."""

from __future__ import annotations


def test_get_op_config_returns_empty_dict_when_unset(app_ctx):
    from post_processing.config_store import get_op_config

    assert get_op_config("discord_notify") == {}


def test_set_op_config_roundtrip(app_ctx):
    from post_processing.config_store import get_op_config, set_op_config

    set_op_config(
        "discord_notify",
        {"webhook_url": "https://discord.com/api/webhooks/1/abc"},
    )
    assert get_op_config("discord_notify") == {
        "webhook_url": "https://discord.com/api/webhooks/1/abc"
    }


def test_set_op_config_updates_existing_row(app_ctx):
    from post_processing.config_store import get_op_config, set_op_config

    set_op_config("plex_refresh", {"base_url": "http://old:32400", "token": "t1"})
    set_op_config("plex_refresh", {"base_url": "http://new:32400", "token": "t2"})

    cfg = get_op_config("plex_refresh")
    assert cfg["base_url"] == "http://new:32400"
    assert cfg["token"] == "t2"


def test_set_op_config_partial_update_preserves_other_fields(app_ctx):
    from post_processing.config_store import get_op_config, set_op_config

    set_op_config(
        "plex_refresh",
        {"base_url": "http://plex:32400", "token": "secret", "section_id": "2"},
    )
    # Only update token
    set_op_config("plex_refresh", {"token": "new-secret"})

    cfg = get_op_config("plex_refresh")
    assert cfg["base_url"] == "http://plex:32400"
    assert cfg["token"] == "new-secret"
    assert cfg["section_id"] == "2"


def test_ops_are_isolated_from_each_other(app_ctx):
    from post_processing.config_store import get_op_config, set_op_config

    set_op_config("emby_refresh", {"base_url": "http://emby", "api_key": "e-key"})
    set_op_config("jellyfin_refresh", {"base_url": "http://jf", "api_key": "j-key"})

    emby = get_op_config("emby_refresh")
    jf = get_op_config("jellyfin_refresh")
    assert emby["api_key"] == "e-key"
    assert jf["api_key"] == "j-key"
    # Unconfigured op still empty
    assert get_op_config("plex_refresh") == {}


def test_set_op_config_coerces_non_string_values(app_ctx):
    from post_processing.config_store import get_op_config, set_op_config

    set_op_config("plex_refresh", {"section_id": 42})  # type: ignore[dict-item]
    cfg = get_op_config("plex_refresh")
    assert cfg["section_id"] == "42"
