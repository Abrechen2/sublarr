"""The opt-in switch for Sublarr's automatic subtitle repairs.

Gates the timing check on downloads (subtitle_timing), signs/credits-only
sidecars counting as missing (suspect_sidecars) and the health sweep's timing
repairs. Off unless the user enables ``auto_repair_enabled``.
"""

from __future__ import annotations


def auto_repair_enabled() -> bool:
    """True when the user enabled automatic repairs. Never raises."""
    try:
        from config import get_settings

        return bool(getattr(get_settings(), "auto_repair_enabled", False))
    except Exception:  # noqa: BLE001 — no settings means no repairs
        return False
