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
    """Return current authentication configuration and session status.
    ---
    get:
      tags:
        - Auth
      summary: Get auth status
      description: Returns whether UI auth is configured, enabled, and whether the current session is authenticated.
      security: []
      responses:
        200:
          description: Auth status
          content:
            application/json:
              schema:
                type: object
                properties:
                  configured:
                    type: boolean
                  enabled:
                    type: boolean
                  authenticated:
                    type: boolean
    """
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

    settings = get_settings()
    remote = request.remote_addr or ""
    is_local = remote in ("127.0.0.1", "::1", "localhost")
    is_session_auth = _is_session_authenticated()

    # If ANY authentication is configured — either an API key (gates
    # /api/v1/* via init_auth) or UI auth (gates /api/v1/* via
    # init_ui_auth) — then the api_key is a credential that must not be
    # handed out to non-local unauthenticated callers. Pre-2026-04-30
    # this gate only checked ui_auth_enabled, so a deployment with
    # api_key set but UI auth off would happily return the key to any
    # caller on the LAN. The "API is open anyway" premise was wrong:
    # when api_key is set, the API is NOT open — bootstrap was the leak.
    auth_required = bool(settings.api_key) or ui_auth.is_ui_auth_enabled()
    if auth_required and not is_local and not is_session_auth:
        return jsonify({"error": "Forbidden"}), 403

    return jsonify({"api_key": settings.api_key})


@auth_ui_bp.post("/setup")
@limiter.limit("5 per minute")
def setup():
    """Configure UI authentication for the first time.
    ---
    post:
      tags:
        - Auth
      summary: Initial auth setup
      description: Sets or disables UI password authentication. Only callable when auth is not yet configured. Rate limited to 5 per minute.
      security: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [action]
              properties:
                action:
                  type: string
                  enum: [set_password, disable]
                password:
                  type: string
                  description: Required when action is set_password. Minimum 12 characters.
      responses:
        200:
          description: Auth configured
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                    enum: [enabled, disabled]
        400:
          description: Password too short or missing
        409:
          description: Auth already configured
    """
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
    """Authenticate with UI password and create a session.
    ---
    post:
      tags:
        - Auth
      summary: Login
      description: Validates the UI password and creates an authenticated session cookie. Rate limited to 10 per minute and 30 per hour.
      security: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [password]
              properties:
                password:
                  type: string
      responses:
        200:
          description: Login successful
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                    example: ok
        401:
          description: Wrong password
    """
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
    """Clear the current session cookie.
    ---
    post:
      tags:
        - Auth
      summary: Logout
      description: Clears the authenticated session. No auth required — always succeeds.
      security: []
      responses:
        200:
          description: Logged out
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                    example: ok
    """
    # session.clear() rather than pop("ui_authenticated") so any future
    # session keys (e.g. CSRF token, last-seen flags) get wiped on
    # logout too — defense in depth.
    session.clear()
    return jsonify({"status": "ok"})


@auth_ui_bp.post("/change-password")
@limiter.limit("5 per minute; 20 per hour")
def change_password():
    """Change the UI authentication password.
    ---
    post:
      tags:
        - Auth
      summary: Change password
      description: Verifies the current password and sets a new one. Requires an active session. Rate limited to 5 per minute and 20 per hour.
      security:
        - sessionAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [current_password, new_password]
              properties:
                current_password:
                  type: string
                new_password:
                  type: string
                  description: Minimum 12 characters.
      responses:
        200:
          description: Password changed
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                    example: ok
        400:
          description: New password too short or missing fields
        401:
          description: Not authenticated or current password incorrect
    """
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
    """Enable or disable UI authentication.
    ---
    post:
      tags:
        - Auth
      summary: Toggle auth
      description: Enables or disables UI password authentication. Requires an active session or a valid API key.
      security:
        - sessionAuth: []
        - apiKeyAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [enabled]
              properties:
                enabled:
                  type: boolean
      responses:
        200:
          description: Auth toggled
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                    enum: [enabled, disabled]
        400:
          description: enabled field missing or not boolean
        401:
          description: Not authenticated
    """
    if not _is_session_authenticated() and not ui_auth._has_valid_api_key():
        return jsonify({"error": "Authentication required"}), 401

    body = request.get_json(silent=True) or {}
    enabled = body.get("enabled")
    if not isinstance(enabled, bool):
        return jsonify({"error": "'enabled' must be a boolean"}), 400

    ui_auth._save_config_entry("ui_auth_enabled", "true" if enabled else "false")
    logger.info("UI auth %s", "enabled" if enabled else "disabled")
    return jsonify({"status": "enabled" if enabled else "disabled"})
