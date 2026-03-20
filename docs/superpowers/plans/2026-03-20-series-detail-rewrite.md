# SeriesDetail.tsx Rewrite — File Split + Mockup Alignment

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the 2369-line `SeriesDetail.tsx` into focused sub-files (<400 lines each) and restructure the episode row layout to match the mockup's 6-column CSS grid design.

**Architecture:** Extract 6 inline sub-components into their own files under `components/series/`. Restructure the episode row from a flex layout with audio/subtitle columns to a CSS grid with FORMAT / PROVIDER / SCORE / ACTIONS columns matching the approved mockup (`mockups/concept-drilldown.html`). All existing functionality (subtitle management, editing, health badges, action menus) is preserved — only the visual layout changes.

**Tech Stack:** React 19, TypeScript, Vitest, CSS custom properties (design tokens from `index.css`)

---

## Reference: Mockup CSS Specs

From `mockups/concept-drilldown.html`:

```css
/* Episode row — 6-column CSS grid */
.episode-row {
  display: grid;
  grid-template-columns: 50px 1fr 80px 90px 70px 140px;
  align-items: center;
  padding: 10px 14px;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  gap: 10px;
}

/* Episode header — same grid */
.episode-header {
  display: grid;
  grid-template-columns: 50px 1fr 80px 90px 70px 140px;
  padding: 6px 14px;
  font-size: 10px; font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  gap: 10px;
}

/* Columns: #  |  Episode  |  Format  |  Provider  |  Score  |  Actions */
```

**Episode row content (from mockup HTML):**
- `ep-number`: `E01` — 13px, 600 weight, text-secondary
- `ep-title-group`: title (13px/500) + file path (10px, muted, truncate 350px)
- `ep-format`: Badge pill — `ASS` / `SRT` / `—` — bg-elevated, 11px/600
- `ep-provider`: Text — `Jimaku` / `OpenSubs` / `—` — 11px, text-muted
- `ep-score`: Colored badge — high(green)/medium(teal)/low(warning)/missing(error)
- `ep-actions`: Compact buttons — `btn sm` style

**Score color tiers:**
- `high` (≥80): success-bg + success color
- `medium` (50-79): accent-bg + accent color
- `low` (1-49): warning-bg + warning color
- `missing` (0 / no sub): error-bg + error color

**Missing episode styling:** `border-left: 2px solid var(--error)`, number in error color, file text says "No subtitle found"

**Low-score episode styling:** `border-left: 2px solid var(--warning)`, number in warning color

---

## File Structure

### New Files to Create

| File | Responsibility | ~Lines |
|------|---------------|--------|
| `frontend/src/components/series/seriesUtils.ts` | `normLang()`, `deriveSubtitlePath()`, `ISO6392_TO_1` map | ~60 |
| `frontend/src/components/series/SubBadge.tsx` | Subtitle language badge (teal/amber/orange) | ~50 |
| `frontend/src/components/series/ScoreBadge.tsx` | Score display badge with color tiers | ~50 |
| `frontend/src/components/series/EpisodeSearchPanel.tsx` | Search results table (download best) | ~130 |
| `frontend/src/components/series/EpisodeHistoryPanel.tsx` | History entries table | ~110 |
| `frontend/src/components/series/GlossaryPanel.tsx` | Full glossary CRUD + AI suggestions | ~380 |
| `frontend/src/components/series/EpisodeGrid.tsx` | Episode header row + grid-based episode rows (NEW LAYOUT) | ~200 |
| `frontend/src/components/series/SeasonGroup.tsx` | Season collapse, episode list, batch toolbar | ~350 |
| `frontend/src/components/series/__tests__/EpisodeGrid.test.tsx` | Tests for the new grid layout | ~120 |
| `frontend/src/components/series/__tests__/seriesUtils.test.tsx` | Tests for utility functions | ~60 |

### Files to Modify

| File | Change |
|------|--------|
| `frontend/src/pages/SeriesDetail.tsx` | Remove extracted code, import new components (~800 lines remaining) |
| `frontend/src/components/library/EpisodeRow.tsx` | Keep as-is (wrapper with status border) |

