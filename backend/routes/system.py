"""System routes — /health, /stats, /database/*, /backup/*, /statistics, /logs, /notifications/*."""

import io
import os
import csv
import json
import time
import zipfile
import logging
from datetime import datetime, timezone

from flask import Blueprint, request, jsonify, send_file
from sqlalchemy import text

from version import __version__

bp = Blueprint("system", __name__, url_prefix="/api/v1")
logger = logging.getLogger(__name__)


@bp.route("/health", methods=["GET"])
def health():
    """Health check endpoint (no auth required).
    ---
    get:
      tags:
        - System
      summary: Basic health check
      description: Returns overall health status, version, and service connectivity. No authentication required.
      responses:
        200:
          description: System is healthy
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                    enum: [healthy, unhealthy]
                  version:
                    type: string
                  services:
                    type: object
                    additionalProperties:
                      type: string
        503:
          description: System is unhealthy
    """
    from ollama_client import check_ollama_health
    from config import get_settings

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

    # Media Servers (replaces old Jellyfin-specific check)
    try:
        from mediaserver import get_media_server_manager
        manager = get_media_server_manager()
        ms_health = manager.health_check_all()
        if ms_health:
            healthy_count = sum(1 for h in ms_health if h["healthy"])
            service_status["media_servers"] = f"{healthy_count}/{len(ms_health)} healthy"
            # Also add individual server status
            for h in ms_health:
                key = f"media_server:{h['name']}"
                service_status[key] = h["message"] if h["healthy"] else f"unhealthy: {h['message']}"
        else:
            service_status["media_servers"] = "none configured"
    except Exception:
        service_status["media_servers"] = "error"

    status_code = 200 if healthy else 503
    return jsonify({
        "status": "healthy" if healthy else "unhealthy",
        "version": __version__,
        "services": service_status,
    }), status_code


