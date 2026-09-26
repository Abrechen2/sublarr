"""Log reading for the support bundle — anonymization, top errors, warnings, payload.

Everything that walks the log files for the support export lives here, so the
endpoints in ``support.py`` stay about assembling the bundle. All readers
stream line by line and understand both log formats (``app_logging``'s text
and JSON), because the bundle is most needed exactly on the installs that
changed ``log_format``.
"""

from __future__ import annotations

import collections
import datetime as _dt
import functools
import ipaddress as _ipaddress
import logging
import os
import re
import socket as _socket

from secret_redaction import redact

logger = logging.getLogger(__name__)

# Total bytes of log history a bundle carries, newest first. The rotation
# settings allow up to 100 MB x 20 backups; a bundle of that size is neither
# uploadable to a bug report nor cheap to build.
LOG_PAYLOAD_CAP_BYTES = 50 * 1024 * 1024
RECENT_WARNINGS_MAX = 500
# Continuation lines (a traceback) kept per warning record.
_MAX_CONTINUATION_LINES = 60
_WARNING_LEVELS = frozenset({"WARNING", "ERROR", "CRITICAL"})
_TOP_ERROR_LEVELS = frozenset({"ERROR", "WARNING", "CRITICAL"})
_TOP_ERROR_MSG_LEN = 80
_TOP_ERROR_WINDOW = _dt.timedelta(hours=24)

# Hostnames too generic to redact: replacing "sublarr" turns `sublarr.db` and
# `sublarr-instance:` into noise while hiding nothing about the user.
_GENERIC_HOSTNAMES = frozenset({"sublarr", "localhost", "docker", "container", "app"})

# ─── Anonymization ────────────────────────────────────────────────────────────

_RFC1918_NETWORKS = [
    _ipaddress.ip_network("10.0.0.0/8"),
    _ipaddress.ip_network("172.16.0.0/12"),
    _ipaddress.ip_network("192.168.0.0/16"),
]

_IP_RE = re.compile(r"\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b")
# Note: may match version strings (e.g. "1.2.3.4") — acceptable over-redaction
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


@functools.lru_cache(maxsize=8)
def _hostname_pattern(hostname: str) -> re.Pattern | None:
    """Whole-word, case-insensitive matcher for ``hostname``; None to skip it."""
    name = hostname.strip()
    if len(name) < 3 or name.lower() in _GENERIC_HOSTNAMES:
        return None
    return re.compile(r"(?<![\w-])" + re.escape(name) + r"(?![\w-])", re.IGNORECASE)


def current_hostname() -> str | None:
    try:
        return _socket.gethostname()
    except OSError as exc:
        logger.debug("gethostname() failed, anonymization will skip the hostname: %s", exc)
        return None


def _anonymize(text: str, hostname: str | None = None) -> str:
    """Redact secrets and identifying data from a log line or text blob.

    Args:
        text: The text to anonymize.
        hostname: Server hostname to redact. If None, resolved via
            socket.gethostname() at call time (so it reflects runtime state,
            not import-time state).
    """
    if hostname is None:
        hostname = current_hostname()

    # Secrets first: the e-mail and path passes below would otherwise cut a
    # DSN (`user:pass@host`) into pieces the secret patterns no longer match.
    text = redact(text)
    text = _EMAIL_RE.sub("***USER***", text)
    text = _UNIX_HOME_RE.sub(r"~\1", text)
    text = _PATH_RE.sub(r"media/\1", text)
    text = _IP_RE.sub(lambda m: _classify_ip(m.group(1)), text)
    if hostname:
        pattern = _hostname_pattern(hostname)
        if pattern is not None:
            text = pattern.sub("***HOST***", text)
    return text


# ─── Readers ──────────────────────────────────────────────────────────────────


def _iter_lines(path: str):
    """Lines of ``path``; a missing file (rotated away mid-read) yields nothing."""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            yield from fh
    except FileNotFoundError:
        return


def _extract_top_errors(max_errors: int = 10) -> list[dict]:
    """Top N error/warning groups from the last 24h, across all rotated files."""
    from app_logging import parse_log_line, rotated_log_candidates

    cutoff = _dt.datetime.now() - _TOP_ERROR_WINDOW
    counts: collections.Counter = collections.Counter()
    last_seen: dict[str, str] = {}
    # Anonymize the message before counting/storing — these messages ship
    # into diagnostic-report.md and db-stats.json verbatim.
    hostname = current_hostname()

    for path in rotated_log_candidates():
        for line in _iter_lines(path):
            parsed = parse_log_line(line)
            if parsed is None:
                continue
            stamp, level, message = parsed
            if level not in _TOP_ERROR_LEVELS or message is None:
                continue
            try:
                if _dt.datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S") < cutoff:
                    continue
            except ValueError:
                pass  # include the line if its timestamp is unparseable
            key = _anonymize(message.rstrip("\n")[:_TOP_ERROR_MSG_LEN], hostname=hostname)
            counts[key] += 1
            last_seen[key] = stamp[11:16]  # HH:MM local time

    return [
        {"message": msg, "count": cnt, "last_seen": last_seen.get(msg, "")}
        for msg, cnt in counts.most_common(max_errors)
    ]


