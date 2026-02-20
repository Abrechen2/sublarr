"""Multi-format configuration and subtitle data export manager.

Exports Sublarr config and subtitle data in multiple formats:
- Bazarr-compatible config structure
- Plex subtitle manifest with naming validation
- Kodi subtitle manifest with naming validation
- Generic JSON full dump

Uses strategy pattern: main dispatcher routes to format-specific exporters.
Pure function module -- no Flask dependencies (uses lazy imports for DB access).
"""

import io
import json
import logging
import os
import zipfile
from typing import Optional

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
            "warnings": [f"Unknown export format: {format}. Supported: {', '.join(sorted(exporters.keys()))}"],
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


# ---------------------------------------------------------------------------
# Format-specific exporters
# ---------------------------------------------------------------------------

def _export_bazarr_format(include_secrets: bool = False) -> dict:
    """Export config in Bazarr-compatible structure.

    Maps Sublarr config keys to Bazarr section structure.
    Labeled as 'Bazarr-compatible' -- not guaranteed exact match.

    Args:
        include_secrets: If True, include API keys unmasked.

    Returns:
        Export result dict.
    """
    warnings = []
    config = _get_config_entries(warnings)

    sonarr_url = config.get("sonarr_url", "")
    sonarr_api_key = config.get("sonarr_api_key", "")
    radarr_url = config.get("radarr_url", "")
    radarr_api_key = config.get("radarr_api_key", "")

    if not include_secrets:
        sonarr_api_key = _mask_secret(sonarr_api_key)
        radarr_api_key = _mask_secret(radarr_api_key)

    data = {
        "_metadata": {
            "format": "bazarr-compatible",
            "source": "Sublarr",
            "version": _get_version(),
            "note": "Bazarr-compatible export. Not guaranteed to match current Bazarr config format exactly.",
        },
        "sonarr": {
            "ip": sonarr_url,
            "apikey": sonarr_api_key,
        },
        "radarr": {
            "ip": radarr_url,
            "apikey": radarr_api_key,
        },
        "general": {
            "serie_default_language": config.get("source_language", "en"),
            "target_language": config.get("target_language", "de"),
        },
    }

    # Add OpenSubtitles credentials if present
    os_api_key = config.get("opensubtitles_api_key", "")
    os_username = config.get("opensubtitles_username", "")
    if os_api_key or os_username:
        data["opensubtitlescom"] = {
            "apikey": _mask_secret(os_api_key) if not include_secrets else os_api_key,
            "username": os_username,
        }

    return {
        "format": "bazarr",
        "data": data,
        "filename": "bazarr_export.json",
        "content_type": "application/json",
        "warnings": warnings,
    }


def _export_plex_format() -> dict:
    """Export Plex subtitle manifest with naming validation.

    Walks media_path, finds subtitle files, runs Plex compatibility check on each.

    Returns:
        Export result dict with subtitle listing and validation results.
    """
    from compat_checker import check_plex_compatibility

    warnings = []
    media_path = _get_media_path(warnings)

    subtitles = _scan_subtitle_files(media_path, warnings)

    plex_subtitles = []
    for sub_info in subtitles:
        sub_path = sub_info["path"]
        video_path = sub_info.get("video_path", "")

        if video_path:
            compat = check_plex_compatibility(sub_path, video_path)
            plex_subtitles.append({
                "path": sub_path,
                "language": sub_info.get("language", ""),
                "format": sub_info.get("format", ""),
                "plex_compatible": compat["compatible"],
                "issues": compat["issues"],
            })
        else:
            plex_subtitles.append({
                "path": sub_path,
                "language": sub_info.get("language", ""),
                "format": sub_info.get("format", ""),
                "plex_compatible": None,
                "issues": ["No associated video file found"],
            })

    data = {
        "media_path": media_path,
        "subtitles": plex_subtitles,
        "summary": {
            "total": len(plex_subtitles),
            "compatible": sum(1 for s in plex_subtitles if s["plex_compatible"] is True),
            "incompatible": sum(1 for s in plex_subtitles if s["plex_compatible"] is False),
            "unknown": sum(1 for s in plex_subtitles if s["plex_compatible"] is None),
        },
    }

    return {
        "format": "plex",
        "data": data,
        "filename": "plex_manifest.json",
        "content_type": "application/json",
        "warnings": warnings,
    }


