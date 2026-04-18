"""System health routes — /health, /update.

The /health/detailed route lives in routes/system/health_detailed.py (B1H split).
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import nullcontext as _nullcontext

from flask import current_app, jsonify, request

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
    """Return (dict of service_status entries, overall_healthy bool).

    Ollama is an optional translation backend — its unavailability never marks
    the system unhealthy (overall=None means 'informational only').
    """
    from ollama_client import check_ollama_health

    _, message = check_ollama_health()
    return {"ollama": message}, None


def _health_check_providers(app=None):
    try:
        from providers import get_provider_manager

        ctx = app.app_context() if app else _nullcontext()
        with ctx:
            manager = get_provider_manager()
            provider_statuses = manager.get_provider_status()
        # Count against ENABLED providers only — `get_provider_status` returns
        # every registered class (including plugins the user hasn't configured
        # and built-ins they've removed), which made the health dashboard read
        # "10/22 active" even when every configured provider was healthy.
        enabled = [p for p in provider_statuses if p.get("enabled")]
        total = len(enabled)
        if total == 0:
            return {"providers": "healthy"}, None
        active_count = sum(1 for p in enabled if p.get("healthy"))
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
      security: []
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

    _app = current_app._get_current_object()
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_name = {
            executor.submit(_health_check_ollama): "ollama",
            executor.submit(_health_check_providers, _app): "providers",
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
                results_by_name[name] = ({name: "error"}, None)

    for name, (part, overall) in results_by_name.items():
        service_status.update(part)
        if overall is False:  # None = optional, False = required service is down
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
      security: []
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