@bp.route("/health/detailed", methods=["GET"])
def health_detailed():
    """Detailed health check with subsystem status (authenticated).
    ---
    get:
      tags:
        - System
      summary: Detailed health check
      description: Returns per-subsystem health status including database, Ollama, providers, disk, and memory.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: All subsystems healthy
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                    enum: [healthy, degraded]
                  subsystems:
                    type: object
                    additionalProperties:
                      type: object
        401:
          description: Unauthorized (API key required)
        503:
          description: One or more subsystems degraded
    """
    from database_health import check_integrity, get_database_stats
    from ollama_client import check_ollama_health
    from db import get_db
    from config import get_settings

    s = get_settings()
    subsystems: dict = {}
    overall_healthy = True

    # Database
    try:
        db = get_db()
        db_ok, db_msg = check_integrity(db)
        db_stats = get_database_stats(db, s.db_path)
        subsystems["database"] = {
            "healthy": db_ok,
            "message": db_msg,
            "size_bytes": db_stats.get("size_bytes", 0),
            "wal_mode": db_stats.get("wal_mode", False),
        }
        if not db_ok:
            overall_healthy = False
    except Exception as exc:
        subsystems["database"] = {"healthy": False, "message": str(exc)}
        overall_healthy = False

    # Ollama
    try:
        ollama_ok, ollama_msg = check_ollama_health()
        subsystems["ollama"] = {"healthy": ollama_ok, "message": ollama_msg}
        if not ollama_ok:
            overall_healthy = False
    except Exception as exc:
        subsystems["ollama"] = {"healthy": False, "message": str(exc)}
        overall_healthy = False

    # Providers + circuit breakers
    try:
        from providers import get_provider_manager
        manager = get_provider_manager()
        providers_detail = []
        for name, cb in manager._circuit_breakers.items():
            cb_status = cb.get_status()
            providers_detail.append({
                "name": name,
                "circuit_breaker": cb_status["state"],
                "failure_count": cb_status["failure_count"],
            })
        subsystems["providers"] = {
            "healthy": all(p["circuit_breaker"] != "open" for p in providers_detail),
            "details": providers_detail,
        }
    except Exception as exc:
        subsystems["providers"] = {"healthy": False, "message": str(exc)}

    # Disk
    try:
        import psutil
        for path, label in [("/config", "config"), ("/media", "media")]:
            try:
                usage = psutil.disk_usage(path)
                subsystems[f"disk_{label}"] = {
                    "healthy": usage.percent < 95,
                    "percent": usage.percent,
                    "free_bytes": usage.free,
                }
                if usage.percent >= 95:
                    overall_healthy = False
            except (FileNotFoundError, OSError):
                subsystems[f"disk_{label}"] = {"healthy": True, "message": "path not found"}
    except ImportError:
        subsystems["disk"] = {"healthy": True, "message": "psutil not installed"}

    # Memory
    try:
        import psutil
        proc = psutil.Process()
        mem = proc.memory_info()
        subsystems["memory"] = {
            "healthy": True,
            "rss_bytes": mem.rss,
            "vms_bytes": mem.vms,
        }
    except ImportError:
        subsystems["memory"] = {"healthy": True, "message": "psutil not installed"}

    # ── New subsystem checks ──────────────────────────────────────────────

    # Translation Backends
    try:
        from translation import get_translation_manager
        tm = get_translation_manager()
        backends_info = tm.get_all_backends()
        backends_health = {}
        for b in backends_info:
            bname = b["name"]
            if not b.get("configured"):
                backends_health[bname] = {"healthy": True, "message": "Not configured"}
                continue
            try:
                instance = tm.get_backend(bname)
                if instance and hasattr(instance, "health_check"):
                    h, msg = instance.health_check()
                    backends_health[bname] = {"healthy": h, "message": msg}
                else:
                    backends_health[bname] = {"healthy": True, "message": "No health check available"}
            except Exception as be:
                backends_health[bname] = {"healthy": False, "message": str(be)}
        subsystems["translation_backends"] = {
            "healthy": any(b["healthy"] for b in backends_health.values()) if backends_health else True,
            "backends": backends_health,
        }
        if not subsystems["translation_backends"]["healthy"]:
            overall_healthy = False
    except Exception as exc:
        subsystems["translation_backends"] = {"healthy": False, "message": str(exc)}
        overall_healthy = False

    # Media Servers
    try:
        from mediaserver import get_media_server_manager
        ms_manager = get_media_server_manager()
        ms_checks = ms_manager.health_check_all()
        if ms_checks:
            instances = [
                {"type": c.get("type", ""), "name": c.get("name", ""), "healthy": c["healthy"], "message": c.get("message", "")}
                for c in ms_checks
            ]
            subsystems["media_servers"] = {
                "healthy": all(c["healthy"] for c in instances),
                "instances": instances,
            }
            if not subsystems["media_servers"]["healthy"]:
                overall_healthy = False
        else:
            subsystems["media_servers"] = {
                "healthy": True,
                "instances": [],
                "message": "No media servers configured",
            }
    except Exception as exc:
        subsystems["media_servers"] = {"healthy": False, "message": str(exc)}
        overall_healthy = False

    # Whisper Backends
    try:
        from whisper import get_whisper_manager
        from db.config import get_config_entry
        whisper_enabled = get_config_entry("whisper_enabled")
        if whisper_enabled and whisper_enabled.lower() in ("true", "1", "yes"):
            wm = get_whisper_manager()
            active_backend = wm.get_active_backend()
            if active_backend and hasattr(active_backend, "health_check"):
                try:
                    w_healthy, w_msg = active_backend.health_check()
                    subsystems["whisper_backends"] = {
                        "healthy": w_healthy,
                        "active_backend": active_backend.name,
                        "message": w_msg,
                    }
                except Exception as we:
                    subsystems["whisper_backends"] = {
                        "healthy": False,
                        "active_backend": active_backend.name,
                        "message": str(we),
                    }
            else:
                subsystems["whisper_backends"] = {
                    "healthy": True,
                    "active_backend": None,
                    "message": "No active whisper backend",
                }
        else:
            subsystems["whisper_backends"] = {
                "healthy": True,
                "active_backend": None,
                "message": "Whisper disabled",
            }
    except Exception as exc:
        subsystems["whisper_backends"] = {"healthy": True, "active_backend": None, "message": str(exc)}

    # Arr Connectivity (Sonarr + Radarr instances)
    try:
        from config import get_sonarr_instances, get_radarr_instances

        sonarr_checks = []
        for inst in get_sonarr_instances():
            iname = inst.get("name", "Default")
            try:
                from sonarr_client import get_sonarr_client
                client = get_sonarr_client(instance_name=iname)
                if client:
                    h, msg = client.health_check()
                    sonarr_checks.append({"instance_name": iname, "healthy": h, "message": msg})
                else:
                    sonarr_checks.append({"instance_name": iname, "healthy": False, "message": "Client not available"})
            except Exception as se:
                sonarr_checks.append({"instance_name": iname, "healthy": False, "message": str(se)})

        radarr_checks = []
        for inst in get_radarr_instances():
            iname = inst.get("name", "Default")
            try:
                from radarr_client import get_radarr_client
                client = get_radarr_client(instance_name=iname)
                if client:
                    h, msg = client.health_check()
                    radarr_checks.append({"instance_name": iname, "healthy": h, "message": msg})
                else:
                    radarr_checks.append({"instance_name": iname, "healthy": False, "message": "Client not available"})
            except Exception as re_exc:
                radarr_checks.append({"instance_name": iname, "healthy": False, "message": str(re_exc)})

        all_arr = sonarr_checks + radarr_checks
        subsystems["arr_connectivity"] = {
            "healthy": all(c["healthy"] for c in all_arr) if all_arr else True,
            "sonarr": sonarr_checks,
            "radarr": radarr_checks,
        }
        if not subsystems["arr_connectivity"]["healthy"]:
            overall_healthy = False
    except Exception as exc:
        subsystems["arr_connectivity"] = {"healthy": False, "message": str(exc)}
        overall_healthy = False

    # Scheduler Status
    try:
        from wanted_scanner import get_scanner
        scanner = get_scanner()
        tasks = []

        # Wanted scan scheduler
        scan_running = scanner.is_scanning
        scan_interval = getattr(s, "wanted_scan_interval_hours", 0)
        tasks.append({
            "name": "wanted_scan",
            "running": scan_running,
            "last_run": scanner.last_scan_at or None,
            "interval_hours": scan_interval,
        })

        # Wanted search scheduler
        search_running = scanner.is_searching
        search_interval = getattr(s, "wanted_search_interval_hours", 0)
        tasks.append({
            "name": "wanted_search",
            "running": search_running,
            "last_run": scanner.last_search_at or None,
            "interval_hours": search_interval,
        })

        # Backup scheduler
        backup_enabled = bool(getattr(s, "backup_schedule_enabled", False))
        tasks.append({
            "name": "backup",
            "enabled": backup_enabled,
            "last_run": None,
        })

        subsystems["scheduler"] = {
            "healthy": True,
            "tasks": tasks,
        }
    except Exception as exc:
        subsystems["scheduler"] = {"healthy": True, "message": str(exc)}

    status_code = 200 if overall_healthy else 503
    return jsonify({
        "status": "healthy" if overall_healthy else "degraded",
        "subsystems": subsystems,
    }), status_code