### Files NOT Changed

- All API hooks, types, modals, action menus — untouched
- `SeasonSummaryBar.tsx` — already extracted
- Backend — no changes

---

## Task 1: Extract Utility Functions

**Files:**
- Create: `frontend/src/components/series/seriesUtils.ts`
- Create: `frontend/src/components/series/__tests__/seriesUtils.test.tsx`
- Modify: `frontend/src/pages/SeriesDetail.tsx` (remove lines 42-90, add import)

- [ ] **Step 1: Write tests for utility functions**

```typescript
// frontend/src/components/series/__tests__/seriesUtils.test.tsx
import { describe, it, expect } from 'vitest'
import { normLang, deriveSubtitlePath } from '../seriesUtils'

describe('normLang', () => {
  it('maps 3-letter ISO 639-2 to 2-letter ISO 639-1', () => {
    expect(normLang('jpn')).toBe('ja')
    expect(normLang('eng')).toBe('en')
    expect(normLang('ger')).toBe('de')
    expect(normLang('deu')).toBe('de')
  })

  it('returns input unchanged if already 2-letter', () => {
    expect(normLang('en')).toBe('en')
    expect(normLang('de')).toBe('de')
  })

  it('returns input unchanged for unknown codes', () => {
    expect(normLang('xyz')).toBe('xyz')
  })
})

describe('deriveSubtitlePath', () => {
  it('constructs subtitle path from media path + lang + format', () => {
    const result = deriveSubtitlePath('/media/show/ep01.mkv', 'de', 'ass')
    expect(result).toBe('/media/show/ep01.de.ass')
  })

  it('handles srt format', () => {
    const result = deriveSubtitlePath('/media/show/ep01.mkv', 'en', 'srt')
    expect(result).toBe('/media/show/ep01.en.srt')
  })
})
```

- [ ] **Step 2: Run tests — expect FAIL (module not found)**

Run: `cd frontend && npx vitest run src/components/series/__tests__/seriesUtils.test.tsx`

- [ ] **Step 3: Create the utility module**

Extract `ISO6392_TO_1`, `normLang()`, and `deriveSubtitlePath()` from `SeriesDetail.tsx` (lines 47-90) into `frontend/src/components/series/seriesUtils.ts`. Export all three.

```typescript
// frontend/src/components/series/seriesUtils.ts

export const ISO6392_TO_1: Record<string, string> = {
  ger: 'de', deu: 'de', eng: 'en', dut: 'nl', nld: 'nl',
  swe: 'sv', dan: 'da', nor: 'no', nob: 'no', nno: 'no',
  fre: 'fr', fra: 'fr', spa: 'es', ita: 'it', por: 'pt',
  ron: 'ro', rum: 'ro', pol: 'pl', rus: 'ru', ces: 'cs', cze: 'cs',
  slk: 'sk', slo: 'sk', hrv: 'hr', srp: 'sr', bul: 'bg', ukr: 'uk',
  jpn: 'ja', chi: 'zh', zho: 'zh', kor: 'ko', tha: 'th', vie: 'vi',
  ind: 'id', ara: 'ar', tur: 'tr', hun: 'hu', fin: 'fi', heb: 'he',
}

/** Normalize ISO 639-2 (3-letter) to ISO 639-1 (2-letter). */
export function normLang(code: string): string {
  return ISO6392_TO_1[code.toLowerCase()] ?? code.toLowerCase()
}

/**
 * Derive the expected sidecar subtitle path from a media file path.
 * Example: /media/show/ep01.mkv + de + ass → /media/show/ep01.de.ass
 */
export function deriveSubtitlePath(filePath: string, lang: string, format: string): string {
  const lastDot = filePath.lastIndexOf('.')
  const base = lastDot >= 0 ? filePath.substring(0, lastDot) : filePath
  return `${base}.${lang}.${format}`
}
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `cd frontend && npx vitest run src/components/series/__tests__/seriesUtils.test.tsx`

- [ ] **Step 5: Update SeriesDetail.tsx imports**

In `SeriesDetail.tsx`:
1. Remove the `ISO6392_TO_1` map, `normLang()`, and `deriveSubtitlePath()` function definitions (lines 47-90)
2. Add import: `import { normLang, deriveSubtitlePath } from '@/components/series/seriesUtils'`

- [ ] **Step 6: Run all frontend tests**

Run: `cd frontend && npm run test -- --run`
Expected: All 515+ tests pass

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/series/seriesUtils.ts frontend/src/components/series/__tests__/seriesUtils.test.tsx frontend/src/pages/SeriesDetail.tsx
git commit -m "refactor: extract seriesUtils from SeriesDetail.tsx"
```

