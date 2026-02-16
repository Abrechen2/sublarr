"""Media server routes -- /mediaservers/types, /mediaservers/instances, /mediaservers/test, /mediaservers/health."""

import json
import logging

from flask import Blueprint, request, jsonify

bp = Blueprint("mediaservers", __name__, url_prefix="/api/v1")
logger = logging.getLogger(__name__)


@bp.route("/mediaservers/types", methods=["GET"])
def list_server_types():
    """Return all registered media server type info (name, display_name, config_fields).
    ---
    get:
      tags:
        - MediaServers
      summary: List media server types
      description: Returns all registered media server types with their display names and configuration field definitions.
      responses:
        200:
          description: List of media server types
          content:
            application/json:
              schema:
                type: array
                items:
                  type: object
                  properties:
                    name:
                      type: string
                    display_name:
                      type: string
                    config_fields:
                      type: array
                      items:
                        type: object
    """
    from mediaserver import get_media_server_manager

    manager = get_media_server_manager()
    types = manager.get_all_server_types()
    return jsonify(types)


@bp.route("/mediaservers/instances", methods=["GET"])
def get_instances():
    """Return current media server instances from config.

    Masks password/token fields in the response (show only last 4 chars).
    ---
    get:
      tags:
        - MediaServers
      summary: List media server instances
      description: Returns all configured media server instances with sensitive fields masked.
      responses:
        200:
          description: List of media server instances
          content:
            application/json:
              schema:
                type: array
                items:
                  type: object
                  properties:
                    type:
                      type: string
                    name:
                      type: string
                    enabled:
                      type: boolean
    """
    from db.config import get_config_entry

    raw = get_config_entry("media_servers_json")
    if not raw:
        return jsonify([])

    try:
        instances = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return jsonify([])

    if not isinstance(instances, list):
        return jsonify([])

    # Mask sensitive fields
    masked = []
    for entry in instances:
        safe = dict(entry)
        for key in ("api_key", "token", "password"):
            if key in safe and safe[key]:
                val = str(safe[key])
                if len(val) > 4:
                    safe[key] = "***" + val[-4:]
                else:
                    safe[key] = "***"
        masked.append(safe)

    return jsonify(masked)


@bp.route("/mediaservers/instances", methods=["PUT"])
def save_instances():
    """Save the full instances array.

    Validates each entry has required fields (type, name).
    After saving, invalidates and reloads the media server manager.
    ---
    put:
      tags:
        - MediaServers
      summary: Save media server instances
      description: Replaces the full media server instances array. Validates entries and reloads the media server manager.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: array
              items:
                type: object
                required:
                  - type
                  - name
                properties:
                  type:
                    type: string
                  name:
                    type: string
                  enabled:
                    type: boolean
      responses:
        200:
          description: Instances saved
          content:
            application/json:
              schema:
                type: array
                items:
                  type: object
        400:
          description: Validation error
    """
    from db.config import save_config_entry
    from mediaserver import invalidate_media_server_manager, get_media_server_manager

    body = request.get_json()
    if not isinstance(body, list):
        return jsonify({"error": "Expected a JSON array"}), 400

    # Validate entries
    for idx, entry in enumerate(body):
        if not isinstance(entry, dict):
            return jsonify({"error": f"Entry at index {idx} is not an object"}), 400
        if not entry.get("type"):
            return jsonify({"error": f"Entry at index {idx} missing 'type'"}), 400
        if not entry.get("name"):
            return jsonify({"error": f"Entry at index {idx} missing 'name'"}), 400

    save_config_entry("media_servers_json", json.dumps(body))

    # Reload manager with new config
    invalidate_media_server_manager()
    manager = get_media_server_manager()
    manager.load_instances()

    logger.info("Media server instances saved: %d entries", len(body))
    return jsonify(body)


@bp.route("/mediaservers/test", methods=["POST"])
def test_instance():
    """Test a single media server instance.

    Accepts JSON body with type + config (url, token, etc.).
    Creates a temporary instance of the specified type, calls health_check().
    Does NOT persist anything -- this is for the "Test" button in UI.
    ---
    post:
      tags:
        - MediaServers
      summary: Test media server connection
      description: Creates a temporary media server instance and tests connectivity. Does not persist the configuration.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required:
                - type
              properties:
                type:
                  type: string
                  description: Media server type (jellyfin, plex, kodi)
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
        400:
          description: Missing type field or unknown server type
    """
    from mediaserver import get_media_server_manager

    data = request.get_json() or {}
    server_type = data.get("type", "")

    if not server_type:
        return jsonify({"error": "Missing 'type' field"}), 400

    manager = get_media_server_manager()
    types = {t["name"]: t for t in manager.get_all_server_types()}

    if server_type not in types:
        return jsonify({"error": f"Unknown server type: {server_type}"}), 400

    # Create a temporary instance with the provided config
    config = {k: v for k, v in data.items() if k not in ("type",)}

    try:
        cls = manager._server_classes[server_type]
        instance = cls(**config)
        healthy, message = instance.health_check()
        return jsonify({"healthy": healthy, "message": message})
    except Exception as e:
        return jsonify({"healthy": False, "message": str(e)})


@bp.route("/mediaservers/health", methods=["GET"])
def health():
    """Get health status of all configured media server instances.
    ---
    get:
      tags:
        - MediaServers
      summary: Check media server health
      description: Returns health status for all configured media server instances.
      responses:
        200:
          description: Health results per instance
          content:
            application/json:
              schema:
                type: array
                items:
                  type: object
                  properties:
                    name:
                      type: string
                    type:
                      type: string
                    healthy:
                      type: boolean
                    message:
                      type: string
    """
    from mediaserver import get_media_server_manager

    manager = get_media_server_manager()
    health_results = manager.health_check_all()
    return jsonify(health_results)