@bp.route("/stats", methods=["GET"])
def get_stats():
    """Get overall statistics.
    ---
    get:
      tags:
        - System
      summary: Get runtime statistics
      description: Returns translation stats, pending jobs, uptime, and batch status.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: Statistics summary
          content:
            application/json:
              schema:
                type: object
                properties:
                  total_jobs:
                    type: integer
                  completed_jobs:
                    type: integer
                  pending_jobs:
                    type: integer
                  uptime_seconds:
                    type: integer
                  batch_running:
                    type: boolean
                  upgrades:
                    type: object
                  quality_warnings:
                    type: integer
    """
    from db.jobs import get_stats_summary, get_pending_job_count
    from routes.translate import batch_state, stats_lock, _memory_stats

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


@bp.route("/database/health", methods=["GET"])
def database_health():
    """Check database integrity and return stats.
    ---
    get:
      tags:
        - System
      summary: Database health check
      description: Runs SQLite integrity check and returns database statistics.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: Database is healthy
          content:
            application/json:
              schema:
                type: object
                properties:
                  healthy:
                    type: boolean
                  message:
                    type: string
                  stats:
                    type: object
                    additionalProperties: true
        503:
          description: Database integrity check failed
    """
    from database_health import check_integrity, get_database_stats
    from db import get_db
    from config import get_settings

    db = get_db()
    is_ok, message = check_integrity(db)
    stats = get_database_stats(db, get_settings().db_path)

    status_code = 200 if is_ok else 503
    return jsonify({
        "healthy": is_ok,
        "message": message,
        "stats": stats,
    }), status_code


@bp.route("/database/backup", methods=["POST"])
def create_backup():
    """Create a manual database backup.
    ---
    post:
      tags:
        - System
      summary: Create database backup
      description: Creates a manual SQLite database backup with optional label.
      security:
        - apiKeyAuth: []
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                label:
                  type: string
                  enum: [daily, weekly, monthly]
                  default: daily
      responses:
        201:
          description: Backup created
          content:
            application/json:
              schema:
                type: object
                properties:
                  path:
                    type: string
                  size_bytes:
                    type: integer
                  label:
                    type: string
    """
    from database_backup import DatabaseBackup
    from config import get_settings

    s = get_settings()
    backup = DatabaseBackup(
        db_path=s.db_path,
        backup_dir=s.backup_dir,
        retention_daily=s.backup_retention_daily,
        retention_weekly=s.backup_retention_weekly,
        retention_monthly=s.backup_retention_monthly,
    )
    data = request.get_json() or {}
    label = data.get("label", "daily")
    if label not in ("daily", "weekly", "monthly"):
        label = "daily"

    result = backup.create_backup(label=label)
    backup.rotate()
    return jsonify(result), 201


@bp.route("/database/backups", methods=["GET"])
def list_backups():
    """List all available database backups.
    ---
    get:
      tags:
        - System
      summary: List database backups
      description: Returns a list of all available SQLite database backup files.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: List of backups
          content:
            application/json:
              schema:
                type: object
                properties:
                  backups:
                    type: array
                    items:
                      type: object
                      properties:
                        filename:
                          type: string
                        size_bytes:
                          type: integer
                        created_at:
                          type: string
    """
    from database_backup import DatabaseBackup
    from config import get_settings

    s = get_settings()
    backup = DatabaseBackup(db_path=s.db_path, backup_dir=s.backup_dir)
    return jsonify({"backups": backup.list_backups()})


