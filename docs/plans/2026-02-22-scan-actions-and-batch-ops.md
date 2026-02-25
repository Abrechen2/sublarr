# Scan Actions & Batch Operations Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add auto-extract-on-scan settings and batch action toolbars to SeriesDetail and Library pages.

**Architecture:** Three independent tracks — (A) backend config + scanner auto-extract, (B) new batch-extract endpoint + extended batch-search, (C) frontend checkboxes + floating batch toolbars.

**Tech Stack:** Python/Flask backend, React 19 + TypeScript frontend, SQLite (dev) / PostgreSQL (prod).

---

### Task 1: Backend Config — Auto-Scan Settings

**Files:**
- Modify: `backend/config.py`

**Step 1: Read `backend/config.py`**

Find the `wanted_scan_on_startup` or `wanted_scan_interval_hours` field in the Settings class.

**Step 2: Add new fields immediately after the wanted-scan block**

```python
scan_auto_extract: bool = Field(default=False, description="Auto-extract embedded subs during wanted scan")
scan_auto_translate: bool = Field(default=False, description="Auto-translate after auto-extract during wanted scan")
```

**Step 3: Verify startup**

Run: `cd backend && python -c "from config import get_settings; s = get_settings(); print(s.scan_auto_extract, s.scan_auto_translate)"`
Expected: `False False`

**Step 4: Commit**

```bash
git add backend/config.py
git commit -m "feat: add scan_auto_extract and scan_auto_translate settings"
```

---

### Task 2: Backend Scanner — Auto-Extract on Scan

**Files:**
- Modify: `backend/wanted_scanner.py`

**Context:** The scanner calls `upsert_wanted_item(...)` with `existing_sub="embedded_ass"` or `"embedded_srt"` when it detects embedded streams but never extracts. We want optional immediate extraction.

**Step 1: Read `backend/wanted_scanner.py` lines 330-620**

Understand where `upsert_wanted_item` is called after detecting `embedded_ass`/`embedded_srt`.

**Step 2: Add `_maybe_auto_extract` helper method**

After the `_batch_probe` method, add:

```python
def _maybe_auto_extract(self, item_id: int, file_path: str) -> None:
    """Trigger embedded subtitle extraction if scan_auto_extract is enabled."""
    try:
        settings = get_settings()
        if not getattr(settings, "scan_auto_extract", False):
            return
        from routes.wanted import _extract_embedded_sub
        auto_translate = getattr(settings, "scan_auto_translate", False)
        logger.info(f"[Auto-Extract] item {item_id} -> {file_path}")
        _extract_embedded_sub(item_id, file_path, auto_translate=auto_translate)
    except Exception as exc:
        logger.warning(f"[Auto-Extract] Failed for item {item_id}: {exc}")
```

**Step 3: Call helper after embedded-sub detection**

Find the `upsert_wanted_item` calls that set `existing_sub` to `"embedded_ass"` or `"embedded_srt"`. After each such call that returns a new item_id (not an update of an already-existing item), call:

```python
self._maybe_auto_extract(item_id, file_path)
```

Only auto-extract for newly created items (check that `existing_sub` was previously empty/None before the upsert).

**Step 4: Verify import**

Run: `cd backend && python -c "from wanted_scanner import WantedScanner; print('OK')"`
Expected: `OK`

**Step 5: Commit**

```bash
git add backend/wanted_scanner.py
git commit -m "feat: auto-extract embedded subs on scan when scan_auto_extract=True"
```

---

### Task 3: Backend Routes — POST /wanted/batch-extract

**Files:**
- Modify: `backend/routes/wanted.py`

**Context:** `POST /api/v1/wanted/<id>/extract` handles single extraction. Add `POST /api/v1/wanted/batch-extract` for multi-item extraction. Register this route BEFORE the `/<int:item_id>/` wildcard routes.

**Step 1: Read `backend/routes/wanted.py` lines 640-780 and 900-1040**

Understand `_extract_embedded_sub()` helper signature and the `batch_action` endpoint pattern.

**Step 2: Add batch-extract endpoint**

Insert BEFORE the first `/<int:item_id>/` route:

```python
@wanted_bp.route("/batch-extract", methods=["POST"])
def batch_extract():
    """Extract embedded subtitles for multiple wanted items in background threads."""
    data = request.get_json(force=True, silent=True) or {}
    item_ids = data.get("item_ids", [])
    auto_translate = bool(data.get("auto_translate", False))
    if not item_ids:
        return jsonify({"error": "item_ids required"}), 400

    job_ids = []
    for item_id in item_ids:
        with _db_lock:
            conn = get_db()
            row = conn.execute(
                "SELECT id, file_path FROM wanted_items WHERE id = ?", (item_id,)
            ).fetchone()
        if row:
            job_id = _extract_embedded_sub(row["id"], row["file_path"], auto_translate=auto_translate)
            if job_id:
                job_ids.append(job_id)

    return jsonify({"job_ids": job_ids, "queued": len(job_ids)})
```

