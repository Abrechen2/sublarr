"""System routes package — health, backup, statistics, logs, tasks."""

from flask import Blueprint

bp = Blueprint("system", __name__, url_prefix="/api/v1")

from routes.system import (  # noqa: E402, F401
    backup,
    backup_full,
    budget,
    health,
    health_detailed,
    logs,
    maintenance,
    setup,
    statistics,
    support,
    tasks,
)

# Re-exports for tests:
# tests/test_quality_dashboard.py: from routes.system import get_statistics
# tests/test_support_export.py: from routes.system import _anonymize, _build_diagnostic
from routes.system.statistics import get_statistics  # noqa: E402, F401
from routes.system.support import _anonymize, _build_diagnostic  # noqa: E402, F401
