"""Support-bundle routes — anonymized log export + diagnostic report.

Routes:
  /api/v1/logs/support-export  — Download an anonymized support ZIP
  /api/v1/logs/support-preview — JSON preview of what the export would contain

All anonymization + diagnostic-building helpers live here because they are
only consumed by these two endpoints (plus their tests in
`tests/test_support_export.py`, which reach them via
`from routes.system import _anonymize, _build_diagnostic` — the re-export
in `routes/system/__init__.py` keeps that contract).
"""

from __future__ import annotations

import io
import ipaddress as _ipaddress
import logging
import os
import re
import socket as _socket

from flask import jsonify, request, send_file

from routes.system import bp

logger = logging.getLogger(__name__)


# ─── Anonymization helpers ────────────────────────────────────────────────────

_RFC1918_NETWORKS = [
    _ipaddress.ip_network("10.0.0.0/8"),
    _ipaddress.ip_network("172.16.0.0/12"),
    _ipaddress.ip_network("192.168.0.0/16"),
]

_IP_RE = re.compile(r"\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b")
# Note: may match version strings (e.g. "1.2.3.4") — acceptable over-redaction
_API_KEY_RE = re.compile(
    r'(["\']?(?:api[_-]?key|apikey|token|password|secret|credential)["\']?\s*[:=]\s*["\']?)'
    r"([A-Za-z0-9+/=_\-]{16,})",
    re.IGNORECASE,
)
_APIKEY_PARAM_RE = re.compile(r"(apikey=)([A-Za-z0-9_\-]{16,})", re.IGNORECASE)
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}")
_PATH_RE = re.compile(r'(?:/[^/]+){2,}/([^/\s][^/]*\.[^/\s]+)(?=["\'\s]|$)')
_UNIX_HOME_RE = re.compile(r"/(?:home/[^/\s]+|root)(/[^\s]+)")


def _classify_ip(ip: str) -> str:
    """Classify and anonymize a single IPv4 address string."""
    try:
        addr = _ipaddress.IPv4Address(ip)
    except ValueError:
        return ip
    if addr.is_loopback:
        return ip
    for network in _RFC1918_NETWORKS:
        if addr in network:
            parts = ip.split(".")
            return f"{parts[0]}.{parts[1]}.xxx.xxx"
    return "xxx.xxx.xxx.xxx"


def _anonymize(text: str, hostname: str | None = None) -> str:
    """Redact sensitive data from a log line or text blob.

    Args:
        text: The text to anonymize.
        hostname: Server hostname to redact. If None, resolved via
            socket.gethostname() at call time (so it reflects runtime state,
            not import-time state).
    """
    if hostname is None:
        try:
            hostname = _socket.gethostname()
        except Exception:
            hostname = None

    text = _API_KEY_RE.sub(r"\1***REDACTED***", text)
    text = _APIKEY_PARAM_RE.sub(r"\1***REDACTED***", text)
    text = _EMAIL_RE.sub("***USER***", text)
    text = _UNIX_HOME_RE.sub(r"~\1", text)
    text = _PATH_RE.sub(r"media/\1", text)
    text = _IP_RE.sub(lambda m: _classify_ip(m.group(1)), text)
    if hostname:
        text = text.replace(hostname, "***HOST***")
    return text


# ─── Diagnostic helpers ───────────────────────────────────────────────────────


def _get_last_scan_minutes() -> int | None:
    """Return minutes since last wanted scan, or None if unknown."""
    import datetime as _dt2

    from db import get_db
    from db.repositories.config import ConfigRepository

    try:
        val = ConfigRepository(get_db()).get_all_config_entries().get("last_scan_timestamp")
        if not val:
            return None
        ts = _dt2.datetime.fromisoformat(val)
        delta = _dt2.datetime.now(_dt2.UTC) - ts
        return int(delta.total_seconds() / 60)
    except Exception:
        return None


