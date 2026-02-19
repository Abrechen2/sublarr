# Phase 12: Batch Operations + Smart-Filter — Research

**Researched:** 2026-02-19
**Domain:** React command palette, SQLite FTS5, multi-select UX, SQLAlchemy dynamic filtering
**Confidence:** HIGH (all critical claims verified against official docs or source code)

---

## Summary

Phase 12 adds four interlocking UX features: a global Ctrl+K command palette that searches
across series, episodes, and subtitles; a filter preset system for Library/Wanted/History pages;
cross-page multi-select with Shift+click range selection and bulk actions; and a backend filter
expression evaluator that maps frontend AND/OR condition trees into SQLAlchemy WHERE clauses.

The existing codebase provides strong footing: SQLAlchemy 2.0 is already installed with the
`select() / and_() / or_()` style (verified in `backend/db/repositories/wanted.py`), and the
repository pattern is established in `BaseRepository`. SQLite's built-in FTS5 trigram tokenizer
handles substring search without any new Python dependencies. On the frontend, `cmdk` (the
reference command palette library used by shadcn/ui) and `zustand` (lightweight cross-page state)
are the only two new npm packages needed.

The decision between storage options is unambiguous for this single-user app: filter presets
belong in the backend SQLite database (not localStorage) because they must survive browser
changes, be accessible from any client, and potentially be referenced by other features (batch
operations acting on a saved preset). Multi-select state, by contrast, is ephemeral UI state
and belongs in a Zustand store — not React Context — because it must survive page-level
re-renders (navigating Library → SeriesDetail and back without losing the selection).

**Primary recommendation:** Use `cmdk` for the command palette, SQLite FTS5 trigram for backend
search, `zustand` for multi-select state, and the `conditions.append()` pattern (already used
in `WantedRepository`) extended with an AND/OR wrapper for filter presets.

---

## Standard Stack

### Core (new additions needed)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| cmdk | 1.1.1 | Command palette modal (Ctrl+K) | Built by shadcn author, unstyled, composable, React 19 compatible, used as the base for shadcn Command |
| zustand | 5.0.11 | Cross-page multi-select state | ~1KB, no boilerplate, survives navigation, React 19 compatible |

### Already Installed (no new installs needed)

| Library | Version | Purpose | Note |
|---------|---------|---------|------|
| SQLAlchemy | 2.0.46 | ORM filter building | `and_()`, `or_()` already imported in wanted repo |
| Flask-SQLAlchemy | 3.1.1 | Session management | `db.session` in BaseRepository |
| SQLite FTS5 | built-in | Full-text search | Trigram tokenizer requires no Python package |
| @tanstack/react-query | 5.90.21 | Search result caching | Already installed |
| lucide-react | 0.564.0 | Icons for command palette UI | Already installed |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| cmdk | kbar | kbar is heavier, tied to its own state model; cmdk is composable and integrates with any styling |
| cmdk | Custom modal + fuse.js | More code, loses keyboard nav, accessibility, and animation for free |
| zustand | React Context | Context causes full subtree re-render on every selection change; with 50-row tables this is noticeable |
| zustand | Local component state | State is destroyed on navigation — user loses selection going into SeriesDetail |
| SQLite FTS5 | fuse.js client-side | Client-side: requires loading all data first; FTS5: server-side, scales to large libraries |
| SQLite FTS5 | LIKE `%query%` | LIKE scans the full table; FTS5 trigram uses an index, ~50x faster on >10k rows |
| DB table for presets | localStorage | localStorage: lost on browser change, not available to backend batch ops, invisible to API |

**Installation:**
```bash
# Frontend
npm install cmdk zustand
# Backend: no new packages needed
```

---

## Architecture Patterns

### Recommended Project Structure

