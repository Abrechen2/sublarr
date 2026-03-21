# Series Detail — Mockup Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild `SeriesDetailPage` so it visually and functionally matches the approved `concept-drilldown.html` mockup exactly.

**Architecture:** The page is decomposed into four independent surfaces: (1) Hero with meta tags + 3 action buttons, (2) a toggled Series-Settings panel, (3) season tab navigation, (4) redesigned episode rows with real score/provider data. The backend gains one new field per episode (score + provider) without breaking existing callers.

**Tech Stack:** React 19, TypeScript, React Query, Flask/SQLAlchemy, Vite, Tailwind (CSS vars only, no Tailwind utility classes for layout)

---

## Reference Material

- **Mockup:** `D:/Sublarr_Projekt/Sublarr/mockups/concept-drilldown.html` — series page section
- **Current page:** `frontend/src/pages/SeriesDetail.tsx` (1164 lines)
- **Current components:**
  - `frontend/src/components/series/SeasonGroup.tsx`
  - `frontend/src/components/series/EpisodeGrid.tsx`
  - `frontend/src/components/library/EpisodeRow.tsx`
  - `frontend/src/components/library/SeasonSummaryBar.tsx`

---

## Gap Analysis (Mockup vs Current)

| Area | Mockup | Current | Action |
|------|--------|---------|--------|
| Hero meta tags | Anime · Fantasy · Sonarr · 2 Seasons · ASS preferred | Path + file count + status badges + language row | Replace entire row |
| Hero action buttons | 3 buttons: Search All Missing (primary), Re-scan Series, Series Settings | 5+ buttons in two rows | Collapse to 3, rest into Settings panel |
| Language row | Hidden (in Series Settings panel) | Always visible, cluttered | Move to Settings panel |
| Season navigation | Season tabs (one active at a time) | All seasons collapsed-groups shown simultaneously | New tab navigation + single-season view |
| Episode EP# | `E01` colored by status (red=missing, yellow=low) | `E86` always neutral | Color by status |
| Episode score column | Numeric score badge (green/yellow/red) or "Missing" badge | Always `—` | Add score from DB |
| Episode provider column | Provider name string | Always `—` | Add provider from DB |
| Episode actions — ok | sync icon + dot icon (small, icon-only) | overflow action menu | Replace with inline pair |
| Episode actions — missing | [Search] [Skip] buttons | expandable search panel | Inline buttons |
| Episode actions — low-score | [Find Better] [Accept] buttons | none | New state + buttons |
| Episode actions — searching | disabled [Searching…] | none | New state |
| Episode file subtitle | basename (muted) / "No subtitle found" (red) / "Searching…" | full file path + language badge pills | Redesign |
| Checkboxes in rows | None visible in normal mode | Always visible | Remove from inline rows |
| Processing Override section | Not in mockup | Always rendered | Remove from page |

---

## File Map

### Modified Files

| File | What changes |
|------|-------------|
| `backend/routes/library/series.py` | Add `score` + `provider` fields per episode |
| `frontend/src/lib/types.ts` | Add `score?: number` + `provider?: string` to `EpisodeInfo` |
| `frontend/src/pages/SeriesDetail.tsx` | Hero, season tabs, remove Processing Override section |
| `frontend/src/components/series/SeasonGroup.tsx` | Remove checkboxes, use new episode row layout |
| `frontend/src/components/series/EpisodeGrid.tsx` | New `ScoreBadge`, `ProviderCell`, `EpisodeActions` helpers |
| `frontend/src/components/library/EpisodeRow.tsx` | Add `low-score` status + update border map |

### New Files

| File | Purpose |
|------|---------|
| `frontend/src/components/series/SeriesSettingsPanel.tsx` | Collapsible panel with all secondary settings (language profile, absolute order, glossary, audio picker, fansub, extract, cleanup, export) |
| `frontend/src/components/series/SeriesHero.tsx` | Extracted hero component (poster + title + meta tags + stat boxes + 3 action buttons) |
| `frontend/src/components/series/SeasonTabs.tsx` | Season tab bar (Season 1, Season 2, …) with active state |

---

## Task 1: Backend — Add score + provider to episode data

**Files:**
- Modify: `backend/routes/library/series.py`
- Modify: `frontend/src/lib/types.ts`

**What to do:** The `subtitle_downloads` table has `file_path`, `language`, `score`, `provider_name`, `downloaded_at`. Join it against episodes by `file_path` and `language` (most-recent download per combo). Add `score` and `provider` to each episode dict in the API response.

- [ ] **Step 1: Locate the episode construction loop in series.py**

  Open `backend/routes/library/series.py`. Find the section (around line 240-300) where `subtitles[lang]` is populated. This is where we inject score + provider.

- [ ] **Step 2: Add the score/provider query**

  The actual query at line ~244 filters by a list of file paths (not `sonarr_series_id`). Find the existing block:

  ```python
  text(
      "SELECT file_path, language, format FROM subtitle_downloads "
      "WHERE file_path IN ({placeholders}) "
      "ORDER BY downloaded_at DESC",
  )
  ```

  Change to:

  ```python
  text(
      "SELECT file_path, language, format, score, provider_name FROM subtitle_downloads "
      "WHERE file_path IN ({placeholders}) "
      "ORDER BY downloaded_at DESC",
  )
  ```

  Then build a parallel `path_scores: dict[str, dict[str, tuple[int|None, str|None]]]` keyed by `file_path → lang → (score, provider_name)`, using the same "first row wins" (most-recent download) logic already used for `format`. Map file_path back to episode_id via the existing `path_to_ep` dict (or equivalent mapping already in the function).

  > **Note:** There may be a second subtitle_downloads query block for standalone mode. Apply the same extension there.

- [ ] **Step 3: Inject score + provider into episode dicts**

  In the loop that builds each `ep` dict (search for `"id": ep.id`), add:

  ```python
  ep_scores = history_scores.get(ep.id, {})
  ep["subtitle_scores"] = {
      lang: ep_scores.get(lang, (None, None))[0]
      for lang in ep.get("subtitles", {})
  }
  ep["subtitle_providers"] = {
      lang: ep_scores.get(lang, (None, None))[1]
      for lang in ep.get("subtitles", {})
  }
  ```

