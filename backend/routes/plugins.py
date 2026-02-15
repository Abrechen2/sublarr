"""Plugin management routes -- /plugins, /plugins/reload, /plugins/<name>/config."""

import logging
from flask import Blueprint, request, jsonify

bp = Blueprint("plugins", __name__, url_prefix="/api/v1")
logger = logging.getLogger(__name__)


@bp.route("/plugins", methods=["GET"])
def list_plugins():
    """List all loaded plugins with their manifest info and config fields.

    Returns:
        {"plugins": [...]} or {"plugins": [], "error": "..."} if no plugin manager.
    """
    from providers.plugins import get_plugin_manager

    manager = get_plugin_manager()
    if not manager:
        return jsonify({"plugins": [], "message": "Plugin system not initialized"})

    plugins = manager.get_plugin_info()
    errors = manager.get_errors()

    return jsonify({
        "plugins": plugins,
        "errors": errors,
    })


@bp.route("/plugins/reload", methods=["POST"])
def reload_plugins():
    """Trigger plugin re-discovery and re-registration.

    This unloads all currently loaded plugins, re-scans the plugins
    directory, and re-initializes the ProviderManager with new plugins.

    Returns:
        {"loaded": [...], "errors": [...]}
    """
    from providers.plugins import get_plugin_manager
    from providers import invalidate_manager

    manager = get_plugin_manager()
    if not manager:
        return jsonify({"error": "Plugin system not initialized"}), 503

    loaded, errors = manager.reload()

    # Re-initialize ProviderManager with new plugins
    invalidate_manager()

    return jsonify({
        "loaded": loaded,
        "errors": errors,
    })


@bp.route("/plugins/<name>/config", methods=["GET"])
def get_plugin_config(name):
    """Get config for a specific plugin.

    Args:
        name: The plugin provider name.

    Returns:
        {"config": {...}} with the plugin's current config values.
    """
    from db.plugins import get_plugin_config as db_get_plugin_config
    from providers import _PROVIDER_CLASSES

    # Check if plugin exists
    cls = _PROVIDER_CLASSES.get(name)
    if not cls or not getattr(cls, "is_plugin", False):
        return jsonify({"error": f"Plugin '{name}' not found"}), 404

    config = db_get_plugin_config(name)
    config_fields = getattr(cls, "config_fields", [])

    return jsonify({
        "name": name,
        "config": config,
        "config_fields": config_fields,
    })


@bp.route("/plugins/<name>/config", methods=["PUT"])
def update_plugin_config(name):
    """Update config for a plugin.

    Accepts JSON body with key-value pairs. Each pair is stored
    in config_entries with namespaced keys.

    After updating, invalidates the ProviderManager so the plugin
    is re-initialized with the new config.

    Body: {"key1": "value1", "key2": "value2"}

    Returns:
        {"status": "updated", "keys": [...]}
    """
    from db.plugins import set_plugin_config
    from providers import _PROVIDER_CLASSES, invalidate_manager

    # Check if plugin exists
    cls = _PROVIDER_CLASSES.get(name)
    if not cls or not getattr(cls, "is_plugin", False):
        return jsonify({"error": f"Plugin '{name}' not found"}), 404

    data = request.get_json()
    if not data or not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400

    updated_keys = []
    for key, value in data.items():
        set_plugin_config(name, key, str(value))
        updated_keys.append(key)

    # Re-initialize providers with new config
    invalidate_manager()

    logger.info("Updated plugin config for '%s': %s", name, updated_keys)
    return jsonify({
        "status": "updated",
        "name": name,
        "keys": updated_keys,
    })
