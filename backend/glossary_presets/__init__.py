"""Bundled glossary suggestions the user can import into the global glossary.

Schema:
  {
    "id": str,
    "name": str,
    "description": str,
    "source_language": str,
    "target_language": str,
    "entries": [{"source_term": str, "target_term": str}, ...]
  }

Nothing here is applied on its own: a preset reaches a prompt only after the
user imports it (services.glossary_presets_service).
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_PRESETS_DIR = Path(__file__).parent


def load_bundled_presets() -> list[dict]:
    """All bundled presets, ordered by id. A file that does not parse is skipped and logged."""
    presets = []
    for path in sorted(_PRESETS_DIR.glob("*.json")):
        try:
            presets.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError) as exc:
            logger.warning("Skipping glossary preset %s: %s", path.name, exc)
    return presets


def get_bundled_preset(preset_id: str) -> dict | None:
    """The preset with ``preset_id``, or None."""
    return next((p for p in load_bundled_presets() if p.get("id") == preset_id), None)
