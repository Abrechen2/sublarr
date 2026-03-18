"""System log routes — /logs/*, /database/vacuum, /cache/ffprobe/*."""

import io
import ipaddress as _ipaddress
import logging
import os
import re
import socket as _socket

from flask import jsonify, request, send_file

from routes.system import bp

logger = logging.getLogger(__name__)

# ─── Support export — anonymization helpers ───────────────────────────────────

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
        hostname: Server hostname to redact. If None, resolved via socket.gethostname()
                  at call time (so it reflects runtime state, not import-time state).
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


# ─── Support export — diagnostic helpers ──────────────────────────────────────


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
        delta = _dt2.datetime.utcnow() - ts
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
                    key = msg_m.group(1)[:80]
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
        "timestamp_utc": _dt4.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
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
        from db import get_db
        from db.repositories.config import ConfigRepository
        from db.repositories.translation import TranslationRepository
        from db.repositories.wanted import WantedRepository

        db = get_db()
        wr = WantedRepository(db)
        diag["wanted"] = {
            "total": wr.get_wanted_count(),
            "pending": wr.get_wanted_count(status="wanted"),
            "extracted": wr.get_wanted_count(status="extracted"),
            "failed": wr.get_wanted_count(status="failed"),
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

    return send_file(
        log_file, mimetype="text/plain", as_attachment=True, download_name="sublarr.log"
    )


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
    import hmac as _hmac
    import json as _json
    import platform
    import zipfile as _zipfile
    from datetime import datetime

    from flask import session as _session

    from config import get_settings
    from version import __version__

    _s = get_settings()
    _api_key = getattr(_s, "api_key", None)
    _provided = request.headers.get("X-Api-Key") or request.args.get("apikey", "")
    _key_ok = bool(_api_key and _hmac.compare_digest(_provided, _api_key))
    _session_ok = bool(_session.get("ui_authenticated"))
    if not (_key_ok or _session_ok or not _api_key):
        return jsonify({"error": "Unauthorized"}), 401

    log_path = getattr(_s, "log_file", "log/sublarr.log")
    candidates = [log_path] + [f"{log_path}.{i}" for i in range(1, 4)]
    ts = datetime.utcnow().strftime("%Y-%m-%dT%H-%M-%SZ")
    zip_name = f"sublarr-support-{ts}.zip"

    hostname: str | None = None
    try:
        hostname = _socket.gethostname()
    except Exception:
        pass

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

        # 4. Config snapshot — redact secret fields by name
        _SECRET_TOKENS = {"key", "token", "password", "secret", "credential"}
        raw_cfg = _s.model_dump()
        safe_cfg = {
            k: "***REDACTED***" if any(t in k.lower() for t in _SECRET_TOKENS) else v
            for k, v in raw_cfg.items()
        }
        zf.writestr("config-snapshot.json", _json.dumps(safe_cfg, indent=2, default=str))

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
    import hmac as _hmac

    from flask import session as _session

    from config import get_settings

    _s = get_settings()
    _api_key = getattr(_s, "api_key", None)
    _provided = request.headers.get("X-Api-Key") or request.args.get("apikey", "")
    _key_ok = bool(_api_key and _hmac.compare_digest(_provided, _api_key))
    _session_ok = bool(_session.get("ui_authenticated"))
    if not (_key_ok or _session_ok or not _api_key):
        return jsonify({"error": "Unauthorized"}), 401

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
    except Exception:
        pass

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

    return jsonify(
        {
            "max_size_mb": max_size_mb,
            "backup_count": backup_count,
        }
    )


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

    logger.info(
        "Log rotation config updated: max_size_mb=%d, backup_count=%d", saved_max, saved_count
    )

    return jsonify(
        {
            "status": "updated",
            "max_size_mb": saved_max,
            "backup_count": saved_count,
            "note": "Changes take effect on next application restart",
        }
    )


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
    from config import get_settings
    from database_health import _is_postgresql, vacuum
    from db import get_db

    if _is_postgresql():
        return jsonify(
            {
                "error": "VACUUM is not available for PostgreSQL. Use VACUUM ANALYZE directly on the database server."
            }
        ), 501

    db = get_db()
    result = vacuum(db, get_settings().db_path)
    return jsonify(result)


@bp.route("/cache/ffprobe/stats", methods=["GET"])
def ffprobe_cache_stats():
    """Return ffprobe cache statistics.
    ---
    get:
      tags:
        - System
      summary: FFprobe cache stats
      description: Returns the number of cached ffprobe entries and timestamps.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: Cache statistics
    """
    from db.cache import get_ffprobe_cache_stats

    return jsonify(get_ffprobe_cache_stats())


@bp.route("/cache/ffprobe/cleanup", methods=["POST"])
def ffprobe_cache_cleanup():
    """Remove stale ffprobe cache entries for files that no longer exist.
    ---
    post:
      tags:
        - System
      summary: Clean up stale ffprobe cache entries
      description: Deletes cache entries whose video files no longer exist on disk. Supports dry_run.
      security:
        - apiKeyAuth: []
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                dry_run:
                  type: boolean
                  default: false
      responses:
        200:
          description: Cleanup result
          content:
            application/json:
              schema:
                type: object
                properties:
                  removed:
                    type: integer
                  dry_run:
                    type: boolean
                  paths:
                    type: array
                    items:
                      type: string
    """
    from db.cache import cleanup_stale_ffprobe_cache

    data = request.get_json() or {}
    dry_run = bool(data.get("dry_run", False))
    result = cleanup_stale_ffprobe_cache(dry_run=dry_run)
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

    import collections

    if not lines or lines <= 0:
        lines = 200
    lines = min(lines, 2000)
    log_entries = []
    if os.path.exists(log_file):
        try:
            with open(log_file, encoding="utf-8", errors="replace") as f:
                recent = list(collections.deque(f, maxlen=lines))
                for line in recent:
                    if level and f"[{level}]" not in line:
                        continue
                    log_entries.append(line.strip())
        except Exception as e:
            logger.warning("Failed to read log file: %s", e)

    return jsonify(
        {
            "entries": log_entries,
            "total": len(log_entries),
        }
    )
