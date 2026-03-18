"""Wanted routes package — list, search, extract, providers."""

from flask import Blueprint

bp = Blueprint("wanted", __name__, url_prefix="/api/v1")

import routes.wanted.extract  # noqa: E402, F401
import routes.wanted.list  # noqa: E402, F401
import routes.wanted.providers  # noqa: E402, F401
import routes.wanted.search  # noqa: E402, F401

# Re-export for wanted_scanner.py: "from routes.wanted import _extract_embedded_sub"
from routes.wanted.extract import _extract_embedded_sub  # noqa: F401
