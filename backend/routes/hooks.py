"""Hooks routes -- CRUD for shell hooks, webhooks, hook logs, event catalog, scoring weights, and provider modifiers.

Provides the API surface for the Settings "Events & Hooks" and "Scoring" tabs.
All endpoints are under /api/v1/.
"""

import logging

from flask import Blueprint, request, jsonify

bp = Blueprint("hooks", __name__, url_prefix="/api/v1")
logger = logging.getLogger(__name__)


# ---- Event Catalog -----------------------------------------------------------

@bp.route("/events/catalog", methods=["GET"])
def get_event_catalog():
    """Return the EVENT_CATALOG as a JSON list for UI dropdowns."""
    from events.catalog import EVENT_CATALOG

    items = []
    for name, meta in EVENT_CATALOG.items():
        items.append({
            "name": name,
            "label": meta.get("label", name),
            "description": meta.get("description", ""),
            "payload_keys": meta.get("payload_keys", []),
        })
    return jsonify(items)


# ---- Hook Config CRUD --------------------------------------------------------

@bp.route("/hooks", methods=["GET"])
def list_hooks():
    """List all hook configs, optionally filtered by event_name."""
    from db.hooks import get_hook_configs

    event_name = request.args.get("event_name")
    configs = get_hook_configs(event_name=event_name)
    return jsonify(configs)


@bp.route("/hooks", methods=["POST"])
def create_hook():
    """Create a new hook config."""
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
        return jsonify({"error": f"event_name must be a valid event from the catalog"}), 400
    if not script_path:
        return jsonify({"error": "script_path is required"}), 400

    hook = create_hook_config(name, event_name, script_path, timeout_seconds)
    return jsonify(hook), 201


@bp.route("/hooks/<int:hook_id>", methods=["GET"])
def get_hook(hook_id):
    """Get a single hook config by ID."""
    from db.hooks import get_hook_config

    hook = get_hook_config(hook_id)
    if hook is None:
        return jsonify({"error": "Hook not found"}), 404
    return jsonify(hook)


@bp.route("/hooks/<int:hook_id>", methods=["PUT"])
def update_hook(hook_id):
    """Update a hook config."""
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
    """Delete a hook config."""
    from db.hooks import delete_hook_config

    delete_hook_config(hook_id)
    return "", 204


@bp.route("/hooks/<int:hook_id>/test", methods=["POST"])
def test_hook(hook_id):
    """Test-fire a hook with sample event data (blocking)."""
    from db.hooks import get_hook_config
    from events.hooks import HookEngine
    from events.catalog import EVENT_CATALOG

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

@bp.route("/webhooks", methods=["GET"])
def list_webhooks():
    """List all webhook configs, optionally filtered by event_name."""
    from db.hooks import get_webhook_configs

    event_name = request.args.get("event_name")
    configs = get_webhook_configs(event_name=event_name)
    return jsonify(configs)


@bp.route("/webhooks", methods=["POST"])
def create_webhook():
    """Create a new webhook config."""
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
    return jsonify(webhook), 201


@bp.route("/webhooks/<int:webhook_id>", methods=["GET"])
def get_webhook(webhook_id):
    """Get a single webhook config by ID."""
    from db.hooks import get_webhook_config

    webhook = get_webhook_config(webhook_id)
    if webhook is None:
        return jsonify({"error": "Webhook not found"}), 404
    return jsonify(webhook)


@bp.route("/webhooks/<int:webhook_id>", methods=["PUT"])
def update_webhook(webhook_id):
    """Update a webhook config."""
    from db.hooks import get_webhook_config, update_webhook_config

    webhook = get_webhook_config(webhook_id)
    if webhook is None:
        return jsonify({"error": "Webhook not found"}), 404

    data = request.get_json(silent=True) or {}
    allowed_keys = {"name", "event_name", "url", "secret", "retry_count", "timeout_seconds", "enabled"}
    updates = {k: v for k, v in data.items() if k in allowed_keys}

    if "enabled" in updates:
        updates["enabled"] = 1 if updates["enabled"] else 0

    if updates:
        update_webhook_config(webhook_id, **updates)

    updated = get_webhook_config(webhook_id)
    return jsonify(updated)


