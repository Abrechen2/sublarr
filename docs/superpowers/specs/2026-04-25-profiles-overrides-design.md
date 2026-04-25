# Profiles & Overrides — Design Spec

**Status:** Approved (brainstorming, 2026-04-25)
**Author:** Claude / Dennis
**Codex Template:** Settings Template C — `RulesLayout`
**Target Release:** 0.73.0-beta (or 0.72.x patch series)

## Summary

A new top-level Settings page **Profiles & Overrides** that gives Sublarr a
true Codex Template C reference: a scope tree (Global → Profile → Series /
Movie) with a detail pane showing every inheritable setting as an
`InheritanceRow` with effective value, source label, and inline override
widget.

Replaces the existing `LanguageProfilesTab` (currently inside
`SubtitlesSettings`) and the standalone `/language-profiles` route. Profile
CRUD becomes part of the new page's scope-tree header.

## Goals

- Land the third Codex Settings template (`RulesLayout`) as a real
  user-facing page, not just a primitive — completing the trio
  General/FormLayout · Providers/CollectionLayout · Profiles/RulesLayout.
- Make the actual three-level inheritance chain (Global → LanguageProfile →
  Series/Movie) visible and editable in one place. Today this chain is
  invisible to users; per-series cleanup_foreign_tracks (0.71.1) is the
  only override they can see, and only deep inside SeriesDetail.
- Add per-series and per-movie overrides for eight more LanguageProfile
  fields so the inheritance pattern actually has anything to override.
- Single home for everything profile-related: list, create, edit, delete,
  assign — and inspect what each setting resolves to for a given scope.

## Non-Goals (Deferred to Future Work)

The following items are intentionally out of scope for this implementation
and should remain so unless explicitly re-prioritised:

- **DEF-1: Audit log** — "who changed which override when" trail.
  Implementation idea: append-only `override_history` table; surfaced as
  an accordion below the rules list. Worth doing only if multi-user setups
  become real.
- **DEF-2: Bulk overrides** — selecting multiple series/movies in the tree
  and applying the same override to all. Useful when a user wants to set
  the same `forced_preference` on a batch of anime series. UI: shift-click
  multi-select on tree, override widget gains a "Apply to N selected"
  affordance.
- **DEF-3: Per-episode overrides** — fourth scope level (Series → Episode).
  Requires new `episode_settings` table, tree UX with potentially hundreds
  of episode rows per series. Almost certainly overkill — only revisit if
  concrete user demand emerges.
- **DEF-4: Quiet-Hours policies as Template C** — second consumer of
  `RulesLayout` for the notification-quiet-hours feature. Currently lives
  in NotificationsSettings as a flat form. Migration to RulesLayout with
  scope = Global → per-channel → per-event would land here when the
  notification feature matures.
- **DEF-5: HealthRail integration** — RulesLayout supports a third column
  for `<HealthRail>` ("missing required override", "profile drift" etc.).
  No clear "defekter Status" concept exists for inheritance today; defer
  until concrete signals emerge that warrant such a rail.
- **DEF-6: Movie-only fields** — `absolute_order` (Anime-specific) and
  `processing_config` (not yet productive) are Series-only in v1. If a
  movie-specific equivalent emerges later, mirror as needed.
- **DEF-7: E2E Playwright tests** — covered by unit + integration tests
  in v1; add Playwright journey for the page in the 0.7x-follow-up release.
- **DEF-8: i18n EN review** — DE primary, EN mirror. Native-speaker EN
  review pass deferred — same approach as elsewhere in Sublarr.
- **DEF-9: Search-index entries** — adding the 12 inheritable fields per
  scope to the Settings global search (`settingsRegistry.ts`) is in v1
  scope, but per-scope dynamic entries (e.g. "Frieren / forced_preference")
  are deferred — too many entries, low signal-to-noise.

## Decisions

