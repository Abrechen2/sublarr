# Support Export — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a fully featured anonymized support bundle export feature with a preview modal in Settings → System → Protokoll tab.

**Architecture:** Backend gains a `_build_diagnostic()` helper shared between a new preview endpoint and the enhanced export endpoint. The existing `support_export()` is extended with richer ZIP contents. Frontend adds a new `ProtokollTab.tsx` component that consolidates log settings, log viewer preferences (localStorage), and the support export modal with live preview.

**Tech Stack:** Python 3.12 / Flask / SQLAlchemy, pytest; React 19 / TypeScript / TanStack Query / react-i18next / Tailwind v4

**Spec:** `docs/superpowers/specs/2026-03-17-support-export-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `backend/routes/system.py` | Modify | Replace `_anonymize()`; add `_build_diagnostic()`, `_extract_top_errors()`, `_get_last_scan_minutes()`; add `/logs/support-preview` endpoint; enhance `/logs/support-export` ZIP |
| `backend/tests/test_support_export.py` | Create | Unit tests for anonymization, diagnostic builder, preview endpoint, export endpoint |
| `frontend/src/api/client.ts` | Modify | Add `fetchSupportPreview()` and `downloadSupportBundle()` |
| `frontend/src/lib/types.ts` | Modify | Add `SupportPreview` response type |
| `frontend/src/pages/Settings/ProtokollTab.tsx` | Create | Log-level setting, log rotation, log viewer prefs, support export modal |
| `frontend/src/pages/Settings/index.tsx` | Modify | Add "Protokoll" to System NAV_GROUPS; render ProtokollTab; remove log_level from General tab |
| `frontend/src/pages/Logs.tsx` | Modify | Remove rotation collapsible + hooks; read `sublarr_log_view_prefs`; apply category filter + display toggles |
| `frontend/src/i18n/locales/en/settings.json` | Modify | Add i18n keys for ProtokollTab strings |
| `frontend/src/i18n/locales/de/settings.json` | Modify | German translations for same keys |
| `frontend/src/i18n/locales/en/logs.json` | Modify | Remove rotation keys (moved to settings.json); add no-op note |
| `frontend/src/i18n/locales/de/logs.json` | Modify | Same |

---

## Auth pattern in system.py

All existing endpoints in `system.py` use **inline auth** — no decorator. Replicate this pattern:

```python
import hmac as _hmac
from flask import session as _session

_settings = get_settings()
_api_key = getattr(_settings, "api_key", None)
_provided = request.headers.get("X-Api-Key") or request.args.get("apikey", "")
_key_ok = bool(_api_key and _hmac.compare_digest(_provided, _api_key))
_session_ok = bool(_session.get("ui_authenticated"))
if not (_key_ok or _session_ok or not _api_key):
    return jsonify({"error": "Unauthorized"}), 401
```

---

## Task 1: Enhanced Anonymization (Backend)

**Files:**
- Modify: `backend/routes/system.py` — replace `_REDACT_PATTERNS` + existing inline anonymization in `support_export()` with module-level `_anonymize()` helper
- Create: `backend/tests/test_support_export.py`

### Step 1.1 — Write failing tests for `_anonymize()`

Create `backend/tests/test_support_export.py`:

```python
"""Tests for support export anonymization and diagnostic builder."""
import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestAnonymize:
    """Test the _anonymize() helper function."""

    def _fn(self, *args, **kwargs):
        from routes.system import _anonymize
        return _anonymize(*args, **kwargs)

    def test_private_ip_192_168(self):
        assert self._fn("Connected to 192.168.178.194") == "Connected to 192.168.xxx.xxx"

    def test_private_ip_10_x(self):
        assert self._fn("Host: 10.0.0.1") == "Host: 10.0.xxx.xxx"

    def test_private_ip_172_16(self):
        assert self._fn("Addr: 172.16.5.20") == "Addr: 172.16.xxx.xxx"

    def test_public_ip_fully_redacted(self):
        assert self._fn("Remote: 85.214.132.17") == "Remote: xxx.xxx.xxx.xxx"

    def test_localhost_preserved(self):
        line = "Listening on 127.0.0.1:5765"
        assert self._fn(line) == line

    def test_api_key_redacted(self):
        line = 'api_key: "3bdcc724abcdef1234567890abcdef12"'
        result = self._fn(line)
        assert "3bdcc724" not in result
        assert "***REDACTED***" in result

    def test_path_keeps_filename_only(self):
        line = "Subtitle for /media/Anime/86 Eighty Six/S01E01.mkv"
        result = self._fn(line)
        assert "86 Eighty Six" not in result
        assert "S01E01.mkv" in result

    def test_email_redacted(self):
        line = "User: somebody@example.com logged in"
        result = self._fn(line)
        assert "***USER***" in result
        assert "somebody@example.com" not in result

    def test_hostname_parameter_redacted(self):
        """Pass hostname explicitly — simulates what export time does."""
        result = self._fn("Request from my-server", hostname="my-server")
        assert "***HOST***" in result
        assert "my-server" not in result

    def test_unix_home_path_shortened(self):
        line = "Config at /home/dennis/sublarr/config.db"
        result = self._fn(line)
        assert "/home/dennis" not in result
        assert "~/sublarr/config.db" in result
```

- [ ] **Step 1.1:** Create the test file at `backend/tests/test_support_export.py`

- [ ] **Step 1.2:** Run tests to confirm they fail

```bash
cd backend
python -m pytest tests/test_support_export.py::TestAnonymize -v
```
Expected: FAIL (ImportError or assertion failures — `_anonymize` doesn't match yet)

- [ ] **Step 1.3:** Add module-level `_anonymize()` to `backend/routes/system.py`

Add the following **before** the first `@bp.route` in `system.py` (e.g., after the existing imports, around line 20). The existing `_REDACT_PATTERNS` list inside `support_export()` will be replaced in Task 3 — for now just add the new helper:

```python
import ipaddress as _ipaddress
import re as _re_anon
import socket as _socket

_RFC1918_NETWORKS = [
    _ipaddress.ip_network("10.0.0.0/8"),
    _ipaddress.ip_network("172.16.0.0/12"),
    _ipaddress.ip_network("192.168.0.0/16"),
]