---

## Task 2: Extract SubBadge and ScoreBadge Components

**Files:**
- Create: `frontend/src/components/series/SubBadge.tsx`
- Create: `frontend/src/components/series/ScoreBadge.tsx`
- Modify: `frontend/src/pages/SeriesDetail.tsx` (remove lines 92-163, add imports)

- [ ] **Step 1: Create SubBadge component**

Extract the `SubBadge` component (currently lines 92-127 in SeriesDetail.tsx) into its own file.

```typescript
// frontend/src/components/series/SubBadge.tsx
import { useTranslation } from 'react-i18next'

interface SubBadgeProps {
  readonly lang: string
  readonly format: string
}

/** Language badge: teal=ASS, amber=SRT, orange=missing */
export function SubBadge({ lang, format }: SubBadgeProps) {
  // Copy the exact existing implementation from SeriesDetail.tsx lines 93-127
  // Keep ALL existing styling and logic unchanged
}
```

- [ ] **Step 2: Create ScoreBadge component**

Extract `ScoreBadge` (lines 129-163) into its own file. Update the color tiers to match the mockup:

```typescript
// frontend/src/components/series/ScoreBadge.tsx
interface ScoreBadgeProps {
  readonly score: number | null
  readonly size?: 'sm' | 'md'
}

/**
 * Score badge with mockup-matching color tiers:
 * - high (≥80): success-bg + success
 * - medium (50-79): accent-bg + accent
 * - low (1-49): warning-bg + warning
 * - missing (0/null): error-bg + error
 */
export function ScoreBadge({ score, size = 'md' }: ScoreBadgeProps) {
  if (score == null || score === 0) {
    return (
      <span
        data-testid="score-badge"
        className="inline-flex items-center justify-center rounded-md text-center"
        style={{
          fontSize: size === 'sm' ? '10px' : '12px',
          fontWeight: 700,
          padding: size === 'sm' ? '2px 6px' : '3px 10px',
          borderRadius: '6px',
          backgroundColor: 'var(--error-bg)',
          color: 'var(--error)',
          width: 'fit-content',
        }}
      >
        {score === 0 ? '0' : 'Missing'}
      </span>
    )
  }

  const tier = score >= 80 ? 'high' : score >= 50 ? 'medium' : 'low'
  const colors = {
    high: { bg: 'var(--success-bg)', color: 'var(--success)' },
    medium: { bg: 'var(--accent-bg)', color: 'var(--accent)' },
    low: { bg: 'var(--warning-bg)', color: 'var(--warning)' },
  }

  return (
    <span
      data-testid="score-badge"
      className="inline-flex items-center justify-center rounded-md text-center"
      style={{
        fontSize: size === 'sm' ? '10px' : '12px',
        fontWeight: 700,
        padding: size === 'sm' ? '2px 6px' : '3px 10px',
        borderRadius: '6px',
        backgroundColor: colors[tier].bg,
        color: colors[tier].color,
        width: 'fit-content',
      }}
    >
      {score}
    </span>
  )
}
```

- [ ] **Step 3: Update SeriesDetail.tsx imports**

Remove `SubBadge` and `ScoreBadge` definitions. Add:
```typescript
import { SubBadge } from '@/components/series/SubBadge'
import { ScoreBadge } from '@/components/series/ScoreBadge'
```

- [ ] **Step 4: Run all frontend tests**

