# Phase 24-01: Uploader Trust Scoring — Summary

**Status:** Complete  
**Date:** 2026-02-22

## What Was Implemented

OpenSubtitles uploader reputation is now extracted per search result and
applied as a 0–20 point bonus in the scoring pipeline. The bonus is
visible in the interactive search UI as a small emerald badge.

## Changed Files

### `backend/providers/base.py`
- `SubtitleResult` dataclass extended with four new fields:
  - `machine_translated: bool = False`
  - `mt_confidence: float = 0.0` (0–100; 100 = definitely MT)
  - `uploader_name: str = ""`
  - `uploader_trust: float = 0.0` (0–20 rank-based bonus)
- `compute_score()` now adds `int(result.uploader_trust)` to the score
  when `result.provider_name == "opensubtitles"` and `uploader_trust > 0`.

### `backend/providers/opensubtitles.py`
- Added `_UPLOADER_RANK_BONUS` constant dict mapping rank strings to
  trust bonus values:
  - `"administrator"` / `"platinum"` → 20.0
  - `"gold"` → 15.0
  - `"silver"` → 10.0
  - `"bronze"` / `"trusted"` → 5.0
  - Unknown / no rank → 0.0
- Per-item loop now extracts `attrs["uploader"]` (uploader_id, name, rank).
  Rank is lowercased and looked up in `_UPLOADER_RANK_BONUS`.
- `SubtitleResult` constructor receives `uploader_name` and `uploader_trust`.

### `backend/wanted_search.py`
- `_result_to_dict_interactive()` extended with four new keys:
  - `"machine_translated"` — via `getattr(result, "machine_translated", False)`
  - `"mt_confidence"` — via `getattr(result, "mt_confidence", 0.0)`
  - `"uploader_trust_bonus"` — via `getattr(result, "uploader_trust", 0.0)`
  - `"uploader_name"` — via `getattr(result, "uploader_name", "")`
  - All four use `getattr` with a default for safe access across all providers.

### `frontend/src/api/client.ts`
- `InteractiveSearchResult` interface extended with:
  - `uploader_trust_bonus?: number  // 0-20`
  - `uploader_name?: string`

### `frontend/src/components/wanted/InteractiveSearchModal.tsx`
- New emerald badge displayed before the MT/HI/F badges when
  `result.uploader_trust_bonus > 0`:
  - Text: `+N Trust` (e.g. "+20 Trust")
  - Color: `text-emerald-400 bg-emerald-400/10`
  - Tooltip: uploader name if available, otherwise "Vertrauenswürdiger Uploader"

## Design Decisions

- `machine_translated` and `mt_confidence` were also added to `SubtitleResult`
  in this phase (were missing from the actual source, only existed in htmlcov
  snapshots from a previous planning cycle). This aligns the dataclass with
  what the frontend already expected.
- `getattr` safe-access pattern used in `wanted_search.py` ensures all
  existing non-OpenSubtitles providers continue to work without modification.
- The trust bonus is intentionally applied as an `int()` cast so fractional
  floats (if introduced later) remain additive without accumulating floating-
  point noise in the score integer.

## Verification

```
backend py_compile: PASS (0 errors)
frontend tsc --noEmit: PASS (0 errors)
```
