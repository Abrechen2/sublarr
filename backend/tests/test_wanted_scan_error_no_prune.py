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
