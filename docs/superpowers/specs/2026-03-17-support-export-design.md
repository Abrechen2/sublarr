# Support Export — Design Spec
**Date:** 2026-03-17
**Status:** Approved
**Feature:** Enhanced Support Bundle Export (Settings → System → Protokoll Tab)

---

## Overview

Replace the minimal existing support export endpoint with a fully featured support bundle system. The feature lives in a **new "Protokoll" sub-tab** within Settings → System group. Before confirming the export, the user sees a full preview: a diagnostic report and a redaction summary showing exactly what data leaves the system.

---

## 1. Anonymization Rules

All sensitive data is redacted before anything leaves the system. Rules applied in order:

| Data Type | Original | Anonymized | Algorithm |
|-----------|----------|------------|-----------|
| RFC 1918 IPv4 | `192.168.178.194` | `192.168.xxx.xxx` | Explicit CIDR check (see below); keep first two octets |
| Public IPv4 | `85.214.132.17` | `xxx.xxx.xxx.xxx` | All non-private, non-loopback |
| Localhost | `127.0.0.1`, `::1` | unchanged | exact match, checked first |
| File paths (full) | `/media/Anime/86 Eighty Six/S01E01.mkv` | `media/S01E01.mkv` | keep only last path segment; strip leading slash |
| Directory segments | `Anime/86 Eighty Six/` | `Media/` | replace intermediate path components |
| API keys / tokens | `apikey=3bdcc724abc...` | `apikey=***REDACTED***` | field-name heuristic (see below) |
| Passwords | `password: "geheim123"` | `password: ***REDACTED***` | field-name heuristic |
| Email addresses | `user@example.com` | `***USER***` | RFC 5322 pattern |
| Server hostname | `pve-node1` | `***HOST***` | dynamic: `socket.gethostname()` at export time |
| Unix home paths | `/home/dennis/sublarr` | `~/sublarr` | `/home/<user>/` and `/root/` prefixes |

**Field-name heuristic for secrets:** any field whose name contains `key`, `token`, `password`, `secret`, or `credential` (case-insensitive) has its value redacted. Applied to log text via regex AND to structured JSON via field-level iteration (not regex-on-JSON).

**IP classification — use explicit RFC 1918 CIDR ranges, not `ipaddress.is_private`** (which covers link-local and other ranges beyond RFC 1918 in Python 3.11+):

```python
import ipaddress, re

_RFC1918 = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
]

def _classify_ip(ip: str) -> str:
    """IPv4 only. Returns anonymized string."""
    try:
        addr = ipaddress.IPv4Address(ip)  # raises for IPv6 / invalid
    except ValueError:
        return ip
    if addr.is_loopback:
        return ip
    for network in _RFC1918:
        if addr in network:
            parts = ip.split(".")
            return f"{parts[0]}.{parts[1]}.xxx.xxx"
    return "xxx.xxx.xxx.xxx"
```

**Example pairs shown in modal** (one rule per example):

```
# Path rule:
Vorher:  Downloading subtitle for /media/Anime/86 Eighty Six/S01E01.mkv
Nachher: Downloading subtitle for media/S01E01.mkv

# IP rule:
Vorher:  Connected to provider at 192.168.178.194
Nachher: Connected to provider at 192.168.xxx.xxx
```

---

## 2. Backend: Preview Endpoint

**`GET /api/v1/logs/support-preview`**

Requires API key auth (same as all `/api/v1/` endpoints). Fast (~100–500ms). Analyzes log files and queries DB; does not generate the ZIP.

**Response 200:**
```json
{
  "diagnostic": {
    "version": "0.30.0-beta",
    "timestamp_utc": "2026-03-17T14:30:00Z",
    "uptime_minutes": 222,
    "memory_mb": 312,
    "top_errors": [
      { "message": "jimaku: 429 Too Many Requests", "count": 12, "last_seen": "14:22" },
      { "message": "Translation timeout", "count": 3, "last_seen": "13:55" }
    ],
    "provider_status": [
      { "name": "Jimaku", "active": true },
      { "name": "Podnapisi", "active": true },
      { "name": "OpenSubtitles", "active": false }
    ],
    "wanted": { "total": 42, "pending": 31, "extracted": 8, "failed": 3 },
    "translations": { "total_requests": 156, "successful": 148, "failed": 8 },
    "last_scan_ago_minutes": 12,
    "config_entries_count": 24
  },
  "redaction_summary": {
    "log_files_found": 3,
    "ips_redacted": 12,
    "api_keys_redacted": 4,
    "paths_redacted": 8,
    "emails_redacted": 0,
    "hostnames_redacted": 2,
    "example_path_before": "Downloading subtitle for /media/Anime/86 Eighty Six/S01E01.mkv",
    "example_path_after":  "Downloading subtitle for media/S01E01.mkv",
    "example_ip_before":   "Connected to provider at 192.168.178.194",
    "example_ip_after":    "Connected to provider at 192.168.xxx.xxx"
  }
}
```

