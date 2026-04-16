# API-Budget Scheduler — V1 Blocker Feature

**Created:** 2026-04-16
**Status:** Planning — blocks V1 stable release
**Target version:** V1.0.0
**Current version:** 0.51.17-beta

## Context — why this blocks V1

A production audit on 2026-04-16 found three interlocking bugs that make the current Wanted-Scheduler unfit for V1:

1. **3919 of 5007 wanted items (78%) have `search_count = 0`** — they were never searched. Root cause: the scheduler processes only `wanted_search_max_items_per_run = 50` items per 24h run, and `db/repositories/wanted.py` returns them sorted `added_at DESC`. Newer items crowd out older ones indefinitely. At this rate a full rotation takes ~100 days.

2. **33 items are stuck in `Max search attempts reached`** despite subtitles being available for 2 of them (verified against provider APIs). The current flow increments `search_count` on *any* search outcome — including transient provider errors (circuit breaker OPEN, HTTP 429, timeout). Once `search_count ≥ wanted_max_search_attempts`, the item freezes permanently.

3. **Provider API limits are ignored**. A single scheduler tick fires ~500 API calls across 10 providers. OpenSubtitles Free-Tier caps at 1000 calls/day — two scheduler runs exhaust it, further calls return HTTP 429, which (per bug #2) poisons affected items.

These are correctness bugs, not feature gaps. V1 cannot ship with 78% of the user's library silently ignored and items randomly frozen by flaky network weather.

## Goals

1. **Fair scheduling**: every wanted item is eventually searched, regardless of library size
2. **Resilient failure handling**: no item gets permanently frozen by transient provider issues
3. **Explicit provider-budget awareness**: Sublarr self-throttles to real API limits, adapts to observed 429s
4. **Hardware scalability**: usable from Raspberry Pi to multi-core server without code changes
5. **User visibility**: budget state is visible in the dashboard; surprising behaviors are surfaced, not hidden
6. **No regression**: existing automations (webhooks, manual search, upgrade scheduler) keep working

## Non-goals

- Replacing the existing provider system (keep `providers/*.py` as-is — only add rate-limit metadata and budget hooks)
- Implementing new subtitle providers
- Touching the translation/LLM pipeline (separate concern)
- Rewriting the circuit breaker (`circuit_breaker.py`) — budget and circuit breaker are orthogonal and coexist

## Architecture

The feature has four load-bearing components:

### 1. Item Selection (Phase 1)
`services/wanted_search_runner.py::run_wanted_search` picks items via `get_wanted_items(page=1, per_page=max_items, status="wanted")`. We change:
- **Ordering** becomes preset-driven via a new `wanted_search_order` setting: `fair` (default, `last_search_at ASC NULLS FIRST, search_count ASC`), `newest_first` (current behavior), `weighted` (new episodes <30d first, then fair)
- **`max_items_per_run`** remains as a safety cap but is no longer the primary rate control — the budget system is

### 2. Failure State Machine (Phase 1)
`_filter_eligible` and `update_wanted_search` separate two outcomes:
- **`no_result`**: provider responded with empty result → increment `search_count`, set `retry_after` via light backoff
- **`provider_error`**: circuit breaker, 429, timeout, connection error → **do NOT increment** `search_count`; set `retry_after` via exponential backoff (6h → 24h → 3d → 7d → 30d)

`wanted_max_search_attempts` still exists but triggers a *permanent-slow-mode* (1x/month) instead of freezing. Removing the freeze is the whole point.

### 3. Provider Budget System (Phase 1 infrastructure, Phase 2 UX)
Every provider declares its own rate limits as class metadata:

```python
class OpenSubtitlesProvider(SubtitleProvider):
    rate_limits: ClassVar[dict[str, dict]] = {
        "free": {"daily": 1000, "hourly": 200, "per_second": 5},
        "vip":  {"daily": 10000, "hourly": 1000, "per_second": 10},
    }
```

A new `ProviderBudgetManager` (`services/provider_budget.py`) tracks three windows per provider (second, hour, day) in Redis (fast path) mirrored to Postgres (persistence). Before a provider call, the budget gate returns `allow | wait_seconds | exhausted`. On `exhausted`, the coordinator skips that provider for that item (no error — just one fewer source), and sets `retry_after` on the item to the next budget reset.

### 4. Self-Learning (Phase 3)
When a provider returns HTTP 429 despite our counter saying budget is free, the `ProviderBudgetManager` records the observed limit in `provider_learned_limits` and applies a `0.9x` adjustment factor. After 7 consecutive days without 429, the factor ramps back toward 1.0 in 0.02 steps.

## Data model

### New table: `provider_budget_usage`

Sliding-window counters. Redis holds the live state; this table is the durable source truth for restart recovery and dashboard queries.

```sql
CREATE TABLE provider_budget_usage (
    id              SERIAL PRIMARY KEY,
    provider_name   VARCHAR(50) NOT NULL,
    window_type     VARCHAR(10) NOT NULL,   -- 'second' | 'hour' | 'day'
    window_start    TIMESTAMPTZ NOT NULL,
    calls_used      INTEGER NOT NULL DEFAULT 0,
    calls_limit     INTEGER NOT NULL,
    UNIQUE (provider_name, window_type, window_start)
);

CREATE INDEX ix_budget_provider_window
    ON provider_budget_usage (provider_name, window_type, window_start DESC);
```

### New table: `provider_learned_limits`

Adaptive limit learning from real 429s.

```sql
CREATE TABLE provider_learned_limits (
    provider_name        VARCHAR(50) NOT NULL,
    window_type          VARCHAR(10) NOT NULL,
    configured_limit     INTEGER     NOT NULL,
    observed_limit       INTEGER,
    adjustment_factor    REAL        NOT NULL DEFAULT 1.0,
    last_429_at          TIMESTAMPTZ,
    consecutive_good_days INTEGER    NOT NULL DEFAULT 0,
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (provider_name, window_type)
);
```

### New table: `provider_account_pools` (Phase 4)

Multi-API-key pools for budget aggregation.

```sql
CREATE TABLE provider_account_pools (
    id              SERIAL PRIMARY KEY,
    provider_name   VARCHAR(50)  NOT NULL,
    account_label   VARCHAR(100) NOT NULL,   -- user-friendly ("primary", "backup")
    api_key         VARCHAR(500) NOT NULL,
    tier            VARCHAR(20)  NOT NULL,   -- 'free' | 'vip' | 'vip+' etc.
    enabled         BOOLEAN      NOT NULL DEFAULT TRUE,
    calls_today     INTEGER      NOT NULL DEFAULT 0,
    last_used_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (provider_name, account_label)
);
```

### `wanted_items` additions

```sql
ALTER TABLE wanted_items
    ADD COLUMN priority       VARCHAR(20) NOT NULL DEFAULT 'standard'
        CHECK (priority IN ('premium', 'standard', 'backlog')),
    ADD COLUMN failure_kind   VARCHAR(20),   -- 'no_result' | 'provider_error' | NULL
    ADD COLUMN error_count    INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN last_error_at  TIMESTAMPTZ;

-- New indexes for fair-rotation query planner
CREATE INDEX ix_wanted_fair_rotation
    ON wanted_items (status, last_search_at NULLS FIRST, search_count);

CREATE INDEX ix_wanted_retry_after
    ON wanted_items (status, retry_after)
    WHERE retry_after IS NOT NULL;
```

### New config entries (via Pydantic Settings + DB config_entries)

| Key | Type | Default | Purpose |
|---|---|---|---|
| `wanted_search_order` | str | `fair` | One of `fair | newest_first | weighted` |
| `wanted_search_max_items_per_run` | int | **500** (was 50) | Safety cap per run |
| `scheduler_profile` | str | `balanced` | One of `light | balanced | aggressive | custom` |
| `provider_budget_enabled` | bool | `true` | Master toggle |
| `provider_budget_stretch_mode` | str | `stretch` | `stretch | burst | adaptive` |
| `provider_budget_safety_margin_pct` | int | `20` | Leave X% headroom below declared limit |

## Phase breakdown

Each phase produces a separately executable plan document before execution, written with TDD-level task detail. The master list:

### Phase 1 — Foundation (blocker fixes + budget infrastructure)

**Plan doc:** `docs/superpowers/plans/2026-04-16-phase-1-scheduler-foundation.md`

- Reset all `Max search attempts reached` items (data migration)
- Implement fair-rotation sort in item selection
- Add `wanted_search_order` setting + UI preset dropdown
- Split failure handling: `no_result` vs `provider_error` with exponential backoff
- Add `rate_limits` metadata to every provider class
- Implement `ProviderBudgetManager` service with Redis + DB backing
- Integrate budget gate into `SearchCoordinator.search`
- Remove the permanent-freeze behavior of `max_search_attempts`; replace with slow-mode
- Alembic migration: new tables + wanted_items columns + indexes

**Exit criteria:**
- Zero items in `Max attempts reached` state on prod DB
- Every wanted item has `last_search_at` within the expected rotation window
- Budget counters visible via new `/api/v1/system/budget` endpoint
- All existing tests pass + new TDD tests for the 5 listed components

### Phase 2 — User-Facing (wizard + dashboard + stretch mode)

**Plan doc (to be written at start of phase):** `docs/superpowers/plans/2026-04-XX-phase-2-user-facing.md`

- First-run wizard component (frontend): benchmark screen → profile picker → apply
- First-run wizard trigger: shown on v0.51 → V1 upgrade via version-stamped localStorage flag + backend hint
- Dashboard widget: provider-budget bars + reset countdown + queue ETA
- Settings page: scheduler profile dropdown, order preset, provider-level budget overrides
- Implement stretch mode (gleichmäßige Verteilung über 24h) as the default scheduling pattern
- SocketIO live updates: `provider_budget_updated` event emitted on every budget change

**Exit criteria:**
- First-run wizard completable in <60 seconds
- Dashboard shows all enabled providers with live budget state
- Changing profile applies immediately (no restart)

### Phase 3 — Intelligence (self-learning + advanced modes)

**Plan doc (to be written at start of phase):** `docs/superpowers/plans/2026-04-XX-phase-3-intelligence.md`

- Self-learning: detect 429 → reduce internal limit by 10% → store in `provider_learned_limits`
- Recovery: 7 consecutive days without 429 → ramp adjustment factor back toward 1.0
- Burst mode (front-load budget in first N hours after reset)
- Adaptive mode: detect Sonarr upload patterns, align budget peaks to expected demand
- Priority weighting: `premium` items consume budget first, `backlog` only if >50% remains

**Exit criteria:**
- Test scenario: simulated 429 storm reduces configured limit within 1 cycle and recovers within 7 days of clean data
- Priority weights correctly re-order the eligible queue

### Phase 4 — Power-User (pooling, overrides, cost)

**Plan doc (to be written at start of phase):** `docs/superpowers/plans/2026-04-XX-phase-4-power-user.md`

- Multi-API-key account pools per provider (`provider_account_pools`), round-robin key rotation
- Per-series budget override (stored in `series_settings`)
- Cost tracking for paid tiers (OS VIP pricing, subdl Pro, etc.)
- Multi-Sublarr-instance budget sharing via Redis pub/sub channel

**Exit criteria:**
- User can add 2 OS API keys, observe combined budget 2x expected single-key value
- Series marked `premium-override` consumes more than its proportional share

### Phase 5 — Validation

**Plan doc (to be written at start of phase):** `docs/superpowers/plans/2026-04-XX-phase-5-validation.md`

- Spin up ProxMox CT with 1 CPU core + 512 MB RAM for low-end baseline
- Run full 5007-item library against it with each profile
- Migration dry-run: backup prod DB, apply on staging, run for 48h, diff activity_log
- Wiki updates for every new setting (aligned with `wiki_audit_settings.py`)
- CHANGELOG + release notes for V1

**Exit criteria:**
- Low-end CT completes a full rotation within 7 days with zero errors
- All new settings documented in wiki
- Migration rehearsal on staging completes without manual intervention

## Migration strategy

One-shot data migration runs as part of the Alembic upgrade that adds the new tables:

```sql
-- Reset frozen items
UPDATE wanted_items
SET search_count = 0,
    error = NULL,
    retry_after = NULL,
    failure_kind = NULL,
    error_count = 0
WHERE error = 'Max search attempts reached';

-- Seed the three default priority tiers based on added_at
UPDATE wanted_items
SET priority = 'premium'
WHERE added_at >= NOW() - INTERVAL '7 days';

UPDATE wanted_items
SET priority = 'backlog'
WHERE search_count >= 3 AND added_at < NOW() - INTERVAL '180 days';
```

First-run wizard shown to existing users via version-stamped hint from `/api/v1/system/v1-migration-status` — the frontend checks once per session until the user explicitly dismisses or completes.

## Testing strategy

| Test type | Scope | Framework |
|---|---|---|
| Unit | Every new class/method | pytest |
| Integration | Budget manager ↔ Redis ↔ Postgres | pytest + testcontainers |
| Integration | SearchCoordinator ↔ BudgetManager end-to-end | pytest |
| Regression | Existing scheduler paths must still work | existing test suite + new fixtures |
| E2E | First-run wizard completion flow | Playwright |
| Load | 5007-item library rotation under each profile | custom script in `scripts/load_test_scheduler.py` |
| Chaos | Simulate 429 responses, provider outages, Redis unavailability | pytest fixtures injecting faults |

Coverage target: every new module ≥ 90% (foundation code); overall backend coverage delta must be positive.

## Rollback plan

- The Alembic migration is reversible: `alembic downgrade -1` removes new tables, restores `wanted_items` shape, does *not* unfreeze items (they stay reset, which is desirable).
- Feature flag `provider_budget_enabled = false` disables the new gate entirely — SearchCoordinator falls back to the pre-V1 behavior (call every provider, ignore budget).
- Docker image versioning allows immediate rollback: `ghcr.io/abrechen2/sublarr:0.51.17-beta` stays available; if V1 misbehaves, user pulls that tag.

## Open questions

- **Stretch vs. Burst default for the "Aggressive" profile?** Tentative: Stretch for all profiles to avoid rate-limit spikes; user opts in to Burst manually. Revisit in Phase 3.
- **Webhook-triggered urgent searches**: should these bypass the budget gate? Proposed: yes, with a small dedicated reserve (5% of daily budget).
- **Redis availability**: the core system works without Redis (DB-only mode), but stretch/burst timing precision degrades. Decide in Phase 2 whether to surface this as a setting or auto-detect.
