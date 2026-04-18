"""API Key Management routes — /api/v1/api-keys/*.

Centralised API key registry with test, rotate, export/import, and Bazarr
migration endpoints. See `docs/superpowers/plans/2026-04-18-b1-routes-api-keys-split.md`.

Package layout:
    helpers.py  — API_KEY_REGISTRY + _mask_value + _get_service_info
    testing.py  — _test_* connectivity helpers + _TEST_DISPATCH
    routes.py   — list/get/update/test services endpoints + _invalidate_for_service
    io.py       — export/import/bazarr endpoints + ZIP/CSV helpers

Public re-exports below are kept because tests and other callers access
these names at the package scope (`routes.api_keys.<name>`).
"""

from flask import Blueprint

bp = Blueprint("api_keys", __name__, url_prefix="/api/v1/api-keys")

# Submodule imports run at the bottom so `bp` is already defined when the
# @bp.route decorators execute.
from routes.api_keys import io, routes  # noqa: E402, F401

# Public re-exports (test-suite contract — see plan §Patch-path constraint).
from routes.api_keys.helpers import API_KEY_REGISTRY, _mask_value  # noqa: E402, F401
from routes.api_keys.routes import _invalidate_for_service  # noqa: E402, F401
from routes.api_keys.testing import (  # noqa: E402, F401
    _TEST_DISPATCH,
    _test_apprise,
    _test_deepl,
    _test_provider,
    _test_radarr,
    _test_sonarr,
)
