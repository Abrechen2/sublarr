"""Onboarding routes — /onboarding/status, /onboarding/complete."""

import logging

from flask import jsonify

from routes.config import bp

logger = logging.getLogger(__name__)


@bp.route("/onboarding/status", methods=["GET"])
def onboarding_status():
    """Check if onboarding has been completed.
    ---
    get:
      tags:
        - Config
      summary: Get onboarding status
      description: Returns whether onboarding has been completed and which services are configured.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: Onboarding status
          content:
            application/json:
              schema:
                type: object
                properties:
                  completed:
                    type: boolean
                  has_sonarr:
                    type: boolean
                  has_radarr:
                    type: boolean
                  has_ollama:
                    type: boolean
                  has_providers:
                    type: boolean
    """
    from config import get_settings
    from db.config import get_config_entry

    settings = get_settings()
    completed = get_config_entry("onboarding_completed")
    return jsonify(
        {
            "completed": completed == "true",
            "has_sonarr": bool(settings.sonarr_url and settings.sonarr_api_key),
            "has_radarr": bool(settings.radarr_url and settings.radarr_api_key),
            "has_ollama": bool(settings.ollama_url),
            "has_providers": bool(
                settings.opensubtitles_api_key or settings.jimaku_api_key or settings.subdl_api_key
            ),
        }
    )


@bp.route("/onboarding/complete", methods=["POST"])
def onboarding_complete():
    """Mark onboarding as completed.
    ---
    post:
      tags:
        - Config
      summary: Complete onboarding
      description: Marks the onboarding wizard as completed so it will not show again.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: Onboarding marked complete
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
    """
    from db.config import get_config_entry, save_config_entry

    # Reject re-completion. Onboarding flips one-way; the wizard isn't meant
    # to fire its completion side-effects (config defaults, scheduler kick)
    # twice. Without this, anyone with valid auth can replay the call.
    if get_config_entry("onboarding_completed") == "true":
        return jsonify({"status": "already_completed"}), 200

    save_config_entry("onboarding_completed", "true")
    return jsonify({"status": "completed"})