def _extract_top_errors(max_errors: int = 10) -> list[dict]:
    """Parse all log files and return top N error/warning groups from the last 24h."""
    import collections as _coll
    import datetime as _dt3

    from config import get_settings as _gs3

    log_path = getattr(_gs3(), "log_file", "log/sublarr.log")
    cutoff = _dt3.datetime.now() - _dt3.timedelta(hours=24)

    _ts_re = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+\s+\[(ERROR|WARNING)\]")
    _msg_re = re.compile(
        r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d+\s+\[(?:ERROR|WARNING)\]\s+[^:]+:\s*(.*)"
    )

    counts: _coll.Counter = _coll.Counter()
    last_seen: dict[str, str] = {}

    # Anonymize the message before counting/storing — these messages ship
    # into diagnostic-report.md and db-stats.json verbatim, so any leaked
    # DSN/API-key in a SQLAlchemy or provider error would otherwise survive
    # the support bundle unredacted.
    hostname: str | None = None
    try:
        hostname = _socket.gethostname()
    except Exception:
        hostname = None

    candidates = [log_path] + [f"{log_path}.{i}" for i in range(1, 4)]
    for path in candidates:
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    m = _ts_re.match(line)
                    if not m:
                        continue
                    try:
                        ts = _dt3.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
                        if ts < cutoff:
                            continue
                    except ValueError:
                        pass  # include line if timestamp unparseable
                    msg_m = _msg_re.match(line)
                    if not msg_m:
                        continue
                    raw_msg = msg_m.group(1)[:80]
                    key = _anonymize(raw_msg, hostname=hostname)
                    counts[key] += 1
                    last_seen[key] = m.group(1)[11:16]  # HH:MM local time
        except FileNotFoundError:
            continue

    return [
        {"message": msg, "count": cnt, "last_seen": last_seen.get(msg, "")}
        for msg, cnt in counts.most_common(max_errors)
    ]


