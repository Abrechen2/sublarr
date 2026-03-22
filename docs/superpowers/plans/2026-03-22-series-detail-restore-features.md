# Series Detail — Restore Missing Features Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore all missing episode-level features from `master` into `feature/frontend-redesign`'s SeasonGroup component, keeping the new grid-based UI design.

**Architecture:** All handlers and state already exist in `SeriesDetail.tsx` and are passed as props to `SeasonGroup` — they're just ignored (prefixed `_`). The work is entirely in `SeasonGroup.tsx` and `EpisodeGrid.tsx`: wire up the existing props, restore the subtitle badge column, add episode checkboxes, batch toolbar, audio badges, and swap `EpisodeInlineActions` for the full `EpisodeActionMenu`.

**Tech Stack:** React 19, TypeScript, Tailwind CSS utility classes, CSS variables for theming, TanStack Query for mutations.

---

## What's Missing (vs master)

| Feature | Status in current branch |
|---------|--------------------------|
| Episode checkboxes (individual + select-all) | `_` prefixed / unused |
| Subtitle badges (SubBadge teal/amber/orange per lang) | Only first lang, no colour coding |
| Sidecar actions per subtitle (delete, download, NFO, SubtitleActionsMenu) | `sidecarMap` unused |
| HealthBadge + preview/edit buttons per subtitle | `healthScores` + `onPreviewSub` + `onEditSub` unused |
| Extra sidecar badges (non-target langs) | Not rendered |
| Audio language badges column | Not rendered |
| Play button for streaming | `streamingEnabled` + `onPreview` unused |
| Full EpisodeActionMenu (history, tracks, compare, sync, videoSync) | Replaced with simplified `EpisodeInlineActions` |
| Batch toolbar (Search, Extract, Translate, Cleanup) | Removed |
| `onHistory`, `onTracks`, `onClose` wired | Prefixed `_`, not called |

---

## Files to Modify

| File | Change |
|------|--------|
| `frontend/src/components/series/EpisodeGrid.tsx` | Add `☐` column to grid definition + header |
| `frontend/src/components/series/SeasonGroup.tsx` | Full rewrite of episode row + season header; add batch toolbar |

**No changes needed in `SeriesDetail.tsx`** — all handlers/state already exist and are correctly passed.

---

## Task 1: Expand Grid Columns for Checkbox + Subtitle + Audio

**Files:**
- Modify: `frontend/src/components/series/EpisodeGrid.tsx`

The current grid `'50px 1fr 80px 90px 70px 140px'` has no room for checkboxes, audio badges, or a proper multi-language subtitle column. Update it.

- [ ] **Step 1: Update EPISODE_GRID_COLUMNS constant**

In `EpisodeGrid.tsx`, change:
```ts
export const EPISODE_GRID_COLUMNS = '50px 1fr 80px 90px 70px 140px'
```
to:
```ts
// ☐  EP#  Title  Audio  Subtitles  Actions
export const EPISODE_GRID_COLUMNS = '28px 50px 1fr 90px minmax(180px,1.5fr) 170px'
```

- [ ] **Step 2: Update EpisodeGridHeader to match new columns**

Replace the header content:
```tsx
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
        textTransform: 'uppercase' as const,
        letterSpacing: '0.5px',
        gap: '10px',
      }}
    >
      <span /> {/* checkbox placeholder */}
      <span>#</span>
      <span>Episode</span>
      <span>Audio</span>
      <span>Subtitles</span>
      <span style={{ textAlign: 'right' }}>Actions</span>
    </div>
  )
}
```

- [ ] **Step 3: Verify no TypeScript errors**
```bash
cd frontend && npx tsc --noEmit 2>&1 | grep EpisodeGrid
```
Expected: no errors

---

## Task 2: Add SubBadge Component to SeasonGroup

**Files:**
- Modify: `frontend/src/components/series/SeasonGroup.tsx`

The `SubBadge` from master visualises subtitle status as teal (ass), amber (srt), orange (missing). Currently the `FormatBadge` from EpisodeGrid is used but it doesn't have the same semantics.

- [ ] **Step 1: Add SubBadge component at top of SeasonGroup.tsx** (after imports):

