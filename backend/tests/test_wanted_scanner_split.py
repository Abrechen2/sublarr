"""Smoke tests: verify wanted_scanner public API survives the split."""

from unittest.mock import patch

from services.wanted_scanner import WantedScanner, get_scanner, invalidate_scanner


def test_get_scanner_returns_wanted_scanner_instance():
    scanner = get_scanner()
    assert isinstance(scanner, WantedScanner)


def test_invalidate_scanner_resets_singleton():
    s1 = get_scanner()
    invalidate_scanner()
    s2 = get_scanner()
    # After invalidation a new instance is created
    assert s1 is not s2


def test_wanted_scanner_class_importable_from_facade():
    """WantedScanner must be importable from the facade module."""
    from services import wanted_scanner as mod

    assert hasattr(mod, "WantedScanner")
    assert hasattr(mod, "get_scanner")
    assert hasattr(mod, "invalidate_scanner")


# ---------------------------------------------------------------------------
# Scheduler idempotency — regression for prod-audit finding
# ---------------------------------------------------------------------------


class _FakeSettings:
    """Minimal settings stub for start_scheduler invocation."""

    wanted_scan_interval_hours = 6
    wanted_search_interval_hours = 24
    wanted_scan_on_startup = False
    wanted_search_on_startup = False


def test_start_scheduler_cancels_old_timers_before_creating_new_ones():
    """Repeated start_scheduler() calls must not leak concurrent timer chains.

    Prior to this guard, saving settings via the config UI (which calls
    start_scheduler() without stopping first) leaked both scan and search
    timers every time, so after N config saves N parallel timer chains
    would fire.
    """
    scanner = WantedScanner()

    with patch("services.wanted_scanner_scheduler.get_settings", return_value=_FakeSettings):
        scanner.start_scheduler()
        first_scan_timer = scanner._timer
        first_search_timer = scanner._search_timer
        assert first_scan_timer is not None
        assert first_search_timer is not None

        # Second call — must cancel the first pair and swap in new timers.
        scanner.start_scheduler()
        second_scan_timer = scanner._timer
        second_search_timer = scanner._search_timer

    try:
        assert second_scan_timer is not first_scan_timer
        assert second_search_timer is not first_search_timer
        # Old timers must have been cancelled (not just dereferenced).
        assert first_scan_timer.finished.is_set()
        assert first_search_timer.finished.is_set()
    finally:
        # Clean up active timers so the test doesn't leave threads hanging.
        scanner.stop_scheduler()


def test_schedule_next_scan_cancels_previous_scan_timer():
    """_schedule_next_scan must not leak when called twice in a row."""
    scanner = WantedScanner()
    try:
        scanner._schedule_next_scan(6)
        first = scanner._timer
        scanner._schedule_next_scan(6)
        second = scanner._timer
        assert first is not second
        assert first.finished.is_set()
    finally:
        scanner.stop_scheduler()


def test_schedule_next_search_cancels_previous_search_timer():
    scanner = WantedScanner()
    try:
        scanner._schedule_next_search(24)
        first = scanner._search_timer
        scanner._schedule_next_search(24)
        second = scanner._search_timer
        assert first is not second
        assert first.finished.is_set()
    finally:
        scanner.stop_scheduler()


def test_stop_scheduler_cancels_both_timers():
    scanner = WantedScanner()
    with patch("services.wanted_scanner_scheduler.get_settings", return_value=_FakeSettings):
        scanner.start_scheduler()
        scan_timer = scanner._timer
        search_timer = scanner._search_timer
        scanner.stop_scheduler()

    assert scanner._timer is None
    assert scanner._search_timer is None
    assert scan_timer.finished.is_set()
    assert search_timer.finished.is_set()
