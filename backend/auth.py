"""Optional API key authentication middleware for Flask.

If SUBLARR_API_KEY is set, all /api/ requests must include the key
either as X-Api-Key header or as ?apikey= query parameter.
Health endpoint is exempt.
"""

import functools
import hmac
import ipaddress as _ipaddress
import logging
import re
import threading
import time
from collections import defaultdict

from flask import jsonify, request, session

from config import get_settings

logger = logging.getLogger(__name__)

# Per-IP rate limiting for failed API key attempts.
# Tracks timestamps of failures; entries older than _WINDOW are discarded.
_failed_lock = threading.Lock()
_failed_attempts: dict[str, list[float]] = defaultdict(list)
# lockout_duration_minutes from settings applies to UI session lockout (future);
# this window is for API key brute-force protection.
_FAIL_WINDOW = 60  # seconds — fixed sliding window

# Webhook paths already warned about in this process. The warning below records
# that a route is exempt from API-key auth and owes its own verification — a
# property of the route, not of the request — so it needs saying once, not on
# every event. Sonarr and Radarr cannot sign their webhooks at all, so firing
# per request produced hundreds of identical lines an operator could do nothing
# about, drowning the log the same warning was meant to make readable.
_webhook_warn_lock = threading.Lock()
_webhook_warned_paths: set[str] = set()


def _is_rate_limited(ip: str) -> bool:
    """Return True if ip has exceeded the failed-auth rate limit."""
    settings = get_settings()
    fail_limit = getattr(settings, "max_login_attempts", 20)
    now = time.monotonic()
    with _failed_lock:
        cutoff = now - _FAIL_WINDOW
        _failed_attempts[ip] = [t for t in _failed_attempts[ip] if t > cutoff]
        return len(_failed_attempts[ip]) >= fail_limit


def _record_failure(ip: str) -> None:
    """Record a failed auth attempt for ip."""
    with _failed_lock:
        _failed_attempts[ip].append(time.monotonic())


def require_api_key(f):
    """Decorator to enforce API key authentication on a route.

    Honours the same contract as the global check_api_key hook: a valid
    UI session or trusted-proxy SSO request passes without an X-Api-Key.
    Without this, session-authenticated browsers (which may hold no key in
    localStorage) got 401 on decorated routes — e.g. /media/stream-token,
    breaking video playback and re-triggering the /login redirect loop.
    """

    @functools.wraps(f)
    def decorated(*args, **kwargs):
        settings = get_settings()
        if not settings.api_key:
            # No API key configured — allow all requests
            return f(*args, **kwargs)

        if session.get("ui_authenticated"):
            return f(*args, **kwargs)

        from proxy_auth import request_has_valid_proxy_auth

        if request_has_valid_proxy_auth():
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


def _check_ip_allowlist() -> "tuple[dict, int] | None":
    """Returns 403 response tuple if request IP is not in allowed_ip_ranges, else None."""
    try:
        allowed = getattr(get_settings(), "allowed_ip_ranges", "").strip()
    except Exception:
        return None  # settings not available yet
    if not allowed:
        return None  # empty = allow all
    try:
        networks = [
            _ipaddress.ip_network(r.strip(), strict=False) for r in allowed.split(",") if r.strip()
        ]
    except ValueError:
        logger.warning("allowed_ip_ranges contains invalid CIDR — skipping IP check")
        return None
    try:
        client_ip = _ipaddress.ip_address(request.remote_addr)
    except ValueError:
        return None  # can't parse IP, allow through
    if not any(client_ip in net for net in networks):
        return jsonify({"error": "Forbidden"}), 403
    return None


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
        # Enforce IP allowlist first — before any other logic
        ip_block = _check_ip_allowlist()
        if ip_block:
            return ip_block

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

        # Skip auth for OpenAPI discovery — the spec + Swagger UI need to be
        # browsable without an API key, otherwise nobody can find out *that*
        # an API key is required. The "Try it out" button in Swagger UI then
        # injects the key per-request via the standard `Authorize` flow.
        if path == "/api/v1/openapi.json" or path.startswith("/api/docs"):
            return None

        # Skip auth for extracted waveform audio. WaveSurfer.js issues its
        # own internal fetch that bypasses our axios interceptor, so we
        # can't inject the X-Api-Key header on the audio URL. The route
        # itself constrains lookups to a `.opus` temp file under
        # `tempfile.gettempdir()` (no path traversal, no other suffixes),
        # and tmp filenames carry enough entropy that they aren't
        # enumerable. Plan B8 Task 12.
        if path.startswith("/api/v1/tools/waveform-audio/"):
            return None

        # Skip auth for /media/stream requests carrying a valid short-lived
        # stream token. The <video> element cannot send an X-Api-Key header on
        # its own range requests; instead the client mints a path-scoped HMAC
        # token via the (authenticated) /media/stream-token endpoint and passes
        # that in the URL — so the raw API key never appears in access logs.
        from media_token import stream_request_has_valid_token

        if stream_request_has_valid_token():
            return None

        # Skip auth for webhook endpoints — each handler performs its own
        # HMAC-based auth (see routes/webhooks.py). IMPORTANT: any new webhook
        # route added under /api/v1/webhook/ MUST implement auth manually;
        # there is no fallback enforcement here.
        if path.startswith("/api/v1/webhook/"):
            if not request.headers.get("X-Signature") and not request.headers.get(
                "X-Bazarr-Signature"
            ):
                with _webhook_warn_lock:
                    first_time = path not in _webhook_warned_paths
                    _webhook_warned_paths.add(path)
                if first_time:
                    logger.warning(
                        "Webhook request to %s from %s has no X-Signature header — "
                        "ensure the handler implements HMAC verification. Logged once "
                        "per path per start; further unsigned requests stay silent.",
                        path,
                        request.remote_addr,
                    )
            return None

        # Skip auth for UI auth endpoints (login, setup, status, logout)
        # These handle their own authentication logic
        if path.startswith("/api/v1/auth/"):
            return None

        # Skip auth for standalone poster endpoints — posters are public metadata
        # (is_safe_path() in the route prevents directory traversal)
        if re.match(r"^/api/v1/standalone/(series|movies)/\d+/poster$", path):
            return None

        # An authenticated UI session satisfies the API gate. ui_auth.py's
        # contract is "API routes accept either a valid UI session OR an
        # X-Api-Key header", but this hook used to enforce the key
        # unconditionally: a browser that had just logged in (session cookie
        # set, no key in localStorage yet) got 401 on every request, and the
        # frontend's 401 interceptor bounced it back to /login in an endless
        # loop. A session is only free when UI auth is disabled — and in that
        # configuration /auth/bootstrap already hands out the key to any LAN
        # client by design, so this adds no exposure beyond that.
        if session.get("ui_authenticated"):
            return None

        # Same contract for reverse-proxy header auth (Authelia/authentik SSO):
        # a request vouched for by the trusted proxy must not be rejected for
        # lacking an X-Api-Key. Fails closed on any misconfiguration.
        from proxy_auth import request_has_valid_proxy_auth

        if request_has_valid_proxy_auth():
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
