"""Whisper global config routes: /config GET+PUT."""

import logging

from flask import jsonify, request

from routes.whisper import bp

logger = logging.getLogger(__name__)


@bp.route("/config", methods=["GET"])
def get_whisper_config():
    """Get global Whisper config.
    ---
    get:
      security:
        - apiKeyAuth: []
      tags:
        - Whisper
      summary: Get global Whisper config
      description: Returns global Whisper configuration including enabled state, active backend, and concurrency limit.
      responses:
        200:
          description: Whisper config
          content:
            application/json:
              schema:
                type: object
                properties:
                  whisper_backend:
                    type: string
                  max_concurrent_whisper:
                    type: integer
                  whisper_enabled:
                    type: boolean
    """
    # Function-local import: tests monkey-patch routes.whisper._get_config.
    from routes.whisper import _get_config

    config = {
        "whisper_backend": _get_config("whisper_backend", "subgen"),
        "max_concurrent_whisper": int(_get_config("max_concurrent_whisper", "1")),
        "whisper_enabled": _get_config("whisper_enabled", "false").lower() in ("true", "1", "yes"),
    }
    return jsonify(config)


@bp.route("/config", methods=["PUT"])
def save_whisper_config():
    """Save global Whisper config.

    Accepts JSON: {"whisper_backend": str, "max_concurrent_whisper": int, "whisper_enabled": bool}
    ---
    put:
      security:
        - apiKeyAuth: []
      tags:
        - Whisper
      summary: Save global Whisper config
      description: Updates global Whisper configuration. Resets the queue singleton if max_concurrent changes.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                whisper_backend:
                  type: string
                max_concurrent_whisper:
                  type: integer
                whisper_enabled:
                  type: boolean
      responses:
        200:
          description: Config saved
          content:
            application/json:
              schema:
                type: object
                properties:
                  success:
                    type: boolean
        400:
          description: No config data provided
    """
    from db.config import save_config_entry
    from routes.whisper import _reset_queue

    data = request.get_json() or {}
    if not data:
        return jsonify({"error": "No configuration data provided"}), 400

    allowed_keys = {
        "whisper_backend",
        "max_concurrent_whisper",
        "whisper_enabled",
        "whisper_fallback_min_score",
    }
    for key, value in data.items():
        if key not in allowed_keys:
            continue
        # Convert booleans to string
        if isinstance(value, bool):
            value = "true" if value else "false"
        save_config_entry(key, str(value))

    # Reset queue singleton if max_concurrent changed
    if "max_concurrent_whisper" in data:
        _reset_queue()

    return jsonify({"success": True})
