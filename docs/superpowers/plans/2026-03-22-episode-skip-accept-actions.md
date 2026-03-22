# Episode Skip / Accept Actions — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the `onSkip` and `onAccept` stubs in `EpisodeInlineActions` so that clicking "Skip" on a missing episode marks it as `'ignored'`, and clicking "Accept" on a low-score episode also marks it as `'ignored'` (user accepts current quality). Both require a `wanted_id` lookup from the series' wanted items.

**Architecture:** `SeriesDetail.tsx` already has `seriesId` (the Sonarr series ID). Load wanted items filtered by `series_id` via the existing `/wanted?series_id=<id>` backend endpoint. Build a lookup map `sonarr_episode_id → WantedItem.id` in `SeriesDetail`. Pass the map to `SeasonGroup`, which threads the relevant `wanted_id` down to `EpisodeInlineActions.onSkip` and `EpisodeInlineActions.onAccept`. Call `useUpdateWantedStatus(wantedId, 'ignored')` for both actions. Re-query wanted items on success to update the episode row status.

**Tech Stack:** React 19 + TypeScript, existing `useWantedItems` + `useUpdateWantedStatus` hooks, `SeasonGroup` + `EpisodeInlineActions` components.

---

## File Map

| File | Change |
|------|--------|
| `frontend/src/pages/SeriesDetail.tsx` | Fetch wanted items by series_id, build lookup map, pass to SeasonGroup |
| `frontend/src/components/series/SeasonGroup.tsx` | Accept `wantedMap` prop, pass `wanted_id` to EpisodeInlineActions callbacks |
| `frontend/src/components/series/EpisodeGrid.tsx` | `EpisodeInlineActions`: implement `onSkip` and `onAccept` with real callbacks |
| `frontend/src/pages/__tests__/SeriesDetail.test.tsx` | Add test for skip/accept button behavior |

---

### Task 1: Load wanted items by series_id in SeriesDetail

**Files:**
- Modify: `frontend/src/pages/SeriesDetail.tsx`

- [ ] **Step 1: Add `useWantedItems` import to SeriesDetail**

In `SeriesDetail.tsx`, find the `useApi` imports line. Add `useWantedItems` and `useUpdateWantedStatus`:

```typescript
import { useSeriesDetail, useWantedItems, useUpdateWantedStatus } from '@/hooks/useApi'
```

(They may already be imported — check before adding.)

- [ ] **Step 2: Fetch wanted items and build lookup map**

Inside `SeriesDetailPage` (or the main component), after the `seriesId` is parsed, add:

```typescript
const { data: seriesWanted } = useWantedItems(
  1, 9999, 'episode', undefined, undefined, true,
  undefined  // no movieId
)
const updateStatus = useUpdateWantedStatus()

// Build lookup: sonarr_episode_id → wanted item id
const episodeWantedMap = useMemo((): Map<number, number> => {
  const map = new Map<number, number>()
  if (!seriesWanted?.data) return map
  for (const item of seriesWanted.data) {
    // Only include items belonging to this series
    if (item.sonarr_series_id === seriesId && item.sonarr_episode_id != null) {
      map.set(item.sonarr_episode_id, item.id)
    }
  }
  return map
}, [seriesWanted?.data, seriesId])
```

Add `useMemo` to the React imports if not already present.

- [ ] **Step 3: Pass `episodeWantedMap` and `updateStatus` to SeasonGroup**

Find where `<SeasonGroup>` is rendered in `SeriesDetail.tsx`. Add two props:

```tsx
<SeasonGroup
  {/* ... existing props ... */}
  episodeWantedMap={episodeWantedMap}
  onSkipEpisode={(episodeId) => {
    const wantedId = episodeWantedMap.get(episodeId)
    if (wantedId != null) updateStatus.mutate({ itemId: wantedId, status: 'ignored' })
  }}
  onAcceptEpisode={(episodeId) => {
    const wantedId = episodeWantedMap.get(episodeId)
    if (wantedId != null) updateStatus.mutate({ itemId: wantedId, status: 'ignored' })
  }}
/>
```

- [ ] **Step 4: Write the test**

