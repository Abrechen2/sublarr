# Phase 11: Subtitle Editor - Research

**Researched:** 2026-02-18
**Domain:** Browser-based code editor, subtitle format parsing, diff views
**Confidence:** HIGH

## Summary

Phase 11 adds a subtitle preview and editor to Sublarr so users can view, edit, and compare ASS/SRT subtitle files directly in the browser. The codebase already has substantial infrastructure to build upon: a backend `tools.py` with file validation, preview (first 100 lines), backup creation, HI removal, timing adjustment, and common fixes; a `previewSubtitle` API client function; and `pysubs2` for backend ASS/SRT parsing. The frontend stack is React 19 + TypeScript + Tailwind v4 + TanStack Query.

The editor component should use `@uiw/react-codemirror` (v4.25.x), the most popular React wrapper for CodeMirror 6. For diff views, `react-codemirror-merge` (same ecosystem) wraps `@codemirror/merge`. ASS/SRT syntax highlighting should be implemented as a lightweight `StreamLanguage` tokenizer -- no need for a full Lezer grammar since these are line-oriented formats with well-defined section headers, timestamps, and override tags. The backend already has the security model (path validation under `media_path`, `.bak` backup creation) that the editor API endpoints will extend.

**Primary recommendation:** Use `@uiw/react-codemirror` for the editor, write custom `StreamLanguage` tokenizers for ASS and SRT syntax highlighting, extend the existing `/api/v1/tools/` backend routes with full-file-read and save endpoints, and integrate the editor as a modal/panel component accessible from SeriesDetail, Wanted, and History pages.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `@uiw/react-codemirror` | ^4.25.4 | React wrapper for CodeMirror 6 | 486 dependents, HIGH reputation, handles React lifecycle, controlled state, onChange |
| `@codemirror/merge` | ^6.7.x | Unified diff view extension | Official CodeMirror package for comparing document versions |
| `react-codemirror-merge` | ^4.23.x | React wrapper for @codemirror/merge | Same uiwjs ecosystem, provides `<Original>` and `<Modified>` components |
| `@codemirror/search` | ^6.5.x | Find and replace panel | Official CodeMirror package, built-in search/replace UI |
| `@codemirror/language` | ^6.x | StreamLanguage, syntax highlighting | Required for custom ASS/SRT tokenizers |
| `@codemirror/commands` | ^6.x | History (undo/redo), keymaps | Core editing commands |
| `@uiw/codemirror-themes` | ^4.x | Theme creation utilities | Dark theme matching Sublarr's teal *arr-style |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `@codemirror/state` | ^6.x | EditorState, extensions | Peer dependency of react-codemirror |
| `@codemirror/view` | ^6.x | EditorView, decorations | Peer dependency, also for custom decorations (timeline markers) |
| `@lezer/highlight` | ^1.x | Highlight tag definitions | Needed for StreamLanguage tokenizer tags |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `@uiw/react-codemirror` | Raw CodeMirror 6 + useRef | More control but must manage React lifecycle manually; wrapper handles 95% of cases |
| `StreamLanguage` tokenizer | Full Lezer grammar | Lezer is overkill for line-oriented subtitle formats; StreamLanguage is simpler and sufficient |
| `react-codemirror-merge` | Custom `unifiedMergeView` via extension | Wrapper handles React concerns; raw extension requires manual view management |
| Client-side parsing only | `pysubs2` on backend | Backend already has pysubs2; use it for validation and structured data, client for display |

**Installation:**
```bash
cd frontend && npm install @uiw/react-codemirror @uiw/codemirror-themes @codemirror/merge react-codemirror-merge @codemirror/search @codemirror/language @codemirror/commands @codemirror/state @codemirror/view @lezer/highlight
```

Note: Some of these may already be peer dependencies of `@uiw/react-codemirror`. Check after install.

## Architecture Patterns

