"""The translation direction comes from the language profile governing the file (#254).

UI-started translations (translate, re-translate, batch, job retry) call
translate_file() without a target language. They used the global
settings.target_language, whose built-in default is 'de', so a series under a
Russian profile was validated against German and every batch was rejected.
"""

import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from translator.target_resolution import TranslationTarget, resolve_translation_target

_SETTINGS = SimpleNamespace(
    target_language="de",
    target_language_name="German",
    source_language="en",
)

_RU_PROFILE = {
    "source_language": "ja",
    "target_languages": ["ru", "uk"],
    "target_language_names": ["Russian", "Ukrainian"],
}


@pytest.fixture
def lookups():
    with (
        patch("translator.target_resolution.get_settings", return_value=_SETTINGS),
        patch("translator.target_resolution.get_wanted_items_by_path", return_value=[]) as items,
        patch("translator.target_resolution.get_profile_for_item") as profile,
    ):
        yield SimpleNamespace(items=items, profile=profile)


def test_profile_target_wins_over_global_default(lookups):
    lookups.profile.return_value = _RU_PROFILE
    target = resolve_translation_target("/media/show/e01.mkv", {"sonarr_series_id": 7})
    assert target == TranslationTarget("ru", "Russian", "ja")
    lookups.profile.assert_called_once_with({"sonarr_series_id": 7})


def test_wanted_item_of_the_file_picks_the_profile(lookups):
    item = {"id": 3, "sonarr_series_id": 7, "target_language": "uk"}
    lookups.items.return_value = [item]
    lookups.profile.return_value = _RU_PROFILE
    target = resolve_translation_target("/media/show/e01.mkv")
    lookups.profile.assert_called_once_with(item)
    # The wanted row names the language still missing for this file.
    assert target == TranslationTarget("uk", "Ukrainian", "ja")


def test_wanted_rows_follow_profile_order(lookups):
    lookups.items.return_value = [
        {"id": 4, "sonarr_series_id": 7, "target_language": "uk"},
        {"id": 3, "sonarr_series_id": 7, "target_language": "ru"},
    ]
    lookups.profile.return_value = _RU_PROFILE
    assert resolve_translation_target("/media/show/e01.mkv").code == "ru"


def test_no_context_uses_the_default_profile(lookups):
    lookups.profile.return_value = _RU_PROFILE
    assert resolve_translation_target("/media/x.mkv").code == "ru"
    lookups.profile.assert_called_once_with(None)


def test_profile_without_targets_falls_back_to_settings(lookups):
    lookups.profile.return_value = {"target_languages": []}
    assert resolve_translation_target("/media/x.mkv") == TranslationTarget("de", "German", "en")


def test_lookup_failure_falls_back_to_settings_and_logs(lookups):
    lookups.profile.side_effect = RuntimeError("db down")
    with patch("translator.target_resolution.logger") as log:
        target = resolve_translation_target("/media/x.mkv")
    assert target == TranslationTarget("de", "German", "en")
    assert "db down" in str(log.warning.call_args)


def test_unnamed_profile_target_gets_a_language_name(lookups):
    lookups.profile.return_value = {"target_languages": ["ru"], "target_language_names": []}
    assert resolve_translation_target("/media/x.mkv").name == "Russian"


class _StopError(Exception):
    pass


def test_translate_file_without_target_uses_the_profile(tmp_path):
    """translate_file() resolves the profile target when the caller passes none."""
    from translator import core

    mkv = tmp_path / "e01.mkv"
    mkv.write_bytes(b"")
    seen = {}

    def _detect(path, lang, probe):
        seen["lang"] = lang
        raise _StopError

    pkg = MagicMock()
    pkg.get_settings.return_value = SimpleNamespace(
        **vars(_SETTINGS), auto_translate_source_languages=["en"]
    )
    with (
        patch("translator.core._pkg", return_value=pkg),
        patch(
            "translator.core.resolve_translation_target",
            return_value=TranslationTarget("ru", "Russian", "ja"),
        ) as resolve,
        patch("translator.core.detect_existing_target_for_lang", side_effect=_detect),
        pytest.raises(_StopError),
    ):
        core.translate_file(str(mkv), arr_context={"sonarr_series_id": 7})
    resolve.assert_called_once_with(str(mkv), {"sonarr_series_id": 7})
    assert seen["lang"] == "ru"


def test_translate_file_explicit_target_skips_the_lookup(tmp_path):
    from translator import core

    mkv = tmp_path / "e01.mkv"
    mkv.write_bytes(b"")
    pkg = MagicMock()
    pkg.get_settings.return_value = SimpleNamespace(
        **vars(_SETTINGS), auto_translate_source_languages=["en"]
    )
    with (
        patch("translator.core._pkg", return_value=pkg),
        patch("translator.core.resolve_translation_target") as resolve,
        patch("translator.core.detect_existing_target_for_lang", side_effect=_StopError),
        pytest.raises(_StopError),
    ):
        core.translate_file(str(mkv), target_language="fr", target_language_name="French")
    resolve.assert_not_called()


def test_explicit_translate_to_in_context_wins(lookups):
    """A re-translation of one wanted row carries its language in the job context."""
    lookups.profile.return_value = _RU_PROFILE
    target = resolve_translation_target(
        "/media/x.mkv", {"sonarr_series_id": 7, "translate_to": "uk"}
    )
    assert target == TranslationTarget("uk", "Ukrainian", "ja")


def test_target_sidecar_patterns_follow_the_language():
    from translator.target_resolution import target_sidecar_patterns

    patterns = target_sidecar_patterns("ru", "srt")
    assert ".ru.srt" in patterns
    assert not any(".de." in p for p in patterns)


def test_explicit_target_without_name_is_not_named_after_the_global_one(tmp_path):
    """target_language='ru' without a name used to report itself as 'German'."""
    from translator import core

    mkv = tmp_path / "e01.mkv"
    mkv.write_bytes(b"")
    pkg = MagicMock()
    pkg.get_settings.return_value = SimpleNamespace(
        **vars(_SETTINGS), auto_translate_source_languages=["en"]
    )
    with (
        patch("translator.core._pkg", return_value=pkg),
        patch("translator.core.detect_existing_target_for_lang", return_value="ass"),
        patch(
            "services.suspect_sidecars.existing_ignoring_suspects", side_effect=lambda p, l, s: s
        ),
    ):
        result = core.translate_file(str(mkv), target_language="ru")
    assert "Russian" in str(result)
    assert "German" not in str(result)


def test_scan_directory_checks_each_files_profile_language(tmp_path):
    from translator import jobs

    ass = "[Script Info]\n\n[Events]\nFormat: Layer, Start, End, Style, Text\n"
    ass += "Dialogue: 0,0:00:01.00,0:00:02.00,Default,Privet\n"
    for name in ("done.mkv", "todo.mkv"):
        (tmp_path / name).write_bytes(b"")
    for name in ("done.ru.ass", "todo.de.ass"):
        (tmp_path / name).write_text(ass)
    with patch(
        "translator.target_resolution.resolve_translation_target",
        return_value=TranslationTarget("ru", "Russian", "ja"),
    ):
        found = [os.path.basename(f["path"]) for f in jobs.scan_directory(str(tmp_path))]
    assert found == ["todo.mkv"]
