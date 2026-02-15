---
phase: 08-i18n-backup-admin-polish
plan: 02
subsystem: api
tags: [flask, backup, zip, statistics, csv, log-rotation, subtitle-tools, hi-removal, timing-shift]

# Dependency graph
requires:
  - phase: 00-architecture-refactoring
    provides: "Blueprint-based route modules, database_backup.py, error_handler.py"
provides:
  - "ZIP backup/restore endpoints (POST/GET /backup/full/*)"
  - "Statistics API with time-range filtering and CSV/JSON export"
  - "Log download and rotation config endpoints"
  - "Subtitle processing tools Blueprint (remove-hi, adjust-timing, common-fixes, preview)"
affects: [08-03-backup-restore-ui, 08-04-statistics-admin-ui, 08-05-subtitle-tools-ui]

# Tech tracking
tech-stack:
  added: [zipfile, csv, io, chardet (optional)]
  patterns: [ZIP archive creation with manifest, file validation with media_path security, .bak backup before modification]

key-files:
  created:
    - backend/routes/tools.py
  modified:
    - backend/routes/system.py
    - backend/routes/__init__.py

key-decisions:
  - "ZIP backup uses in-memory BytesIO buffer then writes to backup_dir -- avoids temp file management"
  - "ZIP restore imports config keys but skips secrets (same pattern as config/import endpoint)"
  - "Statistics endpoint queries 5 DB tables independently (daily_stats, provider_stats, subtitle_downloads, translation_backend_stats, upgrade_history)"
  - "Log rotation config stored in config_entries (log_max_size_mb, log_backup_count) -- applied on next restart"
  - "Tools blueprint validates all file_path args against media_path using os.path.abspath for path traversal prevention"
  - "All tool operations create .bak backup before modifying files -- non-destructive by default"
  - "ASS timing adjustment uses centisecond precision (H:MM:SS.cc format) with ms-to-cs conversion"

patterns-established:
  - "File validation pattern: _validate_file_path() returns (error, status_code) or (None, abs_path)"
  - "Backup-before-modify pattern: _create_backup() copies original to <name>.bak.<ext>"
  - "ZIP manifest with schema_version for future backward compatibility"

# Metrics
duration: 12min
completed: 2026-02-15
---

# Phase 8 Plan 2: Backend APIs Summary

**ZIP backup/restore with manifest, statistics API with time-range filtering and CSV/JSON export, log management, and subtitle processing tools Blueprint**

## Performance

- **Duration:** 12 min
- **Started:** 2026-02-15T20:05:16Z
- **Completed:** 2026-02-15T20:17:53Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- 12 new API endpoints across system.py (8 endpoints) and tools.py (4 endpoints)
- Full ZIP backup/restore with manifest.json, config.json, and sublarr.db
- Comprehensive statistics with daily/provider/download/backend/upgrade data and time-range filtering
- Statistics export in JSON and CSV formats as downloadable attachments
- Subtitle processing tools: HI removal, timing adjustment (SRT + ASS), common fixes (encoding, whitespace, linebreaks, empty lines), and file preview

## Task Commits

Each task was committed atomically:

1. **Task 1: ZIP backup/restore, statistics, log download/rotation** - `4c02fad` (feat)
2. **Task 2: Subtitle processing tools Blueprint** - `c85c1d6` (feat -- included in parallel 08-01 summary commit due to git lock timing)

## Files Created/Modified
- `backend/routes/system.py` - Added 8 new endpoints: ZIP backup CRUD, statistics + export, log download + rotation config
- `backend/routes/tools.py` - New Blueprint with 4 endpoints: remove-hi, adjust-timing, common-fixes, preview
- `backend/routes/__init__.py` - Registered tools_bp Blueprint

## Decisions Made
- ZIP manifest includes schema_version=1 for future backward compatibility during restore
- Statistics endpoint queries 5 tables independently for comprehensive data without joins
- Log rotation config is stored in config_entries and applied on next restart (no hot-reload of RotatingFileHandler)
- Tool endpoints validate all file paths against media_path for security, preventing arbitrary file access
- All tool modifications create .bak backups before writing changes

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Git index.lock conflict during Task 2 commit caused the tools files to be included in a parallel agent's commit (c85c1d6). All code is properly committed and functional, just the commit boundary is slightly off.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- All backend APIs ready for frontend plans 03 (backup UI), 04 (statistics/admin UI), and 05 (tools UI)
- 12 endpoints verified registered via create_app() URL map check
- All 24 existing unit tests pass (pre-existing integration test failures unchanged)

## Self-Check: PASSED

- FOUND: backend/routes/system.py
- FOUND: backend/routes/tools.py
- FOUND: backend/routes/__init__.py
- FOUND: commit 4c02fad
- FOUND: commit c85c1d6

---
*Phase: 08-i18n-backup-admin-polish*
*Completed: 2026-02-15*
