---
phase: 15-api-key-mgmt-notifications-cleanup
verified: 2026-02-20T13:55:02Z
status: human_needed
score: 4/5 must-haves verified
re_verification: false
gaps:
  - truth: "Dashboard includes a disk space analysis widget"
    status: failed
    reason: "DiskSpaceWidget.tsx exists but NOT in widgetRegistry.ts"
    artifacts:
      - path: "frontend/src/components/dashboard/widgets/DiskSpaceWidget.tsx"
        issue: "135 lines with useCleanupStats, never referenced by widgetRegistry.ts"
      - path: "frontend/src/components/dashboard/widgetRegistry.ts"
        issue: "WIDGET_REGISTRY has 8 entries but NO disk-space entry"
    missing:
      - "Add disk-space entry to WIDGET_REGISTRY with id=disk-space, HardDrive icon, lazy import of ./widgets/DiskSpaceWidget"
human_verification:
  - test: "Settings > Cleanup, click Scan for Duplicates, observe progress bar"
    expected: "Progress bar animates; duplicate groups appear after scan"
    why_human: "Background scan progress cannot be verified statically"
  - test: "Settings > API Keys, configure a service key, click Test button"
    expected: "Toast shows success or failure message"
    why_human: "Service connectivity requires live backend"
  - test: "Notification Templates, create template, click a variable from the panel"
    expected: "Variable inserted at cursor position in textarea"
    why_human: "requestAnimationFrame cursor restoration requires interactive testing"
  - test: "Configure quiet hours covering current time, trigger a notification"
    expected: "Notification suppressed; logs show suppressed by quiet hours"
    why_human: "Time-dependent suppression requires runtime verification"
  - test: "Upload Bazarr config.yaml in API Keys > Bazarr Migration without confirming"
    expected: "Preview modal shows config entries, profile count, blacklist count"
    why_human: "File upload and modal interaction require interactive testing"
---

# Phase 15: API Key Management, Notifications, Cleanup Verification Report

**Phase Goal:** Users have centralized key management, customizable notification templates with quiet hours, and tools to deduplicate and clean up subtitle files
**Verified:** 2026-02-20T13:55:02Z
**Status:** gaps_found
**Re-verification:** No - initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | User can view, test, rotate, export/import API keys with masked display | VERIFIED | `backend/routes/api_keys.py` (757 lines): 7 routes with `_mask_value` and `_invalidate_for_service`, ZIP export with config+profiles+glossary. `ApiKeysTab.tsx` (457 lines): renders `key.masked_value`, test/rotate/export/import/Bazarr migration. |
| 2 | Bazarr migration tool imports configuration, language profiles, and blacklist | VERIFIED | `bazarr_migrator.py` (467 lines): YAML/INI auto-detection. `migrate_bazarr_db` reads language_profiles, blacklist, arr settings with per-table try/except. `preview_migration` and `apply_migration` present. Endpoint delegates to all four functions. |
| 3 | User can create notification templates with variables, per-service/event assignment, preview before saving | VERIFIED | `notifications_mgmt.py` (723 lines): Jinja2 syntax validation, EVENT_CATALOG sample data. `TemplateEditor.tsx` (263 lines): click-to-insert with requestAnimationFrame cursor restoration. `TemplatePreview.tsx` (100 lines): 500ms debounced preview. |
| 4 | Quiet hours prevent notifications during configured time windows with exception events | VERIFIED | `NotificationRepository.is_quiet_hours` (line 298): overnight range support, day-of-week, exception bypass. `notifier.py` line 227 calls `is_quiet_hours` before send. `QuietHoursConfig.tsx` (242 lines): time inputs, day toggles, 24h timeline. |
| 5 | Deduplication engine scans by content hash, groups in UI, batch deletion, disk space analysis | PARTIAL | Backend: SHA-256 with CRLF normalization, ThreadPoolExecutor(max_workers=4), two-stage safety guard. `DedupGroupList.tsx` (256 lines): radio/checkbox, `disabled={\!allValid}`. Gap: dashboard `DiskSpaceWidget.tsx` (135 lines) NOT in `widgetRegistry.ts`. |