**Step 3: Smoke-test**

```bash
curl -s -X POST http://localhost:5765/api/v1/wanted/batch-extract \
  -H "Content-Type: application/json" \
  -d '{"item_ids": [999999]}' | python3 -m json.tool
```
Expected: `{"job_ids": [], "queued": 0}`

**Step 4: Commit**

```bash
git add backend/routes/wanted.py
git commit -m "feat: add POST /wanted/batch-extract endpoint"
```

---

### Task 4: Backend Routes — Extend batch-search for series_ids

**Files:**
- Modify: `backend/routes/wanted.py`

**Context:** `POST /api/v1/wanted/batch-search` already handles `item_ids` array or single `series_id`. Add support for `series_ids: list[int]` to allow the Library page to trigger batch search across multiple series.

**Step 1: Read lines 455-568 in `backend/routes/wanted.py`**

Find the `batch_search()` function. Locate where `item_ids` is populated from `series_id`.

**Step 2: Add series_ids branch**

After the `if series_id:` branch, add:

```python
series_ids = data.get("series_ids", [])
if series_ids and not item_ids:
    with _db_lock:
        conn = get_db()
        placeholders = ",".join("?" * len(series_ids))
        rows = conn.execute(
            f"SELECT id FROM wanted_items WHERE series_id IN ({placeholders}) "
            f"AND status NOT IN ('downloading', 'translating')",
            series_ids,
        ).fetchall()
    item_ids = [r["id"] for r in rows]
```

**Step 3: Run existing tests**

```bash
cd backend && python -m pytest tests/ -q -x 2>&1 | tail -20
```
Expected: all existing tests pass.

**Step 4: Commit**

```bash
git add backend/routes/wanted.py
git commit -m "feat: batch-search accepts series_ids array for multi-series processing"
```

---

### Task 5: Frontend Settings — Auto-Scan Settings UI

**Files:**
- Modify: `frontend/src/pages/Settings/AdvancedTab.tsx`

**Step 1: Read `frontend/src/pages/Settings/AdvancedTab.tsx` fully**

Find the scanner settings section (search for `wanted_scan_on_startup` or `wanted_anime_only`).

**Step 2: Identify the toggle pattern used in this file**

It will be either a `<ToggleRow>` component or an inline checkbox pattern. Use the SAME pattern.

**Step 3: Add two new toggles after the existing scanner toggles**

```tsx
<ToggleRow
  label={t('settings.advanced.scanAutoExtract') ?? 'Auto-extract embedded subs on scan'}
  description="When scanner detects embedded ASS/SRT streams, extract them automatically"
  value={!!config.scan_auto_extract}
  onChange={(v) => updateConfig('scan_auto_extract', v)}
/>
<ToggleRow
  label={t('settings.advanced.scanAutoTranslate') ?? 'Auto-translate after extraction'}
  description="Immediately translate extracted subtitle (requires auto-extract enabled)"
  value={!!config.scan_auto_translate}
  onChange={(v) => updateConfig('scan_auto_translate', v)}
  disabled={!config.scan_auto_extract}
/>
```

If no `t()` translations exist, omit the `t()` call and use the plain string directly.

**Step 4: Lint check**

```bash
cd frontend && npm run lint 2>&1 | tail -10
```
Expected: 0 errors.

**Step 5: Commit**

```bash
git add frontend/src/pages/Settings/AdvancedTab.tsx
git commit -m "feat: add scan_auto_extract/scan_auto_translate settings UI in AdvancedTab"
```

---

### Task 6: Frontend API Client — New Batch Functions

**Files:**
- Modify: `frontend/src/api/client.ts`

**Step 1: Read `frontend/src/api/client.ts` lines 140-175**

Identify where `startWantedBatchSearch` and `extractEmbeddedSub` are defined.

**Step 2: Add two new exported functions after `startWantedBatchSearch`**

```typescript
/** Extract embedded subtitles for multiple wanted items. */
export async function batchExtractEmbedded(
  itemIds: number[],
  autoTranslate = false,
): Promise<{ job_ids: string[]; queued: number }> {
  const { data } = await api.post('/wanted/batch-extract', {
    item_ids: itemIds,
    auto_translate: autoTranslate,
  })
  return data
}

/** Start batch search across multiple series. */
export async function startSeriesBatchSearch(
  seriesIds: number[],
): Promise<{ queued: number }> {
  const { data } = await api.post('/wanted/batch-search', { series_ids: seriesIds })
  return data
}
```

