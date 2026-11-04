"""#234: wanted items for a language the profile no longer asks for go away."""

from db.wanted import get_wanted_items_by_path, update_wanted_status, upsert_wanted_item
from services.wanted_item_scanner import _drop_other_languages

PATH = "/media/Akiba Maid War/S01E04.mkv"


def _row(lang):
    item_id, _ = upsert_wanted_item(
        item_type="episode",
        file_path=PATH,
        title=f"Akiba Maid War — S01E04 [{lang.upper()}]",
        missing_languages=[lang],
        target_language=lang,
    )
    return item_id


def _languages():
    return sorted(r["target_language"] for r in get_wanted_items_by_path(PATH))


def test_a_waiting_item_of_a_dropped_language_is_removed(app_ctx):
    _row("de")
    _row("en")
    _drop_other_languages({PATH}, ["en"])
    assert _languages() == ["en"]


def test_an_item_with_a_result_stays(app_ctx):
    provisional = _row("de")
    update_wanted_status(provisional, "provisional")
    _drop_other_languages({PATH}, ["en"])
    assert _languages() == ["de"]


def test_no_profile_languages_removes_nothing(app_ctx):
    _row("de")
    _drop_other_languages({PATH}, [])
    assert _languages() == ["de"]


def test_language_codes_compare_case_insensitively(app_ctx):
    _row("de")
    _drop_other_languages({PATH}, ["DE"])
    assert _languages() == ["de"]
