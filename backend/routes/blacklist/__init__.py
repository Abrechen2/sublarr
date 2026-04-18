"""Blacklist + history routes package.

Split from the flat routes/blacklist.py (B1Bl, 2026-04-18). Both resource
groups share a Blueprint because they were colocated in the original file
and are surfaced under the same UI area in the frontend.
"""

import logging

from flask import Blueprint

bp = Blueprint("blacklist", __name__, url_prefix="/api/v1")
logger = logging.getLogger(__name__)

# Register route submodules — must come after bp is defined.
from routes.blacklist import (  # noqa: E402, F401
    core,
    history,
)