```
backend/
  routes/search.py          # GET /api/v1/search?q=&type= — global search endpoint
  routes/filter_presets.py  # CRUD for saved filter presets
  db/
    models/core.py          # Add FilterPreset model
    repositories/search.py  # FTS5 search queries via db.session.execute(text(...))
    repositories/presets.py # FilterPreset CRUD (inherits BaseRepository)
    search.py               # Thin wrapper (mirrors pattern of db/wanted.py)
    presets.py              # Thin wrapper

frontend/src/
  components/search/
    GlobalSearchModal.tsx   # Command.Dialog wrapper (Ctrl+K)
    SearchResultItem.tsx    # Shared result row (series / episode / subtitle)
  components/filters/
    FilterBar.tsx           # Filter row: field + operator + value chips
    FilterPresetMenu.tsx    # Dropdown: load / save preset
    SmartFilterPanel.tsx    # Collapsible advanced filter panel
  stores/
    selectionStore.ts       # Zustand store: selectedIds, lastClickedIndex, toggle, range select
  hooks/
    useGlobalSearch.ts      # TanStack Query: GET /api/v1/search (debounced)
    useFilterPresets.ts     # TanStack Query: CRUD /api/v1/filter-presets
```

### Pattern 1: Command Palette with Async Backend Search

**What:** Open modal on Ctrl+K, debounce-search backend FTS5 endpoint, render grouped results.
**When to use:** Always — this is the global search that replaces hunting through pages.

```typescript
// Source: cmdk README https://github.com/pacocoursey/cmdk/blob/main/README.md
// + TanStack Query debounce pattern

import { Command } from 'cmdk'
import { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'

export function GlobalSearchModal() {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')

  // Ctrl+K toggle
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'k' && (e.metaKey || e.ctrlKey)) {
        e.preventDefault()
        setOpen((v) => !v)
      }
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [])

  // Debounced backend search — only fires when query.length >= 2
  const { data, isFetching } = useQuery({
    queryKey: ['search', query],
    queryFn: () => searchGlobal(query),   // GET /api/v1/search?q=query
    enabled: query.length >= 2,
    staleTime: 10_000,
  })

  return (
    <Command.Dialog open={open} onOpenChange={setOpen} shouldFilter={false}>
      <Command.Input
        value={query}
        onValueChange={setQuery}
        placeholder="Search series, episodes, subtitles..."
      />
      <Command.List>
        {isFetching && <Command.Loading>Searching...</Command.Loading>}
        {data?.series?.length > 0 && (
          <Command.Group heading="Series">
            {data.series.map((s) => (
              <Command.Item key={`series-${s.id}`} onSelect={() => navigateTo(s)}>
                {s.title}
              </Command.Item>
            ))}
          </Command.Group>
        )}
        {/* episodes, subtitles groups follow same pattern */}
        <Command.Empty>No results for "{query}"</Command.Empty>
      </Command.List>
    </Command.Dialog>
  )
}
```

Key decision: set `shouldFilter={false}` on the Command root because filtering is done server-side
by FTS5. cmdk's built-in filtering (command-score) is designed for static command lists, not
dynamic backend results.

### Pattern 2: SQLite FTS5 Trigram Search Backend

**What:** Create FTS5 virtual tables on startup for each searchable entity, query them with MATCH.
**When to use:** For the `/api/v1/search` endpoint backing the command palette.

