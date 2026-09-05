"""A source that answers with an EMPTY list must not get its queue pruned.

Prod 2026-09-04 19:48 CEST: Cardinal came back from a NUT shutdown, Sonarr
and Sublarr started within the same second, and the boot-time full scan
asked Sonarr for its series while Sonarr was still initialising. Sonarr
answered 200 with an empty list — no exception, so the 2026-08-30 guard
(``test_wanted_scan_error_no_prune``) never fired — and the cleanup that
followed removed every Sonarr wanted item whose path the scan "had not
seen": 11 862 rows, re-created minutes later as fresh rows. 619 queued
translations were dropped as orphans, the search history of the whole
Sonarr queue was lost, and it had already happened once on 2026-09-01.

Reproduced on RC with a fake Sonarr serving ``[]``: 5 of 5 Sonarr rows gone
in 2.2 s, the Radarr row untouched.

Two independent guards, so neither has to be perfect:

1. A source that returns nothing while the database still holds rows for
   it is treated exactly like a source that raised — flagged, nothing
   pruned, watermark frozen.
2. The cleanup itself refuses to remove more than half of the table in one
   pass. A library does not lose half its files between two scans; a scan
   that saw too little does.
"""

from unittest.mock import MagicMock, patch


def _scanner():
    from services.wanted_scanner_core import WantedScanner

    s = WantedScanner.__new__(WantedScanner)
    s.__init__()
    return s


class TestEmptySourceIsUnavailable:
    def test_sonarr_empty_list_with_known_rows_flags_error(self):
        scanner = _scanner()
        sonarr = MagicMock()
        sonarr.get_anime_series.return_value = []
        settings = MagicMock(wanted_anime_only=True, scan_yield_ms=0)
        with patch("db.wanted.get_wanted_count_for_instance", return_value=11862) as count:
            result = scanner._scan_sonarr_instance(sonarr, settings, "Sonarr 1")
        assert result == (0, 0, set())
        assert scanner._scan_had_errors is True
        count.assert_called_once_with("Sonarr 1")

    def test_sonarr_empty_list_on_a_fresh_install_is_not_an_error(self):
        scanner = _scanner()
        sonarr = MagicMock()
        sonarr.get_series.return_value = []
        settings = MagicMock(wanted_anime_only=False, scan_yield_ms=0)
        with patch("db.wanted.get_wanted_count_for_instance", return_value=0):
            result = scanner._scan_sonarr_instance(sonarr, settings, "Sonarr 1")
        assert result == (0, 0, set())
        assert scanner._scan_had_errors is False

    def test_radarr_empty_list_with_known_rows_flags_error(self):
        scanner = _scanner()
        radarr = MagicMock()
        radarr.get_movies.return_value = []
        settings = MagicMock(wanted_anime_movies_only=False, scan_yield_ms=0)
        with patch("db.wanted.get_wanted_count_for_instance", return_value=122):
            result = scanner._scan_radarr_instance(radarr, settings, "Radarr 1")
        assert result == (0, 0, set())
        assert scanner._scan_had_errors is True

    def test_incremental_filter_emptying_the_list_does_not_trip_the_guard(self):
        """The guard looks at what the source RETURNED, not at what survives
        the since-filter — an incremental pass with no changes is normal."""
        from datetime import UTC, datetime

        scanner = _scanner()
        sonarr = MagicMock()
        sonarr.get_series.return_value = [{"id": 1, "added": "2020-01-01T00:00:00Z"}]
        settings = MagicMock(wanted_anime_only=False, scan_yield_ms=0)
        with patch("db.wanted.get_wanted_count_for_instance", return_value=500) as count:
            result = scanner._scan_sonarr_instance(
                sonarr, settings, "Sonarr 1", since=datetime(2026, 1, 1, tzinfo=UTC)
            )
        assert result == (0, 0, set())
        assert scanner._scan_had_errors is False
        count.assert_not_called()


def _items(n: int) -> list[dict]:
    return [
        {
            "id": i,
            "file_path": f"/media/show/ep{i:03d}.mkv",
            "target_language": "de",
            "instance_name": "Sonarr 1",
        }
        for i in range(1, n + 1)
    ]


def _run_cleanup(scanner, items, scanned_paths):
    with (
        patch("db.wanted.get_wanted_items_for_cleanup", return_value=items),
        patch("db.wanted.delete_wanted_items_by_ids") as delete,
        patch("services.wanted_scanner_core.os.path.exists", return_value=True),
        patch("services.wanted_scanner_core.detect_existing_target_for_lang", return_value=""),
        patch(
            "services.wanted_scanner_core.get_settings",
            return_value=MagicMock(upgrade_enabled=True),
        ),
    ):
        removed = scanner._cleanup(scanned_paths)
    return removed, delete


class TestCleanupFuse:
    def test_fuse_refuses_to_remove_most_of_the_table(self):
        scanner = _scanner()
        items = _items(100)
        seen = {i["file_path"] for i in items[:10]}
        removed, delete = _run_cleanup(scanner, items, seen)
        assert removed == 0
        delete.assert_not_called()

    def test_a_normal_prune_still_removes_the_stragglers(self):
        scanner = _scanner()
        items = _items(100)
        seen = {i["file_path"] for i in items[:95]}
        removed, delete = _run_cleanup(scanner, items, seen)
        assert removed == 5
        delete.assert_called_once_with([96, 97, 98, 99, 100])

    def test_fuse_leaves_tiny_tables_alone(self):
        """Below the minimum the ratio is meaningless — four of five rows
        vanishing on a five-row test library is not a wipe."""
        scanner = _scanner()
        items = _items(5)
        seen = {items[0]["file_path"]}
        removed, delete = _run_cleanup(scanner, items, seen)
        assert removed == 4
        delete.assert_called_once()

    def test_fuse_threshold_is_half(self):
        from services import wanted_scanner_core as core

        assert core.CLEANUP_FUSE_MAX_FRACTION == 0.5
        assert core.CLEANUP_FUSE_MIN_ITEMS == 20


def test_repository_counts_rows_per_instance(app_ctx):
    from db.wanted import get_wanted_count_for_instance, upsert_wanted_item

    upsert_wanted_item(
        item_type="episode",
        file_path="/media/a/one.mkv",
        title="one",
        season_episode="S01E01",
        target_language="de",
        instance_name="Sonarr 1",
    )
    upsert_wanted_item(
        item_type="episode",
        file_path="/media/a/two.mkv",
        title="two",
        season_episode="S01E02",
        target_language="de",
        instance_name="Sonarr 2",
    )
    assert get_wanted_count_for_instance("Sonarr 1") == 1
    assert get_wanted_count_for_instance("Sonarr 2") == 1
    assert get_wanted_count_for_instance("Radarr 1") == 0