**Score:** 4/5 truths verified (5th partial - backend + cleanup UI complete, dashboard widget orphaned)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|  
| `backend/routes/api_keys.py` | API key registry, CRUD, test, export/import | VERIFIED | 757 lines, 7 routes, Blueprint at /api/v1/api-keys |
| `backend/bazarr_migrator.py` | Dual-format Bazarr parser | VERIFIED | 467 lines, all four public functions |
| `backend/routes/__init__.py` | Blueprint registration | VERIFIED | All three blueprints registered |
| `backend/db/models/notifications.py` | Three notification ORM models | VERIFIED | 72 lines, all three models |
| `backend/db/repositories/notifications.py` | NotificationRepository | VERIFIED | 352 lines, fallback chain, is_quiet_hours, log_notification |
| `backend/routes/notifications_mgmt.py` | Notifications API Blueprint | VERIFIED | 723 lines, Blueprint at /api/v1/notifications, 15+ endpoints |
| `backend/notifier.py` | Enhanced with Jinja2 and quiet hours | VERIFIED | 348 lines, SandboxedEnvironment, is_quiet_hours, history logging |
| `backend/db/models/cleanup.py` | Three cleanup ORM models | VERIFIED | 64 lines, SubtitleHash, CleanupRule, CleanupHistory |
| `backend/db/repositories/cleanup.py` | CleanupRepository | VERIFIED | 387 lines, upsert_hash, get_duplicate_groups, get_disk_stats |
| `backend/dedup_engine.py` | SHA-256 scan, safe deletion | VERIFIED | 340 lines, SHA-256, ThreadPoolExecutor, two-stage safety guard |
| `backend/routes/cleanup.py` | Cleanup API Blueprint | VERIFIED | 962 lines, Blueprint at /api/v1/cleanup |
| `backend/cleanup_scheduler.py` | Scheduled cleanup runner | VERIFIED | 193 lines, start_cleanup_scheduler wired into app.py |
| `frontend/src/pages/Settings/ApiKeysTab.tsx` | API key management UI (min 150 lines) | VERIFIED | 457 lines, masked values, all actions wired |
| `frontend/src/pages/Settings/NotificationTemplatesTab.tsx` | Templates, quiet hours, history UI (min 200 lines) | VERIFIED | 719 lines, three hooks used |
| `frontend/src/components/notifications/TemplateEditor.tsx` | Variable-aware editor (min 80 lines) | VERIFIED | 263 lines, click-to-insert with cursor restoration |
| `frontend/src/components/notifications/QuietHoursConfig.tsx` | Time range + day checkboxes (min 60 lines) | VERIFIED | 242 lines, time inputs, day toggles, 24h timeline |
| `frontend/src/pages/Settings/CleanupTab.tsx` | Cleanup management tab (min 200 lines) | VERIFIED | 596 lines, 5 collapsible sections |
| `frontend/src/components/cleanup/DedupGroupList.tsx` | Duplicate groups with keep/delete (min 100 lines) | VERIFIED | 256 lines, radio/checkbox, disabled until valid |
| `frontend/src/components/cleanup/DiskSpaceWidget.tsx` | Disk usage visualization (min 60 lines) | VERIFIED | 237 lines, Recharts charts |
| `frontend/src/components/dashboard/widgets/DiskSpaceWidget.tsx` | Dashboard widget (min 30 lines) | ORPHANED | 135 lines with useCleanupStats - NOT in widgetRegistry.ts |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|  
| api_keys.py | db/config.py | get/save_config_entry | WIRED | Lazy imports at lines 95, 310, 546 |
| api_keys.py | clients + notifier | _invalidate_for_service | WIRED | Lines 341-360 |
| routes/__init__.py | api_keys.py | blueprint registration | WIRED | Lines 27, 49 |
| notifier.py | NotificationRepository | quiet hours + template lookup | WIRED | Lines 224-232: is_quiet_hours and find_template_for_event |
| notifier.py | SandboxedEnvironment | template rendering | WIRED | Lines 47-57: singleton _sandbox_env |
| notifications_mgmt.py | NotificationRepository | CRUD | WIRED | Used throughout all endpoints |
| dedup_engine.py | CleanupRepository | store/query hashes | WIRED | Lines 95, 157, 172, 202 |
| routes/cleanup.py | dedup_engine.py | scan and delete | WIRED | Lines 86, 245, 316 |
| cleanup_scheduler.py | dedup_engine.py | scheduled scan | WIRED | Lines 123-144 |
| app.py | cleanup_scheduler.py | startup | WIRED | Lines 359-360: start_cleanup_scheduler(app, socketio) |
| ApiKeysTab.tsx | /api/v1/api-keys | React Query hooks | WIRED | useApiKeys, useUpdateApiKey, useTestApiKey, useExportApiKeys, useBazarrMigration |
| NotificationTemplatesTab.tsx | /api/v1/notifications | React Query hooks | WIRED | useNotificationTemplates, useQuietHours, useNotificationHistory |
| CleanupTab.tsx | /api/v1/cleanup | React Query hooks | WIRED | useCleanupStats, useStartCleanupScan, useDuplicates, useDeleteDuplicates, useCleanupRules |
| Settings/index.tsx | 3 new tabs | import + render | WIRED | Lines 19-21, 25, 41, 662-697 |
| DiskSpaceWidget (dashboard) | /api/v1/cleanup/stats | useCleanupStats | ORPHANED | Component calls hook but widgetRegistry.ts has no disk-space entry |