### Recommended Component Structure
```
frontend/src/
├── components/
│   └── editor/
│       ├── SubtitlePreview.tsx     # Read-only preview with syntax highlighting + timeline
│       ├── SubtitleEditor.tsx      # Full editor (CodeMirror) with undo/redo, validation
│       ├── SubtitleDiff.tsx        # Side-by-side or unified diff view
│       ├── SubtitleTimeline.tsx    # Visual timeline bar (cue markers on time axis)
│       ├── lang-ass.ts            # StreamLanguage tokenizer for ASS format
│       ├── lang-srt.ts            # StreamLanguage tokenizer for SRT format
│       └── editor-theme.ts        # Dark theme matching Sublarr's design system
├── hooks/
│   └── useApi.ts                  # Add: useSubtitleContent, useSaveSubtitle, useSubtitleBackup
└── pages/
    ├── SeriesDetail.tsx           # Add preview/edit button per episode subtitle
    ├── Wanted.tsx                 # Add preview button per wanted item
    └── History.tsx                # Add preview + diff button per history entry
```

### Backend Extension
```
backend/
└── routes/
    └── tools.py                   # Extend with:
        # GET /tools/content        — Full file content (not just 100 lines)
        # PUT /tools/content        — Save edited content (with backup)
        # GET /tools/backup         — Read .bak file for diff
        # POST /tools/validate      — Validate ASS/SRT structure (via pysubs2)
```

### Pattern 1: Modal Editor with Lazy Loading
**What:** The editor is a modal/drawer that opens over the current page, lazy-loaded to avoid bundling CodeMirror on every page.
**When to use:** Always -- CodeMirror is ~200KB+ gzipped, should not be in the main bundle.
**Example:**
```typescript
// SubtitleEditorModal.tsx -- lazy loaded
const SubtitleEditor = lazy(() => import('@/components/editor/SubtitleEditor'));

function SubtitleEditorModal({ filePath, onClose }: Props) {
  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center">
      <div className="w-[90vw] h-[85vh] rounded-lg overflow-hidden"
           style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
        <Suspense fallback={<Loader2 className="animate-spin" />}>
          <SubtitleEditor filePath={filePath} onClose={onClose} />
        </Suspense>
      </div>
    </div>
  );
}
```

### Pattern 2: StreamLanguage Tokenizer for ASS
**What:** A CM6 StreamLanguage-based tokenizer that colorizes ASS section headers, style definitions, dialogue lines, timestamps, and override tags.
**When to use:** For both read-only preview and full editor.
**Example:**
```typescript
// lang-ass.ts
import { StreamLanguage, StringStream } from '@codemirror/language';
import { tags as t } from '@lezer/highlight';

const assLanguage = StreamLanguage.define({
  token(stream: StringStream): string | null {
    // Section headers: [Script Info], [V4+ Styles], [Events]
    if (stream.match(/^\[.+\]$/)) return 'heading';
    // Key: Value metadata lines
    if (stream.match(/^[A-Za-z ]+:/)) return 'keyword';
    // Dialogue line prefix
    if (stream.match(/^Dialogue:\s*/)) {
      return 'keyword';
    }
    // Comment lines
    if (stream.match(/^Comment:\s*/)) return 'comment';
    // Override tags {...}
    if (stream.match(/\{[^}]*\}/)) return 'meta';
    // Timestamps H:MM:SS.CC
    if (stream.match(/\d:\d{2}:\d{2}\.\d{2}/)) return 'number';
    // Format line
    if (stream.match(/^Format:\s*/)) return 'keyword';
    // Style line
    if (stream.match(/^Style:\s*/)) return 'keyword';
    // Consume one char if nothing matched
    stream.next();
    return null;
  },
});
```

