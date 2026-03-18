"""System health routes — /health, /update, /health/detailed."""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from flask import jsonify, request

from routes.system import bp
from version import __version__

logger = logging.getLogger(__name__)

# ─── Update check (GitHub releases) ──────────────────────────────────────────

_GITHUB_REPO = "Abrechen2/sublarr"
_UPDATE_CACHE_TTL = 6 * 60 * 60  # 6 hours
_update_cache: dict = {"result": None, "checked_at": None}


def _is_newer_version(tag: str, current: str) -> bool:
    """Return True if tag represents a newer stable version than current.

    Strips 'v' prefix and pre-release suffixes (e.g. -beta) before comparing
    (major, minor, patch) integer tuples. No external dependencies.
    """

    def _parse(v: str) -> tuple[int, ...]:
        v = v.lstrip("v").split("-")[0]
        try:
            return tuple(int(x) for x in v.split(".")[:3])
        except ValueError:
            return (0, 0, 0)

    return _parse(tag) > _parse(current)


def _health_check_ollama():
    """Return (dict of service_status entries, overall_healthy bool)."""
    from ollama_client import check_ollama_health

    healthy, message = check_ollama_health()
    return {"ollama": message}, healthy


def _health_check_providers():
    try:
        from providers import get_provider_manager

        manager = get_provider_manager()
        provider_statuses = manager.get_provider_status()
        total = len(provider_statuses)
        if total == 0:
            return {"providers": "healthy"}, None
        active_count = sum(1 for p in provider_statuses if p["healthy"])
        error_count = total - active_count
        if error_count == 0:
            status = "healthy"
        elif error_count == total:
            status = "error"
        else:
            status = "degraded"
        return {"providers": f"{status} ({active_count}/{total} active)"}, None
    except Exception:
        return {"providers": "error"}, None


def _health_check_sonarr():
    try:
        from sonarr_client import get_sonarr_client

        sonarr = get_sonarr_client()
        if sonarr:
            s_healthy, s_msg = sonarr.health_check()
            return {"sonarr": s_msg if s_healthy else f"unhealthy: {s_msg}"}, None
        return {"sonarr": "not configured"}, None
    except Exception:
        return {"sonarr": "error"}, None


def _health_check_radarr():
    try:
        from radarr_client import get_radarr_client

        radarr = get_radarr_client()
        if radarr:
            r_healthy, r_msg = radarr.health_check()
            return {"radarr": r_msg if r_healthy else f"unhealthy: {r_msg}"}, None
        return {"radarr": "not configured"}, None
    except Exception:
        return {"radarr": "error"}, None


def _health_check_media_servers():
    try:
        from mediaserver import get_media_server_manager

        manager = get_media_server_manager()
        ms_health = manager.health_check_all()
        if ms_health:
            healthy_count = sum(1 for h in ms_health if h["healthy"])
            out = {"media_servers": f"{healthy_count}/{len(ms_health)} healthy"}
            for h in ms_health:
                key = f"media_server:{h['name']}"
                out[key] = h["message"] if h["healthy"] else f"unhealthy: {h['message']}"
            return out, None
        return {"media_servers": "none configured"}, None
    except Exception:
        return {"media_servers": "error"}, None


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
    service_status = {}
    healthy = True
    results_by_name = {}

    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_name = {
            executor.submit(_health_check_ollama): "ollama",
            executor.submit(_health_check_providers): "providers",
            executor.submit(_health_check_sonarr): "sonarr",
            executor.submit(_health_check_radarr): "radarr",
            executor.submit(_health_check_media_servers): "media_servers",
        }
        for fut in as_completed(future_to_name):
            name = future_to_name[fut]
            try:
                part, overall = fut.result()
                results_by_name[name] = (part, overall)
            except Exception as exc:
                logger.debug("Health check %s failed: %s", name, exc)
                results_by_name[name] = ({name: "error"}, False if name == "ollama" else None)

    for name, (part, overall) in results_by_name.items():
        service_status.update(part)
        if name == "ollama" and overall is False:
            healthy = False

    status_code = 200 if healthy else 503

    # Include version and service detail only for authenticated callers.
    # Unauthenticated probes (uptime monitors, scanners) receive only the status.
    import hmac as _hmac

    from flask import session as _session

    from config import get_settings as _get_settings

    _settings = _get_settings()
    _api_key = getattr(_settings, "api_key", None)
    _provided = request.headers.get("X-Api-Key") or request.args.get("apikey", "")
    _key_ok = bool(_api_key and _hmac.compare_digest(_provided, _api_key))
    _session_ok = bool(_session.get("ui_authenticated"))
    _authenticated = _key_ok or _session_ok or not _api_key

    body: dict = {"status": "healthy" if healthy else "unhealthy"}
    if _authenticated:
        body["version"] = __version__
        body["services"] = service_status

    return jsonify(body), status_code


@bp.route("/update", methods=["GET"])
def check_update():
    """Check GitHub for a newer stable release.

    Result is cached for 6 hours. Never raises — returns available=false on
    any error so the UI degrades gracefully.
    ---
    get:
      tags:
        - System
      summary: Check for updates
      description: Checks GitHub releases for a newer stable version. Cached for 6 hours.
      responses:
        200:
          description: Update check result
          content:
            application/json:
              schema:
                type: object
                properties:
                  available:
                    type: boolean
                  latest:
                    type: string
                    nullable: true
                  current:
                    type: string
                  url:
                    type: string
                    nullable: true
    """
    global _update_cache

    now = time.time()
    cached = _update_cache
    if (
        cached["result"] is not None
        and cached["checked_at"] is not None
        and now - cached["checked_at"] < _UPDATE_CACHE_TTL
    ):
        return jsonify(cached["result"])

    fallback = {"available": False, "latest": None, "current": __version__, "url": None}
    try:
        import requests as _req

        resp = _req.get(
            f"https://api.github.com/repos/{_GITHUB_REPO}/releases/latest",
            timeout=5,
            headers={"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"},
        )
        if resp.status_code == 200:
            data = resp.json()
            tag = data.get("tag_name", "")
            url = data.get("html_url", "")
            # Skip pre-releases (the /releases/latest endpoint already excludes them,
            # but guard explicitly in case that changes)
            if tag and not data.get("prerelease", False):
                result: dict = {
                    "available": _is_newer_version(tag, __version__),
                    "latest": tag,
                    "current": __version__,
                    "url": url,
                }
            else:
                result = fallback
        else:
            result = fallback
    except Exception:
        result = fallback

    _update_cache = {"result": result, "checked_at": now}
    return jsonify(result)


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
        from wanted_scanner import get_scanner

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
