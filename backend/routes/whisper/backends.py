"""Whisper backend routes: /backends, /backends/test/<name>, /backends/config/<name>."""

import logging

from flask import jsonify, request

from routes.whisper import bp

logger = logging.getLogger(__name__)


@bp.route("/backends", methods=["GET"])
def list_backends():
    """List available Whisper backends with config.
    ---
    get:
      security:
        - apiKeyAuth: []
      tags:
        - Whisper
      summary: List Whisper backends
      description: Returns all available Whisper backends with their configuration fields and status.
      responses:
        200:
          description: List of Whisper backends
          content:
            application/json:
              schema:
                type: object
                properties:
                  backends:
                    type: array
                    items:
                      type: object
    """
    from whisper import get_whisper_manager

    manager = get_whisper_manager()
    backends = manager.get_all_backends()
    return jsonify({"backends": backends})


@bp.route("/backends/test/<name>", methods=["POST"])
def test_backend(name):
    """Test a specific Whisper backend.
    ---
    post:
      security:
        - apiKeyAuth: []
      tags:
        - Whisper
      summary: Test Whisper backend
      description: Tests connectivity and availability of a specific Whisper backend.
      parameters:
        - in: path
          name: name
          required: true
          schema:
            type: string
      responses:
        200:
          description: Test result
          content:
            application/json:
              schema:
                type: object
                properties:
                  healthy:
                    type: boolean
                  message:
                    type: string
        404:
          description: Backend not found
    """
    from whisper import get_whisper_manager

    manager = get_whisper_manager()
    backend = manager.get_backend(name)

    if not backend:
        return jsonify({"error": f"Backend '{name}' not found"}), 404

    healthy, message = backend.health_check()
    return jsonify({"healthy": healthy, "message": message})


@bp.route("/backends/config/<name>", methods=["GET"])
def get_backend_config(name):
    """Get backend config.

    Reads from config_entries with whisper.<name>.<key> namespacing.
    Masks password fields.
    ---
    get:
      security:
        - apiKeyAuth: []
      tags:
        - Whisper
      summary: Get Whisper backend config
      description: Returns the configuration for a specific Whisper backend with password fields masked.
      parameters:
        - in: path
          name: name
          required: true
          schema:
            type: string
      responses:
        200:
          description: Backend config
          content:
            application/json:
              schema:
                type: object
                additionalProperties:
                  type: string
        404:
          description: Backend not found
    """
    from db.config import get_all_config_entries
    from whisper import get_whisper_manager

    # Validate backend exists
    manager = get_whisper_manager()
    all_backends = manager.get_all_backends()
    backend_info = None
    for b in all_backends:
        if b["name"] == name:
            backend_info = b
            break

    if not backend_info:
        return jsonify({"error": f"Backend '{name}' not found"}), 404

    # Load config entries with namespace prefix
    all_entries = get_all_config_entries()
    prefix = f"whisper.{name}."
    config = {}
    for key, value in all_entries.items():
        if key.startswith(prefix):
            short_key = key[len(prefix) :]
            config[short_key] = value

    # Build set of password field keys for masking
    password_keys = set()
    for field_def in backend_info.get("config_fields", []):
        if field_def.get("type") == "password":
            password_keys.add(field_def["key"])

    # Mask password fields
    for key in config:
        if key in password_keys and config[key]:
            config[key] = "***"

    return jsonify(config)


@bp.route("/backends/config/<name>", methods=["PUT"])
def save_backend_config(name):
    """Save backend config.

    Accepts JSON config dict. Saves to config_entries with whisper.<name>.<key> namespacing.
    Invalidates cached backend instance.
    ---
    put:
      security:
        - apiKeyAuth: []
      tags:
        - Whisper
      summary: Save Whisper backend config
      description: Saves configuration for a specific Whisper backend and invalidates the cached instance.
      parameters:
        - in: path
          name: name
          required: true
          schema:
            type: string
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              additionalProperties:
                type: string
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
        404:
          description: Backend not found
    """
    from db.config import save_config_entry
    from whisper import get_whisper_manager

    data = request.get_json() or {}
    if not data:
        return jsonify({"error": "No configuration data provided"}), 400

    # Validate backend exists
    manager = get_whisper_manager()
    all_backends = manager.get_all_backends()
    known_names = {b["name"] for b in all_backends}
    if name not in known_names:
        return jsonify({"error": f"Backend '{name}' not found"}), 404

    # Store each config entry with namespace prefix
    for key, value in data.items():
        config_key = f"whisper.{name}.{key}"
        save_config_entry(config_key, str(value))

    # Invalidate cached instance so next use picks up new config
    manager.invalidate_backend()

    return jsonify({"success": True})
