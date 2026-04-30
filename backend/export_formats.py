"""Format-specific exporters + helpers for the config/subtitle export manager.

Extracted from export_manager.py. Contains the four per-format exporters
(``_export_bazarr_format``, ``_export_plex_format``, ``_export_kodi_format``,
``_export_json_format``) and the internal helpers they share
(config entry loader, media-path accessor, subtitle scanner, secret masker).

The dispatcher public API (``export_config``, ``export_to_zip``) stays in
``export_manager.py``.
"""

import logging
import os

logger = logging.getLogger(__name__)


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
            plex_subtitles.append(
                {
                    "path": sub_path,
                    "language": sub_info.get("language", ""),
                    "format": sub_info.get("format", ""),
                    "plex_compatible": compat["compatible"],
                    "issues": compat["issues"],
                }
            )
        else:
            plex_subtitles.append(
                {
                    "path": sub_path,
                    "language": sub_info.get("language", ""),
                    "format": sub_info.get("format", ""),
                    "plex_compatible": None,
                    "issues": ["No associated video file found"],
                }
            )

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
            kodi_subtitles.append(
                {
                    "path": sub_path,
                    "language": sub_info.get("language", ""),
                    "format": sub_info.get("format", ""),
                    "kodi_compatible": compat["compatible"],
                    "issues": compat["issues"],
                }
            )
        else:
            kodi_subtitles.append(
                {
                    "path": sub_path,
                    "language": sub_info.get("language", ""),
                    "format": sub_info.get("format", ""),
                    "kodi_compatible": None,
                    "issues": ["No associated video file found"],
                }
            )

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

    # Mask secrets unless explicitly requested. Use the central rule set
    # (mirrors `Settings.get_safe_config()`) so DB-loaded entries get the
    # same protection as Pydantic dumps. The earlier keyword-only heuristic
    # missed Apprise notification URLs (Discord/Slack/Telegram tokens
    # embedded in the URL itself), database_url / redis_url DSNs, and the
    # nested API keys inside *_instances_json blobs.
    if not include_secrets:
        config = _mask_config_secrets(config)

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


# Sensitive-key heuristics — mirrors `Settings.get_safe_config()` in
# config_settings.py so the export pipeline cannot drift from the
# in-process safe-view used elsewhere (e.g. config endpoint, support bundle).
# Update both together when adding a new credential-bearing field.
_SENSITIVE_PARTS = {"password", "pin", "secret", "token", "api_key"}
_EXPLICIT_MASKED = {"database_url", "redis_url"}
_JSON_BLOB_FIELDS = {
    "sonarr_instances_json",
    "radarr_instances_json",
    "media_servers_json",
}
_CREDENTIAL_SUBKEYS = {"api_key", "apiKey", "password", "token", "secret", "pin"}


def _mask_config_secrets(data: dict) -> dict:
    """Apply Sublarr's central masking rules to an arbitrary config dict.

    The DB-loaded `config_entries` table is just key/value strings — it has
    no awareness of which keys are credentials. Apply the same rules
    `Settings.get_safe_config()` uses for Pydantic dumps so both data
    sources export with identical protection. Returns a new dict.
    """
    import json as _json

    masked = dict(data)
    for key in list(masked.keys()):
        value = masked[key]
        is_sensitive_name = (
            key in _EXPLICIT_MASKED
            or "api_key" in key
            or "key" in key.split("_")
            or any(s in key for s in _SENSITIVE_PARTS)
        )
        if is_sensitive_name:
            if value:
                masked[key] = _mask_secret(str(value))
        elif key == "notification_urls_json" and value:
            # Apprise URLs (discord://…/token, slack://…/secret, tgram://bot_token/…)
            # carry the secret in the URL itself — keyword-based masking misses them.
            masked[key] = "***configured***"
        elif key in _JSON_BLOB_FIELDS and value:
            try:
                parsed = _json.loads(value) if isinstance(value, str) else value
                if isinstance(parsed, list):
                    for item in parsed:
                        if isinstance(item, dict):
                            for sub in _CREDENTIAL_SUBKEYS:
                                if sub in item and item[sub]:
                                    item[sub] = _mask_secret(str(item[sub]))
                masked[key] = _json.dumps(parsed) if isinstance(value, str) else parsed
            except Exception:
                masked[key] = "***configured***"
    return masked


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

                results.append(
                    {
                        "path": sub_path,
                        "language": lang_code or "",
                        "format": ext.lstrip(".").lower(),
                        "video_path": video_path,
                    }
                )
    except OSError as exc:
        warnings.append(f"Error scanning media path: {exc}")

    return results
