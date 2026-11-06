"""Marketplace write-side routes — install, uninstall."""

import logging

from flask import jsonify, request

from config import get_settings
from routes.marketplace import bp, get_marketplace

logger = logging.getLogger(__name__)

_SESSION_REQUIRED = {
    "error": "Installing or removing plugins needs a signed-in UI session; "
    "the API key alone is not enough.",
    "session_required": True,
}


def _registry_entry(name: str) -> dict | None:
    """The indexed plugin ``name`` — its URL and hash, never the caller's (#71)."""
    from db.models.plugins import MarketplaceCache
    from extensions import db as sa_db

    row = sa_db.session.get(MarketplaceCache, name)
    if row is not None:
        return {
            "zip_url": row.zip_url,
            "sha256": row.sha256,
            "version": row.version,
            "display_name": row.display_name,
        }
    try:
        info = get_marketplace().get_plugin_info(name)
    except RuntimeError as e:
        logger.warning("Plugin registry unavailable while resolving %s: %s", name, e)
        return None
    if not info:
        return None
    return {
        "zip_url": info.get("zip_url", ""),
        "sha256": info.get("sha256", ""),
        "version": info.get("version", "0.0.0"),
        "display_name": info.get("display_name", name),
    }


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

    import ui_auth
    from db.models.plugins import InstalledPlugin
    from extensions import db as sa_db
    from providers import invalidate_manager
    from providers.plugins import get_plugin_manager
    from services.marketplace import PluginMarketplace, is_valid_plugin_name

    if not ui_auth.request_has_admin_presence():
        return jsonify(_SESSION_REQUIRED), 403

    data = request.get_json(silent=True) or {}
    name = data.get("plugin_name") or data.get("name")
    if not is_valid_plugin_name(name):
        return jsonify({"error": "A valid name (or plugin_name) is required"}), 400

    # URL and hash come from the plugin index. A caller who sends their own
    # must send the indexed ones: a mismatch means the index changed since
    # the page loaded, or someone tries another download.
    entry = _registry_entry(name)
    if entry is None:
        return jsonify({"error": f"Plugin {name!r} is not in the plugin index"}), 404
    zip_url, sha256 = entry["zip_url"], entry["sha256"]
    if not zip_url or not sha256:
        return jsonify({"error": "The plugin index has no download or hash for it"}), 409
    for field, indexed in (("zip_url", zip_url), ("sha256", sha256)):
        sent = data.get(field)
        if sent and str(sent).lower() != indexed.lower():
            logger.warning("Plugin install of %s refused: %s differs from the index", name, field)
            return jsonify(
                {"error": f"{field} does not match the plugin index; reload the list"}
            ), 409

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
            existing.version = entry["version"] or existing.version
            existing.plugin_dir = result["path"]
            existing.sha256 = sha256
            existing.capabilities = capabilities
            existing.installed_at = now
        else:
            sa_db.session.add(
                InstalledPlugin(
                    name=name,
                    display_name=entry["display_name"] or name,
                    version=entry["version"] or "0.0.0",
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
        logger.exception("Plugin install failed: %s", e)
        return jsonify({"error": "Internal server error"}), 500
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
    import ui_auth
    from db.models.plugins import InstalledPlugin
    from extensions import db as sa_db
    from providers import invalidate_manager
    from providers.plugins import get_plugin_manager
    from services.marketplace import is_valid_plugin_name

    if not ui_auth.request_has_admin_presence():
        return jsonify(_SESSION_REQUIRED), 403

    data = request.get_json(silent=True) or {}
    plugin_name = data.get("plugin_name")
    if not is_valid_plugin_name(plugin_name):
        return jsonify({"error": "A valid plugin_name is required"}), 400

    try:
        settings = get_settings()
        plugins_dir = getattr(settings, "plugins_dir", "/config/plugins")

        marketplace = get_marketplace()
        result = marketplace.uninstall_plugin(plugin_name, plugins_dir)

        # Symmetry with install: drop the InstalledPlugin DB row and
        # hot-reload so the manager forgets the now-missing module.
        # Pre-fix: install persisted + reloaded but uninstall did neither —
        # GET /marketplace/installed kept showing the ghost row, and the
        # provider stayed live in memory until a server restart.
        InstalledPlugin.query.filter_by(name=plugin_name).delete()
        sa_db.session.commit()

        manager = get_plugin_manager()
        if manager:
            manager.reload()
            invalidate_manager()

        return jsonify(result), 200
    except RuntimeError as e:
        logger.exception("Plugin uninstallation failed: %s", e)
        return jsonify({"error": "Internal server error"}), 500
    except Exception:
        logger.exception("Unexpected error during plugin uninstallation")
        return jsonify({"error": "Internal server error"}), 500
