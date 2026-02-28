"""Hooks routes -- CRUD for shell hooks, webhooks, hook logs, event catalog, scoring weights, and provider modifiers.

Provides the API surface for the Settings "Events & Hooks" and "Scoring" tabs.
All endpoints are under /api/v1/.
"""

import logging

from flask import Blueprint, jsonify, request

bp = Blueprint("hooks", __name__, url_prefix="/api/v1")
logger = logging.getLogger(__name__)


# ---- Event Catalog -----------------------------------------------------------


@bp.route("/events/catalog", methods=["GET"])
def get_event_catalog():
    """Return the EVENT_CATALOG as a JSON list for UI dropdowns.
    ---
    get:
      tags:
        - Events
      summary: Get event catalog
      description: Returns all available event types with labels, descriptions, and payload key definitions for hook/webhook configuration.
      responses:
        200:
          description: Event catalog
          content:
            application/json:
              schema:
                type: array
                items:
                  type: object
                  properties:
                    name:
                      type: string
                    label:
                      type: string
                    description:
                      type: string
                    payload_keys:
                      type: array
                      items:
                        type: string
    """
    from events.catalog import EVENT_CATALOG

    items = []
    for name, meta in EVENT_CATALOG.items():
        items.append(
            {
                "name": name,
                "label": meta.get("label", name),
                "description": meta.get("description", ""),
                "payload_keys": meta.get("payload_keys", []),
            }
        )
    return jsonify(items)


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


# ---- Webhook Config CRUD -----------------------------------------------------


def _mask_webhook_secret(webhook: dict) -> dict:
    """Return a copy of a webhook config dict with the secret masked."""
    if webhook and webhook.get("secret"):
        return {**webhook, "secret": "***configured***"}
    return webhook


@bp.route("/webhooks", methods=["GET"])
def list_webhooks():
    """List all webhook configs, optionally filtered by event_name.
    ---
    get:
      tags:
        - Events
      summary: List outgoing webhooks
      description: Returns all outgoing webhook configurations. Optionally filter by event name.
      parameters:
        - in: query
          name: event_name
          schema:
            type: string
          description: Filter webhooks by event name
      responses:
        200:
          description: List of webhook configs
          content:
            application/json:
              schema:
                type: array
                items:
                  type: object
    """
    from db.hooks import get_webhook_configs

    event_name = request.args.get("event_name")
    configs = get_webhook_configs(event_name=event_name)
    return jsonify([_mask_webhook_secret(w) for w in configs])


@bp.route("/webhooks", methods=["POST"])
def create_webhook():
    """Create a new webhook config.
    ---
    post:
      tags:
        - Events
      summary: Create an outgoing webhook
      description: Creates a new outgoing webhook that sends HTTP POST requests when events fire. Use '*' for event_name to receive all events.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required:
                - name
                - event_name
                - url
              properties:
                name:
                  type: string
                event_name:
                  type: string
                  description: Event name from catalog, or '*' for all events
                url:
                  type: string
                  description: Must start with http:// or https://
                secret:
                  type: string
                  description: HMAC signing secret for payload verification
                retry_count:
                  type: integer
                  default: 3
                timeout_seconds:
                  type: integer
                  default: 10
      responses:
        201:
          description: Webhook created
          content:
            application/json:
              schema:
                type: object
        400:
          description: Validation error
    """
    from db.hooks import create_webhook_config
    from events.catalog import EVENT_CATALOG

    data = request.get_json(silent=True) or {}

    name = data.get("name", "").strip()
    event_name = data.get("event_name", "").strip()
    url = data.get("url", "").strip()
    secret = data.get("secret", "")
    retry_count = int(data.get("retry_count", 3))
    timeout_seconds = int(data.get("timeout_seconds", 10))

    if not name:
        return jsonify({"error": "name is required"}), 400
    if not event_name:
        return jsonify({"error": "event_name is required"}), 400
    if event_name != "*" and event_name not in EVENT_CATALOG:
        return jsonify({"error": "event_name must be a valid event or '*' for all events"}), 400
    if not url or not (url.startswith("http://") or url.startswith("https://")):
        return jsonify({"error": "url is required and must start with http:// or https://"}), 400

    webhook = create_webhook_config(name, event_name, url, secret, retry_count, timeout_seconds)
    return jsonify(_mask_webhook_secret(webhook)), 201


@bp.route("/webhooks/<int:webhook_id>", methods=["GET"])
def get_webhook(webhook_id):
    """Get a single webhook config by ID.
    ---
    get:
      tags:
        - Events
      summary: Get webhook config
      description: Returns a single outgoing webhook configuration by ID.
      parameters:
        - in: path
          name: webhook_id
          required: true
          schema:
            type: integer
      responses:
        200:
          description: Webhook config
          content:
            application/json:
              schema:
                type: object
        404:
          description: Webhook not found
    """
    from db.hooks import get_webhook_config

    webhook = get_webhook_config(webhook_id)
    if webhook is None:
        return jsonify({"error": "Webhook not found"}), 404
    return jsonify(_mask_webhook_secret(webhook))


