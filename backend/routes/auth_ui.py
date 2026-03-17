"""UI authentication endpoints.

GET  /api/v1/auth/status          — auth state (no session required)
POST /api/v1/auth/setup           — first-run: set password or disable
POST /api/v1/auth/login           — verify password, create session
POST /api/v1/auth/logout          — clear session
POST /api/v1/auth/change-password — update password (active session required)
POST /api/v1/auth/toggle          — enable/disable auth (session or API key required)
"""

import logging

from flask import Blueprint, jsonify, request, session

import ui_auth
from extensions import limiter

logger = logging.getLogger(__name__)

auth_ui_bp = Blueprint("auth_ui", __name__, url_prefix="/api/v1/auth")
_MIN_PASSWORD_LENGTH = 12


def _is_session_authenticated() -> bool:
    return bool(session.get("ui_authenticated"))


@auth_ui_bp.get("/status")
def get_status():
    return jsonify(
        {
            "configured": ui_auth.is_ui_auth_configured(),
            "enabled": ui_auth.is_ui_auth_enabled(),
            "authenticated": _is_session_authenticated(),
        }
    )


@auth_ui_bp.get("/bootstrap")
def bootstrap():
    """Return the API key for the local frontend.

    Only accessible from localhost or when a valid UI session exists.
    This allows the SPA to auto-configure its API key without requiring
    manual copy-paste, similar to how Sonarr/Radarr work.
    """
    from config import get_settings

    remote = request.remote_addr or ""
    is_local = remote in ("127.0.0.1", "::1", "localhost")
    is_session_auth = _is_session_authenticated()

    if not is_local and not is_session_auth:
        return jsonify({"error": "Forbidden"}), 403

    settings = get_settings()
    return jsonify({"api_key": settings.api_key})


@auth_ui_bp.post("/setup")
def setup():
    if ui_auth.is_ui_auth_configured():
        return jsonify({"error": "Already configured. Use /toggle or /change-password."}), 409

    body = request.get_json(silent=True) or {}
    action = body.get("action")

    if action == "disable":
        ui_auth._save_config_entry("ui_auth_enabled", "false")
        ui_auth._save_config_entry("ui_password_hash", "disabled")
        logger.info("UI auth disabled during first-run setup")
        return jsonify({"status": "disabled"})

    if action == "set_password":
        password = body.get("password", "")
        if len(password) < _MIN_PASSWORD_LENGTH:
            return jsonify(
                {"error": f"Password must be at least {_MIN_PASSWORD_LENGTH} characters"}
            ), 400
        ui_auth._save_config_entry("ui_password_hash", ui_auth.hash_password(password))
        ui_auth._save_config_entry("ui_auth_enabled", "true")
        session["ui_authenticated"] = True
        logger.info("UI auth password set during first-run setup")
        return jsonify({"status": "enabled"})

    return jsonify({"error": "Invalid action. Use 'set_password' or 'disable'."}), 400


@auth_ui_bp.post("/login")
@limiter.limit("10/minute; 30/hour")
def login():
    if not ui_auth.is_ui_auth_enabled():
        session["ui_authenticated"] = True
        return jsonify({"status": "ok"})

    body = request.get_json(silent=True) or {}
    password = body.get("password", "")
    pw_hash = ui_auth._get_config_entry("ui_password_hash") or ""

    if pw_hash == "disabled" or not ui_auth.verify_password(password, pw_hash):
        logger.warning("Failed UI login attempt from %s", request.remote_addr)
        return jsonify({"error": "Invalid password"}), 401

    session["ui_authenticated"] = True
    session.permanent = True
    logger.info("UI login from %s", request.remote_addr)
    return jsonify({"status": "ok"})


@auth_ui_bp.post("/logout")
def logout():
    session.pop("ui_authenticated", None)
    return jsonify({"status": "ok"})


@auth_ui_bp.post("/change-password")
def change_password():
    if not _is_session_authenticated():
        return jsonify({"error": "Authentication required"}), 401

    body = request.get_json(silent=True) or {}
    current = body.get("current_password", "")
    new_pw = body.get("new_password", "")

    pw_hash = ui_auth._get_config_entry("ui_password_hash") or ""
    if not ui_auth.verify_password(current, pw_hash):
        return jsonify({"error": "Current password is incorrect"}), 401

    if len(new_pw) < _MIN_PASSWORD_LENGTH:
        return jsonify(
            {"error": f"Password must be at least {_MIN_PASSWORD_LENGTH} characters"}
        ), 400

    ui_auth._save_config_entry("ui_password_hash", ui_auth.hash_password(new_pw))
    logger.info("UI password changed")
    return jsonify({"status": "ok"})


@auth_ui_bp.post("/toggle")
def toggle():
    if not _is_session_authenticated() and not ui_auth._has_valid_api_key():
        return jsonify({"error": "Authentication required"}), 401

    body = request.get_json(silent=True) or {}
    enabled = body.get("enabled")
    if not isinstance(enabled, bool):
        return jsonify({"error": "'enabled' must be a boolean"}), 400

    ui_auth._save_config_entry("ui_auth_enabled", "true" if enabled else "false")
    logger.info("UI auth %s", "enabled" if enabled else "disabled")
    return jsonify({"status": "enabled" if enabled else "disabled"})