### Requirements Coverage

| Requirement | Status | Blocking Issue |
|-------------|--------|----------------|
| Centralized API key management with masked display, test, rotate, export/import | SATISFIED | None |
| Bazarr migration with config + language profiles + blacklist import | SATISFIED | None |
| Notification templates with variables, per-service/event assignment, preview | SATISFIED | None |
| Quiet hours with time windows and exception events | SATISFIED | None |
| Deduplication with content hash, UI grouping, batch deletion, disk space analysis | PARTIAL | Dashboard widget not registered in widgetRegistry.ts |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `frontend/src/components/dashboard/widgetRegistry.ts` | N/A | Orphaned component: DiskSpaceWidget in widgets/ folder but not registered | WARNING | Dashboard disk space widget unreachable by users |
| `frontend/src/i18n/locales/en/dashboard.json` | widgets.disk_space | i18n keys exist for unregistered widget | INFO | Translations present but unreachable |

No TODO/FIXME code stubs found in any backend or frontend file. No empty return stubs. All HTML placeholder= attributes are legitimate input hints.

### Human Verification Required

**1. Deduplication Scan Progress UI**
Test: Settings > Cleanup tab, click Scan for Duplicates, observe progress updates.
Expected: Progress bar animates during scan; duplicate groups appear with file paths, sizes, format badges after completion.
Why human: Polling-based progress (2s interval) and background ThreadPoolExecutor cannot be verified statically.

**2. API Key Test Connectivity**
Test: Configure a Sonarr or Radarr API key in Settings > API Keys, click Test button.
Expected: Toast notification shows success or failure with a descriptive message.
Why human: Requires live backend and configured external service.

**3. Template Editor Click-to-Insert Variables**
Test: Settings > Notification Templates, create template, select event type, click a variable from the panel.
Expected: The variable is inserted at the current cursor position in the textarea.
Why human: requestAnimationFrame-based cursor restoration requires interactive DOM testing.

**4. Quiet Hours Suppression**
Test: Configure quiet hours covering current time, trigger a notification.
Expected: Notification suppressed; backend log shows Notification suppressed by quiet hours.
Why human: Time-dependent behavior requires runtime verification.

**5. Bazarr Migration Upload and Preview**
Test: Upload a Bazarr config.yaml in Settings > API Keys > Bazarr Migration without confirming.
Expected: Preview modal shows config entries, profile count, blacklist count before import.
Why human: File upload interaction and preview modal rendering require interactive testing.

### Gaps Summary

One gap blocks full goal achievement: the dashboard disk space widget is orphaned.

The DiskSpaceDashboardWidget component at `frontend/src/components/dashboard/widgets/DiskSpaceWidget.tsx` (135 lines) is fully implemented with `useCleanupStats()`, Recharts donut chart, total files/duplicates/savings display. The i18n translations for `widgets.disk_space` were correctly added to `dashboard.json`. However, the component was never added to `frontend/src/components/dashboard/widgetRegistry.ts`. The WIDGET_REGISTRY array contains 8 entries (stat-cards, quick-actions, service-status, provider-health, quality, translation-stats, wanted-summary, recent-activity) but no `disk-space` entry.

Fix required: Add `HardDrive` to the lucide-react import in `widgetRegistry.ts`, then add to WIDGET_REGISTRY:

    {
      id: 'disk-space',
      titleKey: 'widgets.disk_space',
      icon: HardDrive,
      defaultLayout: { w: 4, h: 3, x: 0, y: 13, minW: 3, minH: 2 },
      component: lazy(() => import('./widgets/DiskSpaceWidget')),
    },

All other phase goals are fully achieved: centralized API key management with masked display and cache invalidation, Bazarr YAML/INI dual-format migration, notification templates with Jinja2 SandboxedEnvironment and quiet hours, and the deduplication engine with SHA-256 content hashing and keep-at-least-one safety guard are all complete and wired end-to-end.

---

_Verified: 2026-02-20T13:55:02Z_
_Verifier: Claude (gsd-verifier)_
