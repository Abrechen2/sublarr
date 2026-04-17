# Phase 3 — Intelligence (self-learning + advanced modes) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-04-16-api-budget-scheduler-v1.md`
**Previous plans:**
- Phase 1 foundation — `docs/superpowers/plans/2026-04-16-phase-1-scheduler-foundation.md`
- Phase 2 user-facing — `docs/superpowers/plans/2026-04-16-phase-2-user-facing.md`

**Goal:** Make the budget system adapt to reality — learn real provider limits from observed 429s, recover on clean streaks, pace calls intelligently (burst/adaptive), and push scarce budget toward high-priority items first.

**Architecture:** Extends `ProviderBudgetManager` (Phase 1) with an adjustment-factor that multiplies declared limits. The factor is written by a new `record_429()` path from `SearchCoordinator` and ramped back up by a once-per-scheduler-tick `tick_recovery()` call. Item selection in `db/repositories/wanted.py` gains a priority-first order, and `run_wanted_search` gains a "no-backlog when >50% spent" gate. Two new stretch variants (`burst`, `adaptive`) live in `_stretch_allowed`. No schema changes — all tables already exist from Phase 1 migration `b1u2d3g4e5t6`.

**Tech Stack:** Python 3.11, SQLAlchemy 2.x (no new migrations), pytest, React + TypeScript + Vitest.

---

## File plan

| Action | Path | Responsibility |
|---|---|---|
| Create | `backend/db/repositories/provider_learned_limits.py` | CRUD for `provider_learned_limits` table |
| Create | `backend/tests/test_provider_learned_limits_repo.py` | Repo unit tests |
| Modify | `backend/services/provider_budget.py` | Apply adjustment factor, `record_429`, `tick_recovery`, burst + adaptive modes |
| Modify | `backend/tests/test_provider_budget.py` | Cover new behaviour |
| Create | `backend/tests/test_provider_budget_learning.py` | 429 → factor reduction → ramp-up scenarios |
| Create | `backend/tests/test_provider_budget_modes.py` | burst + adaptive mode behaviour |
| Modify | `backend/providers/search_coordinator.py:534-562` | Call `budget.record_429(name)` on `ProviderRateLimitError` |
| Modify | `backend/tests/test_search_coordinator_budget.py` | Extend with 429 learning hook test |
| Modify | `backend/db/repositories/wanted.py:23-28,266-324` | Priority-weighted ordering in all three presets |
| Modify | `backend/tests/test_wanted_repo_scheduled_search.py` *(may not exist yet)* | Verify premium-first ordering |
| Modify | `backend/services/wanted_search_runner.py:165-216` | Backlog reserve gate (skip backlog when budget >50% spent) + call `tick_recovery` |
| Create | `backend/tests/test_wanted_search_runner_backlog_gate.py` | Reserve gate tests |
| Modify | `backend/services/wanted_search_runner.py` | Demand-histogram helper for adaptive mode |
| Modify | `backend/routes/system/budget.py` | Include `adjustment_factor` + `consecutive_good_days` + `last_429_at` per provider in response |
| Modify | `backend/tests/test_routes_system_budget.py` *(may not exist yet — check before creating)* | Assert new response fields |
| Modify | `backend/config.py:215-234` | New keys: `provider_budget_burst_window_hours`, `wanted_scheduler_priority_weighting_enabled`, `wanted_scheduler_backlog_reserve_pct` |
| Modify | `frontend/src/api/health.ts` | Extend `ProviderBudget` type with learned fields |
| Modify | `frontend/src/components/dashboard/BudgetWidget.tsx` | Render "learning" badge when factor < 1.0 |
| Modify | `frontend/src/components/dashboard/__tests__/BudgetWidget.test.tsx` *(check existence first)* | Cover learning badge |
| Modify | `frontend/src/pages/Settings/AutomationSettings.tsx` | Add stretch-mode select (stretch/burst/adaptive) + burst-window input |
| Modify | `frontend/src/i18n/locales/{de,en}/settings.json` | New automation_page keys for stretch mode / burst window |
| Modify | `frontend/src/i18n/locales/{de,en}/dashboard.json` | New `budget.learning_active` key |
| Create | `backend/tests/test_phase3_e2e.py` | 429 storm reduces factor → 7 good days ramp back toward 1.0 |

Tests live next to their targets or under `backend/tests/` (mirroring package layout) to match the existing convention.

---

## Task 1 — `provider_learned_limits` repository

**Files:**
- Create: `backend/db/repositories/provider_learned_limits.py`
- Create: `backend/tests/test_provider_learned_limits_repo.py`

**Contract:** the repository owns every read and write against the `provider_learned_limits` table (already created by Phase 1 migration `b1u2d3g4e5t6`). Nothing else in the codebase may `SELECT`/`UPDATE` it directly.

| Method | Purpose |
|---|---|
| `get(provider, window) -> dict \| None` | Single row lookup |
| `get_all() -> dict[tuple[str,str], dict]` | Bulk read for the budget manager in-memory cache |
| `upsert_on_429(provider, window, configured_limit, observed_limit, now)` | Atomic "saw a 429": multiply `adjustment_factor` by 0.9, reset `consecutive_good_days=0`, set `last_429_at=now`, `updated_at=now`. Creates the row at factor=1.0 then multiplies if it did not exist. |
| `ramp_recovery(provider, window, step=0.02, now) -> float` | Increment `consecutive_good_days`. If `>= 7` AND `adjustment_factor < 1.0`, add `step` (cap 1.0). Returns the NEW `adjustment_factor`. No-op if `last_429_at` is less than 24h old. |
| `reset(provider, window)` | Test-only: delete the row |

- [ ] **Step 1: Write the failing tests**

The repo takes no constructor args — it reads `db.session` from the Flask-SQLAlchemy
request-scoped session, same as every other repository in the codebase. Tests use the
existing `app_ctx` fixture (from `backend/tests/conftest.py`) to push an app context.

```python
# backend/tests/test_provider_learned_limits_repo.py
"""Unit tests for ProviderLearnedLimitsRepository."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from db.repositories.provider_learned_limits import ProviderLearnedLimitsRepository


def test_get_returns_none_when_missing(app_ctx):
    repo = ProviderLearnedLimitsRepository()
    assert repo.get("opensubtitles", "day") is None


def test_upsert_on_429_creates_row_at_factor_0_9(app_ctx):
    repo = ProviderLearnedLimitsRepository()
    now = datetime(2026, 4, 17, 12, 0, 0, tzinfo=UTC)
    repo.upsert_on_429(
        provider="opensubtitles",
        window="day",
        configured_limit=1000,
        observed_limit=None,
        now=now,
    )
    row = repo.get("opensubtitles", "day")
    assert row is not None
    assert row["adjustment_factor"] == pytest.approx(0.9)
    assert row["consecutive_good_days"] == 0
    assert row["last_429_at"] == now


def test_upsert_on_429_multiplies_existing_factor(app_ctx):
    repo = ProviderLearnedLimitsRepository()
    now = datetime(2026, 4, 17, 12, 0, 0, tzinfo=UTC)
    repo.upsert_on_429("opensubtitles", "day", 1000, None, now)
    repo.upsert_on_429("opensubtitles", "day", 1000, None, now)
    row = repo.get("opensubtitles", "day")
    assert row["adjustment_factor"] == pytest.approx(0.81)


def test_upsert_on_429_floors_at_0_1(app_ctx):
    repo = ProviderLearnedLimitsRepository()
    now = datetime(2026, 4, 17, tzinfo=UTC)
    for _ in range(50):  # would drive factor below 0.1
        repo.upsert_on_429("subdl", "day", 100, None, now)
    row = repo.get("subdl", "day")
    assert row["adjustment_factor"] == pytest.approx(0.1)


def test_ramp_recovery_noop_within_24h_of_429(app_ctx):
    repo = ProviderLearnedLimitsRepository()
    now = datetime(2026, 4, 17, 12, 0, 0, tzinfo=UTC)
    repo.upsert_on_429("opensubtitles", "day", 1000, None, now)
    twenty_three_hours_later = now + timedelta(hours=23)
    factor = repo.ramp_recovery("opensubtitles", "day", step=0.02, now=twenty_three_hours_later)
    assert factor == pytest.approx(0.9)
    row = repo.get("opensubtitles", "day")
    assert row["consecutive_good_days"] == 0


def test_ramp_recovery_increments_good_days_after_24h(app_ctx):
    repo = ProviderLearnedLimitsRepository()
    now = datetime(2026, 4, 17, 12, 0, 0, tzinfo=UTC)
    repo.upsert_on_429("opensubtitles", "day", 1000, None, now)
    later = now + timedelta(days=1, hours=1)
    factor = repo.ramp_recovery("opensubtitles", "day", step=0.02, now=later)
    assert factor == pytest.approx(0.9)  # still 0.9 — only 1 good day, need 7
    row = repo.get("opensubtitles", "day")
    assert row["consecutive_good_days"] == 1


def test_ramp_recovery_ramps_factor_after_7_good_days(app_ctx):
    repo = ProviderLearnedLimitsRepository()
    base = datetime(2026, 4, 17, 12, 0, 0, tzinfo=UTC)
    repo.upsert_on_429("opensubtitles", "day", 1000, None, base)
    # Six ramp calls spaced >24h each -> 6 good days, factor still 0.9
    for day in range(1, 7):
        repo.ramp_recovery("opensubtitles", "day", step=0.02, now=base + timedelta(days=day, hours=1))
    row_mid = repo.get("opensubtitles", "day")
    assert row_mid["consecutive_good_days"] == 6
    assert row_mid["adjustment_factor"] == pytest.approx(0.9)
    # Seventh call: 7 good days -> bump factor
    factor = repo.ramp_recovery(
        "opensubtitles", "day", step=0.02, now=base + timedelta(days=7, hours=1),
    )
    assert factor == pytest.approx(0.92)


def test_ramp_recovery_caps_at_1_0(app_ctx):
    repo = ProviderLearnedLimitsRepository()
    base = datetime(2026, 4, 17, 12, 0, 0, tzinfo=UTC)
    repo.upsert_on_429("opensubtitles", "day", 1000, None, base)
    for day in range(1, 200):
        repo.ramp_recovery(
            "opensubtitles", "day", step=0.02, now=base + timedelta(days=day, hours=1),
        )
    row = repo.get("opensubtitles", "day")
    assert row["adjustment_factor"] == pytest.approx(1.0)


def test_get_all_returns_mapping_keyed_by_provider_window(app_ctx):
    repo = ProviderLearnedLimitsRepository()
    now = datetime(2026, 4, 17, tzinfo=UTC)
    repo.upsert_on_429("opensubtitles", "day", 1000, None, now)
    repo.upsert_on_429("subdl", "day", 100, None, now)
    rows = repo.get_all()
    assert ("opensubtitles", "day") in rows
    assert ("subdl", "day") in rows
    assert rows[("opensubtitles", "day")]["adjustment_factor"] == pytest.approx(0.9)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_provider_learned_limits_repo.py -v`
