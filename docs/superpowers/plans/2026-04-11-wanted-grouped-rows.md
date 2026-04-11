# Wanted Page — Grouped Rows per Episode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Group wanted_items by file_path so each episode shows one row with DE+EN as sub-rows, instead of two separate rows.

**Architecture:** Backend adds `file_path` as secondary ORDER BY to guarantee pairs are adjacent. Frontend introduces a `WantedGroup` type, a pure `groupByFilePath()` function, and a new `WantedGroupedRow` component. `WantedTableRow` is refactored to export `WantedRowActions`, `SearchResultsRow`, and `FailureReasonRow` so both row components share them without circular imports.

**Tech Stack:** Python/SQLAlchemy (backend), React 19, TypeScript, Vitest, Tailwind/CSS variables

---

## File Map

| Action | File | What changes |
|--------|------|--------------|
| Modify | `backend/db/repositories/wanted.py:240` | Add `WantedItem.file_path` secondary ORDER BY |
| Modify | `frontend/src/types/wanted.ts` | Add `WantedGroup` interface |
| Modify | `frontend/src/pages/wanted/WantedTableRow.tsx` | Move `FailureReasonRow`+`formatRetryCountdown` in; extract+export `WantedRowActions`; export `SearchResultsRow` |
| Modify | `frontend/src/pages/Wanted.tsx` | Remove `FailureReasonRow` def; add `groupByFilePath`; switch render loop to `WantedGroupedRow`; update `visibleIds` |
| Create | `frontend/src/pages/wanted/WantedGroupedRow.tsx` | New grouped row component |
| Create | `frontend/src/pages/__tests__/groupByFilePath.test.ts` | Unit tests for the grouping function |
| Create | `backend/tests/test_wanted_sort.py` | Backend sort order test |

---

## Task 1: Backend — Secondary Sort Key

**Files:**
- Modify: `backend/db/repositories/wanted.py:240`
- Create: `backend/tests/test_wanted_sort.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_wanted_sort.py`:

```python
"""Verify that get_wanted_items uses file_path as secondary sort key."""

import pytest
from datetime import datetime, UTC
from unittest.mock import MagicMock, patch
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from db.models.core import Base, WantedItem
from db.repositories.wanted import WantedRepository


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def make_item(session, file_path: str, target_language: str) -> WantedItem:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    item = WantedItem(
        item_type="episode",
        file_path=file_path,
        title="Test",
        season_episode="S01E01",
        existing_sub="",
        missing_languages="[]",
        embedded_languages="[]",
        target_language=target_language,
        subtitle_type="full",
        status="wanted",
        added_at=now,
        updated_at=now,
    )
    session.add(item)
    session.commit()
    return item


def test_secondary_sort_by_file_path(session):
    """Items with same added_at must be returned ordered by file_path."""
    make_item(session, "/media/Z_Last.mkv", "de")
    make_item(session, "/media/A_First.mkv", "de")
    make_item(session, "/media/M_Middle.mkv", "de")

    repo = WantedRepository(session)
    result = repo.get_wanted_items(sort_by="added_at", sort_dir="asc")
    paths = [item["file_path"] for item in result["data"]]

    assert paths == ["/media/A_First.mkv", "/media/M_Middle.mkv", "/media/Z_Last.mkv"]


def test_pairs_adjacent_after_secondary_sort(session):
    """DE+EN pairs for the same file_path are always adjacent in results."""
    make_item(session, "/media/Ep1.mkv", "en")
    make_item(session, "/media/Ep2.mkv", "de")
    make_item(session, "/media/Ep1.mkv", "de")
    make_item(session, "/media/Ep2.mkv", "en")

    repo = WantedRepository(session)
    result = repo.get_wanted_items(sort_by="added_at", sort_dir="asc")
    paths = [item["file_path"] for item in result["data"]]

    # Ep1 pair must be adjacent, Ep2 pair must be adjacent
    assert paths[0] == paths[1]  # first two are same file
    assert paths[2] == paths[3]  # second two are same file
    assert paths[0] != paths[2]  # different files
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/test_wanted_sort.py -v
```

Expected: `FAILED` — the secondary sort is not yet applied, so file_path order is non-deterministic.

- [ ] **Step 3: Add secondary sort to get_wanted_items**

In `backend/db/repositories/wanted.py`, find line 240 (the data query ORDER BY):

```python
# Before (line 240):
        data_stmt = select(WantedItem).order_by(order).limit(per_page).offset(offset)

# After:
        data_stmt = select(WantedItem).order_by(order, WantedItem.file_path).limit(per_page).offset(offset)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && python -m pytest tests/test_wanted_sort.py -v
```

Expected: `PASSED` for both tests.

- [ ] **Step 5: Run full backend test suite to catch regressions**