### Pattern 3: Backend Content API with Security
**What:** Extend existing `tools.py` with endpoints that read/write full file content, reusing the existing `_validate_file_path` and `_create_backup` functions.
**When to use:** For all editor save operations and full content loading.
**Example:**
```python
# In routes/tools.py
@bp.route("/content", methods=["GET"])
def get_file_content():
    """Read full subtitle file content for editing."""
    file_path = request.args.get("file_path", "")
    error, result = _validate_file_path(file_path)
    if error:
        return jsonify({"error": error}), result
    abs_path = result
    # Detect encoding
    detected_encoding = "utf-8"
    try:
        import chardet
        with open(abs_path, "rb") as f:
            raw = f.read()
        det = chardet.detect(raw)
        detected_encoding = det.get("encoding", "utf-8") or "utf-8"
    except ImportError:
        pass
    with open(abs_path, "r", encoding=detected_encoding, errors="replace") as f:
        content = f.read()
    ext = os.path.splitext(abs_path)[1].lower()
    fmt = "ass" if ext in (".ass", ".ssa") else "srt"
    return jsonify({
        "format": fmt,
        "content": content,
        "encoding": detected_encoding,
        "size_bytes": os.path.getsize(abs_path),
    })

@bp.route("/content", methods=["PUT"])
def save_file_content():
    """Save edited subtitle content (creates backup first)."""
    data = request.get_json() or {}
    file_path = data.get("file_path", "")
    content = data.get("content", "")
    error, result = _validate_file_path(file_path)
    if error:
        return jsonify({"error": error}), result
    abs_path = result
    # Always create backup before saving
    bak_path = _create_backup(abs_path)
    with open(abs_path, "w", encoding="utf-8") as f:
        f.write(content)
    return jsonify({
        "status": "saved",
        "backup_path": bak_path,
    })
```

### Pattern 4: Diff View with Backup Content
**What:** When opening diff view, load both the current file and its `.bak` version for comparison.
**When to use:** After editing, or when user wants to compare current vs original.
**Example:**
```typescript
// SubtitleDiff.tsx
import CodeMirrorMerge from 'react-codemirror-merge';
const Original = CodeMirrorMerge.Original;
const Modified = CodeMirrorMerge.Modified;

function SubtitleDiff({ originalContent, modifiedContent, language }) {
  return (
    <CodeMirrorMerge>
      <Original value={originalContent} extensions={[language]} />
      <Modified value={modifiedContent} extensions={[language]} />
    </CodeMirrorMerge>
  );
}
```

### Anti-Patterns to Avoid
- **Parsing ASS/SRT entirely on the client:** The backend already has `pysubs2` and mature parsing. Use the backend for validation, use client-side tokenizers only for highlighting.
- **Loading full editor on every page:** CodeMirror is large. Always lazy-load the editor modal/drawer.
- **Saving without backup:** The existing `_create_backup()` must ALWAYS be called before writes. This is a project safety rule (CLAUDE.md: "KEINE Medien-Dateien loeschen/ueberschreiben").
- **Direct file paths from frontend:** All file paths are validated server-side against `media_path`. Never trust client input.
- **Storing file content in global state:** Subtitle files can be large. Load on demand, discard on close.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Code editing | Custom textarea + key handlers | `@uiw/react-codemirror` | Undo/redo stacks, selection, keymaps, accessibility are deceptively complex |
| Find & Replace | Custom search UI | `@codemirror/search` extension | Regex support, match highlighting, replace-all, keyboard shortcuts |
| Diff view | Custom line-by-line diff | `@codemirror/merge` + `react-codemirror-merge` | Proper diff algorithm, side-by-side + unified views, change highlighting |
| Syntax highlighting | Manual regex + spans | `StreamLanguage` from `@codemirror/language` | Incremental parsing, efficient updates, proper token classification |
| Undo/Redo | Custom history stack | `@codemirror/commands` `history()` | Handles selection changes, grouped edits, memory management |
| File path security | Frontend-only validation | Backend `_validate_file_path()` | Path traversal attacks, symlink exploits; always validate server-side |
| Backup creation | Frontend file copy | Backend `_create_backup()` | Atomic file operations, proper permissions, server-side filesystem |

**Key insight:** CodeMirror 6 is a professional-grade editor framework. Its extension system handles all the hard problems (incremental parsing, efficient DOM updates, accessibility, mobile support, bidirectional text). The only custom work needed is the ASS/SRT tokenizers and the Sublarr-specific theme.

## Common Pitfalls

