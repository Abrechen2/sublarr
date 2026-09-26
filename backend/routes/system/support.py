"""Support-bundle routes — anonymized log export + diagnostic report.

Routes:
  /api/v1/logs/support-export  — Download an anonymized support ZIP
  /api/v1/logs/support-preview — JSON preview of what the export would contain

Log reading and anonymization live in ``support_logs``, the diagnostic sections
in ``support_sections`` and the allow-list config snapshot in
``support_config``. Tests reach ``_anonymize`` / ``_build_diagnostic`` via
``from routes.system import ...`` — the re-export in ``routes/system/__init__.py``
keeps that contract.
"""

from __future__ import annotations

import json
import logging
import platform
import tempfile
import threading
import time
import zipfile
from datetime import UTC, datetime

from flask import jsonify, request, send_file

from extensions import limiter
from routes.system import bp
from routes.system.support_logs import (  # noqa: F401 — _anonymize is re-exported
    _anonymize,
    _extract_top_errors,
    current_hostname,
    payload_summary,
    plan_log_payload,
    recent_warnings,
    redaction_summary,
    write_log_member,
)

logger = logging.getLogger(__name__)

# Building a bundle reads every rotated log file; six a minute is far more than
# a person clicking "export" needs and far less than a loop can do damage with.
SUPPORT_RATE_LIMIT = "6 per minute"
# The preview re-reads the whole log history; the dialog is often reopened.
PREVIEW_CACHE_TTL_S = 30.0
# The ZIP stays in memory up to this size, then spills to a temp file.
_SPOOL_MAX_MEMORY = 8 * 1024 * 1024

_preview_lock = threading.Lock()
_preview_cache: dict = {"expires": 0.0, "data": None}


def _reset_preview_cache() -> None:
    """Drop the cached preview (tests, and after anything that changes it)."""
    with _preview_lock:
        _preview_cache["expires"] = 0.0
        _preview_cache["data"] = None


# ─── Diagnostic helpers ───────────────────────────────────────────────────────


def _get_last_scan_minutes() -> int | None:
    """Return minutes since last wanted scan, or None if unknown."""
    from db.repositories.config import ConfigRepository

    try:
        # Repositories take no session argument; passing one raised TypeError
        # here on every call, so this field was always None.
        val = ConfigRepository().get_all_config_entries().get("last_scan_timestamp")
        if not val:
            return None
        delta = datetime.now(UTC) - datetime.fromisoformat(val)
        return int(delta.total_seconds() / 60)
    except Exception as exc:  # noqa: BLE001 — a diagnostic field, not a failure
        logger.debug("last scan timestamp unavailable: %s", exc)
        return None


def _build_diagnostic() -> dict:
    """Build the diagnostic data dict. Used by both the preview endpoint and the ZIP report.

    Never raises — all errors are caught and reflected in the returned dict.
    """
    from version import __version__ as _ver

    diag: dict = {
        "version": _ver,
        "timestamp_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "uptime_minutes": None,
        "memory_mb": None,
    }

    # Process uptime + memory via psutil (optional dependency)
    try:
        import psutil

        proc = psutil.Process()
        diag["uptime_minutes"] = int((time.time() - proc.create_time()) / 60)
        diag["memory_mb"] = round(proc.memory_info().rss / 1024 / 1024, 1)
    except Exception as exc:  # noqa: BLE001 — psutil missing or failing: fields stay None
        logger.debug("psutil process stats unavailable: %s", exc)

    # Wanted + translation stats from DB
    try:
        from sqlalchemy import func, select

        from db import get_db
        from db.models.core import WantedItem
        from db.repositories.config import ConfigRepository
        from db.repositories.translation import TranslationRepository

        db = get_db()
        rows = db.execute(
            select(WantedItem.status, func.count().label("cnt")).group_by(WantedItem.status)
        ).all()
        counts_by_status = {row[0]: row[1] for row in rows}
        diag["wanted"] = {
            "total": sum(counts_by_status.values()),
            "pending": counts_by_status.get("wanted", 0),
            "extracted": counts_by_status.get("extracted", 0),
            "failed": counts_by_status.get("failed", 0),
        }
        # No session argument — see _get_last_scan_minutes. Passing one made
        # every bundle report these stats as "unavailable".
        rows = TranslationRepository().get_backend_stats()
        diag["translations"] = {
            "total_requests": sum(r.get("total_requests", 0) or 0 for r in rows),
            "successful": sum(r.get("successful_translations", 0) or 0 for r in rows),
            "failed": sum(r.get("failed_translations", 0) or 0 for r in rows),
        }
        diag["config_entries_count"] = len(ConfigRepository().get_all_config_entries())
    except Exception as exc:
        logger.warning("_build_diagnostic: DB query failed: %s", exc)
        diag["db_stats_error"] = "unavailable"

    # Provider status — `active` is "initialised in the running manager". It
    # used to be `not providers_enabled or name in providers_enabled`, and an
    # empty setting (the default: "all allowed") listed every provider as
    # active, including the unconfigured ones.
    try:
        from routes.system.support_sections import provider_rows

        diag["provider_status"] = provider_rows()
    except Exception as exc:
        logger.warning("_build_diagnostic: provider status failed: %s", exc)
        diag["provider_status"] = []

    diag["last_scan_ago_minutes"] = _get_last_scan_minutes()
    diag["top_errors"] = _extract_top_errors()

    return diag