```bash
cd backend && python -m pytest --tb=short -q \
  --ignore=tests/performance \
  --ignore=tests/integration/test_provider_pipeline.py \
  --ignore=tests/test_video_sync.py \
  --ignore=tests/test_translation_backends.py \
  -k "not (test_sonarr_download_webhook or test_radarr_download_webhook or test_parse_llm_response_too_many_merge or test_record_backend_success)"
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/db/repositories/wanted.py backend/tests/test_wanted_sort.py
git commit -m "fix: add file_path secondary sort to get_wanted_items for stable grouped display"
```

---

## Task 2: Frontend Types — Add WantedGroup

**Files:**
- Modify: `frontend/src/types/wanted.ts`

- [ ] **Step 1: Add WantedGroup interface**

In `frontend/src/types/wanted.ts`, insert after the closing `}` of `WantedItem` (after line 27):

```typescript
export interface WantedGroup {
  /** Stable group identity — equals file_path. */
  key: string
  title: string
  season_episode: string
  file_path: string
  item_type: 'episode' | 'movie'
  instance_name?: string
  /** One WantedItem per target_language, sorted alphabetically (de < en). */
  languages: WantedItem[]
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/types/wanted.ts
git commit -m "feat: add WantedGroup type for grouped wanted rows"
```

---

## Task 3: Refactor WantedTableRow — Export Shared Pieces

This task moves `FailureReasonRow` and `formatRetryCountdown` into `WantedTableRow.tsx` (so `WantedGroupedRow` can import them without a circular dep), extracts `WantedRowActions`, and exports `SearchResultsRow`.

**Files:**
- Modify: `frontend/src/pages/wanted/WantedTableRow.tsx`
- Modify: `frontend/src/pages/Wanted.tsx`

- [ ] **Step 1: Add FailureReasonRow and formatRetryCountdown to WantedTableRow.tsx**

At the top of `frontend/src/pages/wanted/WantedTableRow.tsx`, after the imports block, add:

