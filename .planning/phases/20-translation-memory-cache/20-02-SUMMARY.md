# Phase 20-02: Translation Memory Cache — Frontend

## Status: COMPLETE

## What was implemented

### Task 1: API client functions (`frontend/src/api/client.ts`)

Added a `// --- Phase 20-02: Translation Memory ---` section at the end of the file with:

- `TranslationMemoryStats` interface (`{ entries: number; cache_size_bytes?: number }`)
- `getTranslationMemoryStats()`: `GET /api/v1/translation-memory/stats` — returns entry count
- `clearTranslationMemoryCache()`: `DELETE /api/v1/translation-memory/cache` — returns `{ cleared, deleted }`

Both routes were confirmed implemented in Phase 20-01 (`backend/routes/translate.py` lines 1294–1358).

### Task 2: React Query hooks (`frontend/src/hooks/useApi.ts`)

Added at the end of the file:

- `useTranslationMemoryStats()`: `useQuery` with key `['translation-memory-stats']`, 30s stale time
- `useClearTranslationMemoryCache()`: `useMutation` wrapping `clearTranslationMemoryCache`; on success invalidates `['translation-memory-stats']`

### Task 3: Translation Memory UI (`frontend/src/pages/Settings/TranslationTab.tsx`)

Added new exported component `TranslationMemorySection` with:

- Enable toggle: reads/writes `translation_memory_enabled` config key via existing `useConfig`/`useUpdateConfig` pattern; defaults to `true`
- Similarity threshold input: number input (0.0–1.0, step 0.05), reads/writes `translation_memory_similarity_threshold`; snaps to 0.05 increments on blur; disabled when memory is off
- Clear cache button: destructive button calling `window.confirm()` before `useClearTranslationMemoryCache`; disabled when cache is empty; shows spinner during mutation
- Stats display: "X cached entries" count shown in header and below the clear button; loaded via `useTranslationMemoryStats`

Imports added: `Database` icon from lucide-react, `Toggle` from shared components, new hooks.

### Wiring (`frontend/src/pages/Settings/index.tsx`)

- Added lazy import: `TranslationMemorySection`
- Rendered between the main Translation settings card and `GlobalGlossaryPanel`

## Verification

`npx tsc --noEmit` produced zero errors.

## Files changed

- `frontend/src/api/client.ts` — added 2 API functions + 1 interface
- `frontend/src/hooks/useApi.ts` — added 2 React Query hooks
- `frontend/src/pages/Settings/TranslationTab.tsx` — added `TranslationMemorySection` component
- `frontend/src/pages/Settings/index.tsx` — added lazy import and render of `TranslationMemorySection`
- `.planning/phases/20-translation-memory-cache/20-02-SUMMARY.md` — this file
