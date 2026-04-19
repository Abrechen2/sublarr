"""Smoke tests: verify wanted_scanner public API survives the split."""

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
# Adapter idempotency — Phase 5 / P4 migration to APScheduler.
# The legacy threading.Timer tests were deleted because lifecycle is now
# owned by APScheduler (see services/scheduler.py). These tests exercise
# the adapter contract: start_scheduler caches app/socketio and does not
# raise, stop_scheduler is a no-op.
# ---------------------------------------------------------------------------


class _FakeSettings:
    """Minimal settings stub for start_scheduler invocation."""

    wanted_scan_interval_hours = 6
    wanted_search_interval_hours = 24
    wanted_scan_on_startup = False
    wanted_search_on_startup = False


def test_start_scheduler_is_idempotent(monkeypatch):
    """Repeated start_scheduler() calls must not raise or leak state.

    Under APScheduler the mixin is an adapter — repeated calls simply
    push the latest interval to the scheduler. No timers are created.
    """
    scanner = WantedScanner()
    monkeypatch.setattr("services.wanted_scanner_scheduler.get_settings", lambda: _FakeSettings)

    # First call caches app=None / socketio=None and records scheduler_started_at.
    scanner.start_scheduler()
    first_started_at = scanner._scheduler_started_at
    assert first_started_at is not None

    # Second call — must not raise. scheduler_started_at is refreshed.
    scanner.start_scheduler()
    assert scanner._scheduler_started_at is not None


def test_stop_scheduler_is_noop():
    """stop_scheduler must not raise; APScheduler owns lifecycle now."""
    scanner = WantedScanner()
    assert scanner.stop_scheduler() is None
