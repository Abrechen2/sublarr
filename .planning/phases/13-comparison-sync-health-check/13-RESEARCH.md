# Phase 13: Comparison + Sync + Health-Check - Research

**Researched:** 2026-02-18
**Domain:** Subtitle comparison/diff, timing synchronization, quality analysis/health-check engine
**Confidence:** HIGH

## Summary

Phase 13 adds three major capabilities to Sublarr: (1) subtitle comparison with side-by-side diff highlighting and multi-version support (up to 4), (2) timing synchronization with offset, speed multiplier, and framerate adjustment, and (3) a health-check engine that detects and auto-fixes common subtitle problems. The phase depends on Phase 11's subtitle editor infrastructure, which provides CodeMirror integration, SubtitleEditorModal, backend tools.py endpoints (content read/write, validation, parsing, backup), and pysubs2 for subtitle parsing.

The codebase already has substantial infrastructure to build upon. The backend `tools.py` already implements `adjust-timing` (offset shift for SRT/ASS), `common-fixes` (encoding, whitespace, linebreaks, empty lines), and `validate` (pysubs2 structure validation). The `SubtitleDiff.tsx` component already implements two-file diff comparison using `react-codemirror-merge`. The `pysubs2` library (v1.7.3, installed) provides `SSAFile.shift()` for time-based and frame-based offsets, `SSAFile.transform_framerate()` for FPS conversion, and `classify_styles()` in `ass_utils.py` for style analysis. Recharts (v3.7.0, installed) is already used across Statistics, Dashboard, and chart components for data visualization. The database uses SQLAlchemy ORM with Alembic migrations (render_as_batch for SQLite).

**Primary recommendation:** Extend the existing `tools.py` backend with new health-check and advanced sync endpoints, build the comparison UI as an enhanced version of the existing `SubtitleDiff` component (multi-panel grid layout), create a new `health_checker.py` backend module for the detection engine, and add quality metrics tables to the database for trend tracking. Use pysubs2 exclusively for all subtitle manipulation (no hand-rolled timestamp parsing beyond what already exists in tools.py).

## Standard Stack

### Core (Already Installed)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `pysubs2` | 1.7.3 | Subtitle parsing, shifting, framerate transform | Already used throughout codebase; provides `shift()`, `transform_framerate()`, `get_text_events()` |
| `react-codemirror-merge` | ^4.25.4 | Two-file diff comparison | Already used in `SubtitleDiff.tsx`; wraps `@codemirror/merge` |
| `@uiw/react-codemirror` | ^4.25.4 | Code editor for subtitle preview | Already used in `SubtitleEditor.tsx` |
| `recharts` | ^3.7.0 | Charts for quality metrics dashboard | Already used in Statistics page and chart components |
| `chardet` | (optional import) | Encoding detection | Already used with ImportError fallback in tools.py |

### Supporting (Already Installed)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `@codemirror/merge` | ^6.12.0 | Underlying merge/diff engine | Used by react-codemirror-merge |
| `@codemirror/state` | ^6.5.4 | Editor state management | Read-only state for comparison panels |
| `lucide-react` | ^0.564.0 | Icons for UI components | Health badges, sync controls, comparison UI |
| `@tanstack/react-query` | ^5.90.21 | Data fetching/caching | API hooks for health data, sync operations |

### No New Dependencies Needed
This phase requires **zero new npm or pip packages**. Everything builds on the existing stack.

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| pysubs2 `shift()` + `transform_framerate()` | Custom regex-based timestamp manipulation | pysubs2 handles edge cases (negative clamp, centisecond precision); existing `adjust-timing` endpoint has custom regex but pysubs2 is safer for advanced operations |
| Multi-panel grid of CodeMirror instances | Single merged diff with 4-way support | CodeMirror 6 merge view only supports 2-way; multi-panel grid with synchronized scrolling is the practical approach for 4 versions |
| Backend-computed diffs | Client-side CodeMirror merge | CodeMirror merge already handles diff computation client-side; backend just needs to serve file content |
| chardet | charset-normalizer | charset-normalizer is faster for large files, but chardet is already used with fallback pattern; not worth switching mid-project |

## Architecture Patterns