_IP_RE = _re_anon.compile(r'\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b')
_API_KEY_RE = _re_anon.compile(
    r'(["\']?(?:api[_-]?key|apikey|token|password|secret|credential)["\']?\s*[:=]\s*["\']?)'
    r'([A-Za-z0-9+/=_\-]{16,})',
    _re_anon.IGNORECASE,
)
_APIKEY_PARAM_RE = _re_anon.compile(r'(apikey=)([A-Za-z0-9_\-]{16,})', _re_anon.IGNORECASE)
_EMAIL_RE = _re_anon.compile(r'[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}')
_PATH_RE = _re_anon.compile(r'(?:/[^\s/]+){2,}/([^\s/]+\.[^\s/]+)')
_UNIX_HOME_RE = _re_anon.compile(r'/(?:home|root)/[^/\s]+(/[^\s]*)')


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
```

- [ ] **Step 1.4:** Run tests again

```bash
cd backend
python -m pytest tests/test_support_export.py::TestAnonymize -v
```
Expected: All PASS

- [ ] **Step 1.5:** Commit

```bash
git add backend/routes/system.py backend/tests/test_support_export.py
git commit -m "feat: add module-level _anonymize() with RFC1918 IP classification and dynamic hostname"
```

---

## Task 2: `_build_diagnostic()` Helper (Backend)

**Files:**
- Modify: `backend/routes/system.py` — add `_build_diagnostic()`, `_extract_top_errors()`, `_get_last_scan_minutes()`
- Modify: `backend/tests/test_support_export.py` — add `TestBuildDiagnostic`

### Step 2.1 — Write failing tests

Append to `backend/tests/test_support_export.py`:

```python
class TestBuildDiagnostic:
    """Test the _build_diagnostic() shared helper."""

    def _call(self):
        from routes.system import _build_diagnostic
        return _build_diagnostic()

    def test_returns_version(self):
        result = self._call()
        assert "version" in result
        assert isinstance(result["version"], str)

    def test_wanted_counts_present(self):
        result = self._call()
        # Either wanted dict exists, or db_stats_error is set — both are valid
        assert "wanted" in result or result.get("db_stats_error") == "unavailable"

    def test_translations_present(self):
        result = self._call()
        assert "translations" in result or result.get("db_stats_error") == "unavailable"

    def test_top_errors_is_list(self):
        result = self._call()
        assert isinstance(result.get("top_errors", []), list)

    def test_provider_status_is_list(self):
        result = self._call()
        assert isinstance(result.get("provider_status", []), list)
        for p in result.get("provider_status", []):
            assert "name" in p
            assert "active" in p

    def test_memory_mb_present(self):
        result = self._call()
        assert "memory_mb" in result  # may be None if psutil absent

    def test_db_error_handled_gracefully(self):
        from unittest.mock import patch
        # Simulate DB failure by patching _db_lock.__enter__
        with patch("routes.system._db_lock") as mock_lock:
            mock_lock.__enter__ = lambda s: (_ for _ in ()).throw(Exception("locked"))
            mock_lock.__exit__ = lambda s, *a: False
            result = _build_diagnostic_fn()  # see below
        assert "db_stats_error" in result

    def _build_diagnostic_fn(self):
        from routes.system import _build_diagnostic
        return _build_diagnostic()
```

Note: The `test_db_error_handled_gracefully` test patches `_db_lock.__enter__` to raise — this is the correct way to simulate a locked DB since `_db_lock` is a `threading.Lock` used as a context manager.

- [ ] **Step 2.1:** Append tests to `backend/tests/test_support_export.py`

- [ ] **Step 2.2:** Run to confirm failure

```bash
cd backend
python -m pytest tests/test_support_export.py::TestBuildDiagnostic -v
```
Expected: FAIL (`_build_diagnostic` not found)

- [ ] **Step 2.3:** Add `_build_diagnostic()` and helpers to `backend/routes/system.py`

Add after `_anonymize()`:

```python
def _get_last_scan_minutes() -> int | None:
    """Return minutes since last wanted scan, or None if unknown."""
    import datetime
    from db import _db_lock, get_db
    from db.repositories.config import ConfigRepository
    try:
        with _db_lock:
            val = ConfigRepository(get_db()).get_all_config_entries().get("last_scan_timestamp")
        if not val:
            return None
        ts = datetime.datetime.fromisoformat(val)
        delta = datetime.datetime.utcnow() - ts
        return int(delta.total_seconds() / 60)
    except Exception:
        return None


