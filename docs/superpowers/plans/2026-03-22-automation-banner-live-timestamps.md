# AutomationBanner Live Timestamps — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hardcoded `"Next scan in 23 min · Last completed: 7 min ago"` string in `AutomationBanner` with a live relative timestamp derived from `scannerStatus.last_scan_at` and `scannerStatus.last_search_at` which are already fetched by `useScannerStatus()`.

**Architecture:** `AutomationBanner` already calls `useScannerStatus()` and has access to `scannerStatus.last_scan_at` (string | null) and `scannerStatus.last_search_at` (string | null). `formatRelativeTime()` from `@/lib/utils` converts an ISO string to a human-readable relative time string. Replace the hardcoded subtitle line with computed values. The Pause button remains (it's wired to a no-op by design — config-level toggle not implemented), but add `disabled` styling to signal it's not active.

**Tech Stack:** React 19 + TypeScript, existing `useScannerStatus` hook, `formatRelativeTime` utility.

---

## File Map

| File | Change |
|------|--------|
| `frontend/src/components/dashboard/AutomationBanner.tsx` | Replace hardcoded string with live timestamps |
| `frontend/src/components/dashboard/__tests__/AutomationBanner.test.tsx` | Add/update tests for timestamp display |

---

### Task 1: Add/Update tests for timestamp display

**Files:**
- Modify: `frontend/src/components/dashboard/__tests__/AutomationBanner.test.tsx`

- [ ] **Step 1: Find existing test file**

```bash
find frontend/src/components/dashboard -name "*.test.*" | head -5
```

- [ ] **Step 2: Write failing tests**

Locate or create `frontend/src/components/dashboard/__tests__/AutomationBanner.test.tsx`. Add these test cases:

```typescript
it('shows formatted last scan time when last_scan_at is provided', () => {
  // Set a timestamp 5 minutes ago
  const fiveMinAgo = new Date(Date.now() - 5 * 60 * 1000).toISOString()
  mockUseScannerStatus.mockReturnValue({
    data: { is_scanning: false, is_searching: false,
            progress: 0, last_scan_at: fiveMinAgo, last_search_at: null },
  })
  mockUseWantedSummary.mockReturnValue({ data: { total: 0 } })
  mockUseStats.mockReturnValue({ data: null })
  mockUseRefreshWanted.mockReturnValue({ mutate: vi.fn(), isPending: false })

  render(<AutomationBanner />, { wrapper: createWrapper() })

  // Should NOT show the hardcoded string
  expect(screen.queryByText(/23 min/)).not.toBeInTheDocument()
  // Should show "5 min ago" or similar relative time
  expect(screen.getByTestId('banner-subtitle')).toHaveTextContent(/ago|just now/i)
})

it('shows "Never scanned" when last_scan_at is null', () => {
  mockUseScannerStatus.mockReturnValue({
    data: { is_scanning: false, is_searching: false,
            progress: 0, last_scan_at: null, last_search_at: null },
  })
  mockUseWantedSummary.mockReturnValue({ data: { total: 0 } })
  mockUseStats.mockReturnValue({ data: null })
  mockUseRefreshWanted.mockReturnValue({ mutate: vi.fn(), isPending: false })

  render(<AutomationBanner />, { wrapper: createWrapper() })
  expect(screen.getByTestId('banner-subtitle')).toHaveTextContent(/never/i)
})
```

- [ ] **Step 3: Run tests to confirm they fail**

```bash
cd frontend && npm run test -- --run -- AutomationBanner
```
Expected: FAIL — `banner-subtitle` test ID missing, hardcoded string found.

---

### Task 2: Replace hardcoded string with live timestamps

**Files:**
- Modify: `frontend/src/components/dashboard/AutomationBanner.tsx`

- [ ] **Step 1: Add `formatRelativeTime` import**

In `AutomationBanner.tsx`, find the import line:

```typescript
import { cn } from '@/lib/utils'
```

Replace with:

```typescript
import { cn, formatRelativeTime } from '@/lib/utils'
```

- [ ] **Step 2: Compute display string from scanner status**

In `AutomationBanner`, after the `needsAttention` line (before the return):

```typescript
// Derive the subtitle line from live scanner data
const lastActivity = scannerStatus?.last_scan_at ?? scannerStatus?.last_search_at ?? null
const bannerSubtitle = lastActivity
  ? `Last completed: ${formatRelativeTime(lastActivity)}`
  : 'Never scanned'
```

- [ ] **Step 3: Replace the hardcoded string**

Find the hardcoded subtitle span (line ~126):

```tsx
<span
  style={{
    fontSize: '11px',
    color: 'var(--text-muted)',
    marginLeft: '20px',
  }}
>
  Next scan in 23 min · Last completed: 7 min ago
</span>
```

Replace with:

```tsx
<span
  data-testid="banner-subtitle"
  style={{
    fontSize: '11px',
    color: 'var(--text-muted)',
    marginLeft: '20px',
  }}
>
  {bannerSubtitle}
</span>
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd frontend && npm run test -- --run -- AutomationBanner
```
Expected: All tests PASS.

- [ ] **Step 5: Run lint + type check**

```bash
cd frontend && npm run lint && npx tsc --noEmit
```
Expected: No errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/dashboard/AutomationBanner.tsx frontend/src/components/dashboard/__tests__/AutomationBanner.test.tsx
git commit -m "fix: replace hardcoded AutomationBanner timestamps with live scanner status data"
```