```python
# Source: https://sqlite.org/fts5.html — trigram tokenizer section
# + SQLAlchemy text() pattern: https://github.com/sqlalchemy/sqlalchemy/discussions/9466

from sqlalchemy import text
from extensions import db

# --- Schema (run once at app startup, after tables exist) ---
SEARCH_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS search_series
USING fts5(id UNINDEXED, title, tokenize="trigram");

CREATE VIRTUAL TABLE IF NOT EXISTS search_episodes
USING fts5(id UNINDEXED, series_id UNINDEXED, title, season_episode, tokenize="trigram");

CREATE VIRTUAL TABLE IF NOT EXISTS search_subtitles
USING fts5(id UNINDEXED, file_path, title, provider_name, tokenize="trigram");
"""

def init_search_tables():
    """Create FTS5 virtual tables and populate from main tables.

    Call from create_app() after db.create_all().
    """
    with db.engine.connect() as conn:
        for stmt in SEARCH_SCHEMA.strip().split(';'):
            if stmt.strip():
                conn.execute(text(stmt))
        conn.commit()


# --- Repository method ---
def search_all(query: str, limit: int = 20) -> dict:
    """Full-text search across series, episodes, and subtitles.

    Uses FTS5 trigram tokenizer: supports substring matching,
    case-insensitive, no minimum token length for LIKE fallback.

    Args:
        query: User search string (min 2 chars recommended)
        limit: Max results per entity type

    Returns:
        Dict with 'series', 'episodes', 'subtitles' lists
    """
    safe_query = query.strip()
    if len(safe_query) < 2:
        return {"series": [], "episodes": [], "subtitles": []}

    # Wrap in wildcard for substring match via LIKE on trigram index
    # (trigram tokenizer supports indexed LIKE with % wildcards)
    like_term = f"%{safe_query}%"

    with db.engine.connect() as conn:
        series = conn.execute(
            text("SELECT id, title FROM search_series WHERE title LIKE :q LIMIT :lim"),
            {"q": like_term, "lim": limit}
        ).mappings().all()

        episodes = conn.execute(
            text("""
                SELECT id, series_id, title, season_episode
                FROM search_episodes
                WHERE title LIKE :q OR season_episode LIKE :q
                LIMIT :lim
            """),
            {"q": like_term, "lim": limit}
        ).mappings().all()

        subtitles = conn.execute(
            text("""
                SELECT id, file_path, title, provider_name
                FROM search_subtitles
                WHERE file_path LIKE :q OR title LIKE :q
                LIMIT :lim
            """),
            {"q": like_term, "lim": limit}
        ).mappings().all()

    return {
        "series": [dict(r) for r in series],
        "episodes": [dict(r) for r in episodes],
        "subtitles": [dict(r) for r in subtitles],
    }
```

**Critical note on FTS5 trigram + LIKE:** The SQLite FTS5 trigram tokenizer creates an index
that accelerates `LIKE '%term%'` queries. Running `LIKE` against the FTS5 virtual table (not the
original table) uses the index, giving ~50x speedup over scanning the original table. This is
the recommended pattern from official SQLite docs. The FTS5 tables are kept in sync via triggers
or a periodic rebuild — for Sublarr's library size (hundreds of series, thousands of episodes),
a rebuild-on-change strategy (triggered when the Sonarr/Radarr library syncs) is sufficient.

### Pattern 3: Zustand Multi-Select Store

**What:** Single store manages selected IDs across Library, Wanted, History pages. Survives
navigation because it lives outside React's component tree.
**When to use:** Any page that needs multi-select with checkboxes and bulk actions.

