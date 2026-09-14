"""A wanted scan whose source errored must not prune — and must not advance.

Prod 2026-08-30 20:34Z: the whole stack restarted, the boot-time full scan
started before Postgres accepted connections, the Sonarr sweep died with
``server closed the connection unexpectedly`` — and the cleanup that
followed pruned every Sonarr item against a path set the failed source
never got to fill: 9 369 wanted items dropped to 154 in one pass. They
came back 35 hours later as brand-new rows (search_count=0, no backoff),
which re-searched an 11k backlog in a day and burned provider quota on
subtitles that were already on disk.

The scan already refuses to prune after a stop request; these tests pin
the same refusal for a failed source, plus the frozen watermark.
"""

from unittest.mock import MagicMock, patch


def _scanner():
    from services.wanted_scanner_core import WantedScanner

    s = WantedScanner.__new__(WantedScanner)
    s.__init__()
    return s


def _run_scan(scanner, sonarr_fails: bool):
    def scan_sonarr(settings, since=None):
        if sonarr_fails:
            # Mirror the mixin's real behavior: swallow, flag, return empty.
            scanner._scan_had_errors = True
            return 0, 0, set()
        return 2, 0, {"/media/a.mkv", "/media/b.mkv"}

    with (
        patch.object(scanner, "_scan_all_sonarr", side_effect=scan_sonarr),
        patch.object(scanner, "_scan_all_radarr", return_value=(1, 0, {"/media/c.mkv"})),
        patch.object(scanner, "_scan_all_standalone", return_value=(0, 0, set())),
        patch.object(scanner, "_cleanup", return_value=0) as cleanup,
        patch("services.wanted_scanner_core.get_settings", return_value=MagicMock()),
        patch("services.wanted_scanner_core.abort_requested", return_value=False),
        patch("services.wanted_scanner_core.log_activity"),
        patch("db.wanted.get_wanted_count", return_value=42),
    ):
        summary = scanner.scan_all(incremental=False)
    return summary, cleanup


class TestScanErrorSkipsPrune:
    def test_failed_source_skips_cleanup(self):
        scanner = _scanner()
        summary, cleanup = _run_scan(scanner, sonarr_fails=True)
        cleanup.assert_not_called()
        assert summary["removed"] == 0

    def test_failed_source_freezes_watermark_and_cycle(self):
        scanner = _scanner()
        _run_scan(scanner, sonarr_fails=True)
        assert scanner._last_scan_timestamp is None
        assert scanner._scan_count == 0

    def test_clean_scan_still_prunes_and_advances(self):
        scanner = _scanner()
        _, cleanup = _run_scan(scanner, sonarr_fails=False)
        cleanup.assert_called_once()
        assert scanner._last_scan_timestamp is not None
        assert scanner._scan_count == 1


def _run_scan_aborting(scanner, *, abort_after_sonarr: bool = True):
    """A scan whose sources answer fine but which is asked to stop on time."""
    calls = {"n": 0}

    def aborted_now():
        # Clean on entry, stop requested once the first source is done —
        # which is what the scheduler's cooperative timeout produces.
        calls["n"] += 1
        return abort_after_sonarr and calls["n"] > 1

    with (
        patch.object(scanner, "_scan_all_sonarr", return_value=(2, 0, {"/media/a.mkv"})),
        patch.object(scanner, "_scan_all_radarr", return_value=(1, 0, {"/media/c.mkv"})),
        patch.object(scanner, "_scan_all_standalone", return_value=(0, 0, set())),
        patch.object(scanner, "_cleanup", return_value=0),
        patch("services.wanted_scanner_core.get_settings", return_value=MagicMock()),
        patch("services.wanted_scanner_core.abort_requested", side_effect=aborted_now),
        patch("services.wanted_scanner_core.log_activity"),
        patch("db.wanted.get_wanted_count", return_value=42),
    ):
        return scanner.scan_all(incremental=False)


class TestAbortDoesNotStickTheRotation:
    """Running out of time is not the same as a source that failed.

    Prod 2026-09-10 to 09-14: a full scan on an 11 900-item queue exceeded the
    hour it is given, was asked to stop, and therefore did not advance the
    rotation counter — so the next scan was full as well, overran as well, and
    the scanner never came back out. Eleven of twelve scans ran full against a
    one-in-six cadence, rewriting ~11 800 rows every six hours instead of every
    thirty-six. The one escape was a full scan that happened to finish four
    minutes under the wire.

    Coverage is not at risk from advancing the counter: the watermark below
    keeps its own guard, so the next incremental pass still asks for changes
    since the last pass that actually completed.
    """

    def test_an_aborted_scan_still_advances_the_rotation(self):
        scanner = _scanner()
        _run_scan_aborting(scanner)

        assert scanner._scan_count == 1, (
            "an aborted full scan scheduled another full scan, for ever"
        )

    def test_an_aborted_scan_still_freezes_the_watermark(self):
        """The half of the guard that must stay: it protects coverage."""
        scanner = _scanner()
        _run_scan_aborting(scanner)

        assert scanner._last_scan_timestamp is None

    def test_a_failed_source_still_freezes_both(self):
        """Regression guard for 2026-08-30 — that case is unchanged."""
        scanner = _scanner()
        _run_scan(scanner, sonarr_fails=True)

        assert scanner._last_scan_timestamp is None
        assert scanner._scan_count == 0
