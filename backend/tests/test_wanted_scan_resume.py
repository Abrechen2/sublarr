"""A full wanted scan that runs out of time must still get somewhere (#248).

A library whose full scan needs longer than the job's ceiling was stuck: the
scheduler asked the scan to stop, the scan pruned nothing and kept its
watermark, and since the watermark only moves on a completed scan, every
following scan was full again and stopped again. Rows for moved files were
never pruned (855 of 4 018 on the reporter's install). After the stop the
scan also kept walking — fetching and probing every remaining series only
to discard it — for two more hours.
"""

from contextlib import ExitStack, nullcontext
from unittest.mock import MagicMock, patch

from services.wanted_scanner_core import WantedScanner


def _scanner():
    s = WantedScanner.__new__(WantedScanner)
    s.__init__()
    return s


SERIES = [{"id": i, "title": f"S{i}"} for i in (1, 2, 3, 4)]


def _settings():
    s = MagicMock()
    s.wanted_anime_only = False
    s.scan_yield_ms = 0
    return s


def _run(scanner, *, stop_after=None, cleanup=None, wanted_count=None):
    """One full scan over SERIES; asked to stop once ``stop_after`` series ran."""
    scanned = []

    def scan_series(sonarr, series_id, *a, **kw):
        scanned.append(series_id)
        return 0, 1, {f"/media/{series_id}.mkv"}

    def stop():
        return stop_after is not None and len(scanned) >= stop_after

    sonarr = MagicMock()
    sonarr.get_series.return_value = list(SERIES)
    cleanup = cleanup or MagicMock(return_value=0)
    with ExitStack() as stack:
        for target, kw in (
            ("config.get_sonarr_instances", {"return_value": [{"name": "Main"}]}),
            ("sonarr_client.get_sonarr_client", {"return_value": sonarr}),
            ("services.wanted_scanner_sources.scan_sonarr_series", {"side_effect": scan_series}),
            ("services.wanted_scanner_sources.batch_upsert_context", {"side_effect": nullcontext}),
            ("services.wanted_scanner_sources.abort_requested", {"side_effect": stop}),
            ("services.wanted_scanner_core.abort_requested", {"side_effect": stop}),
            ("services.wanted_scanner_core.get_settings", {"return_value": _settings()}),
            ("services.wanted_scanner_core.log_activity", {}),
            ("services.suspect_sidecars.trash_quarantined_on_disk", {}),
            ("db.wanted.get_wanted_count", wanted_count or {"return_value": 4}),
        ):
            stack.enter_context(patch(target, **kw))
        stack.enter_context(patch.object(scanner, "_scan_all_radarr", return_value=(0, 0, set())))
        stack.enter_context(
            patch.object(scanner, "_scan_all_standalone", return_value=(0, 0, set()))
        )
        stack.enter_context(patch.object(scanner, "_cleanup", cleanup))
        scanner.scan_all(incremental=False)
    return scanned, cleanup


class TestStopMeansStop:
    def test_no_series_is_fetched_after_the_stop(self):
        scanner = _scanner()
        scanned, _ = _run(scanner, stop_after=2)

        assert scanned == [1, 2]


class TestAbortedScansAddUp:
    def test_the_next_full_scan_resumes_where_the_last_one_stopped(self):
        scanner = _scanner()
        _run(scanner, stop_after=2)
        scanned, _ = _run(scanner)

        assert scanned == [2, 3, 4]

    def test_the_finished_pass_prunes_against_every_series_it_covered(self):
        scanner = _scanner()
        _run(scanner, stop_after=2)
        _, cleanup = _run(scanner)

        assert cleanup.call_args.args[0] == {f"/media/{i}.mkv" for i in (1, 2, 3, 4)}

    def test_the_watermark_is_the_start_of_the_first_part(self):
        """Changes made while the first part ran must not fall behind it."""
        scanner = _scanner()
        _run(scanner, stop_after=2)
        first_start = scanner._resume["started_at"]
        _run(scanner)

        assert scanner._last_scan_timestamp == first_start
        assert scanner._resume is None

    def test_a_series_cut_off_by_the_stop_is_scanned_again(self):
        """Stopped mid-series: its rows may be half written, so it is not done."""
        scanner = _scanner()
        _run(scanner, stop_after=2)

        assert set(scanner._resume["done"]) == {("sonarr", "Main", 1)}

    def test_a_stale_resume_point_is_dropped(self):
        scanner = _scanner()
        _run(scanner, stop_after=2)
        scanner._resume["started_at"] -= WantedScanner.RESUME_MAX_AGE * 2
        scanned, _ = _run(scanner)

        assert scanned == [1, 2, 3, 4]


class TestAbortedScanPrunesWhatItCan:
    def test_rows_are_checked_one_by_one_without_the_path_set(self):
        """The per-row checks (file gone, subtitle present) hold on a partial pass."""
        scanner = _scanner()
        _, cleanup = _run(scanner, stop_after=2)

        cleanup.assert_called_once_with(set())


class TestLockIsReleasedBeforeBookkeeping:
    def test_a_stalled_count_does_not_hold_the_scan_lock(self):
        """#248 bug 2: the lock stayed held for hours after the stop line."""
        scanner = _scanner()
        seen = {}

        def count():
            seen["scanning"] = scanner.is_scanning
            seen["lock_free"] = scanner._scan_lock.acquire(blocking=False)
            if seen["lock_free"]:
                scanner._scan_lock.release()
            return 4

        _run(scanner, wanted_count={"side_effect": count})

        assert seen == {"scanning": False, "lock_free": True}


class TestResumeIsSafe:
    def test_a_pending_resume_makes_the_next_scan_full(self):
        """Incremental scans in between would let the resume point expire."""
        scanner = _scanner()
        _run(scanner, stop_after=2)
        scanner._last_scan_timestamp = scanner._resume["started_at"]
        scanner._scan_count = 1

        scanned, _ = _run(scanner)

        assert scanned == [2, 3, 4]

    def test_rows_added_since_the_first_part_are_not_pruned_by_absence(self):
        """A skipped series may have gained an episode its old paths lack."""
        scanner = _scanner()
        _run(scanner, stop_after=2)
        first_start = scanner._resume["started_at"]
        _, cleanup = _run(scanner)

        assert cleanup.call_args.kwargs == {"protect_since": first_start}


class TestCleanupProtectsNewRows:
    def test_a_row_added_after_protect_since_survives_the_path_check(self):
        from datetime import UTC, datetime, timedelta

        now = datetime.now(UTC)
        rows = [
            {"id": 1, "file_path": "/m/old.mkv", "added_at": now - timedelta(days=1)},
            {
                "id": 2,
                "file_path": "/m/new.mkv",
                "added_at": (now + timedelta(hours=1)).replace(tzinfo=None),
            },
        ]
        rows = [{**r, "target_language": "de", "instance_name": "Main"} for r in rows]
        removed = []
        with (
            patch("db.wanted.get_wanted_items_for_cleanup", return_value=rows),
            patch("services.standalone_library.wanted_item_path_refusal", return_value=None),
            patch("services.wanted_scanner_core.os.path.exists", return_value=True),
            patch(
                "services.wanted_scanner_core.detect_existing_target_for_lang", return_value=None
            ),
            patch("services.wanted_scanner_core.existing_ignoring_suspects", return_value=None),
            patch("services.wanted_scanner_core.get_settings", return_value=_settings()),
            patch(
                "db.wanted.delete_wanted_items_by_ids", side_effect=lambda ids: removed.extend(ids)
            ),
        ):
            _scanner()._cleanup({"/m/other.mkv"}, protect_since=now)

        assert removed == [1]