Run: `cd frontend && npm run test -- --run`

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/series/SubBadge.tsx frontend/src/components/series/ScoreBadge.tsx frontend/src/pages/SeriesDetail.tsx
git commit -m "refactor: extract SubBadge and ScoreBadge from SeriesDetail.tsx"
```

---

## Task 3: Extract EpisodeSearchPanel and EpisodeHistoryPanel

**Files:**
- Create: `frontend/src/components/series/EpisodeSearchPanel.tsx`
- Create: `frontend/src/components/series/EpisodeHistoryPanel.tsx`
- Modify: `frontend/src/pages/SeriesDetail.tsx` (remove lines 165-278 and 654-749, add imports)

- [ ] **Step 1: Extract EpisodeSearchPanel**

Move lines 165-278 from SeriesDetail.tsx to `frontend/src/components/series/EpisodeSearchPanel.tsx`.

Keep the exact same props interface and implementation. Add the necessary imports at the top:
- `useTranslation` from react-i18next
- `Loader2`, `Download` from lucide-react
- `ScoreBadge` from `./ScoreBadge`
- Types: `WantedSearchResponse` from `@/lib/types`

Export: `export function EpisodeSearchPanel(...)`

- [ ] **Step 2: Extract EpisodeHistoryPanel**

Move lines 654-749 to `frontend/src/components/series/EpisodeHistoryPanel.tsx`.

Add imports:
- `useTranslation` from react-i18next
- `Loader2` from lucide-react
- `formatRelativeTime` from `@/lib/utils`
- Types: `EpisodeHistoryEntry` from `@/lib/types`

Export: `export function EpisodeHistoryPanel(...)`

- [ ] **Step 3: Update SeriesDetail.tsx imports**

Remove both component definitions. Add:
```typescript
import { EpisodeSearchPanel } from '@/components/series/EpisodeSearchPanel'
import { EpisodeHistoryPanel } from '@/components/series/EpisodeHistoryPanel'
```

- [ ] **Step 4: Run all frontend tests**

Run: `cd frontend && npm run test -- --run`

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/series/EpisodeSearchPanel.tsx frontend/src/components/series/EpisodeHistoryPanel.tsx frontend/src/pages/SeriesDetail.tsx
git commit -m "refactor: extract EpisodeSearchPanel and EpisodeHistoryPanel"
```

---

## Task 4: Extract GlossaryPanel

**Files:**
- Create: `frontend/src/components/series/GlossaryPanel.tsx`
- Modify: `frontend/src/pages/SeriesDetail.tsx` (remove lines 280-652, add import)

- [ ] **Step 1: Extract GlossaryPanel with all helpers**

Move lines 280-652 to `frontend/src/components/series/GlossaryPanel.tsx`.

This includes:
- `TERM_TYPE_COLORS` constant
- `TermTypeBadge` inline component
- `GlossaryPanel` component with full CRUD logic

Add all necessary imports:
- React hooks: `useState`
- `useTranslation`
- Icons: `Plus`, `Edit2`, `Trash2`, `Check`, `X`, `Download`, `Sparkles`, `Loader2`, `Search`
- API hooks: `useGlossaryEntries`, `useCreateGlossaryEntry`, `useUpdateGlossaryEntry`, `useDeleteGlossaryEntry`, `useSuggestGlossaryTerms`, `useExportGlossaryTsv`
- Types: `GlossaryCandidate` from `@/api/client`
- `toast` from `@/components/shared/Toast`

- [ ] **Step 2: Update SeriesDetail.tsx imports**

Remove GlossaryPanel definition. Add:
```typescript
import { GlossaryPanel } from '@/components/series/GlossaryPanel'
```

Also remove any imports that were ONLY used by GlossaryPanel (e.g., `useCreateGlossaryEntry`, `useUpdateGlossaryEntry`, `useDeleteGlossaryEntry`, `useSuggestGlossaryTerms`, `useExportGlossaryTsv`, `GlossaryCandidate`).

- [ ] **Step 3: Run all frontend tests + lint**

