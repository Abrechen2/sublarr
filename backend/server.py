"""Sublarr Flask API server with Blueprint-based routing.

Serves the React frontend as SPA and provides /api/v1/ endpoints
for translation management, job tracking, and *arr integrations.
"""

import os
import time
import logging
import threading
import ipaddress
from urllib.parse import urlparse
from collections import OrderedDict

import requests
from flask import Flask, Blueprint, request, jsonify, send_from_directory
from flask_socketio import SocketIO

from config import Settings, get_settings, reload_settings, map_path
from auth import init_auth
from database import (
    get_db, create_job, update_job, get_job, get_jobs,
    get_pending_job_count, record_stat, get_stats_summary,
    get_all_config_entries, save_config_entry,
    get_wanted_items, get_wanted_item, get_wanted_summary,
    update_wanted_status, delete_wanted_item,
    get_provider_cache_stats, get_provider_download_stats,
    clear_provider_cache,
)
from translator import translate_file, scan_directory
from ollama_client import check_ollama_health

settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ─── Flask App Setup ──────────────────────────────────────────────────────────

app = Flask(__name__, static_folder="static", static_url_path="")
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# Initialize authentication
init_auth(app)

# Initialize database
get_db()

# Apply DB config overrides on startup (settings saved via UI take precedence)
_db_overrides = get_all_config_entries()
if _db_overrides:
    logger.info("Applying %d config overrides from database", len(_db_overrides))
    settings = reload_settings(_db_overrides)
else:
    logger.info("No config overrides in database, using env/defaults")

# Bazarr deprecation warning
if os.environ.get("SUBLARR_BAZARR_URL") or os.environ.get("SUBLARR_BAZARR_API_KEY"):
    logger.warning(
        "DEPRECATION: SUBLARR_BAZARR_URL/SUBLARR_BAZARR_API_KEY are set but Bazarr "
        "integration has been removed. Sublarr now has its own provider system."
    )

# Initialize wanted scanner & scheduler
from wanted_scanner import get_scanner, invalidate_scanner
_wanted_scanner = get_scanner()
_wanted_scanner.start_scheduler(socketio=socketio)

# ─── API Blueprint ────────────────────────────────────────────────────────────

api = Blueprint("api", __name__, url_prefix="/api/v1")


def _map_path(path):
    """Map a remote file path to a local path. Delegates to config.map_path()."""
    return map_path(path)


# Batch state (still in-memory for real-time tracking)
batch_state = {
    "running": False,
    "total": 0,
    "processed": 0,
    "succeeded": 0,
    "failed": 0,
    "skipped": 0,
    "current_file": None,
    "errors": [],
}
batch_lock = threading.Lock()

# Wanted batch state (in-memory for real-time tracking)
wanted_batch_state = {
    "running": False,
    "total": 0,
    "processed": 0,
    "found": 0,
    "failed": 0,
    "skipped": 0,
    "current_item": None,
}
wanted_batch_lock = threading.Lock()

# In-memory stats for quick access (synced to DB)
stats_lock = threading.Lock()
_memory_stats = {
    "started_at": time.time(),
    "upgrades": {"srt_to_ass_translated": 0, "srt_upgrade_skipped": 0},
    "quality_warnings": 0,
}


def _update_stats(result):
    """Update stats from a translation result (thread-safe)."""
    with stats_lock:
        if result["success"]:
            s = result.get("stats", {})
            if s.get("skipped"):
                record_stat(success=True, skipped=True)
                reason = s.get("reason", "")
                if "no ASS upgrade" in reason:
                    _memory_stats["upgrades"]["srt_upgrade_skipped"] += 1
            else:
                fmt = s.get("format", "")
                source = s.get("source", "")
                record_stat(success=True, skipped=False, fmt=fmt, source=source)
                if s.get("upgrade_from_srt"):
                    _memory_stats["upgrades"]["srt_to_ass_translated"] += 1
                if s.get("quality_warnings"):
                    _memory_stats["quality_warnings"] += len(s["quality_warnings"])
        else:
            record_stat(success=False)


def _run_job(job_data):
    """Execute a translation job in a background thread."""
    job_id = job_data["id"]
    try:
        update_job(job_id, "running")

        result = translate_file(
            job_data["file_path"],
            force=job_data.get("force", False),
            arr_context=job_data.get("arr_context"),
        )

        status = "completed" if result["success"] else "failed"
        update_job(job_id, status, result=result, error=result.get("error"))
        _update_stats(result)

        # Emit WebSocket event
        socketio.emit("job_update", {
            "id": job_id,
            "status": status,
            "result": result,
        })

    except Exception as e:
        logger.exception("Job %s failed", job_id)
        update_job(job_id, "failed", error=str(e))
        record_stat(success=False)


def _build_arr_context(data):
    """Build arr_context from request data if Sonarr IDs are present."""
    series_id = data.get("sonarr_series_id")
    episode_id = data.get("sonarr_episode_id")
    if series_id and episode_id:
        return {
            "sonarr_series_id": series_id,
            "sonarr_episode_id": episode_id,
        }
    return None


