# MovieDetail Subtitle Management — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a subtitle wanted-items section to `MovieDetailPage` so users can see missing subtitles, trigger search/process actions, and skip movies — matching the subtitle management features available in SeriesDetail.

**Architecture:** `MovieDetailPage` fetches the movie's wanted items from `/wanted?item_type=movie&movie_id=<id>`. A new backend query param `movie_id` (maps to `standalone_movie_id`) is added to the existing `/wanted` route. The wanted list is rendered below the file info card with inline Search/Skip/Process actions wired to existing hooks.

**Tech Stack:** Flask (backend route + db layer), React 19 + TypeScript, TanStack Query, existing `useWantedItems` / `useSearchWantedItem` / `useProcessWantedItem` / `useUpdateWantedStatus` hooks.

---

## File Map

| File | Change |
|------|--------|
| `backend/db/wanted.py` | Add `movie_id` param to `get_wanted_items()` |
| `backend/db/repositories/wanted.py` | Add `standalone_movie_id` filter to `get_wanted_items()` query |
| `backend/routes/wanted/list.py` | Parse `movie_id` query param, pass to `get_wanted_items()` |
| `frontend/src/api/client.ts` | Add `movieId` optional param to `getWantedItems()` |
| `frontend/src/hooks/useWantedApi.ts` | Add `movieId` param to `useWantedItems()` |
| `frontend/src/pages/MovieDetail.tsx` | Add `MovieWantedSection` component + wire hooks |
| `frontend/src/pages/__tests__/MovieDetail.test.tsx` | Add tests for wanted section rendering |

---

### Task 1: Backend — Add `movie_id` filter to `/wanted` endpoint

**Files:**
- Modify: `backend/db/repositories/wanted.py` — add `standalone_movie_id` filter
- Modify: `backend/db/wanted.py` — add `movie_id` param
- Modify: `backend/routes/wanted/list.py` — parse + pass `movie_id`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_wanted_movie_filter.py
def test_get_wanted_items_filters_by_movie_id(db_session):
    """movie_id query param filters wanted items by standalone_movie_id."""
    from db.wanted import get_wanted_items

    result_all = get_wanted_items(item_type="movie")
    result_filtered = get_wanted_items(item_type="movie", movie_id=42)

    # filtered result contains only items with standalone_movie_id == 42
    assert all(item["standalone_movie_id"] == 42 for item in result_filtered["data"])
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/test_wanted_movie_filter.py -v
```
Expected: FAIL — `get_wanted_items` doesn't accept `movie_id` param yet.

- [ ] **Step 3: Add `standalone_movie_id` filter in repository**

In `backend/db/repositories/wanted.py`, find the `get_wanted_items()` method signature and body:

```python
# Add movie_id param to signature (alongside series_id):
def get_wanted_items(self, page, per_page, item_type=None, status=None,
                     series_id=None, movie_id=None, subtitle_type=None,
                     sort_by="added_at", sort_dir="desc", search=None):
```

Add the filter clause after the `series_id` block:

```python
if series_id is not None:
    stmt = stmt.where(WantedItem.sonarr_series_id == series_id)
if movie_id is not None:
    stmt = stmt.where(WantedItem.standalone_movie_id == movie_id)
```

- [ ] **Step 4: Add `movie_id` to `db/wanted.py`**

```python
def get_wanted_items(
    page: int = 1,
    per_page: int = 50,
    item_type: str = None,
    status: str = None,
    series_id: int = None,
    movie_id: int = None,       # ← add this line
    subtitle_type: str = None,
    sort_by: str = "added_at",
    sort_dir: str = "desc",
    search: str = None,
) -> dict:
    return _get_repo().get_wanted_items(
        page, per_page, item_type, status, series_id,
        movie_id,                # ← add this line
        subtitle_type, sort_by=sort_by, sort_dir=sort_dir, search=search,
    )
```

- [ ] **Step 5: Parse `movie_id` in route**

In `backend/routes/wanted/list.py`, after line `series_id = request.args.get("series_id", type=int)`:

```python
movie_id = request.args.get("movie_id", type=int)
```

Pass to `get_wanted_items()`:

```python
result = get_wanted_items(
    page=page,
    per_page=per_page,
    item_type=item_type,
    status=status_filter,
    series_id=series_id,
    movie_id=movie_id,    # ← add this line
    subtitle_type=subtitle_type,
    sort_by=sort_by,
    sort_dir=sort_dir,
    search=search,
)
```

- [ ] **Step 6: Run test to verify it passes**

```bash
cd backend && python -m pytest tests/test_wanted_movie_filter.py -v
```
Expected: PASS.

- [ ] **Step 7: Run full backend test suite**

```bash
cd backend && python -m pytest --tb=short -q \
  --ignore=tests/performance \
  --ignore=tests/integration/test_provider_pipeline.py \
  --ignore=tests/test_video_sync.py \
  --ignore=tests/test_translation_backends.py \
  -k "not (test_sonarr_download_webhook or test_radarr_download_webhook or test_parse_llm_response_too_many_merge or test_record_backend_success)"