@bp.route("/database/restore", methods=["POST"])
def restore_backup():
    """Restore the database from a backup file.
    ---
    post:
      tags:
        - System
      summary: Restore database from backup
      description: Restores the SQLite database from a previously created backup file. Requires explicit confirmation.
      security:
        - apiKeyAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [filename, confirm]
              properties:
                filename:
                  type: string
                  description: Backup filename to restore from
                confirm:
                  type: boolean
                  description: Must be true to proceed with restore
      responses:
        200:
          description: Database restored successfully
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                  restored_from:
                    type: string
        400:
          description: Missing filename or confirmation
    """
    from database_backup import DatabaseBackup
    from db import get_db, close_db
    from config import get_settings

    data = request.get_json() or {}
    filename = data.get("filename", "")
    confirm = data.get("confirm", False)

    if not filename:
        return jsonify({"error": "filename is required"}), 400
    if not confirm:
        return jsonify({"error": "Add confirm: true to proceed"}), 400

    s = get_settings()
    backup = DatabaseBackup(db_path=s.db_path, backup_dir=s.backup_dir)
    backup_path = os.path.join(s.backup_dir, filename)

    # Close the current connection before restore
    close_db()

    result = backup.restore_backup(backup_path)

    # Re-open connection
    get_db()

    return jsonify(result)


# ── ZIP Full Backup ────────────────────────────────────────────────────────────


@bp.route("/backup/full", methods=["POST"])
def create_full_backup():
    """Create a full ZIP backup containing manifest, config, and database.
    ---
    post:
      tags:
        - System
      summary: Create full ZIP backup
      description: Creates a ZIP archive containing manifest.json, config.json, and the SQLite database.
      security:
        - apiKeyAuth: []
      responses:
        201:
          description: Full backup created
          content:
            application/json:
              schema:
                type: object
                properties:
                  filename:
                    type: string
                  size_bytes:
                    type: integer
                  created_at:
                    type: string
                    format: date-time
                  contents:
                    type: array
                    items:
                      type: string
    """
    from database_backup import DatabaseBackup
    from config import get_settings

    s = get_settings()
    backup = DatabaseBackup(
        db_path=s.db_path,
        backup_dir=s.backup_dir,
        retention_daily=s.backup_retention_daily,
        retention_weekly=s.backup_retention_weekly,
        retention_monthly=s.backup_retention_monthly,
    )

    # Step 1: Create DB backup
    db_result = backup.create_backup(label="manual")
    db_backup_path = db_result["path"]

    # Step 2: Build config export
    safe_config = s.get_safe_config()

    # Step 3: Create ZIP in memory
    buffer = io.BytesIO()
    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y%m%d_%H%M%S")

    db_backend = db_result.get("backend", "sqlite")
    db_archive_name = "sublarr.db" if db_backend == "sqlite" else "sublarr.pgdump"
    contents = ["manifest.json", "config.json", db_archive_name]
    manifest = {
        "version": __version__,
        "created_at": now.isoformat(),
        "schema_version": 1,
        "contents": contents,
        "db_backend": db_backend,
    }

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        zf.writestr("config.json", json.dumps(safe_config, indent=2))
        zf.write(db_backup_path, db_archive_name)

    buffer.seek(0)

    # Step 4: Save ZIP to backup_dir
    zip_filename = f"sublarr_full_{timestamp}.zip"
    zip_path = os.path.join(s.backup_dir, zip_filename)
    with open(zip_path, "wb") as f:
        f.write(buffer.getvalue())

    size_bytes = os.path.getsize(zip_path)
    logger.info("Full ZIP backup created: %s (%d bytes)", zip_path, size_bytes)

    return jsonify({
        "filename": zip_filename,
        "size_bytes": size_bytes,
        "created_at": now.isoformat(),
        "contents": contents,
    }), 201


@bp.route("/backup/full/download/<filename>", methods=["GET"])
def download_full_backup(filename):
    """Download a ZIP backup file.
    ---
    get:
      tags:
        - System
      summary: Download a ZIP backup
      description: Downloads a previously created full ZIP backup file.
      security:
        - apiKeyAuth: []
      parameters:
        - in: path
          name: filename
          required: true
          schema:
            type: string
          description: ZIP backup filename
      responses:
        200:
          description: ZIP file download
          content:
            application/zip:
              schema:
                type: string
                format: binary
        400:
          description: Invalid filename
        404:
          description: Backup file not found
    """
    from config import get_settings

    # Security: validate filename
    if not filename.endswith(".zip") or "/" in filename or "\\" in filename or ".." in filename:
        return jsonify({"error": "Invalid filename"}), 400

    s = get_settings()
    zip_path = os.path.join(s.backup_dir, filename)
    if not os.path.exists(zip_path):
        return jsonify({"error": "Backup file not found"}), 404

    return send_file(zip_path, mimetype="application/zip", as_attachment=True, download_name=filename)