| # | Decision | Rationale |
|---|---|---|
| 1 | Scope hierarchy: **Global → LanguageProfile → Series / Movie** | Matches existing data model (`SeriesLanguageProfile`, `MovieLanguageProfile`). Three levels gives genuine inheritance UX without exploding into per-episode noise. |
| 2 | Settings bundle: **12 inheritable fields** (Mid bundle) | Covers the most common "why does subtitle search behave wrong for THIS series?" pain points. Lean (6) was too small to demonstrate inheritance over Profile-level fields; Comprehensive (20+) was a backend tax for fields users will never override. |
| 3 | **Series + Movies in parallel** | Codex mockup explicitly mentions per-Movie overrides. New `movie_settings` table mirrors `series_settings` (minus `absolute_order`). |
| 4 | New page **absorbs Profile CRUD** | Tree-as-central-hub is Codex' actual vision — Profile IS a node in the scope tree, edit lives in the tree header. Old `LanguageProfilesTab` and standalone `/language-profiles` route are deleted (the latter 301-redirected). |
| 5 | **Approach 2: All-Settings-Stack** | Pragmatic over Codex' featured-setting pose. Scope picked → all 12 InheritanceRows stacked. Inline override widget per row. Faster to use, fully reuses existing `<InheritanceRow>` primitive. |

## Architecture

### Page Layout

```
Settings → Profiles & Overrides         (route: /settings/profiles)
┌──────────── 320px ──────────┬─────────── 1fr ─────────────┐
│ ▶ ◉ Global default          │ Header strip                │
│ ▼ ◐ Anime DE        ⋮       │   scope-name + type badge   │
│   ▦ Attack on Titan         │   breadcrumb chain          │
│   ▦ Frieren           ←sel  │ ──────────────────────────  │
│ ▼ ◐ Live Action     ⋮       │ All settings (12 rows):     │
│   ◎ Solo Leveling           │ ┌───────────────────────┐   │
│ ─── Series (no profile) ──  │ │ cleanup_foreign_tracks│   │
│   ▦ <unassigned series 1>   │ │   inherited from Profile  │
│ ─── Movies (no profile) ──  │ │   effective: Off [Override]│
│ + Add profile               │ │ … 11 more rows        │   │
│                             │ └───────────────────────┘   │
│                             │ [Reset all overrides]       │
└─────────────────────────────┴─────────────────────────────┘
```

Built with the existing `RulesLayout` primitive — `scopeTree`-slot for the
left tree, `overrideWidget`-slot for the stacked InheritanceRows (Approach
2 maps the 12 rows into the override slot since `resolvedHeader` is just
the scope-name strip in this design). `healthRail` slot stays empty in v1.

### URL state

`?scope=<type>:<id>` — examples:
- `?scope=global`
- `?scope=profile:1`
- `?scope=series:42`
- `?scope=movie:13`

Refresh preserves selection (Codex Convention 5).

### Inheritance Resolution

New module `backend/services/inheritance_resolver.py`. Two pure functions:

```python
def resolve_for_series(series_id: int) -> dict[str, ResolvedSetting]: …
def resolve_for_movie(movie_id: int)  -> dict[str, ResolvedSetting]: …
```

Algorithm: walk the chain Global → Profile → Series (or Global → Profile →
Movie) per inheritable field. First non-NULL value wins. The chain is
returned in full so the UI can show every step, not just the winner.

`ResolvedSetting` shape:

```jsonc
{
  "effective": <any>,
  "source": "global" | "profile" | "series" | "movie",
  "chain": [
    {"scope": "global",  "value": <raw>, "label": "Global default"},
    {"scope": "profile", "value": <raw>, "label": "Anime DE"},
    {"scope": "series",  "value": <raw>, "label": "Frieren"}
  ]
}
```

`INHERITABLE_FIELDS` registry table (declared once, referenced by resolver,
API schemas and FE):

