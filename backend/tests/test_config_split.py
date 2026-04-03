"""Smoke tests: verify config public API survives the split."""


def test_get_settings_importable_from_config():
    from config import get_settings

    s = get_settings()
    assert s is not None


def test_supported_languages_importable_from_config():
    from config import SUPPORTED_LANGUAGES

    assert isinstance(SUPPORTED_LANGUAGES, list)
    assert len(SUPPORTED_LANGUAGES) > 0


def test_get_language_tags_importable_from_config():
    from config import _get_language_tags

    tags = _get_language_tags("de")
    assert "de" in tags
    assert "deu" in tags


def test_instance_helpers_importable_from_config():
    from config import (
        get_media_server_instances,
        get_radarr_instances,
        get_sonarr_instances,
        is_standalone_mode,
    )

    # Just confirm they are callable
    assert callable(get_sonarr_instances)
    assert callable(get_radarr_instances)
    assert callable(is_standalone_mode)
    assert callable(get_media_server_instances)


def test_language_data_importable_directly():
    from config_language_data import _LANGUAGE_TAGS, SUPPORTED_LANGUAGES, _get_language_tags

    assert "de" in _LANGUAGE_TAGS
    assert isinstance(SUPPORTED_LANGUAGES, list)


def test_instances_importable_directly():
    from config_instances import (
        get_media_server_instances,
        get_radarr_instances,
        get_sonarr_instances,
        is_standalone_mode,
    )

    assert callable(get_sonarr_instances)


def test_map_path_importable_from_config():
    from config import map_path

    assert callable(map_path)


def test_map_path_importable_directly():
    from config_utils import map_path

    assert callable(map_path)
