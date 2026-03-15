# Fansub Scoring Integration — Design Spec

**Date:** 2026-03-15
**Status:** Approved

## Overview

Extend Fansub Preferences to support standalone series, wire per-series fansub rules into the automatic processing pipeline, fix the Settings tab placement, and reduce the per-series UI from a prominent panel to a small toolbar button with modal.

---

## Problem Statement

1. **Standalone series excluded from per-series fansub rules.** `wanted_search.py` only checks `sonarr_series_id` when looking up per-series prefs.
2. **`fansub_preferences` table only supports Sonarr.** The PK is `sonarr_series_id` — no column for standalone series IDs.
3. **`process_wanted_item` (scheduler/automatic path) never applies Layer 2 per-series fansub rules.** Only the interactive `search_wanted_item` function applies them. Scheduled and batch downloads use `search_and_download_best` directly, which skips Layer 2 entirely. This affects all series (Sonarr and standalone).
4. **Per-series panel is too prominent.** `SeriesFansubPrefsPanel` renders as a full card section on every series detail page.
5. **Release group fields in wrong Settings tab.** They are hardcoded into the Wanted tab render path; they belong in the Scoring tab alongside HI/Forced Preference.

---

## Architecture — Two Independent Layers

```
ProviderManager.search()                    ← Layer 1: Global
  → release_group_prefer/exclude/bonus from config
  → Applied to ALL searches, already functional

wanted_search.py: _apply_fansub_rules()     ← Layer 2: Per-Series
  → Looked up from fansub_preferences table
  → Applied additively on top of Layer 1
  → Currently: search_wanted_item() only
  → After this spec: process_wanted_item() also
```

Both layers run additively. A per-series rule does not suppress global rules.

---

## Design Decisions

| Decision | Choice |
|----------|--------|
| Layer interaction | Additive — both layers always run |
| Standalone support | Add `standalone_series_id` column to `fansub_preferences` |
| `process_wanted_item` gap | Fix it — add Layer 2 lookup to automatic pipeline |
| Settings placement | Move 3 fields from hardcoded Wanted block → `ScoringTab` component |
| Per-series UI | Small toolbar button + modal, replaces current panel |
| Movie fansub overrides | Out of scope — table remains series-only |

---

## Backend Changes

### 1. `backend/wanted_search.py` — extend fansub lookup in both search paths

**In `search_wanted_item()`** (interactive UI path, lines ~542–554), replace:
```python
series_id = item.get("sonarr_series_id")
if series_id:
    fansub = FansubPreferenceRepository().get_fansub_prefs(series_id)
    if fansub:
        _apply_fansub_rules(...)
```

With a helper call `_apply_series_fansub_rules(all_results, item)` (see below).

**In `process_wanted_item()`** (automatic pipeline), add `_apply_series_fansub_rules()` between obtaining results and selecting the best. Since `process_wanted_item` currently calls `search_and_download_best()` (which returns a single downloaded result), refactor that step to:
1. Call `search_with_fallback()` to get the ranked result list
2. Call `_apply_series_fansub_rules(results, item)` to apply Layer 2
3. Re-sort results: `results.sort(key=lambda r: (0 if r.format == ASS else 1, -r.score))`
4. Iterate and download the best

**New helper:**
```python
def _apply_series_fansub_rules(results: list, item: dict) -> None:
    """Apply per-series fansub rules (Layer 2) in-place if configured."""
    repo = FansubPreferenceRepository()
    fansub = None
    if sonarr_id := item.get("sonarr_series_id"):
        fansub = repo.get_fansub_prefs_by_sonarr(sonarr_id)
    elif standalone_id := item.get("standalone_series_id"):
        fansub = repo.get_fansub_prefs_by_standalone(standalone_id)
    if fansub:
        _apply_fansub_rules(
            results,
            preferred=fansub["preferred_groups"],
            excluded=fansub["excluded_groups"],
            bonus=fansub["bonus"],
        )
```