### Pitfall 1: CodeMirror Bundle Size
**What goes wrong:** Adding CodeMirror to the main bundle increases initial load by 200KB+.
**Why it happens:** Importing CodeMirror components at the top level of pages that don't always need them.
**How to avoid:** Use `React.lazy()` + `Suspense` for the editor component. Only import CodeMirror in the editor module, not in SeriesDetail/Wanted/History pages directly.
**Warning signs:** Vite build output shows increased chunk sizes; initial page load slows.

### Pitfall 2: Controlled vs Uncontrolled Editor State
**What goes wrong:** Setting `value` prop on every render causes cursor position to reset or content to flicker.
**Why it happens:** React re-renders cause CodeMirror state to reset when value is treated as a controlled prop.
**How to avoid:** Use `@uiw/react-codemirror`'s `onChange` callback to track changes, and only set `value` as the initial value. Use the `onUpdate` callback for fine-grained state tracking. Avoid re-setting value from parent state on every keystroke.
**Warning signs:** Cursor jumps to start, content flickers during typing.

### Pitfall 3: Large File Performance
**What goes wrong:** Loading a 10,000+ line ASS file (e.g., full anime season) makes the editor unresponsive.
**Why it happens:** CodeMirror is efficient, but the DOM still has limits. Very large files combined with complex syntax highlighting can cause lag.
**How to avoid:** For the preview component (read-only), limit to a reasonable number of lines and add "load more" pagination. For the editor, consider warning users about very large files. The backend preview endpoint already limits to 100 lines; the full content endpoint should include `total_lines` and `size_bytes` in the response so the UI can warn.
**Warning signs:** Editor lag, browser tab memory exceeding 500MB.

### Pitfall 4: Encoding Detection Inconsistency
**What goes wrong:** File displays garbled characters because encoding was detected differently on read vs write.
**Why it happens:** ASS files from different fansub groups use various encodings (UTF-8, UTF-8 BOM, Shift_JIS, Windows-1252). Detection is heuristic.
**How to avoid:** The backend already uses `chardet` for detection. Always read with detected encoding and always write as UTF-8 (the tools.py pattern). Include detected encoding in the API response so the UI can display it. Store encoding in the save request if the user wants to preserve it.
**Warning signs:** Non-ASCII characters (Japanese, German umlauts) display as replacement characters.

### Pitfall 5: Race Condition on Save
**What goes wrong:** User edits a file that is simultaneously being translated or downloaded by the backend.
**Why it happens:** Wanted search or translation pipeline writes to the same file path.
**How to avoid:** On save, check if the file has been modified since it was loaded (compare mtime or a hash). If modified, show a conflict dialog. Include `last_modified` timestamp in the read response and send it back with the save request for server-side comparison.
**Warning signs:** Editor saves overwrite a translation that just completed.

### Pitfall 6: Backup File Accumulation
**What goes wrong:** Each edit creates a new `.bak` file, but only one `.bak` is kept (overwritten). Users lose intermediate backups.
**Why it happens:** The existing `_create_backup` always writes to the same `.bak{ext}` path.
**How to avoid:** For the editor specifically, consider timestamped backups or a simple version history in the database. Alternatively, document that only the most recent backup is kept, which is the current tools.py behavior.
**Warning signs:** Users expect multi-level undo across sessions but only have one backup.

## Code Examples

