---
phase: 08-i18n-backup-admin-polish
plan: 05
subsystem: ui
tags: [i18n, react-i18next, useTranslation, translation-json, en, de, activity, queue, history, blacklist, onboarding, statusbadge, statistics]

# Dependency graph
requires:
  - phase: 08-i18n-backup-admin-polish
    provides: "i18n infrastructure (react-i18next, common namespace, LanguageSwitcher) and core page translations (dashboard, settings, library, logs, statistics)"
provides:
  - "EN/DE translation JSON files for activity and onboarding namespaces (137 keys)"
  - "useTranslation hooks wrapping Activity, Queue, History, Blacklist, Onboarding, StatusBadge, Statistics"
  - "Complete i18n coverage across the entire frontend -- all pages fully internationalized"
affects: [future-language-additions, community-translations]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Shared activity namespace for related pages (Activity/Queue/History/Blacklist use activity.json with subsections)"
    - "StatusBadge status translation map: API status string -> common:status.* key lookup"
    - "Onboarding titleKey/descKey pattern for static step definitions resolved at render time"

key-files:
  created:
    - "frontend/src/i18n/locales/en/activity.json"
    - "frontend/src/i18n/locales/de/activity.json"
    - "frontend/src/i18n/locales/en/onboarding.json"
    - "frontend/src/i18n/locales/de/onboarding.json"
  modified:
    - "frontend/src/i18n/index.ts"
    - "frontend/src/pages/Activity.tsx"
    - "frontend/src/pages/Queue.tsx"
    - "frontend/src/pages/History.tsx"
    - "frontend/src/pages/Blacklist.tsx"
    - "frontend/src/pages/Onboarding.tsx"
    - "frontend/src/pages/Statistics.tsx"
    - "frontend/src/components/shared/StatusBadge.tsx"
    - "frontend/src/i18n/locales/en/common.json"
    - "frontend/src/i18n/locales/de/common.json"
    - "frontend/src/i18n/locales/en/statistics.json"
    - "frontend/src/i18n/locales/de/statistics.json"

key-decisions:
  - "Activity namespace shared across Activity, Queue, History, Blacklist (related activity pages with subsections)"
  - "StatusBadge uses translation map from API status strings to common:status.* keys (12 statuses mapped)"
  - "SubtitleTypeBadge also wrapped with useTranslation for 'Forced' label"
  - "Onboarding ALL_STEPS uses titleKey/descKey pattern (static const outside component, resolved at render)"
  - "Toast.tsx skipped -- no built-in text labels, only renders dynamic messages from callers"
  - "Statistics.tsx auto-wrapped (created by 08-03, translation JSON existed from 08-04 but component not wrapped)"
  - "Added 7 missing status keys to common.json (wanted, searching, found, ignored, not_configured, skipped, forced)"

patterns-established:
  - "Activity namespace pattern: shared namespace with subsections (queue.*, history.*, blacklist.*)"
  - "StatusBadge translation map: statusTranslationKeys Record mapping API values to i18n keys"
  - "Onboarding key reference pattern: static step definitions use titleKey/descKey resolved via t() at render"

# Metrics
duration: 16min
completed: 2026-02-15
---

# Phase 8 Plan 05: Remaining Pages i18n Summary

**EN/DE translation coverage for Activity, Queue, History, Blacklist, Onboarding, StatusBadge, and Statistics -- completing 100% frontend internationalization**

## Performance

- **Duration:** 16 min
- **Started:** 2026-02-15T21:07:36Z
- **Completed:** 2026-02-15T21:24:17Z
- **Tasks:** 2
- **Files modified:** 16 (4 created, 12 modified)

## Accomplishments
- Created 4 translation JSON files (2 EN, 2 DE) with 137 total translation keys covering all remaining pages
- Wrapped 7 components with useTranslation hooks: Activity, Queue, History, Blacklist, Onboarding, StatusBadge, Statistics
- StatusBadge now translates all 12 status values via a mapping from API strings to common:status.* keys
- Onboarding wizard fully internationalized including all 8 step titles/descriptions, field labels, navigation, and toast messages
- Added 7 missing status keys to common.json for complete StatusBadge coverage
- All page titles, table headers, empty states, action buttons, filter labels, and confirmation dialogs now use t() calls

## Task Commits

Each task was committed atomically:

1. **Task 1: Create EN/DE JSON files for activity and onboarding namespaces** - `4ecb762` (feat)
2. **Task 2: Wrap Activity, Queue, History, Blacklist, Onboarding, StatusBadge, Statistics with useTranslation** - `1fd9d76` (feat)