```
Expected: All tests pass.

- [ ] **Step 8: Commit**

```bash
git add backend/db/repositories/wanted.py backend/db/wanted.py backend/routes/wanted/list.py backend/tests/test_wanted_movie_filter.py
git commit -m "feat: add movie_id filter to /wanted endpoint"
```

---

### Task 2: Frontend — Expose `movieId` in API client and hook

**Files:**
- Modify: `frontend/src/api/client.ts` — add `movieId` to `getWantedItems()`
- Modify: `frontend/src/hooks/useWantedApi.ts` — add `movieId` to `useWantedItems()`

- [ ] **Step 1: Update `getWantedItems` in client.ts**

Find `getWantedItems` in `frontend/src/api/client.ts`:

```typescript
export async function getWantedItems(
  page = 1, perPage = 50, itemType?: string, status?: string,
  subtitleType?: string, movieId?: number
): Promise<PaginatedWanted> {
  const params: Record<string, unknown> = { page, per_page: perPage }
  if (itemType) params.item_type = itemType
  if (status) params.status = status
  if (subtitleType) params.subtitle_type = subtitleType
  if (movieId != null) params.movie_id = movieId   // ← add this line
  const { data } = await api.get('/wanted', { params })
  // ... rest unchanged
```

- [ ] **Step 2: Update `useWantedItems` in useWantedApi.ts**

```typescript
export function useWantedItems(
  page = 1, perPage = 50, itemType?: string, status?: string,
  subtitleType?: string, fetchAll = false, movieId?: number
) {
  return useQuery({
    queryKey: ['wanted', fetchAll ? 'all' : page, fetchAll ? 9999 : perPage,
               itemType, status, subtitleType, movieId],
    queryFn: () =>
      getWantedItems(
        fetchAll ? 1 : page,
        fetchAll ? 9999 : perPage,
        itemType, status, subtitleType, movieId
      ),
  })
}
```

- [ ] **Step 3: Run frontend tests to verify no regressions**

```bash
cd frontend && npm run test -- --run
```
Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/client.ts frontend/src/hooks/useWantedApi.ts
git commit -m "feat: add movieId filter to useWantedItems hook"
```

---

### Task 3: MovieDetail — Add `MovieWantedSection` component

**Files:**
- Modify: `frontend/src/pages/MovieDetail.tsx` — add wanted section
- Modify: `frontend/src/pages/__tests__/MovieDetail.test.tsx` — add tests

- [ ] **Step 1: Write failing tests**

In `frontend/src/pages/__tests__/MovieDetail.test.tsx`, add a mock for `useWantedItems` and test the wanted section:

```typescript
const mockUseWantedItems = vi.fn()

// Add to existing vi.mock block:
vi.mock('@/hooks/useApi', () => ({
  useMovieDetail: (id: number | null) => mockUseMovieDetail(id),
  useWantedItems: (...args: unknown[]) => mockUseWantedItems(...args),
}))

it('renders wanted items section with search button for missing subtitles', () => {
  mockUseMovieDetail.mockReturnValue({
    data: { id: 1, title: 'Test Movie', year: 2024, file_path: '/test.mkv',
            tmdb_id: null, imdb_id: null, poster_url: null, wanted_count: 1,
            metadata_source: 'tmdb', created_at: '', updated_at: '' },
    isLoading: false, error: null,
  })
  mockUseWantedItems.mockReturnValue({
    data: {
      data: [{ id: 10, item_type: 'movie', title: 'Test Movie',
               target_language: 'de', status: 'wanted', missing_languages: ['de'],
               season_episode: '', file_path: '/test.mkv', existing_sub: '',
               last_search_at: '', search_count: 0, error: '', retry_after: null,
               added_at: '', updated_at: '', upgrade_candidate: 0, current_score: 0,
               subtitle_type: 'full', sonarr_series_id: null, sonarr_episode_id: null,
               radarr_movie_id: null }],
      total: 1, page: 1, per_page: 50,
    },
    isLoading: false,
  })
  render(<MovieDetailPage />, { wrapper: createWrapper() })
  expect(screen.getByTestId('movie-wanted-section')).toBeInTheDocument()
  expect(screen.getByText('de')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /search/i })).toBeInTheDocument()
})

it('shows empty state when no wanted items', () => {
  mockUseMovieDetail.mockReturnValue({
    data: { id: 1, title: 'Test Movie', year: 2024, file_path: '/test.mkv',
            tmdb_id: null, imdb_id: null, poster_url: null, wanted_count: 0,
            metadata_source: 'tmdb', created_at: '', updated_at: '' },
    isLoading: false, error: null,
  })
  mockUseWantedItems.mockReturnValue({
    data: { data: [], total: 0, page: 1, per_page: 50 },
    isLoading: false,
  })
  render(<MovieDetailPage />, { wrapper: createWrapper() })
  expect(screen.getByText(/no missing subtitles/i)).toBeInTheDocument()
})
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd frontend && npm run test -- --run -- MovieDetail
```
Expected: FAIL — `movie-wanted-section` test ID doesn't exist yet.

- [ ] **Step 3: Implement `MovieWantedSection` in MovieDetail.tsx**

Add imports at top of `frontend/src/pages/MovieDetail.tsx`:

```typescript
import { Search, SkipForward } from 'lucide-react'
import { useWantedItems, useSearchWantedItem, useUpdateWantedStatus } from '@/hooks/useApi'
import type { WantedItem } from '@/lib/types'
```

Add the `MovieWantedSection` component above `MovieDetailPage`:

```typescript
function MovieWantedSection({ movieId }: { movieId: number }) {
  const { data: wanted, isLoading } = useWantedItems(
    1, 50, 'movie', undefined, undefined, false, movieId
  )
  const search = useSearchWantedItem()
  const updateStatus = useUpdateWantedStatus()

  const items = wanted?.data ?? []

  if (isLoading) {
    return (
      <div
        className="rounded-lg p-5"
        style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
        data-testid="movie-wanted-section"
      >
        <Loader2 size={16} className="animate-spin" style={{ color: 'var(--accent)' }} />
      </div>
    )
  }

  return (
    <div
      className="rounded-lg p-5"
      style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
      data-testid="movie-wanted-section"
    >
      <h2 className="text-sm font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>
        Subtitles
      </h2>

      {items.length === 0 ? (
        <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
          No missing subtitles
        </p>
      ) : (
        <div className="space-y-2">
          {items.map((item: WantedItem) => (
            <div
              key={item.id}
              className="flex items-center justify-between gap-3 py-2 px-3 rounded-md"
              style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)' }}
            >
              <div className="flex items-center gap-2">
                <span
                  className="text-xs font-semibold px-2 py-0.5 rounded"
                  style={{
                    backgroundColor: item.status === 'wanted' ? 'rgba(239,68,68,0.15)' : 'var(--bg-elevated)',
                    color: item.status === 'wanted' ? 'var(--error)' : 'var(--text-secondary)',
                  }}
                >
                  {item.target_language.toUpperCase()}
                </span>
                <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
                  {item.status}
                  {item.search_count > 0 && ` · ${item.search_count} searches`}
                </span>
              </div>
              <div className="flex items-center gap-2">
                {item.status === 'wanted' && (
                  <>
                    <button
                      onClick={() => search.mutate(item.id)}
                      disabled={search.isPending}
                      style={{
                        fontSize: '11px', fontWeight: 600, padding: '3px 10px',
                        borderRadius: '4px', backgroundColor: 'var(--accent)',
                        color: '#fff', border: 'none', cursor: 'pointer',
                        opacity: search.isPending ? 0.6 : 1,
                      }}
                    >
                      <Search size={10} className="inline mr-1" />
                      Search
                    </button>
                    <button
                      onClick={() => updateStatus.mutate({ itemId: item.id, status: 'ignored' })}
                      disabled={updateStatus.isPending}
                      style={{
                        fontSize: '11px', padding: '3px 10px', borderRadius: '4px',
                        backgroundColor: 'transparent', color: 'var(--text-secondary)',
                        border: '1px solid var(--border)', cursor: 'pointer',
                      }}
                    >
                      <SkipForward size={10} className="inline mr-1" />
                      Skip
                    </button>
                  </>
                )}
                {item.status === 'ignored' && (
                  <button
                    onClick={() => updateStatus.mutate({ itemId: item.id, status: 'wanted' })}
                    style={{
                      fontSize: '11px', padding: '3px 10px', borderRadius: '4px',
                      backgroundColor: 'transparent', color: 'var(--text-muted)',
                      border: '1px solid var(--border)', cursor: 'pointer',
                    }}
                  >
                    Re-enable
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Add `MovieWantedSection` to `MovieDetailPage` return**

In `MovieDetailPage`, after the File Info card block:

```tsx
{/* Subtitle Management */}
<MovieWantedSection movieId={movie.id} />
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd frontend && npm run test -- --run -- MovieDetail
```
Expected: All tests PASS.

- [ ] **Step 6: Run lint + type check**

```bash
cd frontend && npm run lint && npx tsc --noEmit
```
Expected: No errors.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/MovieDetail.tsx frontend/src/pages/__tests__/MovieDetail.test.tsx
git commit -m "feat: add subtitle wanted section to MovieDetailPage"
```
