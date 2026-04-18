"""Refactor-safety tests for splitting routes/notifications_mgmt.py into a package.

Pins bp + all 17 URL rules + the `_validate_jinja2_syntax` re-export
(used by tests/test_routes_notifications.py:52).
"""

from __future__ import annotations

import pathlib

import flask

import routes.notifications_mgmt as notif_mod

EXPECTED_URL_RULES = {
    # Templates
    ("/api/v1/notifications/templates", "GET"),
    ("/api/v1/notifications/templates", "POST"),
    ("/api/v1/notifications/templates/<int:template_id>", "GET"),
    ("/api/v1/notifications/templates/<int:template_id>", "PUT"),
    ("/api/v1/notifications/templates/<int:template_id>", "DELETE"),
    ("/api/v1/notifications/templates/<int:template_id>/preview", "POST"),
    # Variables
    ("/api/v1/notifications/variables", "GET"),
    ("/api/v1/notifications/variables/<event_type>", "GET"),
    # Quiet hours
    ("/api/v1/notifications/quiet-hours", "GET"),
    ("/api/v1/notifications/quiet-hours", "POST"),
    ("/api/v1/notifications/quiet-hours/<int:config_id>", "PUT"),
    ("/api/v1/notifications/quiet-hours/<int:config_id>", "DELETE"),
    # History
    ("/api/v1/notifications/history", "GET"),
    ("/api/v1/notifications/history", "DELETE"),
    ("/api/v1/notifications/history/<int:notification_id>/resend", "POST"),
    # Filters
    ("/api/v1/notifications/filters", "GET"),
    ("/api/v1/notifications/filters", "PUT"),
}


def _collect_notif_rules(flask_app: flask.Flask) -> set[tuple[str, str]]:
    return {
        (rule.rule, method)
        for rule in flask_app.url_map.iter_rules()
        if rule.endpoint.startswith("notifications_mgmt.")
        for method in (rule.methods or set()) - {"HEAD", "OPTIONS"}
    }


def test_bp_is_blueprint() -> None:
    assert isinstance(notif_mod.bp, flask.Blueprint)
    assert notif_mod.bp.name == "notifications_mgmt"
    assert notif_mod.bp.url_prefix == "/api/v1/notifications"


def test_all_expected_routes_are_registered(app_ctx) -> None:
    registered = _collect_notif_rules(app_ctx)
    missing = EXPECTED_URL_RULES - registered
    assert not missing, f"Routes missing after refactor: {sorted(missing)}"


def test_no_unexpected_notif_routes(app_ctx) -> None:
    registered = _collect_notif_rules(app_ctx)
    extra = registered - EXPECTED_URL_RULES
    assert not extra, f"Unexpected routes after refactor: {sorted(extra)}"


def test_validate_jinja2_syntax_reexport_accessible() -> None:
    """tests/test_routes_notifications.py:52 imports this directly."""
    assert callable(notif_mod._validate_jinja2_syntax)
    # smoke: valid template -> None, broken -> error string
    assert notif_mod._validate_jinja2_syntax("{{ x }}") is None
    assert notif_mod._validate_jinja2_syntax("{% if %}") is not None


def test_package_init_stays_small_after_split() -> None:
    backend_root = pathlib.Path(__file__).resolve().parents[1]
    init_path = backend_root / "routes" / "notifications_mgmt" / "__init__.py"
    if not init_path.exists():
        import pytest

        pytest.skip("pre-split: routes/notifications_mgmt is still a single file")
    loc = sum(1 for _ in init_path.open(encoding="utf-8"))
    assert loc < 60, (
        f"routes/notifications_mgmt/__init__.py grew to {loc} LOC. "
        f"Move new code into a submodule."
    )
