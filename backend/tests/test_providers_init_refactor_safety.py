"""Characterization tests for backend/providers/__init__.py refactor (B1).

These tests pin the public API and singleton contract of the providers package
BEFORE extraction tasks T2-T5 begin.  After every extraction step in the plan
2026-04-18-b1-providers-init-split.md this file MUST keep passing without
modification.

Key behaviour pinned here:
- 10 public symbols importable from `providers`
- Singleton identity / invalidation / in-place update contract
- `register_provider` duplicate-name handling (first wins, warning logged)
- `get_provider_status()` return shape
- `get_provider_summary()` return shape
- `shutdown()` does not raise

NOTE: Tests that exercise ProviderManager() directly require a Flask app
context + a live database (the constructor calls get_provider_stats() via
_init_providers).  These tests use the shared ``app_ctx`` fixture from
conftest.py which sets up a temp SQLite DB and pushes an app context.

Tests that do NOT construct ProviderManager or call get_provider_manager
(the 10 import tests, the duplicate-name test) work without any app context.

Singleton teardown is handled by the ``reset_provider_manager`` autouse
fixture in conftest.py — no duplicate fixture is needed here.
"""

# ---------------------------------------------------------------------------
# 1. Public symbols importable from `providers`
# ---------------------------------------------------------------------------


def test_provider_manager_class_importable_from_providers():
    from providers import ProviderManager

    assert ProviderManager is not None
    assert isinstance(ProviderManager, type)


def test_get_provider_manager_importable():
    from providers import get_provider_manager

    assert get_provider_manager is not None
    assert callable(get_provider_manager)


def test_invalidate_manager_importable():
    from providers import invalidate_manager

    assert invalidate_manager is not None
    assert callable(invalidate_manager)


def test_update_manager_providers_importable():
    from providers import update_manager_providers

    assert update_manager_providers is not None
    assert callable(update_manager_providers)


def test_register_provider_importable():
    from providers import register_provider

    assert register_provider is not None
    assert callable(register_provider)


def test_provider_classes_dict_importable():
    from providers import _PROVIDER_CLASSES

    assert _PROVIDER_CLASSES is not None
    assert isinstance(_PROVIDER_CLASSES, dict)


def test_stream_download_importable():
    from providers import _stream_download

    assert _stream_download is not None
    assert callable(_stream_download)


def test_validate_subtitle_content_importable():
    from providers import _validate_subtitle_content

    assert _validate_subtitle_content is not None
    assert callable(_validate_subtitle_content)


def test_compute_score_importable():
    from providers import compute_score

    assert compute_score is not None
    assert callable(compute_score)


def test_provider_exceptions_importable():
    from providers import ProviderAuthError, ProviderRateLimitError, ProviderTimeoutError

    for exc_cls in (ProviderAuthError, ProviderRateLimitError, ProviderTimeoutError):
        assert exc_cls is not None
        assert isinstance(exc_cls, type)
        assert issubclass(exc_cls, Exception)


# ---------------------------------------------------------------------------
# 2. Singleton contract (require app_ctx because get_provider_manager
#    calls ProviderManager() which hits the DB via _init_providers)
# ---------------------------------------------------------------------------


def test_get_provider_manager_returns_singleton(app_ctx):
    from providers import get_provider_manager

    m1 = get_provider_manager()
    m2 = get_provider_manager()
    assert m1 is m2


def test_invalidate_manager_creates_new_instance_on_next_call(app_ctx):
    from providers import get_provider_manager, invalidate_manager

    m1 = get_provider_manager()
    invalidate_manager()
    m2 = get_provider_manager()
    assert m2 is not m1


def test_update_manager_providers_mutates_live_singleton(app_ctx):
    """update_manager_providers must NOT replace the singleton — it mutates it."""
    from providers import get_provider_manager, update_manager_providers

    m1 = get_provider_manager()
    # "opensubtitles" is always registered as a built-in; minimal valid arg.
    update_manager_providers("opensubtitles")
    m2 = get_provider_manager()
    # Identity must be preserved — same object, not a new one.
    assert m2 is m1


# ---------------------------------------------------------------------------
# 3. register_provider duplicate-name handling (no app_ctx needed)
# ---------------------------------------------------------------------------