@bp.route("/webhooks/<int:webhook_id>", methods=["PUT"])
def update_webhook(webhook_id):
    """Update a webhook config.
    ---
    put:
      tags:
        - Events
      summary: Update an outgoing webhook
      description: Updates an existing outgoing webhook configuration. Only provided fields are changed.
      parameters:
        - in: path
          name: webhook_id
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
                url:
                  type: string
                secret:
                  type: string
                retry_count:
                  type: integer
                timeout_seconds:
                  type: integer
                enabled:
                  type: boolean
      responses:
        200:
          description: Updated webhook config
          content:
            application/json:
              schema:
                type: object
        404:
          description: Webhook not found
    """
    from db.hooks import get_webhook_config, update_webhook_config

    webhook = get_webhook_config(webhook_id)
    if webhook is None:
        return jsonify({"error": "Webhook not found"}), 404

    data = request.get_json(silent=True) or {}
    allowed_keys = {
        "name",
        "event_name",
        "url",
        "secret",
        "retry_count",
        "timeout_seconds",
        "enabled",
    }
    updates = {k: v for k, v in data.items() if k in allowed_keys}

    if "enabled" in updates:
        updates["enabled"] = 1 if updates["enabled"] else 0

    if updates:
        update_webhook_config(webhook_id, **updates)

    updated = get_webhook_config(webhook_id)
    return jsonify(_mask_webhook_secret(updated))


@bp.route("/webhooks/<int:webhook_id>", methods=["DELETE"])
def delete_webhook(webhook_id):
    """Delete a webhook config.
    ---
    delete:
      tags:
        - Events
      summary: Delete an outgoing webhook
      description: Deletes an outgoing webhook configuration by ID.
      parameters:
        - in: path
          name: webhook_id
          required: true
          schema:
            type: integer
      responses:
        204:
          description: Webhook deleted
    """
    from db.hooks import delete_webhook_config

    delete_webhook_config(webhook_id)
    return "", 204


@bp.route("/webhooks/<int:webhook_id>/test", methods=["POST"])
def test_webhook(webhook_id):
    """Test-fire a webhook with sample payload (blocking).
    ---
    post:
      tags:
        - Events
      summary: Test an outgoing webhook
      description: Sends a test HTTP POST to the webhook URL with sample payload and returns the result. Wildcards use 'config_updated' as the sample event.
      parameters:
        - in: path
          name: webhook_id
          required: true
          schema:
            type: integer
      responses:
        200:
          description: Test result with status code and response
          content:
            application/json:
              schema:
                type: object
                properties:
                  success:
                    type: boolean
                  status_code:
                    type: integer
                  error:
                    type: string
                  duration_ms:
                    type: number
        404:
          description: Webhook not found
    """
    from db.hooks import get_webhook_config
    from events.catalog import EVENT_CATALOG
    from events.webhooks import WebhookDispatcher

    webhook = get_webhook_config(webhook_id)
    if webhook is None:
        return jsonify({"error": "Webhook not found"}), 404

    event_name = webhook.get("event_name", "")
    if event_name == "*":
        event_name = "config_updated"
    catalog_entry = EVENT_CATALOG.get(event_name, {})
    payload_keys = catalog_entry.get("payload_keys", [])
    sample_payload = {key: "test_value" for key in payload_keys}

    dispatcher = WebhookDispatcher()
    result = dispatcher.send_webhook(webhook, event_name, sample_payload)
    return jsonify(result)


# ---- Hook Log endpoints ------------------------------------------------------


@bp.route("/hooks/logs", methods=["GET"])
def list_hook_logs():
    """List hook execution logs with optional filters.
    ---
    get:
      tags:
        - Events
      summary: List hook execution logs
      description: Returns hook and webhook execution logs with optional filtering by hook or webhook ID.
      parameters:
        - in: query
          name: hook_id
          schema:
            type: integer
          description: Filter logs by hook ID
        - in: query
          name: webhook_id
          schema:
            type: integer
          description: Filter logs by webhook ID
        - in: query
          name: limit
          schema:
            type: integer
            default: 50
      responses:
        200:
          description: List of execution logs
          content:
            application/json:
              schema:
                type: array
                items:
                  type: object
    """
    from db.hooks import get_hook_logs

    hook_id = request.args.get("hook_id", type=int)
    webhook_id = request.args.get("webhook_id", type=int)
    limit = request.args.get("limit", 50, type=int)

    logs = get_hook_logs(hook_id=hook_id, webhook_id=webhook_id, limit=limit)
    return jsonify(logs)


@bp.route("/hooks/logs", methods=["DELETE"])
def clear_logs():
    """Clear all hook logs.
    ---
    delete:
      tags:
        - Events
      summary: Clear hook logs
      description: Deletes all hook and webhook execution logs.
      responses:
        204:
          description: Logs cleared
    """
    from db.hooks import clear_hook_logs

    clear_hook_logs()
    return "", 204


# ---- Scoring Weight endpoints ------------------------------------------------