def _extract_top_errors(max_errors: int = 10) -> list[dict]:
    """Parse all log files and return top N error/warning groups from the last 24h."""
    import collections
    import datetime

    log_path = getattr(get_settings(), "log_file", "log/sublarr.log")
    cutoff = datetime.datetime.now() - datetime.timedelta(hours=24)

    _ts_re = re.compile(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+\s+\[(ERROR|WARNING)\]')
    _msg_re = re.compile(
        r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d+\s+\[(?:ERROR|WARNING)\]\s+[^:]+:\s*(.*)'
    )

    counts: collections.Counter = collections.Counter()
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
                        ts = datetime.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
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
    import time as _time
    import datetime

    from config import get_settings as _gs
    from version import get_version

    settings = _gs()
    diag: dict = {
        "version": get_version(),
        "timestamp_utc": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "uptime_minutes": None,
        "memory_mb": None,
    }

    # Process uptime + memory via psutil (optional dependency)
    try:
        import psutil
        proc = psutil.Process()
        diag["uptime_minutes"] = int((_time.time() - proc.create_time()) / 60)
        diag["memory_mb"] = round(proc.memory_info().rss / 1024 / 1024, 1)
    except Exception:
        pass  # psutil not installed or failed — fields stay None

    # Wanted + translation stats from DB
    try:
        from db import _db_lock, get_db
        from db.repositories.wanted import WantedRepository
        from db.repositories.translation import TranslationRepository
        from db.repositories.config import ConfigRepository

        with _db_lock:
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
            diag["config_entries_count"] = len(
                ConfigRepository(db).get_all_config_entries()
            )
    except Exception as exc:
        logger.warning("_build_diagnostic: DB query failed: %s", exc)
        diag["db_stats_error"] = "unavailable"

    # Provider status — lightweight: read from _PROVIDER_CLASSES + settings, no DB
    try:
        from providers import _PROVIDER_CLASSES, get_provider_manager as _gpm
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
```

- [ ] **Step 2.4:** Run tests

```bash
cd backend
python -m pytest tests/test_support_export.py::TestBuildDiagnostic -v
```
Expected: All PASS (fix any import/key mismatches)

- [ ] **Step 2.5:** Commit

```bash
git add backend/routes/system.py backend/tests/test_support_export.py
git commit -m "feat: add _build_diagnostic(), _extract_top_errors(), _get_last_scan_minutes() helpers"
```

---

## Task 3: Preview Endpoint + Enhanced Export (Backend)

**Files:**
- Modify: `backend/routes/system.py`
- Modify: `backend/tests/test_support_export.py`

### Step 3.1 — Write failing endpoint tests

Append to `backend/tests/test_support_export.py`:

```python
class TestSupportPreviewEndpoint:
    """Test GET /api/v1/logs/support-preview."""

    @pytest.fixture
    def client(self):
        from app import create_app
        app = create_app()
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c

    def _headers(self):
        from config import get_settings
        return {"X-Api-Key": get_settings().api_key or ""}

    def test_returns_200(self, client):
        resp = client.get("/api/v1/logs/support-preview", headers=self._headers())
        assert resp.status_code == 200

    def test_response_shape(self, client):
        data = client.get(
            "/api/v1/logs/support-preview", headers=self._headers()
        ).get_json()
        assert "diagnostic" in data
        assert "redaction_summary" in data

    def test_redaction_summary_fields(self, client):
        rs = client.get(
            "/api/v1/logs/support-preview", headers=self._headers()
        ).get_json()["redaction_summary"]
        for key in ("log_files_found", "ips_redacted", "api_keys_redacted",
                    "paths_redacted", "example_path_before", "example_ip_before"):
            assert key in rs


class TestSupportExportEndpoint:
    """Test GET /api/v1/logs/support-export."""

    @pytest.fixture
    def client(self):
        from app import create_app
        app = create_app()
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c

    def _headers(self):
        from config import get_settings
        return {"X-Api-Key": get_settings().api_key or ""}

    def test_returns_zip(self, client):
        resp = client.get("/api/v1/logs/support-export", headers=self._headers())
        assert resp.status_code == 200
        assert "application/zip" in resp.content_type

    def test_zip_contains_required_files(self, client):
        import io, zipfile
        resp = client.get("/api/v1/logs/support-export", headers=self._headers())
        z = zipfile.ZipFile(io.BytesIO(resp.data))
        names = z.namelist()
        assert "diagnostic-report.md" in names
        assert "db-stats.json" in names
        assert "config-snapshot.json" in names
        assert "system-info.txt" in names

    def test_config_snapshot_redacts_api_key(self, client):
        import io, zipfile, json
        resp = client.get("/api/v1/logs/support-export", headers=self._headers())
        z = zipfile.ZipFile(io.BytesIO(resp.data))
        cfg = json.loads(z.read("config-snapshot.json"))
        # api_key field must be redacted
        assert cfg.get("api_key") == "***REDACTED***"
```

- [ ] **Step 3.1:** Append tests to `backend/tests/test_support_export.py`

- [ ] **Step 3.2:** Run to confirm failure

```bash
cd backend
python -m pytest tests/test_support_export.py::TestSupportPreviewEndpoint tests/test_support_export.py::TestSupportExportEndpoint -v
```
Expected: FAIL (`/support-preview` 404; export ZIP missing new files)

- [ ] **Step 3.3:** Add `/logs/support-preview` endpoint to `backend/routes/system.py`

Add after the existing `support_export()` function. Follow the inline auth pattern documented at the top of this plan:

```python
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
    import hmac as _hmac
    import collections
    from flask import session as _session

    # Inline auth (matches pattern used throughout system.py)
    _s = get_settings()
    _api_key = getattr(_s, "api_key", None)
    _provided = request.headers.get("X-Api-Key") or request.args.get("apikey", "")
    _key_ok = bool(_api_key and _hmac.compare_digest(_provided, _api_key))
    _session_ok = bool(_session.get("ui_authenticated"))
    if not (_key_ok or _session_ok or not _api_key):
        return jsonify({"error": "Unauthorized"}), 401

    diagnostic = _build_diagnostic()

    # Count redactions by scanning all log files
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
                    if re.search(r'(?:\d+\.){1}\d+\.xxx\.xxx|xxx\.xxx\.xxx\.xxx', anon):
                        counts["ips_redacted"] += 1
                        if ip_example is None:
                            ip_example = (line.strip(), anon.strip())
                    if "***REDACTED***" in anon and "***REDACTED***" not in line:
                        counts["api_keys_redacted"] += 1
                    if "***USER***" in anon:
                        counts["emails_redacted"] += 1
                    if "***HOST***" in anon:
                        counts["hostnames_redacted"] += 1
                    if re.search(r'media/[^\s]+\.\w+', anon) and re.search(
                        r'/[^\s]+/[^\s]+\.\w+', line
                    ):
                        counts["paths_redacted"] += 1
                        if path_example is None:
                            path_example = (line.strip(), anon.strip())
            files_found += 1
        except FileNotFoundError:
            continue

    return jsonify({
        "diagnostic": diagnostic,
        "redaction_summary": {
            "log_files_found": files_found,
            "ips_redacted": counts.get("ips_redacted", 0),
            "api_keys_redacted": counts.get("api_keys_redacted", 0),
            "paths_redacted": counts.get("paths_redacted", 0),
            "emails_redacted": counts.get("emails_redacted", 0),
            "hostnames_redacted": counts.get("hostnames_redacted", 0),
            "example_path_before": path_example[0] if path_example else "",
            "example_path_after":  path_example[1] if path_example else "",
            "example_ip_before":   ip_example[0] if ip_example else "",
            "example_ip_after":    ip_example[1] if ip_example else "",
        },
    })
```

- [ ] **Step 3.4:** Replace the body of `support_export()` in `backend/routes/system.py`

Keep the `@bp.route("/logs/support-export", methods=["GET"])` decorator and docstring. Replace everything inside the function body with:

```python
    import hmac as _hmac
    import io
    import json
    import os
    import platform
    import zipfile
    from datetime import datetime
    from flask import session as _session, send_file

    # Inline auth
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
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
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
            "# Sublarr Support Report", "",
            f"**Version:** {diag.get('version', '?')}  ",
            f"**Generated:** {diag.get('timestamp_utc', '?')}  ",
            f"**Uptime:** {diag.get('uptime_minutes', 'N/A')} min  ",
            f"**Memory:** {diag.get('memory_mb', 'N/A')} MB  ",
            "", "## Top Errors (last 24h)", "",
        ]
        for e in diag.get("top_errors", []):
            md_lines.append(f"- **{e['message']}** (×{e['count']}, last: {e['last_seen']})")
        if not diag.get("top_errors"):
            md_lines.append("_No errors in the last 24h_")
        md_lines += ["", "## Provider Status", ""]
        for p in diag.get("provider_status", []):
            md_lines.append(f"- {'✅' if p['active'] else '❌'} {p['name']}")
        md_lines += ["", "## Stats", "", "| Metric | Value |", "|--------|-------|"]
        for k, v in diag.get("wanted", {}).items():
            md_lines.append(f"| Wanted {k} | {v} |")
        for k, v in diag.get("translations", {}).items():
            md_lines.append(f"| Translations {k} | {v} |")
        zf.writestr("diagnostic-report.md", "\n".join(md_lines))

        # 3. DB stats JSON
        zf.writestr("db-stats.json", json.dumps({
            "wanted": diag.get("wanted", {}),
            "translations": diag.get("translations", {}),
            "providers": {
                "active": sum(1 for p in diag.get("provider_status", []) if p["active"]),
                "last_scan_ago_minutes": diag.get("last_scan_ago_minutes"),
            },
            "config_entries": diag.get("config_entries_count"),
            "last_errors": [e["message"] for e in diag.get("top_errors", [])[:5]],
        }, indent=2))

        # 4. Config snapshot — redact secret fields by name
        _SECRET_TOKENS = {"key", "token", "password", "secret", "credential"}
        raw_cfg = _s.model_dump()
        safe_cfg = {
            k: "***REDACTED***" if any(t in k.lower() for t in _SECRET_TOKENS) else v
            for k, v in raw_cfg.items()
        }
        zf.writestr("config-snapshot.json", json.dumps(safe_cfg, indent=2, default=str))

        # 5. System info
        from version import get_version
        zf.writestr("system-info.txt", "\n".join([
            f"Sublarr Version: {get_version()}",
            f"Python: {platform.python_version()}",
            f"OS: {platform.system()} {platform.release()}",
            f"Export Timestamp (UTC): {ts}",
            f"Uptime (min): {diag.get('uptime_minutes', 'N/A')}",
            f"Memory (MB): {diag.get('memory_mb', 'N/A')}",
        ]))

    buf.seek(0)
    return send_file(buf, mimetype="application/zip", as_attachment=True, download_name=zip_name)
