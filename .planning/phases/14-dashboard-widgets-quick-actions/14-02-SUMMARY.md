---
phase: 14-dashboard-widgets-quick-actions
plan: 02
subsystem: ui
tags: [react-hotkeys-hook, keyboard-shortcuts, floating-action-button, quick-actions, i18n, accessibility]

requires:
  - phase: 14-dashboard-widgets-quick-actions
    plan: 01
    provides: Dashboard widget infrastructure and QuickActionsWidget component
  - phase: 12-batch-operations-smart-filter
    provides: useSelectionStore for select-all action handler
  - phase: 08-i18n-backup-admin-polish
    provides: i18n infrastructure (useTranslation, locale JSON files)
provides:
  - QuickActionsFAB floating action button with context-specific actions per route
  - KeyboardShortcutsModal showing all shortcuts grouped by category
  - useKeyboardShortcuts hook for global navigation and help shortcuts
  - quickActionDefinitions with per-route action templates for 5 page contexts
  - Page-specific keyboard shortcuts (Shift+S, Shift+R, Shift+A, etc.)
  - Global navigation shortcuts (g then d/l/w/s/a/h)
  - EN and DE i18n translations for all shortcuts and quick actions
affects: [14-03, future page extensions]

tech-stack:
  added: [react-hotkeys-hook v5]
  patterns: [FAB with context-specific actions per route, useHotkeys for declarative shortcut registration, GlobalShortcuts render-null component pattern]

key-files:
  created:
    - frontend/src/components/quick-actions/quickActionDefinitions.ts
    - frontend/src/components/quick-actions/QuickActionsFAB.tsx
    - frontend/src/components/quick-actions/KeyboardShortcutsModal.tsx
    - frontend/src/hooks/useKeyboardShortcuts.ts
  modified:
    - frontend/src/App.tsx
    - frontend/src/i18n/locales/en/common.json
    - frontend/src/i18n/locales/de/common.json
    - frontend/package.json

key-decisions:
  - "react-hotkeys-hook v5 for declarative keyboard shortcut registration with useHotkeys"
  - "FAB uses useQuickActionHandlers hook mapping action template IDs to handler functions"
  - "GlobalShortcuts is a render-null component inside BrowserRouter for router context access"
  - "Ctrl+K handler preserved in App.tsx as-is -- not re-registered in useKeyboardShortcuts to avoid double-fire"
  - "FAB hides entirely when no actions available for current route"
  - "Page-specific hotkeys registered dynamically based on current route actions"

patterns-established:
  - "QuickActionTemplate: id + labelKey + icon + shortcut display + hotkeyCombo for react-hotkeys-hook"
  - "Route-based action matching: getActionTemplatesForRoute returns readonly action array per pathname"
  - "GLOBAL_SHORTCUTS array for documentation/modal display (not for registration)"
  - "useQuickActionHandlers: Map<string, () => void> pattern for action ID to handler mapping"

duration: 7min
completed: 2026-02-19
---

# Phase 14 Plan 02: Quick-Actions FAB + Keyboard Shortcuts Summary

**Floating action button with context-specific actions per route and global keyboard shortcuts using react-hotkeys-hook, with help modal and full EN/DE i18n**

## Performance

- **Duration:** 7 min
- **Started:** 2026-02-19T19:47:39Z
- **Completed:** 2026-02-19T19:54:45Z
- **Tasks:** 2
- **Files modified:** 8

## Accomplishments
- Installed react-hotkeys-hook and created per-route action definitions for 5 page contexts (Dashboard, Wanted, Library, SeriesDetail, History)
- Built QuickActionsFAB with expandable menu showing icons, labels, and keyboard shortcut badges
- Built KeyboardShortcutsModal grouping shortcuts into Navigation, Global, and Page Actions categories
- Integrated global navigation shortcuts (g then d/l/w/s/a/h) and help shortcut (Shift+/) into App.tsx
- Added complete EN and DE translations for all shortcuts and quick action labels

## Task Commits

Each task was committed atomically:

1. **Task 1: Install react-hotkeys-hook and create action definitions + keyboard shortcuts hook** - `69f7492` (feat)
2. **Task 2: Create FAB component, shortcuts modal, integrate into App.tsx, add i18n** - `1d787ff` (feat)

## Files Created/Modified
- `frontend/src/components/quick-actions/quickActionDefinitions.ts` - Per-route action templates, QuickActionTemplate type, GLOBAL_SHORTCUTS array
- `frontend/src/hooks/useKeyboardShortcuts.ts` - Global navigation and help keyboard shortcuts hook
- `frontend/src/components/quick-actions/QuickActionsFAB.tsx` - Floating action button with context-specific menu and page hotkeys
- `frontend/src/components/quick-actions/KeyboardShortcutsModal.tsx` - Modal listing all keyboard shortcuts by category
- `frontend/src/App.tsx` - Integrated GlobalShortcuts, QuickActionsFAB, and KeyboardShortcutsModal
- `frontend/src/i18n/locales/en/common.json` - Added shortcuts and quick_actions sections (EN)
- `frontend/src/i18n/locales/de/common.json` - Added shortcuts and quick_actions sections (DE)
- `frontend/package.json` - Added react-hotkeys-hook dependency

## Decisions Made
- Used react-hotkeys-hook v5 for declarative keyboard shortcut registration (proven library, TypeScript native)
- Kept existing Ctrl+K handler in App.tsx unchanged to avoid double-fire with GlobalSearchModal
- FAB hides on pages without actions (Logs, Statistics, Settings, etc.) for clean UI
- GlobalShortcuts is a render-null component placed inside BrowserRouter for useNavigate access
- mutateAsync called with explicit `undefined` for optional-parameter mutation hooks (TypeScript strictness)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed TypeScript strict argument errors on mutateAsync calls**
- **Found during:** Task 2 (FAB component verification)
- **Issue:** `mutateAsync()` without arguments fails TypeScript strict mode when mutation function has optional parameter (e.g., `seriesId?: number`)
- **Fix:** Changed to `mutateAsync(undefined)` for all three mutation calls in useQuickActionHandlers
- **Files modified:** frontend/src/components/quick-actions/QuickActionsFAB.tsx
- **Verification:** `npx tsc --noEmit` passes, `npm run build` completes successfully
- **Committed in:** 1d787ff (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Minor TypeScript strictness fix. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Quick-actions system complete and ready for Plan 14-03 (if any)
- Action definitions are extensible: new routes can be added to getActionTemplatesForRoute
- GLOBAL_SHORTCUTS array is extensible for future keyboard shortcuts
- FAB handler map pattern makes it easy to add new action handlers

## Self-Check: PASSED

- All 8 files verified present in commits 69f7492 and 1d787ff
- TypeScript check: `npx tsc --noEmit` passes with 0 errors
- Production build: `npm run build` completes successfully
- Commit 69f7492: 4 files (react-hotkeys-hook + definitions + hook)
- Commit 1d787ff: 5 files (FAB + modal + App.tsx + EN/DE i18n)

---
*Phase: 14-dashboard-widgets-quick-actions*
*Completed: 2026-02-19*