In `frontend/src/pages/__tests__/SeriesDetail.test.tsx`, add a test case:

```typescript
it('calls updateWantedItemStatus with "ignored" when Skip is clicked', async () => {
  const mockUpdateStatus = vi.fn()
  mockUseUpdateWantedStatus.mockReturnValue({ mutate: mockUpdateStatus, isPending: false })
  mockUseWantedItems.mockReturnValue({
    data: {
      data: [{
        id: 99, item_type: 'episode', sonarr_series_id: 1, sonarr_episode_id: 42,
        radarr_movie_id: null, title: 'S01E01', season_episode: 'S01E01',
        file_path: '/ep1.mkv', existing_sub: '', missing_languages: ['de'],
        target_language: 'de', status: 'wanted', last_search_at: '',
        search_count: 0, error: '', retry_after: null, added_at: '',
        updated_at: '', upgrade_candidate: 0, current_score: 0,
        subtitle_type: 'full', instance_name: undefined,
      }],
      total: 1, page: 1, per_page: 9999,
    },
  })

  render(<SeriesDetailPage />, { wrapper: createWrapper() })

  const skipBtn = await screen.findByRole('button', { name: /skip/i })
  await userEvent.click(skipBtn)

  expect(mockUpdateStatus).toHaveBeenCalledWith({ itemId: 99, status: 'ignored' })
})
```

- [ ] **Step 5: Run test to verify it fails**

```bash
cd frontend && npm run test -- --run -- SeriesDetail
```
Expected: FAIL — `onSkip` is still a no-op stub.

---

### Task 2: Update SeasonGroup to thread skip/accept callbacks

**Files:**
- Modify: `frontend/src/components/series/SeasonGroup.tsx`

- [ ] **Step 1: Add new props to SeasonGroup interface**

In `SeasonGroup.tsx`, find the props interface. Add:

```typescript
readonly episodeWantedMap?: Map<number, number>
readonly onSkipEpisode?: (episodeId: number) => void
readonly onAcceptEpisode?: (episodeId: number) => void
```

- [ ] **Step 2: Replace `_` prefix stubs for onSkip/onAccept**

In the `SeasonGroup` component body, find the episode row rendering where `EpisodeInlineActions` is used. Replace the stub callbacks:

```typescript
// Before (stubs):
onSkip={() => { /* TODO: implement skip */ }}
onAccept={() => { /* TODO: implement accept */ }}

// After (wired):
onSkip={() => props.onSkipEpisode?.(episode.id)}
onAccept={() => props.onAcceptEpisode?.(episode.id)}
```

Where `episode.id` is the `sonarr_episode_id` from `EpisodeInfo.id`.

- [ ] **Step 3: Run tests to verify they pass**

```bash
cd frontend && npm run test -- --run -- SeriesDetail
```
Expected: All tests PASS (including the new skip test).

- [ ] **Step 4: Run full frontend test suite**

```bash
cd frontend && npm run test -- --run
```
Expected: All tests pass.

- [ ] **Step 5: Run lint + type check**

```bash
cd frontend && npm run lint && npx tsc --noEmit
```
Expected: No errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/SeriesDetail.tsx \
        frontend/src/components/series/SeasonGroup.tsx \
        frontend/src/pages/__tests__/SeriesDetail.test.tsx
git commit -m "feat: implement episode Skip and Accept actions via wanted status update"
```

---

## Notes

- **`onSkip`** (status=`'missing'`) → `updateWantedItemStatus(wantedId, 'ignored')` — marks item so the scanner won't queue it again.
- **`onAccept`** (status=`'low-score'`) → `updateWantedItemStatus(wantedId, 'ignored')` — user accepts current quality, stops flagging as low-score.
- If `episodeWantedMap.get(episodeId)` returns `undefined` (no wanted record exists for this episode), both buttons silently no-op — this is correct behavior since there's nothing to update.
- The `EpisodeInfo.id` field maps to `sonarr_episode_id` in `WantedItem`. This is the join key.
- `useWantedItems` is fetched with `fetchAll=true` (perPage=9999) to avoid pagination gaps. For large series (500+ episodes) this is still fast since each episode has at most one wanted item per language.