```

- [ ] **Step 3.5:** Run all backend tests

```bash
cd backend
python -m pytest tests/test_support_export.py -v
```
Expected: All PASS

- [ ] **Step 3.6:** Run full test suite for regressions

```bash
cd backend
python -m pytest --tb=short -q \
  --ignore=tests/performance \
  --ignore=tests/integration/test_translator_pipeline.py \
  --ignore=tests/integration/test_provider_pipeline.py \
  --ignore=tests/test_video_sync.py \
  --ignore=tests/test_translation_backends.py \
  --ignore=tests/test_wanted_search_reliability.py \
  -k "not (test_sonarr_download_webhook or test_radarr_download_webhook or test_parse_llm_response_too_many_merge or test_record_backend_success)"
```
Expected: Pass

- [ ] **Step 3.7:** Lint

```bash
cd backend
ruff check . && ruff format --check .
```
Expected: Clean

- [ ] **Step 3.8:** Commit

```bash
git add backend/routes/system.py backend/tests/test_support_export.py
git commit -m "feat: add /logs/support-preview endpoint; enhance /logs/support-export with full ZIP contents"
```

---

## Task 4: Frontend API Client + Types

**Files:**
- Modify: `frontend/src/lib/types.ts`
- Modify: `frontend/src/api/client.ts`

- [ ] **Step 4.1:** Add `SupportPreview` types to `frontend/src/lib/types.ts`

```typescript
export interface SupportTopError {
  message: string
  count: number
  last_seen: string
}

export interface SupportProviderStatus {
  name: string
  active: boolean
}

export interface SupportDiagnostic {
  version: string
  timestamp_utc: string
  uptime_minutes: number | null
  memory_mb: number | null
  top_errors: SupportTopError[]
  provider_status: SupportProviderStatus[]
  wanted: { total: number; pending: number; extracted: number; failed: number }
  translations: { total_requests: number; successful: number; failed: number }
  last_scan_ago_minutes: number | null
  config_entries_count: number
  db_stats_error?: string
}

export interface SupportRedactionSummary {
  log_files_found: number
  ips_redacted: number
  api_keys_redacted: number
  paths_redacted: number
  emails_redacted: number
  hostnames_redacted: number
  example_path_before: string
  example_path_after: string
  example_ip_before: string
  example_ip_after: string
}

export interface SupportPreview {
  diagnostic: SupportDiagnostic
  redaction_summary: SupportRedactionSummary
}
```

- [ ] **Step 4.2:** Add `fetchSupportPreview()` and `downloadSupportBundle()` to `frontend/src/api/client.ts`

Add near the other log-related functions (search for `getLogs`):

```typescript
export async function fetchSupportPreview(): Promise<SupportPreview> {
  const res = await api.get<SupportPreview>('/logs/support-preview')
  return res.data
}

export async function downloadSupportBundle(): Promise<void> {
  const res = await api.get('/logs/support-export', { responseType: 'blob' })
  const contentDisposition = res.headers['content-disposition'] as string | undefined
  const filenameMatch = contentDisposition?.match(/filename="?([^"]+)"?/)
  const filename =
    filenameMatch?.[1] ??
    `sublarr-support-${new Date().toISOString().replace(/[:.]/g, '-')}.zip`
  const url = URL.createObjectURL(res.data as Blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}
