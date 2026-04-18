"""Characterization tests pinning the module-level public API of routes.cleanup.

These tests must continue to pass across every extraction step of plan
2026-04-18-b1-routes-cleanup-split.md. They characterise the package-level
surface that existing callers (routes/__init__.py and test_routes_cleanup.py)
depend on.
"""

import threading

import pytest
from flask import Blueprint


def test_bp_importable_from_routes_cleanup():
    from routes.cleanup import bp

    assert isinstance(bp, Blueprint)
    assert bp.name == "cleanup"
    assert bp.url_prefix == "/api/v1/cleanup"


def test_scan_state_accessible_at_package_scope():
    import routes.cleanup as cleanup_mod

    assert hasattr(cleanup_mod, "_scan_state")
    assert isinstance(cleanup_mod._scan_state, dict)
    for key in ("running", "scan_id", "progress", "total", "result"):
        assert key in cleanup_mod._scan_state, f"_scan_state missing key: {key}"


def test_orphan_state_accessible_at_package_scope():
    import routes.cleanup as cleanup_mod

    assert hasattr(cleanup_mod, "_orphan_state")
    assert isinstance(cleanup_mod._orphan_state, dict)
    for key in ("running", "result"):
        assert key in cleanup_mod._orphan_state, f"_orphan_state missing key: {key}"


def test_scan_lock_accessible_at_package_scope():
    import routes.cleanup as cleanup_mod

    assert hasattr(cleanup_mod, "_scan_lock")
    # threading.Lock() returns a _thread.lock — not isinstance-checkable against Lock directly
    assert hasattr(cleanup_mod._scan_lock, "acquire")
    assert hasattr(cleanup_mod._scan_lock, "release")


def test_orphan_lock_accessible_at_package_scope():
    import routes.cleanup as cleanup_mod

    assert hasattr(cleanup_mod, "_orphan_lock")
    assert hasattr(cleanup_mod._orphan_lock, "acquire")
    assert hasattr(cleanup_mod._orphan_lock, "release")


def test_all_17_routes_registered_on_blueprint():
    """Pin that every URL currently served by /api/v1/cleanup stays served after the split."""
    from routes.cleanup import bp

    expected_rules = {
        ("POST", "/api/v1/cleanup/scan"),
        ("GET", "/api/v1/cleanup/scan/status"),
        ("GET", "/api/v1/cleanup/duplicates"),
        ("POST", "/api/v1/cleanup/duplicates/delete"),
        ("POST", "/api/v1/cleanup/orphaned/scan"),
        ("GET", "/api/v1/cleanup/orphaned"),
        ("POST", "/api/v1/cleanup/orphaned/delete"),
        ("GET", "/api/v1/cleanup/rules"),
        ("POST", "/api/v1/cleanup/rules"),
        ("PUT", "/api/v1/cleanup/rules/<int:rule_id>"),
        ("DELETE", "/api/v1/cleanup/rules/<int:rule_id>"),
        ("POST", "/api/v1/cleanup/rules/<int:rule_id>/run"),
        ("POST", "/api/v1/cleanup/rules/<int:rule_id>/preview"),
        ("GET", "/api/v1/cleanup/stats"),
        ("GET", "/api/v1/cleanup/history"),
        ("POST", "/api/v1/cleanup/preview"),
        ("POST", "/api/v1/cleanup/non-target-subs"),
    }

    # Flask stores rules with a *deferred* prefix on the blueprint itself; to resolve
    # the final URL we need to apply the blueprint to a throwaway Flask app.
    from flask import Flask

    app = Flask(__name__)
    app.register_blueprint(bp)

    actual_rules = set()
    for rule in app.url_map.iter_rules():
        if rule.endpoint.startswith("cleanup."):
            # Each rule has a methods set — expand to one (method, path) pair per method
            for method in rule.methods - {"HEAD", "OPTIONS"}:
                actual_rules.add((method, rule.rule))

    missing = expected_rules - actual_rules
    extra = actual_rules - expected_rules
    assert not missing, f"Missing routes: {missing}"
    assert not extra, f"Unexpected routes: {extra}"


def test_scan_state_is_mutable():
    """Existing tests write to _scan_state directly. Confirm the attribute supports it."""
    import routes.cleanup as cleanup_mod

    original = cleanup_mod._scan_state["running"]
    try:
        cleanup_mod._scan_state["running"] = not original
        assert cleanup_mod._scan_state["running"] != original
    finally:
        cleanup_mod._scan_state["running"] = original


def test_routes_cleanup_init_py_under_100_loc():
    """Pin B1/cleanup achievement: routes/cleanup/__init__.py must stay below 100 LOC.

    If you are adding dedup routes, put them in routes/cleanup/dedup.py.
    If you are adding orphan routes, put them in routes/cleanup/orphan.py.
    If you are adding rule-management routes, put them in routes/cleanup/rules.py.
    If you are adding stats/history routes, put them in routes/cleanup/stats.py.
    If you are adding preview / non-target-subs routes, put them in routes/cleanup/preview.py.
    routes/cleanup/__init__.py is intentionally a thin package facade with only
    the blueprint declaration, shared state, and submodule imports.
    """
    from pathlib import Path

    path = Path(__file__).parent.parent / "routes" / "cleanup" / "__init__.py"
    assert path.exists(), f"routes/cleanup/__init__.py not found at {path}"
    line_count = sum(1 for _ in path.open(encoding="utf-8"))
    assert line_count < 100, (
        f"backend/routes/cleanup/__init__.py is {line_count} LOC, must stay below 100. "
        "Move new routes into the appropriate submodule (see docstring)."
    )