**Step 3: Type-check**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -30
```
Expected: 0 errors.

**Step 4: Commit**

```bash
git add frontend/src/api/client.ts
git commit -m "feat: add batchExtractEmbedded and startSeriesBatchSearch API functions"
```

---

### Task 7: Frontend SeriesDetail — Episode Checkboxes + Batch Toolbar

**Files:**
- Modify: `frontend/src/pages/SeriesDetail.tsx`

**Context:** The `SeasonGroup` component renders a table of episodes. Each row needs a checkbox. When any episode is selected, a floating batch toolbar appears at the bottom of the season group with Search, Extract, and Clear actions.

**Step 1: Read `frontend/src/pages/SeriesDetail.tsx` lines 540-700**

Understand the `SeasonGroup` component, episode row structure (`<tr>` cells), and how `ep.wanted_id` is used.

**Step 2: Add selection state inside `SeasonGroup`**

At the top of the `SeasonGroup` component function body:

```typescript
const [selectedEpisodes, setSelectedEpisodes] = useState<Set<number>>(new Set())

const toggleEpisode = useCallback((id: number) => {
  setSelectedEpisodes(prev => {
    const next = new Set(prev)
    if (next.has(id)) next.delete(id) else next.add(id)
    return next
  })
}, [])

const allSelectableIds = episodes.map(e => e.wanted_id).filter((id): id is number => id != null)
const selectAll = useCallback(() => setSelectedEpisodes(new Set(allSelectableIds)), [allSelectableIds])
const clearAll = useCallback(() => setSelectedEpisodes(new Set()), [])
```

**Step 3: Add select-all checkbox to table header `<thead>`**

Add a new `<th>` as the FIRST column:

```tsx
<th className="w-8 pl-2">
  <input
    type="checkbox"
    checked={allSelectableIds.length > 0 && selectedEpisodes.size === allSelectableIds.length}
    onChange={() => selectedEpisodes.size === allSelectableIds.length ? clearAll() : selectAll()}
    className="rounded"
    style={{ accentColor: 'var(--accent)' }}
  />
</th>
```

**Step 4: Add checkbox to each episode data row**

Add a new `<td>` as the first cell of each episode row:

```tsx
<td className="w-8 pl-2">
  <input
    type="checkbox"
    checked={ep.wanted_id != null && selectedEpisodes.has(ep.wanted_id)}
    onChange={() => ep.wanted_id != null && toggleEpisode(ep.wanted_id)}
    disabled={ep.wanted_id == null}
    className="rounded"
    style={{ accentColor: 'var(--accent)' }}
  />