| display_name | profile_attr | series/movie override col | global config key |
|---|---|---|---|
| `cleanup_foreign_tracks` | — | `cleanup_foreign_tracks` | `cleanup_foreign_tracks_default` |
| `forced_preference` | `forced_preference` | `forced_preference_override` | `forced_preference_default` |
| `hi_preference` | `hi_preference` | `hi_preference_override` | `hi_preference_default` |
| `forced_scoring` | `forced_scoring` | `forced_scoring_override` | `forced_scoring_default` |
| `target_languages` | `target_languages_json` | `target_languages_override` | `target_languages_default` |
| `cutoff_language` | `cutoff_language` | `cutoff_language_override` | — |
| `must_contain` | `must_contain_json` | `must_contain_override` | — |
| `must_not_contain` | `must_not_contain_json` | `must_not_contain_override` | — |
| `audio_exclude_languages` | `audio_exclude_languages_json` | `audio_exclude_languages_override` | — |
| `preferred_audio_track_index` | — | `preferred_audio_track_index` | — |
| `priority_override` | — | `priority_override` | `priority_default` |
| `min_attempts_per_day` | — | `min_attempts_per_day` | — |

## Backend Schema

### New columns on `series_settings`

8 new TEXT/JSON nullable columns; existing rows get NULL on add (= inherit
from profile, falling through to global).

```sql
ALTER TABLE series_settings ADD COLUMN forced_preference_override          TEXT NULL;
ALTER TABLE series_settings ADD COLUMN hi_preference_override              TEXT NULL;
ALTER TABLE series_settings ADD COLUMN forced_scoring_override             TEXT NULL;
ALTER TABLE series_settings ADD COLUMN target_languages_override           TEXT NULL;  -- JSON array
ALTER TABLE series_settings ADD COLUMN cutoff_language_override            TEXT NULL;
ALTER TABLE series_settings ADD COLUMN must_contain_override               TEXT NULL;  -- JSON array
ALTER TABLE series_settings ADD COLUMN must_not_contain_override           TEXT NULL;  -- JSON array
ALTER TABLE series_settings ADD COLUMN audio_exclude_languages_override    TEXT NULL;  -- JSON array
```

Naming: `<field>_override` — deliberate suffix to make the override slot
visually distinct from the LanguageProfile field of the same name. Existing
non-suffixed `cleanup_foreign_tracks` and `priority_override` are kept for
backwards compatibility (their semantics already match: NULL = inherit).

### New table `movie_settings`

```sql
CREATE TABLE movie_settings (
  radarr_movie_id              INTEGER PRIMARY KEY,
  preferred_audio_track_index  INTEGER NULL,
  cleanup_foreign_tracks       BOOLEAN NULL,
  priority_override            VARCHAR(20) NULL,
  min_attempts_per_day         INTEGER NOT NULL DEFAULT 0,
  forced_preference_override          TEXT NULL,
  hi_preference_override              TEXT NULL,
  forced_scoring_override             TEXT NULL,
  target_languages_override           TEXT NULL,
  cutoff_language_override            TEXT NULL,
  must_contain_override               TEXT NULL,
  must_not_contain_override           TEXT NULL,
  audio_exclude_languages_override    TEXT NULL,
  updated_at                   TIMESTAMP NOT NULL
);
CREATE INDEX ix_movie_settings_updated ON movie_settings (updated_at);
```

`absolute_order` and `processing_config` deliberately omitted from the
movie table — see DEF-6.

### Migration

`backend/db/migrations/versions/<rev>_profiles_overrides_phase1.py`

- 8× idempotent `op.add_column` on `series_settings` — each guarded by
  `Inspector.has_column()` because `_patch_pre_alembic_columns` in
  `app.py` may have already created some at first start
- `op.create_table('movie_settings', …)` guarded by `has_table()`
- Index on `movie_settings.updated_at`
- Down path: `drop_column` × 8 + `drop_table('movie_settings')`
  (cosmetic — drops user data, but Alembic semantics)

Memory lessons applied:
- `feedback_alembic_pitfalls.md` — `IF NOT EXISTS` pattern via inspector
- Single revision file, no chain trick
- `feedback_no_shortcuts.md` — full schema in one go, not incremental

## API Surface

New blueprint `routes/profiles_overrides.py` registered at
`/api/v1/profiles-overrides/`.

