"""Hooks Blueprint package -- CRUD for shell hooks, webhooks, hook logs, event catalog, scoring weights, and provider modifiers.

Provides the API surface for the Settings "Events & Hooks" and "Scoring" tabs.
All endpoints are under /api/v1/.
"""

import logging

from flask import Blueprint

bp = Blueprint("hooks", __name__, url_prefix="/api/v1")
logger = logging.getLogger(__name__)

# Import submodules AFTER bp is defined — they register routes on bp
from routes.hooks import crud, events, logs, scoring, webhooks  # noqa: E402, F401
