# Fansub Scoring Integration — Design Spec

**Date:** 2026-03-15
**Status:** Approved

## Overview

Redesign Fansub Preferences to integrate properly into the scoring pipeline with a global default and an optional per-series override. Fix the standalone series bug. Reduce the per-series UI from a prominent panel to a small toolbar button with modal.

---

## Problem Statement

1. **Global fields exist but are not wired.** `release_group_prefer`, `release_group_exclude`, and `release_group_prefer_bonus` exist in `config.py` and the Settings UI (Wanted tab), but `_apply_fansub_rules()` in `wanted_search.py` never reads them — they are dead config.
2. **Standalone series are excluded.** `wanted_search.py` line ~543 only applies fansub prefs when `sonarr_series_id` is set. Standalone series (`standalone_series_id` only) never get fansub rules applied.
3. **Per-series panel is too prominent.** `SeriesFansubPrefsPanel` renders as a full card section on every series detail page regardless of whether the user has configured anything.
4. **Wrong Settings tab.** Release group fields live in the Wanted tab, but conceptually they are score modifiers like HI Preference and Forced Preference, which live in the Scoring tab.

---

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Global vs per-series | Global default + per-series override (replaces) | 80% of users want one rule set; power users can override per series |
| Per-series merge strategy | Override **replaces** global entirely for that series | Simple, no surprising interactions |
| Settings placement | Move to Scoring tab | Consistent with HI/Forced Preference which also adjust scores |
| Per-series UI | Small toolbar button + modal | Not prominent, but accessible when needed |

---

## Architecture

### Scoring Pipeline — New Flow

```
search_wanted_item(item)
  → collect all provider results
  → resolve fansub rules:
      if series has per-series override → use override
      else → use global config (release_group_prefer/exclude/bonus)
  → _apply_fansub_rules(results, rules)   ← same function, no change
  → sort by priority key
  → return results
```

The `_apply_fansub_rules()` function itself is unchanged — it already does case-insensitive substring matching, +bonus for preferred groups, −999 for excluded groups.

---

## Backend Changes

### 1. `backend/wanted_search.py`

Replace the current block (lines ~542–554):
```python
# CURRENT (broken)
series_id = item.get("sonarr_series_id")
if series_id:
    fansub = FansubPreferenceRepository().get_fansub_prefs(series_id)
    if fansub:
        _apply_fansub_rules(...)
```

With a new helper `_resolve_fansub_rules(item, settings)` that:
1. Checks `sonarr_series_id` → `FansubPreferenceRepository().get_fansub_prefs(sonarr_id)`
2. Falls back to `standalone_series_id` → `FansubPreferenceRepository().get_fansub_prefs_standalone(standalone_id)`
3. Falls back to global config:
   ```python
   preferred = [g.strip() for g in settings.release_group_prefer.split(",") if g.strip()]
   excluded  = [g.strip() for g in settings.release_group_exclude.split(",") if g.strip()]
   bonus     = settings.release_group_prefer_bonus
   ```
4. Always calls `_apply_fansub_rules()` (even if lists are empty — no-op).

### 2. `backend/db/models/core.py` — `FansubPreference` table

Add a nullable `standalone_series_id` column. The table currently has `sonarr_series_id` as the primary key; change to a surrogate auto-increment PK and add a unique constraint per source:

```python
class FansubPreference(Base):
    __tablename__ = "fansub_preferences"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sonarr_series_id: Mapped[int | None] = mapped_column(Integer, nullable=True, unique=True)
    standalone_series_id: Mapped[int | None] = mapped_column(Integer, nullable=True, unique=True)
    preferred_groups_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    excluded_groups_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    bonus: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False, default=...)
```

Constraint: exactly one of `sonarr_series_id` / `standalone_series_id` must be non-null (enforced at repository level).

### 3. `backend/db/repositories/fansub_prefs.py`

Add:
- `get_fansub_prefs_standalone(standalone_series_id: int) -> dict | None`
- `set_fansub_prefs_standalone(standalone_series_id, preferred, excluded, bonus)`
- `delete_fansub_prefs_standalone(standalone_series_id)`

### 4. `backend/routes/fansub_prefs.py`

Current endpoints are keyed to Sonarr series ID:
```
GET/PUT/DELETE /api/v1/series/<id>/fansub-prefs
```