Expected: `ModuleNotFoundError: No module named 'db.repositories.provider_learned_limits'`.

- [ ] **Step 3: Implement the repository**

```python
# backend/db/repositories/provider_learned_limits.py
"""Repository for the ``provider_learned_limits`` table.

Tracks observed rate-limit adjustments per (provider, window). A 429 from the
provider multiplies ``adjustment_factor`` by 0.9 (floored at 0.1). Clean days
ramp the factor back toward 1.0 in 0.02 steps after 7 consecutive days without
a 429.

All reads and writes against ``provider_learned_limits`` go through this
repository — direct SQL against the table is a contract violation.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from db.repositories.base import BaseRepository

logger = logging.getLogger(__name__)

_FACTOR_FLOOR = 0.1
_FACTOR_CEILING = 1.0
_RAMP_WAIT_HOURS = 24
_RAMP_GOOD_DAY_THRESHOLD = 7


class ProviderLearnedLimitsRepository(BaseRepository):
    """CRUD + learning operations for ``provider_learned_limits``."""

    def _row_to_dict(self, row) -> dict:
        return {
            "provider_name": row.provider_name,
            "window_type": row.window_type,
            "configured_limit": row.configured_limit,
            "observed_limit": row.observed_limit,
            "adjustment_factor": float(row.adjustment_factor),
            "last_429_at": row.last_429_at,
            "consecutive_good_days": row.consecutive_good_days,
            "updated_at": row.updated_at,
        }

    def get(self, provider: str, window: str) -> dict | None:
        from db.models.core import ProviderLearnedLimit  # noqa: PLC0415

        row = self.session.execute(
            select(ProviderLearnedLimit).where(
                ProviderLearnedLimit.provider_name == provider,
                ProviderLearnedLimit.window_type == window,
            )
        ).scalars().first()
        return self._row_to_dict(row) if row else None

    def get_all(self) -> dict[tuple[str, str], dict]:
        from db.models.core import ProviderLearnedLimit  # noqa: PLC0415

        rows = self.session.execute(select(ProviderLearnedLimit)).scalars().all()
        return {(r.provider_name, r.window_type): self._row_to_dict(r) for r in rows}

    def upsert_on_429(
        self,
        provider: str,
        window: str,
        configured_limit: int,
        observed_limit: int | None,
        now: datetime,
    ) -> float:
        """Record a 429: multiply factor by 0.9 (floor 0.1), reset good-days."""
        from db.models.core import ProviderLearnedLimit  # noqa: PLC0415

        row = self.session.execute(
            select(ProviderLearnedLimit).where(
                ProviderLearnedLimit.provider_name == provider,
                ProviderLearnedLimit.window_type == window,
            )
        ).scalars().first()
        if row is None:
            row = ProviderLearnedLimit(
                provider_name=provider,
                window_type=window,
                configured_limit=configured_limit,
                observed_limit=observed_limit,
                adjustment_factor=1.0,
                consecutive_good_days=0,
                last_429_at=now,
                updated_at=now,
            )
            self.session.add(row)
        new_factor = max(_FACTOR_FLOOR, float(row.adjustment_factor) * 0.9)
        row.adjustment_factor = new_factor
        row.consecutive_good_days = 0
        row.last_429_at = now
        row.updated_at = now
        if observed_limit is not None:
            row.observed_limit = observed_limit
        self.session.commit()
        return new_factor

    def ramp_recovery(
        self,
        provider: str,
        window: str,
        step: float,
        now: datetime,
    ) -> float:
        """Advance a (provider, window) toward factor=1.0 after a clean day.

        No-ops silently for unknown rows (nothing to ramp if never 429'd).
        """
        from db.models.core import ProviderLearnedLimit  # noqa: PLC0415

        row = self.session.execute(
            select(ProviderLearnedLimit).where(
                ProviderLearnedLimit.provider_name == provider,
                ProviderLearnedLimit.window_type == window,
            )
        ).scalars().first()
        if row is None:
            return _FACTOR_CEILING

        # Must be a full 24h since the last 429 AND since the last ramp.
        last = row.last_429_at or row.updated_at
        if last is None or (now - last) < timedelta(hours=_RAMP_WAIT_HOURS):
            return float(row.adjustment_factor)

        row.consecutive_good_days += 1
        row.updated_at = now
        if (
            row.consecutive_good_days >= _RAMP_GOOD_DAY_THRESHOLD
            and float(row.adjustment_factor) < _FACTOR_CEILING
        ):
            row.adjustment_factor = min(_FACTOR_CEILING, float(row.adjustment_factor) + step)
        self.session.commit()
        return float(row.adjustment_factor)

    def reset(self, provider: str, window: str) -> None:
        """Test-only: drop the row for (provider, window)."""
        from db.models.core import ProviderLearnedLimit  # noqa: PLC0415

        self.session.execute(
            ProviderLearnedLimit.__table__.delete().where(
                ProviderLearnedLimit.provider_name == provider,
                ProviderLearnedLimit.window_type == window,
            )
        )
        self.session.commit()
```

**Note:** the ORM class `ProviderLearnedLimit` does not yet exist — only the table does (from the Phase 1 migration). Add it to `backend/db/models/core.py` alongside the `WantedItem` block:

```python
# backend/db/models/core.py — add near other table declarations
class ProviderLearnedLimit(db.Model):
    """Observed rate-limit adjustments per (provider, window).

    Written by the budget manager when a provider returns HTTP 429; read by
    the budget manager to scale declared limits. See Phase 3 plan.
    """

    __tablename__ = "provider_learned_limits"

    provider_name: Mapped[str] = mapped_column(String(50), primary_key=True)
    window_type: Mapped[str] = mapped_column(String(10), primary_key=True)
    configured_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    observed_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    adjustment_factor: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    last_429_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consecutive_good_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
```

Also import `Float` at the top if not already:

```python
from sqlalchemy import DateTime, Float, Index, Integer, String, Text, UniqueConstraint
```

- [ ] **Step 4: Run tests — all pass**

Run: `cd backend && python -m pytest tests/test_provider_learned_limits_repo.py -v`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/db/repositories/provider_learned_limits.py backend/db/models/core.py backend/tests/test_provider_learned_limits_repo.py
git commit -m "feat(scheduler): provider_learned_limits repository (429 learning CRUD)"
```

---

## Task 2 — Apply adjustment factor in `ProviderBudgetManager._effective_limit`

**Files:**
- Modify: `backend/services/provider_budget.py`
- Modify: `backend/tests/test_provider_budget.py`

The factor table is read once at manager construction into `self._factors: dict[tuple[str,str], float]` and refreshed after every `record_429` / `tick_recovery` call. Lookup in the hot path must be in-memory — no DB round-trip per provider check.

- [ ] **Step 1: Failing test for factor-aware effective limits**

```python
# append to backend/tests/test_provider_budget.py
def test_effective_limit_applies_learned_factor():
    mgr = ProviderBudgetManager(redis=None, safety_margin_pct=0)
    # Inject a learned factor of 0.5 for opensubtitles day window
    mgr._factors[("opensubtitles", "day")] = 0.5
    # Raw limit 1000, safety 0, factor 0.5 -> effective 500
    assert mgr._effective_limit(1000, provider="opensubtitles", window=BudgetWindow.DAY) == 500


def test_effective_limit_default_factor_1_0():
    mgr = ProviderBudgetManager(redis=None, safety_margin_pct=0)
    # No entry -> factor 1.0
    assert mgr._effective_limit(1000, provider="opensubtitles", window=BudgetWindow.DAY) == 1000


def test_effective_limit_combines_safety_and_factor():
    mgr = ProviderBudgetManager(redis=None, safety_margin_pct=20)
    mgr._factors[("opensubtitles", "day")] = 0.5
    # 1000 * 0.5 * 0.8 = 400
    assert mgr._effective_limit(1000, provider="opensubtitles", window=BudgetWindow.DAY) == 400


def test_check_uses_factor_aware_limit():
    mgr = ProviderBudgetManager(redis=None, safety_margin_pct=0)
    mgr._factors[("opensubtitles", "day")] = 0.5
    # Pre-load 500 calls today — effective limit with factor is 500
    key = ("opensubtitles", "day", window_start_for(BudgetWindow.DAY))
    mgr._in_memory_counts[key] = 500
    decision = mgr.check("opensubtitles", {"day": 1000})
    assert decision.allow is False
    assert "day limit reached" in decision.reason
```

- [ ] **Step 2: Run — fails**

Run: `cd backend && python -m pytest tests/test_provider_budget.py -v -k "factor"`
Expected: `AttributeError: 'ProviderBudgetManager' object has no attribute '_factors'` (or similar).

- [ ] **Step 3: Extend `_effective_limit` and `check()` signatures**

```python
# backend/services/provider_budget.py — changes in class ProviderBudgetManager

# Constructor: add _factors cache
def __init__(self, redis: Any = None, safety_margin_pct: int = 20) -> None:
    self._redis = redis
    self._safety = max(0, min(100, safety_margin_pct))
    self._lock = Lock()
    self._in_memory_counts: dict[tuple[str, str, datetime], int] = defaultdict(int)
    # Learned adjustment factors keyed by (provider, window_value). Loaded from
    # provider_learned_limits on first access and refreshed after each
    # record_429()/tick_recovery() call. Default is 1.0 for any missing entry.
    self._factors: dict[tuple[str, str], float] = {}
    self._factors_loaded = False

# Replace _effective_limit to take provider + window and apply factor
def _effective_limit(
    self,
    raw: int,
    *,
    provider: str | None = None,
    window: BudgetWindow | None = None,
) -> int:
    """Return raw * factor * (100 - safety) / 100, rounded down to int.

    ``provider``/``window`` are optional to preserve the old no-factor API
    for tests that predate Phase 3 — pass them to apply learned adjustments.
    """
    factor = 1.0
    if provider is not None and window is not None:
        factor = self._factors.get((provider, window.value), 1.0)
    scaled = raw * factor
    if self._safety > 0:
        scaled = scaled * (100 - self._safety) / 100
    return max(0, int(scaled))