@bp.route("/backup/full/restore", methods=["POST"])
def restore_full_backup():
    """Restore from a full ZIP backup (config + database).
    ---
    post:
      tags:
        - System
      summary: Restore from full ZIP backup
      description: Uploads and restores a full ZIP backup containing config and database. Secrets are skipped during config import.
      security:
        - apiKeyAuth: []
      requestBody:
        required: true
        content:
          multipart/form-data:
            schema:
              type: object
              properties:
                file:
                  type: string
                  format: binary
                  description: ZIP backup file
      responses:
        200:
          description: Backup restored
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                  config_imported:
                    type: array
                    items:
                      type: string
                  db_restored:
                    type: boolean
        400:
          description: Invalid or missing file
    """
    from database_backup import DatabaseBackup
    from db import get_db, close_db
    from db.config import save_config_entry, get_all_config_entries
    from config import Settings, get_settings, reload_settings

    if "file" not in request.files:
        return jsonify({"error": "No file uploaded. Use multipart/form-data with key 'file'"}), 400

    file = request.files["file"]

    # Validate ZIP
    file_stream = io.BytesIO(file.read())
    if not zipfile.is_zipfile(file_stream):
        return jsonify({"error": "Uploaded file is not a valid ZIP archive"}), 400

    file_stream.seek(0)

    try:
        with zipfile.ZipFile(file_stream, "r") as zf:
            # Read and validate manifest
            if "manifest.json" not in zf.namelist():
                return jsonify({"error": "ZIP missing manifest.json"}), 400

            manifest = json.loads(zf.read("manifest.json"))
            if manifest.get("schema_version") != 1:
                return jsonify({"error": f"Unsupported schema_version: {manifest.get('schema_version')}"}), 400

            s = get_settings()
            imported_keys = []
            db_restored = False

            # Import config if present
            if "config.json" in zf.namelist():
                config_data = json.loads(zf.read("config.json"))
                valid_keys = set(Settings.model_fields.keys()) if hasattr(Settings, "model_fields") else set()
                secret_keys = {"api_key", "sonarr_api_key", "radarr_api_key", "jellyfin_api_key",
                               "opensubtitles_api_key", "opensubtitles_password",
                               "jimaku_api_key", "subdl_api_key", "tmdb_api_key", "tvdb_api_key", "tvdb_pin"}

                for key, value in config_data.items():
                    if key in secret_keys:
                        continue
                    if str(value) == "***configured***":
                        continue
                    if not valid_keys or key in valid_keys:
                        save_config_entry(key, str(value))
                        imported_keys.append(key)

            # Restore DB if present (dialect-aware via manifest)
            backup_backend = manifest.get("db_backend", "sqlite")
            db_archive_name = "sublarr.pgdump" if backup_backend == "postgresql" else "sublarr.db"
            suffix = ".pgdump" if backup_backend == "postgresql" else ".db"

            if db_archive_name in zf.namelist():
                import tempfile
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    tmp.write(zf.read(db_archive_name))
                    tmp_path = tmp.name

                try:
                    backup = DatabaseBackup(db_path=s.db_path, backup_dir=s.backup_dir)
                    close_db()
                    backup.restore_backup(tmp_path)
                    get_db()
                    db_restored = True
                finally:
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass

            # Reload settings with DB overrides
            all_overrides = get_all_config_entries()
            reload_settings(all_overrides)

            # Invalidate caches
            try:
                from sonarr_client import invalidate_client as _inv_sonarr
                from radarr_client import invalidate_client as _inv_radarr
                from mediaserver import invalidate_media_server_manager as _inv_media
                from providers import invalidate_manager as _inv_providers
                _inv_sonarr()
                _inv_radarr()
                _inv_media()
                _inv_providers()
            except Exception:
                pass

            logger.info("Full backup restored: config=%s, db=%s", imported_keys, db_restored)

            return jsonify({
                "status": "restored",
                "config_imported": imported_keys,
                "db_restored": db_restored,
            })

    except (json.JSONDecodeError, KeyError, zipfile.BadZipFile) as exc:
        return jsonify({"error": f"Invalid backup file: {exc}"}), 400


@bp.route("/backup/full/list", methods=["GET"])
def list_full_backups():
    """List all ZIP backup files.
    ---
    get:
      tags:
        - System
      summary: List full ZIP backups
      description: Returns a list of all full ZIP backup files with metadata.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: List of ZIP backups
          content:
            application/json:
              schema:
                type: object
                properties:
                  backups:
                    type: array
                    items:
                      type: object
                      properties:
                        filename:
                          type: string
                        size_bytes:
                          type: integer
                        created_at:
                          type: string
                          format: date-time
    """
    from config import get_settings

    s = get_settings()
    backups = []

    if not os.path.isdir(s.backup_dir):
        return jsonify({"backups": []})

    for name in sorted(os.listdir(s.backup_dir), reverse=True):
        if not name.endswith(".zip"):
            continue
        path = os.path.join(s.backup_dir, name)
        try:
            size = os.path.getsize(path)
        except OSError:
            size = 0
        # Parse timestamp from filename: sublarr_full_YYYYMMDD_HHMMSS.zip
        created_at = ""
        if name.startswith("sublarr_full_") and len(name) >= 30:
            ts_part = name[len("sublarr_full_"):].replace(".zip", "")
            try:
                dt = datetime.strptime(ts_part, "%Y%m%d_%H%M%S")
                created_at = dt.replace(tzinfo=timezone.utc).isoformat()
            except ValueError:
                created_at = ""
        backups.append({
            "filename": name,
            "size_bytes": size,
            "created_at": created_at,
        })

    return jsonify({"backups": backups})


# ── Statistics ─────────────────────────────────────────────────────────────────


