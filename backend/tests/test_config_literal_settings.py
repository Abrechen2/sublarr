"""PUT /config rejects values outside a setting's declared choices.

``reload_settings`` overlays saved values with ``model_copy`` (no
validation), so a ``Literal[...]`` on ``UISettings`` never guarded what the
API stored. The track variant policy settings are the Literal fields today;
the check derives the allowed values from the field itself, so a future
Literal setting is covered without touching the route.
"""

import pytest


def test_every_literal_setting_is_checked():
    from routes.config.bounds import literal_choices

    assert literal_choices("cleanup_track_variant_mode") == {"all", "one_per_language"}
    assert literal_choices("cleanup_sidecar_policy") == {"keep_embedded", "drop_if_real_sidecar"}
    assert literal_choices("foreign_track_sweep_budget_s") is None


@pytest.mark.parametrize(
    "key,value",
    [
        ("cleanup_track_variant_mode", "one_track"),
        ("cleanup_track_variant_mode", ""),
        ("cleanup_track_variant_mode", 1),
        ("cleanup_sidecar_policy", "drop"),
        ("cleanup_sidecar_policy", None),
    ],
)
def test_a_value_outside_the_choices_is_rejected_and_nothing_saved(client, key, value):
    from db.config import get_config_entry

    with client.application.app_context():
        before = get_config_entry("cleanup_keep_sdh")
    response = client.put("/api/v1/config", json={"cleanup_keep_sdh": True, key: value})
    assert response.status_code == 400, response.get_json()
    assert key in response.get_json()["error"]
    with client.application.app_context():
        assert get_config_entry("cleanup_keep_sdh") == before


@pytest.mark.parametrize(
    "key,value",
    [
        ("cleanup_track_variant_mode", "one_per_language"),
        ("cleanup_track_variant_mode", "all"),
        ("cleanup_sidecar_policy", "drop_if_real_sidecar"),
    ],
)
def test_a_valid_choice_roundtrips(client, key, value):
    response = client.put("/api/v1/config", json={key: value})
    assert response.status_code == 200, response.get_json()
    assert response.get_json()["config"][key] == value


def test_an_optional_literal_setting_is_checked_too(monkeypatch):
    """``Literal[...] | None`` is a Union, not a Literal: its choices are the
    literal values plus None."""
    from typing import Literal

    from pydantic.fields import FieldInfo

    from config_settings import UISettings
    from routes.config.bounds import literal_choices, literal_keys

    monkeypatch.setitem(
        UISettings.model_fields,
        "zz_optional_mode",
        FieldInfo(annotation=Literal["a", "b"] | None, default=None),
    )
    assert literal_choices("zz_optional_mode") == {"a", "b", None}
    assert "zz_optional_mode" in literal_keys()


# --- POST /config/import (night review I2) ---------------------------------------


def test_import_skips_a_literal_value_outside_the_choices(client):
    """An import saved any writable key as a string; a bad Literal value then
    broke reload_settings for everything. It is skipped and reported."""
    from db.config import get_config_entry

    response = client.post(
        "/api/v1/config/import",
        json={
            "cleanup_track_variant_mode": "one_track",
            "cleanup_sidecar_policy": "drop_if_real_sidecar",
        },
    )
    assert response.status_code == 200, response.get_json()
    body = response.get_json()
    assert "cleanup_track_variant_mode" not in body["imported_keys"]
    assert "cleanup_sidecar_policy" in body["imported_keys"]
    skipped = {e["key"]: e["error"] for e in body["skipped_invalid"]}
    assert "cleanup_track_variant_mode" in skipped
    assert "one_per_language" in skipped["cleanup_track_variant_mode"]
    with client.application.app_context():
        assert get_config_entry("cleanup_track_variant_mode") != "one_track"
        assert get_config_entry("cleanup_sidecar_policy") == "drop_if_real_sidecar"


@pytest.mark.parametrize("value", ["5", 10**9, "abc", True])
def test_import_skips_an_out_of_range_sweep_budget(client, value):
    from db.config import get_config_entry

    response = client.post("/api/v1/config/import", json={"foreign_track_sweep_budget_s": value})
    assert response.status_code == 200, response.get_json()
    body = response.get_json()
    assert "foreign_track_sweep_budget_s" not in body["imported_keys"]
    assert [e["key"] for e in body["skipped_invalid"]] == ["foreign_track_sweep_budget_s"]
    with client.application.app_context():
        assert get_config_entry("foreign_track_sweep_budget_s") != str(value)


def test_import_saves_a_valid_sweep_budget_as_an_integer(client):
    from db.config import get_config_entry

    response = client.post("/api/v1/config/import", json={"foreign_track_sweep_budget_s": " 900 "})
    assert response.status_code == 200, response.get_json()
    assert "foreign_track_sweep_budget_s" in response.get_json()["imported_keys"]
    with client.application.app_context():
        assert get_config_entry("foreign_track_sweep_budget_s") == "900"
