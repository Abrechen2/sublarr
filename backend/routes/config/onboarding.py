"""Onboarding routes — /onboarding/status, /onboarding/complete."""

import logging

from flask import jsonify

from routes.config import bp

logger = logging.getLogger(__name__)


def _enabled_provider_names() -> list[str]:
    """Providers this install actually has, by the same rule the provider list uses.

    ``providers_enabled`` is an allow-list, and an EMPTY value means "every
    registered provider is enabled" — the default for most installs. Asking
    the manager keeps this answer identical to /api/v1/providers instead of
    testing three hardcoded API-key fields, which reported ``has_providers:
    false`` on an install running happily on customapi (forgejo #14).

    Failure to build the manager is reported as "no providers" rather than
    raised: the status endpoint's job is to describe the install, not to fail
    with it.
    """
    try:
        from providers import get_provider_manager

        return [p["name"] for p in get_provider_manager().get_provider_status() if p.get("enabled")]
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("onboarding status could not read the provider list: %s", exc)
        return []


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
            "has_providers": bool(_enabled_provider_names()),
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
    # Onboarding is the superset of the first-run modal, so finishing it leaves
    # that modal nothing to ask. The UI path happens to call
    # /system/setup/complete on its own; a caller provisioning through the API
    # did not, and got the setup dialog thrown back at a finished install
    # (forgejo #14). Only the flag is set here -- the performance profile stays
    # whatever it is, since nobody chose one.
    save_config_entry("setup_wizard_completed", "true")
    return jsonify({"status": "completed"})
