---
phase: 15-api-key-mgmt-notifications-cleanup
plan: 04
subsystem: ui
tags: [react, typescript, tanstack-query, i18n, settings, api-keys, notifications, templates, quiet-hours]

# Dependency graph
requires:
  - phase: 15-01
    provides: API key management backend endpoints (/api/v1/api-keys)
  - phase: 15-02
    provides: Notification templates, quiet hours, history, filters backend endpoints
provides:
  - ApiKeysTab Settings component for centralized API key management
  - NotificationTemplatesTab with template editor, quiet hours, history, event filters
  - TemplateEditor with variable-aware Jinja2 editing and click-to-insert
  - QuietHoursConfig with time pickers, day-of-week checkboxes, 24h timeline
  - TemplatePreview with debounced live rendering
  - TypeScript types for all API key and notification entities
  - React Query hooks for full CRUD on API keys, templates, quiet hours, history, filters
  - i18n translations (en + de) for apiKeys.* and notifications.templates/quietHours/history/filters
affects: [frontend, settings, onboarding]

# Tech tracking
tech-stack:
  added: []
  patterns: [self-contained tab components with React Query hooks, variable-aware template editor, 24h timeline visualization]

key-files:
  created:
    - frontend/src/pages/Settings/ApiKeysTab.tsx
    - frontend/src/pages/Settings/NotificationTemplatesTab.tsx
    - frontend/src/components/notifications/TemplateEditor.tsx
    - frontend/src/components/notifications/TemplatePreview.tsx
    - frontend/src/components/notifications/QuietHoursConfig.tsx
  modified:
    - frontend/src/lib/types.ts
    - frontend/src/api/client.ts
    - frontend/src/hooks/useApi.ts
    - frontend/src/pages/Settings/index.tsx
    - frontend/src/i18n/locales/en/settings.json
    - frontend/src/i18n/locales/de/settings.json

key-decisions:
  - "NotificationTemplatesTab merges legacy notification toggles + Apprise URLs at top for backward compat"
  - "Old Notifications tab replaced (not kept alongside) -- all notification config in one unified tab"
  - "Notification fields removed from FIELDS array -- NotificationTemplatesTab manages its own config via React Query"
  - "TemplateEditor uses simple regex-based Jinja2 highlighting (not full parser) for lightweight bundle"
  - "TemplatePreview debounces at 500ms to avoid excessive API calls on rapid editing"
  - "QuietHoursConfig includes 24h timeline bar visualization for overnight range support"

patterns-established:
  - "Variable-aware template editor: click-to-insert with cursor position restoration via requestAnimationFrame"
  - "Timeline visualization: CSS absolute positioning with percentage-based width for overnight range rendering"

# Metrics
duration: 10min
completed: 2026-02-20
---

# Phase 15 Plan 04: Frontend Settings Tabs for API Keys and Notification Templates Summary

**ApiKeysTab with centralized key management (masked display, test, export/import, Bazarr migration) and NotificationTemplatesTab with Jinja2 template editor, quiet hours 24h timeline, paginated history, and event filters**

## Performance

- **Duration:** 10 min
- **Started:** 2026-02-20T13:29:48Z
- **Completed:** 2026-02-20T13:39:23Z
- **Tasks:** 2
- **Files modified:** 11

## Accomplishments
- Created ApiKeysTab showing all services with masked key values, status badges, inline edit, test buttons, and Bazarr migration preview modal
- Created NotificationTemplatesTab unifying legacy notification toggles with template CRUD, quiet hours config, notification history with re-send, and advanced event filters
- Built TemplateEditor with event-type-aware variable panel, click-to-insert at cursor, Jinja2 syntax highlighting hints
- Built QuietHoursConfig with time pickers, day-of-week checkboxes, exception events multi-select, and visual 24h timeline bar
- Added 8 TypeScript interfaces and ~30 React Query hooks for full API key and notification management
- Added comprehensive i18n translations in English and German for all new UI sections

## Task Commits

Each task was committed atomically:

1. **Task 1: TypeScript Types, React Query Hooks, and ApiKeysTab** - `9ad8bfb` (feat)
2. **Task 2: Notification Components and NotificationTemplatesTab** - `d73bfb7` (feat)

## Files Created/Modified
- `frontend/src/lib/types.ts` - Added ApiKeyService, BazarrMigrationPreview, NotificationTemplate, NotificationHistoryEntry, QuietHoursConfig, TemplateVariable, NotificationFilter interfaces
- `frontend/src/api/client.ts` - Added API functions for /api-keys and /notifications endpoints (CRUD, test, export/import, Bazarr, templates, quiet hours, history, filters)
- `frontend/src/hooks/useApi.ts` - Added ~30 React Query hooks for API keys and notification management
- `frontend/src/pages/Settings/ApiKeysTab.tsx` - Centralized API key management UI with service cards, masked values, test, export/import, Bazarr migration
- `frontend/src/pages/Settings/NotificationTemplatesTab.tsx` - Unified notification management with toggles, templates, quiet hours, history, and filters sections
- `frontend/src/components/notifications/TemplateEditor.tsx` - Variable-aware template text editor with click-to-insert and Jinja2 highlighting
- `frontend/src/components/notifications/TemplatePreview.tsx` - Live template preview with 500ms debounce in notification card style
- `frontend/src/components/notifications/QuietHoursConfig.tsx` - Quiet hours editor with time pickers, day checkboxes, exception events, 24h timeline
- `frontend/src/pages/Settings/index.tsx` - Added API Keys and Notification Templates tabs, removed old inline Notifications section
- `frontend/src/i18n/locales/en/settings.json` - Added apiKeys.*, notifications.templates/quietHours/history/filters keys
- `frontend/src/i18n/locales/de/settings.json` - Added German translations for all new keys

## Decisions Made
- Merged legacy notification toggles and Apprise URL config into the top of NotificationTemplatesTab for backward compatibility
- Replaced old "Notifications" tab entirely with "Notification Templates" (no parallel tabs)
- Removed notification fields from FIELDS array since NotificationTemplatesTab manages config via its own React Query hooks
- Used simple regex-based Jinja2 highlighting rather than a full parser to keep bundle size small
- TemplatePreview uses 500ms debounce to avoid excessive preview API calls
- QuietHoursConfig renders overnight ranges by splitting into two bars (start-to-midnight and midnight-to-end)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 15 frontend is complete -- API Keys, Notification Templates, and associated components all wired up
- Backend endpoints from 15-01 (API keys) and 15-02 (notifications) required for full functionality
- TypeScript compilation passes with zero errors across all new files

---
*Phase: 15-api-key-mgmt-notifications-cleanup*
*Completed: 2026-02-20*

## Self-Check: PASSED

All 5 created files verified present. Both task commits (9ad8bfb, d73bfb7) found in git log.
