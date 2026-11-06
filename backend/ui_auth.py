"""UI session authentication for Sublarr web interface.

Provides optional single-password protection for the web UI.
API routes accept either a valid UI session OR an X-Api-Key header.
Auth endpoints and /api/v1/health are always exempt.
"""

import hmac
import ipaddress
import json
import logging
import os
import secrets
import time

import bcrypt
from flask import jsonify, request, session

logger = logging.getLogger(__name__)

# The config keys this module owns. They are set through the auth endpoints,
# which know the rules — changing the password requires the current one, and
# enabling auth requires a password to already exist. Declared here so the
# generic config writer can refuse them instead of offering a second, ruleless
# way to set a password hash.
AUTH_OWNED_CONFIG_KEYS = frozenset(
    {
        "ui_auth_enabled",
        "ui_password_hash",
        "ui_session_secret",
        "ui_session_generation",
        "ui_revoked_sessions",
    }
)

_AUTH_FLAG_TTL = 30.0
_auth_enabled_cache: tuple[float, bool] | None = None

# Every session carries the generation it was issued under. Changing the
# password or switching UI auth on or off starts a new generation, which ends
# every older session at once (#73).
_SESSION_GENERATION_KEY = "ui_session_generation"
# Sessions ended by logout, as {sid: expiry epoch}. A Flask session is a signed
# cookie, so without this list a copied cookie outlived its logout (#73).
_REVOKED_SESSIONS_KEY = "ui_revoked_sessions"
_MAX_REVOKED_SESSIONS = 500
# Generation and revocations are read on every API request; same TTL cache as
# the auth flag, dropped on every write in this process.
_session_state_cache: tuple[float, str, dict] | None = None

# A forwarding header means the request came through a reverse proxy, whose
# own private address says nothing about where the client is.
_FORWARDING_HEADERS = ("X-Forwarded-For", "Forwarded", "X-Real-IP", "CF-Connecting-IP")
# Tailscale and other overlay VPNs hand out addresses from the shared range.
_SHARED_RANGE = ipaddress.ip_network("100.64.0.0/10")

# One-time token for the first setup from outside the local network (#72).
# Kept in memory and logged at start; the app runs a single worker.
_setup_token: str | None = None


def _get_config_entry(key: str):
    from db.config import get_config_entry

    return get_config_entry(key)


def _save_config_entry(key: str, value: str):
    from db.config import save_config_entry

    save_config_entry(key, value)
    if key == "ui_auth_enabled":
        global _auth_enabled_cache
        _auth_enabled_cache = None
    if key in (_SESSION_GENERATION_KEY, _REVOKED_SESSIONS_KEY):
        global _session_state_cache
        _session_state_cache = None


def _invalidate_cache() -> None:
    global _auth_enabled_cache, _session_state_cache
    _auth_enabled_cache = None
    _session_state_cache = None


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    if not password:
        return False
    return bcrypt.checkpw(password.encode(), hashed.encode())


def is_ui_auth_configured() -> bool:
    return _get_config_entry("ui_password_hash") is not None


def is_ui_auth_enabled() -> bool:
    """Called by check_ui_session on EVERY /api request — cache the flag so
    it costs one ORM query per 30s instead of one per request.

    Reads the module global exactly once into a local variable before
    inspecting it. ``_save_config_entry`` can reassign the global to
    ``None`` from another thread (Flask's default threaded mode) at any
    point; re-reading the global between the ``is not None`` check and the
    subsequent subscript access would risk a ``TypeError`` if that
    reassignment lands in between.
    """
    global _auth_enabled_cache
    cache = _auth_enabled_cache
    now = time.monotonic()
    if cache is not None and (now - cache[0]) < _AUTH_FLAG_TTL:
        return cache[1]
    enabled = _get_config_entry("ui_auth_enabled") == "true"
    _auth_enabled_cache = (now, enabled)
    return enabled


def _get_or_create_secret_key() -> str:
    existing = _get_config_entry("ui_session_secret")
    if existing:
        return existing
    new_secret = secrets.token_hex(32)
    _save_config_entry("ui_session_secret", new_secret)
    return new_secret


def _has_valid_api_key() -> bool:
    from config import get_settings

    settings = get_settings()
    if not settings.api_key:
        return False
    provided = request.headers.get("X-Api-Key") or request.args.get("apikey")
    if not provided:
        return False
    return hmac.compare_digest(provided, settings.api_key)


def request_is_local_network() -> bool:
    """Whether the request comes straight from a loopback or private address.

    Signing in without a password and the first setup are limited to these
    (like Sonarr's "disabled for local addresses"). A request through a reverse
    proxy never counts: the proxy may forward the internet.
    """
    if any(request.headers.get(h) for h in _FORWARDING_HEADERS):
        return False
    try:
        addr = ipaddress.ip_address(request.remote_addr or "")
    except ValueError:
        return False
    if addr.version == 6 and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    return addr.is_loopback or addr.is_private or addr in _SHARED_RANGE