def recent_warnings(candidates: list[str], hostname: str | None) -> list[str]:
    """The last ``RECENT_WARNINGS_MAX`` WARNING+ records, anonymized, full length.

    A record keeps its continuation lines (the traceback), because a warning
    with its stack cut off is the report that needs a second round trip.
    """
    from app_logging import parse_log_line

    entries: collections.deque[list[str]] = collections.deque(maxlen=RECENT_WARNINGS_MAX)
    # Oldest file first, so the deque ends on the newest records.
    for path in reversed(candidates):
        current: list[str] | None = None
        for line in _iter_lines(path):
            parsed = parse_log_line(line)
            if parsed is None:
                if current is not None and len(current) <= _MAX_CONTINUATION_LINES:
                    current.append(line)
                continue
            if parsed[1] in _WARNING_LEVELS:
                current = [line]
                entries.append(current)
            else:
                current = None
    return [_anonymize(line, hostname=hostname) for entry in entries for line in entry]


def plan_log_payload(candidates: list[str], cap: int | None = None) -> dict:
    """Which files (and from which offset) fit into the bundle, newest first."""
    if cap is None:
        cap = LOG_PAYLOAD_CAP_BYTES
    files: list[dict] = []
    skipped: list[str] = []
    total = 0
    used = 0
    for path in candidates:
        try:
            size = os.path.getsize(path)
        except OSError:
            continue
        total += size
        budget = cap - used
        if budget <= 0:
            skipped.append(os.path.basename(path))
            continue
        start = max(0, size - budget)
        files.append({"path": path, "start": start, "size": size})
        used += size - start
    return {
        "files": files,
        "total_bytes": total,
        "included_bytes": used,
        "cap_bytes": cap,
        "truncated": used < total,
        "skipped_files": skipped,
    }


def payload_summary(plan: dict) -> dict:
    """The plan without local paths — safe to show and to ship."""
    return {
        "files_included": len(plan["files"]),
        "total_bytes": plan["total_bytes"],
        "included_bytes": plan["included_bytes"],
        "cap_bytes": plan["cap_bytes"],
        "truncated": plan["truncated"],
        "skipped_files": plan["skipped_files"],
        "partial_files": [os.path.basename(f["path"]) for f in plan["files"] if f["start"]],
    }


def write_log_member(zf, entry: dict, hostname: str | None) -> None:
    """Stream one log file into the ZIP, anonymizing line by line."""
    path = entry["path"]
    with open(path, "rb") as src:
        if entry["start"]:
            src.seek(entry["start"])
            src.readline()  # drop the line the cut landed in
        with zf.open(f"logs/{os.path.basename(path)}", "w", force_zip64=True) as dst:
            for raw in src:
                line = raw.decode("utf-8", errors="replace")
                dst.write(_anonymize(line, hostname=hostname).encode("utf-8"))


_PREVIEW_IP_RE = re.compile(r"(?:\d+\.){1}\d+\.xxx\.xxx|xxx\.xxx\.xxx\.xxx")
_PREVIEW_MEDIA_RE = re.compile(r"media/[^\s]+\.\w+")
_PREVIEW_PATH_RE = re.compile(r"/[^\s]+/[^\s]+\.\w+")


def redaction_summary(candidates: list[str], hostname: str | None) -> dict:
    """Counts and one example per kind of what the export will redact.

    The "before" examples are shown to the user in the export dialog; they keep
    the IP or path being illustrated but never a secret.
    """
    counts: collections.Counter = collections.Counter()
    path_example: tuple[str, str] | None = None
    ip_example: tuple[str, str] | None = None
    files_found = 0

    for path in candidates:
        if not os.path.exists(path):
            continue
        files_found += 1
        for line in _iter_lines(path):
            anon = _anonymize(line, hostname=hostname)
            if anon == line:
                continue
            if _PREVIEW_IP_RE.search(anon):
                counts["ips_redacted"] += 1
                if ip_example is None:
                    ip_example = (redact(line.strip()), anon.strip())
            if "***REDACTED***" in anon and "***REDACTED***" not in line:
                counts["api_keys_redacted"] += 1
            if "***USER***" in anon:
                counts["emails_redacted"] += 1
            if "***HOST***" in anon:
                counts["hostnames_redacted"] += 1
            if _PREVIEW_MEDIA_RE.search(anon) and _PREVIEW_PATH_RE.search(line):
                counts["paths_redacted"] += 1
                if path_example is None:
                    path_example = (redact(line.strip()), anon.strip())

    return {
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
    }