### Recommended Project Structure
```
backend/
  health_checker.py              # NEW: Health-check engine (detect + fix)
  routes/tools.py                # EXTEND: New endpoints for health-check, advanced sync, comparison
  db/models/quality.py           # NEW: SubtitleHealthResult, QualityMetrics ORM models
  db/repositories/quality.py     # NEW: Quality data repository
  db/quality.py                  # NEW: Quality data shim module

frontend/src/
  components/
    comparison/
      SubtitleComparison.tsx      # NEW: Multi-file comparison (2-4 panels)
      ComparisonPanel.tsx         # NEW: Single panel with CodeMirror (read-only)
      ComparisonSelector.tsx      # NEW: File picker for versions to compare
    health/
      HealthBadge.tsx             # NEW: Per-file health status badge
      HealthCheckPanel.tsx        # NEW: Health results with fix options
      HealthDashboardWidget.tsx   # NEW: Dashboard widget for quality overview
    sync/
      SyncControls.tsx            # NEW: Offset/speed/framerate controls
      SyncPreview.tsx             # NEW: Before/after timing preview
    charts/
      QualityTrendChart.tsx       # NEW: Score trend line chart
      ProviderSuccessChart.tsx    # NEW: Provider success rate chart
  pages/
    SeriesDetail.tsx              # EXTEND: Add sync UI, health badges, comparison entry
    Dashboard.tsx                 # EXTEND: Add quality metrics widgets
```

### Pattern 1: Health-Check Engine (Backend)
**What:** A detection engine that scans subtitle files for common problems and returns structured results.
**When to use:** File-level analysis, batch health scans, auto-fix operations.
**Example:**
```python
# Source: Custom pattern following existing tools.py structure
class HealthCheck:
    """Individual health check with detection and optional fix."""
    name: str           # e.g., "duplicate_lines"
    severity: str       # "error", "warning", "info"
    description: str
    auto_fixable: bool

class HealthCheckResult:
    """Result of running health checks on a subtitle file."""
    file_path: str
    checks_run: int
    issues_found: list[HealthIssue]
    score: int          # 0-100 quality score
    checked_at: str

class HealthIssue:
    """A specific problem detected in a subtitle file."""
    check_name: str
    severity: str
    message: str
    line_number: int | None
    auto_fixable: bool
    fix_description: str | None

# Checks to implement:
HEALTH_CHECKS = [
    "duplicate_lines",       # Exact duplicate text+timing
    "timing_overlaps",       # Events overlap in time
    "encoding_issues",       # Non-UTF8, BOM presence, mixed encodings
    "missing_styles",        # ASS events reference undefined styles
    "empty_events",          # Events with no text content
    "excessive_duration",    # Single event >10 seconds
    "negative_timing",       # End time before start time
    "zero_duration",         # Start == end
    "line_too_long",         # >80 characters per line
    "missing_newlines",      # ASS without proper \N line breaks
]
```

### Pattern 2: Multi-Panel Comparison (Frontend)
**What:** A grid layout of synchronized read-only CodeMirror instances for comparing 2-4 subtitle versions.
**When to use:** Comparing provider results, original vs translated, different language versions.
**Example:**
```typescript
// Grid layout approach for multi-version comparison
// CodeMirror 6 @codemirror/merge only supports 2-way diff.
// For 4-way: use CSS Grid with individual CodeMirror instances.

interface ComparisonConfig {
  panels: Array<{
    label: string        // "Original", "Provider A", "Translated", etc.
    filePath: string
    content: string
    format: 'ass' | 'srt'
  }>
  syncScroll: boolean     // Scroll all panels together
  highlightDiffs: boolean // Highlight differences between panels
}

// 2-panel: Use existing react-codemirror-merge (SubtitleDiff pattern)
// 3-4 panels: CSS Grid with synchronized scroll via shared scroll handler
```

### Pattern 3: Advanced Sync Operations (Backend using pysubs2)
**What:** Subtitle timing manipulation leveraging pysubs2's built-in methods.
**When to use:** Offset shifts, framerate conversion, speed multiplier.
**Example:**
```python
# Source: pysubs2 API (verified via installed v1.7.3)
import pysubs2

subs = pysubs2.load("subtitle.ass")

# Offset shift (time-based)
subs.shift(ms=500)               # Shift all events +500ms
subs.shift(s=-2.5)               # Shift all events -2.5s
subs.shift(h=0, m=1, s=30)       # Shift +1m30s

# Frame-based shift
subs.shift(frames=10, fps=23.976) # Shift by 10 frames at 23.976fps

# Framerate conversion
subs.transform_framerate(25.0, 23.976)  # Convert 25fps to 23.976fps

# Per-event shift (for selective operations)
for event in subs.events:
    if event.start >= 60000:      # Only shift events after 1 minute
        event.shift(ms=500)

# Speed multiplier (custom, pysubs2 doesn't have built-in)
speed_factor = 1.05  # 5% faster
for event in subs.events:
    event.start = int(event.start / speed_factor)
    event.end = int(event.end / speed_factor)

subs.save("subtitle_synced.ass")
```

