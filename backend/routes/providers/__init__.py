"""Provider routes package — management, search, stats/health, rerank.

Split from the flat routes/providers.py (B1Pv, 2026-04-18). The Blueprint `bp`
lives here; submodules attach their @bp.route handlers and are imported at the
bottom so they register on startup.
"""

import logging

from flask import Blueprint

bp = Blueprint("providers", __name__, url_prefix="/api/v1")
logger = logging.getLogger(__name__)

# Register route submodules — must come after bp is defined.
from routes.providers import (  # noqa: E402, F401
    management,
    rerank,
    search,
)
