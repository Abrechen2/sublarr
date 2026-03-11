"""Plugin marketplace routes — /marketplace/plugins, /marketplace/install."""

import logging

from flask import Blueprint, jsonify, request

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
        installed.append({
            "name": row.name,
            "display_name": row.display_name,
            "version": row.version,
            "capabilities": json.loads(row.capabilities or "[]"),
            "enabled": bool(row.enabled),
            "installed_at": row.installed_at,
        })
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
    except Exception as e:
        logger.exception("Failed to refresh marketplace from GitHub")
        return jsonify({"error": str(e)}), 500


@bp.route("/marketplace/install", methods=["POST"])
def install_marketplace_plugin():
    """Install a plugin from the marketplace.
    ---
    post:
      tags:
        - Marketplace
      summary: Install plugin
      description: Downloads a plugin ZIP, verifies its SHA256, extracts it, persists the
        record to installed_plugins, and hot-reloads the plugin manager.
      security:
        - apiKeyAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required:
                - name
                - zip_url
              properties:
                name:
                  type: string
                plugin_name:
                  type: string
                  description: Alias for name (either field is accepted)
                zip_url:
                  type: string
                sha256:
                  type: string
                version:
                  type: string
                display_name:
                  type: string
                capabilities:
                  type: array
                  items:
                    type: string
      responses:
        200:
          description: Installation successful
        400:
          description: Invalid request — name/zip_url missing
        500:
          description: Installation error (download failed, SHA256 mismatch, etc.)
    """
    import json
    from datetime import UTC, datetime

    from db.models.plugins import InstalledPlugin
    from extensions import db as sa_db
    from providers import invalidate_manager
    from providers.plugins import get_plugin_manager
    from services.marketplace import PluginMarketplace

    data = request.get_json(silent=True) or {}
    name = data.get("plugin_name") or data.get("name")
    zip_url = data.get("zip_url")
    sha256 = data.get("sha256", "")

    if not name or not zip_url:
        return jsonify({"error": "name (or plugin_name) and zip_url are required"}), 400

    try:
        plugins_dir = getattr(get_settings(), "plugins_dir", "/config/plugins")
        marketplace = PluginMarketplace()
        result = marketplace.install_plugin_from_zip(
            plugin_name=name,
            zip_url=zip_url,
            expected_sha256=sha256,
            plugins_dir=plugins_dir,
        )

        # Persist to installed_plugins
        now = datetime.now(UTC).isoformat()
        capabilities = json.dumps(data.get("capabilities", []))
        existing = InstalledPlugin.query.get(name)
        if existing:
            existing.version = data.get("version", existing.version)
            existing.plugin_dir = result["path"]
            existing.sha256 = sha256
            existing.capabilities = capabilities
            existing.installed_at = now
        else:
            sa_db.session.add(InstalledPlugin(
                name=name,
                display_name=data.get("display_name", name),
                version=data.get("version", "0.0.0"),
                plugin_dir=result["path"],
                sha256=sha256,
                capabilities=capabilities,
                enabled=1,
                installed_at=now,
            ))
        sa_db.session.commit()

        # Hot-reload plugins
        manager = get_plugin_manager()
        if manager:
            manager.reload()
            invalidate_manager()

        return jsonify({"status": "installed", "name": name})
    except RuntimeError as e:
        logger.error("Plugin install failed: %s", e)
        return jsonify({"error": str(e)}), 500
    except Exception:
        logger.exception("Plugin install unexpected error")
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
    except Exception:
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