def _export_kodi_format() -> dict:
    """Export Kodi subtitle manifest with naming validation.

    Same as Plex but using Kodi compatibility checker.

    Returns:
        Export result dict with subtitle listing and validation results.
    """
    from compat_checker import check_kodi_compatibility

    warnings = []
    media_path = _get_media_path(warnings)

    subtitles = _scan_subtitle_files(media_path, warnings)

    kodi_subtitles = []
    for sub_info in subtitles:
        sub_path = sub_info["path"]
        video_path = sub_info.get("video_path", "")

        if video_path:
            compat = check_kodi_compatibility(sub_path, video_path)
            kodi_subtitles.append({
                "path": sub_path,
                "language": sub_info.get("language", ""),
                "format": sub_info.get("format", ""),
                "kodi_compatible": compat["compatible"],
                "issues": compat["issues"],
            })
        else:
            kodi_subtitles.append({
                "path": sub_path,
                "language": sub_info.get("language", ""),
                "format": sub_info.get("format", ""),
                "kodi_compatible": None,
                "issues": ["No associated video file found"],
            })

    data = {
        "media_path": media_path,
        "subtitles": kodi_subtitles,
        "summary": {
            "total": len(kodi_subtitles),
            "compatible": sum(1 for s in kodi_subtitles if s["kodi_compatible"] is True),
            "incompatible": sum(1 for s in kodi_subtitles if s["kodi_compatible"] is False),
            "unknown": sum(1 for s in kodi_subtitles if s["kodi_compatible"] is None),
        },
    }

    return {
        "format": "kodi",
        "data": data,
        "filename": "kodi_manifest.json",
        "content_type": "application/json",
        "warnings": warnings,
    }