# ─── Authorization ────────────────────────────────────────────────────────────


def _is_support_caller_authorized() -> bool:
    """Allow API-key holders, UI sessions, trusted-proxy SSO, or open deployments.

    Centralised so /support-export and /support-preview can't drift apart.
    The "fully-open" branch requires BOTH api_key AND ui_auth_enabled to
    be unset — when either is configured, the caller must authenticate.
    Pre-2026-04-30 the checks ignored ui_auth_enabled, leaking the
    support bundle to unauthenticated probes when api_key="" but UI auth
    was on (same auth-layer-composition bug as /auth/bootstrap and
    /health). See `project_2026_04_30_health_audit.md`.

    Reverse-proxy header auth (Authelia/authentik) is accepted on the same
    terms as the global middleware in auth.py/ui_auth.py: without it, an SSO
    user who passes every other route got a 401 here and nowhere else.
    """
    import hmac as _hmac

    from flask import session as _session

    import ui_auth as _ui_auth
    from config import get_settings
    from proxy_auth import request_has_valid_proxy_auth

    s = get_settings()
    api_key = getattr(s, "api_key", None)
    provided = request.headers.get("X-Api-Key") or request.args.get("apikey", "")
    if api_key and _hmac.compare_digest(provided, api_key):
        return True
    if _session.get("ui_authenticated"):
        return True
    if request_has_valid_proxy_auth():
        return True
    try:
        ui_auth_on = _ui_auth.is_ui_auth_enabled()
    except Exception as exc:  # noqa: BLE001 — fail closed only when a key exists
        logger.warning("support auth: could not read ui_auth state: %s", exc)
        ui_auth_on = False
    # Fully-open deployment: nothing protects /api/v1/* anyway.
    return not api_key and not ui_auth_on


# ─── Report rendering ─────────────────────────────────────────────────────────


def _render_report(diag: dict, sections: dict, payload: dict, warnings_count: int) -> str:
    lines = [
        "# Sublarr Support Report",
        "",
        f"**Version:** {diag.get('version', '?')}  ",
        f"**Generated:** {diag.get('timestamp_utc', '?')}  ",
        f"**Uptime:** {diag.get('uptime_minutes', 'N/A')} min  ",
        f"**Memory:** {diag.get('memory_mb', 'N/A')} MB  ",
        "",
        "## Log payload",
        "",
        f"- {payload['files_included']} file(s), {payload['included_bytes']} of "
        f"{payload['total_bytes']} bytes (cap {payload['cap_bytes']})",
    ]
    if payload["truncated"]:
        lines.append(
            "- **Truncated:** older log history did not fit into the bundle "
            f"(partial: {', '.join(payload['partial_files']) or '-'}; "
            f"skipped: {', '.join(payload['skipped_files']) or '-'})"
        )
    lines.append(f"- recent-warnings.log: {warnings_count} line(s)")
    lines += ["", "## Top Errors (last 24h)", ""]
    for e in diag.get("top_errors", []):
        lines.append(f"- **{e['message']}** (x{e['count']}, last: {e['last_seen']})")
    if not diag.get("top_errors"):
        lines.append("_No errors in the last 24h_")
    lines += ["", "## Provider Status", ""]
    for p in diag.get("provider_status", []):
        state = "active" if p.get("active") else "inactive"
        breaker = p.get("circuit_state") or "-"
        lines.append(f"- {state}: {p['name']} (circuit: {breaker})")
    lines += ["", "## Stats", "", "| Metric | Value |", "|--------|-------|"]
    for k, v in diag.get("wanted", {}).items():
        lines.append(f"| Wanted {k} | {v} |")
    for k, v in diag.get("translations", {}).items():
        lines.append(f"| Translations {k} | {v} |")
    lines += ["", "## Sections", ""]
    for name, data in sections.items():
        if "unavailable" in data:
            lines.append(f"- {name}: unavailable: {data['unavailable']}")
        else:
            lines.append(f"- {name}: see sections.json")
    return "\n".join(lines)


# ─── Endpoints ────────────────────────────────────────────────────────────────