```tsx
function SubBadge({ lang, format }: { lang: string; format: string }) {
  const isOptimal = format === 'ass' || format === 'embedded_ass'
  const isUpgradeable = format === 'srt' || format === 'embedded_srt'
  const isEmbedded = format === 'embedded_ass' || format === 'embedded_srt'
  const hasFile = isOptimal || isUpgradeable

  const bg = isOptimal ? 'var(--accent-bg)' : isUpgradeable ? 'var(--upgrade-bg, rgba(167,139,250,0.12))' : 'var(--warning-bg, rgba(245,158,11,0.12))'
  const color = isOptimal ? 'var(--accent)' : isUpgradeable ? 'var(--upgrade, #a78bfa)' : 'var(--warning, #f59e0b)'
  const border = isOptimal
    ? '1px solid var(--accent-dim)'
    : isUpgradeable
      ? '1px solid rgba(167,139,250,0.4)'
      : '1px solid rgba(245,158,11,0.3)'
  const label = isEmbedded ? format.replace('embedded_', '') + '⊕' : format
  const title = hasFile
    ? `${lang.toUpperCase()} (${format.toUpperCase()}${isEmbedded ? ' — embedded' : ''}${isUpgradeable ? ' — upgradeable to ASS' : ''})`
    : `${lang.toUpperCase()} missing`

  return (
    <span
      className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wide"
      style={{ backgroundColor: bg, color, border }}
      title={title}
    >
      {lang.toUpperCase()}
      {hasFile && <span style={{ opacity: 0.6, fontSize: '9px' }}>{label}</span>}
    </span>
  )
}
```

---

## Task 3: Rewrite SeasonGroup — Episode Row & Season Header

**Files:**
- Modify: `frontend/src/components/series/SeasonGroup.tsx`

This is the main task. Replace the simplified episode row with the full-featured version.

### 3a: Add missing imports

At the top of `SeasonGroup.tsx`, add:
```tsx
import { useState, useMemo, useCallback } from 'react'
import { Play, Eye, Pencil, X, FileCode, Download } from 'lucide-react'
import { normLang, deriveSubtitlePath } from './seriesUtils'
import { HealthBadge } from '@/components/health/HealthBadge'
import { EpisodeActionMenu } from '@/components/episodes/EpisodeActionMenu'
import { SubtitleActionsMenu } from '@/components/processing/SubtitleActionsMenu'
import { useBatchTranslate } from '@/hooks/useTranslationApi'
import { startWantedBatchSearch, exportSubtitleNfo, getSubtitleDownloadUrl } from '@/api/client'
import { toast } from '@/components/shared/Toast'
```

Remove unused imports: `Mic`, `Tv2`, `useTranscribeEpisode`, `useDetectOpeningEnding`, `FormatBadge`, `ScoreCell`, `ProviderCell`, `EpisodeInlineActions` (unless used elsewhere).

### 3b: Remove `_` prefixes from destructured props

In the function signature, rename all `_` prefixed parameters to their real names:
- `onHistory: _onHistory` → `onHistory`
- `onTracks: _onTracks` → `onTracks`
- `onClose: _onClose` → `onClose`
- `onPreviewSub: _onPreviewSub` → `onPreviewSub`
- `onEditSub: _onEditSub` → `onEditSub`
- `onCompare: _onCompare` → `onCompare`
- `onSync: _onSync` → `onSync`
- `onVideoSync: _onVideoSync` → `onVideoSync`
- `onHealthCheck: _onHealthCheck` → `onHealthCheck`
- `healthScores: _healthScores` → `healthScores`
- `sidecarMap: _sidecarMap` → `sidecarMap`
- `onOpenCleanupModal: _onOpenCleanupModal` → `onOpenCleanupModal`
- `onPreview: _onPreview` → `onPreview`
- `streamingEnabled: _streamingEnabled` → `streamingEnabled`
- `onRefreshSidecars: _onRefreshSidecars` → `onRefreshSidecars`
- `isExtracting: _isExtracting` → `isExtracting`
- `onExtract: _onExtract` → `onExtract`
- `seriesId: _seriesId` → `seriesId` (already used in hooks, actually keep as-is if not needed in row)

### 3c: Add selection state + batch translate

Inside the `SeasonGroup` function body, after `const [expanded, setExpanded] = useState(true)`:

