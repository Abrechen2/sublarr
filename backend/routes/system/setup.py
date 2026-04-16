"""First-run wizard endpoints — status + completion + reset.

Backs the Phase 2 frontend wizard that ships a scheduler profile on first
launch. Three endpoints:

- ``GET  /api/v1/system/setup/status``   — wizard flag + hardware benchmark
- ``POST /api/v1/system/setup/complete`` — apply chosen profile, persist flag
- ``POST /api/v1/system/setup/reset``    — clear the flag (QA / dev)
"""

from __future__ import annotations

import logging
import os

from flask import jsonify, request

from db.repositories import get_config_entry, save_config_entry
from routes.system import bp
from services.scheduler_profile import apply_profile, recommend_profile

logger = logging.getLogger(__name__)

try:
    import psutil

    _HAS_PSUTIL = True
except ImportError:  # pragma: no cover — psutil is a standard dependency
    _HAS_PSUTIL = False


def _detect_cpu_count() -> int:
    """Return the logical CPU count, falling back to 2 when undetectable."""
    return os.cpu_count() or 2


def _detect_ram_gb() -> float:
    """Return total RAM in GB (rounded to 1 decimal). Falls back to 2.0."""
    if not _HAS_PSUTIL:
        return 2.0
    try:
        return round(psutil.virtual_memory().total / (1024**3), 1)
    except Exception as e:  # noqa: BLE001
        logger.debug("RAM detection failed: %s", e)
        return 2.0


def _wizard_completed() -> bool:
    """Read the persisted flag, tolerating any string/bool representation."""
    raw = get_config_entry("setup_wizard_completed")
    if raw is None:
        return False
    return str(raw).strip().lower() in ("true", "1", "yes")


@bp.route("/system/setup/status", methods=["GET"])
def get_setup_status():
    """Return wizard-completion flag + hardware benchmark for profile recommendation.

    ---
    get:
      tags:
        - System
      summary: First-run wizard status + hardware detection
      description: >
        Reports whether the first-run wizard has been completed and returns a
        hardware benchmark (CPU/RAM) plus the profile that best matches the
        detected specs. The frontend uses this to show the wizard at most once
        and to pre-select a recommendation.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: Wizard status + recommended profile
    """
    cpu = _detect_cpu_count()
    ram = _detect_ram_gb()
    return jsonify(
        {
            "wizard_completed": _wizard_completed(),
            "benchmark": {
                "cpu_count": cpu,
                "ram_gb": ram,
                "recommended_profile": recommend_profile(cpu, ram),
            },
        }
    )


@bp.route("/system/setup/complete", methods=["POST"])
def complete_setup():
    """Apply the chosen profile and mark the wizard as completed.

    ---
    post:
      tags:
        - System
      summary: Apply chosen scheduler profile and mark wizard done
      description: >
        Persists every setting prescribed by the chosen profile, records the
        profile name itself, and sets setup_wizard_completed=true. Triggers a
        settings-cache reload so in-process readers see the new values
        immediately.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: Profile applied
        400:
          description: Unknown profile
    """
    data = request.get_json(silent=True) or {}
    profile = data.get("profile", "")
    try:
        settings_to_apply = apply_profile(profile)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    # Persist each setting the profile prescribes
    for key, value in settings_to_apply.items():
        save_config_entry(key, str(value))

    # Persist the profile name itself + the completion flag
    save_config_entry("scheduler_profile", profile)
    save_config_entry("setup_wizard_completed", "true")

    # Settings cache may need refresh so in-process readers see the new values
    try:
        from config import reload_settings

        reload_settings()
    except Exception as e:  # noqa: BLE001
        logger.debug("reload_settings after wizard completion failed: %s", e)

    return jsonify({"ok": True, "applied": settings_to_apply, "profile": profile})


@bp.route("/system/setup/reset", methods=["POST"])
def reset_setup():
    """Reset the wizard flag so it shows again on next session. Dev/QA only.

    ---
    post:
      tags:
        - System
      summary: Clear the wizard-completed flag (QA)
      description: >
        Clears setup_wizard_completed so the wizard is shown again. Intended
        for QA — no guard beyond the existing API-key auth middleware.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: Flag cleared
    """
    save_config_entry("setup_wizard_completed", "false")
    return jsonify({"ok": True})
