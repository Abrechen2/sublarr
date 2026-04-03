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
