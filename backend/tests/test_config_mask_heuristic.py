"""The masking heuristic must not read a secret into an ordinary field name.

Found while putting the documented path-mapping editor on the Connections
page: the editor showed "***configured***" instead of the mapping, and saving
it would have written that literal string over the user's real paths.

Cause: the rule tested its sensitive words as substrings, and "map**pin**g"
contains "pin". Two settings were caught by it — path_mapping and the boolean
anidb_fallback_to_mapping, which GET /config therefore answered with a string
where the UI expected true or false.
"""

import pytest

from config_settings import is_sensitive_config_key


@pytest.mark.parametrize(
    "key",
    [
        "api_key",
        "opensubtitles_api_key",
        "customapi_api_key_header",
        "addic7ed_password",
        "opensubtitles_password",
        "github_token",
        "tvdb_pin",  # the segment really is "pin" here
        "database_url",  # no telltale word; masked by name
        "redis_url",
    ],
)
def test_credentials_stay_masked(key):
    assert is_sensitive_config_key(key) is True


@pytest.mark.parametrize(
    "key",
    [
        "path_mapping",  # "mapping" contains "pin"
        "anidb_fallback_to_mapping",  # a bool, and it contains "pin" too
        "log_level",
        "media_path",
        "target_language",
    ],
)
def test_ordinary_settings_are_not_masked(key):
    assert is_sensitive_config_key(key) is False


def test_the_two_rules_differ_only_on_the_mapping_false_positives():
    """Guard the change itself: nothing else may have been opened up.

    The old rule was a substring test. Enumerating every declared settings
    field, exactly two answers change — and both are the "map-pin-g" false
    positive. If this list ever grows, the narrowing let something real out.
    """
    import re
    from pathlib import Path

    source = Path(__file__).resolve().parents[1] / "config_settings.py"
    fields = re.findall(r"^\s{4}([a-z][a-z0-9_]*)\s*:\s*[A-Za-z]", source.read_text("utf-8"), re.M)
    old_parts = {"password", "pin", "secret", "token", "api_key"}

    def old_rule(key):
        return (
            key in {"database_url", "redis_url"}
            or "api_key" in key
            or "key" in key.split("_")
            or any(part in key for part in old_parts)
        )

    changed = sorted({f for f in fields if old_rule(f) != is_sensitive_config_key(f)})
    assert changed == ["anidb_fallback_to_mapping", "path_mapping"], changed


def test_masked_config_keeps_the_path_mapping_readable(app_ctx):
    """End to end: the value reaches the editor instead of a mask."""
    from config import get_settings

    with app_ctx.app_context():
        safe = get_settings().get_safe_config()

    assert safe["path_mapping"] != "***configured***"
    assert isinstance(safe["anidb_fallback_to_mapping"], bool)
    assert safe["api_key"] in ("", "***configured***")
