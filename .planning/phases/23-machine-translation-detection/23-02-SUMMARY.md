# Phase 23-02 — Machine Translation Detection Frontend

**Status:** Complete  
**Date:** 2026-02-22

## What Was Implemented

### 1. Type Extension — `frontend/src/api/client.ts`

Extended `InteractiveSearchResult` interface with two optional fields:
```typescript
machine_translated?: boolean
mt_confidence?: number  // 0-100
```
These are backward-compatible (optional) and align with the backend fields added in Phase 23-01.

### 2. MT Badge — `frontend/src/components/wanted/InteractiveSearchModal.tsx`

Added an orange MT badge to the Flags column of the interactive search results table. Badge logic:
- Shows when `machine_translated === true` OR `mt_confidence > 0`
- Badge text: `"MT 85%"` when confidence is available, plain `"MT"` when only boolean flag
- Color: `text-orange-400 bg-orange-400/10` (warning orange, distinct from HI amber and Forced blue)
- Tooltip: `"Likely machine-translated"`
- Placed before the HI and Forced flags in the same flex container

### 3. MT Settings — `frontend/src/pages/Settings/EventsTab.tsx` (ScoringTab)

Added `MtDetectionSection` component at the bottom of the **Scoring** tab (Providers group), consistent with the scoring/penalty theme.

Config keys saved via `updateConfig`:
- `providers.mt_penalty`: Integer -50 to 0 (default -30; 0 = disabled)
- `providers.mt_confidence_threshold`: Integer 0-100 (default 50)

UI:
- Two labeled number inputs with min/max validation
- Inline help text explaining each field
- Dedicated Save button (does not trigger the global settings save)
- Reads current values from `useConfig()` on first render

## Files Changed

| File | Change |
|------|--------|
| `frontend/src/api/client.ts` | Added `machine_translated?` and `mt_confidence?` to `InteractiveSearchResult` |
| `frontend/src/components/wanted/InteractiveSearchModal.tsx` | MT badge in flags column of search results table |
| `frontend/src/pages/Settings/EventsTab.tsx` | `MtDetectionSection` component added; `useConfig`/`useUpdateConfig` imports added |

## Verification

TypeScript compile: `npx tsc --noEmit` — passed with zero errors.
