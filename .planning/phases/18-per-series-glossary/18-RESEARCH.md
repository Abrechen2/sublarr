# Phase 18 Research: Per-Series Glossary

## Current State Summary

The existing codebase has a **per-series-only** glossary system (M9). Phase 18 needs to add:
1. A **global glossary** (series-independent entries)
2. **Merge logic** (per-series overrides global for same source_term)
3. **Global glossary UI** in Settings

---

## Existing Glossary System

**Model:** `backend/db/models/translation.py` — `GlossaryEntry`

```python
class GlossaryEntry(db.Model):
    __tablename__ = "glossary_entries"
    id: Mapped[int]  — primary key
    series_id: Mapped[int] = mapped_column(Integer, nullable=False)  # ← NOT NULL
    source_term: Mapped[str]
    target_term: Mapped[str]
    notes: Mapped[Optional[str]]
    created_at: Mapped[str]
    updated_at: Mapped[str]
    __table_args__ = (
        Index("idx_glossary_series_id", "series_id"),
        Index("idx_glossary_source_term", "source_term"),
    )
```

**Key finding:** `series_id` is NOT NULLABLE → no global glossary entries possible today.

---

## Translation Pipeline Integration Point

**File:** `backend/translator.py`

```python
# Line 183-193: glossary loading
glossary_entries = None
if series_id:
    entries = get_glossary_for_series(series_id)
    if entries:
        glossary_entries = entries

# Lines 461, 591, 989: passed to manager.translate_with_fallback()
```

**File:** `backend/db/repositories/translation.py`

```python
def get_glossary_for_series(self, series_id: int) -> list[dict]:
    # returns [{source_term, target_term}], limited to 15 entries, ordered by updated_at DESC
```

**Merge point:** The `glossary_entries` list is passed directly to `TranslationManager.translate_with_fallback()` which forwards it to each backend's `translate_batch()`. For Ollama, `build_prompt_with_glossary()` prepends entries as `"term → translation"` to the prompt.

---

## Series Identifier

**Identifier used:** `sonarr_series_id` (integer, extracted from `arr_context`)
**In DB:** `GlossaryEntry.series_id` stores the Sonarr series ID
**Special value for global:** Will use `series_id = NULL` (requires migration to make nullable)

---

## What's Already Done ✅

1. **GlossaryEntry model** — exists, needs series_id made nullable
2. **CRUD repository methods** — `add_glossary_entry`, `get_glossary_entries`, `get_glossary_for_series`, `update_glossary_entry`, `delete_glossary_entry` — all exist
3. **API routes** — `GET/POST /api/v1/glossary`, `PUT/DELETE /api/v1/glossary/<id>` — exist in `backend/routes/profiles.py`, but require `series_id` (will need to allow NULL)
4. **Frontend GlossaryPanel** — `frontend/src/pages/SeriesDetail.tsx` lines 190-440 — full CRUD UI for per-series glossary, toggle button in hero header
5. **Translation pipeline** — translator.py already loads and uses glossary; just needs merge logic

---

## What Phase 18 Must Build ❌

### Backend:
1. **DB migration** — `series_id` nullable on `glossary_entries` (`render_as_batch=True`)
2. **Repository: `get_global_glossary()`** — fetch entries where `series_id IS NULL`
3. **Repository: `get_merged_glossary_for_series(series_id)`** — load global entries + series-specific, per-series overrides on same `source_term`
4. **Route update** — allow `series_id=null` / omit for global entries; GET without series_id returns global
5. **translator.py** — replace `get_glossary_for_series(series_id)` call with `get_merged_glossary_for_series(series_id)` to include global entries with per-series override

### Frontend:
6. **Settings global glossary UI** — add a "Global Glossary" section to `Settings/TranslationTab.tsx` (reuse GlossaryPanel pattern but without series_id filter, pass `seriesId=null`)
7. **API client** — update `getGlossaryEntries()` and `createGlossaryEntry()` to allow `seriesId=null` for global entries

---

## Current Alembic Migration HEAD

`fa890ea72dab` — add_filter_presets

New migration down_revision: `fa890ea72dab`

---

## Series Detail Page Layout

- Hero header section with action buttons row (lines 1200-1230)
- "Glossary" toggle button already exists (line 1209-1227), uses `showGlossary` state
- When `showGlossary === true`, renders `<GlossaryPanel seriesId={seriesId} />` (line 1262-1267)
- The `GlossaryPanel` component (lines 190-440) has: search, add form, edit inline, delete confirm

---

## Merge Logic Design

```python
def get_merged_glossary_for_series(self, series_id: int) -> list[dict]:
    """
    Returns merged glossary: global entries + per-series entries.
    Per-series entries OVERRIDE global entries with same source_term (case-insensitive).
    Limit: 30 entries total (15 global + 15 series-specific, deduped).
    """
    global_entries = {e["source_term"].lower(): e for e in self._get_global()}
    series_entries = {e["source_term"].lower(): e for e in self._get_series(series_id)}
    merged = {**global_entries, **series_entries}  # series overrides global
    return list(merged.values())[:30]
```

---

## Key Files to Modify

| File | Change |
|------|--------|
| `backend/db/models/translation.py` | Make `series_id` nullable |
| `backend/db/repositories/translation.py` | Add `get_global_glossary()`, `get_merged_glossary_for_series()` |
| `backend/db/translation.py` | Expose new repo methods as module-level functions |
| `backend/db/migrations/versions/<new>.py` | Migration to ALTER series_id to nullable |
| `backend/routes/profiles.py` | Allow null series_id in GET/POST glossary routes |
| `backend/translator.py` | Use `get_merged_glossary_for_series()` instead of `get_glossary_for_series()` |
| `frontend/src/api/client.ts` | Allow `seriesId=null` in glossary API functions |
| `frontend/src/pages/Settings/TranslationTab.tsx` | Add GlobalGlossaryPanel section |
| `frontend/src/hooks/useApi.ts` (if exists) | Add hook for global glossary |

---

## RESEARCH COMPLETE