```tsx
const [selectedEpisodes, setSelectedEpisodes] = useState<Set<number>>(new Set())
const batchTranslateMutation = useBatchTranslate()

const allSelectableIds = useMemo(
  () => episodes.map((e) => e.id).filter((id): id is number => id != null),
  [episodes]
)

const toggleEpisode = useCallback((id: number) => {
  setSelectedEpisodes((prev) => {
    const next = new Set(prev)
    if (next.has(id)) { next.delete(id) } else { next.add(id) }
    return next
  })
}, [])

const selectAll = useCallback(() => setSelectedEpisodes(new Set(allSelectableIds)), [allSelectableIds])
const clearAll = useCallback(() => setSelectedEpisodes(new Set()), [])
```

### 3d: Season header — add "Select All" checkbox

Replace the season header `<div>` content with:
```tsx
<div
  className="flex items-center"
  style={{
    backgroundColor: expanded ? 'var(--bg-elevated)' : 'var(--bg-surface)',
    borderBottom: expanded ? '1px solid var(--border)' : 'none',
    transition: 'background-color 0.15s',
  }}
>
  <button
    data-testid="season-group"
    onClick={() => setExpanded(!expanded)}
    className="flex-1 flex items-center gap-2 text-left transition-colors"
    style={{ padding: '8px 16px' }}
  >
    {expanded ? (
      <ChevronDown size={14} style={{ color: 'var(--accent)' }} />
    ) : (
      <ChevronRight size={14} style={{ color: 'var(--text-muted)' }} />
    )}
    <span style={{ fontSize: '13px', fontWeight: 600 }}>
      {t('series_detail.season', { number: season })}
    </span>
    <span style={{ fontSize: '11px', color: 'var(--text-muted)', marginLeft: '4px' }}>
      ({t('series_detail.episodes_count', { count: episodes.length })})
    </span>
  </button>
  {expanded && (
    <div className="pr-4 flex items-center gap-1.5">
      <input
        type="checkbox"
        checked={allSelectableIds.length > 0 && selectedEpisodes.size === allSelectableIds.length}
        onChange={() => selectedEpisodes.size === allSelectableIds.length ? clearAll() : selectAll()}
        style={{ accentColor: 'var(--accent)' }}
        title="Select all episodes in this season"
      />
      <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>All</span>
    </div>
  )}
</div>
```

### 3e: Episode row — full rewrite

Replace the episode row `<div style={{ ...episodeGridRowStyle(...) }}>` content entirely.

The new row uses `EPISODE_GRID_COLUMNS` = `'28px 50px 1fr 90px minmax(180px,1.5fr) 170px'`.

