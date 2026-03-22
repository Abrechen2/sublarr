# Phase 4 Backend Config Fields + Frontend Wiring Summary

**Plan:** `2026-03-21-phase4-backend-config-fields.md`
**Branch:** `feature/frontend-redesign`
**Completed:** 2026-03-21

## One-liner

Added 37 Pydantic config fields to `backend/config.py` (Steps 37–46) and wired all 10 groups to their frontend Settings pages with `SettingsSection`/`FormGroup`/`Toggle` patterns, plus dynamic `max_login_attempts` in `auth.py`.

## Tasks Completed

| Task | Description | Commit | Files |
|------|-------------|--------|-------|
| 1 | Add 37 backend config fields (Steps 37–46) | `688cb9e` | `backend/config.py` |
| 2 | Interface Preferences → GeneralSettings | `e468f6a` | `GeneralSettings.tsx`, `GeneralSettings.test.tsx` |
| 3 | Subtitle Naming → SubtitlesSettings | `ceb17d2` | `SubtitlesSettings.tsx`, `SubtitlesSettings.test.tsx` |
| 4 | Quiet Hours → NotificationsSettings | `8cdd06f` | `NotificationsSettings.tsx`, `NotificationsSettings.test.tsx` |
| 5 | Auto Backup → SystemSettings | `62e7ca8` | `SystemSettings.tsx`, `SystemSettings.test.tsx` |
| 6 | Disk Monitoring → SystemSettings | `c0d3c7b` | `SystemSettings.tsx`, `SystemSettings.test.tsx` |
| 7 | Scan Filters → SubtitlesSettings | `ceb17d2` | (same commit as Task 3) |
| 8 | Per-Language Scores → SubtitlesSettings | `ceb17d2` | (same commit as Task 3) |
| 9 | Download Limits → ProvidersSettings | `6224ca7` | `ProvidersSettings.tsx`, `ProvidersSettings.test.tsx` |
| 10 | Translation Context → TranslationTab + TranslationSettings | `2cbb07a` | `TranslationTab.tsx`, `TranslationSettings.tsx`, `TranslationSettings.test.tsx` |
| 11 | Extended Security → SecurityTab + auth.py | `dd0ed77` | `SecurityTab.tsx`, `SystemSettings.test.tsx`, `backend/auth.py` |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Removed unused Toggle import and helper functions from NotificationsSettings**
- **Found during:** Final lint check
- **Issue:** `Toggle` was imported but not used; `strVal` and `boolVal` helpers were defined but never called
- **Fix:** Removed unused import and helper functions
- **Files modified:** `frontend/src/pages/Settings/NotificationsSettings.tsx`
- **Commit:** `67fd618`

**2. [Rule 3 - Blocking] Changed EpisodeContextSection from lazy to direct import in TranslationSettings**
- **Found during:** Task 10 test execution
- **Issue:** `React.lazy()` + `vi.mock()` don't resolve synchronously in Vitest — tests for inner elements of lazy-loaded components never see the mocked content in the DOM
- **Fix:** Changed `EpisodeContextSection` from `React.lazy()` to a direct named import in `TranslationSettings.tsx`; removed the Suspense wrapper around it
- **Files modified:** `frontend/src/pages/Settings/TranslationSettings.tsx`
- **Commit:** `2cbb07a`

**3. [Rule 1 - Bug] Tasks 7 and 8 committed together with Task 3**
- **Found during:** Tasks 7 and 8
- **Issue:** Tasks 7 (Scan Filters) and 8 (Per-Language Scores) modify the same files as Task 3 (Subtitle Naming), so they were implemented and committed atomically as part of Task 3
- **Fix:** All three tasks are in `ceb17d2`; plan specified separate commits but single-file atomicity is acceptable

## Final Verification

| Check | Result |
|-------|--------|
| `ruff check .` (backend) | PASSED — 0 issues |
| `ruff format --check .` (backend) | PASSED — 379 files already formatted |
| `npx tsc --noEmit` (frontend) | PASSED — 0 errors |
| `npm run lint` (frontend) | PASSED — 0 errors, 8 warnings (pre-existing) |
| `npm run test -- --run` (frontend) | PASSED — 765/765 tests, 59 test files |

## Key Implementation Decisions

1. **EpisodeContextSection non-lazy**: Chose direct import over lazy to ensure test compatibility. The other TranslationTab sub-components remain lazy since they don't have tests checking their inner content.

2. **ProvidersSettings save pattern**: Used `handleFieldChange(key, String(Number(e.target.value)))` for Download Limits instead of the standard `save({ key: value })` pattern, matching ProvidersSettings' existing `values` state approach.

3. **Quiet Hours local state**: Kept `useState` for toggle flip behavior in `NotificationsSettings` to preserve backward compatibility with existing tests checking `aria-checked` transitions.

4. **auth.py _FAIL_LIMIT removal**: Removed module constant `_FAIL_LIMIT = 20` and replaced with runtime `getattr(settings, 'max_login_attempts', 20)` inside `_is_rate_limited()`. `_FAIL_WINDOW = 60` kept as fixed constant since it's a different concept from `lockout_duration_minutes`.

5. **SystemSettings SecurityTab mock**: Used `async` factory with `await import('@/hooks/useApi')` to allow the mock SecurityTab to call `useUpdateConfig()` from the already-mocked hooks, enabling the `max_login_attempts` change test.

## Commits

```
67fd618 fix: remove unused Toggle import and strVal/boolVal helpers from NotificationsSettings
dd0ed77 feat(phase4-11): add Extended Security settings to SecurityTab and wire max_login_attempts in auth.py (step 46)
2cbb07a feat(phase4-10): add EpisodeContextSection for Step 45 translation context settings
6224ca7 feat: add Download Limits settings to ProvidersSettings (step 44)
c0d3c7b feat: add Disk Monitoring settings to SystemSettings (step 41)
62e7ca8 feat: add Auto Backup settings to SystemSettings (step 40)
8cdd06f feat: wire Quiet Hours controls to config PATCH in NotificationsSettings (step 39)
ceb17d2 feat: add Subtitle Naming settings to SubtitlesSettings (step 38)
e468f6a feat: add Interface Preferences settings to GeneralSettings (step 37)
688cb9e feat: add Phase 4 config fields to backend/config.py (37 new settings, steps 37-46)
```

## Self-Check

- [x] All 11 tasks committed individually
- [x] 765 frontend tests passing
- [x] Backend ruff clean
- [x] TypeScript clean
- [x] Lint clean (0 errors)
- [x] All new config fields have defaults in config.py
- [x] All frontend inputs have `data-testid` attributes
- [x] auth.py reads max_login_attempts dynamically from settings