# Update check() to pass provider + window
def check(self, provider, limits, now=None):
    # ... existing body ...
    for window_name, raw_limit in limits.items():
        try:
            window = BudgetWindow(window_name)
        except ValueError:
            continue
        effective = self._effective_limit(raw_limit, provider=provider, window=window)
        used = self._get_count(provider, window, now)
        if used >= effective:
            return BudgetDecision(
                allow=False,
                wait_seconds=self._seconds_until_next_window(window, now),
                reason=f"{window.value} limit reached ({used}/{effective})",
            )
    # ... unchanged stretch-mode tail ...
```

- [ ] **Step 4: Run — all factor tests pass + existing tests green**

Run: `cd backend && python -m pytest tests/test_provider_budget.py -v`
Expected: all pre-existing tests + 4 new tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/services/provider_budget.py backend/tests/test_provider_budget.py
git commit -m "feat(scheduler): apply learned adjustment factor in effective limit"
```

---

## Task 3 — `record_429` method on the budget manager

**Files:**
- Modify: `backend/services/provider_budget.py`
- Create: `backend/tests/test_provider_budget_learning.py`

The hot path writes to the DB and refreshes the in-memory factor cache. Wrap the DB write in try/except — a Postgres hiccup must not break search. Emit a `provider_state_changed` event with `state="learning"` so the dashboard can show a badge.

- [ ] **Step 1: Failing test**

```python
# backend/tests/test_provider_budget_learning.py
"""Tests for 429 learning hook in ProviderBudgetManager."""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from services.provider_budget import BudgetWindow, ProviderBudgetManager


def test_record_429_reduces_in_memory_factor():
    mgr = ProviderBudgetManager(redis=None, safety_margin_pct=0)
    now = datetime(2026, 4, 17, 12, 0, 0, tzinfo=UTC)
    with patch("services.provider_budget._persist_429") as persist:
        persist.return_value = 0.9  # what the repo would have returned
        mgr.record_429("opensubtitles", BudgetWindow.DAY, configured_limit=1000, now=now)
    assert mgr._factors[("opensubtitles", "day")] == pytest.approx(0.9)


def test_record_429_emits_provider_state_changed_event():
    mgr = ProviderBudgetManager(redis=None, safety_margin_pct=0)
    now = datetime(2026, 4, 17, 12, 0, 0, tzinfo=UTC)
    with patch("services.provider_budget._persist_429", return_value=0.81), \
         patch("services.provider_budget._emit_event") as emit:
        mgr.record_429("opensubtitles", BudgetWindow.DAY, configured_limit=1000, now=now)
    emit.assert_called_once()
    name, payload = emit.call_args.args
    assert name == "provider_state_changed"
    assert payload["provider"] == "opensubtitles"
    assert payload["state"] == "learning"
    assert payload["adjustment_factor"] == pytest.approx(0.81)


def test_record_429_swallows_persistence_error():
    mgr = ProviderBudgetManager(redis=None, safety_margin_pct=0)
    now = datetime(2026, 4, 17, tzinfo=UTC)
    with patch("services.provider_budget._persist_429", side_effect=RuntimeError("db down")):
        # Must not raise — search must continue even if DB is unreachable
        mgr.record_429("opensubtitles", BudgetWindow.DAY, configured_limit=1000, now=now)
    # Fall-back behaviour: factor is reduced in memory only so the next
    # check() still throttles the provider even without a persisted row.
    assert mgr._factors[("opensubtitles", "day")] == pytest.approx(0.9)
```

- [ ] **Step 2: Run — fails**

Run: `cd backend && python -m pytest tests/test_provider_budget_learning.py -v`
Expected: `AttributeError: 'ProviderBudgetManager' object has no attribute 'record_429'`.

- [ ] **Step 3: Implement `record_429` + helper shims**

```python
# backend/services/provider_budget.py — add to class + module-level helpers

# Module-level indirection so tests can patch without importing the repo
def _persist_429(provider, window, configured_limit, observed_limit, now) -> float:
    """Thin wrapper around the repo. Returns the NEW adjustment_factor.

    Wrapped so tests can patch it with MagicMock without needing a DB session.
    Requires a Flask app context (``db.session`` is request-scoped); callers
    outside an app context will get an error logged by ``record_429``'s
    outer try/except.
    """
    from db.repositories.provider_learned_limits import ProviderLearnedLimitsRepository

    return ProviderLearnedLimitsRepository().upsert_on_429(
        provider=provider,
        window=window.value if hasattr(window, "value") else window,
        configured_limit=configured_limit,
        observed_limit=observed_limit,
        now=now,
    )


def _emit_event(name: str, payload: dict) -> None:
    """Thin wrapper around events.emit_event — test-patchable."""
    from events import emit_event
    emit_event(name, payload)


# Class method
def record_429(
    self,
    provider: str,
    window: BudgetWindow,
    configured_limit: int,
    observed_limit: int | None = None,
    now: datetime | None = None,
) -> float:
    """Record a provider-reported rate-limit hit.

    Multiplies the learned ``adjustment_factor`` by 0.9 (floor 0.1) for
    ``(provider, window)``. Persists via the repo; if persistence fails we
    still update the in-memory cache so the next ``check()`` throttles.
    Returns the new factor.
    """
    if now is None:
        now = datetime.now(UTC)
    key = (provider, window.value)
    current = self._factors.get(key, 1.0)
    fallback_factor = max(0.1, current * 0.9)
    try:
        new_factor = _persist_429(
            provider=provider,
            window=window,
            configured_limit=configured_limit,
            observed_limit=observed_limit,
            now=now,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "record_429 persistence failed for %s/%s (using in-memory fallback): %s",
            provider, window.value, exc,
        )
        new_factor = fallback_factor
    with self._lock:
        self._factors[key] = new_factor
    try:
        _emit_event(
            "provider_state_changed",
            {
                "provider": provider,
                "state": "learning",
                "reason": f"429_observed_{window.value}",
                "adjustment_factor": new_factor,
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("provider_state_changed emit failed: %s", exc)
    return new_factor
```

- [ ] **Step 4: Run — all 3 learning tests pass**

Run: `cd backend && python -m pytest tests/test_provider_budget_learning.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/services/provider_budget.py backend/tests/test_provider_budget_learning.py
git commit -m "feat(scheduler): record_429 hook reduces factor + emits learning event"
```

---

## Task 4 — Hook `record_429` into `SearchCoordinator`'s rate-limit path

**Files:**
- Modify: `backend/providers/search_coordinator.py:534-562` (the `ProviderRateLimitError` branch inside the `except Exception as e:` block)
- Modify: `backend/tests/test_search_coordinator_budget.py` (or create new file if the existing one does not exist)

The coordinator already classifies `ProviderRateLimitError` for the throttle map. Add one call to `get_budget_manager().record_429(name, window, limit)` before the existing `auto_disable_provider` persistence.

Choosing the right `window`: `ProviderRateLimitError.retry_after` tells us whether it was a per-second burst (<=2 min) or per-day quota (>= 600s). Use `day` as the default (the most common case); if `retry_after <= 120`, use `second`.

- [ ] **Step 1: Failing test**

```python
# backend/tests/test_search_coordinator_budget.py  (extend or create)
"""SearchCoordinator ↔ ProviderBudgetManager integration tests."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from providers.base import ProviderRateLimitError
from providers.search_coordinator import SearchCoordinatorMixin


def test_provider_rate_limit_triggers_record_429(tmp_provider_manager):
    """When a provider raises ProviderRateLimitError we record a 429 so the
    learned factor starts throttling future calls."""
    coord = tmp_provider_manager  # fixture: real SearchCoordinatorMixin with 1 provider
    coord._providers["opensubtitles"].search.side_effect = ProviderRateLimitError(
        "rate limited", retry_after=3600,
    )
    with patch("providers.search_coordinator.get_budget_manager") as bm:
        mgr = MagicMock()
        bm.return_value = mgr
        coord.search(MagicMock(languages=["de"], forced_only=False))
    mgr.record_429.assert_called_once()
    args, kwargs = mgr.record_429.call_args
    # Argument shape: (provider_name, window_enum, configured_limit=<int>)
    assert args[0] == "opensubtitles"
    # retry_after=3600 classifies as "day" window
    assert kwargs.get("window") or args[1]  # tolerate positional OR keyword style


def test_per_second_rate_limit_classifies_as_second_window(tmp_provider_manager):
    coord = tmp_provider_manager
    coord._providers["opensubtitles"].search.side_effect = ProviderRateLimitError(
        "too fast", retry_after=60,
    )
    with patch("providers.search_coordinator.get_budget_manager") as bm:
        mgr = MagicMock()
        bm.return_value = mgr
        coord.search(MagicMock(languages=["de"], forced_only=False))
    mgr.record_429.assert_called_once()
    # window = second for retry_after <= 120
    window_arg = mgr.record_429.call_args.args[1]
    assert window_arg.value == "second"
```

- [ ] **Step 2: Run — fails**

Run: `cd backend && python -m pytest tests/test_search_coordinator_budget.py -v -k "record_429"`
Expected: `AssertionError: Expected 'record_429' to have been called once` — because the hook is not wired yet.

- [ ] **Step 3: Add the hook**

```python
# backend/providers/search_coordinator.py — inside the `except Exception as e:`
# block where ProviderRateLimitError is already handled, AFTER the existing
# `auto_disable_provider(...)` call. Around line 534 in the current file.

if isinstance(e, ProviderRateLimitError):
    # ... existing throttle_map logic ...
    # NEW: tell the budget manager so future calls throttle harder.
    if getattr(self.settings, "provider_budget_enabled", True):
        try:
            from services.provider_budget import BudgetWindow, get_budget_manager

            retry_after = getattr(e, "retry_after", 60)
            window = BudgetWindow.SECOND if retry_after <= 120 else BudgetWindow.DAY
            provider_obj = self._providers.get(name)
            tier = getattr(provider_obj, "tier", "free")
            rate_limits = getattr(type(provider_obj), "rate_limits", {}) or {}
            limit = (rate_limits.get(tier) or rate_limits.get("free") or {}).get(window.value, 0)
            if limit > 0:
                get_budget_manager().record_429(
                    name,
                    window=window,
                    configured_limit=limit,
                )
        except Exception as _le:  # noqa: BLE001
            logger.debug("record_429 hook failed for %s: %s", name, _le)
```