```tsx
<div
  data-testid="episode-row"
  key={ep.id}
>
  <div
    style={{
      display: 'grid',
      gridTemplateColumns: EPISODE_GRID_COLUMNS,
      alignItems: 'center',
      gap: '10px',
      padding: '6px 14px',
      borderBottom: isExpanded ? 'none' : '1px solid var(--border)',
      backgroundColor: isExpanded ? 'var(--bg-surface-hover)' : 'var(--bg-surface)',
      ...(status === 'missing' ? { borderLeft: '2px solid var(--error)' } :
         status === 'low-score' ? { borderLeft: '2px solid var(--warning)' } : {}),
    }}
    onMouseEnter={(e) => { if (!isExpanded) e.currentTarget.style.backgroundColor = 'var(--bg-surface-hover)' }}
    onMouseLeave={(e) => { if (!isExpanded) e.currentTarget.style.backgroundColor = 'var(--bg-surface)' }}
  >
    {/* Col 1: Checkbox */}
    <input
      type="checkbox"
      checked={selectedEpisodes.has(ep.id)}
      onChange={() => toggleEpisode(ep.id)}
      onClick={(e) => e.stopPropagation()}
      style={{ accentColor: 'var(--accent)' }}
    />

    {/* Col 2: EP number */}
    <div style={{ fontFamily: 'var(--font-mono)', fontSize: '12px', fontWeight: 600, color: epNumberColor }}>
      E{String(ep.episode).padStart(2, '0')}
    </div>

    {/* Col 3: Title + subtitle status line */}
    <div style={{ minWidth: 0 }}>
      <div style={{ fontSize: '13px', fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {ep.title || 'TBA'}
      </div>
      <div style={{ fontSize: '11px', marginTop: '2px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {status === 'missing' ? (
          <span style={{ color: 'var(--error)' }}>No subtitle found</span>
        ) : ep.file_path ? (
          <span style={{ color: 'var(--text-muted)' }}>
            {ep.file_path.split(/[/\\]/).pop() ?? ep.file_path}
          </span>
        ) : (
          <span style={{ color: 'var(--text-muted)' }}>No file</span>
        )}
      </div>
    </div>

    {/* Col 4: Audio language badges */}
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '3px' }}>
      {ep.audio_languages && ep.audio_languages.length > 0 ? (
        ep.audio_languages.map((lang, i) => (
          <span
            key={i}
            className="px-1.5 py-0.5 rounded text-[10px] font-medium uppercase"
            style={{ backgroundColor: 'rgba(99,102,241,0.12)', color: '#818cf8' }}
          >
            {lang}
          </span>
        ))
      ) : (
        <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>—</span>
      )}
    </div>

    {/* Col 5: Subtitle badges + sidecar actions */}
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px', alignItems: 'center' }}>
      {ep.has_file ? (
        <>
          {/* Target language badges */}
          {targetLanguages.length > 0 ? targetLanguages.map((lang) => {
            const subFormat = ep.subtitles[lang] || ''
            const epSidecars = sidecarMap[String(ep.id)] ?? []
            const matchingSidecar = (subFormat === 'ass' || subFormat === 'srt')
              ? epSidecars.find((s) => normLang(s.language) === normLang(lang) && s.format === subFormat)
              : null
            const subPath = (subFormat === 'ass' || subFormat === 'srt')
              ? deriveSubtitlePath(ep.file_path, lang, subFormat)
              : null
            return (
              <span key={lang} className="inline-flex items-center gap-0.5">
                <SubBadge lang={lang} format={subFormat} />
                {matchingSidecar && (
                  <>
                    <button
                      onClick={(e) => { e.stopPropagation(); void onDeleteSidecar(matchingSidecar.path) }}
                      className="p-0.5 rounded hover:opacity-80"
                      style={{ color: 'var(--error)', lineHeight: 1 }}
                      title={`Delete: ${matchingSidecar.path}`}
                    >
                      <X size={9} />
                    </button>
                    <a
                      href={getSubtitleDownloadUrl(matchingSidecar.path)}
                      download
                      title={`Download ${matchingSidecar.language} ${matchingSidecar.format}`}
                      className="p-0.5"
                      style={{ color: 'var(--text-muted)', lineHeight: 1 }}
                      onClick={(e) => e.stopPropagation()}
                    >
                      <Download size={10} />
                    </a>
                    <button
                      onClick={(e) => {
                        e.stopPropagation()
                        exportSubtitleNfo(matchingSidecar.path)
                          .then(() => toast('NFO exported', 'success'))
                          .catch(() => toast('NFO export failed', 'error'))
                      }}
                      className="p-0.5 rounded transition-colors"
                      style={{ color: 'var(--text-muted)', lineHeight: 1 }}
                      title="Export NFO sidecar"
                    >
                      <FileCode size={10} />
                    </button>
                    <SubtitleActionsMenu
                      subtitlePath={matchingSidecar.path}
                      onRefresh={onRefreshSidecars}
                    />
                  </>
                )}
                {subPath && (
                  <>
                    <HealthBadge score={healthScores[subPath] ?? null} size="sm" />
                    <button
                      onClick={() => onPreviewSub(subPath)}
                      className="p-0.5 rounded transition-colors"
                      style={{ color: 'var(--text-muted)' }}
                      title="Preview subtitle"
                      onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--accent)' }}
                      onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--text-muted)' }}
                    >
                      <Eye size={12} />
                    </button>
                    <button
                      onClick={() => onEditSub(subPath)}
                      className="p-0.5 rounded transition-colors"
                      style={{ color: 'var(--text-muted)' }}
                      title="Edit subtitle"
                      onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--accent)' }}
                      onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--text-muted)' }}
                    >
                      <Pencil size={12} />
                    </button>
                  </>
                )}
              </span>
            )
          }) : <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>—</span>}

          {/* Extra sidecars (non-target langs) */}
          {(() => {
            const epSidecars = sidecarMap[String(ep.id)] ?? []
            const extras = epSidecars.filter(
              (s) => !targetLanguages.some((tl) => normLang(tl) === normLang(s.language))
            )
            return extras.map((s) => (
              <span
                key={s.path}
                className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase"
                style={{ backgroundColor: 'var(--bg-surface)', color: 'var(--text-muted)', border: '1px solid var(--border)' }}
                title={`${s.language.toUpperCase()} ${s.format.toUpperCase()} — extra sidecar`}
              >
                {s.language.toUpperCase()}
                <span style={{ opacity: 0.6, fontSize: '9px' }}>{s.format}</span>
                <button
                  onClick={(e) => { e.stopPropagation(); void onDeleteSidecar(s.path) }}
                  className="ml-0.5 rounded hover:opacity-80"
                  style={{ color: 'var(--error)', lineHeight: 1 }}
                  title={`Delete: ${s.path}`}
                >
                  <X size={9} />
                </button>
                <a
                  href={getSubtitleDownloadUrl(s.path)}
                  download
                  title={`Download ${s.language} ${s.format}`}
                  className="p-0.5"
                  style={{ color: 'var(--text-muted)', lineHeight: 1 }}
                  onClick={(e) => e.stopPropagation()}
                >
                  <Download size={10} />
                </a>
                <SubtitleActionsMenu subtitlePath={s.path} onRefresh={onRefreshSidecars} />
              </span>
            ))
          })()}
        </>
      ) : (
        <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>No file</span>
      )}
    </div>

    {/* Col 6: Actions */}
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: '2px' }}>
      {/* Play button (streaming) */}
      {streamingEnabled && ep.has_file && ep.file_path && (
        <button
          onClick={() => onPreview(ep)}
          className="p-1 rounded transition-colors"
          style={{ color: 'var(--text-muted)' }}
          title="Preview in player"
          onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--accent)' }}
          onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--text-muted)' }}
        >
          <Play size={13} />
        </button>
      )}
      {/* Full action menu */}
      {(() => {
        const firstEntry = ep.has_file
          ? Object.entries(ep.subtitles).find(([, f]) => f === 'ass' || f === 'srt')
          : null
        const firstSubPath = firstEntry
          ? deriveSubtitlePath(ep.file_path, firstEntry[0], firstEntry[1])
          : null
        const hasMultipleSubs = ep.has_file
          ? Object.values(ep.subtitles).filter((f) => f === 'ass' || f === 'srt').length >= 2
          : false
        return (
          <EpisodeActionMenu
            ep={ep}
            isExpanded={isExpanded}
            mode={mode}
            searchLoading={searchLoading}
            historyLoading={historyLoading}
            firstSubPath={firstSubPath}
            hasMultipleSubs={hasMultipleSubs}
            onSearch={() => onSearch(ep)}
            onEditSub={onEditSub}
            onPreviewSub={onPreviewSub}
            onCompare={() => onCompare(ep)}
            onSync={onSync}
            onAutoSync={onAutoSync}
            onVideoSync={(subtitlePath) => onVideoSync(ep, subtitlePath)}
            onHealthCheck={onHealthCheck}
            onTracks={() => onTracks(ep)}
            onInteractiveSearch={() => onInteractiveSearch(ep)}
            onHistory={() => onHistory(ep)}
            onClose={onClose}
          />
        )
      })()}
    </div>
  </div>

  {/* Expanded panels */}
  {isExpanded && (
    <div style={{ borderBottom: '1px solid var(--border)' }}>
      {mode === 'search' && (
        <EpisodeSearchPanel
          results={searchResults}
          isLoading={searchLoading}
          onProcess={onProcess}
        />
      )}
      {mode === 'history' && (
        <EpisodeHistoryPanel
          entries={historyEntries}
          isLoading={historyLoading}
        />
      )}
      {mode === 'tracks' && (
        <TrackPanel episodeId={ep.id} onOpenEditor={onOpenEditor} />
      )}
    </div>
  )}
</div>
```

