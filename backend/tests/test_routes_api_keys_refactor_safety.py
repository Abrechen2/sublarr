"""Refactor-safety tests for `routes.api_keys`.

Pins the public surface needed by the existing test suite and by
routes/__init__.py so the B1A split cannot silently break callers.

Covers:
1. `from routes.api_keys import bp` works and is a flask.Blueprint.
2. All 8 expected URL rules are registered under /api/v1/api-keys.
3. Public re-exports are accessible at `routes.api_keys.<name>`:
   - `_mask_value` (imported by tests/test_routes_api_keys.py line 16)
   - `_TEST_DISPATCH` (patched via patch.dict in several tests)
   - `_test_sonarr` (auxiliary patch target, must be importable)
   - `API_KEY_REGISTRY` (data that tests indirectly depend on)
4. After the package split completes, `routes/api_keys/__init__.py` stays
   under the 80-LOC target set by the plan.
"""

from __future__ import annotations

import pathlib

import flask
import pytest

import routes.api_keys as api_keys_mod

EXPECTED_URL_RULES = {
    ("/api/v1/api-keys/", "GET"),
    ("/api/v1/api-keys/<service>", "GET"),
    ("/api/v1/api-keys/<service>", "PUT"),
    ("/api/v1/api-keys/<service>/test", "POST"),
    ("/api/v1/api-keys/export", "POST"),
    ("/api/v1/api-keys/import", "POST"),
    ("/api/v1/api-keys/import/bazarr", "POST"),
}


def _collect_api_keys_rules(flask_app: flask.Flask) -> set[tuple[str, str]]:
    return {
        (rule.rule, method)
        for rule in flask_app.url_map.iter_rules()
        if rule.endpoint.startswith("api_keys.")
        for method in (rule.methods or set()) - {"HEAD", "OPTIONS"}
    }


def test_import_surface_bp_is_blueprint() -> None:
    assert hasattr(api_keys_mod, "bp"), "routes.api_keys must expose `bp`"
    assert isinstance(api_keys_mod.bp, flask.Blueprint)


def test_blueprint_name_and_prefix() -> None:
    bp = api_keys_mod.bp
    assert bp.name == "api_keys"
    assert bp.url_prefix == "/api/v1/api-keys"


def test_all_expected_routes_are_registered(app_ctx) -> None:
    """Every pre-split URL path + method must still be registered after the split."""
    registered = _collect_api_keys_rules(app_ctx)
    missing = EXPECTED_URL_RULES - registered
    assert not missing, f"Routes missing after refactor: {sorted(missing)}"


def test_no_unexpected_api_keys_routes(app_ctx) -> None:
    """Catch accidental route additions during the split."""
    registered = _collect_api_keys_rules(app_ctx)
    extra = registered - EXPECTED_URL_RULES
    assert not extra, f"Unexpected routes after refactor: {sorted(extra)}"


def test_public_reexports_stay_accessible() -> None:
    """These names MUST stay accessible at `routes.api_keys.<name>` for tests."""
    assert callable(api_keys_mod._mask_value)
    assert isinstance(api_keys_mod._TEST_DISPATCH, dict)
    # _test_sonarr is indexed into _TEST_DISPATCH and patched by tests
    assert "_test_sonarr" in api_keys_mod._TEST_DISPATCH
    assert callable(api_keys_mod._TEST_DISPATCH["_test_sonarr"])
    assert isinstance(api_keys_mod.API_KEY_REGISTRY, dict)
    assert "sonarr" in api_keys_mod.API_KEY_REGISTRY


def test_mask_value_behaviour_unchanged() -> None:
    """Quick behaviour pin for _mask_value."""
    from routes.api_keys import _mask_value

    assert _mask_value("") == ""
    assert _mask_value("short") == "***"  # <= 8 chars
    assert _mask_value("exactly8") == "***"  # == 8 chars
    assert _mask_value("abcdefghijklmn") == "abcd***klmn"  # first4 *** last4


def test_package_init_stays_small_after_split() -> None:
    """Pin the < 80-LOC ceiling for routes/api_keys/__init__.py."""
    backend_root = pathlib.Path(__file__).resolve().parents[1]
    init_path = backend_root / "routes" / "api_keys" / "__init__.py"
    if not init_path.exists():
        pytest.skip("pre-split: routes/api_keys is still a single file")
    loc = sum(1 for _ in init_path.open(encoding="utf-8"))
    assert loc < 80, (
        f"routes/api_keys/__init__.py grew to {loc} LOC — plan targets < 40, "
        f"hard ceiling 80. Move new code into a submodule."
    )