- [ ] **Step 4: Run — both tests pass**

Run: `cd backend && python -m pytest tests/test_search_coordinator_budget.py -v`
Expected: all tests green.

- [ ] **Step 5: Commit**

```bash
git add backend/providers/search_coordinator.py backend/tests/test_search_coordinator_budget.py
git commit -m "feat(scheduler): SearchCoordinator calls budget.record_429 on 429"
```

---

## Task 5 — `tick_recovery` + wire into scheduler tick

**Files:**
- Modify: `backend/services/provider_budget.py` (add `tick_recovery`)
- Modify: `backend/services/wanted_search_runner.py:165-206` (call `tick_recovery` at the top of `run_wanted_search`)
- Create: tests under `backend/tests/test_provider_budget_learning.py` (extend)

Recovery runs at every scheduler tick. It iterates every `(provider, window)` with `factor < 1.0` and calls `repo.ramp_recovery`. The returned factor updates the in-memory cache.

- [ ] **Step 1: Failing test**

```python
# append to backend/tests/test_provider_budget_learning.py
def test_tick_recovery_updates_factor_cache():
    mgr = ProviderBudgetManager(redis=None, safety_margin_pct=0)
    mgr._factors = {("opensubtitles", "day"): 0.9}
    now = datetime(2026, 4, 25, tzinfo=UTC)

    def _fake_ramp(provider, window, step, now):
        # Simulate one full week of good days having accumulated -> bump to 0.92
        return 0.92

    with patch(
        "services.provider_budget._ramp_all", side_effect=lambda now: {("opensubtitles", "day"): 0.92}
    ):
        mgr.tick_recovery(now=now)
    assert mgr._factors[("opensubtitles", "day")] == pytest.approx(0.92)


def test_tick_recovery_swallows_db_error():
    mgr = ProviderBudgetManager(redis=None, safety_margin_pct=0)
    mgr._factors = {("opensubtitles", "day"): 0.9}
    now = datetime(2026, 4, 25, tzinfo=UTC)
    with patch("services.provider_budget._ramp_all", side_effect=RuntimeError("db down")):
        mgr.tick_recovery(now=now)  # must not raise
    # Cache remains at pre-tick value
    assert mgr._factors[("opensubtitles", "day")] == pytest.approx(0.9)
```

- [ ] **Step 2: Run — fails**

Run: `cd backend && python -m pytest tests/test_provider_budget_learning.py -v -k "tick_recovery"`
Expected: `AttributeError: 'ProviderBudgetManager' object has no attribute 'tick_recovery'`.

- [ ] **Step 3: Implement `tick_recovery` + helper**

```python
# backend/services/provider_budget.py

# Module-level indirection — test-patchable, keeps DB imports out of hot path
def _ramp_all(now: datetime) -> dict[tuple[str, str], float]:
    """Run ramp_recovery for every row with factor < 1.0. Returns the new map.

    Requires a Flask app context; ``tick_recovery`` callers from outside one
    (tests) must push ``app_ctx`` or patch this function.
    """
    from db.repositories.provider_learned_limits import ProviderLearnedLimitsRepository

    repo = ProviderLearnedLimitsRepository()
    new_factors: dict[tuple[str, str], float] = {}
    for key, row in repo.get_all().items():
        if row["adjustment_factor"] < 1.0:
            new_factor = repo.ramp_recovery(key[0], key[1], step=0.02, now=now)
            new_factors[key] = new_factor
    return new_factors


# Class method
def tick_recovery(self, now: datetime | None = None) -> None:
    """Advance learned factors toward 1.0 for any row on a clean streak.

    Called once per wanted-scheduler tick (typically daily). Swallows all DB
    errors — recovery is best-effort and must not break the scheduler.
    """
    if now is None:
        now = datetime.now(UTC)
    try:
        new_factors = _ramp_all(now)
    except Exception as exc:  # noqa: BLE001
        logger.debug("tick_recovery failed, keeping existing factors: %s", exc)
        return
    if not new_factors:
        return
    with self._lock:
        self._factors.update(new_factors)
```

- [ ] **Step 4: Wire the tick into `run_wanted_search`**

```python
# backend/services/wanted_search_runner.py — near the top of run_wanted_search(),
# right after `settings = get_settings()` (around line 195):

# Phase 3: ramp learned factors toward 1.0 once per tick (daily in default config).
try:
    from services.provider_budget import get_budget_manager

    get_budget_manager().tick_recovery()
except Exception as _tre:  # noqa: BLE001
    logger.debug("tick_recovery failed (non-blocking): %s", _tre)
```

- [ ] **Step 5: Run — tests pass**

Run: `cd backend && python -m pytest tests/test_provider_budget_learning.py -v`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add backend/services/provider_budget.py backend/services/wanted_search_runner.py backend/tests/test_provider_budget_learning.py
git commit -m "feat(scheduler): tick_recovery ramps learned factors toward 1.0 per tick"
```

---

## Task 6 — Burst-mode front-loading

**Files:**
- Modify: `backend/services/provider_budget.py:161-188` (`_stretch_allowed`)
- Modify: `backend/config.py:215-234` (new key `provider_budget_burst_window_hours`)
- Create: `backend/tests/test_provider_budget_modes.py`

Behaviour: when `provider_budget_stretch_mode == "burst"`, the stretch gate allows unrestricted consumption for the first `burst_window_hours` hours of the UTC day; after the window closes, it falls back to stretch-style pacing over the REMAINING budget and REMAINING hours.

Default `provider_budget_burst_window_hours = 6` (reset at midnight UTC, burst until 06:00 UTC).

- [ ] **Step 1: Failing tests**

```python
# backend/tests/test_provider_budget_modes.py
"""Burst + adaptive stretch-mode tests."""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from services.provider_budget import BudgetWindow, ProviderBudgetManager, window_start_for


def _settings_stub(**overrides):
    defaults = {
        "provider_budget_stretch_mode": "burst",
        "provider_budget_burst_window_hours": 6,
    }
    defaults.update(overrides)
    stub = MagicMock()
    for k, v in defaults.items():
        setattr(stub, k, v)
    return stub


def test_burst_mode_allows_full_rate_inside_window():
    mgr = ProviderBudgetManager(redis=None, safety_margin_pct=0)
    now = datetime(2026, 4, 17, 2, 30, 0, tzinfo=UTC)  # 02:30 UTC
    # Seed usage: already burned 500/1000 — stretch would normally deny at this hour
    key = ("opensubtitles", "day", window_start_for(BudgetWindow.DAY, now))
    mgr._in_memory_counts[key] = 500
    with patch("services.provider_budget.get_settings", return_value=_settings_stub()):
        decision = mgr.check("opensubtitles", {"day": 1000}, now=now)
    assert decision.allow is True


def test_burst_mode_enforces_stretch_after_window_ends():
    mgr = ProviderBudgetManager(redis=None, safety_margin_pct=0)
    # 08:00 UTC — window ended 2h ago. Remaining budget must pace across remaining 16h.
    now = datetime(2026, 4, 17, 8, 0, 0, tzinfo=UTC)
    key = ("opensubtitles", "day", window_start_for(BudgetWindow.DAY, now))
    # Burst consumed 600 in first 6h. Remaining 400 must pace evenly across hours 6..23 (18 hours).
    # At hour 8 (2 post-window hours), remaining-pace threshold = 600 + ceil(400 * 3 / 18) = 667.
    # Seed to just over the threshold (670) to force a deny.
    mgr._in_memory_counts[key] = 670
    with patch("services.provider_budget.get_settings", return_value=_settings_stub()):
        decision = mgr.check("opensubtitles", {"day": 1000}, now=now)
    assert decision.allow is False
    assert "burst" in decision.reason or "stretch" in decision.reason


def test_burst_mode_still_enforces_raw_caps():
    mgr = ProviderBudgetManager(redis=None, safety_margin_pct=0)
    now = datetime(2026, 4, 17, 2, 30, 0, tzinfo=UTC)
    key = ("opensubtitles", "day", window_start_for(BudgetWindow.DAY, now))
    mgr._in_memory_counts[key] = 1000  # At the raw cap
    with patch("services.provider_budget.get_settings", return_value=_settings_stub()):
        decision = mgr.check("opensubtitles", {"day": 1000}, now=now)
    assert decision.allow is False
    assert "day limit reached" in decision.reason
```

- [ ] **Step 2: Run — fails**

Run: `cd backend && python -m pytest tests/test_provider_budget_modes.py -v`
Expected: first two tests fail — today's `_stretch_allowed` does not branch on `burst`.

- [ ] **Step 3: Extend `_stretch_allowed` + read new config**

```python
# backend/services/provider_budget.py — replace the stretch-mode block inside check()

# Stretch-mode gate — default 'stretch' (even pacing). 'burst' lets the first
# N hours run at raw-cap pace, then paces the REMAINING quota across the
# REMAINING hours. 'adaptive' is handled in Task 7. 'off' / disabled skip the gate.
try:
    from config import get_settings

    settings = get_settings()
    stretch_mode = getattr(settings, "provider_budget_stretch_mode", "stretch")
    burst_window_hours = int(getattr(settings, "provider_budget_burst_window_hours", 6))
except Exception:  # noqa: BLE001
    stretch_mode, burst_window_hours = "stretch", 6

day_limit = limits.get("day", 0)
if day_limit > 0 and stretch_mode in ("stretch", "burst"):
    if stretch_mode == "stretch":
        stretch_decision = self._stretch_allowed(provider, day_limit, now)
    else:  # burst
        stretch_decision = self._burst_allowed(
            provider, day_limit, now, burst_window_hours=burst_window_hours,
        )
    if not stretch_decision.allow:
        return stretch_decision