```typescript
export function formatRetryCountdown(retryAfter: string | null): string | null {
  if (!retryAfter) return null
  const diff = new Date(retryAfter).getTime() - Date.now()
  if (diff <= 0) return null
  const totalMinutes = Math.floor(diff / 60_000)
  const hours = Math.floor(totalMinutes / 60)
  const minutes = totalMinutes % 60
  return hours > 0 ? `${hours}h ${minutes}m` : `${minutes}m`
}

interface FailureReasonRowProps {
  error: string
  retryAfter: string | null
  searchCount: number
}

export function FailureReasonRow({ error, retryAfter, searchCount }: FailureReasonRowProps) {
  if (!error) return null
  const countdown = formatRetryCountdown(retryAfter)
  return (
    <div style={{
      display: 'flex', alignItems: 'flex-start', gap: '8px',
      padding: '5px 10px', marginTop: '4px',
      background: 'color-mix(in srgb, var(--error) 8%, transparent)',
      borderLeft: '3px solid var(--error)',
      borderRadius: '0 4px 4px 0', fontSize: '12px',
      color: 'var(--text-secondary)',
    }}>
      <span style={{ color: 'var(--error)', flexShrink: 0 }}>✗</span>
      <div>
        {error}
        <span style={{ marginLeft: '6px', color: 'var(--text-muted)' }}>
          ({searchCount} attempt{searchCount !== 1 ? 's' : ''})
        </span>
        {countdown && (
          <span style={{ marginLeft: '6px', color: 'var(--text-muted)' }}>
            · Next retry in {countdown}
          </span>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Remove the FailureReasonRow import from WantedTableRow.tsx**

The file currently has (line 9):
```typescript
import { FailureReasonRow } from '@/pages/Wanted'
```

Delete that line. The function is now defined locally.

- [ ] **Step 3: Export SearchResultsRow**

Change the `function SearchResultsRow` declaration (currently around line 32) from:
```typescript
function SearchResultsRow({ results, isLoading, onBlacklist, t }: SearchResultsRowProps) {
```
to:
```typescript
export function SearchResultsRow({ results, isLoading, onBlacklist, t }: SearchResultsRowProps) {
```

- [ ] **Step 4: Add WantedRowActionsProps interface and WantedRowActions component**

After the `deriveSubtitlePath` helper function (~line 189), add:

```typescript
interface WantedRowActionsProps {
  item: WantedItem
  processingItemId: number | null
  extractingItemId: number | null
  processPending: boolean
  retranslatePending: boolean
  translationEnabled: boolean
  onProcess: (itemId: number) => void
  onExtract: (itemId: number, targetLanguage?: string) => void
  onRetranslate: (itemId: number) => void
  onUpdateStatus: (itemId: number, status: string) => void
  onPreview: (filePath: string) => void
  onInteractiveSearch: (item: { id: number; title: string }) => void
}

export function WantedRowActions({
  item,
  processingItemId,
  extractingItemId,
  processPending,
  retranslatePending,
  translationEnabled,
  onProcess,
  onExtract,
  onRetranslate,
  onUpdateStatus,
  onPreview,
  onInteractiveSearch,
}: WantedRowActionsProps) {
  const { t } = useTranslation('library')
  return (
    <div className="flex items-center justify-end gap-1">
      {(item.existing_sub === 'ass' || item.existing_sub === 'srt') && item.file_path && item.target_language && (
        <button
          onClick={() => onPreview(deriveSubtitlePath(item.file_path, item.target_language, item.existing_sub))}
          className="p-1 rounded transition-colors duration-150"
          title="Preview subtitle"
          style={{ color: 'var(--text-muted)' }}
          onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--accent)')}
          onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--text-muted)')}
        >
          <Eye size={14} />
        </button>
      )}
      <button
        data-testid="wanted-search-btn"
        onClick={() => onProcess(item.id)}
        disabled={processingItemId === item.id}
        className="p-1 rounded transition-colors duration-150"
        title={t('wanted.search_providers')}
        style={{ color: 'var(--text-muted)' }}
        onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--accent)')}
        onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--text-muted)')}
      >
        {processingItemId === item.id
          ? <Loader2 size={14} className="animate-spin" />
          : <Search size={14} />}
      </button>
      {(item.existing_sub === 'embedded_ass' || item.existing_sub === 'embedded_srt') && (
        <button
          onClick={() => onExtract(item.id, item.target_language)}
          disabled={extractingItemId === item.id}
          className="p-1 rounded transition-colors duration-150"
          title={t('wanted.extract_embedded')}
          style={{ color: 'var(--text-muted)' }}
          onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--accent)')}
          onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--text-muted)')}
        >
          {extractingItemId === item.id ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}
        </button>
      )}
      <button
        onClick={() => onInteractiveSearch({ id: item.id, title: item.title })}
        className="p-1 rounded transition-colors duration-150"
        title="Interaktive Suche"
        style={{ color: 'var(--text-muted)' }}
        onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--accent)')}
        onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--text-muted)')}
      >
        <ScanSearch size={14} />
      </button>
      <button
        data-testid="wanted-process-btn"
        onClick={() => onProcess(item.id)}
        disabled={processPending || item.status === 'searching'}
        className="p-1 rounded transition-colors duration-150"
        title={t('wanted.download_translate')}
        style={{ color: 'var(--text-muted)' }}
        onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--success)')}
        onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--text-muted)')}
      >
        <Play size={14} />
      </button>
      {translationEnabled && (
        <button
          onClick={() => onRetranslate(item.id)}
          disabled={retranslatePending}
          className="p-1 rounded transition-colors duration-150"
          title={t('wanted.re_translate')}
          style={{ color: 'var(--text-muted)' }}
          onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--warning)')}
          onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--text-muted)')}
        >
          <RefreshCw size={14} />
        </button>
      )}
      <button
        onClick={() => onUpdateStatus(item.id, item.status === 'ignored' ? 'wanted' : 'ignored')}
        className="p-1 rounded transition-colors duration-150"
        title={item.status === 'ignored' ? t('wanted.un_ignore_action') : t('wanted.ignore_action')}
        style={{ color: 'var(--text-muted)' }}
        onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--accent)')}
        onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--text-muted)')}
      >
        {item.status === 'ignored' ? <Eye size={14} /> : <EyeOff size={14} />}
      </button>
    </div>
  )
}
```

- [ ] **Step 5: Replace action JSX in WantedTableRow with WantedRowActions**

In `WantedTableRow`, find the actions `<td>` (currently around line 329):

```typescript
// Replace this entire <td>:
        <td className="px-4 py-2.5 text-right" style={{ position: 'sticky', right: 0, backgroundColor: 'var(--bg-elevated)' }}>
          <div className="flex items-center justify-end gap-1">
            {/* ... all the action buttons ... */}
          </div>
        </td>
// With this:
        <td className="px-4 py-2.5 text-right" style={{ position: 'sticky', right: 0, backgroundColor: 'var(--bg-elevated)' }}>
          <WantedRowActions
            item={item}
            processingItemId={processingItemId}
            extractingItemId={extractingItemId}
            processPending={processPending}
            retranslatePending={retranslatePending}
            translationEnabled={translationEnabled}
            onProcess={onProcess}
            onExtract={onExtract}
            onRetranslate={onRetranslate}
            onUpdateStatus={onUpdateStatus}
            onPreview={onPreview}
            onInteractiveSearch={onInteractiveSearch}
          />
        </td>
