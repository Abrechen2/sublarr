"""Webhook secret routes (#71).

Routes:
  GET  /api/v1/system/webhook-secret             — the secret, for the arr settings
  POST /api/v1/system/webhook-secret/regenerate  — replace it
"""

from __future__ import annotations

import logging
import secrets

from flask import jsonify

from routes.system import bp

logger = logging.getLogger(__name__)


@bp.route("/system/webhook-secret", methods=["GET"])
def get_webhook_secret():
    """Return the secret Sonarr, Radarr and Jellyfin send as X-Api-Key.
    ---
    get:
      tags:
        - System
      summary: Get webhook secret
      description: The secret that authenticates /api/v1/webhook/* and nothing else.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: Webhook secret
    """
    from config import get_settings

    s = get_settings()
    return jsonify(
        {
            "webhook_secret": getattr(s, "webhook_secret", "") or "",
            "legacy_auth": bool(getattr(s, "webhook_legacy_auth", True)),
        }
    )


@bp.route("/system/webhook-secret/regenerate", methods=["POST"])
def regenerate_webhook_secret():
    """Replace the webhook secret; connections using the old one stop working.
    ---
    post:
      tags:
        - System
      summary: Regenerate webhook secret
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: The new webhook secret
    """
    from config import reload_settings
    from db.config import get_all_config_entries, save_config_entry

    new_secret = secrets.token_hex(32)
    save_config_entry("webhook_secret", new_secret)
    reload_settings(get_all_config_entries())
    logger.info("Webhook secret regenerated")
    return jsonify({"webhook_secret": new_secret})