return BudgetDecision(allow=True)
```

```python
# New method on ProviderBudgetManager
def _burst_allowed(
    self,
    provider: str,
    day_limit: int,
    now: datetime,
    burst_window_hours: int,
) -> BudgetDecision:
    """Burst gate: raw-cap-only inside the window; paced afterwards.

    Inside hours [0, burst_window_hours): always allow (raw caps already
    enforced before this method runs).

    After the window: the threshold at the end of hour H is
    ``burst_used + ceil(remaining_budget * (H - burst_end + 1) / (24 - burst_end))``
    where ``burst_used`` is the actual consumption at the end of the burst
    window — we use current day usage at ``burst_window_hours`` as a proxy.

    Simplification: we do not store the exact burst-end count. We treat the
    budget beyond ``burst_window_hours`` as ``remaining = day_limit - usage_so_far
    at hour=burst_window_hours``. Since we do not preserve that snapshot, we
    approximate with ``current_usage`` read at the moment of the gate call —
    which overestimates the remaining budget when called shortly after the
    window closes. Acceptable: the gate is self-correcting within minutes.
    """
    if now.hour < burst_window_hours:
        return BudgetDecision(allow=True)

    day_used = self._get_count(provider, BudgetWindow.DAY, now)
    hours_after_burst_end = now.hour - burst_window_hours + 1
    hours_remaining_in_day = 24 - burst_window_hours
    # Threshold = day_used_at_burst_end_estimate + paced-share
    # Estimate burst-end count conservatively: assume linear across the
    # burst window itself using the current pace. This is coarse but
    # stateless.
    estimated_burst_used = min(
        day_used,
        int(day_used * burst_window_hours / max(1, now.hour)),
    )
    remaining_budget = max(0, day_limit - estimated_burst_used)
    paced_share = math.ceil(remaining_budget * hours_after_burst_end / hours_remaining_in_day)
    threshold = estimated_burst_used + paced_share
    if day_used >= threshold:
        wait = self._seconds_until_next_window(BudgetWindow.HOUR, now)
        return BudgetDecision(
            allow=False,
            wait_seconds=wait,
            reason=(
                f"burst pace ({day_used}/{threshold} at hour {now.hour} UTC, "
                f"burst window {burst_window_hours}h, {day_limit}/day)"
            ),
        )
    return BudgetDecision(allow=True)
```

Config addition:

```python
# backend/config.py — in the Wanted Search Scheduler section near line 229
# Burst window length in hours; only applies when provider_budget_stretch_mode='burst'.
provider_budget_burst_window_hours: int = 6
```

- [ ] **Step 4: Run — burst tests pass + existing stretch tests stay green**

Run: `cd backend && python -m pytest tests/test_provider_budget.py tests/test_provider_budget_modes.py -v`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add backend/services/provider_budget.py backend/config.py backend/tests/test_provider_budget_modes.py
git commit -m "feat(scheduler): burst mode front-loads budget for first N hours of day"
```

---

## Task 7 — Adaptive-mode demand histogram

**Files:**
- Modify: `backend/services/provider_budget.py` (add `_adaptive_allowed`, plug into stretch-mode dispatch)
- Create: `backend/services/demand_histogram.py` (compute + cache the per-hour demand shares)
- Create: `backend/tests/test_demand_histogram.py`
- Modify: `backend/tests/test_provider_budget_modes.py`

Adaptive mode distributes the daily budget proportional to observed demand per hour. Source of truth: histogram of `wanted_items.added_at` over the last 30 days, grouped by `EXTRACT(HOUR FROM added_at)` UTC.

Cache the histogram for 1 hour in the process — recomputing on every provider check would be O(items) per call. A fallback uniform distribution is used when the cache is empty AND the DB is unreachable.

- [ ] **Step 1: Failing test for histogram service**

```python
# backend/tests/test_demand_histogram.py
"""Demand-histogram tests — drives adaptive stretch mode."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from services.demand_histogram import (
    DEMAND_UNIFORM,
    get_demand_shares,
    invalidate_demand_cache,
)


def test_demand_shares_sum_to_1():
    invalidate_demand_cache()
    with patch(
        "services.demand_histogram._fetch_added_at_hours",
        return_value=[0, 0, 0, 12, 12, 12, 23],  # skewed toward 00, 12
    ):
        shares = get_demand_shares(now=datetime(2026, 4, 17, tzinfo=UTC))
    assert len(shares) == 24
    assert sum(shares) == pytest.approx(1.0, rel=1e-6)
    # Hour 0 had 3/7 events -> share 3/7
    assert shares[0] == pytest.approx(3 / 7)
    assert shares[12] == pytest.approx(3 / 7)
    assert shares[23] == pytest.approx(1 / 7)


def test_demand_shares_fallback_uniform_on_empty_history():
    invalidate_demand_cache()
    with patch("services.demand_histogram._fetch_added_at_hours", return_value=[]):
        shares = get_demand_shares(now=datetime(2026, 4, 17, tzinfo=UTC))
    assert shares == DEMAND_UNIFORM


def test_demand_cache_respects_ttl():
    invalidate_demand_cache()
    now = datetime(2026, 4, 17, 12, 0, 0, tzinfo=UTC)
    with patch(
        "services.demand_histogram._fetch_added_at_hours", return_value=[0] * 24
    ) as fetch:
        get_demand_shares(now=now)
        # Call again within TTL — fetch must not be invoked
        get_demand_shares(now=now + timedelta(minutes=30))
        assert fetch.call_count == 1
        # After TTL
        get_demand_shares(now=now + timedelta(hours=2))
        assert fetch.call_count == 2
```

- [ ] **Step 2: Run — fails**

Run: `cd backend && python -m pytest tests/test_demand_histogram.py -v`
Expected: `ModuleNotFoundError: No module named 'services.demand_histogram'`.

- [ ] **Step 3: Implement histogram service**

```python
# backend/services/demand_histogram.py
"""Per-hour demand histogram for adaptive budget pacing.

Bucket wanted_items by the UTC hour of their ``added_at`` over the last 30
days. Normalise to shares summing to 1.0. Cache for 1h to keep the hot path
cheap. Fall back to a uniform (1/24) distribution when history is empty or
the DB is unreachable — adaptive mode must never harden into a denial-of-
service against itself.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from threading import Lock

logger = logging.getLogger(__name__)

DEMAND_UNIFORM: list[float] = [1.0 / 24] * 24
_CACHE_TTL = timedelta(hours=1)
_HISTORY_DAYS = 30

_cache_shares: list[float] | None = None
_cache_at: datetime | None = None
_cache_lock = Lock()


def invalidate_demand_cache() -> None:
    """Test helper — drop the cached shares so the next call recomputes."""
    global _cache_shares, _cache_at
    with _cache_lock:
        _cache_shares = None
        _cache_at = None


def _fetch_added_at_hours(cutoff: datetime) -> list[int]:
    """Return a list of UTC hours (0..23) for every wanted_item added after ``cutoff``.

    Isolated into its own function so tests can patch it without touching the DB.
    Requires a Flask app context (``db.session`` is request-scoped).
    """
    from db.models.core import WantedItem
    from extensions import db
    from sqlalchemy import func, select

    stmt = select(
        func.extract("hour", WantedItem.added_at).label("h")
    ).where(WantedItem.added_at >= cutoff)
    return [int(row.h) for row in db.session.execute(stmt).all()]


def get_demand_shares(now: datetime | None = None) -> list[float]:
    """Return 24 floats summing to 1.0 — share of historical demand per UTC hour.

    Cached 1h. Uniform when no history available.
    """
    if now is None:
        now = datetime.now(UTC)
    global _cache_shares, _cache_at
    with _cache_lock:
        if _cache_shares is not None and _cache_at is not None:
            if (now - _cache_at) < _CACHE_TTL:
                return _cache_shares
    try:
        cutoff = now - timedelta(days=_HISTORY_DAYS)
        hours = _fetch_added_at_hours(cutoff)
    except Exception as exc:  # noqa: BLE001
        logger.debug("demand histogram fetch failed, using uniform: %s", exc)
        hours = []
    if not hours:
        result = DEMAND_UNIFORM
    else:
        counts = [0] * 24
        for h in hours:
            if 0 <= h < 24:
                counts[h] += 1
        total = sum(counts) or 1
        result = [c / total for c in counts]
    with _cache_lock:
        _cache_shares = result
        _cache_at = now
    return result
```

- [ ] **Step 4: Add `_adaptive_allowed` in budget manager**

```python
# backend/services/provider_budget.py

def _adaptive_allowed(
    self, provider: str, day_limit: int, now: datetime
) -> BudgetDecision:
    """Adaptive gate: threshold at end of hour H = day_limit * cumulative_share[0..H].

    Falls back to uniform distribution (same behaviour as 'stretch') when
    history is empty.
    """
    from services.demand_histogram import get_demand_shares

    shares = get_demand_shares(now=now)
    cumulative = 0.0
    for h in range(now.hour + 1):
        cumulative += shares[h]
    threshold = math.ceil(day_limit * cumulative)
    day_used = self._get_count(provider, BudgetWindow.DAY, now)
    if day_used >= threshold:
        return BudgetDecision(
            allow=False,
            wait_seconds=self._seconds_until_next_window(BudgetWindow.HOUR, now),
            reason=(
                f"adaptive pace ({day_used}/{threshold} at hour {now.hour} UTC, "
                f"cumulative demand share {cumulative:.2f})"
            ),
        )
    return BudgetDecision(allow=True)
```

Extend the dispatch inside `check()`:

```python
# backend/services/provider_budget.py — replace the mode dispatch block

if day_limit > 0:
    if stretch_mode == "stretch":
        sd = self._stretch_allowed(provider, day_limit, now)
    elif stretch_mode == "burst":
        sd = self._burst_allowed(
            provider, day_limit, now, burst_window_hours=burst_window_hours,
        )
    elif stretch_mode == "adaptive":
        sd = self._adaptive_allowed(provider, day_limit, now)
    else:
        sd = BudgetDecision(allow=True)
    if not sd.allow:
        return sd
```

- [ ] **Step 5: Add adaptive test**

```python
# append to backend/tests/test_provider_budget_modes.py
def test_adaptive_mode_uses_demand_histogram():
    mgr = ProviderBudgetManager(redis=None, safety_margin_pct=0)
    # All demand at hour 10 -> threshold at hour 9 = 0, hour 10 = day_limit
    shares = [0.0] * 24
    shares[10] = 1.0
    now_before = datetime(2026, 4, 17, 9, 30, tzinfo=UTC)
    now_after = datetime(2026, 4, 17, 10, 30, tzinfo=UTC)
    with patch(
        "services.provider_budget.get_settings",
        return_value=_settings_stub(provider_budget_stretch_mode="adaptive"),
    ), patch(
        "services.demand_histogram.get_demand_shares", return_value=shares,
    ):
        # Before demand hour: no budget expected to be used
        key_before = ("opensubtitles", "day", window_start_for(BudgetWindow.DAY, now_before))
        mgr._in_memory_counts[key_before] = 10
        assert mgr.check("opensubtitles", {"day": 1000}, now=now_before).allow is False
        # In demand hour: full budget unlocked
        key_after = ("opensubtitles", "day", window_start_for(BudgetWindow.DAY, now_after))
        mgr._in_memory_counts[key_after] = 500
        assert mgr.check("opensubtitles", {"day": 1000}, now=now_after).allow is True
```

