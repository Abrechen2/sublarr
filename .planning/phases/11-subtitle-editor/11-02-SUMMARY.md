---
phase: 11-subtitle-editor
plan: 02
subsystem: ui
tags: [react, codemirror, typescript, react-query, subtitle-editor, timeline, syntax-highlighting]

# Dependency graph
requires:
  - phase: 11-subtitle-editor
    provides: "Editor API endpoints (content, backup, validate, parse) and CodeMirror tokenizers/themes from Plan 01"
provides:
  - "SubtitlePreview read-only viewer component with syntax highlighting and timeline"
  - "SubtitleTimeline visual cue bar with color-coded style markers and click navigation"
  - "6 TypeScript interfaces for editor API responses"
  - "5 API client functions for editor endpoints"
  - "5 React Query hooks for editor data fetching and mutations"
affects: [11-03, 11-04]

# Tech tracking
tech-stack:
  added: []
  patterns: ["useRef for CodeMirror EditorView access", "EditorView.scrollIntoView for programmatic scroll", "Timeline cue-to-line estimation by format"]

key-files:
  created:
    - "frontend/src/components/editor/SubtitlePreview.tsx"
    - "frontend/src/components/editor/SubtitleTimeline.tsx"
  modified:
    - "frontend/src/lib/types.ts"
    - "frontend/src/api/client.ts"
    - "frontend/src/hooks/useApi.ts"

key-decisions:
  - "SubtitlePreview uses ReactCodeMirrorRef for view access instead of EditorView.updateListener"
  - "Timeline cue-to-line mapping uses format-aware estimation (ASS: header offset + index, SRT: index * 4)"
  - "Timeline label count auto-scales: one label per ~5min, clamped 2-10 labels"
  - "Cue color-coding: teal for dialog, amber for signs/songs -- matches SubtitleTimeline styles prop"

patterns-established:
  - "CodeMirror ref pattern: useRef<ReactCodeMirrorRef> with view?.dispatch for scroll effects"
  - "Timeline formatTime helper: H:MM:SS for >1h, MM:SS otherwise"

# Metrics
duration: 4min
completed: 2026-02-18
---

# Phase 11 Plan 02: SubtitlePreview & SubtitleTimeline Components Summary

**Read-only subtitle viewer with ASS/SRT syntax highlighting, visual cue timeline bar, and typed API layer (6 interfaces, 5 client functions, 5 React Query hooks)**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-18T20:08:49Z
- **Completed:** 2026-02-18T20:12:59Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- SubtitlePreview component rendering full file content with CodeMirror syntax highlighting (ASS or SRT auto-detected)
- SubtitleTimeline component visualizing all cues as positioned blocks on a time axis with style-based color coding
- Click-to-scroll from timeline cue to approximate editor line using format-aware estimation
- Complete typed API layer: 6 interfaces, 5 client functions, 5 React Query hooks with caching and invalidation

## Task Commits

Each task was committed atomically:

1. **Task 1: TypeScript types, API client functions, and React Query hooks** - `4f9e7df` (feat)
2. **Task 2: SubtitlePreview and SubtitleTimeline components** - `4b6eec6` (feat)

## Files Created/Modified
- `frontend/src/lib/types.ts` - Added 6 interfaces: SubtitleContent, SubtitleSaveResult, SubtitleBackup, SubtitleValidation, SubtitleCue, SubtitleParseResult
- `frontend/src/api/client.ts` - Added 5 API functions: getSubtitleContent, saveSubtitleContent, getSubtitleBackup, validateSubtitle, parseSubtitleCues
- `frontend/src/hooks/useApi.ts` - Added 5 hooks: useSubtitleContent, useSubtitleParse, useSubtitleBackup, useSaveSubtitle, useValidateSubtitle
- `frontend/src/components/editor/SubtitlePreview.tsx` - Read-only viewer with CodeMirror, metadata bar, timeline integration, edit/close buttons
- `frontend/src/components/editor/SubtitleTimeline.tsx` - Horizontal cue timeline with color-coded blocks, time ruler, click-to-scroll

## Decisions Made
- Used ReactCodeMirrorRef (from @uiw/react-codemirror) for EditorView access instead of a custom update listener
- Timeline cue-to-line estimation is format-aware: ASS uses header offset (~15% of lines, max 60) + cue index; SRT uses cue index * 4 (number + timestamp + text + blank)
- Timeline auto-scales label count from 2-10 based on total duration (~1 label per 5 minutes)
- Cue color coding uses teal for dialog styles and amber for signs/songs styles (determined from parse endpoint's styles map)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- SubtitlePreview and SubtitleTimeline ready for integration into SubtitleEditor (Plan 03)
- API hooks ready for the full editor component with save/validate mutations
- Backup hook ready for diff view component (Plan 03)
- Components can be used standalone from Wanted, History, and SeriesDetail pages

## Self-Check: PASSED

- All 5 created/modified files exist on disk
- Both task commits (4f9e7df, 4b6eec6) found in git log
- TypeScript compiles with zero errors

---
*Phase: 11-subtitle-editor*
*Completed: 2026-02-18*
