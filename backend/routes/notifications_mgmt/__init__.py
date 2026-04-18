"""Notification management routes package — /api/v1/notifications/*.

Blueprint for /api/v1/notifications/* endpoints providing full CRUD for
notification templates, quiet hours, notification history with re-send,
event filters, and template variable discovery.

Submodules:
    templates.py    — template CRUD + preview (6 routes)
    variables.py    — template variable discovery (2 routes)
    quiet_hours.py  — quiet hours CRUD (4 routes)
    history.py      — notification history + resend + clear (3 routes)
    filters.py      — event filter config (2 routes)
"""

import logging

from flask import Blueprint

bp = Blueprint("notifications_mgmt", __name__, url_prefix="/api/v1/notifications")
logger = logging.getLogger(__name__)

# Submodule imports — decorators register routes at import time.
from routes.notifications_mgmt import (  # noqa: E402, F401
    filters,
    history,
    quiet_hours,
    templates,
    variables,
)

# Public re-export — tests/test_routes_notifications.py:52 imports this directly.
from routes.notifications_mgmt.templates import _validate_jinja2_syntax  # noqa: E402, F401
