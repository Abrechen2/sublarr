import pytest


def test_default_is_off():
    from config_settings import Settings

    s = Settings()
    assert s.cleanup_signs_removal_level == "off"


def test_accepts_valid_levels():
    from config_settings import Settings

    for v in ("off", "signs", "signs_forced", "signs_forced_songs"):
        assert Settings(cleanup_signs_removal_level=v).cleanup_signs_removal_level == v


def test_rejects_invalid_level():
    from config_settings import Settings

    with pytest.raises(ValueError):
        Settings(cleanup_signs_removal_level="nuke_everything")