### ASS StreamLanguage Tokenizer (Complete)
```typescript
// Source: Based on CodeMirror StreamLanguage docs + ASS format spec
// frontend/src/components/editor/lang-ass.ts

import { StreamLanguage } from '@codemirror/language';

export const assLanguage = StreamLanguage.define({
  token(stream) {
    // Skip leading whitespace
    if (stream.eatSpace()) return null;

    // Section headers: [Script Info], [V4+ Styles], [Events]
    if (stream.sol() && stream.match(/^\[.*\]\s*$/)) return 'heading';

    // Comment lines (semicolons at start of line in Script Info)
    if (stream.sol() && stream.peek() === ';') {
      stream.skipToEnd();
      return 'comment';
    }

    // Event type keywords at start of line
    if (stream.sol() && stream.match(/^(Dialogue|Comment|Format|Style):\s*/)) {
      return 'keyword';
    }

    // Metadata key: value at start of line
    if (stream.sol() && stream.match(/^[A-Za-z][A-Za-z0-9 ]*:/)) {
      return 'propertyName';
    }

    // Override tags: {...}
    if (stream.match(/\{[^}]*\}/)) return 'meta';

    // ASS timestamps: H:MM:SS.CC
    if (stream.match(/\d:\d{2}:\d{2}\.\d{2}/)) return 'number';

    // ASS line break markers
    if (stream.match(/\\[Nn]/)) return 'escape';

    // Consume one character
    stream.next();
    return null;
  },
  languageData: {
    commentTokens: { line: ';' },
  },
});
```

### SRT StreamLanguage Tokenizer (Complete)
```typescript
// frontend/src/components/editor/lang-srt.ts

import { StreamLanguage } from '@codemirror/language';

export const srtLanguage = StreamLanguage.define({
  token(stream) {
    if (stream.eatSpace()) return null;

    // Cue number (digits only on a line by itself)
    if (stream.sol() && stream.match(/^\d+\s*$/)) return 'number';

    // SRT timestamps: 00:00:00,000 --> 00:00:00,000
    if (stream.match(/\d{2}:\d{2}:\d{2},\d{3}/)) return 'number';
    if (stream.match(/-->/)) return 'operator';

    // HTML-style tags: <i>, </i>, <b>, <font color="...">
    if (stream.match(/<\/?[a-z][^>]*>/i)) return 'meta';

    // Consume one character
    stream.next();
    return null;
  },
});
```

### Custom Dark Theme for Sublarr
```typescript
// frontend/src/components/editor/editor-theme.ts

import { createTheme } from '@uiw/codemirror-themes';
import { tags as t } from '@lezer/highlight';

export const sublarrTheme = createTheme({
  theme: 'dark',
  settings: {
    background: 'var(--bg-surface)',         // Matches Sublarr surface
    foreground: 'var(--text-primary)',
    caret: 'var(--accent)',                  // Teal caret
    selection: 'rgba(29, 184, 212, 0.2)',    // Teal selection
    selectionMatch: 'rgba(29, 184, 212, 0.1)',
    lineHighlight: 'rgba(255, 255, 255, 0.04)',
    gutterBackground: 'var(--bg-elevated)',
    gutterForeground: 'var(--text-muted)',
  },
  styles: [
    { tag: t.heading, color: '#22d3ee', fontWeight: 'bold' },   // Section headers
    { tag: t.keyword, color: '#a78bfa' },                       // Dialogue/Format/Style
    { tag: t.comment, color: '#6b7280', fontStyle: 'italic' },
    { tag: t.number, color: '#34d399' },                        // Timestamps
    { tag: t.meta, color: '#f59e0b' },                          // Override tags / HTML tags
    { tag: t.propertyName, color: '#60a5fa' },                  // Metadata keys
    { tag: t.escape, color: '#fb923c' },                        // \N line breaks
    { tag: t.operator, color: '#94a3b8' },                      // --> arrow
  ],
});
```

### Timeline Component (Visual Cue Markers)
```typescript
// Simplified timeline: horizontal bar with markers at each cue's start time
interface TimelineCue {
  start: number;  // seconds
  end: number;    // seconds
  style?: string; // ASS style name for color-coding
}

function SubtitleTimeline({ cues, totalDuration, onCueClick }: {
  cues: TimelineCue[];
  totalDuration: number;
  onCueClick: (index: number) => void;
}) {
  return (
    <div className="relative h-6 rounded overflow-hidden"
         style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border)' }}>
      {cues.map((cue, i) => {
        const left = (cue.start / totalDuration) * 100;
        const width = Math.max(((cue.end - cue.start) / totalDuration) * 100, 0.2);
        return (
          <div
            key={i}
            className="absolute top-0 h-full cursor-pointer opacity-70 hover:opacity-100"
            style={{
              left: `${left}%`,
              width: `${width}%`,
              backgroundColor: 'var(--accent)',
            }}
            onClick={() => onCueClick(i)}
            title={`${formatTime(cue.start)} - ${formatTime(cue.end)}`}
          />
        );
      })}
    </div>
  );
}
```

