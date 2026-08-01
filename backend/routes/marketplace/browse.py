"""Marketplace read-side routes — list, get, installed, refresh, updates."""

import logging

from flask import jsonify, request

from config import get_settings
from routes.marketplace import bp, get_marketplace

logger = logging.getLogger(__name__)


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
        # Registry not available (e.g. URL does not exist yet) — return empty list
        logger.warning("Marketplace registry unavailable: %s", e)
        return jsonify({"plugins": [], "registry_unavailable": True}), 200


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
    except Exception:
        logger.exception("Failed to get plugin info")
        return jsonify({"error": "Internal server error"}), 500


@bp.route("/marketplace/installed", methods=["GET"])
def get_installed_plugins():
    """List installed plugins from the local database.
    ---
    get:
      tags:
        - Marketplace
      summary: List installed plugins
      description: Returns all locally installed plugins from the installed_plugins DB table.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: Installed plugin list
          content:
            application/json:
              schema:
                type: object
                properties:
                  installed:
                    type: array
                    items:
                      type: object
    """
    import json

    from db.models.plugins import InstalledPlugin

    rows = InstalledPlugin.query.order_by(InstalledPlugin.name).all()
    installed = []
    for row in rows:
        installed.append(
            {
                "name": row.name,
                "display_name": row.display_name,
                "version": row.version,
                "capabilities": json.loads(row.capabilities or "[]"),
                "enabled": bool(row.enabled),
                "installed_at": row.installed_at,
            }
        )
    return jsonify({"installed": installed})


@bp.route("/marketplace/refresh", methods=["POST"])
def refresh_marketplace():
    """Force-refresh the marketplace cache from GitHub.
    ---
    post:
      tags:
        - Marketplace
      summary: Refresh marketplace cache
      description: Force-fetches the latest plugin list from GitHub, bypassing the 1h cache TTL.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: Refreshed plugin list
        500:
          description: GitHub fetch error
    """
    try:
        from services.github_registry import GitHubRegistry

        github_token = getattr(get_settings(), "github_token", "")
        registry = GitHubRegistry(github_token=github_token)
        plugins = registry.search(force_refresh=True)
        return jsonify({"plugins": plugins, "count": len(plugins)})
    except Exception:
        logger.exception("Failed to refresh marketplace from GitHub")
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
    except Exception as exc:
        # An unreachable registry is an expected offline state, not a server
        # fault: browse_plugins() already degrades to an empty list plus a
        # warning for the same failure. 500ing here made the plugin page error
        # out whenever the community registry was down or unpublished.
        logger.warning("Marketplace update check unavailable: %s", exc)
        return jsonify({"updates": {}, "registry_available": False}), 200