### Pattern 4: Quality Metrics Storage
**What:** Database tables to track per-file health scores and per-series quality trends over time.
**When to use:** Dashboard widgets, series detail quality badges, trend analysis.
**Example:**
```python
# New SQLAlchemy model following existing patterns (db/models/quality.py)
class SubtitleHealthResult(db.Model):
    """Cached health check results for subtitle files."""
    __tablename__ = "subtitle_health_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    issues_json: Mapped[str] = mapped_column(Text, default="[]")
    checks_run: Mapped[int] = mapped_column(Integer, default=0)
    checked_at: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        Index("idx_health_results_path", "file_path"),
        Index("idx_health_results_score", "score"),
    )
```

### Anti-Patterns to Avoid
- **Hand-rolling timestamp parsing for sync:** pysubs2's `shift()` and `transform_framerate()` handle all edge cases (negative clamp, centisecond rounding, overflow). The existing regex-based `adjust-timing` in tools.py is fine for simple offsets but pysubs2 is safer for advanced operations.
- **Loading full subtitle content for health checks:** Use pysubs2's parsed model (events, styles) instead of re-parsing raw text. Avoid reading the file multiple times.
- **Client-side subtitle parsing for health checks:** All analysis should happen server-side via pysubs2. The client only receives structured results.
- **Storing health results in memory only:** Persist to database for trend tracking. Recalculate on-demand only for "check now" actions.
- **Synchronized scrolling via DOM manipulation:** Use CodeMirror's built-in scroll syncing API (EditorView.scrollTo) rather than manual DOM scroll events.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Timestamp shifting | Custom regex shifting | `pysubs2.SSAFile.shift()` | Handles h/m/s/ms/frames, negative clamping, per-event or bulk |
| Framerate conversion | Manual ratio calculation | `pysubs2.SSAFile.transform_framerate(in_fps, out_fps)` | Rescales all timestamps correctly, validates FPS values |
| Subtitle parsing | Custom ASS/SRT parsers | `pysubs2.load()` / `pysubs2.SSAFile.from_string()` | Handles all format variants, encoding, edge cases |
| Two-way diff | Custom diff algorithm | `react-codemirror-merge` (`SubtitleDiff.tsx` pattern) | Already working in codebase, handles syntax highlighting |
| Chart rendering | Custom SVG/Canvas | `recharts` (BarChart, LineChart, AreaChart) | Already used in Statistics page with Sublarr theme |
| Encoding detection | Manual BOM/charset | `chardet.detect()` with fallback | Already implemented in tools.py pattern |
| Style classification | Manual ASS style parsing | `classify_styles()` from `ass_utils.py` | Already handles dialog vs signs/songs heuristics |

**Key insight:** The existing codebase already has 80% of the backend primitives needed. The health-check engine is primarily composition of existing tools (pysubs2 parsing + style classification + timing analysis) into a structured detection framework.

## Common Pitfalls

### Pitfall 1: Multi-Panel Scroll Synchronization
**What goes wrong:** Scrolling one comparison panel doesn't scroll others, or scroll positions drift due to different content heights.
**Why it happens:** CodeMirror instances are independent; line heights differ when content varies between files.
**How to avoid:** Use line-number-based sync (scroll to same line number) rather than pixel-based sync. Use `EditorView.requestMeasure()` to coordinate updates. Debounce scroll events to avoid cascading updates.
**Warning signs:** Panels "jump" or oscillate when scrolling.

### Pitfall 2: Health-Check Performance on Large Files
**What goes wrong:** Running all health checks on a large ASS file (10K+ events) takes >5 seconds, blocking the UI.
**Why it happens:** Some checks (like duplicate detection) are O(n^2) if naive, and encoding detection reads the entire file.
**How to avoid:** Run health checks asynchronously (return a job ID, use WebSocket for results). Use set-based duplicate detection (O(n)). Cache health results in database. Implement per-check timeouts.
**Warning signs:** API timeouts on large files, spinner that never completes.

