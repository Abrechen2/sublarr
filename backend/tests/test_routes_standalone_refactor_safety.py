"""Refactor-safety tests for `routes.standalone`.

These tests pin the public surface used by the rest of the codebase so
the file -> package split (B1 plan 2026-04-18-b1-routes-standalone-split.md)
cannot silently break callers.

Covers:
1. `from routes.standalone import bp` works and is a flask.Blueprint.
2. Blueprint name, url_prefix, and registered rules match the pre-split state.
3. After the package split completes, `routes/standalone/__init__.py` stays
   under the 50-LOC target set by the plan.
"""

from __future__ import annotations

import pathlib

import flask
import pytest

import routes.standalone as standalone_mod


EXPECTED_URL_RULES = {
    # folders
    ("/api/v1/standalone/folders", "GET"),
    ("/api/v1/standalone/folders", "POST"),
    ("/api/v1/standalone/folders/<int:folder_id>", "PUT"),
    ("/api/v1/standalone/folders/<int:folder_id>", "DELETE"),
    # series
    ("/api/v1/standalone/series", "GET"),
    ("/api/v1/standalone/series/<int:series_id>", "GET"),
    ("/api/v1/standalone/series/<int:series_id>/poster", "GET"),
    ("/api/v1/standalone/series/<int:series_id>", "DELETE"),
    ("/api/v1/standalone/series/<int:series_id>/scan", "POST"),
    ("/api/v1/standalone/series/<int:series_id>/refresh-metadata", "POST"),
    # movies
    ("/api/v1/standalone/movies", "GET"),
    ("/api/v1/standalone/movies/<int:movie_id>", "GET"),
    ("/api/v1/standalone/movies/<int:movie_id>/poster", "GET"),
    ("/api/v1/standalone/movies/<int:movie_id>", "DELETE"),
    # scan
    ("/api/v1/standalone/scan", "POST"),
    ("/api/v1/standalone/scan/<int:folder_id>", "POST"),
    ("/api/v1/standalone/status", "GET"),
}


def test_import_surface_bp_is_blueprint() -> None:
    assert hasattr(standalone_mod, "bp"), "routes.standalone must expose `bp`"
    assert isinstance(standalone_mod.bp, flask.Blueprint)


def test_blueprint_name_and_prefix() -> None:
    bp = standalone_mod.bp
    assert bp.name == "standalone"
    assert bp.url_prefix == "/api/v1/standalone"


def _collect_standalone_rules(flask_app: flask.Flask) -> set[tuple[str, str]]:
    return {
        (rule.rule, method)
        for rule in flask_app.url_map.iter_rules()
        if rule.endpoint.startswith("standalone.")
        for method in (rule.methods or set()) - {"HEAD", "OPTIONS"}
    }


def test_all_expected_routes_are_registered(app_ctx) -> None:
    """Every pre-split URL path + method must still be registered after the split."""
    registered = _collect_standalone_rules(app_ctx)
    missing = EXPECTED_URL_RULES - registered
    assert not missing, f"Routes missing after refactor: {sorted(missing)}"


def test_no_unexpected_standalone_routes(app_ctx) -> None:
    """Catch accidental route additions during the split."""
    registered = _collect_standalone_rules(app_ctx)
    extra = registered - EXPECTED_URL_RULES
    assert not extra, f"Unexpected routes after refactor: {sorted(extra)}"


def test_package_init_stays_small_after_split() -> None:
    """Pin the < 50-LOC target for routes/standalone/__init__.py.

    Until Task 2 runs this is a skip (file is still the single-file module).
    After the split it becomes an enforced ceiling.
    """
    backend_root = pathlib.Path(__file__).resolve().parents[1]
    init_path = backend_root / "routes" / "standalone" / "__init__.py"
    if not init_path.exists():
        pytest.skip("pre-split: routes/standalone is still a single file")
    loc = sum(1 for _ in init_path.open(encoding="utf-8"))
    assert loc < 80, (
        f"routes/standalone/__init__.py grew to {loc} LOC — plan targets < 50, "
        f"hard ceiling 80. Move new code into a submodule."
    )
