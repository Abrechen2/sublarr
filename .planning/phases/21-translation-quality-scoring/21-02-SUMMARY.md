# Phase 21-02: Translation Quality Scoring — Frontend

**Status:** Complete
**Date:** 2026-02-22

## What was implemented

### Task 1: Types and API (types.ts)
- Added `quality_score?: number` (0-100) to `SubtitleCue` interface
- Added `has_quality_scores?: boolean` to `SubtitleParseResult` interface
- No client.ts changes needed — the `parseSubtitleCues` function already returns `SubtitleParseResult`; the new fields flow through automatically via the existing typed response

### Task 2: Per-line quality in editor and timeline
- **SubtitleTimeline.tsx**: Added `getQualityColor()` helper (green >=75, yellow 50-74, red <50). Each timeline cue block now shows a small colored dot at its bottom edge when a `quality_score` is present and the cue block is wide enough (>=0.8% width). The score is included in the hover `title` tooltip.
- **SubtitlePreview.tsx**: Added a quality summary badge in the metadata bar (e.g. "Q: 73% · 2 low") when `parseData.has_quality_scores` is true. The badge is color-coded using the same green/yellow/red thresholds. Computed from average across all scored cues; also shows low-quality cue count when > 0.

### Task 3: Activity job history quality display (Activity.tsx)
- In the `ExpandedRow` component, after the existing stat chips, added a conditional quality block that renders when `job.stats.avg_quality` is present.
- Shows: colored "Avg quality: X.X%" chip and (if > 0) a red "Low: N lines" chip.
- Uses `Number()` safe-casting to handle `Record<string, unknown>` stats type.

### Task 4: Settings quality controls (TranslationTab.tsx, Settings/index.tsx)
- Added `TranslationQualitySection` component to `TranslationTab.tsx` after `TranslationMemorySection`.
- Controls: Enable toggle (translation_quality_enabled), threshold input (translation_quality_threshold, 0-100, default 50), max retries input (translation_quality_max_retries, 0-5, default 2).
- Help text: "Lines scoring below threshold are retried up to max retries."
- In `Settings/index.tsx`: added lazy import for `TranslationQualitySection` and rendered it between `TranslationMemorySection` and `GlobalGlossaryPanel`.
- Uses existing `useConfig` / `useUpdateConfig` pattern — no new hooks needed.

## Verification
- `npx tsc --noEmit` — zero errors
- All changes are purely additive; no existing editing functionality was altered
