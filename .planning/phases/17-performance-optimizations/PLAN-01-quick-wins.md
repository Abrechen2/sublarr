# Plan 17-01: Quick Wins — Debug Interceptor + Polling + Provider Timeouts

## Goal
Remove the leaked debug interceptor, reduce excessive polling intervals, and cut
provider search timeouts — three independent changes with immediate measurable impact.

## Changes

### 1. frontend/src/api/client.ts — Remove debug interceptor (lines 38-53)
Delete the entire `#region agent log` block. Every API error currently fires a
fetch() to 127.0.0.1:7652 with session IDs and error data (leftover hook artifact).

Remove lines 38-53:
```
// #region agent log
api.interceptors.response.use(...)
// #endregion
```

### 2. frontend/src/hooks/useApi.ts — Reduce polling intervals

| Line | Hook | Old | New |
|------|------|-----|-----|
| ~211 | useWantedBatchStatus | 3000 | 10000 |
| ~94  | useJobs              | 5000 | 15000 |
| ~104 | useBatchStatus       | 5000 | 15000 |
| ~722 | useWhisperQueue      | 5000 | 15000 |
| ~1351| useCleanupScanStatus | 2000 | 5000  |
| ~84  | useStats             | 10000| 30000 |
| ~1023| useTasks             | 10000| 30000 |
| ~770 | useStandaloneStatus  | 10000| 30000 |

### 3. backend/providers/__init__.py — Reduce timeouts (lines ~94-101)

```python
PROVIDER_TIMEOUTS = {
    "animetosho": 10,   # was 20
    "opensubtitles": 10, # was 15
    "jimaku": 12,        # was 30
    "subdl": 10,         # was 15
}
```

Also change line ~635: `+ 5` overhead buffer → `+ 3`

## Verification
- DevTools Network: no requests to 127.0.0.1:7652 on errors
- Dashboard Network tab: less polling over 30s window
- Provider search: completes in <15s for healthy providers
- npm test passes
