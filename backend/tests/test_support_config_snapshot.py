"""The support bundle's config snapshot is an allow-list, not a deny-list.

`get_safe_config()` masks names containing password/pin/secret/token/key and
ships everything else in clear: usernames, internal URLs with their hosts,
trusted proxy IPs, path mappings, the media path. The test below walks EVERY
settings field, fills each string field with a unique sentinel, and asserts
that only allow-listed fields let their sentinel through — so a future
``discord_webhook_url`` is masked by default instead of by someone remembering.
"""

from __future__ import annotations

import json
import types
import typing

import pytest

from config_settings import BootSettings, Settings, UISettings


def _is_stringish(ann) -> bool:
    """str, list[...], or an Optional/Union containing one of them."""
    if ann is str or typing.get_origin(ann) is list:
        return True
    if typing.get_origin(ann) in (typing.Union, types.UnionType):
        return any(_is_stringish(a) for a in typing.get_args(ann))
    return False


def _string_fields():
    for model in (BootSettings, UISettings):
        for name, field in model.model_fields.items():
            ann = field.annotation
            if _is_stringish(ann):
                yield name, ann


def _sentinel_settings():
    values = {}
    sentinels = {}
    for name, ann in _string_fields():
        if name == "cleanup_signs_removal_level":  # validated enum-like string
            continue
        token = f"SNT{abs(hash(name)) % 10**8:08d}{name.replace('_', '')[:12]}"
        sentinels[name] = token
        if typing.get_origin(ann) is list:
            values[name] = [token]
        elif name.endswith(("_url", "_endpoint")):
            values[name] = f"http://usr{token}:pw{token}@host{token}.lan:8080/p{token}"
        else:
            values[name] = token
    return Settings(**values), sentinels


class TestAllowListSnapshot:
    def test_no_non_allow_listed_string_value_leaks(self):
        from routes.system.support_config import SAFE_STRING_FIELDS, build_config_snapshot

        settings, sentinels = _sentinel_settings()
        dumped = json.dumps(build_config_snapshot(settings))

        leaked = [
            name
            for name, token in sentinels.items()
            if name not in SAFE_STRING_FIELDS and token in dumped
        ]
        assert leaked == []

    def test_allow_listed_fields_ship_in_clear(self):
        from routes.system.support_config import build_config_snapshot

        snap = build_config_snapshot(
            Settings(log_level="DEBUG", target_language="de", provider_priorities="jimaku")
        )
        assert snap["log_level"] == "DEBUG"
        assert snap["target_language"] == "de"
        assert snap["provider_priorities"] == "jimaku"

    def test_scalars_and_literals_ship_in_clear(self):
        from routes.system.support_config import build_config_snapshot

        snap = build_config_snapshot(
            Settings(
                port=1234,
                foreign_track_sweep_enabled=True,
                cleanup_sidecar_policy="drop_if_real_sidecar",
            )
        )
        assert snap["port"] == 1234
        assert snap["foreign_track_sweep_enabled"] is True
        assert snap["cleanup_sidecar_policy"] == "drop_if_real_sidecar"

    def test_presence_stays_visible(self):
        from routes.system.support_config import MASK_SET, build_config_snapshot

        snap = build_config_snapshot(Settings(addic7ed_username="bob", path_mapping=""))
        assert snap["addic7ed_username"] == MASK_SET
        assert snap["path_mapping"] == ""

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("http://user:pw@192.168.178.20:8989/sonarr", "http://<private-ip>:8989"),
            ("https://sonarr.example.com", "https://<host>"),
            ("http://localhost:11434", "http://<loopback>:11434"),
            ("http://127.0.0.1:11434", "http://<loopback>:11434"),
            ("http://85.214.132.17", "http://<public-ip>"),
            ("not a url", "***configured***"),
        ],
    )
    def test_urls_are_reduced_to_scheme_and_host_class(self, value, expected):
        from routes.system.support_config import build_config_snapshot

        snap = build_config_snapshot(Settings(sonarr_url=value))
        assert snap["sonarr_url"] == expected

    def test_credentials_keep_the_configured_marker(self):
        from routes.system.support_config import build_config_snapshot

        snap = build_config_snapshot(
            Settings(database_url="postgresql://u:p@db/x", api_key="abcdefgh")
        )
        assert snap["database_url"] == "***configured***"
        assert snap["api_key"] == "***configured***"

    def test_a_secret_inside_an_allow_listed_field_is_still_redacted(self):
        # Defence in depth: the whole snapshot runs through redact().
        from routes.system.support_config import build_config_snapshot

        snap = build_config_snapshot(
            Settings(jimaku_api_key="LeakyKey123", ollama_model="model-LeakyKey123")
        )
        assert "LeakyKey123" not in json.dumps(snap)


def test_non_ascii_secret_in_an_allow_listed_field_is_redacted():
    """I-3: redacting the JSON text missed a secret that JSON had escaped."""
    from routes.system.support_config import build_config_snapshot

    snap = build_config_snapshot(
        Settings(jimaku_api_key="Schlüssel123", ollama_model="m-Schlüssel123")
    )
    assert "Schlüssel123" not in json.dumps(snap, ensure_ascii=False)


def test_a_quote_in_an_allow_listed_value_does_not_break_the_snapshot():
    from routes.system.support_config import build_config_snapshot

    snap = build_config_snapshot(Settings(ollama_model='weird "token: x" model'))
    assert isinstance(snap, dict)
    assert snap["log_level"]


@pytest.mark.parametrize(
    "annotation",
    [str | None, typing.Union[str, None], list[str] | None],  # noqa: UP007 — both spellings
)
def test_an_optional_string_field_is_masked_by_default(annotation):
    """Review gap: the every-field walk skipped `str | None` fields (none exist
    today). A future one must still be masked, not shipped in clear."""
    from routes.system.support_config import MASK_SET, _snapshot_value

    assert _is_stringish(annotation)
    value = ["x"] if typing.get_origin(annotation) is list else "SecretishValue"
    assert _snapshot_value("some_future_field", value, annotation) == MASK_SET