### 2. `backend/db/models/core.py` — `FansubPreference` table

Current: `sonarr_series_id` is the primary key. SQLite does not support in-place PK changes, so the migration must recreate the table.

New schema:
```python
class FansubPreference(Base):
    __tablename__ = "fansub_preferences"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sonarr_series_id: Mapped[int | None] = mapped_column(Integer, nullable=True, unique=True)
    standalone_series_id: Mapped[int | None] = mapped_column(Integer, nullable=True, unique=True)
    preferred_groups_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    excluded_groups_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    bonus: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)
```

Invariant (enforced at repository level): exactly one of `sonarr_series_id` / `standalone_series_id` must be non-null per row.

### 3. `backend/db/repositories/fansub_prefs.py`

Rename existing method and add standalone equivalents. All methods query by column value, not PK:

```python
def get_fansub_prefs_by_sonarr(self, sonarr_series_id: int) -> dict | None:
    row = self.session.query(FansubPreference).filter_by(sonarr_series_id=sonarr_series_id).first()
    ...

def set_fansub_prefs_by_sonarr(self, sonarr_series_id: int, preferred, excluded, bonus) -> None:
    now = datetime.utcnow().isoformat()
    existing = self.session.query(FansubPreference).filter_by(sonarr_series_id=sonarr_series_id).first()
    if existing:
        existing.preferred_groups_json = json.dumps(preferred)
        existing.excluded_groups_json = json.dumps(excluded)
        existing.bonus = bonus
        existing.updated_at = now
    else:
        self.session.add(FansubPreference(
            sonarr_series_id=sonarr_series_id,
            preferred_groups_json=json.dumps(preferred),
            excluded_groups_json=json.dumps(excluded),
            bonus=bonus,
            updated_at=now,
        ))

def delete_fansub_prefs_by_sonarr(self, sonarr_series_id: int) -> None: ...

# Mirror of the above three for standalone_series_id
def get_fansub_prefs_by_standalone(self, standalone_series_id: int) -> dict | None: ...
def set_fansub_prefs_by_standalone(self, standalone_series_id: int, preferred, excluded, bonus) -> None: ...
def delete_fansub_prefs_by_standalone(self, standalone_series_id: int) -> None: ...
```

Keep `get_fansub_prefs(series_id)` as a deprecated alias for `get_fansub_prefs_by_sonarr(series_id)` to avoid breaking any callers outside `wanted_search.py`.

### 4. `backend/routes/fansub_prefs.py`

Update existing routes to use renamed repository methods. Add standalone routes:

```
GET    /api/v1/series/<id>/fansub-prefs              (Sonarr, existing)
PUT    /api/v1/series/<id>/fansub-prefs              (Sonarr, existing)
DELETE /api/v1/series/<id>/fansub-prefs              (Sonarr, existing)
GET    /api/v1/standalone/series/<id>/fansub-prefs   (new)
PUT    /api/v1/standalone/series/<id>/fansub-prefs   (new)
DELETE /api/v1/standalone/series/<id>/fansub-prefs   (new)
```

Standalone routes register under the existing `/api/v1/standalone` blueprint.

### 5. Database migration (Alembic)

SQLite requires table-rename pattern for PK changes:

