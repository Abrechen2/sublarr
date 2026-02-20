"""Plugin marketplace routes — /marketplace/plugins, /marketplace/install."""

import logging

from flask import Blueprint, request, jsonify

from config import get_settings
from services.marketplace import PluginMarketplace

bp = Blueprint("marketplace", __name__, url_prefix="/api/v1")
logger = logging.getLogger(__name__)

# Singleton marketplace instance
_marketplace: PluginMarketplace | None = None


def get_marketplace() -> PluginMarketplace:
    """Get or create marketplace instance."""
    global _marketplace
    if _marketplace is None:
        settings = get_settings()
        registry_url = getattr(settings, "plugin_registry_url", None)
        if registry_url:
            _marketplace = PluginMarketplace(registry_url)
        else:
            _marketplace = PluginMarketplace()  # Use default registry
    return _marketplace


@bp.route("/marketplace/plugins", methods=["GET"])
def list_marketplace_plugins():
    """List available plugins from marketplace.
    ---
    get:
      tags:
        - Marketplace
      summary: List plugins
      description: Returns list of available plugins from the marketplace registry.
      security:
        - apiKeyAuth: []
      parameters:
        - in: query
          name: category
          schema:
            type: string
          description: Filter by category (provider, translation, tool)
      responses:
        200:
          description: Plugin list
          content:
            application/json:
              schema:
                type: object
                properties:
                  plugins:
                    type: array
                    items:
                      type: object
        500:
          description: Registry fetch error
    """
    try:
        marketplace = get_marketplace()
        category = request.args.get("category")
        plugins = marketplace.list_plugins(category=category)

        return jsonify({"plugins": plugins}), 200
    except Exception as e:
        logger.exception("Failed to list marketplace plugins")
        return jsonify({"error": str(e)}), 500


@bp.route("/marketplace/plugins/<plugin_name>", methods=["GET"])
def get_marketplace_plugin(plugin_name: str):
    """Get detailed information about a plugin.
    ---
    get:
      tags:
        - Marketplace
      summary: Get plugin info
      description: Returns detailed information about a specific plugin.
      security:
        - apiKeyAuth: []
      parameters:
        - in: path
          name: plugin_name
          required: true
          schema:
            type: string
      responses:
        200:
          description: Plugin information
        404:
          description: Plugin not found
        500:
          description: Registry fetch error
    """
    try:
        marketplace = get_marketplace()
        plugin_info = marketplace.get_plugin_info(plugin_name)

        if not plugin_info:
            return jsonify({"error": "Plugin not found"}), 404

        return jsonify(plugin_info), 200
    except Exception as e:
        logger.exception("Failed to get plugin info")
        return jsonify({"error": str(e)}), 500


@bp.route("/marketplace/install", methods=["POST"])
def install_marketplace_plugin():
    """Install a plugin from the marketplace.
    ---
    post:
      tags:
        - Marketplace
      summary: Install plugin
      description: Installs a plugin from the marketplace to the plugins directory.
      security:
        - apiKeyAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                plugin_name:
                  type: string
                version:
                  type: string
      responses:
        200:
          description: Installation successful
        400:
          description: Invalid request
        500:
          description: Installation error
    """
    data = request.get_json(silent=True) or {}
    plugin_name = data.get("plugin_name")

    if not plugin_name:
        return jsonify({"error": "plugin_name is required"}), 400

    try:
        settings = get_settings()
        plugins_dir = getattr(settings, "plugins_dir", "/config/plugins")

        marketplace = get_marketplace()
        version = data.get("version")
        result = marketplace.install_plugin(plugin_name, plugins_dir, version)

        return jsonify(result), 200
    except RuntimeError as e:
        logger.error("Plugin installation failed: %s", e)
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        logger.exception("Unexpected error during plugin installation")
        return jsonify({"error": "Internal server error"}), 500


@bp.route("/marketplace/uninstall", methods=["POST"])
def uninstall_marketplace_plugin():
    """Uninstall a plugin.
    ---
    post:
      tags:
        - Marketplace
      summary: Uninstall plugin
      description: Uninstalls a plugin from the plugins directory.
      security:
        - apiKeyAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                plugin_name:
                  type: string
      responses:
        200:
          description: Uninstallation successful
        400:
          description: Invalid request
        500:
          description: Uninstallation error
    """
    data = request.get_json(silent=True) or {}
    plugin_name = data.get("plugin_name")

    if not plugin_name:
        return jsonify({"error": "plugin_name is required"}), 400

    try:
        settings = get_settings()
        plugins_dir = getattr(settings, "plugins_dir", "/config/plugins")

        marketplace = get_marketplace()
        result = marketplace.uninstall_plugin(plugin_name, plugins_dir)

        return jsonify(result), 200
    except RuntimeError as e:
        logger.error("Plugin uninstallation failed: %s", e)
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        logger.exception("Unexpected error during plugin uninstallation")
        return jsonify({"error": "Internal server error"}), 500


@bp.route("/marketplace/updates", methods=["GET"])
def check_marketplace_updates():
    """Check for plugin updates.
    ---
    get:
      tags:
        - Marketplace
      summary: Check updates
      description: Checks for available updates for installed plugins.
      security:
        - apiKeyAuth: []
      parameters:
        - in: query
          name: installed
          schema:
            type: array
            items:
              type: string
          description: List of installed plugin names
      responses:
        200:
          description: Update information
        500:
          description: Registry fetch error
    """
    try:
        marketplace = get_marketplace()
        installed = request.args.getlist("installed")

        updates = marketplace.check_updates(installed)

        return jsonify({"updates": updates}), 200
    except Exception as e:
        logger.exception("Failed to check updates")
        return jsonify({"error": str(e)}), 500