```

- [ ] **Step 4.3:** Verify TypeScript compiles

```bash
cd frontend
npx tsc --noEmit
```
Expected: No errors

- [ ] **Step 4.4:** Commit

```bash
git add frontend/src/api/client.ts frontend/src/lib/types.ts
git commit -m "feat: add fetchSupportPreview and downloadSupportBundle to API client"
```

---

## Task 5: i18n Keys

**Files:**
- Modify: `frontend/src/i18n/locales/en/settings.json`
- Modify: `frontend/src/i18n/locales/de/settings.json`
- Modify: `frontend/src/i18n/locales/en/logs.json` (note: rotation keys stay, just noting they move to settings tab)
- Modify: `frontend/src/i18n/locales/de/logs.json` (same)

- [ ] **Step 5.1:** Add keys to `frontend/src/i18n/locales/en/settings.json`

Append inside the root JSON object:

```json
"protokoll_tab": "Logging",
"log_settings": "Log Settings",
"log_rotation": "Log Rotation",
"max_size_mb": "Max file size (MB)",
"backup_count": "Backup files",
"log_viewer_display": "Log Viewer Display",
"log_viewer_display_desc": "These settings only affect what you see in the Logs page — they do not change the log files.",
"category_scanner": "Scanner",
"category_translation": "Translation",
"category_providers": "Providers",
"category_jobs": "Background Jobs",
"category_auth": "Auth",
"category_api_access": "API Requests",
"show_timestamps": "Show timestamps",
"wrap_lines": "Wrap long lines",
"support_section": "Support",
"support_section_desc": "Export an anonymized bundle with logs, configuration, and diagnostic data to share with the developer.",
"support_export_button": "Export Support Bundle",
"support_modal_title": "Export Support Bundle",
"support_modal_loading": "Preparing preview...",
"support_modal_error": "Preview could not be loaded",
"support_modal_cancel": "Cancel",
"support_modal_download": "Download ZIP",
"support_diagnostic_title": "Diagnostic Report",
"support_redaction_title": "Anonymization",
"support_uptime": "Uptime",
"support_memory": "Memory",
"support_top_errors": "Top Errors (last 24h)",
"support_providers": "Providers",
"support_log_files": "Log files",
"support_no_errors": "No errors in the last 24h",
"support_before": "Before",
"support_after": "After",
"support_paths_label": "Paths",
"support_ips_label": "IPs"
```

- [ ] **Step 5.2:** Add German translations to `frontend/src/i18n/locales/de/settings.json`

```json
"protokoll_tab": "Protokoll",
"log_settings": "Protokoll-Einstellungen",
"log_rotation": "Log-Rotation",
"max_size_mb": "Max. Dateigröße (MB)",
"backup_count": "Backup-Dateien",
"log_viewer_display": "Protokoll-Ansicht",
"log_viewer_display_desc": "Diese Einstellungen betreffen nur die Anzeige im Protokoll-Fenster — die Log-Dateien bleiben unverändert.",
"category_scanner": "Scanner",
"category_translation": "Übersetzung",
"category_providers": "Provider",
"category_jobs": "Hintergrundjobs",
"category_auth": "Auth",
"category_api_access": "API-Zugriffe",
"show_timestamps": "Zeitstempel anzeigen",
"wrap_lines": "Lange Zeilen umbrechen",
"support_section": "Support",
"support_section_desc": "Exportiert ein anonymisiertes Bundle mit Logs, Konfiguration und Diagnosedaten zur Weitergabe an den Entwickler.",
"support_export_button": "Support-Bundle exportieren",
"support_modal_title": "Support-Bundle exportieren",
"support_modal_loading": "Vorschau wird geladen...",
"support_modal_error": "Vorschau konnte nicht geladen werden",
"support_modal_cancel": "Abbrechen",
"support_modal_download": "ZIP herunterladen",
"support_diagnostic_title": "Diagnostic Report",
"support_redaction_title": "Anonymisierung",
"support_uptime": "Uptime",
"support_memory": "Speicher",
"support_top_errors": "Top-Fehler (letzte 24h)",
"support_providers": "Provider",
"support_log_files": "Log-Dateien",
"support_no_errors": "Keine Fehler in den letzten 24h",
"support_before": "Vorher",
"support_after": "Nachher",
"support_paths_label": "Pfade",
"support_ips_label": "IPs"
```

- [ ] **Step 5.3:** Note on `logs.json` — the rotation keys (`rotation_config`, `max_size_mb`, `backup_count`) **remain** in `logs.json` as they are still referenced in the old Logs.tsx until Task 8 removes them. After Task 8 they become unused — remove them from `logs.json` in Task 8's commit to keep the files clean.

- [ ] **Step 5.4:** Commit

```bash
git add frontend/src/i18n/
git commit -m "feat: add i18n keys for ProtokollTab and support export modal (en + de)"
```

---

## Task 6: ProtokollTab Component

**Files:**
- Create: `frontend/src/pages/Settings/ProtokollTab.tsx`

- [ ] **Step 6.1:** Create `frontend/src/pages/Settings/ProtokollTab.tsx`

Follow the SecurityTab pattern (SettingsCard + TanStack Query + toast). The log-level control is an inline `<select>` calling the existing settings save API — same pattern as other settings fields:

```tsx
import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { FileText, Eye, Package } from 'lucide-react'
import {
  fetchSupportPreview,
  downloadSupportBundle,
  getConfig,
  updateConfig,
} from '@/api/client'
import { useLogRotation, useUpdateLogRotation } from '@/hooks/useApi'
import { toast } from '@/components/shared/Toast'
import { SettingsCard } from '@/components/shared/SettingsCard'
import type { SupportPreview } from '@/lib/types'

// ─── Log viewer preferences (localStorage, client-side only) ─────────────────

const PREFS_KEY = 'sublarr_log_view_prefs'

interface LogViewPrefs {
  categories: Record<string, boolean>
  showTimestamps: boolean
  wrapLines: boolean
}

const DEFAULT_PREFS: LogViewPrefs = {
  categories: {
    scanner: true,
    translation: true,
    providers: true,
    jobs: true,
    auth: true,
    api_access: false,
  },
  showTimestamps: true,
  wrapLines: false,
}

function loadPrefs(): LogViewPrefs {
  try {
    const raw = localStorage.getItem(PREFS_KEY)
    return raw ? { ...DEFAULT_PREFS, ...JSON.parse(raw) } : DEFAULT_PREFS
  } catch {
    return DEFAULT_PREFS
  }
}

function savePrefs(prefs: LogViewPrefs): void {
  localStorage.setItem(PREFS_KEY, JSON.stringify(prefs))
}

// ─── Support export modal ─────────────────────────────────────────────────────