def _build_diagnostic() -> dict:
    """Build the diagnostic data dict. Used by both the preview endpoint and the ZIP report.

    Never raises — all errors are caught and reflected in the returned dict.
    """
    import datetime as _dt4
    import time as _time2

    from config import get_settings as _gs4
    from version import __version__ as _ver

    settings = _gs4()
    diag: dict = {
        "version": _ver,
        "timestamp_utc": _dt4.datetime.now(_dt4.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "uptime_minutes": None,
        "memory_mb": None,
    }

    # Process uptime + memory via psutil (optional dependency)
    try:
        import psutil

        proc = psutil.Process()
        diag["uptime_minutes"] = int((_time2.time() - proc.create_time()) / 60)
        diag["memory_mb"] = round(proc.memory_info().rss / 1024 / 1024, 1)
    except Exception:
        pass  # psutil not installed or failed — fields stay None

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
        total = sum(counts_by_status.values())
        diag["wanted"] = {
            "total": total,
            "pending": counts_by_status.get("wanted", 0),
            "extracted": counts_by_status.get("extracted", 0),
            "failed": counts_by_status.get("failed", 0),
        }
        tr = TranslationRepository(db)
        rows = tr.get_backend_stats()
        diag["translations"] = {
            "total_requests": sum(r.get("total_requests", 0) or 0 for r in rows),
            "successful": sum(r.get("successful_translations", 0) or 0 for r in rows),
            "failed": sum(r.get("failed_translations", 0) or 0 for r in rows),
        }
        diag["config_entries_count"] = len(ConfigRepository(db).get_all_config_entries())
    except Exception as exc:
        logger.warning("_build_diagnostic: DB query failed: %s", exc)
        diag["db_stats_error"] = "unavailable"

    # Provider status — read from _PROVIDER_CLASSES + settings, no DB needed
    try:
        from providers import _PROVIDER_CLASSES

        enabled_raw = getattr(settings, "providers_enabled", "") or ""
        enabled_set = {p.strip().lower() for p in enabled_raw.split(",") if p.strip()}
        diag["provider_status"] = [
            {
                "name": name,
                "active": not enabled_set or name.lower() in enabled_set,
            }
            for name in _PROVIDER_CLASSES
        ]
    except Exception as exc:
        logger.warning("_build_diagnostic: provider status failed: %s", exc)
        diag["provider_status"] = []

    diag["last_scan_ago_minutes"] = _get_last_scan_minutes()
    diag["top_errors"] = _extract_top_errors()

    return diag


# ─── Endpoints ────────────────────────────────────────────────────────────────


def _is_support_caller_authorized() -> bool:
    """Allow API-key holders, valid UI sessions, or fully-open deployments.

    Centralised so /support-export and /support-preview can't drift apart.
    The "fully-open" branch requires BOTH api_key AND ui_auth_enabled to
    be unset — when either is configured, the caller must authenticate.
    Pre-2026-04-30 the checks ignored ui_auth_enabled, leaking the
    support bundle to unauthenticated probes when api_key="" but UI auth
    was on (same auth-layer-composition bug as /auth/bootstrap and
    /health). See `project_2026_04_30_health_audit.md`.
    """
    import hmac as _hmac

    from flask import session as _session

    import ui_auth as _ui_auth
    from config import get_settings

    s = get_settings()
    api_key = getattr(s, "api_key", None)
    provided = request.headers.get("X-Api-Key") or request.args.get("apikey", "")
    if api_key and _hmac.compare_digest(provided, api_key):
        return True
    if _session.get("ui_authenticated"):
        return True
    try:
        ui_auth_on = _ui_auth.is_ui_auth_enabled()
    except Exception:
        ui_auth_on = False
    # Fully-open deployment: nothing protects /api/v1/* anyway.
    return not api_key and not ui_auth_on


@bp.route("/logs/support-export", methods=["GET"])
def support_export():
    """Download an anonymized support bundle (log files + system info) as a ZIP.

    Sensitive data is stripped before export:
    - API keys and passwords replaced with ***REDACTED***
    - Local file paths shortened to filename only
    - IPv4 addresses replaced with x.x.x.x
    - Usernames and email addresses replaced with ***USER***
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
    """
    import json as _json
    import platform
    import zipfile as _zipfile
    from datetime import UTC, datetime

    from config import get_settings
    from version import __version__

    if not _is_support_caller_authorized():
        return jsonify({"error": "Unauthorized"}), 401

    _s = get_settings()
    log_path = getattr(_s, "log_file", "log/sublarr.log")
    candidates = [log_path] + [f"{log_path}.{i}" for i in range(1, 4)]
    ts = datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%SZ")
    zip_name = f"sublarr-support-{ts}.zip"

    hostname: str | None = None
    try:
        hostname = _socket.gethostname()
    except Exception as exc:
        logger.debug("gethostname() failed, log anonymization will skip hostname: %s", exc)

    buf = io.BytesIO()
    with _zipfile.ZipFile(buf, "w", _zipfile.ZIP_DEFLATED) as zf:
        # 1. Anonymized log files
        for path in candidates:
            try:
                with open(path, encoding="utf-8", errors="replace") as fh:
                    content = "".join(_anonymize(line, hostname=hostname) for line in fh)
                zf.writestr(f"logs/{os.path.basename(path)}", content)
            except FileNotFoundError:
                continue

        # 2. Diagnostic report as Markdown (shared helper)
        diag = _build_diagnostic()
        md_lines = [
            "# Sublarr Support Report",
            "",
            f"**Version:** {diag.get('version', '?')}  ",
            f"**Generated:** {diag.get('timestamp_utc', '?')}  ",
            f"**Uptime:** {diag.get('uptime_minutes', 'N/A')} min  ",
            f"**Memory:** {diag.get('memory_mb', 'N/A')} MB  ",
            "",
            "## Top Errors (last 24h)",
            "",
        ]
        for e in diag.get("top_errors", []):
            md_lines.append(f"- **{e['message']}** (x{e['count']}, last: {e['last_seen']})")
        if not diag.get("top_errors"):
            md_lines.append("_No errors in the last 24h_")
        md_lines += ["", "## Provider Status", ""]
        for p in diag.get("provider_status", []):
            md_lines.append(f"- {'active' if p['active'] else 'inactive'}: {p['name']}")
        md_lines += ["", "## Stats", "", "| Metric | Value |", "|--------|-------|"]
        for k, v in diag.get("wanted", {}).items():
            md_lines.append(f"| Wanted {k} | {v} |")
        for k, v in diag.get("translations", {}).items():
            md_lines.append(f"| Translations {k} | {v} |")
        zf.writestr("diagnostic-report.md", "\n".join(md_lines))

        # 3. DB stats JSON
        zf.writestr(
            "db-stats.json",
            _json.dumps(
                {
                    "wanted": diag.get("wanted", {}),
                    "translations": diag.get("translations", {}),
                    "providers": {
                        "active": sum(1 for p in diag.get("provider_status", []) if p["active"]),
                        "last_scan_ago_minutes": diag.get("last_scan_ago_minutes"),
                    },
                    "config_entries": diag.get("config_entries_count"),
                    "last_errors": [e["message"] for e in diag.get("top_errors", [])[:5]],
                },
                indent=2,
            ),
        )

        # 4. Config snapshot — delegate to Settings.get_safe_config() so the
        #    bundle inherits the same masking rules used by /config (and the
        #    /export endpoint). A previous keyword-only loop here missed
        #    notification_urls_json (Apprise tokens), database_url / redis_url
        #    (DSN-embedded creds), and *_instances_json (nested api_keys).
        zf.writestr(
            "config-snapshot.json",
            _json.dumps(_s.get_safe_config(), indent=2, default=str),
        )

        # 5. System info
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

    buf.seek(0)
    return send_file(buf, mimetype="application/zip", as_attachment=True, download_name=zip_name)


@bp.route("/logs/support-preview", methods=["GET"])
def support_preview():
    """Return anonymized diagnostic data + redaction summary for the support export modal.
    ---
    get:
      tags: [System]
      summary: Support bundle preview (anonymization summary + diagnostic)
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: Preview data for the support export modal
    """
    import collections

    from config import get_settings

    if not _is_support_caller_authorized():
        return jsonify({"error": "Unauthorized"}), 401

    _s = get_settings()
    diagnostic = _build_diagnostic()

    log_path = getattr(_s, "log_file", "log/sublarr.log")
    candidates = [log_path] + [f"{log_path}.{i}" for i in range(1, 4)]

    counts: collections.Counter = collections.Counter()
    path_example: tuple[str, str] | None = None
    ip_example: tuple[str, str] | None = None
    files_found = 0

    hostname: str | None = None
    try:
        hostname = _socket.gethostname()
    except Exception as exc:
        logger.debug("gethostname() failed, log anonymization will skip hostname: %s", exc)

    for path in candidates:
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    anon = _anonymize(line, hostname=hostname)
                    if anon == line:
                        continue
                    if re.search(r"(?:\d+\.){1}\d+\.xxx\.xxx|xxx\.xxx\.xxx\.xxx", anon):
                        counts["ips_redacted"] += 1
                        if ip_example is None:
                            ip_example = (line.strip(), anon.strip())
                    if "***REDACTED***" in anon and "***REDACTED***" not in line:
                        counts["api_keys_redacted"] += 1
                    if "***USER***" in anon:
                        counts["emails_redacted"] += 1
                    if "***HOST***" in anon:
                        counts["hostnames_redacted"] += 1
                    if re.search(r"media/[^\s]+\.\w+", anon) and re.search(
                        r"/[^\s]+/[^\s]+\.\w+", line
                    ):
                        counts["paths_redacted"] += 1
                        if path_example is None:
                            path_example = (line.strip(), anon.strip())
            files_found += 1
        except FileNotFoundError:
            continue

    return jsonify(
        {
            "diagnostic": diagnostic,
            "redaction_summary": {
                "log_files_found": files_found,
                "ips_redacted": counts.get("ips_redacted", 0),
                "api_keys_redacted": counts.get("api_keys_redacted", 0),
                "paths_redacted": counts.get("paths_redacted", 0),
                "emails_redacted": counts.get("emails_redacted", 0),
                "hostnames_redacted": counts.get("hostnames_redacted", 0),
                "example_path_before": path_example[0] if path_example else "",
                "example_path_after": path_example[1] if path_example else "",
                "example_ip_before": ip_example[0] if ip_example else "",
                "example_ip_after": ip_example[1] if ip_example else "",
            },
        }
    )
