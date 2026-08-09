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


# ---------------------------------------------------------------------------
# on_startup gate — settings save must NOT trigger one-shot scan/search.
# ---------------------------------------------------------------------------


class _FakeSettingsOnStartupTrue:
    """Settings stub with both on_startup flags enabled (the default for search)."""

    wanted_scan_interval_hours = 6
    wanted_search_interval_hours = 24
    wanted_scan_on_startup = True
    wanted_search_on_startup = True


def test_start_scheduler_without_on_startup_does_not_spawn_daemon_threads(monkeypatch):
    """A settings save (default ``on_startup=False``) MUST NOT kick a scan/search.

    Regression for the bug where every config save spawned a fresh
    wanted_search daemon thread that bypassed adaptive backoff, slow-mode,
    backlog reserve, and fair-ordering — burning provider budget invisibly.
    """
    monkeypatch.setattr(
        "services.wanted_scanner_scheduler.get_settings",
        lambda: _FakeSettingsOnStartupTrue,
    )

    spawned: list[object] = []
    real_thread = __import__("threading").Thread

    def _capture_thread(*args, **kwargs):
        instance = real_thread(*args, **kwargs)
        spawned.append(instance)
        return instance

    monkeypatch.setattr("services.wanted_scanner_scheduler.threading.Thread", _capture_thread)

    scanner = WantedScanner()
    scanner.start_scheduler()  # default on_startup=False — settings-save path

    assert spawned == [], "start_scheduler() without on_startup=True must not spawn daemon threads"


def test_start_scheduler_with_on_startup_spawns_daemon_threads(monkeypatch):
    """The boot path (``on_startup=True``) honours the on_startup flags.

    Pins the legacy app-boot behaviour so we do not regress the
    settings-save fix into "never run on-startup tasks".
    """
    monkeypatch.setattr(
        "services.wanted_scanner_scheduler.get_settings",
        lambda: _FakeSettingsOnStartupTrue,
    )

    started: list[object] = []
    real_thread = __import__("threading").Thread

    class _NoStartThread:
        def __init__(self, *args, **kwargs):
            self._wrapped = real_thread(*args, **kwargs)
            started.append(self)

        def start(self):
            # Don't actually start — we just want to verify Thread() was created
            # with daemon=True and a target. Running the target would touch the
            # real DB / scheduler.
            pass

        @property
        def daemon(self):
            return self._wrapped.daemon

    monkeypatch.setattr("services.wanted_scanner_scheduler.threading.Thread", _NoStartThread)

    scanner = WantedScanner()
    scanner.start_scheduler(on_startup=True)

    # One thread for scan_on_startup, one for search_on_startup.
    assert len(started) == 2, "Expected scan + search daemons when on_startup=True"
    for t in started:
        assert t.daemon is True


def test_start_scheduler_on_startup_with_flags_off_does_not_spawn(monkeypatch):
    """``on_startup=True`` alone is not sufficient — the per-feature flags
    still gate the spawn. Pins this so a future refactor doesn't accidentally
    remove the user-facing setting."""
    monkeypatch.setattr("services.wanted_scanner_scheduler.get_settings", lambda: _FakeSettings)

    spawned: list[object] = []
    real_thread = __import__("threading").Thread
    monkeypatch.setattr(
        "services.wanted_scanner_scheduler.threading.Thread",
        lambda *a, **kw: spawned.append(real_thread(*a, **kw)) or real_thread(*a, **kw),
    )

    scanner = WantedScanner()
    scanner.start_scheduler(on_startup=True)

    assert spawned == []


def test_a_stopped_full_scan_never_prunes(app_ctx, monkeypatch):
    """The hazard specific to this job (#183, bug 3).

    A full scan removes every wanted item whose path it did not see. Stopping
    after the Sonarr phase would leave every Radarr and standalone path unseen
    — and deleting them is not a cosmetic wrong, it is the wanted queue.

    So a scan that was cut short must neither prune nor advance the incremental
    watermark: the phases it skipped were never looked at, and a watermark that
    moved would mean their changes are never picked up either.
    """
    import threading

    from services.scheduler import cancellation

    scanner = WantedScanner()
    event = threading.Event()
    cleaned: list[object] = []

    def _sonarr(settings, since):
        event.set()  # the stop arrives while the first phase runs
        return 1, 0, {"/media/show.mkv"}

    def _fail(*a, **k):
        raise AssertionError("a stopped scan must not start the next phase")

    monkeypatch.setattr(scanner, "_scan_all_sonarr", _sonarr, raising=False)
    monkeypatch.setattr(scanner, "_scan_all_radarr", _fail, raising=False)
    monkeypatch.setattr(scanner, "_scan_all_standalone", _fail, raising=False)
    monkeypatch.setattr(
        scanner, "_cleanup", lambda paths: cleaned.append(paths) or 0, raising=False
    )

    token = cancellation.activate(event)
    try:
        summary = scanner.scan_all(incremental=False)
    finally:
        cancellation.deactivate(token)

    assert cleaned == [], "a partial scan pruned the wanted queue against an incomplete path set"
    assert summary.get("removed") == 0
    assert scanner._last_scan_timestamp is None, (
        "the incremental watermark advanced past phases that were never scanned"
    )
