# Support Export — Design Spec
**Date:** 2026-03-17
**Status:** Approved
**Feature:** Enhanced Support Bundle Export (Settings → System Tab)

---

## Overview

Replace the minimal existing support export endpoint with a fully featured support bundle system. The feature lives in **Settings → System Tab** and lets a user export an anonymized diagnostic bundle to send to the developer. Before confirming, the user sees a full preview of what will be exported — both a diagnostic report and a redaction summary.

---

## 1. Anonymization Rules

All sensitive data is redacted before anything leaves the system. Rules applied in order:

| Data Type | Original | Anonymized |
|-----------|----------|------------|
| Private IPv4 | `192.168.178.194` | `192.168.xxx.xxx` |
| Public IPv4 | `85.214.132.17` | `xxx.xxx.xxx.xxx` |
| Localhost | `127.0.0.1` | unchanged |
| File paths | `/media/Anime/86 Eighty Six/S01E01.mkv` | `media/S01E01.mkv` |
| Directory names (series) | `/Anime/86 Eighty Six/` | `/Media/` |
| API keys / tokens | `apikey=3bdcc724abc...` | `apikey=***REDACTED***` |
| Passwords | `password: "geheim123"` | `password: ***REDACTED***` |
| Email addresses | `user@example.com` | `***USER***` |
| Hostnames | `pve-node1`, `cardinal` | `***HOST***` |
| Unix home paths | `/home/dennis/sublarr` | `~/sublarr` |

The anonymization logic lives in a standalone `_anonymize(text: str) -> str` helper in `backend/routes/system.py` (replacing the existing minimal version).

---

## 2. Backend: Preview Endpoint

**`GET /api/v1/logs/support-preview`**

Fast endpoint (~100–500ms). Analyzes log files and config without generating the ZIP. Returns everything needed to render the modal.

**Response:**
```json
{
  "diagnostic": {
    "version": "0.30.0-beta",
    "timestamp_utc": "2026-03-17T14:30:00Z",
    "uptime_minutes": 222,
    "memory_mb": 312,
    "top_errors": [
      { "message": "jimaku: 429 Too Many Requests", "count": 12, "last_seen": "14:22" },
      { "message": "Translation timeout", "count": 3, "last_seen": "13:55" },
      { "message": "Scanner: path not found", "count": 1, "last_seen": "11:30" }
    ],
    "provider_status": [
      { "name": "Jimaku", "active": true },
      { "name": "Podnapisi", "active": true },
      { "name": "OpenSubtitles", "active": false }
    ],
    "wanted": { "total": 42, "pending": 31, "extracted": 8, "failed": 3 },
    "translations": { "total": 156, "completed": 148, "failed": 8 },
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
    "example_before": "[INFO] Downloading subtitle for /media/Anime/86 Eighty Six/S01E01.mkv from 192.168.178.194",
    "example_after":  "[INFO] Downloading subtitle for media/S01E01.mkv from 192.168.xxx.xxx"
  }
}
```

---

## 3. Backend: Export Endpoint

**`GET /api/v1/logs/support-export`** (enhanced, replaces existing)

Generates and streams a ZIP file. All content is anonymized before writing to the archive.

**ZIP structure:**
```
sublarr-support-2026-03-17T14-30-00Z.zip
├── logs/
│   ├── sublarr.log          (anonymized)
│   ├── sublarr.log.1        (anonymized, if present)
│   ├── sublarr.log.2        (anonymized, if present)
│   └── sublarr.log.3        (anonymized, if present)
├── config-snapshot.json     (all settings; secrets = ***REDACTED***)
├── db-stats.json            (counts and status only, no user data)
├── system-info.txt          (version, Python, OS, uptime, memory)
└── diagnostic-report.md    (human-readable error summary)
```

**`db-stats.json` example:**
```json
{
  "wanted": { "total": 42, "pending": 31, "extracted": 8, "failed": 3 },
  "translations": { "total": 156, "completed": 148, "failed": 8 },
  "providers": { "active": 3, "last_scan_ago_minutes": 12 },
  "config_entries": 24,
  "last_errors": [
    "jimaku 429 at 14:22",
    "translation timeout at 13:55"
  ]
}
```

