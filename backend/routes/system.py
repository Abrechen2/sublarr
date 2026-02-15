"""System routes — /health, /stats, /database/*, /logs, /notifications/*."""

import os
import time
import logging

from flask import Blueprint, request, jsonify

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