**`top_errors` extraction algorithm:**
1. Read all available log files (`sublarr.log`, `.log.1`–`.log.3`)
2. Parse lines matching `[ERROR]` or `[WARNING]` via regex on log format: `\[(ERROR|WARNING)\]`
3. Filter to lines whose timestamp (parsed from `%(asctime)s` prefix, local time) falls within the last 24h; if parsing fails, include the line
4. Group by normalizing: strip timestamp + logger prefix, keep first 80 chars of message as group key
5. Count occurrences per group; sort descending; return top 10
6. `last_seen` = timestamp of most recent occurrence, formatted `HH:MM` (local time, no timezone label — log timestamps are local time via Python's default `time.localtime()`)
7. If uptime < 24h, window covers all available logs

**`provider_status` data source:**
Read `settings.providers_enabled` (a comma-separated string; empty = all registered providers enabled). Call `get_provider_registry()` to get all registered provider names, then mark each as `active: True` if it appears in `providers_enabled` or if `providers_enabled` is empty. One settings read — no DB query needed.

**`translations` data source:**
Use `TranslationRepository.get_all_backend_stats()` which returns per-backend rows with `total_requests`, `successful_translations`, `failed_translations`. Sum all rows: `total_requests` → `total_requests`, `successful_translations` → `successful`, `failed_translations` → `failed`. Wrap with `with _db_lock:` (import: `from db import _db_lock, get_db`).

**`wanted` data source:**
Use `WantedRepository.get_wanted_count(status=None)` for total, and per-status calls for pending/extracted/failed. Wrap with `with _db_lock:`.

**`uptime_minutes`:**
Process uptime via `psutil.Process().create_time()` if psutil available: `int((time.time() - psutil.Process().create_time()) / 60)`. Not system uptime.

**`memory_mb` / `uptime_minutes`:**
Use `psutil` if available; if not installed, return `null` for both. Frontend omits those lines when `null`.

**Error responses:**
- No log files found: return 200 with `"log_files_found": 0` and empty `top_errors`
- DB locked / query fails: return 200 with `"db_stats_error": "unavailable"` in the diagnostic; omit affected fields
- Unexpected exception: return 500 `{"error": "Preview generation failed: <message>"}`

---

## 3. Backend: Export Endpoint

**`GET /api/v1/logs/support-export`** (enhanced, replaces existing)

Requires API key auth. Generates and streams a ZIP file. All content anonymized.

**ZIP filename:** `sublarr-support-2026-03-17T14-30-00Z.zip` — use `datetime.utcnow().strftime("%Y-%m-%dT%H-%M-%SZ")` (hyphens instead of colons for Windows filesystem compatibility).

**ZIP structure:**
```
sublarr-support-2026-03-17T14-30-00Z.zip
├── logs/
│   ├── sublarr.log          (anonymized)
│   ├── sublarr.log.1        (anonymized, if present)
│   ├── sublarr.log.2        (anonymized, if present)
│   └── sublarr.log.3        (anonymized, if present)
├── config-snapshot.json     (all settings; secrets redacted by field-name heuristic)
├── db-stats.json            (counts and status only, no user data)
├── system-info.txt          (version, Python, OS, uptime, memory)
└── diagnostic-report.md     (same data as preview, rendered as Markdown)
```

**`config-snapshot.json` redaction:** iterate all settings fields by name; any field whose name contains `key`, `token`, `password`, `secret`, or `credential` → value replaced with `***REDACTED***`. Field-level operation on the Python dict — not regex-on-JSON text.

**`diagnostic-report.md`** contains identical data to the preview response, formatted as human-readable Markdown. Generated via a shared `_build_diagnostic() -> dict` helper called by both endpoints.

**Download auth:** Frontend uses `fetch()` with the `X-Api-Key` header, converts response to Blob, triggers download via a temporary `<a>` element. Do **not** use `window.open()` — cannot attach auth headers.

```typescript
const res = await apiClient.get('/api/v1/logs/support-export', { responseType: 'blob' })
const url = URL.createObjectURL(res.data)
const a = document.createElement('a')
a.href = url
a.download = `sublarr-support-${new Date().toISOString().replace(/[:.]/g, '-')}.zip`
a.click()
URL.revokeObjectURL(url)
```

---

## 4. Frontend: New "Protokoll" Tab

A new entry **"Protokoll"** is added to the **System** nav group in `frontend/src/pages/Settings/index.tsx` (`NAV_GROUPS`). A new component `frontend/src/pages/Settings/ProtokollTab.tsx` is created.

### 4a. Log-Einstellungen

**Log-Level** (moved from General tab):
- Remove `log_level` from the General tab's "Protokollierung" card (line ~1042 in `index.tsx`) and from the `FIELDS.filter(f => f.tab === 'General' && f.key === 'log_level')` render — it must not appear in two places.
- Render it in ProtokollTab via the standard `renderField` pattern or a dedicated control.

**Log-Rotation** (moved from `Logs.tsx`):
- Number input: Max. Dateigröße 1–100 MB
- Number input: Backup-Anzahl 1–20
- Defaults loaded on mount via `GET /api/v1/logs/rotation`; save via `PUT /api/v1/logs/rotation`
- Remove from `Logs.tsx`: the `useLogRotation` and `useUpdateLogRotation` hook imports, all local rotation state, the `handleSaveRotation` function, and the entire collapsible JSX block.

### 4b. Protokoll-Ansicht

Client-side only. Stored in `localStorage` under key `sublarr_log_view_prefs` as JSON. No backend call.

| Category key | Display name | Logger prefixes matched | Default |
|---|---|---|---|
| `scanner` | Scanner | `wanted_scanner`, `standalone` | true |
| `translation` | Übersetzung | `translation`, `llm_utils` | true |
| `providers` | Provider | `jimaku`, `podnapisi`, `opensubtitles`, `subdl`, `addic7ed` | true |
| `jobs` | Hintergrundjobs | `apscheduler`, `worker` | true |
| `auth` | Auth | `auth`, `auth_ui` | true |
| `api_access` | API-Zugriffe | `werkzeug` | false |

Two display toggles (also in `sublarr_log_view_prefs`):
- `showTimestamps`: boolean, default `true`
- `wrapLines`: boolean, default `false`

`Logs.tsx` reads `sublarr_log_view_prefs` on mount; applies category filter (hide log lines whose logger name starts with any prefix in a disabled category) and display options to the log stream.

### 4c. Support

Button: **"Support-Bundle exportieren"**

On click → modal opens and fires `fetchSupportPreview()`.

**Modal states:**
- **Loading:** spinner while preview loads
- **Loaded:** show diagnostic report + redaction summary
- **Error:** "Vorschau konnte nicht geladen werden" message, "ZIP herunterladen" button still shown (graceful degradation)

**Modal layout:**
```
[ Support-Bundle exportieren ]

  ┌── Diagnostic Report ──────────────────────────┐
  │ Sublarr v0.30.0-beta · 2026-03-17 14:30 UTC   │
  │                                                │
  │ System                                         │
  │   Uptime: 3h 42m · Speicher: 312 MB            │
  │                                                │
  │ Top-Fehler (letzte 24h)                        │
  │   ✗ jimaku: 429 Too Many Requests (×12)        │
  │   ✗ Übersetzungs-Timeout (×3)                  │
  │                                                │
  │ Provider                                       │
  │   ● Jimaku  ● Podnapisi  ○ OpenSubtitles       │
  │                                                │
  │ Wanted: 42 · Pending: 31 · Failed: 3           │
  └───────────────────────────────────────────────┘

  ┌── Anonymisierung ──────────────────────────────┐
  │ 3 Log-Dateien · 12 IPs · 4 Keys · 8 Pfade     │
  │                                                │
  │ Pfade:                                         │
  │   Vorher:  /media/Anime/86 Eighty Six/S01.mkv  │
  │   Nachher: media/S01.mkv                       │
  │                                                │
  │ IPs:                                           │
  │   Vorher:  192.168.178.194                     │
  │   Nachher: 192.168.xxx.xxx                     │
  └───────────────────────────────────────────────┘

  [ Abbrechen ]           [ ZIP herunterladen ]
```

---

## 5. Files to Create / Modify

### Backend
| File | Change |
|------|--------|
| `backend/routes/system.py` | Replace `_anonymize()` + `_REDACT_PATTERNS` with enhanced version (RFC 1918 CIDR check, dynamic hostname, path rules); add `_build_diagnostic()` shared helper; add `GET /api/v1/logs/support-preview`; enhance `GET /api/v1/logs/support-export` ZIP contents |

### Frontend
| File | Change |
|------|--------|
| `frontend/src/pages/Settings/index.tsx` | Add `"Protokoll"` to System `NAV_GROUPS`; render `<ProtokollTab />`; remove `log_level` from General tab Protokollierung card |
| `frontend/src/pages/Settings/ProtokollTab.tsx` | **New file.** Log-level setting, log rotation UI, log viewer category toggles (localStorage), support export modal |
| `frontend/src/pages/Logs.tsx` | Remove `useLogRotation`, `useUpdateLogRotation` imports, all rotation state/handlers, rotation collapsible JSX; read `sublarr_log_view_prefs` from localStorage; apply category filter + display toggles |
| `frontend/src/api/client.ts` | Add `fetchSupportPreview()` returning typed response; add `downloadSupportBundle()` using fetch→Blob pattern |
| `frontend/src/locales/de.json` (and `en.json`) | Add i18n keys for all new UI strings in ProtokollTab and support modal |

---

## 6. Out of Scope

- Async/background ZIP generation
- User-configurable anonymization rules
- Sending the bundle automatically
- Storing export history
- Log viewer category preferences synced to backend
