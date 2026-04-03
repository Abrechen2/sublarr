"""API error handling utilities.

Provides @handle_api_error decorator to eliminate boilerplate
try/except blocks in route handlers.
"""

import functools
import logging

from flask import jsonify

logger = logging.getLogger(__name__)


def handle_api_error(default_msg: str, status_code: int = 500):
    """Decorator that catches unhandled exceptions in route handlers.

    Logs the exception at ERROR level and returns a JSON error response.
    The decorated function's name and docstring are preserved via functools.wraps.

    Args:
        default_msg: Human-readable message returned to the caller in {"error": "..."}.
        status_code: HTTP status code for error responses (default 500).
    """

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except Exception as exc:
                logger.error("%s: %s", default_msg, exc, exc_info=True)
                return jsonify({"error": default_msg}), status_code

        return wrapper

    return decorator