@bp.route("/logs/support-export", methods=["GET"])
@limiter.limit(SUPPORT_RATE_LIMIT)
def support_export():
    """Download an anonymized support bundle (log files + system info) as a ZIP.

    Sensitive data is stripped before export:
    - Configured secrets and credential shapes replaced with ***REDACTED***
    - Local file paths shortened to filename only
    - IPv4 addresses replaced with x.x.x.x
    - Usernames and email addresses replaced with ***USER***
    Log history is capped (newest first); the report says when it was cut.
    ---
    get:
      tags:
        - System
      summary: Download anonymized support bundle
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: ZIP file with anonymized logs and system info
        401:
          description: Not authenticated
        429:
          description: Rate limit exceeded
    """
    from app_logging import rotated_log_candidates
    from config import get_settings
    from routes.system.support_config import build_config_snapshot
    from routes.system.support_sections import collect_sections
    from version import __version__

    if not _is_support_caller_authorized():
        return jsonify({"error": "Unauthorized"}), 401

    settings = get_settings()
    candidates = rotated_log_candidates(settings)
    ts = datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%SZ")
    hostname = current_hostname()
    plan = plan_log_payload(candidates)
    payload = payload_summary(plan)

    spool = tempfile.SpooledTemporaryFile(max_size=_SPOOL_MAX_MEMORY)  # noqa: SIM115 — send_file closes it
    try:
        with zipfile.ZipFile(spool, "w", zipfile.ZIP_DEFLATED) as zf:
            # 1. Anonymized log files, streamed — never whole files in memory
            for entry in plan["files"]:
                try:
                    write_log_member(zf, entry, hostname)
                except FileNotFoundError:
                    continue  # rotated away between planning and reading

            warnings = recent_warnings(candidates, hostname)
            zf.writestr("recent-warnings.log", "".join(warnings))

            diag = _build_diagnostic()
            sections = collect_sections()
            zf.writestr(
                "diagnostic-report.md", _render_report(diag, sections, payload, len(warnings))
            )
            zf.writestr("sections.json", json.dumps(sections, indent=2, default=str))
            zf.writestr(
                "db-stats.json",
                json.dumps(
                    {
                        "wanted": diag.get("wanted", {}),
                        "translations": diag.get("translations", {}),
                        "providers": {
                            "active": sum(
                                1 for p in diag.get("provider_status", []) if p.get("active")
                            ),
                            "last_scan_ago_minutes": diag.get("last_scan_ago_minutes"),
                        },
                        "config_entries": diag.get("config_entries_count"),
                        "last_errors": [e["message"] for e in diag.get("top_errors", [])[:5]],
                        "log_payload": payload,
                    },
                    indent=2,
                ),
            )
            # Allow-list snapshot: see routes/system/support_config.py.
            zf.writestr(
                "config-snapshot.json",
                json.dumps(build_config_snapshot(settings), indent=2, default=str),
            )
            zf.writestr(
                "system-info.txt",
                "\n".join(
                    [
                        f"Sublarr Version: {__version__}",
                        f"Python: {platform.python_version()}",
                        f"OS: {platform.system()} {platform.release()}",
                        f"Export Timestamp (UTC): {ts}",
                        f"Uptime (min): {diag.get('uptime_minutes', 'N/A')}",
                        f"Memory (MB): {diag.get('memory_mb', 'N/A')}",
                    ]
                ),
            )
    except Exception:
        spool.close()
        logger.exception("support export failed")
        return jsonify({"error": "Support bundle could not be built — see the server log"}), 500

    spool.seek(0)
    return send_file(
        spool,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"sublarr-support-{ts}.zip",
    )


def _build_preview() -> dict:
    from app_logging import rotated_log_candidates
    from config import get_settings
    from routes.system.support_sections import collect_sections

    candidates = rotated_log_candidates(get_settings())
    hostname = current_hostname()
    return {
        "diagnostic": _build_diagnostic(),
        "redaction_summary": redaction_summary(candidates, hostname),
        "log_payload": payload_summary(plan_log_payload(candidates)),
        "recent_warnings_count": len(recent_warnings(candidates, hostname)),
        "sections": collect_sections(),
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


@bp.route("/logs/support-preview", methods=["GET"])
@limiter.limit(SUPPORT_RATE_LIMIT)
def support_preview():
    """Return anonymized diagnostic data + redaction summary for the support export modal.

    Cached for 30 s: the preview reads the whole log history, and the export
    dialog tends to be opened, closed and reopened.
    ---
    get:
      tags: [System]
      summary: Support bundle preview (anonymization summary + diagnostic)
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: Preview data for the support export modal
        401:
          description: Not authenticated
        429:
          description: Rate limit exceeded
    """
    if not _is_support_caller_authorized():
        return jsonify({"error": "Unauthorized"}), 401

    now = time.monotonic()
    with _preview_lock:
        if _preview_cache["data"] is not None and _preview_cache["expires"] > now:
            return jsonify({**_preview_cache["data"], "cached": True})

    data = _build_preview()
    with _preview_lock:
        _preview_cache["data"] = data
        _preview_cache["expires"] = time.monotonic() + PREVIEW_CACHE_TTL_S
    return jsonify({**data, "cached": False})