```

- [ ] **Step 6: Remove FailureReasonRow definition from Wanted.tsx and update its import**

In `frontend/src/pages/Wanted.tsx`:

1. Delete the `formatRetryCountdown` function definition (lines 28-36 area).
2. Delete the `FailureReasonRowProps` interface and `FailureReasonRow` function definition (lines 38-70 area).
3. Add an import at the top of the file:

```typescript
import { FailureReasonRow, formatRetryCountdown } from './wanted/WantedTableRow'
```

(These are now re-imported from WantedTableRow where they live.)

- [ ] **Step 7: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 8: Run frontend tests**

```bash
cd frontend && npm run test -- --run
```

Expected: all pass. The existing Wanted.toolbar tests still pass because the UI structure is unchanged.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/pages/wanted/WantedTableRow.tsx frontend/src/pages/Wanted.tsx
git commit -m "refactor: extract WantedRowActions and export SearchResultsRow/FailureReasonRow from WantedTableRow"
```

---

## Task 4: Create WantedGroupedRow Component

**Files:**
- Create: `frontend/src/pages/wanted/WantedGroupedRow.tsx`

- [ ] **Step 1: Create the file**

Create `frontend/src/pages/wanted/WantedGroupedRow.tsx` with the following content:

```typescript
import { Fragment } from 'react'
import { useTranslation } from 'react-i18next'
import { CheckSquare, Square, MinusSquare } from 'lucide-react'
import { formatRelativeTime, truncatePath } from '@/lib/utils'
import { StatusBadge, SubtitleTypeBadge } from '@/components/shared/StatusBadge'
import { SubtitlePresencePills } from '@/pages/wanted/SubtitlePresencePills'
import {
  WantedRowActions,
  SearchResultsRow,
  FailureReasonRow,
} from '@/pages/wanted/WantedTableRow'
import type { WantedGroup } from '@/types/wanted'
import type { WantedSearchResponse } from '@/lib/types'

interface WantedGroupedRowProps {
  group: WantedGroup
  groupIndex: number
  expandedItem: number | null
  sourceLanguage: string
  searchingItems: Set<number>
  searchResults: Record<number, WantedSearchResponse>
  extractingItemId: number | null
  processPending: boolean
  retranslatePending: boolean
  translationEnabled: boolean
  processingItemId: number | null
  isSelected: (id: number) => boolean
  onToggleGroup: (itemIds: number[], shiftKey: boolean) => void
  onProcess: (itemId: number) => void
  onExtract: (itemId: number, targetLanguage?: string) => void
  onRetranslate: (itemId: number) => void
  onUpdateStatus: (itemId: number, status: string) => void
  onPreview: (filePath: string) => void
  onInteractiveSearch: (item: { id: number; title: string }) => void
  onBlacklist: (itemId: number, providerName: string, subtitleId: string, language: string) => void
}

export function WantedGroupedRow({
  group,
  groupIndex,
  expandedItem,
  sourceLanguage,
  searchingItems,
  searchResults,
  extractingItemId,
  processPending,
  retranslatePending,
  translationEnabled,
  processingItemId,
  isSelected,
  onToggleGroup,
  onProcess,
  onExtract,
  onRetranslate,
  onUpdateStatus,
  onPreview,
  onInteractiveSearch,
  onBlacklist,
}: WantedGroupedRowProps) {
  const { t } = useTranslation('library')
  const lastIdx = group.languages.length - 1
  const allSelected = group.languages.every((l) => isSelected(l.id))
  const someSelected = group.languages.some((l) => isSelected(l.id))
  const selectionState: 'all' | 'some' | 'none' = allSelected ? 'all' : someSelected ? 'some' : 'none'
  const earliestAdded = group.languages.reduce<string | null>(
    (min, item) => (!min || (item.added_at && item.added_at < min) ? item.added_at : min),
    null
  )

  return (
    <Fragment>
      {group.languages.map((item, langIdx) => {
        const isFirst = langIdx === 0
        const isLast = langIdx === lastIdx

        return (
          <Fragment key={item.id}>
            <tr
              data-testid="wanted-item"
              className="transition-colors duration-100"
              style={{
                borderBottom: isLast
                  ? '1px solid var(--border)'
                  : '1px dashed color-mix(in srgb, var(--border) 50%, transparent)',
                animationDelay: `${Math.min(groupIndex * 30, 300)}ms`,
              }}
              onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = 'var(--bg-surface-hover)')}
              onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
            >
              {/* Checkbox — first sub-row only */}
              <td className="px-3 py-2.5 w-8" style={{ verticalAlign: 'top' }}>
                {isFirst && (
                  <button
                    onClick={(e) =>
                      onToggleGroup(
                        group.languages.map((l) => l.id),
                        e.shiftKey
                      )
                    }
                    className="p-0.5"
                    style={{ color: 'var(--text-muted)' }}
                  >
                    {selectionState === 'all' ? (
                      <CheckSquare size={14} style={{ color: 'var(--accent)' }} />
                    ) : selectionState === 'some' ? (
                      <MinusSquare size={14} style={{ color: 'var(--accent)' }} />
                    ) : (
                      <Square size={14} />
                    )}
                  </button>
                )}
              </td>

              {/* Title — first sub-row only */}
              <td className="px-3 py-2.5" title={group.file_path}>
                {isFirst && (
                  <div className="flex items-center gap-1.5">
                    <span
                      className="truncate max-w-xs text-sm"
                      style={{ fontFamily: 'var(--font-mono)', fontSize: '12px' }}
                    >
                      {group.title || truncatePath(group.file_path)}
                    </span>
                    {group.instance_name && (
                      <span
                        className="shrink-0 px-1.5 py-0.5 rounded text-[10px] font-medium"
                        style={{
                          backgroundColor: 'var(--bg-surface)',
                          color: 'var(--text-secondary)',
                          border: '1px solid var(--border)',
                        }}
                      >
                        {group.instance_name}
                      </span>
                    )}
                  </div>
                )}
              </td>

              {/* S/E — first sub-row only */}
              <td className="px-3 py-2.5">
                {isFirst && (
                  <span
                    className="text-xs"
                    style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}
                  >
                    {group.season_episode || (group.item_type === 'movie' ? t('wanted.movie') : '—')}
                  </span>
                )}
              </td>

              {/* Language badge + Status — per sub-row */}
              <td className="px-3 py-2.5">
                <div className="flex flex-col gap-0.5">
                  <div className="flex items-center gap-1.5">
                    <span
                      className="shrink-0 px-1.5 py-0.5 rounded text-[10px] font-bold uppercase"
                      style={{
                        backgroundColor: 'var(--accent-bg)',
                        color: 'var(--accent)',
                        fontFamily: 'var(--font-mono)',
                      }}
                    >
                      {item.target_language}
                    </span>
                    <StatusBadge status={item.status} />
                    <SubtitleTypeBadge subtitleType={item.subtitle_type} />
                  </div>
                  {item.status === 'failed' && (
                    <FailureReasonRow
                      error={item.error}
                      retryAfter={item.retry_after}
                      searchCount={item.search_count}
                    />
                  )}
                </div>
              </td>

              {/* Existing subtitle pills — per sub-row */}
              <td className="px-3 py-2.5 hidden sm:table-cell">
                <SubtitlePresencePills
                  existingSub={item.existing_sub}
                  targetLanguage={item.target_language}
                  sourceLanguage={sourceLanguage}
                  embeddedLanguages={item.embedded_languages ?? []}
                  upgradeCandidate={item.upgrade_candidate === 1}
                />
              </td>

              {/* Search count — per sub-row */}
              <td
                className="px-3 py-2.5 text-xs tabular-nums hidden md:table-cell"
                style={{ color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}
              >
                {item.search_count}
              </td>

              {/* Last search — per sub-row */}
              <td
                className="px-3 py-2.5 text-xs tabular-nums hidden lg:table-cell"
                style={{ color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}
              >
                {item.last_search_at ? formatRelativeTime(item.last_search_at) : t('wanted.never')}
              </td>

              {/* Added — first sub-row only (earliest across all languages) */}
              <td
                className="px-3 py-2.5 text-xs tabular-nums hidden lg:table-cell"
                style={{ color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}
              >
                {isFirst && earliestAdded ? formatRelativeTime(earliestAdded) : ''}
              </td>

              {/* Actions — per sub-row */}
              <td
                className="px-4 py-2.5 text-right"
                style={{ position: 'sticky', right: 0, backgroundColor: 'var(--bg-elevated)' }}
              >
                <WantedRowActions
                  item={item}
                  processingItemId={processingItemId}
                  extractingItemId={extractingItemId}
                  processPending={processPending}
                  retranslatePending={retranslatePending}
                  translationEnabled={translationEnabled}
                  onProcess={onProcess}
                  onExtract={onExtract}
                  onRetranslate={onRetranslate}
                  onUpdateStatus={onUpdateStatus}
                  onPreview={onPreview}
                  onInteractiveSearch={onInteractiveSearch}
                />
              </td>
            </tr>

            {/* Expandable search results for this language item */}
            {expandedItem === item.id && (
              <SearchResultsRow
                results={searchResults[item.id] ?? null}
                isLoading={searchingItems.has(item.id)}
                t={t}
                onBlacklist={(providerName, subtitleId, language) =>
                  onBlacklist(item.id, providerName, subtitleId, language)
                }
              />
            )}
          </Fragment>
        )
      })}
    </Fragment>
  )
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/wanted/WantedGroupedRow.tsx
git commit -m "feat: add WantedGroupedRow component for grouped language sub-rows"
```