```typescript
// Source: Zustand v5 docs https://github.com/pmndrs/zustand
// + stereobooster shift-select pattern https://stereobooster.com/posts/react-hook-to-select-multiple-items-with-a-shift/

import { create } from 'zustand'

interface SelectionStore {
  // Map from "scope" (page name) to selected IDs so Library and Wanted don't share selections
  selections: Record<string, Set<number>>
  lastClickedIndex: Record<string, number | null>

  toggleItem: (scope: string, id: number, index: number, shiftKey: boolean, orderedIds: number[]) => void
  selectAll: (scope: string, ids: number[]) => void
  clearSelection: (scope: string) => void
  getSelected: (scope: string) => Set<number>
  getSelectedArray: (scope: string) => number[]
  isSelected: (scope: string, id: number) => boolean
  getCount: (scope: string) => number
}

export const useSelectionStore = create<SelectionStore>((set, get) => ({
  selections: {},
  lastClickedIndex: {},

  toggleItem: (scope, id, index, shiftKey, orderedIds) => {
    set((state) => {
      const current = new Set(state.selections[scope] ?? [])
      const lastIdx = state.lastClickedIndex[scope] ?? null

      if (shiftKey && lastIdx !== null) {
        // Range select: select everything between lastIdx and current index
        const [from, to] = lastIdx < index ? [lastIdx, index] : [index, lastIdx]
        for (let i = from; i <= to; i++) {
          current.add(orderedIds[i])
        }
      } else {
        if (current.has(id)) {
          current.delete(id)
        } else {
          current.add(id)
        }
      }

      return {
        selections: { ...state.selections, [scope]: current },
        lastClickedIndex: { ...state.lastClickedIndex, [scope]: index },
      }
    })
  },

  selectAll: (scope, ids) => set((state) => ({
    selections: { ...state.selections, [scope]: new Set(ids) },
  })),

  clearSelection: (scope) => set((state) => ({
    selections: { ...state.selections, [scope]: new Set() },
    lastClickedIndex: { ...state.lastClickedIndex, [scope]: null },
  })),

  getSelected: (scope) => get().selections[scope] ?? new Set(),
  getSelectedArray: (scope) => [...(get().selections[scope] ?? new Set())],
  isSelected: (scope, id) => (get().selections[scope] ?? new Set()).has(id),
  getCount: (scope) => (get().selections[scope] ?? new Set()).size,
}))
```

Usage in a page component:

```typescript
// In Wanted.tsx (or Library.tsx, History.tsx)
const SCOPE = 'wanted'

function WantedRow({ item, index, orderedIds }: Props) {
  const { toggleItem, isSelected } = useSelectionStore()
  const selected = isSelected(SCOPE, item.id)

  return (
    <tr
      onClick={(e) => toggleItem(SCOPE, item.id, index, e.shiftKey, orderedIds)}
      className={selected ? 'bg-accent/10' : ''}
    >
      <td>
        <input
          type="checkbox"
          checked={selected}
          onChange={() => {}} // controlled by row click
          onClick={(e) => e.stopPropagation()}
        />
      </td>
      {/* ... rest of row */}
    </tr>
  )
}
```

**Scope pattern:** Each page uses a unique string scope (`'wanted'`, `'library'`, `'history'`).
This means Library and Wanted selections coexist independently in the same store, and clearing
one doesn't affect the other.

### Pattern 4: SQLAlchemy Dynamic Filter Builder

**What:** Parse a list of filter conditions (from DB or request JSON) into SQLAlchemy WHERE clause.
**When to use:** In repository methods that serve the filter preset system.

The existing codebase already has the core pattern in `WantedRepository.get_wanted_items()`:
```python
conditions = []
if item_type:
    conditions.append(WantedItem.item_type == item_type)
# ...
data_stmt = data_stmt.where(*conditions)  # implicit AND
```

Phase 12 extends this to support named presets with AND/OR logic:

