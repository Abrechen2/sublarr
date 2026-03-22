# Phase 5 & 6 — Missing UI Features (Steps 47–66) Summary

**Plan:** `2026-03-21-phase5-6-missing-ui-features.md`
**Branch:** `feature/frontend-redesign`
**Completed:** 2026-03-21

## One-liner

Wired 20 missing backend routes to frontend UI surfaces including export/import, provider health, Whisper transcription, OP/ED detection, remux UI, webhook viewer, batch translate, and cache management.

## Completed Steps

| Step | Description | Commit |
|------|-------------|--------|
| 47 | Settings export/import UI (ConfigExportImportTab) | 35e4d8b |
| 48 | Ollama model pull UI in TranslationSettings | 54be3dc |
| 49 | Notification history section | 51390cc |
| 50 | Hook Manager page (CRUD, test, logs) | 4935e0b |
| 51 | Format convert tool in subtitle editor toolbar | 0c97462 |
| 52 | Season batch search button in SeriesDetail | b67acdf |
| 53 | Update check banner on Dashboard | a63af58 |
| 54 | Provider health/circuit breaker status in ProvidersSettings | 797caba |
| 55+61 | ffprobe cache stats + DB vacuum UI (CacheTab in SystemSettings) | 7371bfd |
| 56+57 | Batch translate button + data-testids in Wanted toolbar | 1c41afa |
| 58 | Already complete (pre-existing) | — |
| 59 | Already complete (pre-existing) | — |
| 60 | Already complete (pre-existing) | — |
| 62+63 | Whisper transcription + OP/ED detection buttons in episode detail | 69cfc47 |
| 64 | Already complete (pre-existing) | — |
| 65 | Incoming webhooks URL viewer page | bf10857 |
| 66 | Remux track removal hook + data-testid in TrackPanel | 6731cb0 |

## Test Coverage

All 799 frontend tests pass. New tests added:
- `ConfigExportImportTab.test.tsx`
- `TranslationTab.ollama.test.tsx`
- `NotificationHistoryTab.test.tsx`
- `HooksPage.test.tsx`
- `SubtitleEditorModal.convert.test.tsx`
- `SeasonGroup.transcribe.test.tsx`
- `WebhooksPage.test.tsx`
- `TrackPanel.remux.test.tsx`
- `Wanted.toolbar.test.tsx`

## Deviations from Plan

### Pre-existing implementations (steps marked as already complete)

**Steps 58, 59, 60, 64:** Verified already complete via grep before implementation.

### Combined steps

**Steps 55+61 (Cache):** DB vacuum (61) combined with ffprobe cache (55) into single `CacheTab.tsx` component — one commit, cleaner architecture.

**Steps 56+57 (Wanted toolbar):** Implemented in a single commit since they touch the same file and test.

**Steps 62+63 (Episode buttons):** Implemented in a single commit (Transcribe + OP/ED detect use the same pattern, same component).

### Auto-fixed issues (Rule 1-3)

**[Rule 2 - Missing] toast not imported in useSystemApi.ts**
- Discovered when adding `useFfprobeCleanup` and `useDbVacuum`
- Fix: Added `import { toast } from '@/components/shared/Toast'`

**[Rule 1 - Bug] HooksPage unused imports**
- `lazy` and `Toggle` imported but never used — lint errors
- Fix: Removed unused imports

**[Rule 1 - Bug] Section count tests outdated**
- `NotificationsSettings.test` expected 3 sections; now 4 after adding History section
- `SystemSettings.test` expected 11 sections; now 13 after adding Cache + Export/Import
- Fix: Updated expected counts

### Architecture note (Step 62/63)

Transcribe/OP-ED buttons placed in `SeasonGroup.tsx` using local hooks rather than prop-drilling through SeriesDetailPage → SeasonGroup. This minimized changes to the protected SeriesDetailPage component while achieving the required `data-testid` attributes.

### Step 66 (Remux)

`TrackPanel.tsx` already had full remux remove + confirm + restore backup UI implemented. Only needed to add `data-testid="remux-remove-track-{index}"` to the existing button.

## Files Created

- `frontend/src/pages/Settings/ConfigExportImportTab.tsx`
- `frontend/src/pages/Settings/NotificationHistoryTab.tsx`
- `frontend/src/pages/Settings/HooksPage.tsx`
- `frontend/src/pages/Settings/CacheTab.tsx`
- `frontend/src/pages/Settings/WebhooksPage.tsx`
- `frontend/src/pages/__tests__/Wanted.toolbar.test.tsx`
- `frontend/src/components/series/__tests__/SeasonGroup.transcribe.test.tsx`
- `frontend/src/components/tracks/__tests__/TrackPanel.remux.test.tsx`
- `frontend/src/pages/Settings/__tests__/WebhooksPage.test.tsx`
- `frontend/src/pages/Settings/__tests__/ConfigExportImportTab.test.tsx`
- `frontend/src/pages/Settings/__tests__/TranslationTab.ollama.test.tsx`
- `frontend/src/pages/Settings/__tests__/NotificationHistoryTab.test.tsx`
- `frontend/src/pages/Settings/__tests__/HooksPage.test.tsx`
- `frontend/src/components/editor/__tests__/SubtitleEditorModal.convert.test.tsx`

## Files Modified

- `frontend/src/pages/Settings/SystemSettings.tsx` (added sections 12-13)
- `frontend/src/pages/Settings/NotificationsSettings.tsx` (added section 3)
- `frontend/src/pages/Settings/TranslationTab.tsx` (added OllamaPullSection)
- `frontend/src/pages/Settings/ProvidersTab.tsx` (added health status display)
- `frontend/src/pages/Settings/index.tsx` (added hooks + webhooks routes)
- `frontend/src/pages/SeriesDetail.tsx` (added season batch search button)
- `frontend/src/pages/Dashboard.tsx` (added update banner)
- `frontend/src/pages/Wanted.tsx` (added batch translate button + testids)
- `frontend/src/components/editor/SubtitleEditorModal.tsx` (added format convert UI)
- `frontend/src/components/series/SeasonGroup.tsx` (added transcribe + detect buttons)
- `frontend/src/components/tracks/TrackPanel.tsx` (added data-testid to remux button)
- `frontend/src/hooks/useSystemApi.ts` (added ffprobe/vacuum hooks + toast import)
- `frontend/src/hooks/useTranslationApi.ts` (added 4 new hooks)
- `frontend/src/hooks/useProvidersApi.ts` (added useProviderHealth)
- `frontend/src/hooks/useLibraryApi.ts` (added useRemoveTrackFromContainer)
- `frontend/src/api/client.ts` (added 5 new API functions)

## Self-Check

All commits verified present in git log. All 799 tests passing. TypeScript: no errors. ESLint: 0 errors (8 pre-existing warnings).