function SupportModal({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation('settings')
  const [downloading, setDownloading] = useState(false)

  const { data, isLoading, isError } = useQuery<SupportPreview>({
    queryKey: ['support-preview'],
    queryFn: fetchSupportPreview,
    staleTime: 0,
    retry: 1,
  })

  const handleDownload = async () => {
    setDownloading(true)
    try {
      await downloadSupportBundle()
    } catch {
      toast(t('support_modal_error'), 'error')
    } finally {
      setDownloading(false)
    }
  }

  const diag = data?.diagnostic
  const rs = data?.redaction_summary

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={e => e.target === e.currentTarget && onClose()}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="support-modal-title"
        className="w-full max-w-lg rounded-xl p-6 shadow-xl"
        style={{ background: 'var(--bg-surface)', maxHeight: '85vh', overflowY: 'auto' }}
      >
        <h2 id="support-modal-title" className="mb-4 text-lg font-semibold">
          {t('support_modal_title')}
        </h2>

        {isLoading && (
          <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
            {t('support_modal_loading')}
          </p>
        )}

        {isError && !data && (
          <p className="mb-3 text-sm" style={{ color: 'var(--text-error, #f87171)' }}>
            {t('support_modal_error')}
          </p>
        )}

        {diag && (
          <div
            className="mb-4 rounded-lg p-4 text-sm space-y-3"
            style={{ background: 'var(--bg-primary)', border: '1px solid var(--border)' }}
          >
            <p className="font-medium">{t('support_diagnostic_title')}</p>
            <p style={{ color: 'var(--text-secondary)' }}>
              Sublarr {diag.version} · {diag.timestamp_utc}
            </p>
            {(diag.uptime_minutes != null || diag.memory_mb != null) && (
              <p style={{ color: 'var(--text-secondary)' }}>
                {diag.uptime_minutes != null &&
                  `${t('support_uptime')}: ${Math.floor(diag.uptime_minutes / 60)}h ${diag.uptime_minutes % 60}m`}
                {diag.uptime_minutes != null && diag.memory_mb != null && '  ·  '}
                {diag.memory_mb != null && `${t('support_memory')}: ${diag.memory_mb} MB`}
              </p>
            )}
            <div>
              <p className="font-medium mb-1">{t('support_top_errors')}</p>
              {diag.top_errors.length === 0 ? (
                <p style={{ color: 'var(--text-secondary)' }}>{t('support_no_errors')}</p>
              ) : (
                <ul className="space-y-0.5">
                  {diag.top_errors.slice(0, 5).map((e, i) => (
                    <li key={i} style={{ color: 'var(--text-secondary)' }}>
                      ✗ {e.message} (×{e.count})
                    </li>
                  ))}
                </ul>
              )}
            </div>
            {diag.provider_status.length > 0 && (
              <div>
                <p className="font-medium mb-1">{t('support_providers')}</p>
                <p style={{ color: 'var(--text-secondary)' }}>
                  {diag.provider_status
                    .map(p => `${p.active ? '●' : '○'} ${p.name}`)
                    .join('  ')}
                </p>
              </div>
            )}
            {!diag.db_stats_error && (
              <p style={{ color: 'var(--text-secondary)' }}>
                Wanted: {diag.wanted.total} · Pending: {diag.wanted.pending} · Failed:{' '}
                {diag.wanted.failed}
              </p>
            )}
          </div>
        )}

        {rs && (
          <div
            className="mb-4 rounded-lg p-4 text-sm space-y-2"
            style={{ background: 'var(--bg-primary)', border: '1px solid var(--border)' }}
          >
            <p className="font-medium">{t('support_redaction_title')}</p>
            <p style={{ color: 'var(--text-secondary)' }}>
              {rs.log_files_found} {t('support_log_files')} · {rs.ips_redacted} IPs ·{' '}
              {rs.api_keys_redacted} Keys · {rs.paths_redacted}{' '}
              {t('support_paths_label').toLowerCase()}
            </p>
            {rs.example_path_before && (
              <div className="mt-2">
                <p className="text-xs font-medium">{t('support_paths_label')}:</p>
                <p className="text-xs font-mono" style={{ color: 'var(--text-secondary)' }}>
                  <span className="font-sans font-medium">{t('support_before')}:</span>{' '}
                  {rs.example_path_before}
                </p>
                <p className="text-xs font-mono" style={{ color: 'var(--text-secondary)' }}>
                  <span className="font-sans font-medium">{t('support_after')}:</span>{' '}
                  {rs.example_path_after}
                </p>
              </div>
            )}
            {rs.example_ip_before && (
              <div className="mt-1">
                <p className="text-xs font-medium">{t('support_ips_label')}:</p>
                <p className="text-xs font-mono" style={{ color: 'var(--text-secondary)' }}>
                  <span className="font-sans font-medium">{t('support_before')}:</span>{' '}
                  {rs.example_ip_before}
                </p>
                <p className="text-xs font-mono" style={{ color: 'var(--text-secondary)' }}>
                  <span className="font-sans font-medium">{t('support_after')}:</span>{' '}
                  {rs.example_ip_after}
                </p>
              </div>
            )}
          </div>
        )}

        <div className="flex justify-end gap-3">
          <button
            autoFocus
            onClick={onClose}
            className="rounded-lg px-4 py-2 text-sm"
            style={{ background: 'var(--bg-primary)', border: '1px solid var(--border)' }}
          >
            {t('support_modal_cancel')}
          </button>
          <button
            onClick={handleDownload}
            disabled={downloading}
            className="rounded-lg px-4 py-2 text-sm font-medium"
            style={{ background: 'var(--bg-accent)', color: 'var(--text-on-accent)' }}
          >
            {downloading ? '...' : t('support_modal_download')}
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── Main tab component ───────────────────────────────────────────────────────

const LOG_LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR'] as const

export function ProtokollTab() {
  const { t } = useTranslation('settings')
  const queryClient = useQueryClient()

  // Log-level (uses the same settings API as the rest of the settings page)
  const { data: config } = useQuery({ queryKey: ['config'], queryFn: getConfig })
  const { mutate: saveConfig } = useMutation({
    mutationFn: (patch: Record<string, unknown>) => updateConfig(patch),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['config'] })
      toast(t('saved', { ns: 'common' }), 'success')
    },
  })

  // Log rotation
  const { data: rotation } = useLogRotation()
  const updateRotation = useUpdateLogRotation()
  const [maxSize, setMaxSize] = useState(5)
  const [backupCount, setBackupCount] = useState(3)

  useEffect(() => {
    if (rotation) {
      setMaxSize(rotation.max_size_mb ?? 5)
      setBackupCount(rotation.backup_count ?? 3)
    }
  }, [rotation])

  const handleSaveRotation = () => {
    updateRotation.mutate(
      { max_size_mb: maxSize, backup_count: backupCount },
      { onSuccess: () => toast(t('saved', { ns: 'common' }), 'success') },
    )
  }

  // Log viewer prefs (localStorage)
  const [prefs, setPrefs] = useState<LogViewPrefs>(loadPrefs)
  const [showModal, setShowModal] = useState(false)

  const toggleCategory = (key: string) => {
    const next = { ...prefs, categories: { ...prefs.categories, [key]: !prefs.categories[key] } }
    setPrefs(next)
    savePrefs(next)
  }

  const togglePref = (key: 'showTimestamps' | 'wrapLines') => {
    const next = { ...prefs, [key]: !prefs[key] }
    setPrefs(next)
    savePrefs(next)
  }

  const CATEGORIES = [
    { key: 'scanner',     label: t('category_scanner') },
    { key: 'translation', label: t('category_translation') },
    { key: 'providers',   label: t('category_providers') },
    { key: 'jobs',        label: t('category_jobs') },
    { key: 'auth',        label: t('category_auth') },
    { key: 'api_access',  label: t('category_api_access') },
  ]

  return (
    <div className="space-y-6">
      {/* ── Log Settings ── */}
      <SettingsCard title={t('log_settings')} icon={FileText}>
        <div className="space-y-4 p-4">
          {/* Log level */}
          <div>
            <label className="block text-sm font-medium mb-1">Log-Level</label>
            <select
              value={(config as Record<string, string> | undefined)?.log_level ?? 'INFO'}
              onChange={e => saveConfig({ log_level: e.target.value })}
              className="rounded-lg px-3 py-2 text-sm"
              style={{ background: 'var(--bg-primary)', border: '1px solid var(--border)' }}
            >
              {LOG_LEVELS.map(l => (
                <option key={l} value={l}>{l}</option>
              ))}
            </select>
          </div>

          {/* Log rotation */}
          <p className="text-sm font-medium">{t('log_rotation')}</p>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm mb-1">{t('max_size_mb')}</label>
              <input
                type="number" min={1} max={100} value={maxSize}
                onChange={e => setMaxSize(Math.min(100, Math.max(1, Number(e.target.value))))}
                className="w-full rounded-lg px-3 py-2 text-sm"
                style={{ background: 'var(--bg-primary)', border: '1px solid var(--border)' }}
              />
            </div>
            <div>
              <label className="block text-sm mb-1">{t('backup_count')}</label>
              <input
                type="number" min={1} max={20} value={backupCount}
                onChange={e => setBackupCount(Math.min(20, Math.max(1, Number(e.target.value))))}
                className="w-full rounded-lg px-3 py-2 text-sm"
                style={{ background: 'var(--bg-primary)', border: '1px solid var(--border)' }}
              />
            </div>
          </div>
          <button
            onClick={handleSaveRotation}
            disabled={updateRotation.isPending}
            className="rounded-lg px-4 py-2 text-sm font-medium"
            style={{ background: 'var(--bg-accent)', color: 'var(--text-on-accent)' }}
          >
            {updateRotation.isPending ? '...' : t('save', { ns: 'common' })}
          </button>
        </div>
      </SettingsCard>

      {/* ── Log Viewer Display ── */}
      <SettingsCard title={t('log_viewer_display')} icon={Eye}>
        <div className="space-y-3 p-4">
          <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
            {t('log_viewer_display_desc')}
          </p>
          <div className="grid grid-cols-2 gap-2">
            {CATEGORIES.map(cat => (
              <label key={cat.key} className="flex items-center gap-2 cursor-pointer text-sm">
                <input
                  type="checkbox"
                  checked={prefs.categories[cat.key] ?? true}
                  onChange={() => toggleCategory(cat.key)}
                  className="rounded"
                />
                {cat.label}
              </label>
            ))}
          </div>
          <div className="border-t pt-3 space-y-2" style={{ borderColor: 'var(--border)' }}>
            <label className="flex items-center gap-2 cursor-pointer text-sm">
              <input type="checkbox" checked={prefs.showTimestamps}
                onChange={() => togglePref('showTimestamps')} className="rounded" />
              {t('show_timestamps')}
            </label>
            <label className="flex items-center gap-2 cursor-pointer text-sm">
              <input type="checkbox" checked={prefs.wrapLines}
                onChange={() => togglePref('wrapLines')} className="rounded" />
              {t('wrap_lines')}
            </label>
          </div>
        </div>
      </SettingsCard>

      {/* ── Support ── */}
      <SettingsCard title={t('support_section')} icon={Package}>
        <div className="p-4">
          <p className="text-sm mb-4" style={{ color: 'var(--text-secondary)' }}>
            {t('support_section_desc')}
          </p>
          <button
            onClick={() => setShowModal(true)}
            className="rounded-lg px-4 py-2 text-sm font-medium"
            style={{ background: 'var(--bg-accent)', color: 'var(--text-on-accent)' }}
          >
            {t('support_export_button')}
          </button>
        </div>
      </SettingsCard>

      {showModal && <SupportModal onClose={() => setShowModal(false)} />}
    </div>
  )
}
```

- [ ] **Step 6.2:** Verify TypeScript compiles

```bash
cd frontend
npx tsc --noEmit
```
Expected: No errors (fix any missing imports or type errors)

- [ ] **Step 6.3:** Commit

```bash
git add frontend/src/pages/Settings/ProtokollTab.tsx
git commit -m "feat: add ProtokollTab with log settings, viewer prefs, and support export modal"
```

---

## Task 7: Wire ProtokollTab into Settings

**Files:**
- Modify: `frontend/src/pages/Settings/index.tsx`

- [ ] **Step 7.1:** Add lazy import for `ProtokollTab` at the top of `index.tsx` alongside the other lazy imports

```typescript
const ProtokollTab = lazy(() =>
  import('./ProtokollTab').then(m => ({ default: m.ProtokollTab }))
)
```

- [ ] **Step 7.2:** Add `"Protokoll"` to the System group in `NAV_GROUPS` (around line 69)

```typescript
{ title: 'System', icon: Cog, items: ['Events & Hooks', 'Backup', 'Subtitle Tools', 'Cleanup', 'Integrations', 'Notification Templates', 'Security', 'Protokoll'] },
```

- [ ] **Step 7.3:** Add `TAB_KEYS` entry (around line 600)

```typescript
'Protokoll': 'settings:protokoll_tab',
```

- [ ] **Step 7.4:** Render `ProtokollTab` in the tab render block (search for `<SecurityTab`)

```tsx
{activeTab === 'Protokoll' && <ProtokollTab />}
```

- [ ] **Step 7.5:** Remove `log_level` from the General tab

Find the `SettingsCard` with title `"Protokollierung"` that renders only `log_level` (around line 1042). Remove the entire `<SettingsCard>` block. Verify no other settings were inside it before deleting.

- [ ] **Step 7.6:** Verify TypeScript + lint

```bash
cd frontend
npx tsc --noEmit && npm run lint
```
Expected: No errors

- [ ] **Step 7.7:** Commit

```bash
git add frontend/src/pages/Settings/index.tsx
git commit -m "feat: add Protokoll tab to System settings group; remove log_level from General tab"
```

---

## Task 8: Update Logs.tsx

**Files:**
- Modify: `frontend/src/pages/Logs.tsx`
- Modify: `frontend/src/i18n/locales/en/logs.json` (remove now-unused rotation keys)
- Modify: `frontend/src/i18n/locales/de/logs.json` (same)

- [ ] **Step 8.1:** Remove rotation-related code from `Logs.tsx`

Remove these imports:
```typescript
import { useLogRotation, useUpdateLogRotation } from '@/hooks/useApi'
```
(keep `useLogs`, `useWebSocket`, and other imports)

Remove all rotation state and handlers: `showRotation`, `maxSizeMb`, `backupCount`, `rotation` query, `updateRotation` mutation, `handleSaveRotation` function, and the entire rotation collapsible JSX block (the `<div>` containing the ChevronDown/ChevronUp toggle and the grid with inputs).

- [ ] **Step 8.2:** Add log viewer prefs reading and category filter

Add near the top of the `Logs` component (after existing state declarations):

```typescript
const CATEGORY_PREFIXES: Record<string, string[]> = {
  scanner:     ['wanted_scanner', 'standalone'],
  translation: ['translation', 'llm_utils'],
  providers:   ['jimaku', 'podnapisi', 'opensubtitles', 'subdl', 'addic7ed'],
  jobs:        ['apscheduler', 'worker'],
  auth:        ['auth', 'auth_ui'],
  api_access:  ['werkzeug'],
}