Add standalone equivalents:
```
GET/PUT/DELETE /api/v1/standalone/series/<id>/fansub-prefs
```

The existing Sonarr-keyed routes remain unchanged.

### 5. Database migration

New Alembic migration:
- Add `standalone_series_id` column (nullable int)
- Add unique index on `standalone_series_id`
- Change PK from `sonarr_series_id` to auto-increment `id`
- Make `sonarr_series_id` nullable (was non-nullable PK)

### 6. Settings — move fields from Wanted to Scoring tab

In `frontend/src/pages/Settings/index.tsx`, change `tab` from `'Wanted'` to `'Scoring'` for:
- `release_group_prefer`
- `release_group_exclude`
- `release_group_prefer_bonus`

Also update the Scoring tab section grouping to include a "Release Group Filtering" section header.

---

## Frontend Changes

### 1. `SeriesDetail.tsx` — remove Fansub Preferences panel

Remove the `{/* Fansub Preferences Panel */}` block (currently renders `SeriesFansubPrefsPanel` as a full card section). Replace with nothing — the panel is gone.

### 2. `SeriesDetail.tsx` — add Fansub toolbar button

In the actions toolbar row (next to "Tracks extrahieren", "Bereinigen", "Export ZIP"), add:

```tsx
<FansubOverrideButton seriesId={seriesId} source={seriesData.source} />
```

Button states:
- **No override set** → grey icon + label "Fansub", tooltip "Using global defaults"
- **Override active** → teal/accent color + label "Fansub", tooltip shows configured groups

### 3. New component: `FansubOverrideButton`

Location: `frontend/src/components/series/FansubOverrideButton.tsx`

Responsibilities:
- Renders the toolbar button
- On click, opens `FansubOverrideModal`
- Uses `useSeriesFansubPrefs(seriesId)` / `useStandaloneFansubPrefs(seriesId)` based on `source`
- Visual state: teal when override active, grey when using global

### 4. New component: `FansubOverrideModal`

Location: `frontend/src/components/series/FansubOverrideModal.tsx`

Content:
- "Override for this series" heading
- Read-only info row: "Global: SubsPlease, Erai-raws" (from settings)
- Preferred Groups input (comma-separated)
- Blocked Groups input (comma-separated)
- Bonus Points number input
- Save button + "Reset to Global" button (deletes the override)
- Follows existing Modal pattern: `role="dialog"`, `aria-modal`, backdrop click to close, Escape to close

### 5. `api/client.ts` + `hooks/useApi.ts`

Add:
- `getStandaloneFansubPrefs(seriesId)`
- `setStandaloneFansubPrefs(seriesId, prefs)`
- `deleteStandaloneFansubPrefs(seriesId)`
- `useStandaloneFansubPrefs(seriesId)` hook
- `useSetStandaloneFansubPrefs(seriesId)` hook
- `useDeleteStandaloneFansubPrefs(seriesId)` hook

---

## File Summary

| File | Change |
|------|--------|
| `backend/wanted_search.py` | Replace series-only fansub block with `_resolve_fansub_rules()` helper |
| `backend/db/models/core.py` | Add `standalone_series_id` column, change PK |
| `backend/db/repositories/fansub_prefs.py` | Add standalone CRUD methods |
| `backend/routes/fansub_prefs.py` | Add `/standalone/series/<id>/fansub-prefs` routes |
| `backend/db/migrations/versions/...` | Migration: schema change on `fansub_preferences` |
| `frontend/src/pages/Settings/index.tsx` | Move 3 fields from Wanted → Scoring tab |
| `frontend/src/pages/SeriesDetail.tsx` | Remove panel, add `FansubOverrideButton` to toolbar |
| `frontend/src/components/series/FansubOverrideButton.tsx` | New component |
| `frontend/src/components/series/FansubOverrideModal.tsx` | New component |
| `frontend/src/api/client.ts` | Add standalone fansub API functions |
| `frontend/src/hooks/useApi.ts` | Add standalone fansub hooks |

---

## Out of Scope

- Movie-level fansub overrides (only series for now)
- Per-episode fansub rules
- Regex matching for group names (keep substring match)
- UI to show which rule was applied to a past search result