## Existing Codebase Assets

The following already exist and should be reused/extended, NOT reimplemented:

### Backend (routes/tools.py)
| Existing | What It Does | How Editor Uses It |
|----------|--------------|--------------------|
| `_validate_file_path()` | Checks path exists, is subtitle, under media_path | Reuse for all new endpoints |
| `_create_backup()` | Creates `.bak{ext}` copy | Call before every save operation |
| `GET /tools/preview` | Returns first 100 lines + encoding | Extend or add new `/tools/content` for full file |
| `POST /tools/remove-hi` | Removes HI markers with backup | Can be triggered from editor toolbar |
| `POST /tools/adjust-timing` | Shifts timestamps | Can be triggered from editor toolbar |
| `POST /tools/common-fixes` | Encoding, whitespace, linebreak fixes | Can be triggered from editor toolbar |

### Backend (ass_utils.py)
| Existing | What It Does | How Editor Uses It |
|----------|--------------|--------------------|
| `classify_styles()` | Classifies dialog vs signs/songs | Show style classification in preview |
| `extract_tags()` / `restore_tags()` | Handle ASS override tags | Backend validation of edited content |
| `run_ffprobe()` | Get subtitle stream info | Already used by SeriesDetail to detect subs |

### Backend (pysubs2)
| Existing | What It Does | How Editor Uses It |
|----------|--------------|--------------------|
| `pysubs2.load()` | Parse ASS/SRT into structured data | Validate edited file structure |
| `pysubs2.SSAFile` | Object model for subtitles | Extract cue data for timeline component |

### Frontend
| Existing | What It Does | How Editor Uses It |
|----------|--------------|--------------------|
| `previewSubtitle()` API client | Calls `GET /tools/preview` | Basis for preview component |
| `usePreviewSubtitle()` hook | TanStack Query mutation | Extend with content + save hooks |
| `runSubtitleTool()` API client | Calls `POST /tools/{tool}` | Trigger HI removal, timing, fixes from editor |
| `SubtitleToolsTab` in Settings | UI for tools | Reference for tool invocation patterns |
| `EpisodeInfo.file_path` type | Episode file path | Derive subtitle path for preview/edit |
| `EpisodeInfo.subtitles` | `Record<string, string>` (lang -> format) | Determine which subtitle files exist |

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| CodeMirror 5 `mode` system | CodeMirror 6 `StreamLanguage` / Lezer | 2022 | CM5 modes still work via `@codemirror/legacy-modes`, but new tokenizers should use CM6 `StreamLanguage` |
| `@codemirror/merge` v0.x | `@codemirror/merge` ^6.7 | 2024 | Added `unifiedMergeView`, `allowInlineDiffs`, `collapseUnchanged` options |
| Separate diff libraries (diff-match-patch) | `@codemirror/merge` built-in | 2023+ | No need for external diff libraries; CM merge handles diffing internally |
| `react-codemirror2` (CM5 wrapper) | `@uiw/react-codemirror` (CM6 wrapper) | 2022 | The CM5 wrapper is effectively abandoned; `@uiw/react-codemirror` is the standard React CM6 wrapper |

**Deprecated/outdated:**
- `react-codemirror2`: CM5-based, unmaintained for CM6
- `codemirror` v5.x npm package: Legacy; CM6 is the current version
- `defineSimpleMode` (CM5): Replaced by `StreamLanguage.define()` in CM6

## Open Questions

1. **Timeline data source**
   - What we know: ASS files have timing data per dialogue line. `pysubs2` can parse this into structured `{start, end, text, style}` data.
   - What's unclear: Should the timeline data come from a separate backend endpoint (parsed by pysubs2) or be parsed client-side from the raw file content?
   - Recommendation: Add a `/tools/parse` endpoint that returns structured cue data from pysubs2. This avoids duplicating ASS/SRT parsing logic in TypeScript and leverages the existing backend dependency.

