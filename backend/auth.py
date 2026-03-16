"""Optional API key authentication middleware for Flask.

If SUBLARR_API_KEY is set, all /api/ requests must include the key
either as X-Api-Key header or as ?apikey= query parameter.
Health endpoint is exempt.
"""

import functools
import hmac
import logging
import threading
import time
from collections import defaultdict

from flask import jsonify, request

from config import get_settings

logger = logging.getLogger(__name__)

# Per-IP rate limiting for failed API key attempts.
# Tracks timestamps of failures; entries older than _WINDOW are discarded.
_failed_lock = threading.Lock()
_failed_attempts: dict[str, list[float]] = defaultdict(list)
_FAIL_LIMIT = 20  # max failed attempts per window
_FAIL_WINDOW = 60  # seconds


def _is_rate_limited(ip: str) -> bool:
    """Return True if ip has exceeded the failed-auth rate limit."""
    now = time.monotonic()
    with _failed_lock:
        cutoff = now - _FAIL_WINDOW
        _failed_attempts[ip] = [t for t in _failed_attempts[ip] if t > cutoff]
        return len(_failed_attempts[ip]) >= _FAIL_LIMIT


def _record_failure(ip: str) -> None:
    """Record a failed auth attempt for ip."""
    with _failed_lock:
        _failed_attempts[ip].append(time.monotonic())


def require_api_key(f):
    """Decorator to enforce API key authentication on a route."""

    @functools.wraps(f)
    def decorated(*args, **kwargs):
        settings = get_settings()
        if not settings.api_key:
            # No API key configured — allow all requests
            return f(*args, **kwargs)

        # Check header first, then query parameter
        provided_key = request.headers.get("X-Api-Key") or request.args.get("apikey")

        if not provided_key:
            logger.warning("API request without key from %s", request.remote_addr)
            return jsonify({"error": "API key required"}), 401

        if not hmac.compare_digest(provided_key, settings.api_key):
            logger.warning("Invalid API key from %s", request.remote_addr)
            return jsonify({"error": "Invalid API key"}), 401

        return f(*args, **kwargs)

    return decorated


def init_auth(app):
    """Initialize authentication for the Flask app.

    Adds a before_request hook that checks API key for all /api/ routes
    except /api/v1/health. The key is read on each request so DB overrides
    (config changes via UI) take effect immediately without a restart.
    """
    logger.info("API key authentication hook registered (active when SUBLARR_API_KEY is set)")

    @app.before_request
    def check_api_key():
        """Check API key for /api/ routes (except health)."""
        # Read settings on every request to pick up runtime config changes
        current_settings = get_settings()
        if not current_settings.api_key:
            # No API key configured — allow all requests
            return None

        path = request.path

        # Skip auth for non-API routes (frontend, static files)
        if not path.startswith("/api/"):
            return None

        # Skip auth for health endpoint
        if path == "/api/v1/health":
            return None

        # Skip auth for webhook endpoints — each handler performs its own
        # HMAC-based auth (see routes/webhooks.py). IMPORTANT: any new webhook
        # route added under /api/v1/webhook/ MUST implement auth manually;
        # there is no fallback enforcement here.
        if path.startswith("/api/v1/webhook/"):
            return None

        # Skip auth for UI auth endpoints (login, setup, status, logout)
        # These handle their own authentication logic
        if path.startswith("/api/v1/auth/"):
            return None

        ip = request.remote_addr or "unknown"

        # Reject IPs that have exceeded the failed-auth rate limit
        if _is_rate_limited(ip):
            logger.warning("Rate limit exceeded for API key auth from %s", ip)
            resp = jsonify({"error": "Too many failed attempts. Try again later."})
            resp.headers["Retry-After"] = str(_FAIL_WINDOW)
            return resp, 429

        provided_key = request.headers.get("X-Api-Key") or request.args.get("apikey")

        if not provided_key:
            _record_failure(ip)
            return jsonify({"error": "API key required"}), 401

        if not hmac.compare_digest(provided_key, current_settings.api_key):
            _record_failure(ip)
            logger.warning("Invalid API key from %s", ip)
            return jsonify({"error": "Invalid API key"}), 401

        return None