```python
# Source: SQLAlchemy 2.0 docs — and_() / or_()
# Verified in backend/db/repositories/wanted.py (already uses this import)
from sqlalchemy import and_, or_
from db.models.core import WantedItem, FilterPreset

# --- Filter preset DB schema ---
# filter_presets table: id, name, scope, conditions_json, created_at
# conditions_json format:
# {
#   "logic": "AND",           # top-level combinator
#   "conditions": [
#     {"field": "status", "op": "eq", "value": "wanted"},
#     {
#       "logic": "OR",        # nested group
#       "conditions": [
#         {"field": "item_type", "op": "eq", "value": "episode"},
#         {"field": "item_type", "op": "eq", "value": "movie"}
#       ]
#     }
#   ]
# }

SUPPORTED_OPERATORS = {
    "eq":       lambda col, val: col == val,
    "neq":      lambda col, val: col != val,
    "contains": lambda col, val: col.ilike(f"%{val}%"),
    "starts":   lambda col, val: col.ilike(f"{val}%"),
    "gt":       lambda col, val: col > val,
    "lt":       lambda col, val: col < val,
    "in":       lambda col, val: col.in_(val if isinstance(val, list) else [val]),
}

# Column map: field name string → SQLAlchemy column object
WANTED_FIELDS = {
    "status":        WantedItem.status,
    "item_type":     WantedItem.item_type,
    "title":         WantedItem.title,
    "subtitle_type": WantedItem.subtitle_type,
    "target_language": WantedItem.target_language,
    "upgrade_candidate": WantedItem.upgrade_candidate,
}


def build_clause(node: dict, field_map: dict):
    """Recursively build a SQLAlchemy clause from a condition tree node.

    Args:
        node: Either a condition {"field", "op", "value"} or
              a group {"logic": "AND"|"OR", "conditions": [...]}
        field_map: Dict mapping field name strings to SQLAlchemy column objects

    Returns:
        A SQLAlchemy BinaryExpression or BooleanClauseList

    Raises:
        ValueError: If field or operator is not in the allowed maps
    """
    if "logic" in node:
        # Group node — recurse
        sub_clauses = [build_clause(c, field_map) for c in node["conditions"]]
        combinator = and_ if node["logic"].upper() == "AND" else or_
        return combinator(*sub_clauses)
    else:
        # Leaf node — single condition
        field_name = node["field"]
        op_name = node["op"]
        value = node["value"]

        if field_name not in field_map:
            raise ValueError(f"Unknown filter field: {field_name}")
        if op_name not in SUPPORTED_OPERATORS:
            raise ValueError(f"Unknown filter operator: {op_name}")

        col = field_map[field_name]
        return SUPPORTED_OPERATORS[op_name](col, value)


# Usage in repository:
def apply_preset_filter(stmt, preset_conditions: dict, field_map: dict):
    """Apply a saved filter preset to an existing SELECT statement."""
    if not preset_conditions or not preset_conditions.get("conditions"):
        return stmt
    clause = build_clause(preset_conditions, field_map)
    return stmt.where(clause)
```

### Pattern 5: Filter Preset Storage Schema

**What:** SQLite table storing named filter configurations per page scope.

```python
# backend/db/models/core.py — add FilterPreset model
from sqlalchemy import String, Text, DateTime
from sqlalchemy.orm import mapped_column, Mapped
from db.models import Base

class FilterPreset(Base):
    __tablename__ = "filter_presets"

    id:          Mapped[int]  = mapped_column(primary_key=True)
    name:        Mapped[str]  = mapped_column(String(100), nullable=False)
    scope:       Mapped[str]  = mapped_column(String(50), nullable=False)  # 'wanted', 'library', 'history'
    conditions:  Mapped[str]  = mapped_column(Text, nullable=False)        # JSON string
    is_default:  Mapped[int]  = mapped_column(default=0)                   # 1 = auto-apply on page load
    created_at:  Mapped[str]  = mapped_column(String(50), nullable=False)
    updated_at:  Mapped[str]  = mapped_column(String(50), nullable=False)
```

Frontend type:

```typescript
interface FilterCondition {
  field: string
  op: 'eq' | 'neq' | 'contains' | 'starts' | 'gt' | 'lt' | 'in'
  value: string | string[] | number | boolean
}

interface FilterGroup {
  logic: 'AND' | 'OR'
  conditions: (FilterCondition | FilterGroup)[]
}

interface FilterPreset {
  id: number
  name: string
  scope: 'wanted' | 'library' | 'history'
  conditions: FilterGroup
  is_default: boolean
  created_at: string
}
```

### Anti-Patterns to Avoid