**`diagnostic-report.md`** contains: version header, system status, top-10 errors of the last 24h with counts, provider status table, wanted/translation stats. Same data as the preview endpoint — identical source, different format.

---

## 4. Frontend: System Tab Restructure

The Settings → System Tab gets three new/updated sections. The log rotation collapsible block in the Logs page (`Logs.tsx`) is **removed** — that UI moves here.

### 4a. Protokoll-Einstellungen (Log Settings)

- **Log-Level** dropdown: DEBUG / INFO / WARNING / ERROR (existing setting, moved here if not already)
- **Log-Rotation**:
  - Max. Dateigröße: number input (1–100 MB)
  - Backup-Anzahl: number input (1–20)
  - Calls existing `GET/PUT /api/v1/logs/rotation` endpoints — no backend change needed

### 4b. Protokoll-Ansicht (Log Viewer Display — localStorage only)

Toggle which logger categories appear in the Logs page viewer. Stored in `localStorage`, never sent to backend.

| Category | Loggers | Default |
|----------|---------|---------|
| Scanner | `wanted_scanner`, `standalone` | on |
| Übersetzung | `translation`, `llm_utils` | on |
| Provider | `jimaku`, `podnapisi`, `opensubtitles`, … | on |
| Hintergrundjobs | `apscheduler`, `worker` | on |
| Auth | `auth`, `auth_ui` | on |
| API-Zugriffe | `werkzeug` | off (very noisy) |

Two additional display toggles:
- **Zeitstempel anzeigen** (show timestamps)
- **Lange Zeilen umbrechen** (wrap long lines)

The Logs page reads these settings from `localStorage` on mount and applies them as client-side filters on the log stream.

### 4c. Support

Button: **"Support-Bundle exportieren"**

On click → modal opens and immediately fires `GET /api/v1/logs/support-preview`.

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
  │   ✗ Scanner: Pfad nicht gefunden (×1)          │
  │                                                │
  │ Provider                                       │
  │   ● Jimaku  ● Podnapisi  ○ OpenSubtitles       │
  │                                                │
  │ Wanted: 42 · Pending: 31 · Failed: 3           │
  └───────────────────────────────────────────────┘

  ┌── Anonymisierung ──────────────────────────────┐
  │ 3 Log-Dateien · 12 IPs · 4 Keys · 8 Pfade     │
  │                                                │
  │ Vorher:  /Anime/86 Eighty Six/S01E01.mkv       │
  │ Nachher: media/S01E01.mkv                      │
  └───────────────────────────────────────────────┘

  [ Abbrechen ]           [ ZIP herunterladen ]
```

Loading state shown while preview loads. Error state if preview fails (still allows download). ZIP download triggered directly via `window.open` or `<a download>` against the export endpoint.

---

## 5. Files to Create / Modify

### Backend
| File | Change |
|------|--------|
| `backend/routes/system.py` | Replace `_anonymize()` + `_REDACT_PATTERNS` with enhanced version; add `GET /api/v1/logs/support-preview` endpoint; enhance `GET /api/v1/logs/support-export` ZIP contents |

### Frontend
| File | Change |
|------|--------|
| `frontend/src/pages/Settings/SystemTab.tsx` | Add Protokoll-Einstellungen section, Protokoll-Ansicht section (localStorage toggles), Support section with modal |
| `frontend/src/pages/Logs.tsx` | Remove log rotation collapsible; read logger category + display toggles from localStorage and apply as filters |
| `frontend/src/api/client.ts` | Add `fetchSupportPreview()` and ensure `downloadSupportExport()` exists |

---

## 6. Out of Scope

- Async/background ZIP generation (not needed — ZIP builds in <2s for typical log sizes)
- User-configurable anonymization rules
- Sending the bundle automatically (always manual user action)
- Storing export history
