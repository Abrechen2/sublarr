"""Subtitle processing tools routes package."""

from flask import Blueprint

bp = Blueprint("tools", __name__, url_prefix="/api/v1/tools")

from routes.tools import (  # noqa: E402, F401
    analysis,
    content,
    convert,
    diff,
    editing,
    sync_tools,
    validation,
)