### Pitfall 3: Timing Overlap Detection Edge Cases
**What goes wrong:** Overlaps detected where they are intentional (e.g., karaoke effects, signs overlapping dialog).
**Why it happens:** ASS subtitles commonly have intentional overlaps between different styles (dialog + signs).
**How to avoid:** Only flag overlaps within the same style/layer as errors. Cross-style overlaps should be warnings at most. Use pysubs2's `layer` and `style` fields to distinguish.
**Warning signs:** Excessive false positives on anime fansub ASS files.

### Pitfall 4: Auto-Fix Destroying ASS Formatting
**What goes wrong:** Auto-fixing an issue (e.g., removing duplicates) strips ASS override tags or reorders events.
**Why it happens:** Text-based fixes don't preserve the ASS event structure. Saving back through pysubs2 may normalize formatting.
**How to avoid:** Always operate on pysubs2's parsed model, not raw text. Create backups before any fix (existing `_create_backup()` pattern). Preview the fix result before applying. Preserve original event ordering.
**Warning signs:** Fixed file has different styling than original.

### Pitfall 5: Speed Multiplier Precision Loss
**What goes wrong:** Applying speed multiplier 1.05x, then 1/1.05x doesn't return to original timing.
**Why it happens:** Integer millisecond truncation accumulates rounding errors across many events.
**How to avoid:** Store original timing before speed adjustment. Use `round()` instead of `int()` for timestamp calculation. Always allow "reset to original" from backup.
**Warning signs:** Timestamps drift by 1-2 frames after round-trip operations.

### Pitfall 6: Comparison File Path Security
**What goes wrong:** Comparison endpoint allows reading arbitrary files by providing paths outside media_path.
**Why it happens:** New endpoints skip the existing `_validate_file_path()` security check.
**How to avoid:** Every endpoint that reads file content MUST use the existing `_validate_file_path()` from tools.py. This is already enforced for all current tools endpoints.
**Warning signs:** Any endpoint accepting `file_path` without calling `_validate_file_path()`.

## Code Examples

### Health-Check Detection Functions (Backend)
```python
# Source: Custom patterns using pysubs2 (verified API via installed v1.7.3)

def check_duplicate_lines(subs):
    """Detect exact duplicate events (same text + timing)."""
    issues = []
    seen = set()
    for i, event in enumerate(subs.events):
        if event.is_comment:
            continue
        key = (event.start, event.end, event.text, event.style)
        if key in seen:
            issues.append({
                "check": "duplicate_lines",
                "severity": "warning",
                "message": f"Duplicate event at line {i+1}: '{event.plaintext[:50]}...'",
                "line": i + 1,
                "auto_fixable": True,
                "fix": "Remove duplicate event",
            })
        seen.add(key)
    return issues


def check_timing_overlaps(subs):
    """Detect overlapping events within the same style/layer."""
    issues = []
    # Group events by (style, layer)
    groups = {}
    for i, event in enumerate(subs.events):
        if event.is_comment:
            continue
        key = (event.style, event.layer)
        if key not in groups:
            groups[key] = []
        groups[key].append((i, event))

    for (style, layer), events in groups.items():
        sorted_events = sorted(events, key=lambda x: x[1].start)
        for j in range(1, len(sorted_events)):
            prev_idx, prev = sorted_events[j - 1]
            curr_idx, curr = sorted_events[j]
            if curr.start < prev.end:
                overlap_ms = prev.end - curr.start
                issues.append({
                    "check": "timing_overlaps",
                    "severity": "warning" if overlap_ms < 500 else "error",
                    "message": f"Events {prev_idx+1} and {curr_idx+1} overlap by {overlap_ms}ms (style: {style})",
                    "line": curr_idx + 1,
                    "auto_fixable": True,
                    "fix": f"Trim previous event end to {curr.start}ms",
                })
    return issues


def check_missing_styles(subs):
    """Detect events referencing undefined styles (ASS only)."""
    issues = []
    defined_styles = set(subs.styles.keys())
    for i, event in enumerate(subs.events):
        if event.is_comment:
            continue
        if event.style not in defined_styles:
            issues.append({
                "check": "missing_styles",
                "severity": "error",
                "message": f"Event {i+1} references undefined style '{event.style}'",
                "line": i + 1,
                "auto_fixable": True,
                "fix": f"Change style to 'Default'",
            })
    return issues


def calculate_quality_score(issues):
    """Calculate 0-100 quality score from detected issues."""
    score = 100
    for issue in issues:
        if issue["severity"] == "error":
            score -= 10
        elif issue["severity"] == "warning":
            score -= 3
        elif issue["severity"] == "info":
            score -= 1
    return max(0, score)
```

