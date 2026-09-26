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
