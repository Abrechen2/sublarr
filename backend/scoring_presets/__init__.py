"""Bundled scoring presets for TRaSH-compatible import.

Presets define scoring weight overrides and optional provider modifiers.
Schema:
  {
    "name": str,
    "description": str,
    "type": "episode" | "movie" | "both",
    "weights": {
      "episode"?: {weight_key: int, ...},
      "movie"?: {weight_key: int, ...}
    },
    "provider_modifiers": {provider_name: int, ...}
  }
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_PRESETS_DIR = Path(__file__).parent

_VALID_WEIGHT_KEYS = {
    "hash",
    "series",
    "year",
    "season",
    "episode",
    "release_group",
    "source",
    "audio_codec",
    "resolution",
    "hearing_impaired",
    "title",
    "format_bonus",
}


def load_bundled_presets() -> list[dict]:
    """Load all bundled preset JSON files. Returns metadata only (no full weights)."""
    presets = []
    for path in sorted(_PRESETS_DIR.glob("*.json")):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if validate_preset(data):
                presets.append(
                    {
                        "name": data["name"],
                        "description": data.get("description", ""),
                        "type": data.get("type", "both"),
                    }
                )
        except Exception as exc:
            logger.warning("Failed to load preset %s: %s", path.name, exc)
    return presets


def get_bundled_preset(name: str) -> dict | None:
    """Get a full bundled preset by name. Returns None if not found."""
    for path in _PRESETS_DIR.glob("*.json"):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if data.get("name") == name and validate_preset(data):
                return data
        except Exception:
            continue
    return None


def validate_preset(data: dict) -> bool:
    """Validate preset structure. Returns True if valid."""
    if not isinstance(data, dict):
        return False
    if not data.get("name") or not isinstance(data["name"], str):
        return False
    weights = data.get("weights", {})
    if not isinstance(weights, dict):
        return False
    for score_type, w in weights.items():
        if score_type not in ("episode", "movie"):
            return False
        if not isinstance(w, dict):
            return False
        for key, val in w.items():
            if key not in _VALID_WEIGHT_KEYS:
                return False
            if not isinstance(val, int):
                return False
    modifiers = data.get("provider_modifiers", {})
    if not isinstance(modifiers, dict):
        return False
    for name, val in modifiers.items():
        if not isinstance(name, str) or not isinstance(val, int):
            return False
    return True