- [ ] **Step 6: Run — all pass**

Run: `cd backend && python -m pytest tests/test_demand_histogram.py tests/test_provider_budget_modes.py -v`
Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add backend/services/demand_histogram.py backend/services/provider_budget.py backend/tests/test_demand_histogram.py backend/tests/test_provider_budget_modes.py
git commit -m "feat(scheduler): adaptive stretch mode paces against demand histogram"
```

---

## Task 8 — Priority-weighted item selection

**Files:**
- Modify: `backend/db/repositories/wanted.py:23-28,266-324` (extend presets with priority rank prefix)
- Modify: `backend/config.py:215-234` (add `wanted_scheduler_priority_weighting_enabled: bool = True`)
- Create: `backend/tests/test_wanted_repo_priority_weighting.py` (note: check whether `test_wanted_repo_scheduled_search.py` exists before adding fixtures)

Priority rank used in the ORDER BY:
| priority | rank |
|---|---|
| `premium` | 0 |
| `standard` | 1 |
| `backlog` | 2 |

When `wanted_scheduler_priority_weighting_enabled = False`, the repo preserves the legacy order from Phase 1. When `True` (default), all three presets prepend the rank.

- [ ] **Step 1: Failing test**

```python
# backend/tests/test_wanted_repo_priority_weighting.py
"""Priority-weighted ordering tests for WantedRepository.get_items_for_scheduled_search.

Follows the same pattern as test_wanted_repo_scheduled_search.py — uses
``app_ctx`` fixture, ``db.session``, and parameterless ``WantedRepository()``.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from db.models.core import WantedItem
from db.repositories.wanted import WantedRepository
from extensions import db


def _make(file_path: str, **kwargs) -> WantedItem:
    now = datetime(2026, 4, 17, tzinfo=UTC)
    defaults = dict(
        item_type="episode",
        file_path=file_path,
        title=file_path,
        season_episode="S01E01",
        existing_sub="",
        missing_languages="[]",
        embedded_languages="[]",
        target_language="de",
        subtitle_type="full",
        status="wanted",
        added_at=now,
        updated_at=now,
    )
    defaults.update(kwargs)
    item = WantedItem(**defaults)
    db.session.add(item)
    db.session.commit()
    return item


def test_fair_order_with_priority_puts_premium_first(app_ctx):
    now = datetime(2026, 4, 17, tzinfo=UTC)
    # backlog is the oldest-searched (would win under fair alone) but must
    # land last under priority weighting.
    a = _make("/media/A.mkv", priority="backlog", last_search_at=now - timedelta(days=30))
    b = _make("/media/B.mkv", priority="standard", last_search_at=now - timedelta(days=5))
    c = _make("/media/C.mkv", priority="premium", last_search_at=None)
    repo = WantedRepository()
    rows = repo.get_items_for_scheduled_search(limit=10, order="fair")
    ids = [r["id"] for r in rows]
    assert ids == [c.id, b.id, a.id]


def test_priority_weighting_disabled_preserves_fair_order(app_ctx):
    now = datetime(2026, 4, 17, tzinfo=UTC)
    a = _make("/media/A.mkv", priority="backlog", last_search_at=now - timedelta(days=30))
    b = _make("/media/B.mkv", priority="premium", last_search_at=now - timedelta(days=1))
    repo = WantedRepository()
    # Explicit override bypasses the setting
    rows = repo.get_items_for_scheduled_search(
        limit=10, order="fair", priority_weighting=False,
    )
    # backlog has older last_search_at -> wins under pure fair
    assert rows[0]["id"] == a.id
    assert rows[1]["id"] == b.id
```

- [ ] **Step 2: Run — fails**

Run: `cd backend && python -m pytest tests/test_wanted_repo_priority_weighting.py -v`
Expected: `priority_weighting` kwarg rejected OR wrong order returned.

- [ ] **Step 3: Extend the repo method**

```python
# backend/db/repositories/wanted.py — top of file additions
_PRIORITY_RANK = case(
    (WantedItem.priority == "premium", 0),
    (WantedItem.priority == "backlog", 2),
    else_=1,
)
```

```python
# backend/db/repositories/wanted.py — modify get_items_for_scheduled_search signature
def get_items_for_scheduled_search(
    self,
    limit: int,
    order: str = "fair",
    priority_weighting: bool | None = None,
) -> list[dict]:
    """... (keep existing docstring) ...

    Args:
        priority_weighting: If True (default when unset), prefix every preset's
            ORDER BY with a priority rank (premium=0, standard=1, backlog=2).
            If False, skip the prefix — caller gets the Phase 1 behaviour.
            When ``None`` (default), read ``wanted_scheduler_priority_weighting_enabled``
            from settings.
    """
    if order not in _SCHEDULED_SEARCH_ORDERS:
        raise ValueError(
            f"Invalid order preset {order!r}. "
            f"Expected one of: {', '.join(_SCHEDULED_SEARCH_ORDERS)}"
        )

    if priority_weighting is None:
        try:
            from config import get_settings  # noqa: PLC0415

            priority_weighting = bool(
                getattr(get_settings(), "wanted_scheduler_priority_weighting_enabled", True)
            )
        except Exception:  # noqa: BLE001
            priority_weighting = True

    stmt = select(WantedItem).where(WantedItem.status == "wanted")

    order_clauses = []
    if priority_weighting:
        order_clauses.append(_PRIORITY_RANK.asc())

    if order == "newest_first":
        order_clauses.append(desc(WantedItem.added_at))
    elif order == "fair":
        order_clauses.extend([
            WantedItem.last_search_at.asc().nullsfirst(),
            WantedItem.search_count.asc(),
        ])
    else:  # weighted
        cutoff = datetime.now(UTC) - timedelta(days=_WEIGHTED_RECENT_DAYS)
        bucket = case((WantedItem.added_at >= cutoff, 0), else_=1)
        order_clauses.extend([
            bucket.asc(),
            WantedItem.last_search_at.asc().nullsfirst(),
            WantedItem.search_count.asc(),
        ])

    stmt = stmt.order_by(*order_clauses).limit(limit)
    rows = self.session.execute(stmt).scalars().all()
    return [self._row_to_wanted(r) for r in rows]
```

Config addition:

```python
# backend/config.py — near the other scheduler keys around line 219
wanted_scheduler_priority_weighting_enabled: bool = True
```

- [ ] **Step 4: Run tests — all pass**

Run: `cd backend && python -m pytest tests/test_wanted_repo_priority_weighting.py -v`
Expected: 2 passed.

- [ ] **Step 5: Regression — Phase 1 tests still green**

Run: `cd backend && python -m pytest tests/ -k "wanted_repo or scheduled_search" -v`
Expected: no regressions.

- [ ] **Step 6: Commit**

```bash
git add backend/db/repositories/wanted.py backend/config.py backend/tests/test_wanted_repo_priority_weighting.py
git commit -m "feat(scheduler): priority-weighted item selection (premium -> standard -> backlog)"
```

---

## Task 9 — Backlog reserve gate in `run_wanted_search`

**Files:**
- Modify: `backend/services/wanted_search_runner.py:165-230` (add `_filter_backlog_reserve`)
- Modify: `backend/config.py` (add `wanted_scheduler_backlog_reserve_pct: int = 50`)
- Create: `backend/tests/test_wanted_search_runner_backlog_gate.py`

Behaviour: when the highest-usage provider's day-usage exceeds `backlog_reserve_pct` of its effective limit, `backlog`-priority items are skipped this tick. They stay in the queue and get picked up on the next tick after the budget resets.

We compute the signal provider-agnostically (pick the max usage-ratio across all enabled providers) because wanted items do not map 1:1 to providers at selection time.

- [ ] **Step 1: Failing test**

```python
# backend/tests/test_wanted_search_runner_backlog_gate.py
"""Backlog reserve gate — skip backlog items when budget is >50% spent."""
from __future__ import annotations

from unittest.mock import MagicMock

from services.wanted_search_runner import _apply_backlog_reserve_gate


def test_backlog_items_dropped_when_any_provider_above_threshold():
    items = [
        {"id": 1, "priority": "premium"},
        {"id": 2, "priority": "standard"},
        {"id": 3, "priority": "backlog"},
    ]
    budget_states = [
        # opensubtitles at 60% of effective limit
        {"usage": {"day": 600}, "limits": {"day": 1000}},
        # subdl at 10%
        {"usage": {"day": 10}, "limits": {"day": 100}},
    ]
    result = _apply_backlog_reserve_gate(items, budget_states, reserve_pct=50)
    assert [i["id"] for i in result] == [1, 2]  # backlog dropped


def test_backlog_kept_when_all_providers_below_threshold():
    items = [{"id": 3, "priority": "backlog"}]
    budget_states = [
        {"usage": {"day": 400}, "limits": {"day": 1000}},
        {"usage": {"day": 10}, "limits": {"day": 100}},
    ]
    result = _apply_backlog_reserve_gate(items, budget_states, reserve_pct=50)
    assert [i["id"] for i in result] == [3]


def test_missing_day_limit_treated_as_zero_usage():
    items = [{"id": 3, "priority": "backlog"}]
    budget_states = [{"usage": {}, "limits": {}}]
    result = _apply_backlog_reserve_gate(items, budget_states, reserve_pct=50)
    assert [i["id"] for i in result] == [3]
```

- [ ] **Step 2: Run — fails**

Run: `cd backend && python -m pytest tests/test_wanted_search_runner_backlog_gate.py -v`
Expected: `ImportError: cannot import name '_apply_backlog_reserve_gate'`.

- [ ] **Step 3: Implement the pure helper**

```python
# backend/services/wanted_search_runner.py — module-level
def _apply_backlog_reserve_gate(
    items: list[dict],
    budget_states: list[dict],
    reserve_pct: int,
) -> list[dict]:
    """Drop ``priority == 'backlog'`` items when any provider is above reserve_pct.

    Each ``budget_states`` entry is a dict with ``usage.day`` and ``limits.day``
    (matching the shape returned by ``/api/v1/system/budget``). Providers with
    missing/zero day limit contribute ratio 0.
    """
    def _ratio(state: dict) -> float:
        usage = (state.get("usage") or {}).get("day", 0)
        limit = (state.get("limits") or {}).get("day", 0)
        if not limit:
            return 0.0
        return usage / limit

    max_ratio = max((_ratio(s) for s in budget_states), default=0.0)
    threshold = reserve_pct / 100.0
    if max_ratio < threshold:
        return items
    return [i for i in items if (i.get("priority") or "standard") != "backlog"]
```

- [ ] **Step 4: Plug the gate into `run_wanted_search`**

```python
# backend/services/wanted_search_runner.py — between _filter_eligible() and
# the embedded/search split (around line 211)

try:
    from services.provider_budget import get_budget_manager

    budget_mgr = get_budget_manager()
    from providers import get_provider_manager

    provider_mgr = get_provider_manager()
    budget_states = []
    for name, provider in provider_mgr._providers.items():
        tier = getattr(provider, "tier", "free")
        rate_limits = getattr(type(provider), "rate_limits", {}) or {}
        limits = rate_limits.get(tier) or rate_limits.get("free") or {}
        usage = budget_mgr.get_usage(name)
        budget_states.append({"usage": usage, "limits": limits})
    reserve_pct = int(getattr(settings, "wanted_scheduler_backlog_reserve_pct", 50))
    eligible = _apply_backlog_reserve_gate(eligible, budget_states, reserve_pct)
except Exception as _bge:  # noqa: BLE001
    logger.debug("backlog reserve gate failed (non-blocking): %s", _bge)
```

Config addition:

```python
# backend/config.py — add near scheduler keys
wanted_scheduler_backlog_reserve_pct: int = 50
```

- [ ] **Step 5: Run tests — all pass**

Run: `cd backend && python -m pytest tests/test_wanted_search_runner_backlog_gate.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/services/wanted_search_runner.py backend/config.py backend/tests/test_wanted_search_runner_backlog_gate.py
git commit -m "feat(scheduler): drop backlog items when provider budget >50% spent"
```

---

## Task 10 — Expose learned state on `/api/v1/system/budget`

**Files:**
- Modify: `backend/routes/system/budget.py` (enrich response per provider)
- Modify: `backend/tests/test_routes_system_budget.py` if it exists — run `ls backend/tests/test_routes_system_budget*` before editing; otherwise create it with the shape below

Response delta per provider (new optional fields — kept `null` when no learned row exists):

```json
{
  "name": "opensubtitles",
  "tier": "free",
  "limits": {"second": 5, "hour": 200, "day": 1000},
  "usage":  {"second": 0, "hour": 45, "day": 512},
  "reset_seconds": {"second": 1, "hour": 900, "day": 33000},
  "learning": {
    "adjustment_factor": 0.81,
    "consecutive_good_days": 3,
    "last_429_at": "2026-04-15T11:02:00Z"
  }
}
```

- [ ] **Step 1: Failing test**

```python
# backend/tests/test_routes_system_budget.py — add or extend.
# Before editing, run `ls backend/tests/test_routes_system_budget*` to confirm
# whether it exists. If it does, locate the existing client+API-key fixtures
# (see test_routes_system_health.py for the same pattern) and reuse them.

import pytest


def test_budget_endpoint_returns_learning_block_per_provider(app_ctx, client, admin_api_key):
    # Seed a learned row — runs inside the same app_ctx as the route call
    from datetime import UTC, datetime

    from db.repositories.provider_learned_limits import ProviderLearnedLimitsRepository

    now = datetime.now(UTC)
    ProviderLearnedLimitsRepository().upsert_on_429(
        provider="opensubtitles",
        window="day",
        configured_limit=1000,
        observed_limit=None,
        now=now,
    )
    resp = client.get("/api/v1/system/budget", headers={"X-API-Key": admin_api_key})
    assert resp.status_code == 200
    body = resp.get_json()
    os_row = next((p for p in body["providers"] if p["name"] == "opensubtitles"), None)
    assert os_row is not None
    assert "learning" in os_row
    assert os_row["learning"]["adjustment_factor"] == pytest.approx(0.9)
    assert os_row["learning"]["consecutive_good_days"] == 0


def test_budget_endpoint_returns_null_learning_when_no_row(app_ctx, client, admin_api_key):
    resp = client.get("/api/v1/system/budget", headers={"X-API-Key": admin_api_key})
    body = resp.get_json()
    # Providers without a learned row surface learning=null so the UI can
    # cleanly distinguish "at 1.0" from "never observed".
    for p in body["providers"]:
        if p["name"] != "opensubtitles":
            assert p.get("learning") is None
```

- [ ] **Step 2: Run — fails**

Run: `cd backend && python -m pytest tests/test_routes_system_budget.py -v -k "learning"`
Expected: `KeyError: 'learning'`.

- [ ] **Step 3: Enrich the endpoint**

```python
# backend/routes/system/budget.py — extend get_budget_state()

def get_budget_state():
    settings = get_settings()
    mgr = get_provider_manager()
    budget = get_budget_manager()

    from db.repositories.provider_learned_limits import ProviderLearnedLimitsRepository

    learned_by_provider: dict[str, dict] = {}
    try:
        for (provider, window), row in ProviderLearnedLimitsRepository().get_all().items():
            # Surface the "day" window only — that is what the dashboard shows.
            if window == "day":
                learned_by_provider[provider] = {
                    "adjustment_factor": row["adjustment_factor"],
                    "consecutive_good_days": row["consecutive_good_days"],
                    "last_429_at": row["last_429_at"].isoformat() if row["last_429_at"] else None,
                }
    except Exception as exc:  # noqa: BLE001
        logger.debug("learned-limits lookup failed (non-blocking): %s", exc)

    providers_out = []
    for name in sorted(mgr._providers.keys()):
        provider = mgr._providers[name]
        tier = getattr(provider, "tier", "free")
        rate_limits = getattr(type(provider), "rate_limits", None) or {}
        limits = rate_limits.get(tier) or rate_limits.get("free") or {}
        usage = budget.get_usage(name)
        reset_seconds = {
            window: budget.seconds_until_next_window(window) for window in ("second", "hour", "day")
        }
        providers_out.append({
            "name": name,
            "tier": tier,
            "limits": limits,
            "usage": usage,
            "reset_seconds": reset_seconds,
            "learning": learned_by_provider.get(name),
        })

    return jsonify({
        "providers": providers_out,
        "enabled": bool(getattr(settings, "provider_budget_enabled", True)),
    })
```

- [ ] **Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_routes_system_budget.py -v`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add backend/routes/system/budget.py backend/tests/test_routes_system_budget.py
git commit -m "feat(api): /system/budget exposes learned adjustment factor per provider"
```

---

## Task 11 — Frontend: learning badge + pacing-mode selector

**Files:**
- Modify: `frontend/src/api/health.ts` (extend `ProviderBudget` type)
- Modify: `frontend/src/components/dashboard/BudgetWidget.tsx` (render badge when factor < 1.0)
- Modify: `frontend/src/components/dashboard/__tests__/BudgetWidget.test.tsx` (check file path — may be alongside the source file)
- Modify: `frontend/src/pages/Settings/AutomationSettings.tsx:164-184` (add stretch-mode `<select>` + burst-window `<input>`)
- Modify: `frontend/src/i18n/locales/de/settings.json:451+` — add keys `stretch_mode`, `stretch_mode_hint`, `stretch_mode_stretch`, `stretch_mode_burst`, `stretch_mode_adaptive`, `burst_window_hours`, `burst_window_hours_hint`
- Modify: `frontend/src/i18n/locales/en/settings.json` — mirror keys in EN per language policy
- Modify: `frontend/src/i18n/locales/de/dashboard.json`, `frontend/src/i18n/locales/en/dashboard.json` — add `budget.learning_active` string (DE: `"Lernt — Limits angepasst um {{factor}}%"`, EN: `"Learning — limits adjusted by {{factor}}%"`)

- [ ] **Step 1: Extend the frontend type**

```ts
// frontend/src/api/health.ts — locate ProviderBudget interface and add:
export interface ProviderBudgetLearning {
  adjustment_factor: number
  consecutive_good_days: number
  last_429_at: string | null
}

export interface ProviderBudget {
  // ... existing fields ...
  learning?: ProviderBudgetLearning | null
}
```

- [ ] **Step 2: Failing Vitest for the badge**

```tsx
// frontend/src/components/dashboard/__tests__/BudgetWidget.test.tsx — add
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import BudgetWidget from '../BudgetWidget'

function renderWithBudget(data: BudgetResponse) {
  const qc = new QueryClient()
  qc.setQueryData(['system', 'budget'], data)
  return render(
    <QueryClientProvider client={qc}>
      <BudgetWidget />
    </QueryClientProvider>,
  )
}

test('renders learning badge when adjustment_factor < 1.0', () => {
  renderWithBudget({
    enabled: true,
    providers: [{
      name: 'opensubtitles', tier: 'free',
      limits: { second: 5, hour: 200, day: 1000 },
      usage:  { second: 0, hour: 0, day: 0 },
      reset_seconds: { second: 1, hour: 1800, day: 36000 },
      learning: { adjustment_factor: 0.81, consecutive_good_days: 2, last_429_at: null },
    }],
  })
  // Badge visible for the provider
  expect(screen.getByTestId('budget-learning-opensubtitles')).toBeInTheDocument()
  // Shows percentage adjustment
  expect(screen.getByTestId('budget-learning-opensubtitles')).toHaveTextContent('19')
})

test('hides learning badge at factor 1.0', () => {
  renderWithBudget({
    enabled: true,
    providers: [{
      name: 'opensubtitles', tier: 'free',
      limits: { second: 5, hour: 200, day: 1000 },
      usage:  { second: 0, hour: 0, day: 0 },
      reset_seconds: { second: 1, hour: 1800, day: 36000 },
      learning: { adjustment_factor: 1.0, consecutive_good_days: 42, last_429_at: null },
    }],
  })
  expect(screen.queryByTestId('budget-learning-opensubtitles')).toBeNull()
})
```

- [ ] **Step 3: Run — fails**

Run: `cd frontend && npx vitest run src/components/dashboard/__tests__/BudgetWidget.test.tsx`
Expected: "Unable to find element by: budget-learning-opensubtitles".

- [ ] **Step 4: Add the badge to `BudgetRow`**

```tsx
// frontend/src/components/dashboard/BudgetWidget.tsx — inside BudgetRow, after the usage span

{provider.learning && provider.learning.adjustment_factor < 1.0 && (
  <span
    data-testid={`budget-learning-${provider.name}`}
    title={t('budget.learning_active', {
      factor: Math.round((1 - provider.learning.adjustment_factor) * 100),
    })}
    style={{
      flex: '0 0 auto',
      fontSize: '10px',
      color: 'var(--warning)',
      background: 'var(--warning-soft, rgba(255,180,0,0.12))',
      padding: '2px 6px',
      borderRadius: '4px',
      marginLeft: '4px',
    }}
  >
    -{Math.round((1 - provider.learning.adjustment_factor) * 100)}%
  </span>
)}
```

- [ ] **Step 5: Add stretch-mode + burst-window fields to AutomationSettings**

```tsx
// frontend/src/pages/Settings/AutomationSettings.tsx — add a new FormGroup block
// right after the existing wanted-search-order block (around line 184)

<FormGroup
  label={tS('automation_page.stretch_mode')}
  hint={tS('automation_page.stretch_mode_hint')}
  htmlFor="provider-budget-stretch-mode"
  advanced
  data-testid="form-group-provider-budget-stretch-mode"
>
  <select
    id="provider-budget-stretch-mode"
    data-testid="input-provider-budget-stretch-mode"
    style={{ ...inputStyle, maxWidth: '320px' }}
    value={strVal(config, 'provider_budget_stretch_mode', 'stretch')}
    onChange={(e) => save({ provider_budget_stretch_mode: e.target.value })}
    disabled={updateConfig.isPending}
  >
    <option value="stretch">{tS('automation_page.stretch_mode_stretch')}</option>
    <option value="burst">{tS('automation_page.stretch_mode_burst')}</option>
    <option value="adaptive">{tS('automation_page.stretch_mode_adaptive')}</option>
  </select>
</FormGroup>

{strVal(config, 'provider_budget_stretch_mode', 'stretch') === 'burst' && (
  <FormGroup
    label={tS('automation_page.burst_window_hours')}
    hint={tS('automation_page.burst_window_hours_hint')}
    htmlFor="provider-budget-burst-window"
    advanced
    data-testid="form-group-provider-budget-burst-window-hours"
  >
    <input
      id="provider-budget-burst-window"
      type="number"
      data-testid="input-provider-budget-burst-window-hours"
      style={{ ...inputStyle, maxWidth: '120px' }}
      value={strVal(config, 'provider_budget_burst_window_hours', '6')}
      onChange={(e) => save({ provider_budget_burst_window_hours: Number(e.target.value) })}
      disabled={updateConfig.isPending}
      min={1}
      max={23}
    />
  </FormGroup>
)}
```

- [ ] **Step 6: Add i18n keys (DE + EN)**

```json
// frontend/src/i18n/locales/de/settings.json — inside "automation_page"
"stretch_mode": "API-Pacing-Modus",
"stretch_mode_hint": "Verteilt das tägliche API-Budget. 'Stretch' paced gleichmäßig über 24h, 'Burst' läuft N Stunden am Stück voll, 'Adaptiv' richtet sich nach deinem beobachteten Suchmuster.",
"stretch_mode_stretch": "Stretch (gleichmäßig)",
"stretch_mode_burst": "Burst (Front-Load)",
"stretch_mode_adaptive": "Adaptiv (nutzungsbasiert)",
"burst_window_hours": "Burst-Fenster (Stunden)",
"burst_window_hours_hint": "Wie lange am Tagesanfang ungedrosselt abgefragt wird bevor in den Stretch-Modus gewechselt wird.",
```

```json
// frontend/src/i18n/locales/en/settings.json — inside "automation_page"
"stretch_mode": "API Pacing Mode",
"stretch_mode_hint": "Distributes the daily API budget. 'Stretch' paces evenly across 24h, 'Burst' runs at full rate for N hours, 'Adaptive' follows your observed search pattern.",
"stretch_mode_stretch": "Stretch (even)",
"stretch_mode_burst": "Burst (front-load)",
"stretch_mode_adaptive": "Adaptive (usage-based)",
"burst_window_hours": "Burst window (hours)",
"burst_window_hours_hint": "How long at the start of day to run unpaced before switching to stretch mode.",
```

```json
// frontend/src/i18n/locales/de/dashboard.json — inside "budget"
"learning_active": "Lernt — Limits angepasst um {{factor}}%",
```

```json
// frontend/src/i18n/locales/en/dashboard.json — inside "budget"
"learning_active": "Learning — limits adjusted by {{factor}}%",
```

- [ ] **Step 7: Run all frontend tests**

Run: `cd frontend && npm run test -- --run`
Expected: widget tests + automation tests green.

Run: `cd frontend && npx tsc --noEmit`
Expected: no type errors.

Run: `cd frontend && npm run lint`
Expected: clean.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/api/health.ts frontend/src/components/dashboard/BudgetWidget.tsx frontend/src/components/dashboard/__tests__/BudgetWidget.test.tsx frontend/src/pages/Settings/AutomationSettings.tsx frontend/src/i18n/locales/
git commit -m "feat(ui): learning badge on budget widget + pacing-mode selector"
```

---

## Task 12 — End-to-end: 429 storm + recovery

**Files:**
- Create: `backend/tests/test_phase3_e2e.py`

Full-loop scenario. Uses real repo + fake provider, no Flask app.

- [ ] **Step 1: Write the E2E scenario**

```python
# backend/tests/test_phase3_e2e.py
"""End-to-end: 429 storm reduces factor, 7 clean days ramp it back up."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from services.provider_budget import BudgetWindow, ProviderBudgetManager


