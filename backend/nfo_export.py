"""NFO sidecar export — writes Kodi/Jellyfin-compatible XML metadata alongside subtitle files.

This is an expert feature disabled by default (auto_nfo_export = false).
"""

import logging
import xml.etree.ElementTree as ET
from datetime import datetime

logger = logging.getLogger(__name__)

_FIELDS = [
    "provider",
    "source_language",
    "target_language",
    "score",
    "translation_backend",
    "bleu_score",
    "downloaded_at",
    "sublarr_version",
]


def _is_enabled() -> bool:
    try:
        from config import get_settings

        return bool(getattr(get_settings(), "auto_nfo_export", False))
    except Exception:
        return False


def _get_version() -> str:
    try:
        from version import __version__

        return __version__
    except Exception:
        return ""


def write_nfo(subtitle_path: str, metadata: dict) -> None:
    """Write an NFO XML sidecar to ``{subtitle_path}.nfo``.

    Errors are logged and swallowed — NFO writing must never interrupt the
    subtitle pipeline.
    """
    nfo_path = subtitle_path + ".nfo"
    try:
        root = ET.Element("subtitle")
        meta = dict(metadata)
        meta.setdefault("sublarr_version", _get_version())
        meta.setdefault("downloaded_at", datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"))
        for field in _FIELDS:
            val = meta.get(field)
            ET.SubElement(root, field).text = "" if val is None else str(val)
        tree = ET.ElementTree(root)
        ET.indent(tree, space="  ")
        with open(nfo_path, "wb") as f:
            tree.write(f, xml_declaration=True, encoding="utf-8")
        logger.debug("Wrote NFO sidecar: %s", nfo_path)
    except Exception as exc:
        logger.warning("Failed to write NFO sidecar %s: %s", nfo_path, exc)


def maybe_write_nfo(subtitle_path: str, metadata: dict) -> None:
    """Write NFO only when auto_nfo_export is enabled in settings."""
    if not _is_enabled():
        return
    write_nfo(subtitle_path, metadata)
