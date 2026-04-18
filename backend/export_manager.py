"""Multi-format configuration and subtitle data export manager.

Exports Sublarr config and subtitle data in multiple formats:
- Bazarr-compatible config structure
- Plex subtitle manifest with naming validation
- Kodi subtitle manifest with naming validation
- Generic JSON full dump

Uses strategy pattern: main dispatcher routes to format-specific exporters.
Pure function module -- no Flask dependencies (uses lazy imports for DB access).

The per-format exporters and helpers live in ``export_formats.py``; this
module owns only the dispatcher API (``export_config`` + ``export_to_zip``)
and re-exports the format helpers for back-compat.
"""

import io
import json
import logging
import zipfile

from export_formats import (  # noqa: F401 — re-exported for back-compat
    _SUBTITLE_EXTENSIONS,
    _VIDEO_EXTENSIONS,
    _export_bazarr_format,
    _export_json_format,
    _export_kodi_format,
    _export_plex_format,
    _get_config_entries,
    _get_language_profiles,
    _get_media_path,
    _get_provider_stats_summary,
    _get_version,
    _mask_secret,
    _scan_subtitle_files,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Main dispatcher
# ---------------------------------------------------------------------------


def export_config(format: str, include_secrets: bool = False) -> dict:
    """Export Sublarr configuration in the specified format.

    Args:
        format: One of "bazarr", "plex", "kodi", "json".
        include_secrets: If True, include API keys/passwords unmasked.

    Returns:
        Dict with keys: format, data, filename, content_type, warnings.
    """
    exporters = {
        "bazarr": _export_bazarr_format,
        "plex": _export_plex_format,
        "kodi": _export_kodi_format,
        "json": _export_json_format,
    }

    exporter = exporters.get(format)
    if exporter is None:
        return {
            "format": format,
            "data": None,
            "filename": "",
            "content_type": "application/json",
            "warnings": [
                f"Unknown export format: {format}. Supported: {', '.join(sorted(exporters.keys()))}"
            ],
        }

    # _export_plex_format and _export_kodi_format don't take include_secrets
    if format in ("plex", "kodi"):
        return exporter()
    return exporter(include_secrets)


def export_to_zip(formats: list, include_secrets: bool = False) -> bytes:
    """Create a ZIP archive containing exports in all requested formats.

    Args:
        formats: List of format strings to include.
        include_secrets: If True, include API keys/passwords unmasked.

    Returns:
        Bytes of the ZIP file.
    """
    buffer = io.BytesIO()

    format_filenames = {
        "bazarr": "bazarr_export.json",
        "plex": "plex_manifest.json",
        "kodi": "kodi_manifest.json",
        "json": "sublarr_export.json",
    }

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for fmt in formats:
            result = export_config(fmt, include_secrets=include_secrets)
            if result.get("data") is not None:
                filename = format_filenames.get(fmt, f"{fmt}_export.json")
                content = json.dumps(result["data"], indent=2, default=str)
                zf.writestr(filename, content)

    return buffer.getvalue()
