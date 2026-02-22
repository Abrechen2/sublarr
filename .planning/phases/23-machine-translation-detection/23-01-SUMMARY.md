# Phase 23-01: Machine Translation Detection Backend — SUMMARY

**Status:** DONE
**Date:** 2026-02-22

## Changes Made

### 1. `backend/providers/base.py`

**New fields on `SubtitleResult` dataclass:**
```python
machine_translated: bool = False
mt_confidence: float = 0.0  # 0-100; 100 = definitely MT
```

**New cache variable:**
```python
_mt_config_cache: dict = {"penalty": None, "threshold": None, "expires": 0}
```

**New function `_get_cached_mt_config() -> tuple[int, float]`:**
- Reads `providers.mt_penalty` (int, default -30) from DB config
- Reads `providers.mt_confidence_threshold` (float, default 50.0) from DB config
- 60-second TTL cache, same pattern as existing `_get_cached_modifier`
- Falls back to defaults if DB unavailable

**Updated `invalidate_scoring_cache()`:**
- Now also resets `_mt_config_cache` for consistency

**Updated `compute_score(result, query)`:**
- After provider modifier: if `mt_penalty != 0` AND
  (`result.machine_translated == True` OR `result.mt_confidence >= mt_threshold`),
  adds `mt_penalty` to score
- `mt_penalty == 0` disables the feature (zero = no-op)

### 2. `backend/providers/opensubtitles.py`

In the `search()` method, before constructing `SubtitleResult`:
```python
api_machine_translated = bool(attrs.get("machine_translated", False))
api_ai_translated = bool(attrs.get("ai_translated", False))
is_mt = api_machine_translated or api_ai_translated
mt_confidence = 100.0 if is_mt else 0.0
```
Both `machine_translated=is_mt` and `mt_confidence=mt_confidence` are now
passed to `SubtitleResult(...)`.

### 3. `backend/wanted_search.py`

In `_result_to_dict_interactive()`, two new fields added to the returned dict:
```python
"machine_translated": getattr(result, "machine_translated", False),
"mt_confidence": getattr(result, "mt_confidence", 0.0),
```
Uses `getattr` with defaults so other providers without the fields remain safe.

## Config Keys (via `config_entries` DB table)

| Key | Type | Default | Meaning |
|-----|------|---------|---------|
| `providers.mt_penalty` | int | -30 | Score penalty applied to MT subtitles |
| `providers.mt_confidence_threshold` | float | 50.0 | Min confidence to trigger penalty |

## Design Decisions

- **Penalty = 0 disables feature** — simple on/off without a separate boolean
- **`getattr` with defaults in `_result_to_dict_interactive`** — future-proof; other providers
  that don't set MT fields still serialize safely
- **Binary confidence (0 or 100) for OpenSubtitles** — the API returns booleans only;
  the float field is reserved for future providers that may return probabilistic scores
- **Same cache TTL (60s)** as all other scoring caches — consistent behavior
- **`invalidate_scoring_cache()` clears MT cache too** — single invalidation call covers all

## Syntax Verification

```
cd backend && python -m py_compile providers/base.py providers/opensubtitles.py wanted_search.py
# => No errors
```

## What Is NOT Done (for 23-02)

- Frontend badge/indicator for MT subtitles in Interactive Search modal
- Settings UI for `mt_penalty` and `mt_confidence_threshold`
- Other providers (Jimaku, AnimeTosho etc.) do not yet emit MT metadata
