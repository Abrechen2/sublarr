"""Characterization tests for backend/config.py refactor (B1).

These tests pin behaviour of the parts of config.py NOT yet covered by
test_config.py / test_config_split.py / test_settings_views.py.

After every extraction step in plan 2026-04-18-b1-config-py-split.md
this file MUST keep passing without modification.
"""

import pytest


def test_settings_class_importable_from_config():
    """Settings (the composite class) must be importable from `config`."""
    from config import BootSettings, Settings, UISettings

    assert Settings is not None
    # Composite — model_dump is implemented (forwards to boot+ui).
    assert hasattr(Settings, "model_dump")
    # Boot/UI sub-classes also re-exported for direct construction.
    assert BootSettings is not None
    assert UISettings is not None


def test_settings_instantiable_without_env():
    """Default-constructed Settings produces sensible values."""
    from config import Settings

    s = Settings()
    assert s.port == 5765
    assert s.target_language == "de"
    assert s.source_language == "en"


def test_get_database_url_sqlite_default():
    from config import Settings

    s = Settings(database_url="", db_path="/tmp/x.db")
    assert s.get_database_url() == "sqlite:////tmp/x.db"


def test_get_database_url_explicit_takes_precedence():
    from config import Settings

    s = Settings(database_url="postgresql://u:p@h/db", db_path="/tmp/x.db")
    assert s.get_database_url() == "postgresql://u:p@h/db"


def test_get_target_patterns_returns_dotted_extensions():
    from config import Settings

    s = Settings(target_language="de")
    patterns = s.get_target_patterns(fmt="ass")
    # Must include at least the iso 639-1 form
    assert ".de.ass" in patterns
    # And start with a dot
    assert all(p.startswith(".") for p in patterns)


def test_get_source_patterns_uses_source_language():
    from config import Settings

    s = Settings(source_language="en")
    patterns = s.get_source_patterns(fmt="srt")
    assert ".en.srt" in patterns


def test_get_target_lang_tags_returns_set_of_strings():
    from config import Settings

    s = Settings(target_language="de")
    tags = s.get_target_lang_tags()
    assert isinstance(tags, set)
    assert "de" in tags


def test_get_source_lang_tags_returns_set_of_strings():
    from config import Settings

    s = Settings(source_language="en")
    tags = s.get_source_lang_tags()
    assert isinstance(tags, set)
    assert "en" in tags


def test_get_translation_config_hash_is_12_chars_hex():
    from config import Settings

    s = Settings()
    h = s.get_translation_config_hash()
    assert isinstance(h, str)
    assert len(h) == 12
    int(h, 16)  # raises if not hex


def test_get_translation_config_hash_changes_with_model():
    from config import Settings

    s1 = Settings(ollama_model="qwen2.5:14b-instruct")
    s2 = Settings(ollama_model="llama3:8b")
    assert s1.get_translation_config_hash() != s2.get_translation_config_hash()


def test_get_translation_config_hash_non_ollama_ignores_model():
    from config import Settings

    s1 = Settings(ollama_model="model-a")
    s2 = Settings(ollama_model="model-b")
    # For non-ollama backend the model field is irrelevant.
    assert s1.get_translation_config_hash("deepl") == s2.get_translation_config_hash("deepl")


def test_get_safe_config_masks_api_keys():
    from config import Settings

    s = Settings(opensubtitles_api_key="SECRET123", subdl_api_key="OTHER456")
    safe = s.get_safe_config()
    assert safe["opensubtitles_api_key"] == "***configured***"
    assert safe["subdl_api_key"] == "***configured***"


def test_get_safe_config_passes_through_non_sensitive():
    from config import Settings

    s = Settings(port=5765, target_language="de")
    safe = s.get_safe_config()
    assert safe["port"] == 5765
    assert safe["target_language"] == "de"


def test_get_safe_config_masks_passwords():
    from config import Settings

    s = Settings(addic7ed_password="hunter2")
    safe = s.get_safe_config()
    assert safe["addic7ed_password"] == "***configured***"


