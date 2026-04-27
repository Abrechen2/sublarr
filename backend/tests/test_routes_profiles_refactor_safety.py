"""Refactor-safety tests for splitting routes/profiles.py into a package.

Pins the public surface + all 16 URL rules so the B1Pr split cannot
silently break callers or drop an endpoint.
"""

from __future__ import annotations

import pathlib

import flask

import routes.profiles as profiles_mod

EXPECTED_URL_RULES = {
    # Language profiles
    ("/api/v1/language-profiles", "GET"),
    ("/api/v1/language-profiles", "POST"),
    ("/api/v1/language-profiles/<int:profile_id>", "PUT"),
    ("/api/v1/language-profiles/<int:profile_id>", "DELETE"),
    ("/api/v1/language-profiles/assign", "PUT"),
    ("/api/v1/language-profiles/assign-bulk", "PUT"),
    ("/api/v1/language-profiles/<int:profile_id>/set-as-default-for-all", "POST"),
    # Glossary
    ("/api/v1/glossary", "GET"),
    ("/api/v1/glossary", "POST"),
    ("/api/v1/glossary/<int:entry_id>", "PUT"),
    ("/api/v1/glossary/<int:entry_id>", "DELETE"),
    ("/api/v1/glossary/export", "GET"),
    # Prompt presets
    ("/api/v1/prompt-presets", "GET"),
    ("/api/v1/prompt-presets", "POST"),
    ("/api/v1/prompt-presets/default", "GET"),
    ("/api/v1/prompt-presets/<int:preset_id>", "PUT"),
    ("/api/v1/prompt-presets/<int:preset_id>", "DELETE"),
}


def _collect_profiles_rules(flask_app: flask.Flask) -> set[tuple[str, str]]:
    return {
        (rule.rule, method)
        for rule in flask_app.url_map.iter_rules()
        if rule.endpoint.startswith("profiles.")
        for method in (rule.methods or set()) - {"HEAD", "OPTIONS"}
    }


def test_bp_is_blueprint() -> None:
    assert hasattr(profiles_mod, "bp")
    assert isinstance(profiles_mod.bp, flask.Blueprint)
    assert profiles_mod.bp.name == "profiles"
    assert profiles_mod.bp.url_prefix == "/api/v1"


def test_all_expected_routes_are_registered(app_ctx) -> None:
    registered = _collect_profiles_rules(app_ctx)
    missing = EXPECTED_URL_RULES - registered
    assert not missing, f"Routes missing after refactor: {sorted(missing)}"


def test_no_unexpected_profiles_routes(app_ctx) -> None:
    registered = _collect_profiles_rules(app_ctx)
    extra = registered - EXPECTED_URL_RULES
    assert not extra, f"Unexpected routes after refactor: {sorted(extra)}"


def test_package_init_stays_small_after_split() -> None:
    backend_root = pathlib.Path(__file__).resolve().parents[1]
    init_path = backend_root / "routes" / "profiles" / "__init__.py"
    if not init_path.exists():
        import pytest

        pytest.skip("pre-split: routes/profiles is still a single file")
    loc = sum(1 for _ in init_path.open(encoding="utf-8"))
    assert loc < 60, (
        f"routes/profiles/__init__.py grew to {loc} LOC — plan targets < 30. "
        f"Move new code into a submodule."
    )