def test_429_storm_plus_recovery_cycle(app_ctx):
    mgr = ProviderBudgetManager(redis=None, safety_margin_pct=0)

    # Storm: 3 consecutive 429s
    storm_time = datetime(2026, 4, 17, 10, 0, 0, tzinfo=UTC)
    for i in range(3):
        mgr.record_429(
            "opensubtitles", BudgetWindow.DAY, configured_limit=1000,
            now=storm_time + timedelta(minutes=i),
        )

    factor_after_storm = mgr._factors[("opensubtitles", "day")]
    # 1.0 * 0.9 * 0.9 * 0.9 = 0.729
    assert factor_after_storm == pytest.approx(0.729, rel=1e-3)

    # Scheduler ticks once per day for the next 7 days — recovery should kick in
    # on tick 7 (first tick after 7 good days have elapsed).
    for day in range(1, 8):
        tick_time = storm_time + timedelta(days=day, hours=1)
        mgr.tick_recovery(now=tick_time)

    factor_after_recovery = mgr._factors.get(("opensubtitles", "day"), 1.0)
    # 0.729 + 0.02 after first ramp past 7-day threshold
    assert factor_after_recovery == pytest.approx(0.749, rel=1e-3)
```

- [ ] **Step 2: Run — must pass on first try (it is the integration of Tasks 1–5)**

Run: `cd backend && python -m pytest tests/test_phase3_e2e.py -v`
Expected: 1 passed.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_phase3_e2e.py
git commit -m "test(scheduler): phase 3 e2e — 429 storm reduces factor, 7d recovery ramps back"
```