def test_get_safe_config_masks_database_url_when_set():
    from config import Settings

    s = Settings(database_url="postgresql://user:pw@host/db")
    safe = s.get_safe_config()
    assert safe["database_url"] == "***configured***"


def test_get_safe_config_empty_credentials_stay_empty_string():
    from config import Settings

    s = Settings(opensubtitles_api_key="")
    safe = s.get_safe_config()
    assert safe["opensubtitles_api_key"] == ""


def test_get_safe_config_masks_all_credential_subkeys_in_arr_instances_json():
    import json as _json

    from config import Settings

    payload = _json.dumps(
        [
            {
                "name": "Main",
                "url": "http://s/",
                "api_key": "A",
                "apiKey": "B",
                "password": "C",
                "token": "D",
                "secret": "E",
                "pin": "F",
            }
        ]
    )
    s = Settings(sonarr_instances_json=payload)
    safe = s.get_safe_config()
    parsed = _json.loads(safe["sonarr_instances_json"])
    for subkey in ("api_key", "apiKey", "password", "token", "secret", "pin"):
        assert parsed[0][subkey] == "***configured***", f"subkey {subkey!r} not masked"
    assert parsed[0]["name"] == "Main"
    assert parsed[0]["url"] == "http://s/"


def test_get_settings_returns_singleton():
    from config import get_settings

    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2


def test_reload_settings_replaces_singleton():
    from config import get_settings, reload_settings

    s1 = get_settings()
    s2 = reload_settings()
    # The singleton now points at the reloaded instance.
    assert get_settings() is s2
    # reload_settings() always constructs a fresh Settings(); not the prior cache.
    assert s2 is not s1


def test_reload_settings_applies_overrides_with_type_coercion():
    """DB overrides apply to UI fields with type coercion.

    Boot fields (port, log_level, paths, …) are ENV-only since
    v0.88.0-beta; reload_settings drops boot keys silently. Use UI fields
    here to exercise the type-coercion path.
    """
    from config import reload_settings

    s = reload_settings(overrides={"items_per_page": "75", "wanted_anime_only": "false"})
    assert s.items_per_page == 75  # str → int
    assert s.wanted_anime_only is False  # str → bool


def test_reload_settings_ignores_unknown_keys():
    from config import reload_settings

    s = reload_settings(overrides={"there_is_no_such_field_xyz": "1"})
    assert not hasattr(s, "there_is_no_such_field_xyz")


def test_reload_settings_skips_invalid_values():
    from config import reload_settings

    # "abc" cannot be parsed into the int field `items_per_page` — must be
    # silently skipped so the rest of the settings still load.
    s = reload_settings(overrides={"items_per_page": "abc"})
    assert s.items_per_page == 25  # default preserved


def test_grouped_view_classes_importable_from_config():
    """Already covered by test_settings_views.py but pinned here too for safety."""
    from config import (
        GeneralSettings,
        MediaServerSettings,
        ProviderSettings,
        ScanningSettings,
        TranslationSettings,
    )

    for cls in (
        GeneralSettings,
        TranslationSettings,
        ProviderSettings,
        MediaServerSettings,
        ScanningSettings,
    ):
        assert cls is not None
        assert hasattr(cls, "_fields")
        assert isinstance(cls._fields, frozenset)
        assert len(cls._fields) > 0


def test_config_py_under_600_loc():
    """Pin B1 achievement: config.py must stay below 600 LOC.

    If you are adding settings, put new fields in config_settings.py.
    If you are adding view classes, put them in config_views.py.
    config.py is intentionally a thin re-export façade.
    """
    from pathlib import Path

    config_path = Path(__file__).parent.parent / "config.py"
    assert config_path.exists(), f"config.py not found at {config_path}"
    line_count = sum(1 for _ in config_path.open(encoding="utf-8"))
    assert line_count < 600, (
        f"backend/config.py is {line_count} LOC, must stay below 600. "
        "Move declarations into config_settings.py or config_views.py."
    )


@pytest.fixture(autouse=True)
def _reset_singleton_after_test():
    """Make sure singleton state from this file does not leak into other tests."""
    yield
    # Force a clean reload so subsequent test files see a fresh Settings()
    from config import reload_settings

    reload_settings()