def _export_json_format(include_secrets: bool = False) -> dict:
    """Export full Sublarr config dump as generic JSON.

    Includes config entries, language profiles, provider stats, and version.
    This is the recommended primary export format.

    Args:
        include_secrets: If True, include API keys/passwords unmasked.

    Returns:
        Export result dict.
    """
    warnings = []
    config = _get_config_entries(warnings)

    # Mask secrets unless explicitly requested
    if not include_secrets:
        secret_keywords = {"api_key", "password", "apikey", "token", "secret"}
        masked_config = {}
        for key, value in config.items():
            is_secret = any(kw in key.lower() for kw in secret_keywords)
            if is_secret and value:
                masked_config[key] = _mask_secret(str(value))
            else:
                masked_config[key] = value
        config = masked_config

    # Language profiles
    profiles = _get_language_profiles(warnings)

    # Provider stats summary
    provider_stats = _get_provider_stats_summary(warnings)

    data = {
        "_metadata": {
            "format": "sublarr-json",
            "version": _get_version(),
            "source": "Sublarr",
        },
        "config_entries": config,
        "language_profiles": profiles,
        "provider_stats": provider_stats,
    }

    return {
        "format": "json",
        "data": data,
        "filename": "sublarr_export.json",
        "content_type": "application/json",
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _mask_secret(value: str) -> str:
    """Mask a secret value for safe display."""
    if not value:
        return ""
    if len(value) <= 8:
        return "***"
    return value[:4] + "***" + value[-4:]


def _get_version() -> str:
    """Get Sublarr version string."""
    try:
        from version import __version__
        return __version__
    except ImportError:
        return "unknown"


def _get_config_entries(warnings: list) -> dict:
    """Load all config entries from database.

    Falls back to Pydantic Settings if DB is not available.
    """
    try:
        from db.config import get_all_config_entries
        entries = get_all_config_entries()
        if entries:
            return entries
    except Exception as exc:
        warnings.append(f"Could not load config from DB: {exc}")

    # Fallback to settings
    try:
        from config import get_settings
        return get_settings().model_dump()
    except Exception as exc:
        warnings.append(f"Could not load settings: {exc}")
        return {}


def _get_media_path(warnings: list) -> str:
    """Get the configured media path."""
    try:
        from config import get_settings
        return get_settings().media_path
    except Exception as exc:
        warnings.append(f"Could not determine media path: {exc}")
        return "/media"


def _get_language_profiles(warnings: list) -> list:
    """Load language profiles from database."""
    try:
        from db.profiles import get_all_language_profiles
        return get_all_language_profiles()
    except Exception as exc:
        warnings.append(f"Could not load language profiles: {exc}")
        return []


def _get_provider_stats_summary(warnings: list) -> dict:
    """Get a summary of provider statistics."""
    try:
        from db.repositories import ProviderRepository
        repo = ProviderRepository()
        stats = repo.get_all_provider_stats()
        return {
            "providers": stats if isinstance(stats, list) else [],
        }
    except Exception as exc:
        warnings.append(f"Could not load provider stats: {exc}")
        return {"providers": []}


_SUBTITLE_EXTENSIONS = {".srt", ".ass", ".ssa", ".vtt", ".smi", ".sub"}
_VIDEO_EXTENSIONS = {".mkv", ".mp4", ".avi", ".m4v", ".mov", ".wmv", ".flv", ".webm", ".ts"}


def _scan_subtitle_files(media_path: str, warnings: list) -> list:
    """Scan media path for subtitle files and associate them with video files.

    Returns list of dicts with path, language, format, video_path.
    Limited to first 1000 subtitle files to prevent excessive scanning.
    """
    from compat_checker import _extract_lang_code

    results = []
    max_files = 1000

    if not os.path.isdir(media_path):
        warnings.append(f"Media path does not exist or is not a directory: {media_path}")
        return results

    try:
        for dirpath, _dirnames, filenames in os.walk(media_path):
            if len(results) >= max_files:
                warnings.append(f"Scan limited to {max_files} subtitle files")
                break

            # Find video files in this directory
            video_files = {}
            for f in filenames:
                _, ext = os.path.splitext(f)
                if ext.lower() in _VIDEO_EXTENSIONS:
                    base = os.path.splitext(f)[0]
                    video_files[base.lower()] = os.path.join(dirpath, f)

            # Find subtitle files and match to videos
            for f in filenames:
                if len(results) >= max_files:
                    break

                _, ext = os.path.splitext(f)
                if ext.lower() not in _SUBTITLE_EXTENSIONS:
                    continue

                sub_path = os.path.join(dirpath, f)
                lang_code = _extract_lang_code(f)

                # Try to find matching video file
                # Strip lang code and modifiers to get base name
                from compat_checker import _get_sub_basename
                sub_base = _get_sub_basename(f)
                video_path = video_files.get(sub_base.lower(), "")

                # Also check parent directory for Subtitles/Subs subfolder case
                if not video_path:
                    parent = os.path.dirname(dirpath)
                    dirname_lower = os.path.basename(dirpath).lower()
                    if dirname_lower in ("subtitles", "subs"):
                        try:
                            for pf in os.listdir(parent):
                                p_ext = os.path.splitext(pf)[1].lower()
                                p_base = os.path.splitext(pf)[0].lower()
                                if p_ext in _VIDEO_EXTENSIONS and p_base == sub_base.lower():
                                    video_path = os.path.join(parent, pf)
                                    break
                        except OSError:
                            pass

                results.append({
                    "path": sub_path,
                    "language": lang_code or "",
                    "format": ext.lstrip(".").lower(),
                    "video_path": video_path,
                })
    except OSError as exc:
        warnings.append(f"Error scanning media path: {exc}")

    return results