```python
def upgrade():
    op.execute("""
        CREATE TABLE fansub_preferences_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sonarr_series_id INTEGER UNIQUE,
            standalone_series_id INTEGER UNIQUE,
            preferred_groups_json TEXT NOT NULL DEFAULT '[]',
            excluded_groups_json TEXT NOT NULL DEFAULT '[]',
            bonus INTEGER NOT NULL DEFAULT 20,
            updated_at TEXT NOT NULL DEFAULT ''
        )
    """)
    op.execute("""
        INSERT INTO fansub_preferences_new
            (sonarr_series_id, preferred_groups_json, excluded_groups_json, bonus, updated_at)
        SELECT
            sonarr_series_id,
            preferred_groups_json,
            excluded_groups_json,
            bonus,
            COALESCE(updated_at, datetime('now'))
        FROM fansub_preferences
    """)
    op.execute("DROP TABLE fansub_preferences")
    op.execute("ALTER TABLE fansub_preferences_new RENAME TO fansub_preferences")

def downgrade():
    # Standalone rows are dropped on downgrade; only Sonarr rows preserved
    op.execute("""
        CREATE TABLE fansub_preferences_old (
            sonarr_series_id INTEGER PRIMARY KEY,
            preferred_groups_json TEXT NOT NULL DEFAULT '[]',
            excluded_groups_json TEXT NOT NULL DEFAULT '[]',
            bonus INTEGER NOT NULL DEFAULT 20,
            updated_at TEXT
        )
    """)
    op.execute("""
        INSERT INTO fansub_preferences_old
        SELECT sonarr_series_id, preferred_groups_json, excluded_groups_json, bonus, updated_at
        FROM fansub_preferences
        WHERE sonarr_series_id IS NOT NULL
    """)
    op.execute("DROP TABLE fansub_preferences")
    op.execute("ALTER TABLE fansub_preferences_old RENAME TO fansub_preferences")
```

### 6. Settings — move fields from Wanted block to ScoringTab component

**`frontend/src/pages/Settings/index.tsx`:** Remove the hardcoded key array in the Wanted tab render block:
```tsx
// REMOVE this SettingsCard from the isWantedTab branch:
<SettingsCard title="Release Group Filter" ...>
  {['release_group_prefer','release_group_exclude','release_group_prefer_bonus']
    .map(k => FIELDS.find(f => f.key === k)!).filter(Boolean).map(renderField)}
</SettingsCard>
```

**`frontend/src/pages/Settings/EventsTab.tsx` — `ScoringTab` component:** Add a new `SettingsCard` section at the bottom of `ScoringTab`:
```tsx
<SettingsCard title="Release Group Filter"
  description="Boost preferred groups and block unwanted ones during provider search">
  {['release_group_prefer','release_group_exclude','release_group_prefer_bonus']
    .map(k => FIELDS.find(f => f.key === k)!).filter(Boolean).map(renderField)}
</SettingsCard>
```

`ScoringTab` must import `FIELDS`, `renderField`, and `SettingsCard` (or accept them as props — match the existing pattern used by other special-case tabs in the file).

---

## Frontend Changes

### 1. `SeriesDetail.tsx` — remove Fansub Preferences panel

Remove the `{/* Fansub Preferences Panel */}` block entirely (the `SeriesFansubPrefsPanel` card section).

### 2. `SeriesDetail.tsx` — add Fansub toolbar button

In the actions toolbar row (next to "Tracks extrahieren", "Bereinigen", "Export ZIP"):
```tsx
<FansubOverrideButton seriesId={seriesId} source={seriesData?.source ?? 'sonarr'} />
```

### 3. New component: `FansubOverrideButton`

Location: `frontend/src/components/series/FansubOverrideButton.tsx`

- Renders a small button labelled "Fansub"
- Selects hook based on `source` prop:
  - `'standalone'` → `useStandaloneFansubPrefs(seriesId)` / `useSetStandaloneFansubPrefs` / `useDeleteStandaloneFansubPrefs`
  - anything else → `useSeriesFansubPrefs(seriesId)` / `useSetSeriesFansubPrefs` / `useDeleteSeriesFansubPrefs`
- Active state (teal/accent): `prefs?.preferred_groups.length > 0 || prefs?.excluded_groups.length > 0`
- Inactive state (grey): empty lists or no override row in DB
- On click: opens `FansubOverrideModal`

### 4. New component: `FansubOverrideModal`

Location: `frontend/src/components/series/FansubOverrideModal.tsx`

