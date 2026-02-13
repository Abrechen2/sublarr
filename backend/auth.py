"""Optional API key authentication middleware for Flask.

If SUBLARR_API_KEY is set, all /api/ requests must include the key
either as X-Api-Key header or as ?apikey= query parameter.
Health endpoint is exempt.
"""

import functools
import logging

from flask import request, jsonify

from config import get_settings

logger = logging.getLogger(__name__)


def require_api_key(f):
    """Decorator to enforce API key authentication on a route."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        settings = get_settings()
        if not settings.api_key:
            # No API key configured — allow all requests
            return f(*args, **kwargs)

        # Check header first, then query parameter
        provided_key = (
            request.headers.get("X-Api-Key")
            or request.args.get("apikey")
        )

        if not provided_key:
            logger.warning("API request without key from %s", request.remote_addr)
            return jsonify({"error": "API key required"}), 401

        if provided_key != settings.api_key:
            logger.warning("Invalid API key from %s", request.remote_addr)
            return jsonify({"error": "Invalid API key"}), 401

        return f(*args, **kwargs)
    return decorated


def init_auth(app):
    """Initialize authentication for the Flask app.

    Adds a before_request hook that checks API key for all /api/ routes
    except /api/v1/health.
    """
    settings = get_settings()

    if not settings.api_key:
        logger.info("API key authentication disabled (no SUBLARR_API_KEY set)")
        return

    logger.info("API key authentication enabled")

    @app.before_request
    def check_api_key():
        """Check API key for /api/ routes (except health)."""
        path = request.path

        # Skip auth for non-API routes (frontend, static files)
        if not path.startswith("/api/"):
            return None

        # Skip auth for health endpoint
        if path == "/api/v1/health":
            return None

        # Skip auth for webhook endpoints (they use their own auth)
        if "/webhook/" in path:
            return None

        provided_key = (
            request.headers.get("X-Api-Key")
            or request.args.get("apikey")
        )

        if not provided_key:
            return jsonify({"error": "API key required"}), 401

        if provided_key != settings.api_key:
            return jsonify({"error": "Invalid API key"}), 401

        return None