def _session_state() -> tuple[str, dict]:
    global _session_state_cache
    cache = _session_state_cache
    now = time.monotonic()
    if cache is not None and (now - cache[0]) < _AUTH_FLAG_TTL:
        return cache[1], cache[2]
    generation = _get_config_entry(_SESSION_GENERATION_KEY) or "0"
    try:
        revoked = json.loads(_get_config_entry(_REVOKED_SESSIONS_KEY) or "{}")
    except ValueError:
        logger.warning("Unreadable list of ended UI sessions; starting a new one")
        revoked = {}
    _session_state_cache = (now, generation, revoked)
    return generation, revoked


def _revoked_sessions() -> dict:
    return _session_state()[1]


def _revoke(sid: str, ttl_seconds: float) -> None:
    now = time.time()
    live = {k: v for k, v in _revoked_sessions().items() if v > now}
    live[sid] = now + ttl_seconds
    if len(live) > _MAX_REVOKED_SESSIONS:
        newest = sorted(live.items(), key=lambda kv: kv[1])[-_MAX_REVOKED_SESSIONS:]
        live = dict(newest)
    _save_config_entry(_REVOKED_SESSIONS_KEY, json.dumps(live))


def start_session(*, free: bool = False) -> None:
    """Sign this browser in. ``free`` marks a session issued without a password."""
    session.clear()
    session["ui_authenticated"] = True
    session["ui_generation"] = _session_state()[0]
    session["ui_sid"] = secrets.token_urlsafe(16)
    if free:
        session["ui_free"] = True
    session.permanent = True


def end_session(lifetime_seconds: float) -> None:
    """Sign this browser out and refuse its cookie for the rest of its lifetime."""
    sid = session.get("ui_sid")
    session.clear()
    if sid:
        _revoke(sid, lifetime_seconds)


def end_all_sessions() -> None:
    _save_config_entry(_SESSION_GENERATION_KEY, secrets.token_hex(8))


def has_valid_session() -> bool:
    """Whether the request carries a session that may stand in for the API key.

    A session issued without a password (UI auth disabled) holds only while
    UI auth stays disabled and only for requests from the local network.
    """
    if not session.get("ui_authenticated"):
        return False
    generation, revoked = _session_state()
    if session.get("ui_generation") != generation or session.get("ui_sid") in revoked:
        return False
    if session.get("ui_free"):
        return not is_ui_auth_enabled() and request_is_local_network()
    return True


def setup_token() -> str:
    global _setup_token
    if _setup_token is None:
        _setup_token = secrets.token_urlsafe(18)
    return _setup_token


def setup_allowed(provided_token: str) -> bool:
    """The first setup is open to the local network, the API key or the logged token."""
    if request_is_local_network() or _has_valid_api_key():
        return True
    return bool(provided_token) and hmac.compare_digest(str(provided_token), setup_token())


_EXEMPT_PATHS = {"/api/v1/health"}
_EXEMPT_PREFIXES = ("/api/v1/auth/", "/socket.io/")


def init_ui_auth(app):
    try:
        app.config["SECRET_KEY"] = _get_or_create_secret_key()
    except Exception:
        app.config.setdefault("SECRET_KEY", secrets.token_hex(32))

    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    # Secure flag: opt-in for HTTPS deployments (incl. TLS-terminating reverse
    # proxies). Defaults to False so plain-HTTP LAN deployments keep working,
    # but operators serving over TLS should set SUBLARR_SESSION_SECURE=1 so the
    # browser never transmits the session cookie over an insecure connection.
    _secure = os.environ.get("SUBLARR_SESSION_SECURE", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    app.config["SESSION_COOKIE_SECURE"] = _secure

    # Enforce session_timeout_minutes from config; default to 8 hours instead of Flask's 31-day default
    from datetime import timedelta

    from config import get_settings

    try:
        settings = get_settings()
        timeout = getattr(settings, "session_timeout_minutes", 0)
        if timeout and timeout > 0:
            app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=timeout)
        else:
            app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=8)
    except Exception:
        # If settings fail to load, use secure default
        app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=8)

    @app.before_request
    def check_ui_session():
        path = request.path
        if path in _EXEMPT_PATHS:
            return None
        for prefix in _EXEMPT_PREFIXES:
            if path.startswith(prefix):
                return None
        if not path.startswith("/api/"):
            return None
        if not is_ui_auth_enabled():
            return None
        if has_valid_session():
            return None
        if _has_valid_api_key():
            return None
        from proxy_auth import request_has_valid_proxy_auth

        if request_has_valid_proxy_auth():
            return None
        # Browser-native <video> streaming authenticates via a path-scoped
        # short-lived token instead of the session cookie / API key (see
        # media_token); honour it here too so playback works under UI auth.
        from media_token import stream_request_has_valid_token

        if stream_request_has_valid_token():
            return None
        return jsonify({"error": "Authentication required"}), 401

    logger.info("UI authentication hook registered")
    try:
        unconfigured = not is_ui_auth_configured()
    except Exception:
        unconfigured = False
    if unconfigured:
        logger.warning(
            "UI auth is not set up yet. From outside the local network, the first "
            "setup asks for this one-time token: %s",
            setup_token(),
        )