Run: `cd frontend && npm run lint && npx tsc --noEmit && npm run test -- --run`

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/series/GlossaryPanel.tsx frontend/src/pages/SeriesDetail.tsx
git commit -m "refactor: extract GlossaryPanel (370 lines) from SeriesDetail.tsx"
```

---

## Task 5: Create EpisodeGrid — New Mockup-Aligned Layout

**Files:**
- Create: `frontend/src/components/series/EpisodeGrid.tsx`
- Create: `frontend/src/components/series/__tests__/EpisodeGrid.test.tsx`

This is the key visual change. The mockup defines a 6-column grid layout:

```
 #  |  Episode (title + file)  |  Format  |  Provider  |  Score  |  Actions
```

The current app uses flex with audio + subtitle columns. This task creates the new grid-based layout.

- [ ] **Step 1: Write tests for EpisodeGrid**

```typescript
// frontend/src/components/series/__tests__/EpisodeGrid.test.tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key.split('.').pop() ?? key,
    i18n: { language: 'en', changeLanguage: vi.fn() },
  }),
}))

import { EpisodeGridHeader } from '../EpisodeGrid'

describe('EpisodeGridHeader', () => {
  it('renders 6 column labels', () => {
    render(<EpisodeGridHeader />)
    expect(screen.getByText('#')).toBeInTheDocument()
    expect(screen.getByText('Episode')).toBeInTheDocument()
    expect(screen.getByText('Format')).toBeInTheDocument()
    expect(screen.getByText('Provider')).toBeInTheDocument()
    expect(screen.getByText('Score')).toBeInTheDocument()
    expect(screen.getByText('Actions')).toBeInTheDocument()
  })

  it('uses CSS grid with 6 columns', () => {
    const { container } = render(<EpisodeGridHeader />)
    const header = container.firstChild as HTMLElement
    expect(header.style.display).toBe('grid')
    expect(header.style.gridTemplateColumns).toBe('50px 1fr 80px 90px 70px 140px')
  })
})
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `cd frontend && npx vitest run src/components/series/__tests__/EpisodeGrid.test.tsx`

- [ ] **Step 3: Implement EpisodeGrid**

```typescript
// frontend/src/components/series/EpisodeGrid.tsx

/** CSS grid template matching the mockup exactly */
export const EPISODE_GRID_COLUMNS = '50px 1fr 80px 90px 70px 140px'

/** Episode header row — column labels */
export function EpisodeGridHeader() {
  return (
    <div
      data-testid="episode-grid-header"
      style={{
        display: 'grid',
        gridTemplateColumns: EPISODE_GRID_COLUMNS,
        padding: '6px 14px',
        fontSize: '10px',
        fontWeight: 600,
        color: 'var(--text-muted)',
        textTransform: 'uppercase',
        letterSpacing: '0.5px',
        gap: '10px',
      }}
    >
      <span>#</span>
      <span>Episode</span>
      <span>Format</span>
      <span>Provider</span>
      <span>Score</span>
      <span style={{ textAlign: 'right' }}>Actions</span>
    </div>
  )
}

interface EpisodeGridRowStyleProps {
  /** 'ok' | 'missing' | 'low-score' */
  readonly status: 'ok' | 'missing' | 'low-score'
  readonly isExpanded?: boolean
}

/**
 * Returns inline styles for an episode grid row matching the mockup.
 * Usage: <div style={episodeGridRowStyle({ status: 'ok' })}>{...columns}</div>
 */
export function episodeGridRowStyle({ status, isExpanded }: EpisodeGridRowStyleProps): React.CSSProperties {
  const borderLeftColor =
    status === 'missing' ? 'var(--error)' :
    status === 'low-score' ? 'var(--warning)' :
    'transparent'

  return {
    display: 'grid',
    gridTemplateColumns: EPISODE_GRID_COLUMNS,
    alignItems: 'center',
    padding: '10px 14px',
    backgroundColor: isExpanded ? 'var(--bg-surface-hover)' : 'var(--bg-surface)',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius-md)',
    gap: '10px',
    borderLeft: `2px solid ${borderLeftColor}`,
    transition: 'all 0.15s',
  }
}

/** Format badge pill — ASS / SRT / — */
export function FormatBadge({ format }: { readonly format: string }) {
  if (!format || format === '') {
    return <span style={{ color: 'var(--text-muted)', fontSize: '11px' }}>&mdash;</span>
  }

  const label = format.replace('embedded_', '').toUpperCase()

  return (
    <span
      data-testid="format-badge"
      style={{
        fontSize: '11px',
        fontWeight: 600,
        padding: '2px 8px',
        borderRadius: '4px',
        backgroundColor: 'var(--bg-elevated)',
        color: 'var(--text-secondary)',
        width: 'fit-content',
      }}
    >
      {label}
    </span>
  )
}
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `cd frontend && npx vitest run src/components/series/__tests__/EpisodeGrid.test.tsx`

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/series/EpisodeGrid.tsx frontend/src/components/series/__tests__/EpisodeGrid.test.tsx
git commit -m "feat: add EpisodeGrid component with mockup-aligned 6-column layout"
```