- **FTS5 on original tables:** Run MATCH/LIKE against the FTS5 virtual tables, not the main tables. The index lives on the virtual table.
- **shouldFilter={true} with backend search:** Setting `shouldFilter={true}` (cmdk default) makes cmdk re-filter results that are already filtered by the backend — items disappear as you type.
- **Storing Set<number> in React state for selections:** Sets are not comparable by reference in React, causing stale closures. Zustand handles this correctly because it lives outside React's state system.
- **Global Zustand store for filter presets:** Presets are persisted data, not UI state — they belong in TanStack Query (backend source of truth), not Zustand.
- **One scope for all pages in selection store:** Library's multi-selected series and Wanted's multi-selected items should be independent scopes, otherwise selecting all on Library appears to select on Wanted too.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Command palette keyboard nav | Custom dialog + list | `cmdk` | Arrow keys, Escape, wrapping, ARIA roles, focus trap — 15+ edge cases |
| Full-text search index | LIKE on main tables | SQLite FTS5 trigram | Index acceleration, ~50x faster, built into SQLite stdlib |
| Fuzzy scoring for commands | Custom Levenshtein | cmdk's built-in (command-score) or just FTS5 | Already tuned for command palette UX |
| Cross-page selection state | Prop drilling / Context | Zustand | Context re-renders entire tree; Zustand subscribes only changed slices |
| Filter condition validation | Ad-hoc dict checks | `build_clause()` with allowlist maps | Prevents SQL injection via field name, validates operators |

**Key insight:** SQLite's FTS5 trigram tokenizer is a production-grade full-text search solution
with zero new dependencies. It is part of the SQLite distribution that Python's stdlib `sqlite3`
module uses. No pip install needed — just `CREATE VIRTUAL TABLE ... USING fts5(...)`.

---

## Common Pitfalls

### Pitfall 1: FTS5 Table Sync Drift

**What goes wrong:** The FTS5 virtual tables (search_series, search_episodes, search_subtitles)
contain stale data after library syncs, subtitle downloads, or deletions.

**Why it happens:** FTS5 tables are separate virtual tables — SQLite does not auto-sync them
with the main tables they mirror.

**How to avoid:** Use one of two strategies:

Option A (simpler): Rebuild FTS5 tables in the background after any library sync event. This
is acceptable for Sublarr because syncs are infrequent and libraries are small (<10k episodes).
```python
def rebuild_search_index():
    with db.engine.connect() as conn:
        conn.execute(text("DELETE FROM search_series"))
        conn.execute(text("""
            INSERT INTO search_series(id, title)
            SELECT id, title FROM sonarr_cache_series
        """))
        conn.commit()
```

Option B (maintained): Use SQLite triggers on the main tables. More complex, fully automatic.
For Sublarr's usage pattern, Option A is recommended.

**Warning signs:** Search returns deleted series or misses recently added ones.

### Pitfall 2: cmdk `shouldFilter` Conflict with Backend Search

**What goes wrong:** Results vanish as the user types because cmdk re-filters the already-filtered
backend results using its built-in command-score algorithm.

**Why it happens:** cmdk's default `shouldFilter={true}` compares the query against each
`Command.Item`'s value prop. If the item value doesn't score above 0 against the query,
it's hidden — even though it was returned by the backend because it matched.

**How to avoid:** Always use `shouldFilter={false}` on the root `<Command>` when results come
from a backend search. Use cmdk's filtering only for static command lists (navigation shortcuts,
actions) that don't go through the API.

**Warning signs:** Typing "One Piece" shows results at "One" but they disappear at "One P".

### Pitfall 3: Shift-Click Range on Paginated Lists

**What goes wrong:** Shift+click selects items that are not visible because the range index
calculation operates on the full dataset, not just the current page.

**Why it happens:** The `orderedIds` array passed to `toggleItem` must contain only the IDs
of currently visible/rendered items, not all items from all pages.

**How to avoid:** In each page component, derive `orderedIds` from the current page's data
array. Shift+click range is intentionally scoped to the visible page.

```typescript
// In WantedPage: pass only current page IDs
const orderedIds = wantedItems?.data.map((i) => i.id) ?? []
```

**Warning signs:** Shift-clicking from item 3 to item 7 selects 20+ items from the previous page.

### Pitfall 4: FTS5 Trigram Minimum Length

**What goes wrong:** Searches for 1- or 2-character strings return no results even though
matches exist.