# ─── Health & Status Endpoints ────────────────────────────────────────────────


@api.route("/health", methods=["GET"])
def health():
    """Health check endpoint (no auth required)."""
    healthy, message = check_ollama_health()

    # Check all configured services
    service_status = {"ollama": message}

    # Subtitle Providers
    try:
        from providers import get_provider_manager
        manager = get_provider_manager()
        provider_statuses = manager.get_provider_status()
        active_count = sum(1 for p in provider_statuses if p["healthy"])
        service_status["providers"] = f"{active_count}/{len(provider_statuses)} active"
    except Exception:
        service_status["providers"] = "error"

    # Sonarr
    try:
        from sonarr_client import get_sonarr_client
        sonarr = get_sonarr_client()
        if sonarr:
            s_healthy, s_msg = sonarr.health_check()
            service_status["sonarr"] = s_msg if s_healthy else f"unhealthy: {s_msg}"
        else:
            service_status["sonarr"] = "not configured"
    except Exception:
        service_status["sonarr"] = "error"

    # Radarr
    try:
        from radarr_client import get_radarr_client
        radarr = get_radarr_client()
        if radarr:
            r_healthy, r_msg = radarr.health_check()
            service_status["radarr"] = r_msg if r_healthy else f"unhealthy: {r_msg}"
        else:
            service_status["radarr"] = "not configured"
    except Exception:
        service_status["radarr"] = "error"

    # Jellyfin
    try:
        from jellyfin_client import get_jellyfin_client
        jellyfin = get_jellyfin_client()
        if jellyfin:
            j_healthy, j_msg = jellyfin.health_check()
            service_status["jellyfin"] = j_msg if j_healthy else f"unhealthy: {j_msg}"
        else:
            service_status["jellyfin"] = "not configured"
    except Exception:
        service_status["jellyfin"] = "error"

    status_code = 200 if healthy else 503
    return jsonify({
        "status": "healthy" if healthy else "unhealthy",
        "version": "0.1.0",
        "services": service_status,
    }), status_code


# ─── Translation Endpoints ────────────────────────────────────────────────────


@api.route("/translate", methods=["POST"])
def translate_async():
    """Start an async translation job."""
    data = request.get_json() or {}
    file_path = data.get("file_path")
    force = data.get("force", False)

    if not file_path:
        return jsonify({"error": "file_path is required"}), 400

    if not os.path.exists(file_path):
        return jsonify({"error": f"File not found: {file_path}"}), 404

    arr_context = _build_arr_context(data)
    job = create_job(file_path, force, arr_context)
    thread = threading.Thread(target=_run_job, args=(job,), daemon=True)
    thread.start()

    return jsonify({
        "job_id": job["id"],
        "status": "queued",
        "file_path": file_path,
    }), 202


@api.route("/translate/sync", methods=["POST"])
def translate_sync():
    """Translate a single file synchronously."""
    data = request.get_json() or {}
    file_path = data.get("file_path")
    force = data.get("force", False)

    if not file_path:
        return jsonify({"error": "file_path is required"}), 400

    if not os.path.exists(file_path):
        return jsonify({"error": f"File not found: {file_path}"}), 404

    arr_context = _build_arr_context(data)

    try:
        result = translate_file(file_path, force=force, arr_context=arr_context)
        _update_stats(result)
        status_code = 200 if result["success"] else 500
        return jsonify(result), status_code
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ─── Job & Status Endpoints ──────────────────────────────────────────────────


@api.route("/status/<job_id>", methods=["GET"])
def job_status(job_id):
    """Get the status of a translation job."""
    job = get_job(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)


@api.route("/jobs", methods=["GET"])
def list_jobs():
    """Get paginated job history."""
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 50, type=int), 200)
    status_filter = request.args.get("status")
    result = get_jobs(page=page, per_page=per_page, status=status_filter)
    return jsonify(result)


# ─── Batch Endpoints ─────────────────────────────────────────────────────────