---

## Task 5: Unit Tests for groupByFilePath

**Files:**
- Create: `frontend/src/pages/__tests__/groupByFilePath.test.ts`

The `groupByFilePath` function will be extracted from Wanted.tsx in the next task. Write the tests first so they guide the implementation.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/pages/__tests__/groupByFilePath.test.ts`:

```typescript
import { describe, it, expect } from 'vitest'

// This import will work once groupByFilePath is exported from Wanted.tsx in Task 6.
// It will fail until then — that's intentional (TDD).
import { groupByFilePath } from '@/pages/Wanted'
import type { WantedItem } from '@/types/wanted'

function makeItem(overrides: Partial<WantedItem>): WantedItem {
  return {
    id: 1,
    item_type: 'episode',
    sonarr_series_id: null,
    sonarr_episode_id: null,
    radarr_movie_id: null,
    title: 'Test',
    season_episode: 'S01E01',
    file_path: '/media/test.mkv',
    existing_sub: '',
    embedded_languages: [],
    missing_languages: [],
    target_language: 'de',
    status: 'wanted',
    last_search_at: '',
    search_count: 0,
    error: '',
    retry_after: null,
    added_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    upgrade_candidate: 0,
    current_score: 0,
    subtitle_type: 'full',
    ...overrides,
  }
}

