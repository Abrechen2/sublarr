"""Backend management endpoints — /backends/*."""

import logging

import requests
from flask import jsonify, request

from routes.translate import bp
from routes.translate._helpers import BACKEND_TEMPLATES

logger = logging.getLogger(__name__)


# ─── Backend Management Endpoints ─────────────────────────────────────────────


@bp.route("/backends", methods=["GET"])
def list_backends():
    """List all registered translation backends with config status.
    ---
    get:
      tags:
        - Translate
      summary: List translation backends
      description: Returns all registered translation backends with their configuration status and capabilities.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: Backend list
          content:
            application/json:
              schema:
                type: object
                properties:
                  backends:
                    type: array
                    items:
                      type: object
                      properties:
                        name:
                          type: string
                        display_name:
                          type: string
                        configured:
                          type: boolean
                        config_fields:
                          type: array
                          items:
                            type: object
    """
    from translation import get_translation_manager

    manager = get_translation_manager()
    backends = manager.get_all_backends()
    return jsonify({"backends": backends})


@bp.route("/backends/test/<name>", methods=["POST"])
def test_backend(name):
    """Test a specific translation backend's health.
    ---
    post:
      tags:
        - Translate
      summary: Test translation backend
      description: Runs a health check on the specified translation backend and returns status with optional usage info.
      security:
        - apiKeyAuth: []
      parameters:
        - in: path
          name: name
          required: true
          schema:
            type: string
          description: Backend name (e.g. ollama, deepl, openai)
      responses:
        200:
          description: Health check result
          content:
            application/json:
              schema:
                type: object
                properties:
                  healthy:
                    type: boolean
                  message:
                    type: string
                  usage:
                    type: object
                    additionalProperties: true
        404:
          description: Backend not found
    """
    from translation import get_translation_manager

    manager = get_translation_manager()
    backend = manager.get_backend(name)

    if not backend:
        return jsonify({"error": f"Backend '{name}' not found"}), 404

    healthy, message = backend.health_check()
    result = {"healthy": healthy, "message": message}

    # Include usage info if available
    usage = backend.get_usage()
    if usage:
        result["usage"] = usage

    return jsonify(result)


@bp.route("/backends/<name>/config", methods=["PUT"])
def save_backend_config(name):
    """Save configuration for a translation backend.
    ---
    put:
      tags:
        - Translate
      summary: Save backend configuration
      description: Stores key-value pairs in config_entries with backend.<name>.<key> prefix and invalidates cached instance.
      security:
        - apiKeyAuth: []
      parameters:
        - in: path
          name: name
          required: true
          schema:
            type: string
          description: Backend name
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              additionalProperties:
                type: string
              description: Key-value config pairs for the backend
      responses:
        200:
          description: Configuration saved
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
        400:
          description: No configuration data provided
        404:
          description: Backend not found
    """
    from db.config import save_config_entry
    from translation import get_translation_manager

    data = request.get_json() or {}
    if not data:
        return jsonify({"error": "No configuration data provided"}), 400

    # Validate backend exists as a registered class
    manager = get_translation_manager()
    all_backends = manager.get_all_backends()
    known_names = {b["name"] for b in all_backends}
    if name not in known_names:
        return jsonify({"error": f"Backend '{name}' not found"}), 404

    # Store each config entry with namespace prefix
    for key, value in data.items():
        config_key = f"backend.{name}.{key}"
        save_config_entry(config_key, str(value))

    # Invalidate cached instance so next use picks up new config
    manager.invalidate_backend(name)

    return jsonify({"status": "saved"})


@bp.route("/backends/<name>/config", methods=["GET"])
def get_backend_config(name):
    """Get configuration for a translation backend.
    ---
    get:
      tags:
        - Translate
      summary: Get backend configuration
      description: Reads config_entries matching backend.<name>.* prefix. Password fields are masked with '***'.
      security:
        - apiKeyAuth: []
      parameters:
        - in: path
          name: name
          required: true
          schema:
            type: string
          description: Backend name
      responses:
        200:
          description: Backend configuration
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
    from translation import get_translation_manager

    # Validate backend exists
    manager = get_translation_manager()
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
    prefix = f"backend.{name}."
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


@bp.route("/backends/templates", methods=["GET"])
def get_backend_templates():
    """Return pre-configured LLM backend templates.
    ---
    get:
      tags:
        - Translate
      summary: List LLM backend templates
      description: Returns pre-configured LLM backend templates that users can use to quickly set up known providers.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: Template list
          content:
            application/json:
              schema:
                type: object
                properties:
                  templates:
                    type: array
                    items:
                      type: object
    """
    return jsonify({"templates": BACKEND_TEMPLATES})


@bp.route("/backends/ollama/pull", methods=["POST"])
def ollama_pull_model():
    """Pull an Ollama model by name.
    ---
    post:
      tags:
        - Translate
      summary: Pull an Ollama model
      description: >
        Triggers `ollama pull` for the given model name. Useful for installing
        community models (e.g. anime-translator-v6) directly from the UI.
        The Ollama server must be reachable at the configured URL.
      security:
        - apiKeyAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [model]
              properties:
                model:
                  type: string
                  example: "anime-translator-v6"
      responses:
        200:
          description: Pull completed
        400:
          description: Missing model name
        502:
          description: Ollama unreachable or pull failed
    """
    from translation import get_translation_manager

    data = request.get_json() or {}
    model = data.get("model", "").strip()
    if not model:
        return jsonify({"error": "model name required"}), 400

    # Get configured Ollama URL from active backend or fall back to settings
    try:
        manager = get_translation_manager()
        backend = manager.get_backend("ollama")
        ollama_url = backend._url if backend else None
    except Exception:
        ollama_url = None

    if not ollama_url:
        try:
            from config import get_settings

            ollama_url = get_settings().ollama_url
        except Exception:
            ollama_url = "http://localhost:11434"

    try:
        resp = requests.post(
            f"{ollama_url}/api/pull",
            json={"name": model, "stream": False},
            timeout=600,  # pulls can take several minutes
        )
        resp.raise_for_status()
        return jsonify({"ok": True, "model": model, "status": resp.json().get("status", "done")})
    except requests.Timeout:
        return jsonify(
            {"error": f"Pull timed out for '{model}' — try pulling manually via CLI"}
        ), 502
    except requests.ConnectionError:
        return jsonify({"error": f"Cannot connect to Ollama at {ollama_url}"}), 502
    except requests.HTTPError as e:
        return jsonify({"error": f"Ollama pull failed: {e}"}), 502
    except Exception as e:
        logger.exception("ollama_pull_model failed")
        return jsonify({"error": str(e)}), 500


@bp.route("/backends/stats", methods=["GET"])
def backend_stats():
    """Get translation stats for all backends.
    ---
    get:
      tags:
        - Translate
      summary: Get backend statistics
      description: Returns translation statistics (request count, errors, avg duration) for all translation backends.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: Backend statistics
          content:
            application/json:
              schema:
                type: object
                properties:
                  stats:
                    type: array
                    items:
                      type: object
                      additionalProperties: true
    """
    from db.translation import get_backend_stats

    stats = get_backend_stats()
    return jsonify({"stats": stats})
