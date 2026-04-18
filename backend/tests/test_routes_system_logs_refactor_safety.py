"""Refactor-safety tests for splitting routes/system/logs.py into siblings.

Pins the public surface used by tests/test_support_export.py and by
downstream callers so the split into `logs.py`, `support.py`,
`maintenance.py` cannot silently break anyone.

Covers:
1. `from routes.system import _anonymize` works and is callable.
2. `from routes.system import _build_diagnostic` works and is callable.
3. All 8 pre-split URL rules are registered under `/api/v1/`.
4. After the split completes, `routes/system/logs.py` stays below its
   pre-split LOC (< 450) — the large post-split file is expected to be
   the support-export module, not the logs module.
"""

from __future__ import annotations

import pathlib

import flask

import routes.system as system_mod

EXPECTED_URL_RULES = {
    ("/api/v1/logs", "GET"),
    ("/api/v1/logs/download", "GET"),
    ("/api/v1/logs/support-export", "GET"),
    ("/api/v1/logs/support-preview", "GET"),
    ("/api/v1/logs/rotation", "GET"),
    ("/api/v1/logs/rotation", "PUT"),
    ("/api/v1/database/vacuum", "POST"),
    ("/api/v1/cache/ffprobe/stats", "GET"),
    ("/api/v1/cache/ffprobe/cleanup", "POST"),
}


def _collect_system_rules(flask_app: flask.Flask) -> set[tuple[str, str]]:
    return {
        (rule.rule, method)
        for rule in flask_app.url_map.iter_rules()
        if rule.endpoint.startswith("system.")
        for method in (rule.methods or set()) - {"HEAD", "OPTIONS"}
    }


def test_anonymize_reexport_stays_callable() -> None:
    """`from routes.system import _anonymize` — used by test_support_export.py."""
    assert callable(system_mod._anonymize)
    # Quick smoke: must redact IPv4 and leave an unrelated word alone
    out = system_mod._anonymize("server at 203.0.113.5 said hello")
    assert "203.0.113.5" not in out
    assert "hello" in out


def test_build_diagnostic_reexport_stays_callable() -> None:
    """`from routes.system import _build_diagnostic` — used by test_support_export.py."""
    assert callable(system_mod._build_diagnostic)


def test_all_expected_routes_are_registered(app_ctx) -> None:
    """The 9 pre-split URL paths must all still be registered after the split."""
    registered = _collect_system_rules(app_ctx)
    missing = EXPECTED_URL_RULES - registered
    # These are the pre-split logs.py URLs. Other system/ routes exist too,
    # so we only check that none of the target ones disappeared.
    assert not missing, f"Routes missing after refactor: {sorted(missing)}"


def test_logs_py_shrinks_after_split() -> None:
    """Pin that `logs.py` is no longer the 791-LOC god-file post-split."""
    backend_root = pathlib.Path(__file__).resolve().parents[1]
    logs_path = backend_root / "routes" / "system" / "logs.py"
    assert logs_path.exists()
    loc = sum(1 for _ in logs_path.open(encoding="utf-8"))
    # Plan targets ~250 LOC; hard ceiling 450 accommodates docstrings.
    assert loc < 450, (
        f"routes/system/logs.py is still {loc} LOC — split is incomplete or "
        f"support/maintenance concerns leaked back in."
    )
