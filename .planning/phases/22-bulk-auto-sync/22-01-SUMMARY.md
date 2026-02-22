# Phase 22-01: Bulk Auto-Sync Backend -- Summary

## Status: COMPLETE

**Implemented:** 2026-02-22
**File modified:**  (lines 1712-1912, +201 lines)

---

## What was built

Two new endpoints and four helper functions appended to .

### POST /api/v1/tools/auto-sync (single-file sync)

- **Body:** 
- Validates  via  (path mapping + security boundary).
- Engine resolution: request body ->  config entry -> .
- Media path: explicit  or auto-discovered via .
- Creates  backup via  before modifying the subtitle.
- Runs  or 
  via  with 300 s hard timeout.
- Returns  on success.
- Returns 404 if no video found, 500 for timeout / missing binary / engine error.

### POST /api/v1/tools/auto-sync/bulk (library/series batch)

- **Body:** 
- Concurrent-run guard via  dict + .
- Returns 409 if a batch is already running.
- Builds file list synchronously before starting thread (fast fail on Sonarr errors).
- Background thread runs inside  (same pattern as ).
- Per-file:  ->  -> update state.
  Errors increment , emit in progress event, and do not abort the batch.
- WebSocket events via :
  - : 
  - : 
- Returns 202 with  immediately.

---

## Helper functions

| Function | Purpose |
|---|---|
|  | Finds sibling video file; strips language tags (e.g. ) |
|  | Runs alass or ffsubsync; raises  on non-zero exit |
|  | Walks filesystem to build  pairs; skips  |

---

## Module-level state (new)



---

## Design decisions

- No new DB table: sync is stateless beyond in-memory .
-  strips up to 5-char non-digit suffixes for language codes.
-  walks ;  uses Sonarr series path.
- Engine config key:  in existing  table.

---

## Files changed

| File | Change |
|---|---|
|  | +201 lines: state, 2 endpoints, 4 helpers |

## Files NOT changed

-  --  in  is sufficient.
-  -- uses existing generic  table.

---

## Open items for 22-02 (Frontend)

- Add sync button in Series detail view and Library page.
- Display  /  events in UI.
- Add  selector to Settings.