---

## Task 6: Extract SeasonGroup with New Grid Layout

**Files:**
- Create: `frontend/src/components/series/SeasonGroup.tsx`
- Modify: `frontend/src/pages/SeriesDetail.tsx` (remove lines 751-1245, add import)

This is the largest extraction. `SeasonGroup` contains the episode listing logic with selection, batch actions, and the expanded panel. The episode row rendering must be restructured to use the new `EpisodeGrid` column layout.

- [ ] **Step 1: Create SeasonGroup component file**

Move lines 751-1245 from SeriesDetail.tsx to `frontend/src/components/series/SeasonGroup.tsx`.

**Key changes inside SeasonGroup:**

1. Import new components:
   ```typescript
   import { normLang, deriveSubtitlePath } from './seriesUtils'
   import { SubBadge } from './SubBadge'
   import { ScoreBadge } from './ScoreBadge'
   import { FormatBadge, episodeGridRowStyle } from './EpisodeGrid'
   import { EpisodeSearchPanel } from './EpisodeSearchPanel'
   import { EpisodeHistoryPanel } from './EpisodeHistoryPanel'
   ```

2. **Restructure episode row** from flex to grid layout. Replace the current flex-based row (lines ~872-1149) with the mockup's 6-column grid:

   ```tsx
   <div style={episodeGridRowStyle({ status, isExpanded })}>
     {/* Col 1: Episode number */}
     <div style={{
       fontSize: '13px',
       fontWeight: 600,
       color: status === 'missing' ? 'var(--error)' : status === 'low-score' ? 'var(--warning)' : 'var(--text-secondary)',
     }}>
       E{String(ep.episode).padStart(2, '0')}
     </div>

     {/* Col 2: Title + file */}
     <div style={{ minWidth: 0 }}>
       <div style={{ fontSize: '13px', fontWeight: 500 }}>
         {ep.title || t('series_detail.tba')}
       </div>
       <div style={{
         fontSize: '10px',
         color: status === 'missing' ? 'var(--error)' : 'var(--text-muted)',
         marginTop: '1px',
         whiteSpace: 'nowrap',
         overflow: 'hidden',
         textOverflow: 'ellipsis',
         maxWidth: '350px',
       }}>
         {/* Show subtitle filename or "No subtitle found" */}
         {primarySubtitle ? primarySubtitle.filename : (ep.has_file ? 'No subtitle found' : 'No media file')}
       </div>
     </div>

     {/* Col 3: Format badge */}
     <FormatBadge format={primaryFormat} />

     {/* Col 4: Provider */}
     <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
       {primaryProvider || '—'}
     </div>

     {/* Col 5: Score */}
     <ScoreBadge score={primaryScore} size="sm" />

     {/* Col 6: Actions */}
     <div style={{ display: 'flex', gap: '4px', justifyContent: 'flex-end' }}>
       {/* Keep existing EpisodeActionMenu */}
     </div>
   </div>
   ```