@bp.route("/webhooks/<int:webhook_id>", methods=["DELETE"])
def delete_webhook(webhook_id):
    """Delete a webhook config."""
    from db.hooks import delete_webhook_config

    delete_webhook_config(webhook_id)
    return "", 204


@bp.route("/webhooks/<int:webhook_id>/test", methods=["POST"])
def test_webhook(webhook_id):
    """Test-fire a webhook with sample payload (blocking)."""
    from db.hooks import get_webhook_config
    from events.webhooks import WebhookDispatcher
    from events.catalog import EVENT_CATALOG

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
    """List hook execution logs with optional filters."""
    from db.hooks import get_hook_logs

    hook_id = request.args.get("hook_id", type=int)
    webhook_id = request.args.get("webhook_id", type=int)
    limit = request.args.get("limit", 50, type=int)

    logs = get_hook_logs(hook_id=hook_id, webhook_id=webhook_id, limit=limit)
    return jsonify(logs)


@bp.route("/hooks/logs", methods=["DELETE"])
def clear_logs():
    """Clear all hook logs."""
    from db.hooks import clear_hook_logs

    clear_hook_logs()
    return "", 204


# ---- Scoring Weight endpoints ------------------------------------------------

@bp.route("/scoring/weights", methods=["GET"])
def get_weights():
    """Return all scoring weights (episode + movie) merged with defaults."""
    from db.scoring import get_all_scoring_weights, _DEFAULT_EPISODE_WEIGHTS, _DEFAULT_MOVIE_WEIGHTS

    weights = get_all_scoring_weights()
    return jsonify({
        "episode": weights["episode"],
        "movie": weights["movie"],
        "defaults": {
            "episode": _DEFAULT_EPISODE_WEIGHTS,
            "movie": _DEFAULT_MOVIE_WEIGHTS,
        },
    })


@bp.route("/scoring/weights", methods=["PUT"])
def update_weights():
    """Update scoring weights for episode and/or movie types."""
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
    return jsonify({
        "episode": weights["episode"],
        "movie": weights["movie"],
        "defaults": {
            "episode": _DEFAULT_EPISODE_WEIGHTS,
            "movie": _DEFAULT_MOVIE_WEIGHTS,
        },
    })


@bp.route("/scoring/weights", methods=["DELETE"])
def reset_weights():
    """Reset all scoring weights to defaults."""
    from db.scoring import reset_scoring_weights
    from providers.base import invalidate_scoring_cache

    reset_scoring_weights()
    invalidate_scoring_cache()
    return "", 204


# ---- Provider Modifier endpoints ---------------------------------------------

@bp.route("/scoring/modifiers", methods=["GET"])
def get_modifiers():
    """Return all provider score modifiers."""
    from db.scoring import get_all_provider_modifiers

    modifiers = get_all_provider_modifiers()
    return jsonify(modifiers)


@bp.route("/scoring/modifiers", methods=["PUT"])
def update_modifiers():
    """Update provider modifiers from a dict of {provider_name: modifier}."""
    from db.scoring import set_provider_modifier, get_all_provider_modifiers
    from providers.base import invalidate_scoring_cache

    data = request.get_json(silent=True) or {}

    for provider_name, modifier in data.items():
        set_provider_modifier(provider_name, int(modifier))

    invalidate_scoring_cache()

    modifiers = get_all_provider_modifiers()
    return jsonify(modifiers)


@bp.route("/scoring/modifiers/<provider_name>", methods=["DELETE"])
def delete_modifier(provider_name):
    """Delete a single provider modifier."""
    from db.scoring import delete_provider_modifier
    from providers.base import invalidate_scoring_cache

    delete_provider_modifier(provider_name)
    invalidate_scoring_cache()
    return "", 204
