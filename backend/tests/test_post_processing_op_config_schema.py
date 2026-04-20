"""Plan B6 follow-up — each curated op declares a well-formed config_schema."""

from __future__ import annotations

import pytest


def _all_ops():
    """Return all registered curated op classes."""
    import post_processing.ops  # noqa: F401 — triggers @register_op for every op
    from post_processing.base_op import _OP_REGISTRY

    return list(_OP_REGISTRY)


def test_every_op_declares_config_schema_list():
    for cls in _all_ops():
        assert hasattr(cls, "config_schema"), f"{cls.op_id} missing config_schema"
        assert isinstance(cls.config_schema, list), (
            f"{cls.op_id}.config_schema must be a list"
        )


VALID_TYPES = {"text", "password", "number"}


@pytest.mark.parametrize(
    "op_id,expected_keys",
    [
        ("strip_html", set()),
        ("remove_bom", set()),
        ("convert_encoding", set()),
        ("webhook", {"url", "method", "template"}),
        ("discord_notify", {"webhook_url"}),
        ("plex_refresh", {"base_url", "token", "section_id"}),
        ("emby_refresh", {"base_url", "api_key"}),
        ("jellyfin_refresh", {"base_url", "api_key"}),
    ],
)
def test_op_has_expected_schema_keys(op_id: str, expected_keys: set[str]):
    from post_processing.base_op import _OP_REGISTRY

    cls = next((c for c in _OP_REGISTRY if c.op_id == op_id), None)
    assert cls is not None, f"op {op_id} not registered"

    actual_keys = {entry["key"] for entry in cls.config_schema}
    assert actual_keys == expected_keys, (
        f"{op_id}: expected {expected_keys}, got {actual_keys}"
    )


def test_every_schema_entry_is_well_formed():
    for cls in _all_ops():
        for entry in cls.config_schema:
            assert isinstance(entry, dict), f"{cls.op_id}: entry must be dict"
            for field in ("key", "label", "type", "required", "default"):
                assert field in entry, f"{cls.op_id}: entry missing {field}"
            assert isinstance(entry["key"], str) and entry["key"]
            assert isinstance(entry["label"], str) and entry["label"]
            assert entry["type"] in VALID_TYPES, (
                f"{cls.op_id}: type {entry['type']} not in {VALID_TYPES}"
            )
            assert isinstance(entry["required"], bool)
            assert isinstance(entry["default"], str)


def test_password_fields_marked_correctly():
    """Every secret field (token / api_key / webhook_url) is type=password."""
    from post_processing.base_op import _OP_REGISTRY

    expected = {
        ("discord_notify", "webhook_url"),
        ("plex_refresh", "token"),
        ("emby_refresh", "api_key"),
        ("jellyfin_refresh", "api_key"),
    }
    for op_id, key in expected:
        cls = next((c for c in _OP_REGISTRY if c.op_id == op_id), None)
        assert cls is not None
        entry = next(e for e in cls.config_schema if e["key"] == key)
        assert entry["type"] == "password", (
            f"{op_id}.{key}: secret must be type=password"
        )
