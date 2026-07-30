"""Global release-group tier ranking for subtitle result scoring.

Stores an ordered list of release/fansub group names plus a per-tier step
weight as a JSON config entry (``release_group_tiers_json``). Higher-ranked
groups (lower list index) receive a larger score bonus during wanted-search
scoring: position ``i`` in a list of ``N`` groups earns ``step * (N - i)``
points, so the top group gets ``N * step`` and the last group gets ``step``.

Per-series fansub preferences (``fansub_preferences`` table) stack on top of
the global tiers; an excluded group's -999 always dominates any tier bonus.
"""

import json
import logging

logger = logging.getLogger(__name__)

CONFIG_KEY = "release_group_tiers_json"

DEFAULT_STEP = 10
MAX_TIERS = 100
MAX_GROUP_NAME_LEN = 100
MIN_STEP = 1
MAX_STEP = 500


def _sanitize_tiers(tiers: list) -> list[str]:
    """Strip entries, drop empties, and dedupe case-insensitively (keep order).

    An empty string would substring-match every release_info and grant the
    top-tier bonus to all results — same guard as fansub preferences.
    """
    seen: set[str] = set()
    clean: list[str] = []
    for entry in tiers:
        if not isinstance(entry, str):
            continue
        name = entry.strip()
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        clean.append(name)
    return clean


def get_tier_config() -> dict:
    """Return ``{"tiers": [group, ...], "step": int}`` (defaults if unset/corrupt)."""
    from db.config import get_config_entry

    raw = None
    try:
        raw = get_config_entry(CONFIG_KEY)
    except Exception:
        logger.debug("get_tier_config: config read failed", exc_info=True)
    if not raw:
        return {"tiers": [], "step": DEFAULT_STEP}
    try:
        data = json.loads(raw)
        tiers = _sanitize_tiers(data.get("tiers", []))[:MAX_TIERS]
        step = int(data.get("step", DEFAULT_STEP))
        step = max(MIN_STEP, min(MAX_STEP, step))
        return {"tiers": tiers, "step": step}
    except (ValueError, TypeError, AttributeError):
        logger.warning("Corrupt %s config entry ignored", CONFIG_KEY)
        return {"tiers": [], "step": DEFAULT_STEP}


def set_tier_config(tiers: list, step: int) -> dict:
    """Validate and persist the tier list. Returns the stored config.

    Raises ``ValueError`` on invalid input (non-string entries, too many
    tiers, over-long names, step out of range).
    """
    if not isinstance(tiers, list) or not all(isinstance(g, str) for g in tiers):
        raise ValueError("tiers must be a list of strings")
    if not isinstance(step, int) or isinstance(step, bool):
        raise ValueError("step must be an integer")
    if not (MIN_STEP <= step <= MAX_STEP):
        raise ValueError(f"step must be between {MIN_STEP} and {MAX_STEP}")

    clean = _sanitize_tiers(tiers)
    if len(clean) > MAX_TIERS:
        raise ValueError(f"at most {MAX_TIERS} tiers allowed")
    for name in clean:
        if len(name) > MAX_GROUP_NAME_LEN:
            raise ValueError(f"group name too long (max {MAX_GROUP_NAME_LEN} chars): {name[:40]}")

    from db.config import save_config_entry

    config = {"tiers": clean, "step": step}
    save_config_entry(CONFIG_KEY, json.dumps(config))
    return config