## Files Created/Modified
- `frontend/src/i18n/locales/en/activity.json` - English translations for Activity/Queue/History/Blacklist (72 keys)
- `frontend/src/i18n/locales/de/activity.json` - German translations for Activity/Queue/History/Blacklist (72 keys)
- `frontend/src/i18n/locales/en/onboarding.json` - English translations for Onboarding wizard (65 keys)
- `frontend/src/i18n/locales/de/onboarding.json` - German translations for Onboarding wizard (65 keys)
- `frontend/src/i18n/index.ts` - Added static imports for 4 new JSON files (activity + onboarding, EN + DE)
- `frontend/src/pages/Activity.tsx` - useTranslation('activity'), table headers, filters, expanded row, pagination, retry toasts
- `frontend/src/pages/Queue.tsx` - useTranslation('activity'), batch status labels, section headers, empty states
- `frontend/src/pages/History.tsx` - useTranslation('activity'), summary cards, table headers, filter labels, blacklist actions
- `frontend/src/pages/Blacklist.tsx` - useTranslation('activity'), title, subtitle, table headers, confirm dialog, empty state
- `frontend/src/pages/Onboarding.tsx` - useTranslation('onboarding'), all step titles/descriptions, field labels, navigation, toasts
- `frontend/src/pages/Statistics.tsx` - useTranslation('statistics'), chart titles, export labels, empty state
- `frontend/src/components/shared/StatusBadge.tsx` - useTranslation('common'), status translation map for 12 statuses
- `frontend/src/i18n/locales/en/common.json` - Added 7 status keys (wanted, searching, found, ignored, not_configured, skipped, forced)
- `frontend/src/i18n/locales/de/common.json` - Added 7 German status keys
- `frontend/src/i18n/locales/en/statistics.json` - Added exported/export_failed keys
- `frontend/src/i18n/locales/de/statistics.json` - Added German exported/export_failed keys

## Decisions Made
- **Shared activity namespace:** Activity, Queue, History, and Blacklist are all "activity" group pages, sharing the activity namespace with subsections (queue.*, history.*, blacklist.*)
- **StatusBadge translation map:** Uses a Record<string, string> mapping API status values to translation keys, falling back to raw status string for unknown values
- **SubtitleTypeBadge wrapped:** Also received useTranslation for the "Forced" label
- **Toast.tsx skipped:** Toast component renders only dynamic messages passed by callers -- no built-in text labels to translate
- **Onboarding titleKey/descKey:** Static ALL_STEPS array uses key references instead of literal strings, resolved at render time via t()

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Statistics.tsx not wrapped with useTranslation**
- **Found during:** Task 2 (final sweep for hardcoded strings)
- **Issue:** Statistics.tsx was created by plan 08-03 (parallel execution) and its translation JSON files were created by 08-04, but the component itself was never wrapped with useTranslation
- **Fix:** Added useTranslation('statistics') and replaced all hardcoded strings (title, chart headings, export labels, empty state, toast messages)
- **Files modified:** frontend/src/pages/Statistics.tsx, frontend/src/i18n/locales/en/statistics.json, frontend/src/i18n/locales/de/statistics.json
- **Verification:** TypeScript check and build pass, all strings use t() calls
- **Committed in:** `1fd9d76` (Task 2 commit)

**2. [Rule 2 - Missing Critical] Common.json missing status keys for StatusBadge**
- **Found during:** Task 2 (wrapping StatusBadge with translations)
- **Issue:** StatusBadge renders 12 different statuses but common.json only had 10 status keys (missing wanted, searching, found, ignored, not_configured, skipped, forced)
- **Fix:** Added 7 missing status keys to both en/common.json and de/common.json
- **Files modified:** frontend/src/i18n/locales/en/common.json, frontend/src/i18n/locales/de/common.json
- **Verification:** All 12 StatusBadge statuses + forced now have translation entries in both languages
- **Committed in:** `1fd9d76` (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (2 missing critical)
**Impact on plan:** Both fixes essential for complete i18n coverage. Statistics.tsx was a gap from parallel plan execution. Common.json additions were required for StatusBadge translation to work correctly. No scope creep.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- All frontend pages are now fully internationalized between English and German
- i18n system uses 7 namespaces: common, dashboard, settings, library, activity, logs, statistics, onboarding
- Total translation keys: ~500+ across all JSON files (EN and DE)
- Adding a new language requires only creating new locale JSON files and registering in index.ts
- Phase 8 i18n objectives (I18N-01, I18N-02, I18N-03) are fully achieved
- Some residual hardcoded strings exist in Settings.tsx sub-components (from 08-04 scope) -- mostly technical terms and field labels in complex sub-components

---
*Phase: 08-i18n-backup-admin-polish*
*Completed: 2026-02-15*

## Self-Check: PASSED
