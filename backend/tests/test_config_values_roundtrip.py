"""Stored settings keep their type through save and reload.

Audit #61 A04: lists were saved as their Python repr and reloaded as plain
strings without validation; the foreign-track cleanup then protected the
characters of "['de', 'en']" instead of the languages, and a real remux
dropped the English track.
"""

import pytest

from config_settings import UISettings
from config_values import apply_overrides, serialize_config_value, validation_errors


@pytest.mark.parametrize(
    "stored",
    ['["de", "en", "ja"]', "['de', 'en', 'ja']", "de, en, ja"],
    ids=["json", "legacy-repr", "comma"],
)
def test_a_stored_language_list_is_a_list_again(stored):
    ui = apply_overrides(UISettings(), {"cleanup_foreign_tracks_keep_languages": stored})

    assert ui.cleanup_foreign_tracks_keep_languages == ["de", "en", "ja"]


def test_a_list_is_saved_as_json():
    assert serialize_config_value(["de", "en"]) == '["de", "en"]'
    assert serialize_config_value(True) == "true"


def test_the_source_language_validator_runs_on_load():
    ui = apply_overrides(UISettings(), {"auto_translate_source_languages": '["EN", "ja"]'})

    assert isinstance(ui.auto_translate_source_languages, list)
    assert all(isinstance(code, str) for code in ui.auto_translate_source_languages)


def test_scalars_still_decode():
    ui = apply_overrides(
        UISettings(),
        {
            "upgrade_enabled": "false",
            "wanted_search_interval_hours": "6",
            "target_language": " fr ",
        },
    )

    assert ui.upgrade_enabled is False
    assert ui.wanted_search_interval_hours == 6
    assert ui.target_language == "fr"


def test_an_unreadable_value_keeps_the_default_and_the_rest_applies():
    ui = apply_overrides(
        UISettings(), {"wanted_search_interval_hours": "soon", "target_language": "fr"}
    )

    assert ui.wanted_search_interval_hours == UISettings().wanted_search_interval_hours
    assert ui.target_language == "fr"


def test_an_out_of_range_number_is_clamped_not_reset():
    ui = apply_overrides(UISettings(), {"translation_events_retention_days": "3"})

    assert ui.translation_events_retention_days == 7


def test_unknown_keys_are_ignored():
    assert apply_overrides(UISettings(), {"no_such_setting": "x"}) == UISettings()


def test_validation_reports_the_offending_key_only():
    errors = validation_errors(
        UISettings(), {"translation_quality_max_retries": "9", "target_language": "fr"}
    )

    assert list(errors) == ["translation_quality_max_retries"]