def test_register_provider_rejects_duplicate_name(caplog):
    """When two classes share the same .name, the first wins.

    The second call must:
    - return the second class unchanged (decorator pass-through)
    - NOT overwrite the registry entry
    - emit a warning log
    """
    import logging

    from providers import _PROVIDER_CLASSES, register_provider

    # Use a name unlikely to clash with real providers.
    _test_name = "_test_dup_provider_safety_xyz"

    # Ensure no leftover from a previous run.
    _PROVIDER_CLASSES.pop(_test_name, None)

    try:

        class FirstProvider:
            name = _test_name

        class SecondProvider:
            name = _test_name

        # Register the first — should succeed.
        result_first = register_provider(FirstProvider)
        assert result_first is FirstProvider
        assert _PROVIDER_CLASSES[_test_name] is FirstProvider

        # Register the second — duplicate, should be rejected with a warning.
        with caplog.at_level(logging.WARNING, logger="providers"):
            result_second = register_provider(SecondProvider)

        # Decorator always returns its input (callers can still use the class).
        assert result_second is SecondProvider
        # But the registry still points at the first registration.
        assert _PROVIDER_CLASSES[_test_name] is FirstProvider
        # A warning must have been logged.
        assert any("collision" in record.message.lower() for record in caplog.records), (
            "Expected a 'collision' warning in the log, but got: "
            + str([r.message for r in caplog.records])
        )

    finally:
        # Clean up the test entry so we do not pollute other tests.
        _PROVIDER_CLASSES.pop(_test_name, None)


# ---------------------------------------------------------------------------
# 4. get_provider_status() shape
# ---------------------------------------------------------------------------

_STATUS_KEYS = frozenset(
    {
        "name",
        "enabled",
        "initialized",
        "healthy",
        "message",
        "priority",
        "downloads",
        "config_fields",
        "stats",
        "circuit_breaker_state",
        "throttled_until",
        "throttle_reason",
    }
)

_STATS_KEYS = frozenset(
    {
        "total_searches",
        "successful_downloads",
        "failed_downloads",
        "success_rate",
        "avg_score",
        "consecutive_failures",
        "last_success_at",
        "last_failure_at",
        "avg_response_time_ms",
        "last_response_time_ms",
        "auto_disabled",
        "disabled_until",
    }
)


def test_get_provider_status_shape(app_ctx):
    """get_provider_status() must return a list of dicts with the expected keys."""
    from providers import ProviderManager

    manager = ProviderManager()
    try:
        result = manager.get_provider_status()

        assert isinstance(result, list), f"Expected list, got {type(result)}"

        for entry in result:
            assert isinstance(entry, dict), f"Expected dict entry, got {type(entry)}"
            missing = _STATUS_KEYS - entry.keys()
            assert not missing, f"Entry missing keys: {missing}\nEntry: {entry}"

            # `stats` sub-dict must also have the expected keys.
            stats = entry["stats"]
            assert isinstance(stats, dict), f"Expected stats to be dict, got {type(stats)}"
            missing_stats = _STATS_KEYS - stats.keys()
            assert not missing_stats, f"Stats dict missing keys: {missing_stats}"
    finally:
        manager.shutdown()


# ---------------------------------------------------------------------------
# 5. get_provider_summary() shape
# ---------------------------------------------------------------------------

_SUMMARY_KEYS = frozenset({"active", "throttled", "circuit_open", "throttled_providers"})


def test_get_provider_summary_shape(app_ctx):
    """get_provider_summary() must return a dict with the expected top-level keys."""
    from providers import ProviderManager

    manager = ProviderManager()
    try:
        result = manager.get_provider_summary()

        assert isinstance(result, dict), f"Expected dict, got {type(result)}"
        missing = _SUMMARY_KEYS - result.keys()
        assert not missing, f"Summary dict missing keys: {missing}\nResult: {result}"

        # Basic type checks on values.
        assert isinstance(result["active"], int)
        assert isinstance(result["throttled"], int)
        assert isinstance(result["circuit_open"], int)
        assert isinstance(result["throttled_providers"], list)
    finally:
        manager.shutdown()


# ---------------------------------------------------------------------------
# 6. shutdown() does not raise
# ---------------------------------------------------------------------------


def test_shutdown_does_not_raise(app_ctx):
    """ProviderManager.shutdown() must complete without raising any exception."""
    from providers import ProviderManager

    manager = ProviderManager()
    # Should not raise regardless of provider state.
    manager.shutdown()