@bp.route("/statistics", methods=["GET"])
def get_statistics():
    """Get comprehensive statistics with time range filter.
    ---
    get:
      tags:
        - System
      summary: Get comprehensive statistics
      description: Returns daily stats, provider stats, download counts, backend stats, upgrades, and format breakdown.
      security:
        - apiKeyAuth: []
      parameters:
        - in: query
          name: range
          schema:
            type: string
            enum: ["7d", "30d", "90d", "365d"]
            default: "30d"
          description: Time range for statistics
      responses:
        200:
          description: Statistics data
          content:
            application/json:
              schema:
                type: object
                properties:
                  daily:
                    type: array
                    items:
                      type: object
                  providers:
                    type: object
                    additionalProperties: true
                  downloads_by_provider:
                    type: array
                    items:
                      type: object
                  backend_stats:
                    type: array
                    items:
                      type: object
                  upgrades:
                    type: array
                    items:
                      type: object
                  by_format:
                    type: object
                    additionalProperties:
                      type: integer
                  range:
                    type: string
    """
    from db import get_db, _db_lock
    from db.providers import get_provider_stats

    range_param = request.args.get("range", "30d")
    range_map = {"7d": 7, "30d": 30, "90d": 90, "365d": 365}
    days = range_map.get(range_param, 30)

    db = get_db()

    # Daily stats
    with _db_lock:
        daily_rows = db.execute(
            text("SELECT * FROM daily_stats ORDER BY date DESC LIMIT :days"), {"days": days}
        ).fetchall()
    daily = []
    by_format_totals: dict = {}
    for row in daily_rows:
        d = row._mapping
        daily.append({
            "date": d["date"],
            "translated": d["translated"],
            "failed": d["failed"],
            "skipped": d["skipped"],
        })
        # Aggregate per-format totals across all days
        fmt_json = d.get("by_format_json", '{"ass": 0, "srt": 0}')
        try:
            fmt = json.loads(fmt_json) if isinstance(fmt_json, str) else {}
        except (json.JSONDecodeError, TypeError):
            fmt = {}
        for k, v in fmt.items():
            by_format_totals[k] = by_format_totals.get(k, 0) + (v or 0)

    # Provider stats (all providers)
    providers = get_provider_stats()

    # Downloads by provider
    with _db_lock:
        dl_rows = db.execute(
            text("""SELECT provider_name, COUNT(*) as count, AVG(score) as avg_score
               FROM subtitle_downloads GROUP BY provider_name""")
        ).fetchall()
    downloads_by_provider = [
        {"provider_name": row[0], "count": row[1], "avg_score": round(row[2] or 0, 1)}
        for row in dl_rows
    ]

    # Translation backend stats
    with _db_lock:
        backend_rows = db.execute(text("SELECT * FROM translation_backend_stats")).fetchall()
    backend_stats = [dict(row._mapping) for row in backend_rows]

    # Upgrade history summary
    with _db_lock:
        upgrade_rows = db.execute(
            text("""SELECT old_format || ' -> ' || new_format as upgrade_type, COUNT(*) as count
               FROM upgrade_history GROUP BY upgrade_type""")
        ).fetchall()
    upgrades = [{"type": row[0], "count": row[1]} for row in upgrade_rows]

    return jsonify({
        "daily": daily,
        "providers": providers,
        "downloads_by_provider": downloads_by_provider,
        "backend_stats": backend_stats,
        "upgrades": upgrades,
        "by_format": by_format_totals,
        "range": range_param,
    })


@bp.route("/statistics/export", methods=["GET"])
def export_statistics():
    """Export statistics as JSON or CSV file download.
    ---
    get:
      tags:
        - System
      summary: Export statistics
      description: Downloads statistics as JSON or CSV file for the specified time range.
      security:
        - apiKeyAuth: []
      parameters:
        - in: query
          name: range
          schema:
            type: string
            enum: ["7d", "30d", "90d", "365d"]
            default: "30d"
          description: Time range for export
        - in: query
          name: format
          schema:
            type: string
            enum: [json, csv]
            default: json
          description: Export file format
      responses:
        200:
          description: File download
          content:
            application/json:
              schema:
                type: string
                format: binary
            text/csv:
              schema:
                type: string
                format: binary
    """
    from db import get_db, _db_lock
    from db.providers import get_provider_stats

    range_param = request.args.get("range", "30d")
    export_format = request.args.get("format", "json")
    range_map = {"7d": 7, "30d": 30, "90d": 90, "365d": 365}
    days = range_map.get(range_param, 30)

    db = get_db()

    # Fetch daily stats
    with _db_lock:
        daily_rows = db.execute(
            text("SELECT * FROM daily_stats ORDER BY date DESC LIMIT :days"), {"days": days}
        ).fetchall()
    daily = []
    for row in daily_rows:
        d = row._mapping
        daily.append({
            "date": d["date"],
            "translated": d["translated"],
            "failed": d["failed"],
            "skipped": d["skipped"],
        })

    today = datetime.now(timezone.utc).strftime("%Y%m%d")

    if export_format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["date", "translated", "failed", "skipped"])
        for row in daily:
            writer.writerow([row["date"], row["translated"], row["failed"], row["skipped"]])

        csv_bytes = output.getvalue().encode("utf-8")
        buf = io.BytesIO(csv_bytes)
        return send_file(
            buf,
            mimetype="text/csv",
            as_attachment=True,
            download_name=f"sublarr_stats_{today}.csv",
        )
    else:
        # JSON export with full data
        providers = get_provider_stats()
        with _db_lock:
            dl_rows = db.execute(
                text("""SELECT provider_name, COUNT(*) as count, AVG(score) as avg_score
                   FROM subtitle_downloads GROUP BY provider_name""")
            ).fetchall()
        downloads_by_provider = [
            {"provider": row[0], "count": row[1], "avg_score": round(row[2] or 0, 1)}
            for row in dl_rows
        ]

        stats_data = {
            "daily": daily,
            "providers": providers,
            "downloads_by_provider": downloads_by_provider,
            "range": range_param,
            "exported_at": datetime.now(timezone.utc).isoformat(),
        }

        json_bytes = json.dumps(stats_data, indent=2).encode("utf-8")
        buf = io.BytesIO(json_bytes)
        return send_file(
            buf,
            mimetype="application/json",
            as_attachment=True,
            download_name=f"sublarr_stats_{today}.json",
        )


