# Plan 17-02: Backend N+1 Fixes — Provider Stats Batch + Composite DB Index

## Goal
Fix the two most impactful backend performance issues:
1. N+1 DB queries when initializing providers (2 queries × N providers → 1 batch query)
2. Add composite DB index on wanted_items for multi-filter queries

## Changes

### 1. backend/providers/__init__.py — Batch provider stats in _init_providers()

Current code (lines ~204-212) issues 2 separate DB queries per provider:
```python
for name in enabled_set:
    if name in _PROVIDER_CLASSES:
        stats = get_provider_stats(name)        # DB hit #1
        if stats and stats.get("total_searches", 0) >= 10:
            success_rate = get_provider_success_rate(name)  # DB hit #2
```

Fix: fetch all stats in one call before the loop.
`get_provider_stats()` without a name argument returns ALL provider stats as a dict.
Use it to build a lookup before the loop:

```python
# Before loop: single batch query
all_stats = get_provider_stats()  # returns dict {name: stats_dict}

for name in enabled_set:
    if name in _PROVIDER_CLASSES:
        stats = all_stats.get(name)
        if stats and stats.get("total_searches", 0) >= 10:
            success_rate = stats.get("success_rate", 0.0)  # from batch, no extra query
```

Check the signature of get_provider_stats() in backend/db/repositories/providers.py
to confirm it returns all-providers dict when called without args, or adapt accordingly.

### 2. backend/providers/__init__.py — Batch is_provider_auto_disabled in get_provider_status()

Current code (lines ~965-994) calls is_provider_auto_disabled(name) per provider inside a loop,
despite having already called get_provider_stats() for batch data at line ~962.

Fix: check auto_disabled flag from the batch stats dict instead of separate per-provider calls.
`get_provider_stats()` already returns stats including auto_disabled info — use it.

```python
# Already fetched:
performance_stats = get_provider_stats()  # line ~962

for name, cls in _PROVIDER_CLASSES.items():
    # Old: auto_disabled = is_provider_auto_disabled(name)  # extra DB query
    # New: read from already-fetched batch data
    pstats = performance_stats.get(name, {})
    auto_disabled = pstats.get("auto_disabled", False)
```

If is_provider_auto_disabled returns data not in get_provider_stats(), check
backend/db/repositories/providers.py and either extend the batch query or add the
field to the stats dict.

### 3. backend/db/models/core.py — Add composite index on WantedItem

Current single-column indexes (lines ~94-99):
```python
Index("idx_wanted_status", "status"),
Index("idx_wanted_item_type", "item_type"),
Index("idx_wanted_sonarr_series", "sonarr_series_id"),
```

Add a composite index for the most common multi-filter query pattern
(status + item_type together, used by get_wanted_items()):

```python
Index("idx_wanted_composite", "status", "item_type"),
```

This replaces the need for SQLite to merge two single-column index scans.
Keep the individual indexes for single-column queries.

After adding the index to the model, create an Alembic migration or add it to
the schema initialization so existing databases get the index too.
Check backend/db/ for migration system (alembic/ or schema init script).

## Verification
- Run: `cd backend && python -m pytest tests/ -v`
- Provider init: add timing log temporarily, confirm <100ms for stats batch
- wanted list query: EXPLAIN QUERY PLAN should show "USING INDEX idx_wanted_composite"