@bp.route("/scoring/weights", methods=["GET"])
def get_weights():
    """Return all scoring weights (episode + movie) merged with defaults.
    ---
    get:
      tags:
        - Events
      summary: Get scoring weights
      description: Returns current scoring weights for episode and movie subtitle matching, along with the default values.
      responses:
        200:
          description: Scoring weights
          content:
            application/json:
              schema:
                type: object
                properties:
                  episode:
                    type: object
                    additionalProperties:
                      type: number
                  movie:
                    type: object
                    additionalProperties:
                      type: number
                  defaults:
                    type: object
                    properties:
                      episode:
                        type: object
                        additionalProperties:
                          type: number
                      movie:
                        type: object
                        additionalProperties:
                          type: number
    """
    from db.scoring import _DEFAULT_EPISODE_WEIGHTS, _DEFAULT_MOVIE_WEIGHTS, get_all_scoring_weights

    weights = get_all_scoring_weights()
    return jsonify(
        {
            "episode": weights["episode"],
            "movie": weights["movie"],
            "defaults": {
                "episode": _DEFAULT_EPISODE_WEIGHTS,
                "movie": _DEFAULT_MOVIE_WEIGHTS,
            },
        }
    )


@bp.route("/scoring/weights", methods=["PUT"])
def update_weights():
    """Update scoring weights for episode and/or movie types.
    ---
    put:
      tags:
        - Events
      summary: Update scoring weights
      description: Updates scoring weights for episode and/or movie subtitle matching. Invalidates the scoring cache.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                episode:
                  type: object
                  additionalProperties:
                    type: number
                movie:
                  type: object
                  additionalProperties:
                    type: number
      responses:
        200:
          description: Updated scoring weights
          content:
            application/json:
              schema:
                type: object
    """
    from db.scoring import get_all_scoring_weights, set_scoring_weights
    from providers.base import invalidate_scoring_cache

    data = request.get_json(silent=True) or {}

    if "episode" in data and isinstance(data["episode"], dict):
        set_scoring_weights("episode", data["episode"])
    if "movie" in data and isinstance(data["movie"], dict):
        set_scoring_weights("movie", data["movie"])

    invalidate_scoring_cache()

    weights = get_all_scoring_weights()
    from db.scoring import _DEFAULT_EPISODE_WEIGHTS, _DEFAULT_MOVIE_WEIGHTS

    return jsonify(
        {
            "episode": weights["episode"],
            "movie": weights["movie"],
            "defaults": {
                "episode": _DEFAULT_EPISODE_WEIGHTS,
                "movie": _DEFAULT_MOVIE_WEIGHTS,
            },
        }
    )


@bp.route("/scoring/weights", methods=["DELETE"])
def reset_weights():
    """Reset all scoring weights to defaults.
    ---
    delete:
      tags:
        - Events
      summary: Reset scoring weights
      description: Resets all scoring weights to their default values and invalidates the scoring cache.
      responses:
        204:
          description: Weights reset to defaults
    """
    from db.scoring import reset_scoring_weights
    from providers.base import invalidate_scoring_cache

    reset_scoring_weights()
    invalidate_scoring_cache()
    return "", 204


# ---- Provider Modifier endpoints ---------------------------------------------


@bp.route("/scoring/modifiers", methods=["GET"])
def get_modifiers():
    """Return all provider score modifiers.
    ---
    get:
      tags:
        - Events
      summary: Get provider score modifiers
      description: Returns all provider-specific score modifiers (-100 to +100) that adjust subtitle match scoring.
      responses:
        200:
          description: Provider modifiers map
          content:
            application/json:
              schema:
                type: object
                additionalProperties:
                  type: integer
    """
    from db.scoring import get_all_provider_modifiers

    modifiers = get_all_provider_modifiers()
    return jsonify(modifiers)


@bp.route("/scoring/modifiers", methods=["PUT"])
def update_modifiers():
    """Update provider modifiers from a dict of {provider_name: modifier}.
    ---
    put:
      tags:
        - Events
      summary: Update provider score modifiers
      description: Sets score modifiers for one or more providers. Invalidates the scoring cache.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              additionalProperties:
                type: integer
              example:
                animetosho: 20
                opensubtitles: -10
      responses:
        200:
          description: Updated modifiers
          content:
            application/json:
              schema:
                type: object
                additionalProperties:
                  type: integer
    """
    from db.scoring import get_all_provider_modifiers, set_provider_modifier
    from providers.base import invalidate_scoring_cache

    data = request.get_json(silent=True) or {}

    for provider_name, modifier in data.items():
        set_provider_modifier(provider_name, int(modifier))

    invalidate_scoring_cache()

    modifiers = get_all_provider_modifiers()
    return jsonify(modifiers)


@bp.route("/scoring/modifiers/<provider_name>", methods=["DELETE"])
def delete_modifier(provider_name):
    """Delete a single provider modifier.
    ---
    delete:
      tags:
        - Events
      summary: Delete a provider score modifier
      description: Removes the score modifier for a specific provider, reverting it to the default (0).
      parameters:
        - in: path
          name: provider_name
          required: true
          schema:
            type: string
      responses:
        204:
          description: Modifier deleted
    """
    from db.scoring import delete_provider_modifier
    from providers.base import invalidate_scoring_cache

    delete_provider_modifier(provider_name)
    invalidate_scoring_cache()
    return "", 204