@api.route("/batch", methods=["POST"])
def batch_start():
    """Start batch processing of a directory."""
    data = request.get_json() or {}
    directory = data.get("directory")
    force = data.get("force", False)
    dry_run = data.get("dry_run", False)
    page = data.get("page", 1)
    per_page = min(data.get("per_page", 100), 500)
    callback_url = data.get("callback_url")

    if not directory:
        return jsonify({"error": "directory is required"}), 400

    if callback_url:
        valid, err = _validate_callback_url(callback_url)
        if not valid:
            return jsonify({"error": f"Invalid callback_url: {err}"}), 400

    if not os.path.isdir(directory):
        return jsonify({"error": f"Directory not found: {directory}"}), 404

    files = scan_directory(directory, force=force)

    if dry_run:
        total_files = len(files)
        total_pages = max(1, (total_files + per_page - 1) // per_page)
        page = max(1, min(page, total_pages))
        start = (page - 1) * per_page
        end = start + per_page
        page_files = files[start:end]

        return jsonify({
            "dry_run": True,
            "files_found": total_files,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
            "files": [
                {
                    "path": f["path"],
                    "target_status": f["target_status"],
                    "size_mb": round(f["size_mb"], 1),
                }
                for f in page_files
            ],
        })

    with batch_lock:
        if batch_state["running"]:
            return jsonify({"error": "Batch already running"}), 409

        batch_state.update({
            "running": True,
            "total": len(files),
            "processed": 0,
            "succeeded": 0,
            "failed": 0,
            "skipped": 0,
            "current_file": None,
            "errors": [],
        })

    def _run_batch():
        try:
            for f in files:
                with batch_lock:
                    batch_state["current_file"] = f["path"]

                try:
                    result = translate_file(f["path"], force=force)
                    with batch_lock:
                        batch_state["processed"] += 1
                        if result["success"]:
                            if result["stats"].get("skipped"):
                                batch_state["skipped"] += 1
                            else:
                                batch_state["succeeded"] += 1
                        else:
                            batch_state["failed"] += 1
                            batch_state["errors"].append({
                                "file": f["path"],
                                "error": result.get("error"),
                            })

                    _update_stats(result)

                    # WebSocket notification
                    socketio.emit("batch_progress", {
                        "processed": batch_state["processed"],
                        "total": batch_state["total"],
                        "current_file": f["path"],
                        "success": result["success"],
                    })

                    # Callback notification
                    if callback_url:
                        _send_callback(callback_url, {
                            "event": "file_completed",
                            "file": f["path"],
                            "success": result["success"],
                            "processed": batch_state["processed"],
                            "total": batch_state["total"],
                        })

                except Exception as e:
                    logger.exception("Batch: failed on %s", f["path"])
                    with batch_lock:
                        batch_state["processed"] += 1
                        batch_state["failed"] += 1
                        batch_state["errors"].append({
                            "file": f["path"],
                            "error": str(e),
                        })
        finally:
            with batch_lock:
                batch_state["running"] = False
                batch_state["current_file"] = None
                snapshot = dict(batch_state)

            socketio.emit("batch_completed", snapshot)

            if callback_url:
                _send_callback(callback_url, {
                    "event": "batch_completed",
                    "total": snapshot["total"],
                    "succeeded": snapshot["succeeded"],
                    "failed": snapshot["failed"],
                    "skipped": snapshot["skipped"],
                })

    thread = threading.Thread(target=_run_batch, daemon=True)
    thread.start()

    return jsonify({
        "status": "started",
        "total_files": len(files),
    }), 202


def _validate_callback_url(url):
    """Validate callback URL to prevent SSRF attacks.

    Blocks private IPs, localhost, and non-HTTP schemes.

    Returns:
        tuple: (is_valid: bool, error_message: str or None)
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return False, "Invalid URL"

    if parsed.scheme not in ("http", "https"):
        return False, f"Unsupported scheme: {parsed.scheme}"

    hostname = parsed.hostname
    if not hostname:
        return False, "No hostname in URL"

    # Block localhost variants
    if hostname in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        return False, "Localhost callbacks are not allowed"

    # Block private/reserved IP ranges
    try:
        addr = ipaddress.ip_address(hostname)
        if addr.is_private or addr.is_loopback or addr.is_reserved or addr.is_link_local:
            return False, f"Private/reserved IP not allowed: {hostname}"
    except ValueError:
        # hostname is not an IP — that's fine (it's a domain name)
        pass

    return True, None


def _send_callback(url, data):
    """Send a callback notification (fire-and-forget)."""
    try:
        requests.post(url, json=data, timeout=5)
    except Exception as e:
        logger.warning("Callback to %s failed: %s", url, e)


@api.route("/batch/status", methods=["GET"])
def batch_status_endpoint():
    """Get batch processing status."""
    with batch_lock:
        return jsonify(dict(batch_state))


# ─── Stats Endpoint ───────────────────────────────────────────────────────────


@api.route("/stats", methods=["GET"])
def get_stats():
    """Get overall statistics."""
    db_stats = get_stats_summary()

    with stats_lock:
        uptime = time.time() - _memory_stats["started_at"]
        memory_extras = {
            "upgrades": dict(_memory_stats["upgrades"]),
            "quality_warnings": _memory_stats["quality_warnings"],
        }

    pending = get_pending_job_count()

    return jsonify({
        **db_stats,
        **memory_extras,
        "pending_jobs": pending,
        "uptime_seconds": round(uptime),
        "batch_running": batch_state["running"],
    })


# ─── Config Endpoints ────────────────────────────────────────────────────────


@api.route("/config", methods=["GET"])
def get_config():
    """Get current configuration (without secrets)."""
    s = get_settings()
    return jsonify(s.get_safe_config())


@api.route("/config", methods=["PUT"])
def update_config():
    """Update configuration values and reload settings."""
    global settings
    data = request.get_json() or {}
    if not data:
        return jsonify({"error": "No config values provided"}), 400

    # Validate that keys exist in Settings
    valid_keys = set(Settings.model_fields.keys()) if hasattr(Settings, 'model_fields') else set()
    saved_keys = []

    for key, value in data.items():
        # Skip masked password values (user didn't change them)
        if str(value) == '***configured***':
            continue
        # Only save known config keys (or all if we can't determine valid keys)
        if not valid_keys or key in valid_keys:
            save_config_entry(key, str(value))
            saved_keys.append(key)

    # Reload settings with ALL DB overrides applied
    all_overrides = get_all_config_entries()
    settings = reload_settings(all_overrides)

    # Invalidate singleton clients so they pick up new URLs/keys
    from sonarr_client import invalidate_client as _inv_sonarr
    from radarr_client import invalidate_client as _inv_radarr
    from jellyfin_client import invalidate_client as _inv_jellyfin
    from providers import invalidate_manager as _inv_providers
    _inv_sonarr()
    _inv_radarr()
    _inv_jellyfin()
    _inv_providers()
    invalidate_scanner()

    logger.info("Config updated: %s — settings reloaded", saved_keys)

    socketio.emit("config_updated", {"updated_keys": saved_keys})

    return jsonify({
        "status": "saved",
        "updated_keys": saved_keys,
        "config": settings.get_safe_config(),
    })


# ─── Library Endpoint ─────────────────────────────────────────────────────────


@api.route("/library", methods=["GET"])
def get_library():
    """Get series/movies with subtitle status."""
    result = {"series": [], "movies": []}

    try:
        from sonarr_client import get_sonarr_client
        sonarr = get_sonarr_client()
        if sonarr:
            result["series"] = sonarr.get_library_info()
    except Exception as e:
        logger.warning("Failed to get Sonarr library: %s", e)

    try:
        from radarr_client import get_radarr_client
        radarr = get_radarr_client()
        if radarr:
            result["movies"] = radarr.get_library_info()
    except Exception as e:
        logger.warning("Failed to get Radarr library: %s", e)

    return jsonify(result)


# ─── Provider Endpoints ──────────────────────────────────────────────────────


@api.route("/providers", methods=["GET"])
def list_providers():
    """Get status of all subtitle providers."""
    try:
        from providers import get_provider_manager
        manager = get_provider_manager()
        return jsonify({"providers": manager.get_provider_status()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api.route("/providers/test/<provider_name>", methods=["POST"])
def test_provider(provider_name):
    """Test a specific provider's connectivity."""
    try:
        from providers import get_provider_manager
        manager = get_provider_manager()
        provider = manager._providers.get(provider_name)
        if not provider:
            return jsonify({"error": f"Provider '{provider_name}' not found or not enabled"}), 404

        healthy, message = provider.health_check()
        return jsonify({
            "provider": provider_name,
            "healthy": healthy,
            "message": message,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api.route("/providers/search", methods=["POST"])
def search_providers():
    """Search subtitle providers for a specific file.

    Body: {
        "file_path": "/media/anime/...",
        "series_title": "...",
        "season": 1,
        "episode": 1,
        "language": "en",
        "format": "ass"  // optional filter
    }
    """
    data = request.get_json() or {}

    from providers import get_provider_manager
    from providers.base import VideoQuery, SubtitleFormat

    query = VideoQuery(
        file_path=data.get("file_path", ""),
        series_title=data.get("series_title", ""),
        title=data.get("title", ""),
        season=data.get("season"),
        episode=data.get("episode"),
        imdb_id=data.get("imdb_id", ""),
        anilist_id=data.get("anilist_id"),
        anidb_id=data.get("anidb_id"),
        languages=[data.get("language", get_settings().source_language)],
    )

    format_filter = None
    if data.get("format"):
        try:
            format_filter = SubtitleFormat(data["format"])
        except ValueError:
            pass

    try:
        manager = get_provider_manager()
        results = manager.search(query, format_filter=format_filter)

        return jsonify({
            "results": [
                {
                    "provider": r.provider_name,
                    "subtitle_id": r.subtitle_id,
                    "language": r.language,
                    "format": r.format.value,
                    "filename": r.filename,
                    "release_info": r.release_info,
                    "score": r.score,
                    "hearing_impaired": r.hearing_impaired,
                    "matches": list(r.matches),
                }
                for r in results[:50]  # Limit response size
            ],
            "total": len(results),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api.route("/providers/stats", methods=["GET"])
def provider_stats():
    """Get cache and download statistics for all providers."""
    cache_stats = get_provider_cache_stats()
    download_stats = get_provider_download_stats()
    return jsonify({
        "cache": cache_stats,
        "downloads": download_stats,
    })


@api.route("/providers/cache/clear", methods=["POST"])
def clear_cache():
    """Clear provider cache. Optional body: {provider_name: "..."}"""
    data = request.get_json(silent=True) or {}
    provider_name = data.get("provider_name")
    clear_provider_cache(provider_name)
    return jsonify({
        "status": "cleared",
        "provider": provider_name or "all",
    })


# ─── Language Profile Endpoints ──────────────────────────────────────────────


@api.route("/language-profiles", methods=["GET"])
def list_language_profiles():
    """Get all language profiles."""
    from database import get_all_language_profiles
    profiles = get_all_language_profiles()
    return jsonify({"profiles": profiles})


@api.route("/language-profiles", methods=["POST"])
def create_language_profile_endpoint():
    """Create a new language profile."""
    from database import create_language_profile as db_create_profile
    data = request.get_json() or {}

    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400

    source_lang = data.get("source_language", "en")
    source_name = data.get("source_language_name", "English")
    target_langs = data.get("target_languages", ["de"])
    target_names = data.get("target_language_names", ["German"])

    if not target_langs:
        return jsonify({"error": "At least one target language is required"}), 400

    try:
        profile_id = db_create_profile(
            name, source_lang, source_name, target_langs, target_names
        )
    except Exception as e:
        if "UNIQUE constraint" in str(e):
            return jsonify({"error": f"Profile name '{name}' already exists"}), 409
        return jsonify({"error": str(e)}), 500

    from database import get_language_profile
    profile = get_language_profile(profile_id)
    return jsonify(profile), 201


@api.route("/language-profiles/<int:profile_id>", methods=["PUT"])
def update_language_profile_endpoint(profile_id):
    """Update a language profile."""
    from database import get_language_profile, update_language_profile as db_update_profile
    profile = get_language_profile(profile_id)
    if not profile:
        return jsonify({"error": "Profile not found"}), 404

    data = request.get_json() or {}
    fields = {}
    for key in ("name", "source_language", "source_language_name",
                "target_languages", "target_language_names"):
        if key in data:
            fields[key] = data[key]

    if not fields:
        return jsonify({"error": "No fields to update"}), 400

    try:
        db_update_profile(profile_id, **fields)
    except Exception as e:
        if "UNIQUE constraint" in str(e):
            return jsonify({"error": f"Profile name '{data.get('name')}' already exists"}), 409
        return jsonify({"error": str(e)}), 500

    updated = get_language_profile(profile_id)
    return jsonify(updated)


@api.route("/language-profiles/<int:profile_id>", methods=["DELETE"])
def delete_language_profile_endpoint(profile_id):
    """Delete a language profile (cannot delete default)."""
    from database import delete_language_profile as db_delete_profile
    deleted = db_delete_profile(profile_id)
    if not deleted:
        return jsonify({"error": "Profile not found or is the default profile"}), 400
    return jsonify({"status": "deleted", "id": profile_id})


@api.route("/language-profiles/assign", methods=["PUT"])
def assign_profile():
    """Assign a language profile to a series or movie.

    Body: { type: "series"|"movie", arr_id: int, profile_id: int }
    """
    from database import assign_series_profile, assign_movie_profile, get_language_profile
    data = request.get_json() or {}

    item_type = data.get("type")
    arr_id = data.get("arr_id")
    profile_id = data.get("profile_id")

    if not item_type or arr_id is None or profile_id is None:
        return jsonify({"error": "type, arr_id, and profile_id are required"}), 400

    # Verify profile exists
    profile = get_language_profile(profile_id)
    if not profile:
        return jsonify({"error": "Profile not found"}), 404

    if item_type == "series":
        assign_series_profile(arr_id, profile_id)
    elif item_type == "movie":
        assign_movie_profile(arr_id, profile_id)
    else:
        return jsonify({"error": "type must be 'series' or 'movie'"}), 400

    return jsonify({"status": "assigned", "type": item_type, "arr_id": arr_id, "profile_id": profile_id})


# ─── Wanted Endpoints ────────────────────────────────────────────────────────


@api.route("/wanted", methods=["GET"])
def list_wanted():
    """Get paginated wanted items."""
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 50, type=int), 200)
    item_type = request.args.get("item_type")
    status_filter = request.args.get("status")
    series_id = request.args.get("series_id", type=int)

    result = get_wanted_items(
        page=page, per_page=per_page,
        item_type=item_type, status=status_filter,
        series_id=series_id,
    )
    return jsonify(result)


@api.route("/wanted/summary", methods=["GET"])
def wanted_summary():
    """Get aggregated wanted stats."""
    scanner = get_scanner()
    summary = get_wanted_summary()
    summary["scan_running"] = scanner.is_scanning
    summary["last_scan_at"] = scanner.last_scan_at
    return jsonify(summary)


@api.route("/wanted/refresh", methods=["POST"])
def refresh_wanted():
    """Trigger a wanted scan. Optional body: {series_id: int}"""
    scanner = get_scanner()
    if scanner.is_scanning:
        return jsonify({"error": "Scan already running"}), 409

    data = request.get_json(silent=True) or {}
    series_id = data.get("series_id")

    def _run_scan():
        if series_id:
            result = scanner.scan_series(series_id)
        else:
            result = scanner.scan_all()
        socketio.emit("wanted_scan_completed", result)

    thread = threading.Thread(target=_run_scan, daemon=True)
    thread.start()

    return jsonify({"status": "scan_started", "series_id": series_id}), 202


@api.route("/wanted/<int:item_id>/status", methods=["PUT"])
def update_wanted_item_status(item_id):
    """Update a wanted item's status (e.g. ignore/un-ignore)."""
    data = request.get_json() or {}
    new_status = data.get("status")

    if new_status not in ("wanted", "ignored", "failed"):
        return jsonify({"error": "Invalid status. Use: wanted, ignored, failed"}), 400

    item = get_wanted_item(item_id)
    if not item:
        return jsonify({"error": "Item not found"}), 404

    update_wanted_status(item_id, new_status, error=data.get("error", ""))
    return jsonify({"status": "updated", "id": item_id, "new_status": new_status})


@api.route("/wanted/<int:item_id>", methods=["DELETE"])
def delete_wanted(item_id):
    """Remove a wanted item."""
    item = get_wanted_item(item_id)
    if not item:
        return jsonify({"error": "Item not found"}), 404

    delete_wanted_item(item_id)
    return jsonify({"status": "deleted", "id": item_id})


# ─── Wanted Search & Process Endpoints ────────────────────────────────────────


@api.route("/wanted/<int:item_id>/search", methods=["POST"])
def search_wanted(item_id):
    """Search providers for a specific wanted item."""
    item = get_wanted_item(item_id)
    if not item:
        return jsonify({"error": "Item not found"}), 404

    from wanted_search import search_wanted_item
    result = search_wanted_item(item_id)

    if result.get("error"):
        return jsonify(result), 400

    return jsonify(result)


@api.route("/wanted/<int:item_id>/process", methods=["POST"])
def process_wanted(item_id):
    """Download + translate for a single wanted item (async)."""
    item = get_wanted_item(item_id)
    if not item:
        return jsonify({"error": "Item not found"}), 404

    from wanted_search import process_wanted_item

    def _run():
        result = process_wanted_item(item_id)
        socketio.emit("wanted_item_processed", result)
        if result.get("upgraded"):
            socketio.emit("upgrade_completed", {
                "file_path": result.get("output_path"),
                "provider": result.get("provider"),
            })

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    return jsonify({"status": "processing", "wanted_id": item_id}), 202


@api.route("/wanted/batch-search", methods=["POST"])
def wanted_batch_search():
    """Process all wanted items (async with progress tracking)."""
    with wanted_batch_lock:
        if wanted_batch_state["running"]:
            return jsonify({"error": "Wanted batch already running"}), 409

    data = request.get_json(silent=True) or {}
    item_ids = data.get("item_ids")

    from wanted_search import process_wanted_batch

    # Determine total count upfront
    if item_ids:
        total = len(item_ids)
    else:
        from database import get_wanted_count
        total = get_wanted_count(status="wanted")

    with wanted_batch_lock:
        wanted_batch_state.update({
            "running": True,
            "total": total,
            "processed": 0,
            "found": 0,
            "failed": 0,
            "skipped": 0,
            "current_item": None,
        })

    def _run_batch():
        try:
            for progress in process_wanted_batch(item_ids):
                with wanted_batch_lock:
                    wanted_batch_state["processed"] = progress["processed"]
                    wanted_batch_state["found"] = progress["found"]
                    wanted_batch_state["failed"] = progress["failed"]
                    wanted_batch_state["skipped"] = progress["skipped"]
                    wanted_batch_state["current_item"] = progress["current_item"]

                socketio.emit("wanted_batch_progress", {
                    "processed": progress["processed"],
                    "total": progress["total"],
                    "found": progress["found"],
                    "failed": progress["failed"],
                    "current_item": progress["current_item"],
                })
        finally:
            with wanted_batch_lock:
                snapshot = dict(wanted_batch_state)
                wanted_batch_state["running"] = False
                wanted_batch_state["current_item"] = None

            socketio.emit("wanted_batch_completed", snapshot)

    thread = threading.Thread(target=_run_batch, daemon=True)
    thread.start()

    return jsonify({"status": "started", "total_items": total}), 202


@api.route("/wanted/batch-search/status", methods=["GET"])
def wanted_batch_status():
    """Get wanted batch search progress."""
    with wanted_batch_lock:
        return jsonify(dict(wanted_batch_state))


@api.route("/wanted/search-all", methods=["POST"])
def wanted_search_all():
    """Trigger a search-all for wanted items (provider search for all pending items)."""
    scanner = get_scanner()
    if scanner.is_searching:
        return jsonify({"error": "Search already running"}), 409

    def _run_search():
        scanner.search_all(socketio=socketio)

    thread = threading.Thread(target=_run_search, daemon=True)
    thread.start()

    return jsonify({"status": "search_started"}), 202


# ─── Webhook Endpoints ───────────────────────────────────────────────────────


def _webhook_auto_pipeline(file_path: str, title: str, series_id: int = None):
    """Full webhook automation pipeline: delay -> scan -> search -> translate.

    Each step is individually configurable. Emits WebSocket events at each stage.
    """
    s = get_settings()
    delay = s.webhook_delay_minutes * 60

    socketio.emit("webhook_received", {
        "file_path": file_path,
        "title": title,
        "delay_minutes": s.webhook_delay_minutes,
    })

    # Step 1: Configurable delay
    if delay > 0:
        logger.info("Webhook pipeline: waiting %d minutes...", s.webhook_delay_minutes)
        time.sleep(delay)

    result_info = {"file_path": file_path, "title": title, "steps": []}

    # Step 2: Auto-scan
    if s.webhook_auto_scan and series_id:
        try:
            scanner = get_scanner()
            scan_result = scanner.scan_series(series_id)
            result_info["steps"].append({"scan": scan_result})
            logger.info("Webhook pipeline: scan complete for series %d", series_id)
        except Exception as e:
            logger.warning("Webhook pipeline: scan failed: %s", e)
            result_info["steps"].append({"scan": {"error": str(e)}})

    # Step 3: Auto-search + translate via wanted system
    if s.webhook_auto_search:
        try:
            from database import get_wanted_item_by_path
            wanted_item = get_wanted_item_by_path(file_path)

            if wanted_item and s.webhook_auto_translate:
                from wanted_search import process_wanted_item
                process_result = process_wanted_item(wanted_item["id"])
                result_info["steps"].append({"process": process_result})
                logger.info("Webhook pipeline: process result: %s", process_result.get("status"))
            elif wanted_item:
                from wanted_search import search_wanted_item
                search_result = search_wanted_item(wanted_item["id"])
                result_info["steps"].append({"search": search_result})
            else:
                result_info["steps"].append({"search": "no wanted item found"})
        except Exception as e:
            logger.warning("Webhook pipeline: search/process failed: %s", e)
            result_info["steps"].append({"search": {"error": str(e)}})

    # Step 4: Fallback — direct translate if auto_search disabled
    if not s.webhook_auto_search:
        job = create_job(file_path)
        _run_job(job)
        result_info["steps"].append({"translate": "direct"})

    socketio.emit("webhook_completed", result_info)
    logger.info("Webhook pipeline completed for: %s", file_path)


@api.route("/webhook/sonarr", methods=["POST"])
def webhook_sonarr():
    """Handle Sonarr webhook (OnDownload event)."""
    data = request.get_json() or {}
    event_type = data.get("eventType", "")

    if event_type == "Test":
        return jsonify({"status": "ok", "message": "Test received"}), 200

    if event_type != "Download":
        return jsonify({"status": "ignored", "event": event_type}), 200

    episode_file = data.get("episodeFile", {})
    file_path = episode_file.get("path", "")
    series = data.get("series", {})

    if not file_path:
        return jsonify({"error": "No file path in webhook payload"}), 400

    file_path = _map_path(file_path)
    title = f"{series.get('title', 'Unknown')} — {file_path}"
    series_id = series.get("id")

    logger.info("Sonarr webhook: %s", title)

    thread = threading.Thread(
        target=_webhook_auto_pipeline,
        args=(file_path, title, series_id),
        daemon=True,
    )
    thread.start()

    s = get_settings()
    return jsonify({
        "status": "queued",
        "file_path": file_path,
        "delay_minutes": s.webhook_delay_minutes,
        "auto_pipeline": s.webhook_auto_search,
    }), 202


@api.route("/webhook/radarr", methods=["POST"])
def webhook_radarr():
    """Handle Radarr webhook (OnDownload event)."""
    data = request.get_json() or {}
    event_type = data.get("eventType", "")

    if event_type == "Test":
        return jsonify({"status": "ok", "message": "Test received"}), 200

    if event_type != "Download":
        return jsonify({"status": "ignored", "event": event_type}), 200

    movie_file = data.get("movieFile", {})
    file_path = movie_file.get("path", "")
    movie = data.get("movie", {})

    if not file_path:
        return jsonify({"error": "No file path in webhook payload"}), 400

    file_path = _map_path(file_path)
    title = movie.get("title", "Unknown")

    logger.info("Radarr webhook: %s - %s", title, file_path)

    thread = threading.Thread(
        target=_webhook_auto_pipeline,
        args=(file_path, title),
        daemon=True,
    )
    thread.start()

    s = get_settings()
    return jsonify({
        "status": "queued",
        "file_path": file_path,
        "delay_minutes": s.webhook_delay_minutes,
        "auto_pipeline": s.webhook_auto_search,
    }), 202


# ─── Re-Translation Endpoints ────────────────────────────────────────────────


@api.route("/retranslate/status", methods=["GET"])
def retranslate_status():
    """Get re-translation status: current config hash and outdated file count."""
    from database import get_outdated_jobs_count
    s = get_settings()
    current_hash = s.get_translation_config_hash()
    outdated = get_outdated_jobs_count(current_hash)

    return jsonify({
        "current_hash": current_hash,
        "outdated_count": outdated,
        "ollama_model": s.ollama_model,
        "target_language": s.target_language,
    })


@api.route("/retranslate/<int:job_id>", methods=["POST"])
def retranslate_single(job_id):
    """Re-translate a single item (deletes old sub, forces re-translation)."""
    from database import get_job as get_job_by_id

    job = get_job_by_id(str(job_id))
    if not job:
        # Try as wanted item ID
        item = get_wanted_item(job_id)
        if not item:
            return jsonify({"error": "Item not found"}), 404
        file_path = item["file_path"]
    else:
        file_path = job["file_path"]

    if not os.path.exists(file_path):
        return jsonify({"error": f"File not found: {file_path}"}), 404

    # Delete existing translated subtitle
    s = get_settings()
    base = os.path.splitext(file_path)[0]
    for fmt in ["ass", "srt"]:
        for pattern in s.get_target_patterns(fmt):
            target = base + pattern
            if os.path.exists(target):
                os.remove(target)
                logger.info("Re-translate: removed %s", target)

    # Re-translate with force
    new_job = create_job(file_path, force=True)

    def _run():
        _run_job(new_job)
        socketio.emit("retranslation_completed", {
            "file_path": file_path,
            "job_id": new_job["id"],
        })

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    return jsonify({
        "status": "started",
        "job_id": new_job["id"],
        "file_path": file_path,
    }), 202


@api.route("/retranslate/batch", methods=["POST"])
def retranslate_batch():
    """Re-translate all outdated items (async with WebSocket progress)."""
    from database import get_outdated_jobs

    s = get_settings()
    current_hash = s.get_translation_config_hash()
    outdated = get_outdated_jobs(current_hash)

    if not outdated:
        return jsonify({"status": "nothing_to_do", "count": 0})

    total = len(outdated)

    def _run_retranslate():
        processed = 0
        succeeded = 0
        failed = 0

        for job in outdated:
            file_path = job["file_path"]
            if not os.path.exists(file_path):
                processed += 1
                failed += 1
                continue

            # Remove existing target subs
            base = os.path.splitext(file_path)[0]
            for fmt in ["ass", "srt"]:
                for pattern in s.get_target_patterns(fmt):
                    target = base + pattern
                    if os.path.exists(target):
                        os.remove(target)

            try:
                result = translate_file(file_path, force=True)
                processed += 1
                if result["success"]:
                    succeeded += 1
                else:
                    failed += 1
            except Exception as e:
                processed += 1
                failed += 1
                logger.warning("Re-translate batch: error on %s: %s", file_path, e)

            socketio.emit("retranslation_progress", {
                "processed": processed,
                "total": total,
                "succeeded": succeeded,
                "failed": failed,
                "current_file": file_path,
            })

        socketio.emit("retranslation_completed", {
            "count": processed,
            "succeeded": succeeded,
            "failed": failed,
        })

    thread = threading.Thread(target=_run_retranslate, daemon=True)
    thread.start()

    return jsonify({
        "status": "started",
        "total": total,
    }), 202


# ─── Logs Endpoint ────────────────────────────────────────────────────────────


@api.route("/logs", methods=["GET"])
def get_logs():
    """Get recent log entries."""
    # Read from log file if available, otherwise return empty
    log_file = os.environ.get("SUBLARR_LOG_FILE", "/config/sublarr.log")
    lines = request.args.get("lines", 200, type=int)
    level = request.args.get("level", "").upper()

    log_entries = []
    if os.path.exists(log_file):
        try:
            with open(log_file, "r") as f:
                all_lines = f.readlines()
                recent = all_lines[-lines:] if len(all_lines) > lines else all_lines
                for line in recent:
                    if level and f"[{level}]" not in line:
                        continue
                    log_entries.append(line.strip())
        except Exception as e:
            logger.warning("Failed to read log file: %s", e)

    return jsonify({
        "entries": log_entries,
        "total": len(log_entries),
    })


# ─── WebSocket Events ────────────────────────────────────────────────────────


@socketio.on("connect")
def handle_connect():
    """Handle WebSocket connection."""
    logger.debug("WebSocket client connected")


@socketio.on("disconnect")
def handle_disconnect():
    """Handle WebSocket disconnection."""
    logger.debug("WebSocket client disconnected")


# ─── Register Blueprint & SPA Fallback ────────────────────────────────────────

app.register_blueprint(api)


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_spa(path):
    """Serve the React SPA frontend."""
    static_dir = app.static_folder or "static"

    # Try to serve the exact file first
    if path and os.path.exists(os.path.join(static_dir, path)):
        return send_from_directory(static_dir, path)

    # Fallback to index.html for SPA routing
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return send_from_directory(static_dir, "index.html")

    # No frontend built yet — return API info
    return jsonify({
        "name": "Sublarr",
        "version": "0.1.0",
        "api": "/api/v1/health",
        "message": "Frontend not built. Run 'npm run build' in frontend/ first.",
    })


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=settings.port, debug=True, allow_unsafe_werkzeug=True)