### Advanced Sync Endpoint (Backend)
```python
# Source: pysubs2 API + existing tools.py patterns

@bp.route("/advanced-sync", methods=["POST"])
def advanced_sync():
    """Apply advanced timing synchronization to a subtitle file."""
    import pysubs2

    data = request.get_json() or {}
    file_path = data.get("file_path", "")
    operation = data.get("operation")  # "offset", "speed", "framerate"

    error, result = _validate_file_path(file_path)
    if error:
        return jsonify({"error": error}), result
    abs_path = result

    # Create backup BEFORE any modification
    _create_backup(abs_path)

    subs = pysubs2.load(abs_path)

    if operation == "offset":
        offset_ms = int(data.get("offset_ms", 0))
        subs.shift(ms=offset_ms)
    elif operation == "speed":
        factor = float(data.get("speed_factor", 1.0))
        for event in subs.events:
            event.start = round(event.start / factor)
            event.end = round(event.end / factor)
    elif operation == "framerate":
        in_fps = float(data.get("in_fps", 25.0))
        out_fps = float(data.get("out_fps", 23.976))
        subs.transform_framerate(in_fps, out_fps)

    subs.save(abs_path)
    return jsonify({"status": "synced", "operation": operation, "events": len(subs.events)})
```

### Multi-Panel Comparison (Frontend)
```typescript
// Source: Extension of existing SubtitleDiff pattern + CodeMirror docs

interface ComparisonPanelProps {
  label: string
  content: string
  format: 'ass' | 'srt'
  onScroll?: (lineNumber: number) => void
}

function ComparisonPanel({ label, content, format, onScroll }: ComparisonPanelProps) {
  const language = format === 'ass' ? assLanguage : srtLanguage
  const extensions = [
    language,
    sublarrTheme,
    EditorView.lineWrapping,
    EditorState.readOnly.of(true),
    // Scroll listener for sync
    EditorView.domEventHandlers({
      scroll: (e, view) => {
        const line = view.state.doc.lineAt(
          view.lineBlockAtHeight(view.scrollDOM.scrollTop).from
        ).number
        onScroll?.(line)
      }
    }),
  ]

  return (
    <div className="flex flex-col h-full border border-slate-700 rounded">
      <div className="px-2 py-1 text-xs font-medium bg-slate-800/60 border-b border-slate-700">
        {label}
      </div>
      <CodeMirror
        value={content}
        extensions={extensions}
        theme={sublarrTheme}
        basicSetup={{ lineNumbers: true, foldGutter: false }}
        className="flex-1 overflow-auto"
      />
    </div>
  )
}

// Grid layout for 2-4 panels
function SubtitleComparison({ panels }: { panels: ComparisonPanelProps[] }) {
  const gridCols = panels.length <= 2 ? 'grid-cols-2' : 'grid-cols-2'
  const gridRows = panels.length <= 2 ? '' : 'grid-rows-2'

  return (
    <div className={`grid ${gridCols} ${gridRows} gap-2 h-full`}>
      {panels.map((panel, i) => (
        <ComparisonPanel key={i} {...panel} />
      ))}
    </div>
  )
}
```

