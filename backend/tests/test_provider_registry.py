"""Tests for providers/registry.py and ProviderManager's use of it."""

import threading
from collections import defaultdict

# ---------------------------------------------------------------------------
# Registry structure tests
# ---------------------------------------------------------------------------


def test_registry_has_required_keys():
    from providers.registry import PROVIDER_METADATA

    for name, meta in PROVIDER_METADATA.items():
        assert "rate_limit" in meta, f"{name} missing rate_limit"
        assert "timeout" in meta, f"{name} missing timeout"
        assert "retries" in meta, f"{name} missing retries"


def test_opensubtitles_values():
    from providers.registry import PROVIDER_METADATA

    meta = PROVIDER_METADATA["opensubtitles"]
    assert meta["rate_limit"] == (40, 10)
    assert meta["timeout"] == 10
    assert meta["retries"] == 3


def test_jimaku_values():
    from providers.registry import PROVIDER_METADATA

    meta = PROVIDER_METADATA["jimaku"]
    assert meta["rate_limit"] == (100, 60)
    assert meta["timeout"] == 12
    assert meta["retries"] == 2


def test_animetosho_values():
    from providers.registry import PROVIDER_METADATA

    meta = PROVIDER_METADATA["animetosho"]
    assert meta["rate_limit"] == (50, 30)
    assert meta["timeout"] == 10
    assert meta["retries"] == 2


def test_subdl_values():
    from providers.registry import PROVIDER_METADATA

    meta = PROVIDER_METADATA["subdl"]
    assert meta["rate_limit"] == (30, 10)
    assert meta["timeout"] == 10
    assert meta["retries"] == 2


# ---------------------------------------------------------------------------
# ProviderManager method tests (bypass __init__ to avoid DB/provider overhead)
# ---------------------------------------------------------------------------


def _make_bare_manager(global_timeout: int = 30):
    """Create a ProviderManager without calling __init__."""
    from providers import ProviderManager

    manager = object.__new__(ProviderManager)
    manager.settings = type(
        "_FakeSettings",
        (),
        {"provider_search_timeout": global_timeout},
    )()
    manager._providers = {}
    manager._rate_limits = defaultdict(list)
    manager._rate_limit_lock = threading.Lock()
    manager._circuit_breakers = {}
    return manager


def test_get_rate_limit_uses_registry(monkeypatch):
    """_get_rate_limit falls back to PROVIDER_METADATA when no class attribute overrides it."""
    import providers as _providers_module
    from providers.registry import PROVIDER_METADATA

    monkeypatch.setattr(_providers_module, "_PROVIDER_CLASSES", {})

    manager = _make_bare_manager()
    assert (
        manager._get_rate_limit("opensubtitles") == PROVIDER_METADATA["opensubtitles"]["rate_limit"]
    )
    assert manager._get_rate_limit("jimaku") == PROVIDER_METADATA["jimaku"]["rate_limit"]


def test_get_rate_limit_unknown_provider_returns_no_limit():
    manager = _make_bare_manager()
    assert manager._get_rate_limit("unknown_provider") == (0, 0)


def test_get_timeout_uses_registry(monkeypatch):
    """_get_timeout falls back to PROVIDER_METADATA when no class attribute overrides it."""
    import providers as _providers_module
    from providers.registry import PROVIDER_METADATA

    # Ensure _PROVIDER_CLASSES is empty so no class attribute can shadow the registry lookup.
    monkeypatch.setattr(_providers_module, "_PROVIDER_CLASSES", {})

    manager = _make_bare_manager(global_timeout=30)
    assert manager._get_timeout("opensubtitles") == PROVIDER_METADATA["opensubtitles"]["timeout"]
    assert manager._get_timeout("jimaku") == PROVIDER_METADATA["jimaku"]["timeout"]


def test_get_timeout_unknown_falls_back_to_global():
    manager = _make_bare_manager(global_timeout=42)
    assert manager._get_timeout("unknown_provider") == 42


def test_get_retries_uses_registry(monkeypatch):
    """_get_retries falls back to PROVIDER_METADATA when no class attribute overrides it."""
    import providers as _providers_module
    from providers.registry import PROVIDER_METADATA

    monkeypatch.setattr(_providers_module, "_PROVIDER_CLASSES", {})

    manager = _make_bare_manager()
    assert manager._get_retries("opensubtitles") == PROVIDER_METADATA["opensubtitles"]["retries"]
    assert manager._get_retries("animetosho") == PROVIDER_METADATA["animetosho"]["retries"]


def test_get_retries_unknown_provider_returns_default():
    manager = _make_bare_manager()
    # Default is 2 (unchanged from previous PROVIDER_RETRIES dict)
    assert manager._get_retries("unknown_provider") == 2
