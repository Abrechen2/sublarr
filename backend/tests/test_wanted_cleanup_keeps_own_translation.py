"""The cleanup must not remove a row that our own translation serves while
its profile keeps seeking the original.

The scanner files such a row as ``provisional`` for mt_reseek, but the cleanup
right after it saw the .ass and removed it: prod 2026-11-05 held 1,791
machine-translated .ass files and 1,584 of them had no wanted row, and every
full scan added and removed ~1,600 rows. The original was never sought.
"""

from unittest.mock import MagicMock, patch

import pytest


def _cleanup(existing, *, machine_translated, keep_seeking, upgrade_enabled=True):
    from services.wanted_scanner_core import WantedScanner

    scanner = WantedScanner()
    item = {
        "id": 7,
        "file_path": "/media/show/ep.mkv",
        "target_language": "de",
        "instance_name": "Sonarr",
        "sonarr_series_id": 3,
        "subtitle_type": "full",
    }
    with (
        patch("db.wanted.get_wanted_items_for_cleanup", return_value=[item]),
        patch("db.wanted.delete_wanted_items_by_ids") as delete,
        patch("services.standalone_library.wanted_item_path_refusal", return_value=None),
        patch("services.wanted_scanner_core.PathPresence.state", return_value="present"),
        patch(
            "services.wanted_scanner_core.detect_existing_target_for_lang", return_value=existing
        ),
        patch(
            "services.wanted_scanner_core.existing_ignoring_suspects",
            side_effect=lambda p, lang, e: e,
        ),
        patch("db.providers.is_machine_translated", return_value=machine_translated),
        patch("services.mt_provisional._keep_seeking_or_none", return_value=keep_seeking),
        patch(
            "services.wanted_scanner_core.get_settings",
            return_value=MagicMock(upgrade_enabled=upgrade_enabled),
        ),
    ):
        scanner._cleanup({item["file_path"]})
    return delete


@pytest.mark.parametrize(("existing", "upgrade_enabled"), [("ass", True), ("srt", False)])
def test_our_translation_with_keep_seeking_keeps_the_row(existing, upgrade_enabled):
    delete = _cleanup(
        existing, machine_translated=True, keep_seeking=True, upgrade_enabled=upgrade_enabled
    )
    delete.assert_not_called()


def test_an_unreadable_profile_keeps_the_row():
    delete = _cleanup("ass", machine_translated=True, keep_seeking=None)
    delete.assert_not_called()


@pytest.mark.parametrize(("machine_translated", "keep_seeking"), [(False, True), (True, False)])
def test_a_finished_subtitle_still_removes_the_row(machine_translated, keep_seeking):
    delete = _cleanup("ass", machine_translated=machine_translated, keep_seeking=keep_seeking)
    delete.assert_called_once_with([7])