- [ ] **Step 4: Update TypeScript types**

  In `frontend/src/lib/types.ts`, extend `EpisodeInfo` with **optional** fields (required for backward-compatibility with all existing test `makeEp()` factories):

  ```typescript
  export interface EpisodeInfo {
    id: number
    season: number
    episode: number
    title: string
    has_file: boolean
    file_path: string
    subtitles: Record<string, string>
    subtitle_scores?: Record<string, number | null>    // NEW — optional
    subtitle_providers?: Record<string, string | null> // NEW — optional
    audio_languages: string[]
    monitored: boolean
  }
  ```

  > **Critical:** The `?` optional marker is required. All existing `makeEp()` test factories across `EpisodeRow.test.tsx`, `SeasonSummaryBar.test.tsx`, and `EpisodeGrid.test.tsx` create objects without these fields. Making them required would break TypeScript compilation across all test files. The plan's own `getRowStatus` already uses `ep.subtitle_scores?.` (optional chaining) which is consistent.

- [ ] **Step 5: Verify API response manually**

  ```bash
  curl -s "http://localhost:5765/api/v1/series/1" \
    -H "X-Api-Key: 0353bfe082a825d0ca6f2620df6b2bae2698c92734bf5f576a110ddf626f1080" \
    | python -c "import sys,json; d=json.load(sys.stdin); ep=d.get('episodes',[])[0] if d.get('episodes') else {}; print('scores:', ep.get('subtitle_scores')); print('providers:', ep.get('subtitle_providers'))"
  ```

  Expected: dicts present (may be all null if no downloads yet — that's OK).

- [ ] **Step 6: Commit**

  ```bash
  cd D:/Sublarr_Projekt/Sublarr
  git add backend/routes/library/series.py frontend/src/lib/types.ts
  git commit -m "feat: add subtitle_scores and subtitle_providers to series episode API"
  ```

---

## Task 2: EpisodeGrid helpers — Score badge, Provider cell, Contextual actions

**Files:**
- Modify: `frontend/src/components/series/EpisodeGrid.tsx`
- Modify: `frontend/src/components/library/EpisodeRow.tsx`

**What to do:** Add helper components for the new column cells and determine the episode's visual status (ok / low-score / missing / searching).

- [ ] **Step 1: Add `low-score` to EpisodeRow status**

  In `frontend/src/components/library/EpisodeRow.tsx`:

  ```typescript
  export type EpisodeRowStatus = 'ok' | 'missing' | 'low-score' | 'no-file'

  const STATUS_BORDER: Record<EpisodeRowStatus, string> = {
    ok: 'transparent',          // mockup: no left border for ok rows
    'low-score': 'var(--warning)',
    missing: 'var(--error)',
    'no-file': 'var(--border)',
  }
  ```

  Update `getRowStatus` to accept optional `score`:

  ```typescript
  export function getRowStatus(
    ep: EpisodeInfo,
    targetLanguages: string[],
    lowScoreThreshold = 60,
  ): EpisodeRowStatus {
    if (!ep.has_file) return 'no-file'
    if (targetLanguages.length === 0) return 'ok'
    const hasMissing = targetLanguages.some((lang) => {
      const fmt = ep.subtitles[lang]
      return fmt == null || fmt === ''
    })
    if (hasMissing) return 'missing'
    // Check lowest score among target languages
    const scores = targetLanguages
      .map((lang) => ep.subtitle_scores?.[lang] ?? null)
      .filter((s): s is number => s !== null)
    if (scores.length > 0 && Math.min(...scores) < lowScoreThreshold) return 'low-score'
    return 'ok'
  }
  ```

- [ ] **Step 2: Add `ScoreCell` component to EpisodeGrid.tsx**

  ```typescript
  interface ScoreCellProps {
    readonly status: EpisodeRowStatus
    readonly score: number | null
    readonly isSearching?: boolean
  }

  export function ScoreCell({ status, score, isSearching }: ScoreCellProps) {
    if (isSearching) {
      return (
        <span style={{
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          width: '28px', height: '20px', borderRadius: '4px',
          backgroundColor: 'var(--accent-bg)', color: 'var(--accent)', fontSize: '13px',
        }}>⌛</span>
      )
    }
    if (status === 'missing') {
      return (
        <span style={{
          fontSize: '10px', fontWeight: 700, padding: '2px 6px', borderRadius: '4px',
          backgroundColor: 'rgba(239,68,68,0.15)', color: 'var(--error)',
        }}>Missing</span>
      )
    }
    if (score === null) {
      return <span style={{ color: 'var(--text-muted)', fontSize: '11px' }}>&mdash;</span>
    }
    // Score badge matches mockup .ep-score — background pill with color per tier
    const bgColor = score >= 80 ? 'var(--success-bg)' : score >= 60 ? 'var(--accent-bg)' : 'var(--warning-bg)'
    const color = score >= 80 ? 'var(--success)' : score >= 60 ? 'var(--accent)' : 'var(--warning)'
    return (
      <span style={{
        fontSize: '12px', fontWeight: 700,
        padding: '3px 10px', borderRadius: '6px',
        textAlign: 'center', width: 'fit-content',
        backgroundColor: bgColor, color,
      }}>{score}</span>
    )
  }
  ```

- [ ] **Step 3: Add `ProviderCell` component**

  ```typescript
  export function ProviderCell({ provider }: { provider: string | null }) {
    if (!provider) return <span style={{ color: 'var(--text-muted)', fontSize: '11px' }}>&mdash;</span>
    return <span style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>{provider}</span>
  }
  ```

- [ ] **Step 4: Add `EpisodeInlineActions` component**

  This replaces the overflow menu for normal use. For complex actions (edit, compare, sync, etc.) we keep them accessible via a small `⋯` overflow button.

  ```typescript
  interface EpisodeInlineActionsProps {
    readonly status: EpisodeRowStatus
    readonly isSearching: boolean
    readonly onSearch: () => void
    readonly onSkip: () => void
    readonly onFindBetter: () => void
    readonly onAccept: () => void
    readonly onSync: () => void
    readonly onDelete: () => void
    readonly onMore: () => void  // opens the existing EpisodeActionMenu
  }

  export function EpisodeInlineActions({
    status, isSearching, onSearch, onSkip, onFindBetter, onAccept, onSync, onDelete, onMore
  }: EpisodeInlineActionsProps) {
    if (isSearching) {
      return (
        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <button disabled style={{
            fontSize: '11px', padding: '3px 10px', borderRadius: '4px', opacity: 0.4,
            backgroundColor: 'var(--bg-elevated)', color: 'var(--text-muted)',
            border: '1px solid var(--border)',
          }}>Searching…</button>
        </div>
      )
    }
    if (status === 'missing') {
      return (
        <div style={{ display: 'flex', gap: '6px', justifyContent: 'flex-end' }}>
          <button
            onClick={onSearch}
            style={{
              fontSize: '11px', fontWeight: 600, padding: '3px 10px', borderRadius: '4px',
              backgroundColor: 'var(--accent)', color: '#fff', border: 'none', cursor: 'pointer',
            }}
          >Search</button>
          <button
            onClick={onSkip}
            style={{
              fontSize: '11px', padding: '3px 10px', borderRadius: '4px',
              backgroundColor: 'transparent', color: 'var(--text-secondary)',
              border: '1px solid var(--border)', cursor: 'pointer',
            }}
          >Skip</button>
        </div>
      )
    }
    if (status === 'low-score') {
      return (
        <div style={{ display: 'flex', gap: '6px', justifyContent: 'flex-end' }}>
          <button
            onClick={onFindBetter}
            style={{
              fontSize: '11px', fontWeight: 600, padding: '3px 10px', borderRadius: '4px',
              backgroundColor: 'var(--accent)', color: '#fff', border: 'none', cursor: 'pointer',
            }}
          >Find Better</button>
          <button
            onClick={onAccept}
            style={{
              fontSize: '11px', padding: '3px 10px', borderRadius: '4px',
              backgroundColor: 'transparent', color: 'var(--text-secondary)',
              border: '1px solid var(--border)', cursor: 'pointer',
            }}
          >Accept</button>
        </div>
      )
    }
    // status === 'ok'
    return (
      <div style={{ display: 'flex', gap: '4px', justifyContent: 'flex-end', alignItems: 'center' }}>
        <button
          onClick={onSync}
          title="Auto-sync"
          style={{
            padding: '4px', borderRadius: '4px', border: 'none', cursor: 'pointer',
            backgroundColor: 'transparent', color: 'var(--text-muted)',
          }}
          onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--accent)' }}
          onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--text-muted)' }}
        >↻</button>
        <button
          onClick={onMore}
          title="More actions"
          style={{
            width: '8px', height: '8px', borderRadius: '50%', border: 'none', cursor: 'pointer',
            backgroundColor: 'var(--accent)', display: 'block',
          }}
        />
      </div>
    )
  }
  ```

- [ ] **Step 5: Commit**

  ```bash
  git add frontend/src/components/series/EpisodeGrid.tsx \
          frontend/src/components/library/EpisodeRow.tsx
  git commit -m "feat: add ScoreCell, ProviderCell, EpisodeInlineActions, low-score status"
  ```

---

## Task 3: SeasonGroup — Redesign episode rows

**Files:**
- Modify: `frontend/src/components/series/SeasonGroup.tsx`

**What to do:** Replace the current episode row content (checkboxes, language badges, overflow menu) with the mockup layout: status-colored EP number, file subtitle/status text, format badge, score/provider cells, contextual inline actions. Checkboxes move to batch-only mode (shown only in batch toolbar, not per-row).

- [ ] **Step 1: Update episode row grid to match mockup columns**

  The current `EPISODE_GRID_COLUMNS = '50px 1fr 80px 90px 70px 140px'` is already correct for the mockup columns `# | EPISODE | FORMAT | PROVIDER | SCORE | ACTIONS`. Verify this matches the mockup widths visually.

- [ ] **Step 2: Replace episode row content in SeasonGroup.tsx**

  Replace the episode row JSX (lines ~130-241) with the mockup-aligned layout:

  ```typescript
  // Derive status
  const status = getRowStatus(ep, targetLanguages)
  const isSearching = false // TODO: derive from wanted_items status once exposed

  // Primary score/provider (first target language)
  const firstLang = targetLanguages[0] ?? ''
  const score = ep.subtitle_scores?.[firstLang] ?? null
  const provider = ep.subtitle_providers?.[firstLang] ?? null

  // Subtitle status text (file subtitle line)
  const filename = ep.has_file
    ? ep.file_path.split(/[/\\]/).pop() ?? ep.file_path
    : null

  const epNumberColor =
    status === 'missing' ? 'var(--error)' :
    status === 'low-score' ? 'var(--warning)' :
    'var(--text-secondary)'
  ```

  Replace the JSX columns:

  ```tsx
  {/* Apply status border override: missing → red border, low-score → yellow border,
      matching mockup inline styles border-color + border-left: 2px solid */}
  // In the row container, spread these overrides on top of episodeGridRowStyle:
  // status === 'missing'   → borderColor: 'var(--error)',   borderLeft: '2px solid var(--error)'
  // status === 'low-score' → borderColor: 'var(--warning)', borderLeft: '2px solid var(--warning)'

  {/* Column 1: EP number */}
  <div style={{ fontFamily: 'var(--font-mono)', fontSize: '12px', fontWeight: 600, color: epNumberColor }}>
    E{String(ep.episode).padStart(2, '0')}
  </div>

  {/* Column 2: Title + file/status line */}
  <div style={{ minWidth: 0 }}>
    <div style={{ fontSize: '13px', fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
      {ep.title || 'TBA'}
    </div>
    <div style={{ fontSize: '11px', marginTop: '2px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
      {isSearching ? (
        <span style={{ color: 'var(--error)' }}>Searching…</span>
      ) : status === 'missing' ? (
        <span style={{ color: 'var(--error)' }}>No subtitle found</span>
      ) : filename ? (
        <span style={{ color: 'var(--text-muted)' }}>{filename}</span>
      ) : (
        <span style={{ color: 'var(--text-muted)' }}>No file</span>
      )}
    </div>
  </div>

  {/* Column 3: Format */}
  <FormatBadge format={ep.has_file ? (ep.subtitles[firstLang] ?? '') : ''} />

  {/* Column 4: Provider */}
  <ProviderCell provider={status === 'missing' ? null : provider} />

  {/* Column 5: Score */}
  <ScoreCell status={status} score={score} isSearching={isSearching} />

  {/* Column 6: Inline actions */}
  <EpisodeInlineActions
    status={status}
    isSearching={isSearching}
    onSearch={() => onSearch(ep)}
    onSkip={() => { /* TODO: implement skip (mark as skipped in wanted_items) */ }}
    onFindBetter={() => onSearch(ep)}
    onAccept={() => { /* TODO: implement accept (set upgrade_candidate=false) */ }}
    onSync={() => {
      const path = deriveSubtitlePath(ep.file_path, firstLang, ep.subtitles[firstLang] ?? '')
      if (path) onAutoSync(path, ep.file_path)
    }}
    onDelete={() => {
      const path = deriveSubtitlePath(ep.file_path, firstLang, ep.subtitles[firstLang] ?? '')
      if (path) onDeleteSidecar(path)
    }}
    onMore={() => onInteractiveSearch(ep)}
  />
  ```

- [ ] **Step 3: Remove checkboxes and batch toolbar from SeasonGroup**

  Delete the `<input type="checkbox" ...>` element from Column 1.

  Remove these items from `SeasonGroup.tsx` entirely:
  - `selectedEpisodes` state + `toggleEpisode`, `selectAll`, `clearAll`, `allSelectableIds`
  - The `<div data-testid="episode-batch-toolbar" ...>` block at the bottom of the expanded section
  - `useBatchTranslate` hook call and its import (`import { useBatchTranslate } from '@/hooks/useApi'`)
  - `startWantedBatchSearch` import (`import { startWantedBatchSearch } from '@/api/client'`)
  - The `useCallback` and `useMemo` imports if they become unused after removal

  **Also rename `_onDeleteSidecar` → `onDeleteSidecar`** in both the `SeasonGroupProps` interface and the function destructuring signature. The underscore prefix was a lint-suppression for unused parameter; the new inline actions will call it directly.

  > **Important:** Do NOT remove the corresponding props from `SeasonGroupProps` for the other `_`-prefixed params unless they are also unused. Only `_onDeleteSidecar` changes — the rest stay as-is.

- [ ] **Step 4: Import new components**

  At the top of `SeasonGroup.tsx`:

  ```typescript
  import { ScoreCell, ProviderCell, EpisodeInlineActions, episodeGridRowStyle, FormatBadge } from './EpisodeGrid'
  import { getRowStatus } from '@/components/library/EpisodeRow'
  ```

- [ ] **Step 5: Run frontend checks**

  ```bash
  cd D:/Sublarr_Projekt/Sublarr/frontend
  npx tsc --noEmit
  npm run lint
  ```

  Expected: No errors.

- [ ] **Step 6: Commit**

  ```bash
  git add frontend/src/components/series/SeasonGroup.tsx
  git commit -m "feat: redesign episode rows to match mockup (score, provider, contextual actions)"
  ```

---

## Task 4: SeasonTabs — Season tab navigation component

**Files:**
- Create: `frontend/src/components/series/SeasonTabs.tsx`

**What to do:** A simple tab bar that renders one pill-button per season. The active season is passed as a prop. On click it calls `onSeasonChange(season)`. This replaces the all-season simultaneous display.

- [ ] **Step 1: Create SeasonTabs.tsx**

  ```typescript
  // frontend/src/components/series/SeasonTabs.tsx
  interface SeasonTabsProps {
    readonly seasons: number[]
    readonly activeSeason: number
    readonly onSeasonChange: (season: number) => void
  }

  export function SeasonTabs({ seasons, activeSeason, onSeasonChange }: SeasonTabsProps) {
    return (
      // Pill-container matching .season-tabs in mockup
      <div style={{
        display: 'flex', gap: '2px',
        background: 'var(--bg-surface)', borderRadius: 'var(--radius-md)',
        padding: '3px', width: 'fit-content', marginBottom: '14px',
      }}>
        {seasons.map((s) => (
          <button
            key={s}
            data-testid={`season-tab-${s}`}
            onClick={() => onSeasonChange(s)}
            style={{
              padding: '6px 16px',
              borderRadius: '7px',            // matches .season-tab border-radius
              fontSize: '12px',
              fontWeight: 500,
              cursor: 'pointer',
              transition: 'all 0.15s',
              border: 'none',
              backgroundColor: s === activeSeason ? 'var(--bg-elevated)' : 'transparent',
              color: s === activeSeason ? 'var(--text-primary)' : 'var(--text-secondary)',
              boxShadow: s === activeSeason ? '0 1px 3px rgba(0,0,0,0.2)' : 'none',
            }}
          >
            Season {s}
          </button>
        ))}
      </div>
    )
  }
  ```

- [ ] **Step 2: Commit**

  ```bash
  git add frontend/src/components/series/SeasonTabs.tsx
  git commit -m "feat: add SeasonTabs component for season navigation"
  ```

---

## Task 5: SeriesHero — Extract and redesign hero component

**Files:**
- Create: `frontend/src/components/series/SeriesHero.tsx`

**What to do:** Extract the hero section from `SeriesDetail.tsx` into its own component, redesigning the meta-tag row and action button row to match the mockup exactly.

### Meta tag mapping (Mockup → Data source)

| Tag shown in mockup | Data source |
|--------------------|-------------|
| "Anime" | `series.tags.includes('anime')` or series genre heuristic |
| "Fantasy" | `series.tags` (first tag or genre from TVDB) |
| "Sonarr" | Always "Sonarr" when media server = sonarr; "Standalone" otherwise |
| "2 Seasons" | `series.season_count` + " Season(s)" |
| "ASS preferred" | Derived from `series.profile_name` — if name contains "ASS" or "ass"; otherwise derive from what formats the series has |

### Action button mapping

| Mockup button | Current equivalent | Keep? |
|--------------|-------------------|-------|
| ⚡ Search All Missing | "X fehlende suchen" | ✅ Primary button |
| 🔄 Re-scan Series | Not yet present (calls rescan API) | ✅ New |
| ⚙️ Series Settings | Toggled panel showing language row + secondary actions | ✅ New |

- [ ] **Step 1: Create SeriesHero.tsx**

  ```typescript
  // frontend/src/components/series/SeriesHero.tsx
  import { FileVideo, Search, RefreshCw, Settings, Loader2, Sparkles } from 'lucide-react'
  import type { SeriesDetail } from '@/lib/types'

  interface SeriesHeroProps {
    readonly series: SeriesDetail
    readonly missingCount: number
    readonly withSubsCount: number
    readonly lowScoreCount: number
    readonly isMissingSearchPending: boolean
    readonly missingSearchStarted: boolean
    readonly onSearchAllMissing: () => void
    readonly onRescan: () => void
    readonly onSeriesSettings: () => void
  }

  function buildMetaTags(series: SeriesDetail): string[] {
    const tags: string[] = []
    // Genre/type tags from Sonarr tags
    const knownGenres = ['anime', 'fantasy', 'action', 'drama', 'comedy', 'sci-fi', 'thriller']
    for (const tag of series.tags) {
      const lower = tag.toLowerCase()
      if (knownGenres.includes(lower)) {
        tags.push(tag.charAt(0).toUpperCase() + tag.slice(1))
      }
    }
    // Source
    tags.push('Sonarr')
    // Season count
    if (series.season_count > 0) {
      tags.push(`${series.season_count} Season${series.season_count > 1 ? 's' : ''}`)
    }
    // Format preference — infer from profile name
    const profile = series.profile_name?.toLowerCase() ?? ''
    if (profile.includes('ass')) tags.push('ASS preferred')
    else if (profile.includes('srt')) tags.push('SRT preferred')
    return tags
  }

  export function SeriesHero({
    series, missingCount, withSubsCount, lowScoreCount,
    isMissingSearchPending, missingSearchStarted,
    onSearchAllMissing, onRescan, onSeriesSettings,
  }: SeriesHeroProps) {
    const totalEps = series.episode_file_count
    const metaTags = buildMetaTags(series)

    return (
      <div
        className="rounded-lg overflow-hidden relative"
        style={{ border: '1px solid var(--border)' }}
      >
        {/* Fanart background */}
        {series.fanart && (
          <div
            className="absolute inset-0"
            style={{
              backgroundImage: `url(${series.fanart})`,
              backgroundSize: 'cover', backgroundPosition: 'center',
              opacity: 0.15, filter: 'blur(2px)',
            }}
          />
        )}
        <div className="absolute inset-0" style={{
          background: 'linear-gradient(135deg, rgba(23,25,35,0.95) 0%, rgba(30,33,48,0.85) 100%)',
        }} />

        <div className="relative flex gap-6 p-5">
          {/* Poster */}
          <div
            className="flex-shrink-0 rounded-lg overflow-hidden shadow-lg"
            style={{ width: '180px', minWidth: '180px', aspectRatio: '2/3', border: '1px solid var(--border)' }}
          >
            {series.poster ? (
              <img src={series.poster} alt={series.title} className="w-full h-full object-cover" />
            ) : (
              <div className="w-full h-full flex items-center justify-center" style={{ backgroundColor: 'var(--bg-surface)' }}>
                <FileVideo size={32} style={{ color: 'var(--text-muted)' }} />
              </div>
            )}
          </div>

          {/* Info */}
          <div className="flex-1 min-w-0 flex flex-col gap-3">
            {/* Title + year */}
            <div className="flex items-center gap-2.5">
              <h1 data-testid="series-title" style={{ fontSize: '24px', fontWeight: 700, letterSpacing: '-0.5px' }}>
                {series.title}
              </h1>
              {series.year && (
                <span className="text-sm" style={{ color: 'var(--text-muted)', fontWeight: 400 }}>
                  {series.year}
                </span>
              )}
            </div>

            {/* Meta tags row */}
            <div className="flex flex-wrap gap-1.5">
              {metaTags.map((tag) => (
                <span
                  key={tag}
                  style={{
                    padding: '3px 10px', borderRadius: '6px', fontSize: '11px', fontWeight: 500,
                    backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border)',
                    color: 'var(--text-secondary)',
                  }}
                >
                  {tag}
                </span>
              ))}
            </div>

            {/* Stat boxes */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '10px' }}>
              {[
                { label: 'Episodes', value: totalEps, color: 'var(--accent)' },
                { label: 'With Subs', value: withSubsCount, color: 'var(--success)' },
                { label: 'Missing', value: missingCount, color: missingCount > 0 ? 'var(--error)' : 'var(--success)' },
                { label: 'Low Score', value: lowScoreCount, color: lowScoreCount > 0 ? 'var(--upgrade)' : 'var(--text-muted)' },
              ].map(({ label, value, color }) => (
                <div
                  key={label}
                  className="flex flex-col items-center text-center"
                  style={{
                    backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)',
                    borderRadius: 'var(--radius-md)', padding: '10px 14px',
                  }}
                >
                  <span style={{ fontSize: '20px', fontWeight: 700, color, fontFamily: 'var(--font-mono)' }} className="tabular-nums">
                    {value}
                  </span>
                  <span style={{ fontSize: '10px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.3px', marginTop: '2px' }}>
                    {label}
                  </span>
                </div>
              ))}
            </div>

            {/* Action buttons — exactly 3 as per mockup */}
            <div className="flex flex-wrap gap-2">
              {/* Primary: Search All Missing */}
              <button
                onClick={onSearchAllMissing}
                disabled={isMissingSearchPending || missingSearchStarted || missingCount === 0}
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: '6px',
                  padding: '7px 14px', borderRadius: '6px', fontSize: '13px', fontWeight: 600,
                  backgroundColor: missingSearchStarted ? 'var(--success-bg)' : 'var(--accent)',
                  color: missingSearchStarted ? 'var(--success)' : '#fff',
                  border: 'none', cursor: missingCount === 0 ? 'default' : 'pointer',
                  opacity: (isMissingSearchPending || missingCount === 0) ? 0.6 : 1,
                }}
              >
                {isMissingSearchPending
                  ? <Loader2 size={13} className="animate-spin" />
                  : missingSearchStarted
                    ? <Sparkles size={13} />
                    : '⚡'
                }
                {missingSearchStarted ? 'Suche läuft…' : 'Search All Missing'}
              </button>

              {/* Secondary: Re-scan Series */}
              <button
                onClick={onRescan}
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: '6px',
                  padding: '7px 14px', borderRadius: '6px', fontSize: '13px', fontWeight: 500,
                  backgroundColor: 'var(--bg-elevated)', color: 'var(--text-secondary)',
                  border: '1px solid var(--border)', cursor: 'pointer',
                }}
              >
                <RefreshCw size={13} />
                Re-scan Series
              </button>

              {/* Secondary: Series Settings */}
              <button
                onClick={onSeriesSettings}
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: '6px',
                  padding: '7px 14px', borderRadius: '6px', fontSize: '13px', fontWeight: 500,
                  backgroundColor: 'var(--bg-elevated)', color: 'var(--text-secondary)',
                  border: '1px solid var(--border)', cursor: 'pointer',
                }}
              >
                <Settings size={13} />
                Series Settings
              </button>
            </div>
          </div>
        </div>
      </div>
    )
  }
  ```

- [ ] **Step 2: Commit**

  ```bash
  git add frontend/src/components/series/SeriesHero.tsx
  git commit -m "feat: add SeriesHero component matching mockup meta tags + 3 action buttons"
  ```

---

## Task 6: SeriesSettingsPanel — Secondary settings

**Files:**
- Create: `frontend/src/components/series/SeriesSettingsPanel.tsx`

**What to do:** A collapsible panel (shown/hidden via the "Series Settings" button) that contains all secondary controls currently in the hero's language row and secondary action toolbar: language profile, target languages, glossary toggle, absolute order, AniDB refresh, audio picker, fansub override, extract tracks, cleanup, export ZIP.

- [ ] **Step 1: Create SeriesSettingsPanel.tsx**

  The panel receives all necessary callbacks as props (same ones currently scattered in `SeriesDetailPage`). It renders them in a clean grouped layout inside a `var(--bg-surface)` card.

  ```typescript
  // frontend/src/components/series/SeriesSettingsPanel.tsx

  // Props: all the callbacks + state that currently live in the language row
  // and secondary toolbar of SeriesDetailPage

  interface SeriesSettingsPanelProps {
    readonly series: SeriesDetail
    readonly seriesId: number
    readonly showGlossary: boolean
    readonly hasFansubOverride: boolean
    readonly isExtracting: boolean
    readonly extractProgress: { current: number; total: number; filename: string } | null
    readonly onToggleGlossary: () => void
    readonly onToggleAbsoluteOrder: (enabled: boolean) => void
    readonly onRefreshAnidb: () => void
    readonly onExtract: () => void
    readonly onCleanup: () => void
    readonly onFansub: () => void
    readonly exportUrl: string
    readonly updatePending: boolean
    readonly refreshPending: boolean
  }
  ```

  Render the panel as a rounded card with sections:
  - **Language** section: profile badge + target language badges + source language badge
  - **Subtitles** section: Glossary button, Absolute Order toggle, AniDB refresh (if absolute order active), Audio: Auto picker
  - **Tools** section: Export ZIP link, Extract Tracks button, Bereinigen button, Fansub button

- [ ] **Step 2: Commit**

  ```bash
  git add frontend/src/components/series/SeriesSettingsPanel.tsx
  git commit -m "feat: add SeriesSettingsPanel with language, subtitle settings, and tools"
  ```

---

## Task 7: SeriesDetailPage — Wire everything together

**Files:**
- Modify: `frontend/src/pages/SeriesDetail.tsx`

**What to do:** Replace the old hero JSX and the simultaneous-season layout with the new components. This is the integration step.

- [ ] **Step 1: Extract `withSubsCount` and `lowScoreCount` as `useMemo`**

  The current `withSubs` count is computed inline inside an IIFE inside JSX — it must be extracted as a named `useMemo` so it can be passed to `SeriesHero`. Add these to the component body alongside the existing `missingCount` memo:

  ```typescript
  const withSubsCount = useMemo(() => {
    if (!series?.episodes) return 0
    return series.episodes.filter(
      (ep) => ep.has_file && series.target_languages.some(
        (lang) => { const f = ep.subtitles[lang]; return f != null && f !== '' }
      )
    ).length
  }, [series])

  const LOW_SCORE_THRESHOLD = 60
  const lowScoreCount = useMemo(() => {
    if (!series?.episodes) return 0
    return series.episodes.filter((ep) => {
      if (!ep.has_file) return false
      return series.target_languages.some((lang) => {
        const score = ep.subtitle_scores?.[lang] ?? null
        const fmt = ep.subtitles[lang]
        return fmt != null && fmt !== '' && score !== null && score < LOW_SCORE_THRESHOLD
      })
    }).length
  }, [series])
  ```

- [ ] **Step 1b: Add `activeSeason` state and `showSeriesSettings` state**

  ```typescript
  const [activeSeason, setActiveSeason] = useState<number | null>(null)
  const [showSeriesSettings, setShowSeriesSettings] = useState(false)
  ```

  After `seasonGroups` is computed, derive the default active season:

  ```typescript
  // Default to the most recent season (seasonGroups is sorted latest-first)
  const defaultSeason = seasonGroups[0]?.[0] ?? null
  const currentSeason = activeSeason ?? defaultSeason
  const currentEpisodes = seasonGroups.find(([s]) => s === currentSeason)?.[1] ?? []
  ```

- [ ] **Step 2: Compute lowScoreCount**

  ```typescript
  const LOW_SCORE_THRESHOLD = 60
  const lowScoreCount = useMemo(() => {
    if (!series?.episodes) return 0
    return series.episodes.filter((ep) => {
      if (!ep.has_file) return false
      return series.target_languages.some((lang) => {
        const score = ep.subtitle_scores?.[lang] ?? null
        const fmt = ep.subtitles[lang]
        return fmt != null && fmt !== '' && score !== null && score < LOW_SCORE_THRESHOLD
      })
    }).length
  }, [series])
  ```

- [ ] **Step 3: Replace hero JSX**

  Replace the `{/* Hero Header */}` block (lines ~387-765 in current file) with:

  ```tsx
  <SeriesHero
    series={series}
    missingCount={missingCount}
    withSubsCount={withSubsCount}
    lowScoreCount={lowScoreCount}
    isMissingSearchPending={startSeriesSearch.isPending}
    missingSearchStarted={seriesSearchStarted}
    onSearchAllMissing={handleSearchAllEpisodes}
    onRescan={handleRescan}
    onSeriesSettings={() => setShowSeriesSettings((v) => !v)}
  />
  ```

  Also add `handleRescan`. **First check** `frontend/src/api/client.ts` for an existing rescan/refresh function. If none exists, implement it as a placeholder toast and create a TODO comment — do NOT use `startSeriesSearch` (that starts a subtitle provider search, not a filesystem rescan):

  ```typescript
  const handleRescan = useCallback(() => {
    // TODO: implement proper rescan endpoint (POST /api/v1/library/series/{id}/rescan)
    // For now, show a toast so the button is functional but non-destructive
    toast('Re-scan: coming soon', 'info')
  }, [])
  ```

  If a rescan endpoint already exists in the API client, use it instead. Search `client.ts` for `rescan` before choosing the placeholder.

- [ ] **Step 4: Replace series settings section**

  After `<SeriesHero .../>`, add:

  ```tsx
  {showSeriesSettings && seriesId !== null && (
    <SeriesSettingsPanel
      series={series}
      seriesId={seriesId}
      showGlossary={showGlossary}
      hasFansubOverride={hasFansubOverride}
      isExtracting={extractProgress !== null}
      extractProgress={extractProgress}
      onToggleGlossary={() => setShowGlossary((v) => !v)}
      onToggleAbsoluteOrder={handleToggleAbsoluteOrder}
      onRefreshAnidb={handleRefreshAnidbMapping}
      onExtract={handleExtract}
      onCleanup={() => setShowCleanupModal(true)}
      onFansub={() => setFansubOpen(true)}
      exportUrl={getSeriesSubtitleExportUrl(series.id)}
      updatePending={updateSeriesSettingsMutation.isPending}
      refreshPending={refreshAnidbMappingMutation.isPending}
    />
  )}
  ```

  Move `GlossaryPanel` inside `SeriesSettingsPanel` as a subsection (conditionally rendered when `showGlossary` is true).

- [ ] **Step 5: Remove Processing Override section**

  Delete the `<SeriesProcessingOverride .../>` block (currently at lines ~777-783). The mockup does not include it. If it's needed in the future, it can live in the Series Settings panel.

- [ ] **Step 6: Replace episode table with season tabs + single season view**

  Replace the current episode table section (lines ~785-900) with:

  ```tsx
  {/* Season tabs */}
  <SeasonTabs
    seasons={seasonGroups.map(([s]) => s).reverse()} // ascending order
    activeSeason={currentSeason ?? 0}
    onSeasonChange={setActiveSeason}
  />

  {/* Season summary bar */}
  {currentSeason !== null && (
    <SeasonSummaryBar
      season={currentSeason}
      episodes={currentEpisodes}
      targetLanguages={series.target_languages}
    />
  )}

  {/* Column header (no border — just grid-aligned text above cards) */}
  <EpisodeGridHeader />

  {/* Episode list — individual cards matching mockup .episode-list (gap: 4px) */}
  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
    {currentSeason !== null && (
      <SeasonGroup
        season={currentSeason}
        episodes={currentEpisodes}
        {/* ...same props as before... */}
      />
    )}
  </div>
  ```

  Remove the old `{seasonGroups.map(([season, episodes]) => (...))}` multi-season loop.

- [ ] **Step 7: Also remove the old inline episode table column header** (the one with EP | TITEL | AUDIO | UNTERTITEL | AKTIONEN at lines ~791-831) — this is replaced by `EpisodeGridHeader` from `EpisodeGrid.tsx`.

- [ ] **Step 8: Run all checks**

  ```bash
  cd D:/Sublarr_Projekt/Sublarr/frontend
  npx tsc --noEmit && npm run lint
  ```

  ```bash
  cd D:/Sublarr_Projekt/Sublarr/backend
  ruff check . && ruff format --check .
  ```

- [ ] **Step 9: Commit**

  ```bash
  git add frontend/src/pages/SeriesDetail.tsx \
          frontend/src/components/series/SeasonTabs.tsx \
          frontend/src/components/series/SeriesHero.tsx \
          frontend/src/components/series/SeriesSettingsPanel.tsx
  git commit -m "feat: wire SeriesDetailPage to match mockup — hero, season tabs, episode rows"
  ```

---

## Task 8: Visual polish — SeasonSummaryBar + row hover states

**Files:**
- Modify: `frontend/src/components/library/SeasonSummaryBar.tsx`
- Modify: `frontend/src/components/series/EpisodeGrid.tsx`

**What to do:** Verify the `SeasonSummaryBar` calculates "Low" separately from "Missing" (mockup shows: `19 OK • 2 Low • 3 Missing`). Update `episodeGridRowStyle` so each row is an individual card (`border + border-radius`) matching the mockup `.episode-row` style — the episode list uses `gap: 4px` between cards, not a shared bordered container.

- [ ] **Step 1: Check SeasonSummaryBar legend**

  Open `frontend/src/components/library/SeasonSummaryBar.tsx`. Verify it shows three categories: OK, Low (score < 60), Missing. If it only shows OK + Missing, add "Low Score" category using the same threshold (60) as in `getRowStatus`.

  > **⚠️ Test impact:** Adding the "Low Score" category changes how `ok` is calculated (from `total - missing` to `total - missing - lowScore`). The existing `SeasonSummaryBar.test.tsx` has assertions that will break. **Task 9 must update these tests** — this file is explicitly listed as a test casualty of this change.

- [ ] **Step 2: Update episodeGridRowStyle to match mockup row appearance**

  In `EpisodeGrid.tsx`:

  ```typescript
  export function episodeGridRowStyle({ status, isExpanded }: EpisodeGridRowStyleProps): React.CSSProperties {
    return {
      display: 'grid',
      gridTemplateColumns: EPISODE_GRID_COLUMNS,
      alignItems: 'center',
      padding: '10px 14px',
      gap: '10px',
      backgroundColor: isExpanded ? 'var(--bg-surface-hover)' : 'var(--bg-surface)',
      // Individual card per row matching mockup .episode-row
      border: '1px solid var(--border)',
      borderRadius: 'var(--radius-md)',
      transition: 'all 0.15s',
    }
  }

  // The status-specific border override goes in SeasonGroup when rendering each row:
  // missing rows → borderColor: 'var(--error)', borderLeft: '2px solid var(--error)'
  // low-score rows → borderColor: 'var(--warning)', borderLeft: '2px solid var(--warning)'
  ```

  The left-color indicator comes from `EpisodeRow`'s `borderLeft` — that remains.

- [ ] **Step 3: Verify in browser at http://localhost:5174/library/series/1**

  Visually check:
  - Season tabs at top (Season 1)
  - Summary bar showing counts
  - Clean episode rows with E01 format, score/provider columns
  - "No subtitle found" in red for missing episodes
  - Contextual action buttons

- [ ] **Step 4: Commit**

  ```bash
  git add frontend/src/components/library/SeasonSummaryBar.tsx \
          frontend/src/components/series/EpisodeGrid.tsx
  git commit -m "style: align row styles and summary bar with mockup"
  ```

---

## Task 9: Frontend tests — Update for new structure

**Files:**
- Modify: `frontend/src/components/library/__tests__/` (if exists)
- Modify: `frontend/src/pages/__tests__/` (if exists)

- [ ] **Step 1: Check existing tests**

  ```bash
  cd D:/Sublarr_Projekt/Sublarr/frontend
  npm run test -- --run 2>&1 | tail -30
  ```

  Expected: All pass, or identify which fail.

- [ ] **Step 2: Update broken tests**

  Any test that:
  - Queries for `data-testid="episode-row"` and expects checkboxes → remove checkbox assertion
  - Expects the old action menu → update to expect new inline buttons
  - Expects old header columns → update to new `# | EPISODE | FORMAT | PROVIDER | SCORE | ACTIONS`
  - **`SeasonSummaryBar.test.tsx`** — update OK count assertions now that low-score episodes are a separate category (previously `ok = total - missing`, now `ok = total - missing - lowScore`)
  - **`EpisodeRow.test.tsx`** — verify test factories still compile; `subtitle_scores` and `subtitle_providers` are optional so no factory changes needed, but if any test explicitly checks the `STATUS_BORDER` for `ok` rows, update the expected color from `var(--success)` to `transparent`

- [ ] **Step 3: Run full check suite**

  ```bash
  cd D:/Sublarr_Projekt/Sublarr/frontend
  npm run test -- --run && npx tsc --noEmit && npm run lint
  ```

  Expected: All pass.

- [ ] **Step 4: Commit**

  ```bash
  git add frontend/src/
  git commit -m "test: update frontend tests for series detail mockup alignment"
  ```

---

## Task 10: Backend tests + pre-PR check

**Files:**
- `backend/tests/` (check for series detail tests)

- [ ] **Step 1: Run backend tests**

  ```bash
  cd D:/Sublarr_Projekt/Sublarr/backend
  python -m pytest --tb=short -q \
    --ignore=tests/performance \
    --ignore=tests/integration/test_provider_pipeline.py \
    --ignore=tests/test_video_sync.py \
    --ignore=tests/test_translation_backends.py \
    -k "not (test_sonarr_download_webhook or test_radarr_download_webhook or test_parse_llm_response_too_many_merge or test_record_backend_success)"
  ```

  Expected: All pass.

- [ ] **Step 2: Run ruff on full backend**

  ```bash
  cd D:/Sublarr_Projekt/Sublarr/backend
  ruff check . && ruff format --check .
  ```

  Expected: No violations.

- [ ] **Step 3: Final commit if any test fixes needed**

  ```bash
  git add backend/
  git commit -m "test: ensure backend tests pass after series API score/provider addition"
  ```

---

## Definition of Done

The implementation is complete when:

- [ ] `http://localhost:5174/library/series/1` shows the hero with **3 action buttons only** (Search All Missing, Re-scan Series, Series Settings)
- [ ] Meta tags row shows pill tags (Anime / Sonarr / N Seasons / format preference) — no file path, no status badges in the hero
- [ ] Season tabs appear; clicking a tab shows only that season's episodes
- [ ] Episode rows show `E01`, `E02`, … with status-colored number
- [ ] Score column: shows numeric score or "Missing" badge or `—`
- [ ] Provider column: shows provider name or `—`
- [ ] Missing episodes have [Search] [Skip] buttons
- [ ] Low-score episodes have [Find Better] [Accept] buttons
- [ ] OK episodes have sync + dot action buttons
- [ ] No checkboxes visible in episode rows
- [ ] Processing Override section is gone from the page
- [ ] "Series Settings" button toggles the settings panel with all secondary controls
- [ ] All frontend tests pass (`npm run test -- --run`)
- [ ] All backend tests pass (`pytest ...`)
- [ ] `ruff check .` and `npx tsc --noEmit` both clean
