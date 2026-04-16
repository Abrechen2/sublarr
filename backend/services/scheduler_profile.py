"""Scheduler profile presets — map a profile name to concrete setting values.

Used by the first-run wizard and the settings page to apply a bundle of
values (max items per run, budget safety margin) in one action. See the
Phase 2 plan for rationale and targeted hardware per profile.
"""

from __future__ import annotations

from typing import Any

PROFILES: dict[str, dict[str, Any]] = {
    "light": {
        "wanted_search_max_items_per_run": 100,
        "provider_budget_safety_margin_pct": 40,
    },
    "balanced": {
        "wanted_search_max_items_per_run": 500,
        "provider_budget_safety_margin_pct": 20,
    },
    "aggressive": {
        "wanted_search_max_items_per_run": 2000,
        "provider_budget_safety_margin_pct": 10,
    },
    "custom": {},
}


def apply_profile(profile: str) -> dict[str, Any]:
    """Return the settings dict that the named profile would apply.

    'custom' returns an empty dict — the caller must preserve existing values.
    Unknown profile names raise ``ValueError``.
    """
    if profile not in PROFILES:
        raise ValueError(
            f"unknown scheduler profile: {profile!r}. valid: {sorted(PROFILES.keys())}"
        )
    # Return a copy so callers can't accidentally mutate the preset table
    return dict(PROFILES[profile])


def recommend_profile(cpu_count: int, ram_gb: int | float) -> str:
    """Suggest a profile based on detected hardware.

    Rule table (evaluated top-down):
    - cpu_count <= 2 or ram_gb <= 2 -> 'light'
    - cpu_count >= 8 and ram_gb >= 8 -> 'aggressive'
    - otherwise -> 'balanced'

    'custom' is never auto-recommended — the user has to opt in.
    """
    if cpu_count <= 2 or ram_gb <= 2:
        return "light"
    if cpu_count >= 8 and ram_gb >= 8:
        return "aggressive"
    return "balanced"