### Quality Metrics Dashboard Widget (Frontend)
```typescript
// Source: Existing recharts pattern from Statistics page + chart components
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'

interface QualityTrend {
  date: string
  avg_score: number
  issues_count: number
}

function QualityTrendChart({ data }: { data: QualityTrend[] }) {
  return (
    <ResponsiveContainer width="100%" height={200}>
      <LineChart data={data} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
        <XAxis dataKey="date" stroke="var(--text-muted)" tick={{ fontSize: 11 }} />
        <YAxis stroke="var(--text-muted)" tick={{ fontSize: 11 }} domain={[0, 100]} />
        <Tooltip
          contentStyle={{
            backgroundColor: 'var(--bg-surface)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-md, 8px)',
            color: 'var(--text-primary)',
            fontSize: 12,
          }}
        />
        <Line type="monotone" dataKey="avg_score" stroke="var(--accent)" strokeWidth={2} dot={false} />
      </LineChart>
    </ResponsiveContainer>
  )
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Regex-based timing shift (`tools.py`) | pysubs2 `shift()` + `transform_framerate()` | Phase 13 migration | Safer, handles all edge cases, less code |
| No quality monitoring | Health-check engine + quality score database | Phase 13 new | Users can see subtitle quality at a glance |
| Only 2-file diff view | Multi-version comparison (2-4 panels) | Phase 13 extension | Compare provider results, translations, originals side-by-side |
| Manual timing fixes | Sync UI with preview (offset/speed/fps) | Phase 13 new | Non-technical users can fix timing without editing raw files |

**Existing infrastructure to leverage (not replace):**
- `tools.py` `adjust-timing` endpoint: Keep for simple offset (already used); add advanced-sync alongside
- `tools.py` `common-fixes` endpoint: Keep as-is; health-check auto-fix calls individual fix functions
- `SubtitleDiff.tsx`: Keep for 2-file backup-vs-current comparison; comparison component is a new use case
- `SubtitleEditorModal`: Keep modal pattern; health-check and comparison can open in similar modals or panels

## Open Questions

1. **Health-check scheduling**
   - What we know: Health checks should run on-demand and store results
   - What's unclear: Should they also run automatically after every download/translation? Or only on demand?
   - Recommendation: Start with on-demand only (button click + batch scan). Add automated scheduling as a follow-up if needed. The existing `wanted_scanner.py` scheduler pattern could be reused.

2. **Quality score aggregation per series**
   - What we know: Individual file scores can be calculated. Series-level needs aggregation.
   - What's unclear: How to aggregate (mean? worst score? weighted by recency?)
   - Recommendation: Use mean of most recent scan for each episode's subtitle. Display both the aggregate and worst-case score. This matches how users think about quality -- "how good are my subs overall" vs "which one is worst."

3. **Comparison file selection UI**
   - What we know: Users need to pick which files to compare. Options include: different language subs for same episode, backup vs current, provider search results before download.
   - What's unclear: Exact UX flow for selecting comparison targets.
   - Recommendation: Start with two entry points: (a) Episode detail row with "Compare" button (auto-selects all language versions of that episode), (b) Manual file picker within the comparison modal. Limit to files under the same series path for security.

4. **Sync preview without saving**
   - What we know: Users want to preview timing changes before applying them.
   - What's unclear: Whether to stream the full adjusted file back or just show a few sample events.
   - Recommendation: Return 5-10 representative events (first, middle, last) with before/after timestamps as a preview. Full file stays server-side until user confirms. This avoids transferring large files for preview.

## Sources

### Primary (HIGH confidence)
- pysubs2 v1.7.3 installed locally -- verified `SSAFile.shift()`, `SSAFile.transform_framerate()`, `SSAEvent` fields via Python introspection
- [pysubs2 API Reference](https://pysubs2.readthedocs.io/en/latest/api-reference.html) -- Official docs for shift/transform methods
- Existing codebase: `backend/routes/tools.py` (8 endpoints), `backend/ass_utils.py` (classify_styles), `frontend/src/components/editor/SubtitleDiff.tsx` (CodeMirror merge)
- Existing codebase: `frontend/src/components/charts/` (Recharts patterns), `frontend/src/pages/Statistics.tsx`
- Existing codebase: `backend/db/models/` (SQLAlchemy ORM patterns), `backend/db/repositories/` (repository pattern)

### Secondary (MEDIUM confidence)
- [CodeMirror merge package](https://github.com/codemirror/merge) -- Confirmed 2-way only; no built-in 4-way support
- [react-codemirror-merge](https://www.npmjs.com/package/react-codemirror-merge) -- Verified same ecosystem as existing codebase
- [charset-normalizer docs](https://charset-normalizer.readthedocs.io/) -- Alternative encoding detection; not switching from chardet

### Tertiary (LOW confidence)
- Multi-panel scroll sync approach -- Based on CodeMirror discussion forums; actual EditorView scroll API behavior needs validation during implementation
- Quality score formula (100 - penalties) -- No industry standard; needs user testing for appropriate severity weights

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- All libraries already installed and in use in the codebase
- Architecture: HIGH -- Extends existing patterns (tools.py, editor components, chart components, db models)
- Health-check engine: HIGH -- pysubs2 API verified locally, detection logic is straightforward
- Sync operations: HIGH -- pysubs2 shift/transform_framerate verified locally with help() output
- Multi-panel comparison: MEDIUM -- 2-way diff is proven (SubtitleDiff.tsx exists), 4-way grid layout is standard CSS but scroll sync needs validation
- Quality metrics: MEDIUM -- Database model pattern is established, aggregation formula needs tuning
- Pitfalls: HIGH -- Based on known subtitle format edge cases and codebase-specific patterns

**Research date:** 2026-02-18
**Valid until:** 2026-03-18 (30 days -- stable domain, no fast-moving dependencies)