describe('groupByFilePath', () => {
  it('groups two items with the same file_path into one group', () => {
    const items = [
      makeItem({ id: 1, file_path: '/a.mkv', target_language: 'de' }),
      makeItem({ id: 2, file_path: '/a.mkv', target_language: 'en' }),
    ]
    const groups = groupByFilePath(items)
    expect(groups).toHaveLength(1)
    expect(groups[0].languages).toHaveLength(2)
  })

  it('keeps items with different file_paths as separate groups', () => {
    const items = [
      makeItem({ id: 1, file_path: '/a.mkv', target_language: 'de' }),
      makeItem({ id: 2, file_path: '/b.mkv', target_language: 'de' }),
    ]
    const groups = groupByFilePath(items)
    expect(groups).toHaveLength(2)
  })

  it('sorts languages alphabetically within each group', () => {
    const items = [
      makeItem({ id: 1, file_path: '/a.mkv', target_language: 'en' }),
      makeItem({ id: 2, file_path: '/a.mkv', target_language: 'de' }),
    ]
    const groups = groupByFilePath(items)
    expect(groups[0].languages[0].target_language).toBe('de')
    expect(groups[0].languages[1].target_language).toBe('en')
  })

  it('preserves group order by first occurrence (server sort order)', () => {
    const items = [
      makeItem({ id: 1, file_path: '/z.mkv', target_language: 'de' }),
      makeItem({ id: 2, file_path: '/a.mkv', target_language: 'de' }),
    ]
    const groups = groupByFilePath(items)
    expect(groups[0].key).toBe('/z.mkv')
    expect(groups[1].key).toBe('/a.mkv')
  })

  it('copies group metadata from the first item', () => {
    const items = [
      makeItem({ id: 1, file_path: '/a.mkv', title: 'Anime S01E01', season_episode: 'S01E01', item_type: 'episode' }),
      makeItem({ id: 2, file_path: '/a.mkv', title: 'Anime S01E01', season_episode: 'S01E01', item_type: 'episode' }),
    ]
    const [group] = groupByFilePath(items)
    expect(group.title).toBe('Anime S01E01')
    expect(group.season_episode).toBe('S01E01')
    expect(group.item_type).toBe('episode')
  })

  it('handles empty input', () => {
    expect(groupByFilePath([])).toEqual([])
  })

  it('handles single item (single language profile)', () => {
    const items = [makeItem({ id: 1, file_path: '/a.mkv', target_language: 'de' })]
    const groups = groupByFilePath(items)
    expect(groups).toHaveLength(1)
    expect(groups[0].languages).toHaveLength(1)
  })

  it('handles three languages in one group', () => {
    const items = [
      makeItem({ id: 1, file_path: '/a.mkv', target_language: 'ja' }),
      makeItem({ id: 2, file_path: '/a.mkv', target_language: 'de' }),
      makeItem({ id: 3, file_path: '/a.mkv', target_language: 'en' }),
    ]
    const groups = groupByFilePath(items)
    expect(groups[0].languages.map((l) => l.target_language)).toEqual(['de', 'en', 'ja'])
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd frontend && npm run test -- --run --reporter=verbose 2>&1 | grep groupByFilePath
```

Expected: `FAIL` — `groupByFilePath is not exported from '@/pages/Wanted'`.

- [ ] **Step 3: Commit the test file**

```bash
git add frontend/src/pages/__tests__/groupByFilePath.test.ts
git commit -m "test: add groupByFilePath unit tests (TDD — red)"
```

---

## Task 6: Update Wanted.tsx — groupByFilePath + Switch Render Loop

**Files:**
- Modify: `frontend/src/pages/Wanted.tsx`

- [ ] **Step 1: Add groupByFilePath function and WantedGroup import**

At the top of `frontend/src/pages/Wanted.tsx`, add to the existing imports:

```typescript
import { WantedGroupedRow } from './wanted/WantedGroupedRow'
import type { WantedGroup } from '@/types/wanted'
```

Remove the import of `WantedTableRow`:
```typescript
// Remove this line:
import { WantedTableRow } from './wanted/WantedTableRow'
```

After the existing import block and before the `SCOPE` constant, add the exported `groupByFilePath` function:

```typescript
export function groupByFilePath(items: WantedItem[]): WantedGroup[] {
  const map = new Map<string, WantedGroup>()
  for (const item of items) {
    const key = item.file_path
    if (!map.has(key)) {
      map.set(key, {
        key,
        title: item.title,
        season_episode: item.season_episode,
        file_path: item.file_path,
        item_type: item.item_type,
        instance_name: item.instance_name,
        languages: [],
      })
    }
    map.get(key)!.languages.push(item)
  }
  for (const group of map.values()) {
    group.languages.sort((a, b) => a.target_language.localeCompare(b.target_language))
  }
  return Array.from(map.values())
}
```

- [ ] **Step 2: Add filteredGroups memo**

After the existing `filteredData` useMemo (around line 219), add:

```typescript
  // Group filtered flat items by file_path for the grouped row display
  const filteredGroups = useMemo(() => groupByFilePath(filteredData), [filteredData])
```

- [ ] **Step 3: Update visibleIds to cover all item IDs across groups**

Find (around line 239):
```typescript
  const visibleIds = useMemo(() => filteredData?.map((d) => d.id) ?? [], [filteredData])
```

Replace with:
```typescript
  const visibleIds = useMemo(
    () => filteredGroups.flatMap((g) => g.languages.map((l) => l.id)),
    [filteredGroups]
  )
```

- [ ] **Step 4: Add handleToggleGroup callback**

After the `toggleSelectAll` callback (around line 243), add:

```typescript
  const handleToggleGroup = useCallback(
    (itemIds: number[], _shiftKey: boolean) => {
      const allSel = itemIds.every((id) => isSelected(id))
      if (allSel) {
        // Deselect all items in the group
        for (const id of itemIds) {
          if (isSelected(id)) {
            const idx = visibleIds.indexOf(id)
            toggleItem(SCOPE, id, idx, false, visibleIds)
          }
        }
      } else {
        // Select all items in the group that aren't already selected
        for (const id of itemIds) {
          if (!isSelected(id)) {
            const idx = visibleIds.indexOf(id)
            toggleItem(SCOPE, id, idx, false, visibleIds)
          }
        }
      }
    },
    [isSelected, toggleItem, visibleIds]
  )
```

- [ ] **Step 5: Replace the render loop in the table body**

Find this block (around line 527–566):
```typescript
              ) : filteredData?.length ? (
                <>
                  {filteredData.map((item, i) => (
                    <WantedTableRow
                      key={item.id}
                      item={item}
                      itemIndex={i}
                      isSelected={isSelected(item.id)}
                      expandedItem={expandedItem}
                      sourceLanguage={sourceLanguage}
                      searchingItems={searchingItems}
                      searchResults={searchResults}
                      extractingItemId={extractingItemId}
                      searchPending={searchItem.isPending}
                      processPending={processItem.isPending}
                      retranslatePending={retranslateItem.isPending}
                      translationEnabled={!!translationEnabled}
                      visibleIds={visibleIds}
                      scope={SCOPE}
                      onToggleItem={toggleItem}
                      onSearch={handleSearch}
                      processingItemId={processingItemId}
                      onProcess={handleProcess}
                      onExtract={handleExtract}
                      onRetranslate={(id) => retranslateItem.mutate(id)}
                      onUpdateStatus={(id, status) => updateStatus.mutate({ itemId: id, status })}
                      onPreview={setPreviewFilePath}
                      onInteractiveSearch={setInteractiveItem}
                      onBlacklist={(itemId, providerName, subtitleId, language) => {
                        const item = filteredData.find(d => d.id === itemId)
                        addBlacklist.mutate({
                          provider_name: providerName,
                          subtitle_id: subtitleId,
                          language,
                          title: item?.title ?? '',
                          file_path: item?.file_path ?? '',
                          reason: 'Blacklisted from wanted search',
                        })
                      }}
                    />
                  ))}
```

Replace with:
```typescript
              ) : filteredGroups.length ? (
                <>
                  {filteredGroups.map((group, i) => (
                    <WantedGroupedRow
                      key={group.key}
                      group={group}
                      groupIndex={i}
                      expandedItem={expandedItem}
                      sourceLanguage={sourceLanguage}
                      searchingItems={searchingItems}
                      searchResults={searchResults}
                      extractingItemId={extractingItemId}
                      processPending={processItem.isPending}
                      retranslatePending={retranslateItem.isPending}
                      translationEnabled={!!translationEnabled}
                      processingItemId={processingItemId}
                      isSelected={isSelected}
                      onToggleGroup={handleToggleGroup}
                      onProcess={handleProcess}
                      onExtract={handleExtract}
                      onRetranslate={(id) => retranslateItem.mutate(id)}
                      onUpdateStatus={(id, status) => updateStatus.mutate({ itemId: id, status })}
                      onPreview={setPreviewFilePath}
                      onInteractiveSearch={setInteractiveItem}
                      onBlacklist={(itemId, providerName, subtitleId, language) => {
                        const item = wantedData.find(d => d.id === itemId)
                        addBlacklist.mutate({
                          provider_name: providerName,
                          subtitle_id: subtitleId,
                          language,
                          title: item?.title ?? '',
                          file_path: item?.file_path ?? '',
                          reason: 'Blacklisted from wanted search',
                        })
                      }}
                    />
                  ))}
```

Note: `wantedData.find(...)` (not `filteredData.find(...)`) in the blacklist handler — searches all loaded items regardless of filter.

Also update the empty state condition (around line 578):
```typescript
// Find:
                  {statusFilter || typeFilter || subtitleTypeFilter || languageFilter ? t('wanted.no_match_filters') : t('wanted.no_wanted_items')}
// This line stays the same — no change needed.
```

- [ ] **Step 6: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 7: Run frontend tests (including now-passing groupByFilePath tests)**

```bash
cd frontend && npm run test -- --run
```

Expected: all tests pass, including the new `groupByFilePath.test.ts` suite (8 tests).

- [ ] **Step 8: Run linter**

```bash
cd frontend && npm run lint
```

Expected: no errors.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/pages/Wanted.tsx
git commit -m "feat: group wanted items by file_path — one row per episode with language sub-rows"
```

---

## Task 7: Verify in Browser

- [ ] **Step 1: Start dev server**

```bash
npm run dev
```

- [ ] **Step 2: Open Wanted page**

Navigate to `http://localhost:5173` → Wanted page.

Verify:
- [ ] Each episode appears once, with DE and EN as sub-rows
- [ ] Title, S/E, and Added timestamp appear only in the first sub-row
- [ ] Language badge (e.g., `DE`) appears before the status badge in each sub-row
- [ ] Actions (search, extract, process, ignore) are present per language sub-row
- [ ] Group checkbox toggles both DE and EN selection; shows indeterminate when only one is selected
- [ ] Group separator (dashed) between sub-rows; solid border between groups
- [ ] Infinite scroll still loads more items as you scroll
- [ ] Language filter (e.g., filter to "DE only") shows each episode with only the DE sub-row
- [ ] Upgrade filter still works
- [ ] Batch actions (ignore, export, etc.) work via the floating BatchActionBar

- [ ] **Step 3: Final commit if any browser-driven tweaks were needed**

```bash
git add -p  # stage only intentional changes
git commit -m "fix: tweak WantedGroupedRow visual spacing after browser review"
```

---

## Self-Review Checklist

**Spec coverage:**
- [x] Backend secondary sort → Task 1
- [x] WantedGroup type → Task 2
- [x] WantedRowActions extraction → Task 3
- [x] WantedGroupedRow component → Task 4
- [x] groupByFilePath function → Task 5+6
- [x] Batch selection (indeterminate checkbox, group toggle) → Task 6 step 4
- [x] Search results expansion per language → Task 4 (SearchResultsRow per sub-row)
- [x] N-language profile (3+) → handled generically via `group.languages.map()`
- [x] Single-language profile → group has 1 sub-row, renders cleanly
- [x] Language filter → client-side filter runs on flat items before groupByFilePath, producing groups with only matching sub-rows
- [x] Infinite scroll → unchanged, sentinel row at end of groups list
- [x] No new API endpoints, no migrations

**Placeholder scan:** None found.

**Type consistency:**
- `WantedGroup.languages: WantedItem[]` uses `WantedItem` from `@/types/wanted` ✓
- `WantedGroupedRow` passes individual `item` (WantedItem) to `WantedRowActions` which accepts `WantedItem` (local interface, compatible subset) ✓
- `groupByFilePath` input is `WantedItem[]` from `@/types/wanted`, output is `WantedGroup[]` ✓