| Method | Path | Body / Query | Returns |
|---|---|---|---|
| GET  | `/scopes` | — | `{ profiles: [{ id, name, is_default, series:[…], movies:[…] }], unassigned_series:[…], unassigned_movies:[…] }` |
| GET  | `/resolved/global` | — | resolved settings for Global scope |
| GET  | `/resolved/profile/<id>` | — | resolved settings for a Profile scope |
| GET  | `/resolved/series/<id>` | — | full chain resolved for one series |
| GET  | `/resolved/movie/<id>`  | — | full chain resolved for one movie |
| PATCH | `/series/<id>` | `{ field: value\|null }` | 200 + new resolved or 422 if validation fails |
| PATCH | `/movie/<id>`  | `{ field: value\|null }` | 200 + new resolved |
| POST | `/series/<id>/reset` | — | clears all 12 override fields |
| POST | `/movie/<id>/reset`  | — | clears all 12 override fields |

`null` value in PATCH body → reset that override to inherit. Pydantic
schemas whitelist the 12 known override fields and validate per-field type
(JSON arrays validated against ISO-2 language whitelist, enums against
allowed values, etc.).

Profile CRUD endpoints (`/api/v1/language-profiles/*`) stay unchanged and
are reused by the new page's tree-header CRUD menu.

## Frontend Components

```
frontend/src/pages/Settings/
├── ProfilesOverridesPage.tsx            (~120 LOC)
└── profilesOverrides/
    ├── ScopeTree.tsx                    (~180 LOC)
    ├── ScopeDetail.tsx                  (~130 LOC)
    ├── OverrideWidget.tsx               (~140 LOC)
    ├── ProfileEditDialog.tsx            (~150 LOC)
    ├── inheritanceFields.ts             (~80 LOC)
    ├── useScopesTree.ts                 (~25 LOC)
    ├── useResolved.ts                   (~25 LOC)
    ├── useOverrideMutations.ts          (~50 LOC)
    └── __tests__/
```

Modifications to existing files:
- `components/settings/SettingsNav.tsx` — add 6th entry "Profiles & Overrides"
- `components/settings/settingsRegistry.ts` — register the page + 12 fields (per-scope dynamic search entries deferred — DEF-9)
- `App.tsx` — `/settings/profiles` route + 301-redirect from `/language-profiles`
- `pages/LanguageProfiles.tsx` — **delete** (top-level page goes away)
- `pages/Settings/SubtitlesLanguagesPage.tsx` — remove `<LanguageProfilesTab />` usage
- `pages/Settings/LanguageProfilesTab.tsx` — **delete** (CRUD logic moves to ProfileEditDialog)
- `pages/Settings/AdvancedTab.tsx` — drop dead reference
- `pages/__tests__/LanguageProfiles.test.tsx` — rewrite as `ProfileEditDialog.test.tsx`

API client: new module `frontend/src/api/profilesOverrides.ts` with
`getScopesTree`, `getResolved`, `patchOverride`, `resetOverrides`.

### Override widgets (per field type)

| Type | Fields | Widget |
|---|---|---|
| `boolean` | `cleanup_foreign_tracks` | TriStateToggle (Inherit / Off / On) — extracts state-machine from existing `SeriesSettingsPanel` cleanup-toggle pattern |
| `enum` | `forced_preference`, `hi_preference`, `forced_scoring`, `priority_override` | Select with first option "Inherit (Profile/Global)" |
| `language` | `cutoff_language` | Single-language picker, empty = inherit |
| `language[]` | `target_languages`, `audio_exclude_languages` | `LanguagePillSelector` (existing primitive), empty array = inherit |
| `string[]` | `must_contain`, `must_not_contain` | Tag-input (chip-style), empty = inherit |
| `integer` | `preferred_audio_track_index`, `min_attempts_per_day` | Number input + "Inherit"-reset button |

State management: server-state via React Query, URL-state via
`useSearchParams`, no local stores. Optimistic updates for PATCH with
on-error rollback.

## Edge Cases

