# Wanted Page — Grouped Rows per Episode

**Date:** 2026-04-11
**Status:** Approved
**Scope:** Local only (no deploy)

---

## Problem

With a language profile of `['de', 'en']`, the scanner creates one `wanted_item` per (episode, language). The Wanted page renders each item as a separate row, so every episode appears twice — once for DE and once for EN. This makes the list twice as long as necessary and harder to scan.

## Goal

Show one grouped row per episode. Each group contains sub-rows for DE and EN (or however many languages are configured). Title, S/E, Added, and other shared metadata are rendered once per group. Per-language data (status, existing subtitle, searches, actions) is rendered once per sub-row.

---

## Architecture

### 1. Backend — Secondary Sort Key

**File:** `backend/db/repositories/wanted.py`

Append `file_path` as a secondary `ORDER BY` column to the existing wanted query. This guarantees that items for the same episode are always adjacent in the result set, regardless of the primary sort field chosen by the user. One-line change, no new endpoints, no migrations.

### 2. Frontend Types — `WantedGroup`

**File:** `frontend/src/types/wanted.ts`

Add a new interface alongside the existing `WantedItem`:

```typescript
interface WantedGroup {
  key: string              // file_path — stable group identity
  title: string
  season_episode: string
  file_path: string
  item_type: 'episode' | 'movie'
  instance_name?: string
  languages: WantedItem[]  // 1–N items, one per target_language, sorted alpha (de < en)
}
```

### 3. Grouping Logic — `groupByFilePath`

**File:** `frontend/src/pages/Wanted.tsx`

After the existing `flatMap` over all infinite-query pages, call a pure `groupByFilePath(allItems: WantedItem[]): WantedGroup[]` function. Rules:

- Groups preserve the order of first occurrence (server sort order is respected)
- Languages within a group are sorted alphabetically (`de` before `en`)
- Function is pure — recalculates on every render from accumulated pages; React Query memoization prevents unnecessary re-renders

Replace the existing `WantedItem[]` render loop with a `WantedGroup[]` loop.

### 4. New Component — `WantedGroupedRow`

**File:** `frontend/src/pages/wanted/WantedGroupedRow.tsx`

Replaces `WantedTableRow` as the render unit. Layout:

```
╔═══════════════════╤═══╤══════════════════════════════════════════════╗
║ ☐ Kaguya-sama     │S01│ [DE: found  ] ●●○  2  3h ago  [⬇][🔍][▶][👁] ║
║                   │E01│ [EN: wanted ] ●○○  1  1d ago  [🔍][🔍][▶][👁] ║
╠═══════════════════╧═══╧══════════════════════════════════════════════╣
║ ☐ Mushishi        │S01│ [DE: wanted ] ○○○  0  —       [🔍][🔍][▶][👁] ║
║                   │E02│ [EN: ignored] ○○○  0  —       [👁]            ║
╚═══════════════════╧═══╧══════════════════════════════════════════════╝
```

**Shared columns** (rendered once per group, rowspan across sub-rows):
- Checkbox (`selects all item.id`s in the group`)
- Title + instance badge
- S/E (season_episode or "MOVIE")
- Added (earliest `added_at` across all language items in the group)

**Per-language sub-row columns:**
- Language + Status badge (e.g., `[DE: found]`)
- Existing subtitle — `SubtitlePresencePills` (unchanged component)
- Searches count
- Last Search (relative time)
- Action buttons — identical set to current `WantedTableRow`, scoped to the individual `WantedItem`

**Search-results expansion:** Managed per `item.id` as today (`expandedIds: Set<number>`). Expanding one language sub-row pushes subsequent groups down; no structural change needed.

### 5. Batch Selection

`useSelectionStore` and `BatchActionBar` remain unchanged and operate on `item.id` arrays.

- **Group checkbox checked:** all `item.id`s in the group are added to selection
- **Group checkbox unchecked:** all `item.id`s in the group are removed
- **Partial selection (one of two languages):** group checkbox shows indeterminate state

### 6. Virtual Scroll — Variable Row Height

`VirtualWantedTable.tsx` uses React Virtual with a fixed `estimateSize`. Groups have variable height depending on how many language sub-rows they contain (1 language ≈ 48 px, 2 languages ≈ 88 px). Update `estimateSize` to use the average expected height; React Virtual will self-correct via `measureElement`.

---

## Edge Cases

| Case | Behavior |
|------|----------|
| Single-language profile | Group has 1 sub-row; renders like current layout, just wrapped in group structure |
| 3+ language profile | Group renders N sub-rows (one per language). Shared columns use `rowSpan={languages.length}`. No code-level limit — `languages.map()` handles any count |
| Infinite scroll page boundary | `groupByFilePath` recalculates across all accumulated pages; secondary backend sort guarantees pairs are adjacent so no split-group visible to user |
| Empty state / no results | Unchanged — empty `WantedGroup[]` falls through to existing empty-state UI |
| Movie items | `item_type === 'movie'` grouped same way; usually one language per movie but structure handles N |
| Filters (language filter, status filter) | Applied server-side before grouping; a group may show only one sub-row if the other language is filtered out — correct behavior |

---

## Files Changed

| File | Change |
|------|--------|
| `backend/db/repositories/wanted.py` | Add `file_path` secondary ORDER BY |
| `frontend/src/types/wanted.ts` | Add `WantedGroup` interface |
| `frontend/src/pages/Wanted.tsx` | Add `groupByFilePath`, switch render loop to groups |
| `frontend/src/pages/wanted/WantedGroupedRow.tsx` | **New** — grouped row component |
| `frontend/src/pages/wanted/WantedTableRow.tsx` | Keep as-is — action button JSX is extracted into a shared `WantedRowActions` helper and reused by `WantedGroupedRow` per sub-row |

---

## Out of Scope

- No new API endpoints
- No database migrations
- No changes to filter/sort logic
- No changes to `WantedFilterPanel`, `WantedToolbar`, any mutations, WebSocket handlers, or `BatchActionBar`
- No deploy — local implementation only
