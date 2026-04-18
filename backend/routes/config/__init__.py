"""Config routes package — core config CRUD, onboarding, export/import.

Split from the flat routes/config.py (B1Cf, 2026-04-18). The Blueprint `bp`
lives here; submodules attach their @bp.route handlers and are imported at
the bottom so they register on startup.
"""

import logging

from flask import Blueprint

bp = Blueprint("config", __name__, url_prefix="/api/v1")
logger = logging.getLogger(__name__)

# Register route submodules — must come after bp is defined.
from routes.config import (  # noqa: E402, F401
    core,
    io,
    onboarding,
)
