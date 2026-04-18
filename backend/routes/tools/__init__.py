"""Subtitle processing tools routes package."""

from flask import Blueprint

bp = Blueprint("tools", __name__, url_prefix="/api/v1/tools")

from routes.tools import (  # noqa: E402, F401
    analysis,
    common_fixes,
    content,
    convert,
    diff,
    editing,
    subtitle_health,
    sync_tools,
    timing,
    validation,
)