const logViewPrefs = useMemo(() => {
  try {
    const raw = localStorage.getItem('sublarr_log_view_prefs')
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
// eslint-disable-next-line react-hooks/exhaustive-deps
}, []) // intentionally read once on mount; user must navigate away and back to refresh

function isLineVisible(line: string): boolean {
  if (!logViewPrefs?.categories) return true
  for (const [cat, prefixes] of Object.entries(CATEGORY_PREFIXES)) {
    if (logViewPrefs.categories[cat] === false) {
      if ((prefixes as string[]).some(prefix => line.includes(` ${prefix}:`))) return false
    }
  }
  return true
}
```

Apply the filter to the log data before passing to the virtualizer:

```typescript
const visibleLogs = useMemo(
  () => (logs ?? []).filter(isLineVisible),
  [logs, logViewPrefs],
)
```

Replace `logs` with `visibleLogs` everywhere in the virtualizer and render logic.

- [ ] **Step 8.3:** Apply display prefs

Add a `formatLine` helper:

```typescript
function formatLine(line: string): string {
  if (logViewPrefs?.showTimestamps === false) {
    return line.replace(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d+ /, '')
  }
  return line
}
```

Apply in the log line render: `formatLine(log)`.

Apply `wrapLines` to the line element style:
```typescript
style={{ whiteSpace: logViewPrefs?.wrapLines ? 'pre-wrap' : 'pre' }}
```

- [ ] **Step 8.4:** Remove now-unused rotation keys from logs.json

In `frontend/src/i18n/locales/en/logs.json` and `de/logs.json`, remove the keys `rotation_config`, `max_size_mb`, `backup_count` (they are now in `settings.json`). Verify no other file still references them via `t('rotation_config')` etc. before deleting.

```bash
grep -r "rotation_config\|t('max_size_mb')\|t('backup_count')" frontend/src --include="*.tsx" --include="*.ts"
```
Expected: No results (all rotation UI removed from Logs.tsx)

- [ ] **Step 8.5:** Verify TypeScript + lint

```bash
cd frontend
npx tsc --noEmit && npm run lint
```

- [ ] **Step 8.6:** Commit

```bash
git add frontend/src/pages/Logs.tsx frontend/src/i18n/
git commit -m "feat: remove rotation UI from Logs; apply log viewer category filter and display prefs"
```

---

## Task 9: Full QA

- [ ] **Step 9.1:** Run backend test suite

```bash
cd backend
python -m pytest tests/test_support_export.py -v
ruff check . && ruff format --check .
```
Expected: All PASS, clean lint

- [ ] **Step 9.2:** Run frontend checks

```bash
cd frontend
npm run lint && npx tsc --noEmit && npm run test -- --run
```
Expected: All PASS

- [ ] **Step 9.3:** Manual smoke test (dev server running: `npm run dev` from project root)

1. Open Settings → System → Protokoll
2. Log rotation inputs load with current values — change and save → check toast
3. Toggle "API-Zugriffe" off → go to Logs page → werkzeug lines disappear
4. Toggle "Zeitstempel anzeigen" off → Logs page timestamps disappear
5. Return to Settings → System → Protokoll → click "Support-Bundle exportieren"
6. Modal opens, preview loads (~1s), diagnostic report and redaction section visible
7. At least one before/after example shown
8. Click "ZIP herunterladen" → ZIP downloads
9. Open ZIP: verify `logs/`, `diagnostic-report.md`, `db-stats.json`, `config-snapshot.json`, `system-info.txt` all present
10. Open `config-snapshot.json` → `api_key` value is `***REDACTED***`
11. Open `diagnostic-report.md` → readable Markdown with version, errors, providers

- [ ] **Step 9.4:** Final commit if QA fixes needed

```bash
git add -p
git commit -m "fix: QA fixes for support export feature"
```
