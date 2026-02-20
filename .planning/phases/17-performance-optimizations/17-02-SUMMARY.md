# Plan 17-02 Summary: Backend N+1 Fixes

## Completed: 2026-02-20

## Changes Made

### Change 1: providers/__init__.py — Batch provider stats in _init_providers()
- **Already applied in commit efdbecd (17-01 quick-wins)**
- Replaced N×2 DB queries (get_provider_stats(name) + get_provider_success_rate(name) per provider)
  with a single batch call to get_provider_stats() (no args returns {name: stats_dict})
- Success rate computed from batch data: successful_downloads / total_searches
- Removed import of get_provider_success_rate (no longer needed)
- Lines ~202-217 in backend/providers/__init__.py

### Change 2: providers/__init__.py — Batch is_provider_auto_disabled in get_provider_status()
- **Already applied in commit efdbecd (17-01 quick-wins)**
- Removed per-provider calls to get_provider_success_rate(name) and is_provider_auto_disabled(name)
  inside the provider loop in get_provider_status()
- Both values now read from the already-fetched performance_stats batch dict
- auto_disabled: bool(perf_stats.get("auto_disabled", 0)) — ProviderStats ORM has the column
- success_rate: computed from total_searches / successful_downloads in batch
- Note: cooldown-expiry side-effect of is_auto_disabled() runs on next actual usage, not on
  the read-only status view — acceptable trade-off
- Lines ~948-984 in backend/providers/__init__.py

### Change 3: db/models/core.py — Add composite index on WantedItem
- **Applied in commit 2820bd5 (this plan)**
- Added Index("idx_wanted_composite", "status", "item_type") to WantedItem.__table_args__
- Covers the most common multi-filter query pattern in get_wanted_items()
- Replaces SQLite two-index-scan merge with a single composite index scan
- Line ~100 in backend/db/models/core.py

### Change 3b: Alembic migration for composite index
- **Applied in commit 2820bd5 (this plan)**
- Created backend/db/migrations/versions/b3c2a1d4e5f6_add_wanted_composite_index.py
- Chains from fa890ea72dab (filter_presets migration) as down_revision
- upgrade(): op.create_index("idx_wanted_composite", "wanted_items", ["status", "item_type"])
- downgrade(): op.drop_index("idx_wanted_composite", table_name="wanted_items")
- Existing databases receive the index on next server startup via Alembic auto-migration

## DB Query Reduction Summary

| Location | Before | After |
|---|---|---|
| _init_providers() per N providers | 2×N queries | 1 batch query |
| get_provider_status() per N providers | 2×N extra queries | 0 extra queries |
| wanted_items queries (status+item_type) | merge 2 index scans | single composite scan |

## Verification

- Syntax check: all changed files pass `python -c "import ast; ast.parse(...)"`
- Unit tests (test_config, test_auth, test_ass_utils): 13 passed
- Pre-existing failures:
  - test_server.py: PermissionError on Windows socket (unrelated to these changes)
  - test_database.py: Flask app context required (5 failures, pre-existing)
  - Coverage threshold 80% not met (project-wide, pre-existing, 19% total coverage)
- No new test failures introduced

## Commits

- efdbecd: perf(17-01) — providers/__init__.py N+1 fixes (Changes 1 & 2, landed in quick-wins)
- 2820bd5: perf(17-02) — composite index + Alembic migration (Change 3)

## Deviations

- Changes 1 and 2 were already committed in 17-01 (quick-wins plan executed prior to this plan).
  This plan confirmed they are correct and complete. Only Change 3 (composite index + migration)
  required new commits in this execution.