3. The `primaryFormat`, `primaryProvider`, and `primaryScore` values are derived from the episode's subtitle data for the first target language. Add this derivation at the top of each episode's render:

   ```typescript
   // Derive primary subtitle info for grid columns
   const primaryLang = targetLanguages[0]
   const primarySubFormat = primaryLang ? (ep.subtitles[primaryLang] || '') : ''
   const primaryFormat = primarySubFormat
   const primaryProvider = '' // Provider info not available in episode data — show '—'
   const primaryScore = null  // Score not available in episode data — show '—' or ScoreBadge
   ```

   > **Note:** The mockup shows Provider and Score columns with data like "Jimaku" and "94". In the actual app, these values are NOT stored per-episode in the current data model. For now, show `—` for provider and use ScoreBadge with null. When score data becomes available in the API, these columns will populate automatically.

- [ ] **Step 2: Remove SeasonGroup from SeriesDetail.tsx**

In SeriesDetail.tsx, remove the entire `SeasonGroup` function (lines 751-1245) and add:
```typescript
import { SeasonGroup } from '@/components/series/SeasonGroup'
```

Verify that the props interface matches — the existing usage in SeriesDetailPage passes ~40 props.

- [ ] **Step 3: Run all tests + typecheck**

Run: `cd frontend && npx tsc --noEmit && npm run test -- --run`

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/series/SeasonGroup.tsx frontend/src/pages/SeriesDetail.tsx
git commit -m "refactor: extract SeasonGroup with mockup-aligned episode grid layout"
```

---

## Task 7: Add EpisodeGridHeader to SeriesDetailPage

**Files:**
- Modify: `frontend/src/pages/SeriesDetail.tsx`

- [ ] **Step 1: Add the episode grid header**

In SeriesDetail.tsx, find where the episode table section begins (around the `seasonGroups.map()` call). Add the `EpisodeGridHeader` component above the season groups:

```tsx
import { EpisodeGridHeader } from '@/components/series/EpisodeGrid'

// ... in the render, before the season groups map:
<EpisodeGridHeader />
{seasonGroups.map(([season, episodes]) => (
  // ... SeasonSummaryBar + SeasonGroup
))}
```

- [ ] **Step 2: Run all frontend checks**

Run: `cd frontend && npm run lint && npx tsc --noEmit && npm run test -- --run`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/SeriesDetail.tsx
git commit -m "feat: add episode grid header matching mockup column layout"
```

---

## Task 8: Final Cleanup and Verification

**Files:**
- Modify: `frontend/src/pages/SeriesDetail.tsx` (remove unused imports)

- [ ] **Step 1: Remove unused imports from SeriesDetail.tsx**

After all extractions, check for unused imports. Likely removable:
- Icons that were only used in extracted components
- API hooks only used in GlossaryPanel
- Types only used in extracted components

Run: `cd frontend && npm run lint` — lint warnings will show unused imports.

- [ ] **Step 2: Verify file sizes**

Run: `wc -l frontend/src/pages/SeriesDetail.tsx frontend/src/components/series/*.tsx`

Expected: SeriesDetail.tsx should be ~800-900 lines. All new files should be <400 lines.

- [ ] **Step 3: Run full verification suite**

```bash
cd frontend && npm run lint && npx tsc --noEmit && npm run test -- --run
```

Expected: 0 errors, 0 lint errors, 515+ tests pass.

- [ ] **Step 4: Final commit**

```bash
git add -A frontend/src/
git commit -m "refactor: complete SeriesDetail.tsx split — 2369→~800 lines, 7 focused files"
```

---

## Summary

| Before | After |
|--------|-------|
| 1 file, 2369 lines | 8 files, ~800 lines max each |
| Flex-based episode rows | CSS grid matching mockup |
| Audio + Subtitle columns | Format + Provider + Score columns |
| 7 inline sub-components | 7 focused files with clear responsibilities |

**Risk areas:**
- SeasonGroup has ~40 props — must match exactly when extracting
- Episode row restructuring changes the visual layout significantly — verify in browser
- GlossaryPanel has complex state — test CRUD operations after extraction
