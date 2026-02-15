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

bp = Blueprint("system", __name__, url_prefix="/api/v1")
logger = logging.getLogger(__name__)


@bp.route("/health", methods=["GET"])
def health():
    """Health check endpoint (no auth required)."""
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
        "version": "0.1.0",
        "services": service_status,
    }), status_code


@bp.route("/health/detailed", methods=["GET"])
def health_detailed():
    """Detailed health check with subsystem status (authenticated)."""
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

    status_code = 200 if overall_healthy else 503
    return jsonify({
        "status": "healthy" if overall_healthy else "degraded",
        "subsystems": subsystems,
    }), status_code


@bp.route("/stats", methods=["GET"])
def get_stats():
    """Get overall statistics."""
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
    """Check database integrity and return stats."""
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
    """Create a manual database backup."""
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
    """List all available database backups."""
    from database_backup import DatabaseBackup
    from config import get_settings

    s = get_settings()
    backup = DatabaseBackup(db_path=s.db_path, backup_dir=s.backup_dir)
    return jsonify({"backups": backup.list_backups()})


@bp.route("/database/restore", methods=["POST"])
def restore_backup():
    """Restore the database from a backup file.

    Body: {"filename": "sublarr_daily_20260215_030000.db", "confirm": true}
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
    """Create a full ZIP backup containing manifest, config, and database."""
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

    contents = ["manifest.json", "config.json", "sublarr.db"]
    manifest = {
        "version": "0.1.0",
        "created_at": now.isoformat(),
        "schema_version": 1,
        "contents": contents,
    }

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        zf.writestr("config.json", json.dumps(safe_config, indent=2))
        zf.write(db_backup_path, "sublarr.db")

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
    """Download a ZIP backup file."""
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
    """Restore from a full ZIP backup (config + database)."""
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

            # Restore DB if present
            if "sublarr.db" in zf.namelist():
                import tempfile
                with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp:
                    tmp.write(zf.read("sublarr.db"))
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
    """List all ZIP backup files."""
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
    """Get comprehensive statistics with time range filter."""
    from db import get_db, _db_lock
    from db.providers import get_provider_stats

    range_param = request.args.get("range", "30d")
    range_map = {"7d": 7, "30d": 30, "90d": 90, "365d": 365}
    days = range_map.get(range_param, 30)

    db = get_db()

    # Daily stats
    with _db_lock:
        daily_rows = db.execute(
            "SELECT * FROM daily_stats ORDER BY date DESC LIMIT ?", (days,)
        ).fetchall()
    daily = []
    for row in daily_rows:
        d = dict(row)
        daily.append({
            "date": d["date"],
            "translated": d["translated"],
            "failed": d["failed"],
            "skipped": d["skipped"],
        })

    # Provider stats (all providers)
    providers = get_provider_stats()

    # Downloads by provider
    with _db_lock:
        dl_rows = db.execute(
            """SELECT provider_name, COUNT(*) as count, AVG(score) as avg_score
               FROM subtitle_downloads GROUP BY provider_name"""
        ).fetchall()
    downloads_by_provider = [
        {"provider": row[0], "count": row[1], "avg_score": round(row[2] or 0, 1)}
        for row in dl_rows
    ]

    # Translation backend stats
    with _db_lock:
        backend_rows = db.execute("SELECT * FROM translation_backend_stats").fetchall()
    backend_stats = [dict(row) for row in backend_rows]

    # Upgrade history summary
    with _db_lock:
        upgrade_rows = db.execute(
            """SELECT old_format || ' -> ' || new_format as upgrade_type, COUNT(*) as count
               FROM upgrade_history GROUP BY upgrade_type"""
        ).fetchall()
    upgrades = [{"type": row[0], "count": row[1]} for row in upgrade_rows]

    return jsonify({
        "daily": daily,
        "providers": providers,
        "downloads_by_provider": downloads_by_provider,
        "backend_stats": backend_stats,
        "upgrades": upgrades,
        "range": range_param,
    })


@bp.route("/statistics/export", methods=["GET"])
def export_statistics():
    """Export statistics as JSON or CSV file download."""
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
            "SELECT * FROM daily_stats ORDER BY date DESC LIMIT ?", (days,)
        ).fetchall()
    daily = []
    for row in daily_rows:
        d = dict(row)
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
                """SELECT provider_name, COUNT(*) as count, AVG(score) as avg_score
                   FROM subtitle_downloads GROUP BY provider_name"""
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
    """Download the log file as an attachment."""
    from config import get_settings

    log_file = get_settings().log_file
    if not os.path.exists(log_file):
        return jsonify({"error": "Log file not found"}), 404

    return send_file(log_file, mimetype="text/plain", as_attachment=True, download_name="sublarr.log")


@bp.route("/logs/rotation", methods=["GET"])
def get_log_rotation():
    """Get current log rotation configuration."""
    from db.config import get_config_entry

    max_size_mb = int(get_config_entry("log_max_size_mb") or "10")
    backup_count = int(get_config_entry("log_backup_count") or "5")

    return jsonify({
        "max_size_mb": max_size_mb,
        "backup_count": backup_count,
    })


@bp.route("/logs/rotation", methods=["PUT"])
def update_log_rotation():
    """Update log rotation configuration."""
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
    """Run VACUUM to reclaim unused space."""
    from database_health import vacuum
    from db import get_db
    from config import get_settings

    db = get_db()
    result = vacuum(db, get_settings().db_path)
    return jsonify(result)


@bp.route("/logs", methods=["GET"])
def get_logs():
    """Get recent log entries."""
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
    """Send a test notification."""
    from notifier import test_notification

    data = request.get_json() or {}
    url = data.get("url")  # Optional: test a specific URL
    result = test_notification(url=url)
    status_code = 200 if result["success"] else 500
    return jsonify(result), status_code


@bp.route("/notifications/status", methods=["GET"])
def notification_status():
    """Get notification configuration status."""
    from notifier import get_notification_status
    return jsonify(get_notification_status())