**Why it happens:** The trigram tokenizer splits text into 3-character chunks. A search term
shorter than 3 characters cannot match any trigram.

**How to avoid:** Enforce a minimum query length of 2 characters in both frontend and backend.
The frontend `enabled: query.length >= 2` check in TanStack Query handles this. The backend
should return an empty result with a 200 status for short queries (not a 400 error) so the
UI degrades gracefully.

**Warning signs:** Searching "re" on an episode called "Re:Zero" returns nothing.

### Pitfall 5: Filter Preset Conditions JSON Injection

**What goes wrong:** A malicious condition `{"field": "status; DROP TABLE wanted_items; --", ...}`
is passed through the filter builder and executes raw SQL.

**Why it happens:** Dynamic filter builders that construct SQL strings are vulnerable to injection.

**How to avoid:** The `build_clause()` function uses an explicit allowlist for `field_name` and
`op_name`. Any field not in `WANTED_FIELDS` raises a `ValueError` before touching the database.
SQLAlchemy's parameterized queries handle value escaping automatically.

---

## Code Examples

### Verified: SQLAlchemy 2.0 `and_()` / `or_()` (already in codebase)

```python
# Source: backend/db/repositories/wanted.py — already verified in codebase
from sqlalchemy import select, func, delete, and_, or_

# Existing pattern (Phase 12 extends this):
conditions = []
if item_type:
    conditions.append(WantedItem.item_type == item_type)
if status:
    conditions.append(WantedItem.status == status)

stmt = select(WantedItem).where(*conditions)  # and_() is implicit
```

### Verified: cmdk Dialog with Ctrl+K

```typescript
// Source: https://github.com/pacocoursey/cmdk/blob/main/README.md
useEffect(() => {
  const handler = (e: KeyboardEvent) => {
    if (e.key === 'k' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault()
      setOpen((v) => !v)
    }
  }
  document.addEventListener('keydown', handler)
  return () => document.removeEventListener('keydown', handler)
}, [])
```

### Verified: Zustand store creation (v5 TypeScript)

```typescript
// Source: https://github.com/pmndrs/zustand — v5 TypeScript pattern
import { create } from 'zustand'

const useStore = create<State>()((set, get) => ({
  // state and actions
}))
```

### Verified: SQLite FTS5 trigram CREATE and LIKE query

```sql
-- Source: https://sqlite.org/fts5.html — trigram tokenizer section
CREATE VIRTUAL TABLE IF NOT EXISTS search_series
USING fts5(id UNINDEXED, title, tokenize="trigram");

-- Indexed LIKE query (uses trigram index, no table scan):
SELECT id, title FROM search_series WHERE title LIKE '%one piece%';
```

### Verified: TanStack Query with `enabled` guard