- [ ] **Step 1: Add SubBadge component** (see Task 2)

- [ ] **Step 2: Add missing imports** (see 3a)

- [ ] **Step 3: Remove `_` prefixes from props** (see 3b)

- [ ] **Step 4: Add selection state + batch translate** (see 3c)

- [ ] **Step 5: Rewrite season header with checkbox** (see 3d)

- [ ] **Step 6: Rewrite episode row** (see 3e — replace the old simplified row with the full grid row above)

- [ ] **Step 7: Add batch toolbar after episodes list**

After the `.map((ep) => ...)` block and before closing `</div>`:

```tsx
{selectedEpisodes.size > 0 && (
  <div
    data-testid="episode-batch-toolbar"
    className="flex items-center gap-2 px-3 py-2 rounded-lg mt-2 mx-2 mb-2"
    style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--accent-dim)' }}
  >
    <span className="text-xs font-medium mr-1" style={{ color: 'var(--accent)' }}>
      {selectedEpisodes.size} selected
    </span>
    <button
      onClick={() => { void startWantedBatchSearch([...selectedEpisodes]); clearAll() }}
      className="px-3 py-1 rounded text-xs font-medium"
      style={{ backgroundColor: 'var(--accent-bg)', color: 'var(--accent)', border: '1px solid var(--accent-dim)' }}
    >
      Search
    </button>
    <button
      onClick={() => { onExtract?.(); clearAll() }}
      disabled={isExtracting}
      className="px-3 py-1 rounded text-xs font-medium inline-flex items-center gap-1.5 disabled:opacity-60"
      style={{ backgroundColor: 'var(--bg-surface)', color: 'var(--text-secondary)', border: '1px solid var(--border)' }}
    >
      {isExtracting ? <Loader2 size={11} className="animate-spin" /> : null}
      Extract
    </button>
    <button
      onClick={() => {
        void batchTranslateMutation.mutate([...selectedEpisodes])
        clearAll()
      }}
      disabled={batchTranslateMutation.isPending}
      className="px-3 py-1 rounded text-xs font-medium disabled:opacity-60"
      style={{ backgroundColor: 'var(--bg-surface)', color: 'var(--text-secondary)', border: '1px solid var(--border)' }}
    >
      Translate
    </button>
    <button
      onClick={() => { onOpenCleanupModal(); clearAll() }}
      className="px-3 py-1 rounded text-xs font-medium"
      style={{ backgroundColor: 'var(--bg-surface)', color: 'var(--text-secondary)', border: '1px solid var(--border)' }}
    >
      Cleanup
    </button>
    <button
      onClick={clearAll}
      className="ml-auto px-2 py-1 rounded text-xs"
      style={{ color: 'var(--text-muted)' }}
    >
      Clear
    </button>
  </div>
)}
```

