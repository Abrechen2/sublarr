"""GET /api/v1/health/detailed — authenticated per-subsystem health report."""

import logging

from flask import jsonify

from routes.system import bp

logger = logging.getLogger(__name__)


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
    from config import get_settings
    from database_health import get_health_report
    from ollama_client import check_ollama_health

    s = get_settings()
    subsystems: dict = {}
    overall_healthy = True

    # Database (dialect-aware: SQLite integrity check or PostgreSQL pg_stat)
    try:
        db_report = get_health_report()
        db_ok = db_report["status"] == "healthy"
        db_details = db_report.get("details", {})
        subsystems["database"] = {
            "healthy": db_ok,
            "backend": db_report["backend"],
            "message": db_details.get("integrity", {}).get("message", "ok")
            if db_report["backend"] == "sqlite"
            else ("ok" if db_ok else "connection failed"),
            "size_bytes": db_details.get("size_bytes", 0),
            "wal_mode": db_details.get("wal_mode", False),
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
            providers_detail.append(
                {
                    "name": name,
                    "circuit_breaker": cb_status["state"],
                    "failure_count": cb_status["failure_count"],
                }
            )
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
                    backends_health[bname] = {
                        "healthy": True,
                        "message": "No health check available",
                    }
            except Exception as be:
                backends_health[bname] = {"healthy": False, "message": str(be)}
        subsystems["translation_backends"] = {
            "healthy": any(b["healthy"] for b in backends_health.values())
            if backends_health
            else True,
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
                {
                    "type": c.get("type", ""),
                    "name": c.get("name", ""),
                    "healthy": c["healthy"],
                    "message": c.get("message", ""),
                }
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
        from db.config import get_config_entry
        from whisper import get_whisper_manager

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
        subsystems["whisper_backends"] = {
            "healthy": True,
            "active_backend": None,
            "message": str(exc),
        }

    # Arr Connectivity (Sonarr + Radarr instances)
    try:
        from config import get_radarr_instances, get_sonarr_instances

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
                    sonarr_checks.append(
                        {
                            "instance_name": iname,
                            "healthy": False,
                            "message": "Client not available",
                        }
                    )
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
                    radarr_checks.append(
                        {
                            "instance_name": iname,
                            "healthy": False,
                            "message": "Client not available",
                        }
                    )
            except Exception as re_exc:
                radarr_checks.append(
                    {"instance_name": iname, "healthy": False, "message": str(re_exc)}
                )

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
        from services.wanted_scanner import get_scanner

        scanner = get_scanner()
        tasks = []

        # Wanted scan scheduler
        scan_running = scanner.is_scanning
        scan_interval = getattr(s, "wanted_scan_interval_hours", 0)
        tasks.append(
            {
                "name": "wanted_scan",
                "running": scan_running,
                "last_run": scanner.last_scan_at or None,
                "interval_hours": scan_interval,
            }
        )

        # Wanted search scheduler
        search_running = scanner.is_searching
        search_interval = getattr(s, "wanted_search_interval_hours", 0)
        tasks.append(
            {
                "name": "wanted_search",
                "running": search_running,
                "last_run": scanner.last_search_at or None,
                "interval_hours": search_interval,
            }
        )

        # Backup scheduler
        backup_enabled = bool(getattr(s, "backup_schedule_enabled", False))
        tasks.append(
            {
                "name": "backup",
                "enabled": backup_enabled,
                "last_run": None,
            }
        )

        subsystems["scheduler"] = {
            "healthy": True,
            "tasks": tasks,
        }
    except Exception as exc:
        subsystems["scheduler"] = {"healthy": True, "message": str(exc)}

    status_code = 200 if overall_healthy else 503
    return jsonify(
        {
            "status": "healthy" if overall_healthy else "degraded",
            "subsystems": subsystems,
        }
    ), status_code