# ── Log Download / Rotation ───────────────────────────────────────────────────


@bp.route("/logs/download", methods=["GET"])
def download_logs():
    """Download the log file as an attachment.
    ---
    get:
      tags:
        - System
      summary: Download log file
      description: Downloads the Sublarr log file as a text attachment.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: Log file download
          content:
            text/plain:
              schema:
                type: string
                format: binary
        404:
          description: Log file not found
    """
    from config import get_settings

    log_file = get_settings().log_file
    if not os.path.exists(log_file):
        return jsonify({"error": "Log file not found"}), 404

    return send_file(log_file, mimetype="text/plain", as_attachment=True, download_name="sublarr.log")


@bp.route("/logs/rotation", methods=["GET"])
def get_log_rotation():
    """Get current log rotation configuration.
    ---
    get:
      tags:
        - System
      summary: Get log rotation config
      description: Returns current log rotation settings (max size and backup count).
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: Log rotation configuration
          content:
            application/json:
              schema:
                type: object
                properties:
                  max_size_mb:
                    type: integer
                  backup_count:
                    type: integer
    """
    from db.config import get_config_entry

    max_size_mb = int(get_config_entry("log_max_size_mb") or "10")
    backup_count = int(get_config_entry("log_backup_count") or "5")

    return jsonify({
        "max_size_mb": max_size_mb,
        "backup_count": backup_count,
    })


@bp.route("/logs/rotation", methods=["PUT"])
def update_log_rotation():
    """Update log rotation configuration.
    ---
    put:
      tags:
        - System
      summary: Update log rotation config
      description: Updates log rotation settings. Changes take effect on next application restart.
      security:
        - apiKeyAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                max_size_mb:
                  type: integer
                  minimum: 1
                  maximum: 100
                  description: Maximum log file size in MB
                backup_count:
                  type: integer
                  minimum: 1
                  maximum: 20
                  description: Number of rotated log files to keep
      responses:
        200:
          description: Configuration updated
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                  max_size_mb:
                    type: integer
                  backup_count:
                    type: integer
                  note:
                    type: string
        400:
          description: Invalid parameter values
    """
    from db.config import save_config_entry

    data = request.get_json() or {}
    max_size_mb = data.get("max_size_mb")
    backup_count = data.get("backup_count")

    errors = []
    if max_size_mb is not None:
        if not isinstance(max_size_mb, (int, float)) or max_size_mb < 1 or max_size_mb > 100:
            errors.append("max_size_mb must be between 1 and 100")
    if backup_count is not None:
        if not isinstance(backup_count, (int, float)) or backup_count < 1 or backup_count > 20:
            errors.append("backup_count must be between 1 and 20")

    if errors:
        return jsonify({"error": "; ".join(errors)}), 400

    if max_size_mb is not None:
        save_config_entry("log_max_size_mb", str(int(max_size_mb)))
    if backup_count is not None:
        save_config_entry("log_backup_count", str(int(backup_count)))

    # Read back saved values
    from db.config import get_config_entry
    saved_max = int(get_config_entry("log_max_size_mb") or "10")
    saved_count = int(get_config_entry("log_backup_count") or "5")

    logger.info("Log rotation config updated: max_size_mb=%d, backup_count=%d", saved_max, saved_count)

    return jsonify({
        "status": "updated",
        "max_size_mb": saved_max,
        "backup_count": saved_count,
        "note": "Changes take effect on next application restart",
    })


@bp.route("/database/vacuum", methods=["POST"])
def vacuum_database():
    """Run VACUUM to reclaim unused space.
    ---
    post:
      tags:
        - System
      summary: Vacuum database
      description: Runs SQLite VACUUM command to reclaim unused disk space and defragment the database.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: Vacuum completed
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                  size_before:
                    type: integer
                  size_after:
                    type: integer
    """
    from database_health import vacuum
    from db import get_db
    from config import get_settings

    db = get_db()
    result = vacuum(db, get_settings().db_path)
    return jsonify(result)


