"""API error handling utilities.

Provides @handle_api_error decorator to eliminate boilerplate
try/except blocks in route handlers.
"""

import functools
import logging

from flask import g, has_request_context, jsonify

logger = logging.getLogger(__name__)


PUBLIC_ERROR_TEXT_LIMIT = 300


def public_error_text(exc: BaseException, limit: int = PUBLIC_ERROR_TEXT_LIMIT) -> str:
    """Exception text that a diagnostic response may show: connection tests.

    "Test connection" and health endpoints exist to tell the admin *why* a
    Sonarr, Jellyfin or provider call failed, so they keep the reason. What
    they must not carry is a credential: HTTP client errors quote the request
    URL, and Jellyfin, Plex and several providers put the key in the query
    string. The text is passed through the same secret redaction as the logs,
    collapsed to one line and bounded in length.
    """
    from secret_redaction import redact

    text = " ".join(str(exc).split())
    return redact(text)[:limit]


def internal_error_response(public_msg: str, exc: BaseException | None = None, status: int = 500):
    """Return a JSON error whose text is ``public_msg`` only — never ``str(exc)``.

    Exception text is for the log, not for the client: it carries file
    system paths, SQL, library internals and, for HTTP client errors, URLs
    whose query strings may hold API keys. The response carries the request
    id instead, so a user can quote it and the operator can find the full
    traceback in the log.

    Args:
        public_msg: The message shown to the user, e.g. "Preview failed".
        exc: When given, it is logged here at ERROR with its traceback. Pass
            None when the caller has already logged it.
        status: HTTP status code (default 500).
    """
    request_id = getattr(g, "request_id", None) if has_request_context() else None
    if exc is not None:
        logger.error("%s (request_id=%s)", public_msg, request_id, exc_info=exc)
    body: dict = {"error": public_msg}
    if request_id:
        body["request_id"] = request_id
    return jsonify(body), status


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