2. **Concurrent edit protection**
   - What we know: The translation pipeline and wanted search can write subtitle files. The editor could open a file that gets overwritten.
   - What's unclear: Should we implement file locking, or is optimistic concurrency (mtime comparison) sufficient?
   - Recommendation: Start with optimistic concurrency (include `last_modified` in read response, compare on save). File locking adds complexity and risk of stale locks. Show a conflict warning if the file changed since load.

3. **Backup strategy for editor edits**
   - What we know: Current `_create_backup()` overwrites the single `.bak` file each time.
   - What's unclear: Should the editor maintain more backup history than the existing tools?
   - Recommendation: Keep the same single-backup behavior for consistency with existing tools. The CodeMirror undo/redo handles in-session history. If users need versioning, that's a separate feature (Phase N+1).

4. **Preview vs Editor integration in pages**
   - What we know: Preview should be accessible from Wanted, History, SeriesDetail. Editor from SeriesDetail and History.
   - What's unclear: Should the preview open as an inline expansion (like the existing search/history panels in SeriesDetail), a modal, or a new page?
   - Recommendation: Use a modal/drawer for both preview and editor. Inline expansion would be too cramped for a code editor. A modal provides sufficient space and can be dismissed without navigation. Lazy-load the CodeMirror bundle when the modal opens.

## Sources

### Primary (HIGH confidence)
- Context7: `/uiwjs/react-codemirror` -- React CodeMirror setup, basicSetup options, custom themes, extensions
- Context7: `/websites/codemirror_net` -- CodeMirror 6 official docs: StreamLanguage, history, syntaxHighlighting, unifiedMergeView
- Codebase: `backend/routes/tools.py` -- Existing preview, validation, backup infrastructure
- Codebase: `backend/ass_utils.py` -- ASS parsing, style classification, tag handling
- Codebase: `backend/requirements.txt` -- pysubs2==1.7.3 already a dependency
- Codebase: `frontend/package.json` -- React 19, TypeScript ~5.9.3, Tailwind v4, TanStack Query ^5.x
- Codebase: `frontend/src/api/client.ts` -- Existing `previewSubtitle()`, `runSubtitleTool()`
- Codebase: `frontend/src/hooks/useApi.ts` -- Existing `usePreviewSubtitle()`, `useSubtitleTool()`

### Secondary (MEDIUM confidence)
- npm: `@uiw/react-codemirror@4.25.4` -- Latest stable version, 486 dependents
- npm: `@codemirror/merge` -- Official CodeMirror merge/diff package
- npm: `react-codemirror-merge` -- React wrapper for @codemirror/merge
- [CodeMirror Language Package Example](https://codemirror.net/examples/lang-package/) -- Official guide for custom language modes
- [StreamLanguage discussion](https://discuss.codemirror.net/t/how-to-create-custom-syntax-highlighter-using-stream-parser/3752)

### Tertiary (LOW confidence)
- ASS format specification is informally documented across multiple fan sites; no single authoritative spec exists. The [tcax.org spec](http://www.tcax.org/docs/ass-specs.htm) is commonly referenced but may be incomplete for newer Aegisub extensions.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- `@uiw/react-codemirror` is the dominant React CM6 wrapper; verified via Context7 and npm
- Architecture: HIGH -- Pattern follows existing codebase conventions (modals, lazy loading, Blueprint routes, TanStack Query hooks)
- Pitfalls: HIGH -- Based on existing codebase patterns (encoding detection, backup creation, file validation) and common CodeMirror integration issues
- ASS/SRT tokenizers: MEDIUM -- StreamLanguage approach verified via official docs, but the specific tokenizer implementations are untested code examples
- Diff view: MEDIUM -- `react-codemirror-merge` is real and maintained, but the specific integration with backup files is an architectural proposal

**Research date:** 2026-02-18
**Valid until:** 2026-04-18 (90 days -- CodeMirror ecosystem is stable, not fast-moving)