Content:
- Heading: "Fansub Override — this series only"
- Read-only global defaults row: displays `settings.release_group_prefer` and `settings.release_group_exclude` (split by comma, joined as comma list). Data source: `useConfig()` or passed in as props.
- Preferred Groups input (comma-separated, placeholder from global value)
- Blocked Groups input (comma-separated, placeholder from global value)
- Bonus Points number input (default: `settings.release_group_prefer_bonus`)
- Save button (calls set mutation)
- "Reset to Global" button (calls delete mutation, resets local state to empty)
- Modal pattern: `role="dialog"`, `aria-modal="true"`, `aria-labelledby` on heading, `autoFocus` on first input, backdrop click and Escape close

### 5. `api/client.ts` + `hooks/useApi.ts`

Add standalone fansub API functions and TanStack Query hooks mirroring the existing Sonarr ones:
- `getStandaloneFansubPrefs(seriesId)` → `GET /api/v1/standalone/series/<id>/fansub-prefs`
- `setStandaloneFansubPrefs(seriesId, prefs)` → `PUT /api/v1/standalone/series/<id>/fansub-prefs`
- `deleteStandaloneFansubPrefs(seriesId)` → `DELETE /api/v1/standalone/series/<id>/fansub-prefs`
- `useStandaloneFansubPrefs(seriesId)` — query hook, `queryKey: ['standalone-fansub-prefs', seriesId]`
- `useSetStandaloneFansubPrefs(seriesId)` — mutation hook, invalidates above query key on success
- `useDeleteStandaloneFansubPrefs(seriesId)` — mutation hook, invalidates above query key on success

---

## Test Coverage

New or extended tests in `tests/test_fansub_prefs.py`:

1. **`_apply_series_fansub_rules()` — Sonarr branch**: item with `sonarr_series_id`, repo returns prefs → rules applied
2. **`_apply_series_fansub_rules()` — standalone branch**: item with `standalone_series_id`, repo returns prefs → rules applied
3. **`_apply_series_fansub_rules()` — no override**: item with no series ID → function is no-op, no exception
4. **`process_wanted_item` integration**: verify Layer 2 rules are applied in the automatic pipeline path
5. **Migration**: verify existing Sonarr rows survive upgrade; `sonarr_series_id` values intact; `standalone_series_id` is NULL for migrated rows; downgrade restores original schema and drops standalone rows cleanly

---

## File Summary

| File | Change |
|------|--------|
| `backend/wanted_search.py` | Extract `_apply_series_fansub_rules()` helper; use in both `search_wanted_item` and `process_wanted_item` |
| `backend/db/models/core.py` | Add `standalone_series_id`, change PK to auto-increment |
| `backend/db/repositories/fansub_prefs.py` | Rename to `by_sonarr`/`by_standalone`; keep alias for old name |
| `backend/routes/fansub_prefs.py` | Update + add standalone routes under `/api/v1/standalone` blueprint |
| `backend/db/migrations/versions/<hash>_fansub_standalone.py` | Table-rename migration with explicit downgrade |
| `frontend/src/pages/Settings/index.tsx` | Remove 3-field hardcoded block from Wanted tab render |
| `frontend/src/pages/Settings/EventsTab.tsx` | Add Release Group Filter card to `ScoringTab` |
| `frontend/src/pages/SeriesDetail.tsx` | Remove panel, add `FansubOverrideButton` to toolbar |
| `frontend/src/components/series/FansubOverrideButton.tsx` | New component |
| `frontend/src/components/series/FansubOverrideModal.tsx` | New component |
| `frontend/src/api/client.ts` | Add standalone fansub API functions |
| `frontend/src/hooks/useApi.ts` | Add standalone fansub hooks |

---

## Out of Scope

- Movie-level fansub overrides (table remains series-only — intentional)
- Per-episode fansub rules
- Regex matching for group names (keep substring match)
- UI showing which rule was applied to a past search result
- Changing the additive two-layer model to exclusive override at the provider layer