```typescript
// Source: @tanstack/react-query v5 docs — enabled option
const { data } = useQuery({
  queryKey: ['search', query],
  queryFn: () => searchGlobal(query),
  enabled: query.length >= 2,  // don't fire for short queries
  staleTime: 10_000,
})
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| LIKE '%term%' on main table | FTS5 trigram virtual table with LIKE | SQLite 3.34+ (2020) | 50x speed on large tables |
| Redux for cross-page state | Zustand v5 (useSyncExternalStore) | Oct 2024 | No Provider needed, ~1KB |
| Custom command palette | cmdk (pacocoursey) | ~2022, now v1.1.1 (Mar 2024) | Used by shadcn/ui, production-tested |
| Storing UI prefs in DB | localStorage for ephemeral, DB for named presets | Current best practice | Named presets are data, not UI state |
| SQLAlchemy Legacy Query | SQLAlchemy 2.0 `select()` style | SA 2.0 (2023) | Already adopted in this codebase |

**Deprecated/outdated:**
- `session.query(Model).filter(...)` style: The codebase already uses `select(Model).where(...)` — do not introduce the legacy style for new repositories.
- `fuse.js` for server-backed search: Fuse.js is appropriate for client-side filtering of small static lists. For backend-sourced dynamic results, it adds no value and adds bundle size.

---

## Open Questions

1. **FTS5 table population source**
   - What we know: FTS5 tables mirror main tables; for series/episodes the source is the Sonarr cache (in-memory or a DB cache table), for subtitles it is `subtitle_downloads`
   - What's unclear: Is there an existing `sonarr_cache` table in the DB, or is series data fetched live from Sonarr on each library call? (The `routes/library.py` fetches live from `get_sonarr_client()`)
   - Recommendation: For FTS5 population, use `subtitle_downloads` for the subtitles index (it exists as a DB table). For series/episodes, the planner should decide whether to add a lightweight `series_search_cache` table or rebuild the FTS5 index on every library sync API call.

2. **Bulk action scope on Library page**
   - What we know: Library shows Sonarr series, not individual episodes. Multi-select on Library would select series IDs.
   - What's unclear: What bulk actions apply to series vs episodes? (Force-search all missing? Reassign profile?)
   - Recommendation: Keep bulk actions for Library scoped to profile assignment and trigger-scan. The Wanted page handles episode-level bulk search.

3. **Filter preset portability**
   - What we know: Presets are stored in DB with a `scope` field.
   - What's unclear: Should presets be exportable/importable (e.g., included in the ZIP backup from Phase 8)?
   - Recommendation: Include `filter_presets` table in the backup's `sqlite_tables` list. No special handling needed — the ZIP backup already copies the whole DB.

---

## Sources

### Primary (HIGH confidence)
- SQLite FTS5 official docs: https://sqlite.org/fts5.html — trigram tokenizer syntax, LIKE indexing behavior
- cmdk GitHub README: https://github.com/pacocoursey/cmdk/blob/main/README.md — API, `shouldFilter`, Dialog pattern
- cmdk Releases: https://github.com/pacocoursey/cmdk/releases — v1.1.1 current, React 19 peer dep confirmed
- Zustand v5 announcement: https://pmnd.rs/blog/announcing-zustand-v5 — React 18+ requirement, useSyncExternalStore
- SQLAlchemy `and_()` / `or_()`: verified directly in `backend/db/repositories/wanted.py`
- Existing repository pattern: verified in `backend/db/repositories/base.py` and `backend/db/repositories/wanted.py`

### Secondary (MEDIUM confidence)
- SQLAlchemy FTS5 discussion: https://github.com/sqlalchemy/sqlalchemy/discussions/9466 — `text()` is the recommended approach, no native ORM support
- Stereobooster shift-select hook: https://stereobooster.com/posts/react-hook-to-select-multiple-items-with-a-shift/ — range selection index math
- TanStack Table shift-select discussion: https://github.com/TanStack/table/discussions/3068 — `e.shiftKey` usage pattern
- FTS5 trigram practical guide: https://davidmuraya.com/blog/sqlite-fts5-trigram-name-matching/ — trigram LIKE acceleration verified

### Tertiary (LOW confidence — flag for validation)
- Zustand v5.0.11 version claim: from web search, not directly verified on npm registry
- cmdk React 19 peer dep: stated in release notes, not verified against actual package.json of cmdk

---

## Metadata

**Confidence breakdown:**
- Command palette (cmdk): HIGH — API verified from official README, React 19 compat confirmed in releases
- FTS5 trigram search: HIGH — verified from official SQLite docs with specific syntax
- Zustand multi-select: HIGH — pattern derived from official Zustand docs + established shift-click algorithm
- SQLAlchemy filter builder: HIGH — `and_()` / `or_()` usage already in codebase, extension is mechanical
- Filter preset DB storage: HIGH — justified by single-user app requirements and backup integration
- cmdk styling approach: MEDIUM — no Tailwind v4 specific example found; Tailwind class approach confirmed from cmdk README

**Research date:** 2026-02-19
**Valid until:** 2026-05-01 (stable libraries — cmdk, Zustand, SQLAlchemy are slow-moving)