@bp.route("/logs", methods=["GET"])
def get_logs():
    """Get recent log entries.
    ---
    get:
      tags:
        - System
      summary: Get recent logs
      description: Returns recent log entries with optional line count and level filter.
      security:
        - apiKeyAuth: []
      parameters:
        - in: query
          name: lines
          schema:
            type: integer
            default: 200
          description: Number of recent log lines to return
        - in: query
          name: level
          schema:
            type: string
            enum: [DEBUG, INFO, WARNING, ERROR, CRITICAL]
          description: Filter by log level
      responses:
        200:
          description: Log entries
          content:
            application/json:
              schema:
                type: object
                properties:
                  entries:
                    type: array
                    items:
                      type: string
                  total:
                    type: integer
    """
    from config import get_settings

    settings = get_settings()
    log_file = settings.log_file
    lines = request.args.get("lines", 200, type=int)
    level = request.args.get("level", "").upper()

    log_entries = []
    if os.path.exists(log_file):
        try:
            with open(log_file, "r", encoding="utf-8") as f:
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


@bp.route("/notifications/test", methods=["POST"])
def notification_test():
    """Send a test notification.
    ---
    post:
      tags:
        - System
      summary: Send test notification
      description: Sends a test notification via Apprise. Optionally test a specific notification URL.
      security:
        - apiKeyAuth: []
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                url:
                  type: string
                  description: Optional specific Apprise URL to test
      responses:
        200:
          description: Notification sent successfully
          content:
            application/json:
              schema:
                type: object
                properties:
                  success:
                    type: boolean
                  message:
                    type: string
        500:
          description: Notification failed
    """
    from notifier import test_notification

    data = request.get_json() or {}
    url = data.get("url")  # Optional: test a specific URL
    result = test_notification(url=url)
    status_code = 200 if result["success"] else 500
    return jsonify(result), status_code


@bp.route("/notifications/status", methods=["GET"])
def notification_status():
    """Get notification configuration status.
    ---
    get:
      tags:
        - System
      summary: Get notification status
      description: Returns whether notifications are configured and the count of notification URLs.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: Notification configuration status
          content:
            application/json:
              schema:
                type: object
                properties:
                  configured:
                    type: boolean
                  url_count:
                    type: integer
    """
    from notifier import get_notification_status
    return jsonify(get_notification_status())


@bp.route("/tasks", methods=["GET"])
def list_tasks():
    """List background scheduler tasks with status and timing info.
    ---
    get:
      tags:
        - System
      summary: List background tasks
      description: Returns all background scheduler tasks with their current status, last run time, interval, and enabled state.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: List of scheduler tasks
          content:
            application/json:
              schema:
                type: object
                properties:
                  tasks:
                    type: array
                    items:
                      type: object
                      properties:
                        name:
                          type: string
                        display_name:
                          type: string
                        running:
                          type: boolean
                        last_run:
                          type: string
                          nullable: true
                          format: date-time
                        next_run:
                          type: string
                          nullable: true
                          format: date-time
                        interval_hours:
                          type: number
                          nullable: true
                        enabled:
                          type: boolean
    """
    from config import get_settings
    from wanted_scanner import get_scanner

    s = get_settings()
    tasks = []

    try:
        scanner = get_scanner()

        # Wanted scan
        scan_interval = getattr(s, "wanted_scan_interval_hours", 6)
        scan_last = scanner.last_scan_at or None
        scan_next = None
        if scan_last and scan_interval:
            try:
                from datetime import timedelta
                last_dt = datetime.fromisoformat(str(scan_last))
                scan_next = (last_dt + timedelta(hours=scan_interval)).isoformat()
            except Exception:
                pass
        tasks.append({
            "name": "wanted_scan",
            "display_name": "Wanted Scan",
            "running": scanner.is_scanning,
            "last_run": str(scan_last) if scan_last else None,
            "next_run": scan_next,
            "interval_hours": scan_interval,
            "enabled": scan_interval > 0,
        })

        # Wanted search
        search_interval = getattr(s, "wanted_search_interval_hours", 24)
        search_last = scanner.last_search_at or None
        search_next = None
        if search_last and search_interval:
            try:
                from datetime import timedelta
                last_dt = datetime.fromisoformat(str(search_last))
                search_next = (last_dt + timedelta(hours=search_interval)).isoformat()
            except Exception:
                pass
        tasks.append({
            "name": "wanted_search",
            "display_name": "Wanted Search",
            "running": scanner.is_searching,
            "last_run": str(search_last) if search_last else None,
            "next_run": search_next,
            "interval_hours": search_interval,
            "enabled": search_interval > 0,
        })
    except Exception as exc:
        logger.warning("Failed to read scanner tasks: %s", exc)

    # Backup scheduler
    backup_enabled = bool(getattr(s, "backup_schedule_enabled", False))
    tasks.append({
        "name": "backup",
        "display_name": "Database Backup",
        "running": False,
        "last_run": None,
        "next_run": None,
        "interval_hours": 24 if backup_enabled else None,
        "enabled": backup_enabled,
    })

    return jsonify({"tasks": tasks})


@bp.route("/openapi.json", methods=["GET"])
def openapi_spec():
    """Serve the OpenAPI 3.0.3 specification as JSON."""
    from openapi import spec
    return jsonify(spec.to_dict())