| Scenario | Behaviour |
|---|---|
| Delete profile while series/movies are assigned | DB `ON DELETE CASCADE` drops mappings → series fall into "no profile" tree section. UI confirm dialog: "N series + M movies will fall to 'no profile', continue?" |
| Series with no profile assignment | Tree shows in "Series (no profile)" section. Detail chain shows `Global → (no profile) → Series` — profile row is `null` with hint "no profile assigned". Resolution skips profile step. |
| Delete default profile | Block — backend returns 409 "cannot delete default profile, set another as default first". |
| Delete the last profile | Allowed. All series/movies fall to "no profile". Confirm dialog with count. |
| Concurrent override edits in two tabs | Single-field PATCH, no optimistic-lock collision. React-Query refetches after mutation, picks new server value. |
| Invalid JSON array (e.g. `target_languages_override: '["xx"]'`) | Pydantic validates ISO-2 codes against whitelist → 422; UI shows FormGroup error. |
| Backend 404 (series removed from Sonarr mid-edit) | `useResolved` error → empty state "Series not found, removed from Sonarr?" with refresh button. |
| Migration first run | `_patch_pre_alembic_columns` + idempotent `add_column` guards keep startup safe. |
| Profile rename while user is editing | Tree refetch after profile PATCH; selected scope id stays valid → header re-renders with new name, no selection loss. |

## Validation

- API boundary: Pydantic schemas in `routes/profiles_overrides.py` —
  whitelist of allowed override fields per scope-type, per-field type
  validation
- Frontend boundary: Zod schemas in `api/profilesOverrides.ts` matching the
  Pydantic shape, parse-on-receive
- Schema mismatch FE/BE → emits a Sentry warning; UI shows empty-state
  rather than crashing

## Testing

### Backend (pytest, ~60 new tests)
- `tests/test_inheritance_resolver.py` — resolver chain walks, all 12
  fields, edge cases (~25 tests)
- `tests/test_routes_profiles_overrides.py` — 8 new endpoints, auth,
  validation, 404/409 (~30 tests)
- `tests/test_migrations_profiles_overrides.py` — Alembic up/down, idempotent
  re-run on SQLite-in-memory (~5 tests)
- existing `tests/test_routes_language_profiles.py` keeps running unchanged

### Frontend (Vitest, ~60 new tests)
- `ScopeTree.test.tsx` (~15)
- `ScopeDetail.test.tsx` (~12)
- `OverrideWidget.test.tsx` — all six variants (~15)
- `ProfileEditDialog.test.tsx` (~10)
- `ProfilesOverridesPage.test.tsx` — integration (~8)

Coverage target: 80%+ per new file. Migration test verifies schema. E2E
deferred (DEF-7).

### Pre-deploy gate
```bash
cd backend && ruff check . && ruff format --check . && python -m pytest --tb=short -q --ignore=tests/performance
cd frontend && npm run lint && npx tsc --noEmit && npm run test -- --run
```

## i18n

Keys `settings.profiles_overrides.*` — DE primary + EN mirror per
CLAUDE.md language policy. EN review pass deferred to DEF-8.

## Memory lessons applied

- `feedback_alembic_pitfalls.md` — idempotent `add_column` via inspector
- `feedback_protected_ui.md` — existing SeriesSettingsPanel cleanup-toggle
  is PROTECTED. Logic extracted into `<TriStateToggle>` primitive; existing
  component unchanged.
- `feedback_design_standards.md` — SettingsSection / FormGroup / CSS-var
  tokens / pure Tailwind per Strategic-Tailwind policy
- `feedback_no_shortcuts.md` — full backend schema landed in one go, no
  incremental MVP sub-cuts
- `feedback_ui_workflow.md` — single tab per cycle, missing backend fields
  are explicit plan steps within this design

## Implementation order (preview for plan phase)

1. Backend schema + migration (idempotent)
2. Inheritance resolver service + unit tests
3. New API blueprint + integration tests
4. Frontend API client + Zod schemas
5. RulesLayout primitives wired up: ScopeTree, ScopeDetail, OverrideWidget
6. ProfileEditDialog + tree-header CRUD menu
7. Page assembly + URL state + a11y
8. SettingsNav entry + redirects + delete legacy files
9. i18n keys (DE + EN mirror)
10. Pre-deploy gate run

Detailed implementation plan to be created via the `writing-plans` skill in
the next phase.

## Approval

Brainstorming completed 2026-04-25 with five-section section-by-section
approval. User signed off on:
- Section 1 — Page Architecture
- Section 2 — Backend Schema
- Section 3 — Resolution + API
- Section 4 — Frontend Components
- Section 5 — Edge Cases + Testing
