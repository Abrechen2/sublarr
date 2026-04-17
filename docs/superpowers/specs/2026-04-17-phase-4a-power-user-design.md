# Phase 4a — Power-User (Multi-Key Pools + Per-Series Overrides) Design

**Date:** 2026-04-17
**Status:** Spec
**Parent spec:** `docs/superpowers/specs/2026-04-16-api-budget-scheduler-v1.md` (Phase 4 — Power-User)
**Plan doc (next):** `docs/superpowers/plans/2026-04-XX-phase-4a-power-user.md` (to be created via `superpowers:writing-plans`)

---

## Scope

**In scope (this phase):**
1. **Multi-API-key account pools** per provider with budget-aware selection across keys.
2. **Per-series overrides**: priority override (premium/standard/backlog) + minimum-attempts-per-day guarantee.

**Deferred to Phase 4b:**
- Cost / subscription-utilization tracking. To be rescoped then; flat-rate subscriptions (OS VIP, subdl Pro) don't fit the original per-call "cost" model.
- Multi-instance Redis pub/sub budget sharing. Speculative until multi-Sublarr-instance becomes a real use case.

**Out of scope:**
- Per-key learning (Phase 3's adjustment_factor stays provider-level). Revisit in Phase 4b if per-key 429 patterns diverge.
- Bulk key import (CSV / JSON upload). Single-add UI only.

## Exit criteria

1. Adding a 2nd OpenSubtitles key with `tier="vip"` doubles the aggregate day-budget reported by `GET /api/v1/system/budget` (10,000 → 20,000) and the per-key breakdown shows both keys at 0 used.
2. A series with `priority_override="premium"` and `min_attempts_per_day=5` is always included in the first 5 eligible items of every scheduler tick, even when the backlog-reserve gate is active.
3. All Phase 1/2/3 behaviour preserved: existing single-key setups continue to work via auto-migration without user action.

## Data Model

### New table: `provider_account_pools`

Replaces the single env-var-per-provider model with a row-per-key model. Same shape as the DDL sketched in the parent spec at lines 107-124, with minor extensions (`username`, `password` for the few providers that still need non-key credentials; `last_429_at` for per-key cooldown).

```sql
CREATE TABLE provider_account_pools (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,   -- SERIAL on Postgres
    provider_name   VARCHAR(50)  NOT NULL,
    account_label   VARCHAR(100) NOT NULL,       -- user-chosen ("primary" / "backup")
    api_key         VARCHAR(500) NOT NULL,       -- plaintext; matches config_entries policy
    username        VARCHAR(200),                -- nullable; OS only
    password        VARCHAR(500),                -- nullable; OS only
    tier            VARCHAR(20)  NOT NULL DEFAULT 'free',
    enabled         BOOLEAN      NOT NULL DEFAULT TRUE,
    last_used_at    DATETIME,
    last_429_at     DATETIME,
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (provider_name, account_label)
);
CREATE INDEX ix_pool_provider ON provider_account_pools (provider_name, enabled);
```

### `wanted_series` / `series_settings` additions

Two nullable / zero-default columns. The plan phase will verify whether a dedicated `series_settings` table already exists (part of Sonarr-facing series metadata) and add them there; if no such table exists the plan creates it.

```sql
ALTER TABLE <series_settings>
    ADD COLUMN priority_override    VARCHAR(20)
        CHECK (priority_override IN ('premium','standard','backlog')),
    ADD COLUMN min_attempts_per_day INTEGER NOT NULL DEFAULT 0;
```

- `priority_override` NULL → use item-level priority (Phase 1 default).
- `priority_override` non-NULL → wins over item-level priority in `get_items_for_scheduled_search`'s rank CASE.
- `min_attempts_per_day=0` → no guarantee (default).
- `min_attempts_per_day>0` → runner prefix this many oldest-searched items from this series into every tick's eligible list before the standard ordering.

### Migration (`alembic upgrade head`)

One-shot migration:
1. Create `provider_account_pools` + index.
2. Add the two series-settings columns.
3. Data backfill: for every provider with a non-empty API key in `config_entries` / env vars, insert one row (`account_label="primary"`, `tier=<detected by Phase 1>`).
4. Empty-key providers: skipped; flip provider `enabled=false` in `config_entries` (logged).

Pattern matches `b1u2d3g4e5t6_phase1_scheduler_foundation.py` seed approach.

### Per-key usage accounting

`ProviderBudgetManager` gains a second counter dimension:
- **Aggregate (existing):** `_counts[(provider, window, window_start)] → int` — sum across all keys.
- **Per-key (new):** `_counts_per_key[(provider, key_id, window, window_start)] → int`.

`GET /api/v1/system/budget` response delta:

```json
{
  "name": "opensubtitles",
  "tier": "vip",                   // highest tier across enabled keys (vip+ > vip > free)
  "limits": { ... },                // sum of tier-specific limits across enabled keys
  "usage":  { ... },                // aggregate counts across all keys
  "reset_seconds": { ... },
  "learning": { ... },              // unchanged — provider-level
  "keys": [                         // NEW — one entry per enabled key
    { "id": 1, "label": "primary", "tier": "vip",
      "used": { "second": 0, "hour": 5, "day": 120 },
      "limit": { "second": 10, "hour": 1000, "day": 10000 },
      "last_429_at": null }
  ]
}
```

Concrete example with one VIP key (`10000/day`) + one free key (`200/day`):
- outer `tier` = `"vip"` (the highest enabled)
- outer `limits.day` = `10200` (sum)
- outer `usage.day` = sum of both keys' `day` usage
- `keys[]` has both entries with their respective per-tier limits

## Architecture

### Backend components

```
backend/
  db/
    models/core.py                         (+ ProviderAccountPool, series overrides)
    repositories/
      provider_account_pool.py             (NEW — CRUD + get_enabled_for helper)
      series_settings.py                   (extend — priority_override, min_attempts_per_day)
    migrations/versions/
      <hash>_phase4a_multi_key_pools.py    (NEW)
  services/
    provider_budget.py                     (extend — per-key counts + get_usage_per_key)
    key_selector.py                        (NEW — budget-aware key picker, 60s cache)
    wanted_search_runner.py                (extend — inject min-per-day slots before eligible)
  providers/
    __init__.py                            (ProviderManager loads keys from pool w/ env fallback)
    search_coordinator.py                  (asks KeySelector for key before each call)
  db/
    repositories/wanted.py                 (priority_override wins in rank CASE)
  routes/
    providers.py                           (extend GET; add POST/PATCH/DELETE /providers/<name>/keys)
    system/budget.py                       (surface per-key breakdown)
    library.py or series.py                (PATCH /series/<id>/settings for override + min_attempts)
```

### Key-selection flow (per provider call)

```
SearchCoordinator.search(query)
  └─► for each enabled provider:
        ├─► budget.check(provider, limits)               ← aggregate gate (unchanged)
        ├─► if allow:
        │     key = key_selector.pick(provider)
        │       └─► read enabled keys (in-memory, TTL 60s, invalidated by settings_changed signal)
        │       └─► filter: last_429_at < now - provider.retry_after_seconds
        │       └─► pick: max remaining day budget = tier.limits.day - per_key_used
        │       └─► None if all exhausted/throttled
        ├─► if key is None: skip provider this call, log at info
        ├─► provider.search(query, credentials=<from key row>)
        ├─► budget.consume(provider, key_id)             ← both aggregate + per-key
        └─► on ProviderRateLimitError:
              ├─► budget.record_429(provider, ...)       (Phase 3, unchanged — provider-level)
              └─► pool_repo.mark_429(key_id)             (NEW — per-key cooldown)
```

### Item-selection flow (per scheduler tick)

```
run_wanted_search()
  ├─► tick_recovery()                                     (Phase 3, unchanged)
  ├─► eligible_base = get_items_for_scheduled_search(
  │       limit, order, priority_weighting)
  │     └─► rank CASE now: COALESCE(priority_override, priority)
  ├─► min_per_day_slots = collect_min_attempts_items()    (NEW)
  │     └─► for each series with min_attempts_per_day > N
  │         where searches_today_for_series(s) < N
  │         return oldest-searched wanted_items for that series (up to remaining)
  ├─► eligible = dedup(min_per_day_slots + eligible_base) (prefix preserved)
  ├─► _apply_backlog_reserve_gate(eligible, ...)          (Phase 3 — must preserve
  │     min_per_day_slots even when gate drops backlog items)
  └─► dispatch to providers (honours budget + key selection above)
```

### UI

- **Settings → Providers → `<provider>`:** existing page gains a "Keys" section — list of rows showing label, tier badge, enabled toggle, last-used timestamp, per-key day-usage progress bar. Buttons: "Add key", "Edit", "Delete", "Test connection".
  - Add / Edit dialog: label, tier (select), api_key (password input), optional username + password (shown only for providers that need them — OS, legendasdivx).
  - Delete-last warning: "Deleting this will disable {provider}. Proceed?" — on confirm, the row delete is atomic with a `provider.enabled=false` config update.
- **Library → Series detail:** new "Settings" section (or extend the existing one) with:
  - Priority override: select with values `"Inherit" / "Premium" / "Standard" / "Backlog"`.
  - Min attempts per day: number input 0–20 (0 = default).
- **Dashboard budget widget:** unchanged visually; on hover / click, expands to show per-key rows from `/system/budget` response.

## Error Handling & Edge Cases

### Multi-key pool
- **All keys exhausted/throttled:** `KeySelector.pick()` returns None. Coordinator logs at `info`, skips provider. Same pattern as a single-key provider hitting its cap today.
- **Empty pool for an enabled provider:** fall through to legacy `config_entries` / env-var read for the migration grace window (1 major version). After that, removed.
- **Test-connection on add:** provider-specific probe (OS: `GET /api/v1/infos/formats`; subdl: `GET /version`). Failures block the save with a clear error; user can force-save via a "Save anyway" checkbox for providers without cheap probes.
- **Delete last key** for an enabled provider: frontend prompts "This will disable {provider}. Proceed?"; on confirm, delete + config flip are atomic (single transaction).
- **Pool edit during a scheduler tick:** 60s in-memory cache with a `settings_changed` invalidator. Worst case: one tick uses a stale credential; next tick picks up the change.
- **Per-key 429 cooldown:** `last_429_at` updated by `pool_repo.mark_429(key_id)`; `KeySelector` excludes rows with `last_429_at > now - provider.retry_after_seconds`. Phase 3's `adjustment_factor` stays provider-level — revisit per-key in Phase 4b if warranted.

### Per-series overrides
- **`min_attempts_per_day` + `priority_override="backlog"`:** min-per-day prefix is applied **before** the backlog reserve gate; those items survive. Documented semantics: "min-per-day is a hard floor that the backlog gate cannot override."
- **`min_attempts_per_day > len(wanted_items for series)`:** clamped to available; no error.
- **Series has all subs found:** min-per-day does nothing (no wanted rows to include).
- **Two series with `min=5` each, budget only allows 8 items this tick:** fill 5 from the oldest-searched series first, 3 from the second; log a warning (`"min_attempts_per_day: 2 items skipped for series X, budget exhausted"`).

### Migration
- **Partial rollout across a version boundary:** the alembic migration is backward-read-only for 1 version — code reads both `config_entries` and the pool table. Full cutover after the next major version.
- **Empty API key in `config_entries`:** skipped during seed; provider flipped to `enabled=false` (logged).
- **Dry-run on staging:** part of Phase 5 validation, not this phase.

## Testing Strategy

### Backend unit tests
- `test_provider_account_pool_repo.py` — CRUD, `UNIQUE(provider_name, account_label)`, `get_enabled_for(provider)`, `mark_429(key_id)`.
- `test_key_selector.py` — budget-aware pick, 429 cooldown filter, empty-pool → None, all-throttled → None, mixed-tier pool prefers VIP while it has budget.
- `test_provider_budget_per_key.py` — `consume(provider, key_id)` increments both aggregate + per-key; new `get_usage_per_key(provider)` returns `[{label, used, limit}, …]`.
- `test_wanted_repo_priority_override.py` — rank CASE uses `COALESCE(priority_override, priority)`; override wins; null override leaves item priority untouched.
- `test_wanted_search_runner_min_attempts.py` — min-per-day prefix applied before backlog gate; clamps to available items; two series compete gracefully (oldest-searched first); warning logged when budget insufficient.

### Backend integration tests
- `test_search_coordinator_multikey.py` — coordinator requests key from selector, passes it to `provider.search()`, consumes on the right `key_id`, handles `None` return by skipping.
- `test_migration_phase4a.py` — applies alembic upgrade on a DB seeded with `config_entries`; verifies one pool row per configured provider with `account_label="primary"`; verifies series_settings columns.

### E2E tests (`test_phase4a_e2e.py`)
- **Multi-key aggregate budget:** add a 2nd OS key with `tier="vip"` via the pool API → `/system/budget` reports aggregate `day: 0/20000` and per-key breakdown showing both keys at 0.
- **Per-series min-per-day guarantee:** series with `min_attempts_per_day=3`, 5 wanted items seeded plus 10 unrelated; `run_wanted_search(limit=8)` → first 3 outputs are from that series (oldest-searched), next 5 follow normal order.
- **Priority override wins:** wanted item whose series has `priority_override="premium"` lands in the first rank even when item's intrinsic `priority` is backlog.

### Frontend tests (Vitest)
- `KeysList.test.tsx` — rows render label/tier/enabled/last-used; "Add key" opens dialog; delete-last warning shown.
- `KeyEditDialog.test.tsx` — required-field validation; test-connection success/failure states; force-save path.
- `SeriesOverrideSettings.test.tsx` — priority override select + min-per-day number input; save disabled until a field changes.
- `BudgetWidget.test.tsx` — extend existing: on hover, per-key breakdown appears from `/system/budget` response.

### Pre-release verification
Full pytest sweep, ruff check + format, frontend lint + tsc + vitest, dev-server smoke. Tag `phase-4a-ready`. Same shape as Phase 3 Task 13.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| User deletes last key of a critical provider accidentally | Explicit delete-last confirmation; single-transaction delete + `enabled=false` |
| Legacy env-var keys + new pool rows drift out of sync | One-shot migration seeds pool from legacy; legacy is fallback-only; remove after 1 major |
| Per-key 429 cooldown excludes too eagerly, leaving no keys usable | `retry_after_seconds` comes from the provider's `ProviderRateLimitError`; selector falls back to the least-recently-429'd key when all are cooling down |
| Min-per-day items starve the regular queue | Warning logged when budget insufficient; cap visible in UI; default is 0 |
| Alembic migration is slow on large config_entries tables | Empty migration fires once; backfill reads config_entries (tiny table, <20 rows in practice) |
| Unique-constraint conflict on re-migration | Migration uses `ON CONFLICT DO NOTHING` equivalent; idempotent |

## Open questions for Phase 4b

- Should per-key learning (adjustment_factor per `(provider, key_id)` rather than just provider) replace provider-level learning? Only worth doing if we see per-key 429 divergence in prod.
- Subscription-utilization tracking: what data does the user actually find useful? (Requires a couple weeks of pool usage to answer.)
- Multi-instance Redis pub/sub: still deferred until multi-Sublarr becomes a real use case.
