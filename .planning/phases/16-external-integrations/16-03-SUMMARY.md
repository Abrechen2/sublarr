---
phase: 16-external-integrations
plan: 03
subsystem: ui
tags: [react, typescript, tailwind, settings, integrations, bazarr, plex, kodi, health-diagnostics, export, i18n]

# Dependency graph
requires:
  - phase: 16-external-integrations
    provides: "Extended health checks on all service clients, compat_checker, export_manager, integrations API blueprint with 10 endpoints"
provides:
  - "IntegrationsTab component in Settings with 4 sections (Bazarr, Compat, Health, Export)"
  - "TypeScript interfaces for all integration response types"
  - "API client functions and React Query hooks for integration endpoints"
  - "EN and DE i18n translations for all integrations UI text"
affects: [settings-ui, 16-external-integrations]

# Tech tracking
tech-stack:
  added: []
  patterns: ["Collapsible Section component with icon for IntegrationsTab", "Mutation-based manual trigger for query (useExtendedHealthAll with enabled:false + refetch)"]

key-files:
  created:
    - frontend/src/pages/Settings/IntegrationsTab.tsx
  modified:
    - frontend/src/lib/types.ts
    - frontend/src/api/client.ts
    - frontend/src/hooks/useApi.ts
    - frontend/src/pages/Settings/index.tsx
    - frontend/src/i18n/locales/en/settings.json
    - frontend/src/i18n/locales/de/settings.json

key-decisions:
  - "exportIntegrationConfig named differently from existing exportConfig to avoid name collision in client.ts"
  - "useExtendedHealthAll uses enabled:false with manual refetch trigger (Run Diagnostics button)"
  - "Bazarr section links to existing ApiKeysTab for actual import (no duplication of import logic)"
  - "Compat and Health sections default to collapsed (defaultOpen=false) to reduce initial visual load"

patterns-established:
  - "Section component with icon prop for visually categorized collapsible sections"
  - "Browser download trigger pattern: Blob -> URL.createObjectURL -> a.click -> revokeObjectURL"

# Metrics
duration: 7min
completed: 2026-02-20
---

# Phase 16 Plan 03: Frontend IntegrationsTab with Bazarr Migration, Compat Check, Health Diagnostics, and Config Export

**IntegrationsTab in Settings with 4 collapsible sections consuming all Phase 16 backend API endpoints via typed React Query hooks, with EN/DE i18n**

## Performance

- **Duration:** 7 min
- **Started:** 2026-02-20T15:09:09Z
- **Completed:** 2026-02-20T15:16:38Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments
- IntegrationsTab with 4 sections renders in Settings page between Cleanup and Notification Templates
- 6 TypeScript interfaces covering all integration API response shapes
- 6 API client functions and 5 React Query hooks for all integration endpoints
- Full EN and DE i18n translations for all integrations UI text

## Task Commits

Each task was committed atomically:

1. **Task 1: Add TypeScript types, API client functions, and useApi hooks for integrations** - `ad1f00d` (feat)
2. **Task 2: Create IntegrationsTab component and integrate into Settings** - `bcc8a39` (feat)

## Files Created/Modified
- `frontend/src/lib/types.ts` - Added ExtendedHealthCheck, ExtendedHealthAllResponse, BazarrMappingReport, CompatCheckResult, CompatBatchResult, ExportResult interfaces
- `frontend/src/api/client.ts` - Added 6 API functions for integration endpoints (mapping report, compat check, health all, export, export zip)
- `frontend/src/hooks/useApi.ts` - Added 5 hooks: useBazarrMappingReport, useCompatCheck, useExtendedHealthAll, useExportIntegrationConfig, useExportIntegrationConfigZip
- `frontend/src/pages/Settings/IntegrationsTab.tsx` - New component with BazarrMigrationSection, CompatCheckSection, ExtendedHealthSection, ExportConfigSection
- `frontend/src/pages/Settings/index.tsx` - Added Integrations to TABS, TAB_KEYS, rendering conditional
- `frontend/src/i18n/locales/en/settings.json` - Added integrations.* keys (bazarr, compat, health, export)
- `frontend/src/i18n/locales/de/settings.json` - Added German translations for all integrations keys

## Decisions Made
- Named export function `exportIntegrationConfig` (not `exportConfig`) to avoid collision with existing config export function
- useExtendedHealthAll uses `enabled: false` pattern with manual refetch -- diagnostics are expensive and should only run on user request
- Bazarr section provides "Proceed to Import" as a text reference to Settings > API Keys > Bazarr Migration (no logic duplication)
- Only Bazarr section defaults to open; other sections collapsed by default to reduce cognitive load

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Pre-existing TypeScript build error in DiskSpaceWidget.tsx (Recharts Formatter type mismatch from Phase 15) -- not caused by this plan, `tsc --noEmit` passes clean, Vite build succeeds

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 16 (External Integrations) is now fully complete -- all 3 plans executed
- All backend API endpoints (Plan 01 + 02) are consumed by the frontend IntegrationsTab (Plan 03)
- Project roadmap is complete: all 17 phases (0-16) have been fully executed

---
*Phase: 16-external-integrations*
*Completed: 2026-02-20*

## Self-Check: PASSED
