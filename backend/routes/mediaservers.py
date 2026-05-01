"""Media server routes -- /mediaservers/types, /mediaservers/instances, /mediaservers/test, /mediaservers/health."""

import json
import logging

from flask import Blueprint, jsonify, request

from extensions import limiter
from security_utils import validate_service_url

bp = Blueprint("mediaservers", __name__, url_prefix="/api/v1")
logger = logging.getLogger(__name__)

# Sensitive fields that GET returns masked. PUT treats values matching the
# mask format as "keep existing" so a GET-edit-PUT round-trip does not
# overwrite a real secret with the displayed mask.
_SENSITIVE_FIELDS = ("api_key", "token", "password")
_MASK_PREFIX = "***"
# Cap the number of media-server instances we accept in a single PUT to
# bound memory + DB write churn. Plex/Jellyfin/Kodi: a handful is the
# realistic ceiling.
_MAX_INSTANCES = 32


def _is_masked(value: str) -> bool:
    """True iff value looks like a mask returned from GET (``***abcd`` / ``***``)."""
    if not isinstance(value, str):
        return False
    return value == _MASK_PREFIX or (value.startswith(_MASK_PREFIX) and len(value) <= 7)


@bp.route("/mediaservers/types", methods=["GET"])
def list_server_types():
    """Return all registered media server type info (name, display_name, config_fields).
    ---
    get:
      security:
        - apiKeyAuth: []
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
      security:
        - apiKeyAuth: []
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
      security:
        - apiKeyAuth: []
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
    from db.config import get_config_entry, save_config_entry
    from mediaserver import get_media_server_manager, invalidate_media_server_manager

    body = request.get_json()
    if not isinstance(body, list):
        return jsonify({"error": "Expected a JSON array"}), 400
    if len(body) > _MAX_INSTANCES:
        return jsonify(
            {"error": f"Too many instances (max {_MAX_INSTANCES}, got {len(body)})"}
        ), 400

    # Load currently stored config so we can re-merge masked secret fields
    # the UI sent back unchanged.
    raw_existing = get_config_entry("media_servers_json")
    try:
        existing_entries = json.loads(raw_existing) if raw_existing else []
        if not isinstance(existing_entries, list):
            existing_entries = []
    except (json.JSONDecodeError, TypeError):
        existing_entries = []

    # Index existing by (type, name) — same compound key the manager uses
    # downstream when looking up an instance.
    existing_by_key = {}
    for prev in existing_entries:
        if isinstance(prev, dict) and prev.get("type") and prev.get("name"):
            existing_by_key[(prev["type"], prev["name"])] = prev

    # Validate entries
    for idx, entry in enumerate(body):
        if not isinstance(entry, dict):
            return jsonify({"error": f"Entry at index {idx} is not an object"}), 400
        if not entry.get("type"):
            return jsonify({"error": f"Entry at index {idx} missing 'type'"}), 400
        if not entry.get("name"):
            return jsonify({"error": f"Entry at index {idx} missing 'name'"}), 400
        url = entry.get("url") or entry.get("base_url")
        if url:
            ok, reason = validate_service_url(url)
            if not ok:
                return jsonify(
                    {"error": f"Entry at index {idx}: invalid url — {reason}"}
                ), 400
        # Re-merge masked secrets: if the UI sent ``***abcd`` (the mask GET
        # returns), drop the field so we keep the stored value instead of
        # overwriting with garbage.
        prev = existing_by_key.get((entry["type"], entry["name"]))
        for sensitive in _SENSITIVE_FIELDS:
            value = entry.get(sensitive)
            if value and _is_masked(value):
                if prev and prev.get(sensitive):
                    entry[sensitive] = prev[sensitive]
                else:
                    entry.pop(sensitive, None)

    save_config_entry("media_servers_json", json.dumps(body))

    # Reload manager with new config
    invalidate_media_server_manager()
    manager = get_media_server_manager()
    manager.load_instances()

    logger.info("Media server instances saved: %d entries", len(body))
    return jsonify(body)


@bp.route("/mediaservers/test", methods=["POST"])
@limiter.limit("10 per minute")
def test_instance():
    """Test a single media server instance.

    Accepts JSON body with type + config (url, token, etc.).
    Creates a temporary instance of the specified type, calls health_check().
    Does NOT persist anything -- this is for the "Test" button in UI.
    ---
    post:
      security:
        - apiKeyAuth: []
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

    # SSRF guard on user-supplied URL — rejects file://, ftp://, link-local,
    # cloud-metadata IPs etc. Test-button can otherwise be used to probe the
    # internal network from outside.
    url = data.get("url") or data.get("base_url")
    if url:
        ok, reason = validate_service_url(url)
        if not ok:
            return jsonify({"error": f"Invalid url: {reason}"}), 400

    # Whitelist constructor kwargs against the type's declared config_fields.
    # Stops a caller from passing arbitrary kwargs into the server class.
    type_def = types[server_type]
    allowed_keys = {f["key"] for f in type_def.get("config_fields", [])}
    config = {k: v for k, v in data.items() if k != "type" and k in allowed_keys}

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
      security:
        - apiKeyAuth: []
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