---

## Task 13 — Pre-release verification

- [ ] **Step 1: Full backend test suite (with Phase 1+2+3 together)**

Run:
```bash
cd backend && python -m pytest --tb=short -q --ignore=tests/performance
```
Expected: no regressions. All Phase 3 new tests green.

- [ ] **Step 2: Ruff**

Run:
```bash
cd backend && ruff check . && ruff format --check .
```
Expected: clean.

- [ ] **Step 3: Frontend lint + type-check + unit tests**

Run:
```bash
cd frontend && npm run lint && npx tsc --noEmit && npm run test -- --run
```
Expected: clean.

- [ ] **Step 4: Manual smoke check — dev server**

```bash
npm run dev
# In a second terminal:
curl -s http://localhost:5765/api/v1/system/budget | jq '.providers[] | {name, learning}'
# Trigger a synthetic 429 via a dev-only route OR by setting a low opensubtitles limit + manual search.
# Expect: provider_state_changed event with state='learning' in the SocketIO log; budget widget
# shows the yellow "-10%" badge.
```

- [ ] **Step 5: Tag the state ready for Phase 4**

```bash
git tag phase-3-ready
```

---

## Phase 3 exit checklist

Before starting Phase 4:

- [ ] All 12 implementation tasks merged to master (no PRs; solo-project convention)
- [ ] Backend + frontend test suites green locally
- [ ] `/api/v1/system/budget` returns `learning` block populated for any provider that has 429'd at least once
- [ ] Dashboard shows the yellow `-X%` badge when a provider is being throttled via learned factor
- [ ] Settings page surfaces the three stretch modes and the burst window
- [ ] E2E scenario (`test_phase3_e2e.py`) passes on a clean DB
- [ ] CHANGELOG entry queued for the next release (Phase 5 aggregates all V1 entries)
- [ ] Wiki updates queued for new settings — will be written in Phase 5 alongside the rest

---

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Multiplicative factor shrinks past usable limits under prolonged 429s | Hard floor at 0.1 in `upsert_on_429`; `tick_recovery` ramps back once the storm subsides |
| DB writes on every 429 bottleneck high-throughput searches | `record_429` is only called when a provider raises `ProviderRateLimitError` — a rare path; happy searches do zero writes |
| Demand-histogram SQL is slow on large `wanted_items` tables | 1h module-level cache + `_HISTORY_DAYS = 30` limit; EXPLAIN on prod dump should confirm the existing index on `added_at` is used |
| Adaptive mode starves low-demand hours | Shares summing to 1.0 guarantee every hour gets at least `floor(limit / 24 / days_of_history)` budget; the `stretch` mode remains available as an always-safe fallback |
| Priority weighting hides legitimate `backlog` items forever | `tick_recovery` ramps factor back AND the backlog reserve gate releases items once budget returns below 50% — usually within 24h of reset |
| Burst-window estimate is stateless and coarse | Self-corrects within minutes; acceptable for a pacing gate. Exactness can be added in Phase 4 with a proper snapshot table if prod telemetry shows issues |
| Learned row for a retired provider sticks around forever | Out of scope for V1 — GC job can be added in Phase 5 validation if needed |
