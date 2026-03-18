"""System routes package — health, backup, statistics, logs, tasks."""

from flask import Blueprint

bp = Blueprint("system", __name__, url_prefix="/api/v1")

from routes.system import backup, health, logs, statistics, tasks  # noqa: E402, F401
from routes.system.logs import _anonymize, _build_diagnostic  # noqa: F401

# Re-exports for tests:
# tests/test_quality_dashboard.py: from routes.system import get_statistics
# tests/test_support_export.py: from routes.system import _anonymize, _build_diagnostic
from routes.system.statistics import get_statistics  # noqa: F401