</td>
```

**Step 5: Add batch toolbar after the `</table>` closing tag**

```tsx
{selectedEpisodes.size > 0 && (
  <div
    className="flex items-center gap-2 px-3 py-2 rounded-lg mt-1 mx-1"
    style={{
      backgroundColor: 'var(--bg-elevated)',
      border: '1px solid var(--accent-dim)',
    }}
  >
    <span className="text-xs font-medium mr-2" style={{ color: 'var(--accent)' }}>
      {selectedEpisodes.size} selected
    </span>
    <button
      onClick={() => { startWantedBatchSearch({ item_ids: [...selectedEpisodes] }); clearAll() }}
      className="px-3 py-1 rounded text-xs font-medium"
      style={{ backgroundColor: 'var(--accent-bg)', color: 'var(--accent)', border: '1px solid var(--accent-dim)' }}
    >
      Search
    </button>
    <button
      onClick={() => { batchExtractEmbedded([...selectedEpisodes]); clearAll() }}
      className="px-3 py-1 rounded text-xs font-medium"
      style={{ backgroundColor: 'var(--bg-surface)', color: 'var(--text-secondary)', border: '1px solid var(--border)' }}
    >
      Extract
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

**Step 6: Add missing imports at the top of the file**

```typescript
import { batchExtractEmbedded } from '@/api/client'
// startWantedBatchSearch should already be imported — verify
```

**Step 7: Lint + type-check**

```bash
cd frontend && npm run lint 2>&1 | tail -10 && npx tsc --noEmit 2>&1 | head -20
```
Expected: 0 errors.

**Step 8: Commit**

```bash
git add frontend/src/pages/SeriesDetail.tsx
git commit -m "feat: add episode checkboxes and batch toolbar to SeriesDetail"
```

---

### Task 8: Frontend Library — Series Checkboxes + Batch Toolbar

**Files:**
- Modify: `frontend/src/pages/Library.tsx`

**Context:** The Library table has one row per series (`LibraryTableRow`). Add checkboxes to select multiple series. When any series is checked, show a batch toolbar with "Search All Missing" action.

**Step 1: Read `frontend/src/pages/Library.tsx` lines 72-200 and 250-400**

Understand `LibraryTableRow` component props and where the table header (`<thead>`) is rendered.

**Step 2: Add selection state to the Library page component**

Near the top of the Library component (with other `useState` calls):

```typescript
const [selectedSeries, setSelectedSeries] = useState<Set<number>>(new Set())

const toggleSeries = useCallback((id: number) => {
  setSelectedSeries(prev => {
    const next = new Set(prev)
    if (next.has(id)) next.delete(id) else next.add(id)
    return next
  })
}, [])

const clearSelection = useCallback(() => setSelectedSeries(new Set()), [])
```

**Step 3: Add `selected` + `onToggle` props to `LibraryTableRow`**

In the `LibraryTableRowProps` interface, add:
```typescript
selected: boolean
onToggle: () => void
```

In the `LibraryTableRow` component, add a checkbox as the first `<td>`:

```tsx
<td className="w-10 pl-3">
  <input
    type="checkbox"
    checked={selected}
    onChange={onToggle}
    className="rounded"
    style={{ accentColor: 'var(--accent)' }}
  />
</td>
```

**Step 4: Add select-all `<th>` to the table header**

In the `<thead>` row, add as first `<th>`:

```tsx
<th className="w-10 pl-3">
  <input
    type="checkbox"
    checked={filteredItems.length > 0 && selectedSeries.size === filteredItems.length}
    onChange={() =>
      selectedSeries.size === filteredItems.length
        ? clearSelection()
        : setSelectedSeries(new Set(filteredItems.map(s => s.id)))
    }
    className="rounded"
    style={{ accentColor: 'var(--accent)' }}
  />
</th>
```

**Step 5: Pass props when rendering `LibraryTableRow`**

```tsx
<LibraryTableRow
  ...existingProps
  selected={selectedSeries.has(series.id)}
  onToggle={() => toggleSeries(series.id)}
/>
```

**Step 6: Add batch toolbar above the table**

Insert before the `<table>` element:

```tsx
{selectedSeries.size > 0 && (
  <div
    className="flex items-center gap-2 px-4 py-2 rounded-lg mb-3"
    style={{
      backgroundColor: 'var(--bg-elevated)',
      border: '1px solid var(--accent-dim)',
    }}
  >
    <span className="text-xs font-medium" style={{ color: 'var(--accent)' }}>
      {selectedSeries.size} series selected
    </span>
    <button
      onClick={async () => {
        await startSeriesBatchSearch([...selectedSeries])
        toast('Batch search queued')
        clearSelection()
      }}
      className="px-3 py-1.5 rounded text-xs font-medium"
      style={{ backgroundColor: 'var(--accent-bg)', color: 'var(--accent)', border: '1px solid var(--accent-dim)' }}
    >
      Search All Missing
    </button>
    <button
      onClick={clearSelection}
      className="ml-auto px-2 py-1 rounded text-xs"
      style={{ color: 'var(--text-muted)' }}
    >
      Clear
    </button>
  </div>
)}
```

**Step 7: Add imports**

```typescript
import { startSeriesBatchSearch } from '@/api/client'
import { toast } from '@/components/shared/Toast'
```

**Step 8: Update CHANGELOG.md**

Add a new section at the top of `CHANGELOG.md` for `[0.11.1-beta]` (patch bump since these are additive features):

```markdown
## [0.11.1-beta] — 2026-02-22

### Added
- **Scan Auto-Extract** — `scan_auto_extract` + `scan_auto_translate` settings; scanner
  extracts embedded subs immediately on first detection when enabled
- **Batch Extract Endpoint** — `POST /api/v1/wanted/batch-extract` extracts embedded subs
  for multiple wanted items in one request
- **Multi-Series Batch Search** — `POST /api/v1/wanted/batch-search` now accepts `series_ids`
  array to trigger search across multiple series at once
- **SeriesDetail Batch Toolbar** — episode checkboxes with Search / Extract bulk actions
- **Library Batch Toolbar** — series checkboxes with "Search All Missing" bulk action
```

Also update `backend/VERSION` to `0.11.1-beta`.

**Step 9: Lint + type-check**

```bash
cd frontend && npm run lint 2>&1 | tail -10 && npx tsc --noEmit 2>&1 | head -20
```
Expected: 0 errors.

**Step 10: Commit**

```bash
git add frontend/src/pages/Library.tsx frontend/src/api/client.ts CHANGELOG.md backend/VERSION
git commit -m "feat: add series checkboxes and batch toolbar to Library; bump to 0.11.1-beta"
```
