---
phase: 08-i18n-backup-admin-polish
plan: 01
subsystem: ui
tags: [tailwind, css-variables, dark-mode, light-mode, theme, i18next, react-i18next, i18n, localization]

# Dependency graph
requires:
  - phase: 07-events-hooks-custom-scoring
    provides: "Complete frontend with sidebar, pages, and CSS variable design system"
provides:
  - "Dark/light/system theme toggle with CSS variable swap and flash prevention"
  - "i18next infrastructure with en/de common namespace and static JSON imports"
  - "ThemeToggle and LanguageSwitcher components in sidebar footer"
  - "useTheme hook with localStorage persistence and system preference listener"
affects: [08-02, 08-03, 08-04, 08-05]

# Tech tracking
tech-stack:
  added: [i18next, react-i18next, i18next-browser-languagedetector]
  patterns: [CSS custom-variant dark, theme toggle with localStorage, i18n static JSON imports]

key-files:
  created:
    - frontend/src/hooks/useTheme.ts
    - frontend/src/components/shared/ThemeToggle.tsx
    - frontend/src/components/shared/LanguageSwitcher.tsx
    - frontend/src/i18n/index.ts
    - frontend/src/i18n/locales/en/common.json
    - frontend/src/i18n/locales/de/common.json
  modified:
    - frontend/src/index.css
    - frontend/index.html
    - frontend/src/main.tsx
    - frontend/src/components/layout/Sidebar.tsx
    - frontend/package.json

key-decisions:
  - "Default theme is dark (preserves current appearance, no visual regression)"
  - "Theme stored in localStorage as 'sublarr-theme', language as 'sublarr-language'"
  - "Inline script in index.html prevents flash of wrong theme before React hydration"
  - "i18n uses static JSON imports (no HTTP backend) since only 2 languages"
  - "LanguageSwitcher shows target language label (DE when en active, EN when de active)"
  - "System theme mode listens to prefers-color-scheme media query changes"

patterns-established:
  - "Theme variables: light in :root, dark in .dark class, toggled via classList"
  - "i18n namespace convention: common for shared, page-specific namespaces added later"
  - "Sidebar footer controls: compact 28px buttons with hover accent color"

# Metrics
duration: 10min
completed: 2026-02-15
---

# Phase 8 Plan 01: Theme + i18n Foundation Summary

**Dark/light/system theme toggle with CSS custom-variant directive, react-i18next with en/de common namespace via static JSON imports, and sidebar footer controls**

## Performance

- **Duration:** 10 min
- **Started:** 2026-02-15T20:05:00Z
- **Completed:** 2026-02-15T20:14:39Z
- **Tasks:** 2
- **Files modified:** 11

## Accomplishments
- CSS variable architecture split: light theme values in :root, all current dark values preserved in .dark class
- Tailwind v4 @custom-variant dark directive enables dark: prefix utilities
- useTheme hook manages dark/light/system with localStorage persistence and OS preference listener
- ThemeToggle component cycles through 3 modes with Moon/Sun/Monitor icons
- Inline script in index.html prevents flash-of-wrong-theme on page load
- i18next initialized with static en/de common.json imports and browser language detection
- LanguageSwitcher toggles between English and German with auto-persist to localStorage
- Both controls integrated into sidebar footer above health status indicator

## Task Commits

Each task was committed atomically:

1. **Task 1: Theme system** - `f7789d5` (feat)
2. **Task 2: i18n infrastructure** - `9ca2d8c` (feat)

## Files Created/Modified
- `frontend/src/index.css` - Split CSS variables: light in :root, dark in .dark, added @custom-variant
- `frontend/index.html` - Inline theme script preventing flash of wrong theme
- `frontend/src/hooks/useTheme.ts` - Theme state management hook (dark/light/system)
- `frontend/src/components/shared/ThemeToggle.tsx` - 3-state theme cycle button
- `frontend/src/components/shared/LanguageSwitcher.tsx` - EN/DE language toggle button
- `frontend/src/i18n/index.ts` - i18next initialization with static JSON and language detector
- `frontend/src/i18n/locales/en/common.json` - English translations (nav, status, actions, theme, time, confirm)
- `frontend/src/i18n/locales/de/common.json` - German translations matching all en keys
- `frontend/src/main.tsx` - Added i18n side-effect import before App render
- `frontend/src/components/layout/Sidebar.tsx` - Integrated ThemeToggle and LanguageSwitcher in footer
- `frontend/package.json` - Added i18next, react-i18next, i18next-browser-languagedetector

## Decisions Made
- Default theme is 'dark' (no stored preference = dark theme, matching current appearance)
- Theme uses 3-state cycle (dark -> light -> system) rather than simple toggle
- System mode removes localStorage entry and follows OS preference with live listener
- i18n language detection order: localStorage first, then browser navigator
- LanguageSwitcher shows the OTHER language as button text (DE when en, EN when de) for intuitive switching
- Common namespace covers shared UI: nav, status, actions, theme, language, app, pagination, time, confirm
- Page-specific namespaces declared but empty (i18next falls back to key strings gracefully)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Theme system ready for all pages to auto-adapt via CSS variable swap
- i18n infrastructure ready for Plan 04 to wrap sidebar strings in t() calls
- Later plans can add page-specific namespace JSONs (dashboard.json, settings.json, etc.)
- LanguageSwitcher and ThemeToggle in sidebar footer, visible on all pages

## Self-Check: PASSED

All 11 files verified present. Both commit hashes (f7789d5, 9ca2d8c) confirmed in git log.

---
*Phase: 08-i18n-backup-admin-polish*
*Completed: 2026-02-15*
