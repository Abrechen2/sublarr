"""UI session authentication for Sublarr web interface.

Provides optional single-password protection for the web UI.
API routes accept either a valid UI session OR an X-Api-Key header.
Auth endpoints and /api/v1/health are always exempt.
"""

import hmac
import logging
import os
import secrets

import bcrypt
from flask import jsonify, request, session

logger = logging.getLogger(__name__)


def _get_config_entry(key: str):
    from db.config import get_config_entry

    return get_config_entry(key)


def _save_config_entry(key: str, value: str):
    from db.config import save_config_entry

    save_config_entry(key, value)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    if not password:
        return False
    return bcrypt.checkpw(password.encode(), hashed.encode())


def is_ui_auth_configured() -> bool:
    return _get_config_entry("ui_password_hash") is not None


def is_ui_auth_enabled() -> bool:
    return _get_config_entry("ui_auth_enabled") == "true"


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
        if session.get("ui_authenticated"):
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
