# Phase 22-02: Bulk Auto-Sync Frontend -- Summary

## Status: COMPLETE

**Implemented:** 2026-02-22

---

## What was built

### 1. API Client (`frontend/src/api/client.ts`)

Two new exported async functions in a dedicated Phase 22 section:

**`autoSyncFile(filePath, mediaPath?, engine?)`**
- `POST /api/v1/tools/auto-sync`
- Returns `AutoSyncResult`

**`autoSyncBulk(scope, seriesId?, engine?)`**
- `POST /api/v1/tools/auto-sync/bulk`
- Returns `AutoSyncBulkResult`

### 2. New Types (`frontend/src/lib/types.ts`)

Four new interfaces in a Phase 22 section:
- `AutoSyncResult` — single-file sync response
- `AutoSyncBulkResult` — bulk sync start confirmation (202)
- `SyncBatchProgress` — WebSocket progress payload `{ current, total, file_path, completed, failed, error? }`
- `SyncBatchComplete` — WebSocket completion payload `{ completed, failed, total }`

### 3. WebSocket Handler (`frontend/src/hooks/useWebSocket.ts`)

Two new typed event handlers added to `UseWebSocketOptions`:
- `onSyncBatchProgress?: (data: SyncBatchProgress) => void`
- `onSyncBatchComplete?: (data: SyncBatchComplete) => void`

Events registered: `sync_batch_progress` and `sync_batch_complete`.

### 4. Library Page (`frontend/src/pages/Library.tsx`)

**Bulk Sync Panel (`BulkSyncPanel` component):**
- Scope selector: Entire Library / Single Series
- Series dropdown (visible when scope = series)
- Engine override: Default / alass / ffsubsync
- "Start Bulk Sync" button → `autoSyncBulk(scope, seriesId, engine)`
- Real-time progress bar driven by `sync_batch_progress` WebSocket events
- Shows: current/total, completed count, failed count, percentage, current file path
- Completion toast via `sync_batch_complete`

**Toggle button** in Library header (next to tabs): "Auto-Sync" button shows/hides the panel.

### 5. Series Detail (`frontend/src/pages/SeriesDetail.tsx`)

New `RefreshCw` auto-sync button per episode (shown when episode has subtitle file):
- Sits alongside the existing Timer (SyncControls) button
- Tooltip: "Auto-sync timing (alass/ffsubsync)"
- Calls `autoSyncFile(subtitlePath)` directly
- Shows "Auto-syncing…" toast → success/error toast
- Green hover color (vs accent for manual sync) to distinguish from SyncControls modal

`handleAutoSync` callback wired through `SeasonGroup` `onAutoSync` prop.

### 6. Subtitle Editor Modal (`frontend/src/components/editor/SubtitleEditorModal.tsx`)

New "Auto-Sync" button in the modal header (between mode tabs and file path area):
- `RefreshCw` icon + "Auto-Sync" label
- Shows spinner while loading (`syncLoading` state)
- Calls `autoSyncFile(filePath)` → success/error toast
- Button disabled during sync

### 7. Settings – Default Sync Engine (`frontend/src/pages/Settings/TranslationTab.tsx` + `index.tsx`)

**`DefaultSyncEngineRow` component:**
- `SettingRow` with a dropdown: "alass (recommended)" / "ffsubsync"
- Reads from `config['sync.default_engine']`
- Saves via `updateConfig({ 'sync.default_engine': value })`
- Success/error toasts

Registered in `Settings/index.tsx` as a lazy-loaded component, rendered after `ContextWindowSizeRow` in the Translation tab.

---

## Files changed

| File | Change |
|---|---|
| `frontend/src/lib/types.ts` | +35 lines: 4 new interfaces for auto-sync |
| `frontend/src/api/client.ts` | +25 lines: `autoSyncFile`, `autoSyncBulk` |
| `frontend/src/hooks/useWebSocket.ts` | +6 lines: typed handlers for sync batch events |
| `frontend/src/pages/Library.tsx` | +170 lines: `BulkSyncPanel` + toggle button integration |
| `frontend/src/pages/SeriesDetail.tsx` | +35 lines: `onAutoSync` prop + auto-sync button per episode |
| `frontend/src/components/editor/SubtitleEditorModal.tsx` | +30 lines: Auto-Sync button in header |
| `frontend/src/pages/Settings/TranslationTab.tsx` | +40 lines: `DefaultSyncEngineRow` component |
| `frontend/src/pages/Settings/index.tsx` | +3 lines: lazy import + render of `DefaultSyncEngineRow` |

---

## Design decisions

- **Library page**: No per-series-row sync button (Library only has aggregate data, no individual subtitle file paths). Instead: bulk sync panel with scope=series + series picker provides equivalent functionality.
- **Series Detail**: Two sync options per episode — Timer icon → SyncControls modal (manual offset/speed); RefreshCw → `autoSyncFile` (AI-powered auto-sync). Green hover color distinguishes auto from manual.
- **Engine config key**: `sync.default_engine` in existing `config_entries` table — no new DB migration needed.
- **Progress state**: Local to `BulkSyncPanel` (not global), avoids prop-drilling and keeps concern co-located.
- **No new hook**: `useWebSocket` options pattern handles sync events cleanly without a dedicated `useSyncBatchStatus` hook.

---

## Verification

```bash
cd frontend && npx tsc --noEmit  # 0 errors
```

All 14 remaining ESLint errors are pre-existing (not introduced by this phase).
