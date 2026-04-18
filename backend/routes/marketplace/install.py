"""Marketplace write-side routes — install, uninstall."""

import logging

from flask import jsonify, request

from config import get_settings
from routes.marketplace import bp, get_marketplace

logger = logging.getLogger(__name__)


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

    if not sha256:
        return jsonify({"error": "sha256 is required for plugin installation"}), 400

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
        now = datetime.now(UTC)
        capabilities = json.dumps(data.get("capabilities", []))
        existing = InstalledPlugin.query.get(name)
        if existing:
            existing.version = data.get("version", existing.version)
            existing.plugin_dir = result["path"]
            existing.sha256 = sha256
            existing.capabilities = capabilities
            existing.installed_at = now
        else:
            sa_db.session.add(
                InstalledPlugin(
                    name=name,
                    display_name=data.get("display_name", name),
                    version=data.get("version", "0.0.0"),
                    plugin_dir=result["path"],
                    sha256=sha256,
                    capabilities=capabilities,
                    enabled=1,
                    installed_at=now,
                )
            )
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
