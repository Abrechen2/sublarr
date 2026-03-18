"""Hook config CRUD endpoints + test."""

from flask import jsonify, request

from routes.hooks import bp

# ---- Hook Config CRUD --------------------------------------------------------


@bp.route("/hooks", methods=["GET"])
def list_hooks():
    """List all hook configs, optionally filtered by event_name.
    ---
    get:
      tags:
        - Events
      summary: List shell hooks
      description: Returns all shell hook configurations. Optionally filter by event name.
      parameters:
        - in: query
          name: event_name
          schema:
            type: string
          description: Filter hooks by event name
      responses:
        200:
          description: List of hook configs
          content:
            application/json:
              schema:
                type: array
                items:
                  type: object
    """
    from db.hooks import get_hook_configs

    event_name = request.args.get("event_name")
    configs = get_hook_configs(event_name=event_name)
    return jsonify(configs)


@bp.route("/hooks", methods=["POST"])
def create_hook():
    """Create a new hook config.
    ---
    post:
      tags:
        - Events
      summary: Create a shell hook
      description: Creates a new shell hook that executes a script when the specified event fires.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required:
                - name
                - event_name
                - script_path
              properties:
                name:
                  type: string
                event_name:
                  type: string
                  description: Must be a valid event from the catalog
                script_path:
                  type: string
                timeout_seconds:
                  type: integer
                  default: 30
      responses:
        201:
          description: Hook created
          content:
            application/json:
              schema:
                type: object
        400:
          description: Validation error (missing fields or invalid event_name)
    """
    from db.hooks import create_hook_config
    from events.catalog import EVENT_CATALOG

    data = request.get_json(silent=True) or {}

    name = data.get("name", "").strip()
    event_name = data.get("event_name", "").strip()
    script_path = data.get("script_path", "").strip()
    timeout_seconds = int(data.get("timeout_seconds", 30))

    if not name:
        return jsonify({"error": "name is required"}), 400
    if not event_name or event_name not in EVENT_CATALOG:
        return jsonify({"error": "event_name must be a valid event from the catalog"}), 400
    if not script_path:
        return jsonify({"error": "script_path is required"}), 400

    from config import get_settings
    from security_utils import is_safe_path

    _hooks_dir = getattr(get_settings(), "config_dir", "/config") + "/hooks"
    if not is_safe_path(script_path, _hooks_dir):
        return jsonify({"error": "script_path must be under /config/hooks/"}), 400

    hook = create_hook_config(name, event_name, script_path, timeout_seconds)
    return jsonify(hook), 201


@bp.route("/hooks/<int:hook_id>", methods=["GET"])
def get_hook(hook_id):
    """Get a single hook config by ID.
    ---
    get:
      tags:
        - Events
      summary: Get hook config
      description: Returns a single shell hook configuration by ID.
      parameters:
        - in: path
          name: hook_id
          required: true
          schema:
            type: integer
      responses:
        200:
          description: Hook config
          content:
            application/json:
              schema:
                type: object
        404:
          description: Hook not found
    """
    from db.hooks import get_hook_config

    hook = get_hook_config(hook_id)
    if hook is None:
        return jsonify({"error": "Hook not found"}), 404
    return jsonify(hook)


@bp.route("/hooks/<int:hook_id>", methods=["PUT"])
def update_hook(hook_id):
    """Update a hook config.
    ---
    put:
      tags:
        - Events
      summary: Update a shell hook
      description: Updates an existing shell hook configuration. Only provided fields are changed.
      parameters:
        - in: path
          name: hook_id
          required: true
          schema:
            type: integer
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                name:
                  type: string
                event_name:
                  type: string
                script_path:
                  type: string
                timeout_seconds:
                  type: integer
                enabled:
                  type: boolean
      responses:
        200:
          description: Updated hook config
          content:
            application/json:
              schema:
                type: object
        404:
          description: Hook not found
    """
    from db.hooks import get_hook_config, update_hook_config

    hook = get_hook_config(hook_id)
    if hook is None:
        return jsonify({"error": "Hook not found"}), 404

    data = request.get_json(silent=True) or {}
    allowed_keys = {"name", "event_name", "script_path", "timeout_seconds", "enabled"}
    updates = {k: v for k, v in data.items() if k in allowed_keys}

    if "script_path" in updates:
        from config import get_settings
        from security_utils import is_safe_path

        _hooks_dir = getattr(get_settings(), "config_dir", "/config") + "/hooks"
        if not is_safe_path(updates["script_path"], _hooks_dir):
            return jsonify({"error": "script_path must be under /config/hooks/"}), 400

    if "enabled" in updates:
        updates["enabled"] = 1 if updates["enabled"] else 0

    if updates:
        update_hook_config(hook_id, **updates)

    updated = get_hook_config(hook_id)
    return jsonify(updated)


@bp.route("/hooks/<int:hook_id>", methods=["DELETE"])
def delete_hook(hook_id):
    """Delete a hook config.
    ---
    delete:
      tags:
        - Events
      summary: Delete a shell hook
      description: Deletes a shell hook configuration by ID.
      parameters:
        - in: path
          name: hook_id
          required: true
          schema:
            type: integer
      responses:
        204:
          description: Hook deleted
    """
    from db.hooks import delete_hook_config

    delete_hook_config(hook_id)
    return "", 204


@bp.route("/hooks/<int:hook_id>/test", methods=["POST"])
def test_hook(hook_id):
    """Test-fire a hook with sample event data (blocking).
    ---
    post:
      tags:
        - Events
      summary: Test a shell hook
      description: Executes the hook script with sample payload data and returns the result. Blocks until completion.
      parameters:
        - in: path
          name: hook_id
          required: true
          schema:
            type: integer
      responses:
        200:
          description: Test result with exit code, stdout, stderr
          content:
            application/json:
              schema:
                type: object
                properties:
                  success:
                    type: boolean
                  exit_code:
                    type: integer
                  stdout:
                    type: string
                  stderr:
                    type: string
                  duration_ms:
                    type: number
        404:
          description: Hook not found
    """
    from db.hooks import get_hook_config
    from events.catalog import EVENT_CATALOG
    from events.hooks import HookEngine

    hook = get_hook_config(hook_id)
    if hook is None:
        return jsonify({"error": "Hook not found"}), 404

    event_name = hook.get("event_name", "")
    catalog_entry = EVENT_CATALOG.get(event_name, {})
    payload_keys = catalog_entry.get("payload_keys", [])
    sample_payload = {key: "test_value" for key in payload_keys}

    engine = HookEngine()
    result = engine.execute_hook(hook, event_name, sample_payload)
    return jsonify(result)
