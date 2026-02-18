---
phase: 11-subtitle-editor
plan: 01
subsystem: api, ui
tags: [codemirror, syntax-highlighting, subtitle-editor, flask, pysubs2, tokenizer, ass, srt]

# Dependency graph
requires:
  - phase: 08-i18n-backup-admin-polish
    provides: "tools.py blueprint with preview, HI removal, timing, common fixes, _validate_file_path, _create_backup"
provides:
  - "5 new API endpoints: GET/PUT /tools/content, GET /tools/backup, POST /tools/validate, POST /tools/parse"
  - "ASS StreamLanguage tokenizer for CodeMirror (assLanguage)"
  - "SRT StreamLanguage tokenizer for CodeMirror (srtLanguage)"
  - "Sublarr dark + light editor themes (sublarrTheme, sublarrLightTheme)"
  - "CodeMirror npm dependencies installed"
affects: [11-02, 11-03, 11-04]

# Tech tracking
tech-stack:
  added: ["@uiw/react-codemirror", "@uiw/codemirror-themes", "@codemirror/merge", "react-codemirror-merge", "@codemirror/search", "@codemirror/language", "@codemirror/commands", "@codemirror/state", "@codemirror/view", "@lezer/highlight"]
  patterns: ["StreamLanguage tokenizer for line-oriented formats", "mtime-based optimistic concurrency for file saves", "lazy pysubs2 import in route functions"]

key-files:
  created:
    - "frontend/src/components/editor/lang-ass.ts"
    - "frontend/src/components/editor/lang-srt.ts"
    - "frontend/src/components/editor/editor-theme.ts"
  modified:
    - "backend/routes/tools.py"
    - "frontend/package.json"

key-decisions:
  - "Optimistic concurrency via mtime comparison with 0.01s tolerance (no file locking)"
  - "pysubs2 lazy-imported at function level to match existing tools.py pattern"
  - "classify_styles from ass_utils used for /parse endpoint style classification (dialog vs signs)"
  - "Editor theme uses hardcoded color values (not CSS vars) for reliable CodeMirror rendering"

patterns-established:
  - "StreamLanguage tokenizer: sol() checks for line-start tokens, stream.match() for inline patterns, stream.next() fallback"
  - "createTheme dark/light pair with matching token color palettes"

# Metrics
duration: 5min
completed: 2026-02-18
---

# Phase 11 Plan 01: Editor API & CodeMirror Infrastructure Summary

**5 subtitle editor API endpoints (content CRUD, validation, cue parsing) plus CodeMirror ASS/SRT tokenizers and dark/light themes**

## Performance

- **Duration:** 5 min
- **Started:** 2026-02-18T20:00:45Z
- **Completed:** 2026-02-18T20:05:46Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- 5 new backend endpoints extending tools.py: full content read with encoding detection, save with optimistic concurrency and mandatory backup, backup read for diff view, pysubs2-based validation, and structured cue parsing with ASS style classification
- CodeMirror 6 ecosystem installed (10 packages) with zero version conflicts
- ASS tokenizer classifying section headers, keywords, timestamps, override tags, comments, and line break markers
- SRT tokenizer classifying cue numbers, timestamps, arrows, and HTML formatting tags
- Dark and light editor themes matching Sublarr's teal design system

## Task Commits

Each task was committed atomically:

1. **Task 1: Backend API endpoints for subtitle editor** - `3e5d282` (feat)
2. **Task 2: Install CodeMirror dependencies and create tokenizers + theme** - `a4d37bd` (feat)

## Files Created/Modified
- `backend/routes/tools.py` - Extended with 5 new endpoints: GET/PUT /content, GET /backup, POST /validate, POST /parse
- `frontend/package.json` - Added 10 CodeMirror-related npm dependencies
- `frontend/src/components/editor/lang-ass.ts` - ASS StreamLanguage tokenizer (heading, keyword, comment, number, meta, propertyName, escape)
- `frontend/src/components/editor/lang-srt.ts` - SRT StreamLanguage tokenizer (number, operator, meta)
- `frontend/src/components/editor/editor-theme.ts` - sublarrTheme (dark) + sublarrLightTheme (light) with teal accent colors

## Decisions Made
- Used mtime-based optimistic concurrency (0.01s tolerance) for PUT /content rather than file locking -- simpler and avoids stale lock risk
- pysubs2 imported at function level (lazy) consistent with existing tools.py patterns
- Hardcoded hex colors in editor theme rather than CSS variables for reliable CodeMirror rendering across themes
- Light theme uses darker/saturated variants of the same token color palette for accessibility

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- API endpoints ready for frontend editor components (Plan 02: SubtitleEditor, SubtitlePreview)
- Tokenizers and themes ready for CodeMirror integration
- Cue parsing endpoint ready for timeline component (Plan 03)
- Backup content endpoint ready for diff view component (Plan 03)

## Self-Check: PASSED

- All 5 created/modified files exist on disk
- Both task commits (3e5d282, a4d37bd) found in git log
- Blueprint loads without import errors
- TypeScript compiles with zero errors

---
*Phase: 11-subtitle-editor*
*Completed: 2026-02-18*