- [ ] **Step 8: TypeScript check**
```bash
cd frontend && npx tsc --noEmit 2>&1 | grep -E "SeasonGroup|EpisodeGrid"
```
Expected: no errors

- [ ] **Step 9: Lint check**
```bash
cd frontend && npm run lint 2>&1 | grep -E "SeasonGroup|EpisodeGrid"
```
Expected: no errors or warnings

- [ ] **Step 10: Run frontend unit tests**
```bash
cd frontend && npm run test -- --run 2>&1 | tail -20
```
Expected: all pass (or pre-existing failures only)

---

## Task 4: Commit

- [ ] **Step 1: Stage and commit**
```bash
cd D:/Sublarr_Projekt/Sublarr
git add frontend/src/components/series/SeasonGroup.tsx \
         frontend/src/components/series/EpisodeGrid.tsx
git commit -m "feat: restore full episode features in Series Detail (checkboxes, subtitle badges, sidecar actions, batch toolbar, audio badges)"
```

---

## Verification

After implementation, manually verify in the browser (http://localhost:5173):

1. Open a Series Detail page → each episode row shows: checkbox, EP#, title, audio badges, subtitle badges (coloured), actions menu
2. Subtitle badge teal = ASS, amber = SRT, orange = missing
3. Click episode checkbox → batch toolbar appears at bottom of season
4. "Select All" checkbox in season header works
5. Eye icon → opens subtitle preview, Pencil → opens editor
6. X icon next to badge → opens delete confirm dialog
7. Download icon → downloads subtitle file
8. EpisodeActionMenu "..." button opens with History, Tracks, Compare, Sync, VideoSync options
9. Batch toolbar: Search / Extract / Translate / Cleanup buttons all fire correct actions
10. Non-target-language sidecars show as extra grey badges with same sidecar actions
