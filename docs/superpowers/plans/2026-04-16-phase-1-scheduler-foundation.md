# Phase 1 — Scheduler Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-04-16-api-budget-scheduler-v1.md`

**Goal:** Fix the three production-blocking scheduler bugs (never-searched items, frozen items, ignored API limits) and establish the budget infrastructure that Phase 2–4 build on.

**Architecture:** Extend the existing `wanted_search_runner` + `search_coordinator` pipeline with a new `ProviderBudgetManager` service and a failure-kind-aware state machine. No new frameworks; stays within Flask + SQLAlchemy + Redis.

**Tech Stack:** Python 3.11, SQLAlchemy 2.x, Alembic, Redis (optional), pytest, React + TypeScript + Vitest.

---

## File plan

| Action | Path | Responsibility |
|---|---|---|
| Create | `backend/db/migrations/versions/b1u2d3g4e5t6_phase1_schema.py` | Alembic: new tables, wanted_items columns, data migration |
| Create | `backend/services/provider_budget.py` | `ProviderBudgetManager` class + window types |
| Create | `backend/tests/test_provider_budget.py` | Unit tests for budget manager |
| Create | `backend/routes/system/budget.py` | `/api/v1/system/budget` endpoint |
| Create | `backend/tests/test_routes_system_budget.py` | Route tests |
| Modify | `backend/providers/base.py` | Add `rate_limits` classvar stub |
| Modify | `backend/providers/opensubtitles.py` | Declare rate_limits (+ VIP auto-detect) |
| Modify | `backend/providers/subdl.py` | Declare rate_limits |
| Modify | `backend/providers/animetosho.py` | Declare rate_limits |
| Modify | `backend/providers/gestdown.py` | Declare rate_limits |
| Modify | `backend/providers/kitsunekko.py` | Declare rate_limits |
| Modify | `backend/providers/napisy24.py` | Declare rate_limits |
| Modify | `backend/providers/titrari.py` | Declare rate_limits |
| Modify | `backend/providers/subscene.py` | Declare rate_limits |
| Modify | `backend/providers/addic7ed.py` | Declare rate_limits |
| Modify | `backend/providers/tvsubtitles.py` | Declare rate_limits |
| Modify | `backend/providers/search_coordinator.py` | Integrate budget gate before provider call |
| Modify | `backend/services/wanted_search_runner.py` | Fair-rotation selection, failure-kind split, exp backoff, slow-mode |
| Modify | `backend/db/repositories/wanted.py` | New `get_items_for_scheduled_search()` with order preset |
| Modify | `backend/db/wanted.py` | Facade for new repo method |
| Modify | `backend/config.py` | New settings: `wanted_search_order`, `provider_budget_enabled`, `provider_budget_safety_margin_pct` |
| Modify | `backend/routes/system/__init__.py` | Register budget blueprint |
| Modify | `frontend/src/components/Settings/WantedSettings.tsx` | Preset dropdown |
| Modify | `frontend/src/types/settings.ts` | Type updates |
| Create | `frontend/src/components/Settings/WantedSettings.test.tsx` | Dropdown test |

Tests live next to their targets or under `backend/tests/` (mirroring package layout) to match existing conventions.

---

## Task 1 — Alembic migration: schema + data

**Files:**
- Create: `backend/db/migrations/versions/b1u2d3g4e5t6_phase1_schema.py`

- [ ] **Step 1: Create the migration skeleton**

```python
"""Phase 1 — scheduler foundation: budget tables, wanted_items state-machine, reset frozen items.

Revision ID: b1u2d3g4e5t6
Revises: h1i2j3k4l5m6
Create Date: 2026-04-16
"""

from alembic import op
import sqlalchemy as sa

revision = "b1u2d3g4e5t6"
down_revision = "h1i2j3k4l5m6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # New table: provider_budget_usage
    op.create_table(
        "provider_budget_usage",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("provider_name", sa.String(50), nullable=False),
        sa.Column("window_type", sa.String(10), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("calls_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("calls_limit", sa.Integer(), nullable=False),
        sa.UniqueConstraint(
            "provider_name", "window_type", "window_start",
            name="uq_budget_window",
        ),
    )
    op.create_index(
        "ix_budget_provider_window",
        "provider_budget_usage",
        ["provider_name", "window_type", sa.text("window_start DESC")],
    )

    # New table: provider_learned_limits
    op.create_table(
        "provider_learned_limits",
        sa.Column("provider_name", sa.String(50), nullable=False),
        sa.Column("window_type", sa.String(10), nullable=False),
        sa.Column("configured_limit", sa.Integer(), nullable=False),
        sa.Column("observed_limit", sa.Integer(), nullable=True),
        sa.Column("adjustment_factor", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("last_429_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consecutive_good_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("provider_name", "window_type"),
    )

    # wanted_items additions
    op.add_column("wanted_items", sa.Column("priority", sa.String(20),
                                             nullable=False, server_default="standard"))
    op.create_check_constraint(
        "ck_wanted_priority",
        "wanted_items",
        "priority IN ('premium', 'standard', 'backlog')",
    )
    op.add_column("wanted_items", sa.Column("failure_kind", sa.String(20), nullable=True))
    op.add_column("wanted_items", sa.Column("error_count", sa.Integer(),
                                             nullable=False, server_default="0"))
    op.add_column("wanted_items", sa.Column("last_error_at", sa.DateTime(timezone=True),
                                             nullable=True))

    op.create_index(
        "ix_wanted_fair_rotation",
        "wanted_items",
        ["status", sa.text("last_search_at NULLS FIRST"), "search_count"],
    )
    op.create_index(
        "ix_wanted_retry_after",
        "wanted_items",
        ["status", "retry_after"],
        postgresql_where=sa.text("retry_after IS NOT NULL"),
    )

    # Data migration: reset frozen items
    op.execute("""
        UPDATE wanted_items
        SET search_count = 0,
            error = NULL,
            retry_after = NULL
        WHERE error = 'Max search attempts reached'
    """)

    # Seed priority tiers
    op.execute("""
        UPDATE wanted_items
        SET priority = 'premium'
        WHERE added_at >= NOW() - INTERVAL '7 days'
    """)
    op.execute("""
        UPDATE wanted_items
        SET priority = 'backlog'
        WHERE search_count >= 3 AND added_at < NOW() - INTERVAL '180 days'
    """)


def downgrade() -> None:
    op.drop_index("ix_wanted_retry_after", table_name="wanted_items")
    op.drop_index("ix_wanted_fair_rotation", table_name="wanted_items")
    op.drop_constraint("ck_wanted_priority", "wanted_items", type_="check")
    op.drop_column("wanted_items", "last_error_at")
    op.drop_column("wanted_items", "error_count")
    op.drop_column("wanted_items", "failure_kind")
    op.drop_column("wanted_items", "priority")
    op.drop_table("provider_learned_limits")
    op.drop_index("ix_budget_provider_window", table_name="provider_budget_usage")
    op.drop_table("provider_budget_usage")
```

- [ ] **Step 2: Dry-run migration against a clean SQLite to verify syntax**

Run: `cd backend && python -c "from sqlalchemy import create_engine; from db.migrations.versions.b1u2d3g4e5t6_phase1_schema import upgrade; e = create_engine('sqlite:///:memory:'); print('Migration module loads OK')"`
Expected output: `Migration module loads OK`

- [ ] **Step 3: Apply against a copy of the prod DB dump**

```bash
ssh root@192.168.178.36 "docker exec sublarr-postgres pg_dump -U sublarr sublarr" > /tmp/prod.sql
# restore to a local test DB and run alembic upgrade head
```
Expected: no errors, `alembic_version` advances to `b1u2d3g4e5t6`, 33 frozen items reset.

- [ ] **Step 4: Commit**

```bash
git add backend/db/migrations/versions/b1u2d3g4e5t6_phase1_schema.py
git commit -m "feat(scheduler): alembic migration for Phase 1 (budget tables, failure kind, priority)"
```

---

## Task 2 — ProviderBudgetManager core class

**Files:**
- Create: `backend/services/provider_budget.py`
- Create: `backend/tests/test_provider_budget.py`

- [ ] **Step 1: Write the failing test for window boundary calculation**

```python
# backend/tests/test_provider_budget.py
from datetime import datetime, timezone
from services.provider_budget import BudgetWindow, window_start_for


def test_window_start_for_second_truncates_to_second():
    now = datetime(2026, 4, 16, 12, 34, 56, 789123, tzinfo=timezone.utc)
    result = window_start_for(BudgetWindow.SECOND, now)
    assert result == datetime(2026, 4, 16, 12, 34, 56, tzinfo=timezone.utc)


def test_window_start_for_hour_truncates_to_hour():
    now = datetime(2026, 4, 16, 12, 34, 56, tzinfo=timezone.utc)
    result = window_start_for(BudgetWindow.HOUR, now)
    assert result == datetime(2026, 4, 16, 12, 0, 0, tzinfo=timezone.utc)


def test_window_start_for_day_truncates_to_midnight_utc():
    now = datetime(2026, 4, 16, 12, 34, 56, tzinfo=timezone.utc)
    result = window_start_for(BudgetWindow.DAY, now)
    assert result == datetime(2026, 4, 16, 0, 0, 0, tzinfo=timezone.utc)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_provider_budget.py -v`
Expected: `ModuleNotFoundError: No module named 'services.provider_budget'`

- [ ] **Step 3: Implement the module minimum to pass**

```python
# backend/services/provider_budget.py
"""Provider-budget manager — tracks per-provider API calls across three sliding windows."""

from __future__ import annotations

import enum
from datetime import datetime, timezone


class BudgetWindow(str, enum.Enum):
    SECOND = "second"
    HOUR = "hour"
    DAY = "day"


def window_start_for(window: BudgetWindow, now: datetime | None = None) -> datetime:
    """Return the UTC start of the enclosing window for `now`."""
    if now is None:
        now = datetime.now(timezone.utc)
    if window is BudgetWindow.SECOND:
        return now.replace(microsecond=0)
    if window is BudgetWindow.HOUR:
        return now.replace(minute=0, second=0, microsecond=0)
    if window is BudgetWindow.DAY:
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    raise ValueError(f"unknown window: {window}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_provider_budget.py -v`
Expected: 3 passed.

- [ ] **Step 5: Add the check/consume/status tests (failing)**

```python
# append to backend/tests/test_provider_budget.py
from unittest.mock import MagicMock
from services.provider_budget import ProviderBudgetManager, BudgetDecision


def test_budget_allows_when_under_limit(monkeypatch):
    mgr = ProviderBudgetManager(redis=None, safety_margin_pct=20)
    limits = {"second": 5, "hour": 200, "day": 1000}
    decision = mgr.check("opensubtitles", limits=limits, now=datetime(2026, 4, 16, tzinfo=timezone.utc))
    assert decision.allow is True
    assert decision.wait_seconds == 0


def test_budget_blocks_when_day_exhausted():
    mgr = ProviderBudgetManager(redis=None, safety_margin_pct=0)
    mgr._in_memory_counts[("opensubtitles", "day", datetime(2026, 4, 16, tzinfo=timezone.utc))] = 1000
    decision = mgr.check("opensubtitles", limits={"day": 1000}, now=datetime(2026, 4, 16, 12, tzinfo=timezone.utc))
    assert decision.allow is False
    assert decision.wait_seconds > 0  # until next day reset


def test_consume_increments_all_windows():
    mgr = ProviderBudgetManager(redis=None, safety_margin_pct=0)
    now = datetime(2026, 4, 16, 12, 34, 56, tzinfo=timezone.utc)
    mgr.consume("opensubtitles", now=now)
    mgr.consume("opensubtitles", now=now)
    usage = mgr.get_usage("opensubtitles", now=now)
    assert usage["second"] == 2
    assert usage["hour"] == 2
    assert usage["day"] == 2
```

- [ ] **Step 6: Implement the manager**

```python
# append to backend/services/provider_budget.py
from collections import defaultdict
from dataclasses import dataclass


@dataclass(frozen=True)
class BudgetDecision:
    allow: bool
    wait_seconds: int = 0
    reason: str = ""


class ProviderBudgetManager:
    """Tracks provider API-call usage in three windows (second, hour, day).

    Uses Redis when available for cross-process sharing; falls back to an in-memory dict
    for single-process runs and tests. The in-memory backend is NOT safe across workers.
    """

    def __init__(self, redis=None, safety_margin_pct: int = 20):
        self._redis = redis
        self._safety = safety_margin_pct
        self._in_memory_counts: dict[tuple[str, str, datetime], int] = defaultdict(int)

    def _adjusted_limit(self, raw_limit: int) -> int:
        if self._safety <= 0:
            return raw_limit
        return int(raw_limit * (100 - self._safety) / 100)

    def check(
        self,
        provider: str,
        limits: dict[str, int],
        now: datetime | None = None,
    ) -> BudgetDecision:
        if now is None:
            now = datetime.now(timezone.utc)
        for window_name, raw_limit in limits.items():
            window = BudgetWindow(window_name)
            limit = self._adjusted_limit(raw_limit)
            used = self._get_count(provider, window, now)
            if used >= limit:
                wait = self._seconds_until_next_window(window, now)
                return BudgetDecision(
                    allow=False,
                    wait_seconds=wait,
                    reason=f"{window.value} limit reached ({used}/{limit})",
                )
        return BudgetDecision(allow=True)

    def consume(self, provider: str, now: datetime | None = None) -> None:
        if now is None:
            now = datetime.now(timezone.utc)
        for window in BudgetWindow:
            key = (provider, window.value, window_start_for(window, now))
            self._in_memory_counts[key] += 1
            if self._redis is not None:
                redis_key = f"budget:{provider}:{window.value}:{key[2].isoformat()}"
                try:
                    self._redis.incr(redis_key)
                    self._redis.expire(redis_key, self._ttl_for(window))
                except Exception:  # noqa: BLE001 — Redis failure must not break search
                    pass

    def get_usage(self, provider: str, now: datetime | None = None) -> dict[str, int]:
        if now is None:
            now = datetime.now(timezone.utc)
        return {
            w.value: self._get_count(provider, w, now) for w in BudgetWindow
        }

    def _get_count(self, provider: str, window: BudgetWindow, now: datetime) -> int:
        key = (provider, window.value, window_start_for(window, now))
        # Redis takes precedence when available
        if self._redis is not None:
            redis_key = f"budget:{provider}:{window.value}:{key[2].isoformat()}"
            try:
                val = self._redis.get(redis_key)
                if val is not None:
                    return int(val)
            except Exception:  # noqa: BLE001
                pass
        return self._in_memory_counts.get(key, 0)

    @staticmethod
    def _seconds_until_next_window(window: BudgetWindow, now: datetime) -> int:
        if window is BudgetWindow.SECOND:
            return 1
        if window is BudgetWindow.HOUR:
            return 3600 - (now.minute * 60 + now.second)
        if window is BudgetWindow.DAY:
            return 86400 - (now.hour * 3600 + now.minute * 60 + now.second)
        raise ValueError(window)

    @staticmethod
    def _ttl_for(window: BudgetWindow) -> int:
        return {
            BudgetWindow.SECOND: 2,
            BudgetWindow.HOUR: 3700,
            BudgetWindow.DAY: 90000,
        }[window]
```

- [ ] **Step 7: Run full test file**

Run: `cd backend && python -m pytest tests/test_provider_budget.py -v`
Expected: 6 passed.

- [ ] **Step 8: Commit**

```bash
git add backend/services/provider_budget.py backend/tests/test_provider_budget.py
git commit -m "feat(scheduler): ProviderBudgetManager with per-second/hour/day window tracking"
```

---

## Task 3 — Add `rate_limits` metadata to providers

**Files:**
- Modify: `backend/providers/base.py` (add ClassVar annotation)
- Modify: each of the 10 enabled providers (add `rate_limits` classvar)

- [ ] **Step 1: Write a failing test covering all enabled providers**

```python
# backend/tests/test_provider_rate_limits.py
import pytest
from providers import get_provider_manager


ENABLED = [
    "animetosho", "opensubtitles", "subdl", "gestdown",
    "kitsunekko", "napisy24", "titrari", "subscene",
    "addic7ed", "tvsubtitles",
]


@pytest.mark.parametrize("name", ENABLED)
def test_each_enabled_provider_declares_rate_limits(name):
    mgr = get_provider_manager()
    provider_cls = type(mgr._providers[name])
    limits = getattr(provider_cls, "rate_limits", None)
    assert limits is not None, f"{name} is missing rate_limits classvar"
    assert "free" in limits, f"{name}.rate_limits must have 'free' tier"
    for tier, windows in limits.items():
        assert "day" in windows, f"{name}.{tier} missing 'day' limit"
        assert windows["day"] > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_provider_rate_limits.py -v`
Expected: 10 failures (`rate_limits classvar is missing`).

- [ ] **Step 3: Add `rate_limits` to base class as the interface contract**

```python
# backend/providers/base.py — add near top of SubtitleProvider class
from typing import ClassVar


class SubtitleProvider(ABC):
    # ... existing docstring and fields ...

    #: Per-tier rate limits. Subclasses MUST override.
    #: Format: {"free": {"second": int, "hour": int, "day": int}, "vip": {...}}
    rate_limits: ClassVar[dict[str, dict[str, int]]] = {
        "free": {"second": 1, "hour": 60, "day": 500},
    }
```

- [ ] **Step 4: Fill real limits into each provider**

Each provider file gets a `rate_limits` classvar near the class header. Exact values:

```python
# opensubtitles.py
rate_limits: ClassVar[dict[str, dict[str, int]]] = {
    "free":  {"second": 5,  "hour": 200,  "day": 1000},
    "vip":   {"second": 10, "hour": 1000, "day": 10000},
    "vip+":  {"second": 20, "hour": 5000, "day": 100000},
}

# subdl.py
rate_limits: ClassVar[dict[str, dict[str, int]]] = {
    "free": {"second": 2, "hour": 50, "day": 100},
    "pro":  {"second": 5, "hour": 500, "day": 5000},
}

# animetosho.py  (no official limit; conservative self-imposed)
rate_limits: ClassVar[dict[str, dict[str, int]]] = {
    "free": {"second": 3, "hour": 500, "day": 10000},
}

# gestdown.py, kitsunekko.py, titrari.py, subscene.py (scraping-based, conservative)
rate_limits: ClassVar[dict[str, dict[str, int]]] = {
    "free": {"second": 1, "hour": 30, "day": 300},
}

# addic7ed.py  (Cloudflare-sensitive)
rate_limits: ClassVar[dict[str, dict[str, int]]] = {
    "free": {"second": 1, "hour": 20, "day": 200},
}

# napisy24.py, tvsubtitles.py (modest)
rate_limits: ClassVar[dict[str, dict[str, int]]] = {
    "free": {"second": 1, "hour": 40, "day": 400},
}
```

- [ ] **Step 5: Run tests**

Run: `cd backend && python -m pytest tests/test_provider_rate_limits.py -v`
Expected: 10 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/providers/ backend/tests/test_provider_rate_limits.py
git commit -m "feat(providers): declare rate_limits metadata per tier"
```

---

## Task 4 — OpenSubtitles VIP auto-detect

**Files:**
- Modify: `backend/providers/opensubtitles.py`
- Create or extend: `backend/tests/test_opensubtitles_tier.py`

- [ ] **Step 1: Failing test for tier resolution**

```python
# backend/tests/test_opensubtitles_tier.py
from unittest.mock import MagicMock, patch
from providers.opensubtitles import OpenSubtitlesProvider


def test_detects_free_tier_from_user_info_response():
    fake_session = MagicMock()
    fake_session.get.return_value.status_code = 200
    fake_session.get.return_value.json.return_value = {
        "data": {"level": "Sub leecher", "vip": False},
    }
    p = OpenSubtitlesProvider.__new__(OpenSubtitlesProvider)
    p.session = fake_session
    p.api_key = "x"
    assert p.detect_tier() == "free"


def test_detects_vip_tier():
    fake_session = MagicMock()
    fake_session.get.return_value.status_code = 200
    fake_session.get.return_value.json.return_value = {
        "data": {"level": "VIP member", "vip": True},
    }
    p = OpenSubtitlesProvider.__new__(OpenSubtitlesProvider)
    p.session = fake_session
    p.api_key = "x"
    assert p.detect_tier() == "vip"


def test_defaults_to_free_on_failure():
    fake_session = MagicMock()
    fake_session.get.side_effect = Exception("network")
    p = OpenSubtitlesProvider.__new__(OpenSubtitlesProvider)
    p.session = fake_session
    p.api_key = "x"
    assert p.detect_tier() == "free"
```

- [ ] **Step 2: Run → fails with AttributeError**

Run: `cd backend && python -m pytest tests/test_opensubtitles_tier.py -v`
Expected: `AttributeError: 'OpenSubtitlesProvider' object has no attribute 'detect_tier'`.

- [ ] **Step 3: Implement `detect_tier`**

```python
# backend/providers/opensubtitles.py — add as method on OpenSubtitlesProvider
def detect_tier(self) -> str:
    """Query /api/v1/infos/user to determine the current account tier.

    Returns: 'free', 'vip', or 'vip+' — defaults to 'free' on any error.
    """
    try:
        resp = self.session.get("https://api.opensubtitles.com/api/v1/infos/user")
        if resp.status_code != 200:
            return "free"
        data = resp.json().get("data", {})
        if data.get("vip"):
            return "vip+" if data.get("level", "").lower().startswith("vip+") else "vip"
        return "free"
    except Exception:  # noqa: BLE001
        return "free"
```

- [ ] **Step 4: Run → passes**

Run: `cd backend && python -m pytest tests/test_opensubtitles_tier.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/providers/opensubtitles.py backend/tests/test_opensubtitles_tier.py
git commit -m "feat(opensubtitles): detect_tier() auto-resolves free/vip/vip+ from user info"
```

---

## Task 5 — Fair-rotation repository query

**Files:**
- Modify: `backend/db/repositories/wanted.py`
- Modify: `backend/db/wanted.py`
- Create: `backend/tests/test_wanted_repo_scheduled_search.py`

- [ ] **Step 1: Failing test for order presets**

```python
# backend/tests/test_wanted_repo_scheduled_search.py
from datetime import datetime, timedelta, timezone
import pytest
from db.repositories.wanted import WantedItemRepository


@pytest.fixture
def seed_items(db_session):
    # Three items: one never searched (NULL), one searched 2h ago, one searched 5d ago
    now = datetime.now(timezone.utc)
    items = [
        {"id": 1, "title": "A", "last_search_at": None, "search_count": 0, "added_at": now},
        {"id": 2, "title": "B", "last_search_at": now - timedelta(hours=2),
         "search_count": 2, "added_at": now - timedelta(days=10)},
        {"id": 3, "title": "C", "last_search_at": now - timedelta(days=5),
         "search_count": 1, "added_at": now - timedelta(days=1)},
    ]
    # insert ...
    return items


def test_fair_order_returns_never_searched_first(seed_items, db_session):
    repo = WantedItemRepository(db_session)
    result = repo.get_items_for_scheduled_search(limit=3, order="fair")
    ids = [r["id"] for r in result]
    # NULL first, then oldest last_search_at, then smallest search_count
    assert ids == [1, 3, 2]


def test_newest_first_order_preserves_legacy_behavior(seed_items, db_session):
    repo = WantedItemRepository(db_session)
    result = repo.get_items_for_scheduled_search(limit=3, order="newest_first")
    ids = [r["id"] for r in result]
    assert ids == [1, 3, 2]  # ordered by added_at DESC: A(now) > C(−1d) > B(−10d)


def test_weighted_order_prioritizes_recent_episodes(seed_items, db_session):
    repo = WantedItemRepository(db_session)
    result = repo.get_items_for_scheduled_search(limit=3, order="weighted")
    ids = [r["id"] for r in result]
    # "Recent" bucket (<30d added_at): A, C → fair within bucket → A (NULL first) → C
    # "Old" bucket: B
    assert ids == [1, 3, 2]
```

- [ ] **Step 2: Run → fails with AttributeError**

Run: `cd backend && python -m pytest tests/test_wanted_repo_scheduled_search.py -v`
Expected: `AttributeError: 'WantedItemRepository' object has no attribute 'get_items_for_scheduled_search'`.

- [ ] **Step 3: Implement the method**

```python
# backend/db/repositories/wanted.py — add as method on WantedItemRepository
def get_items_for_scheduled_search(
    self,
    limit: int,
    order: str = "fair",
) -> list[dict]:
    """Return wanted items eligible for scheduler-driven search, ordered by preset.

    Args:
        limit: max rows to return (the safety cap).
        order: 'fair' | 'newest_first' | 'weighted'.
    """
    query = self.session.query(WantedItem).filter(WantedItem.status == "wanted")

    if order == "fair":
        query = query.order_by(
            sa.nulls_first(WantedItem.last_search_at.asc()),
            WantedItem.search_count.asc(),
        )
    elif order == "newest_first":
        query = query.order_by(WantedItem.added_at.desc())
    elif order == "weighted":
        from sqlalchemy import case
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        recent_bucket = case(
            (WantedItem.added_at >= cutoff, 0),
            else_=1,
        )
        query = query.order_by(
            recent_bucket,
            sa.nulls_first(WantedItem.last_search_at.asc()),
            WantedItem.search_count.asc(),
        )
    else:
        raise ValueError(f"unknown order: {order}")

    return [self._row_to_dict(r) for r in query.limit(limit).all()]
```

- [ ] **Step 4: Add the facade function**

```python
# backend/db/wanted.py — add near get_wanted_items
def get_items_for_scheduled_search(limit: int, order: str = "fair") -> list[dict]:
    return _get_repo().get_items_for_scheduled_search(limit, order)
```

- [ ] **Step 5: Run tests**

Run: `cd backend && python -m pytest tests/test_wanted_repo_scheduled_search.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/db/repositories/wanted.py backend/db/wanted.py backend/tests/test_wanted_repo_scheduled_search.py
git commit -m "feat(scheduler): fair-rotation / weighted item selection for scheduled search"
```

---

## Task 6 — Failure-kind split + exponential backoff

**Files:**
- Modify: `backend/services/wanted_search_runner.py` (add `_update_after_search` helper, modify `_filter_eligible`)
- Modify: `backend/db/wanted.py` (extend `update_wanted_search`)
- Modify: `backend/db/repositories/wanted.py`
- Modify: `backend/tests/test_wanted_scanner.py` (or create new `test_wanted_search_runner.py`)

- [ ] **Step 1: Failing test for exponential backoff on provider errors**

```python
# backend/tests/test_wanted_search_runner_backoff.py
from datetime import datetime, timedelta, timezone
from services.wanted_search_runner import compute_retry_after_for_error


def test_first_error_backs_off_6h():
    now = datetime(2026, 4, 16, 10, 0, 0, tzinfo=timezone.utc)
    result = compute_retry_after_for_error(error_count=1, now=now)
    assert result == now + timedelta(hours=6)


def test_second_error_backs_off_24h():
    now = datetime(2026, 4, 16, 10, 0, 0, tzinfo=timezone.utc)
    assert compute_retry_after_for_error(2, now) == now + timedelta(hours=24)


def test_third_error_backs_off_3d():
    now = datetime(2026, 4, 16, 10, 0, 0, tzinfo=timezone.utc)
    assert compute_retry_after_for_error(3, now) == now + timedelta(days=3)


def test_fourth_error_backs_off_7d():
    now = datetime(2026, 4, 16, 10, 0, 0, tzinfo=timezone.utc)
    assert compute_retry_after_for_error(4, now) == now + timedelta(days=7)


def test_fifth_and_above_cap_at_30d():
    now = datetime(2026, 4, 16, 10, 0, 0, tzinfo=timezone.utc)
    assert compute_retry_after_for_error(5, now) == now + timedelta(days=30)
    assert compute_retry_after_for_error(99, now) == now + timedelta(days=30)
```

- [ ] **Step 2: Run → fails**

Run: `cd backend && python -m pytest tests/test_wanted_search_runner_backoff.py -v`
Expected: `ImportError: cannot import name 'compute_retry_after_for_error'`.

- [ ] **Step 3: Implement the pure function**

```python
# backend/services/wanted_search_runner.py — add at module top level
_ERROR_BACKOFF_TABLE = [
    timedelta(hours=6),
    timedelta(hours=24),
    timedelta(days=3),
    timedelta(days=7),
    timedelta(days=30),
]


def compute_retry_after_for_error(error_count: int, now: datetime) -> datetime:
    """Exponential backoff for *provider-error* outcomes.

    Provider errors do NOT exhaust search_count — they only delay the next try.
    """
    idx = max(0, min(error_count - 1, len(_ERROR_BACKOFF_TABLE) - 1))
    return now + _ERROR_BACKOFF_TABLE[idx]
```

- [ ] **Step 4: Run → passes**

Run: `cd backend && python -m pytest tests/test_wanted_search_runner_backoff.py -v`
Expected: 5 passed.

- [ ] **Step 5: Failing test for failure_kind recording**

```python
# append to backend/tests/test_wanted_search_runner_backoff.py
from unittest.mock import patch
from services.wanted_search_runner import record_search_outcome


def test_provider_error_does_not_increment_search_count(db_session):
    _insert_item(db_session, id=1, search_count=0, error_count=0)
    record_search_outcome(
        item_id=1, kind="provider_error", error_message="HTTP 429",
    )
    row = _fetch(db_session, 1)
    assert row["search_count"] == 0          # unchanged
    assert row["error_count"] == 1           # incremented
    assert row["failure_kind"] == "provider_error"
    assert row["retry_after"] is not None


def test_no_result_increments_search_count_only(db_session):
    _insert_item(db_session, id=2, search_count=0, error_count=0)
    record_search_outcome(item_id=2, kind="no_result")
    row = _fetch(db_session, 2)
    assert row["search_count"] == 1
    assert row["error_count"] == 0
    assert row["failure_kind"] == "no_result"


def test_max_attempts_switches_to_slow_mode_not_freeze(db_session):
    _insert_item(db_session, id=3, search_count=3, error_count=0)
    record_search_outcome(item_id=3, kind="no_result")
    row = _fetch(db_session, 3)
    # No more 'Max search attempts reached' freezing
    assert row["error"] != "Max search attempts reached"
    # Slow-mode: retry after 30 days
    assert row["retry_after"] is not None
```

- [ ] **Step 6: Run → fails**

Expected: `ImportError: cannot import name 'record_search_outcome'`.

- [ ] **Step 7: Implement `record_search_outcome`**

```python
# backend/services/wanted_search_runner.py
from db.wanted import update_wanted_search_outcome  # new function added next


def record_search_outcome(
    item_id: int,
    kind: str,                       # 'no_result' | 'provider_error' | 'found'
    error_message: str | None = None,
) -> None:
    """Central mutation point for any scheduler-driven search outcome.

    - 'found': clears failure state
    - 'no_result': increments search_count, sets small backoff, may enter slow-mode
    - 'provider_error': increments error_count ONLY, uses exp backoff, does NOT freeze
    """
    now = datetime.now(timezone.utc)
    settings = get_settings()

    if kind == "found":
        update_wanted_search_outcome(
            item_id,
            status="found",
            reset_failure=True,
        )
        return

    if kind == "provider_error":
        # Read current error_count, bump, compute retry
        from db.wanted import get_wanted_item
        item = get_wanted_item(item_id)
        new_err = (item.get("error_count") or 0) + 1
        retry_at = compute_retry_after_for_error(new_err, now)
        update_wanted_search_outcome(
            item_id,
            failure_kind="provider_error",
            error_count=new_err,
            retry_after=retry_at,
            last_error_at=now,
            error_message=error_message,
        )
        return

    if kind == "no_result":
        from db.wanted import get_wanted_item
        item = get_wanted_item(item_id)
        new_count = (item.get("search_count") or 0) + 1
        base_h = getattr(settings, "wanted_backoff_base_hours", 1.0)
        cap_h = getattr(settings, "wanted_backoff_cap_hours", 168)
        max_attempts = getattr(settings, "wanted_max_search_attempts", 3)
        if new_count >= max_attempts:
            # SLOW-MODE — no more freezing
            retry_at = now + timedelta(days=30)
            failure_kind = "no_result_slow"
        else:
            retry_at = now + timedelta(hours=min(base_h * (2 ** (new_count - 1)), cap_h))
            failure_kind = "no_result"
        update_wanted_search_outcome(
            item_id,
            search_count=new_count,
            failure_kind=failure_kind,
            retry_after=retry_at,
            last_search_at=now,
        )
        return

    raise ValueError(f"unknown outcome kind: {kind}")
```

- [ ] **Step 8: Add DB helper**

```python
# backend/db/wanted.py
def update_wanted_search_outcome(item_id: int, **fields) -> None:
    return _get_repo().update_wanted_search_outcome(item_id, **fields)

# backend/db/repositories/wanted.py — add method
def update_wanted_search_outcome(self, item_id: int, **fields) -> None:
    allowed = {
        "status", "search_count", "error_count", "failure_kind",
        "retry_after", "last_error_at", "last_search_at",
    }
    patch = {k: v for k, v in fields.items() if k in allowed}
    if fields.get("reset_failure"):
        patch.update({"error_count": 0, "failure_kind": None, "error": None, "retry_after": None})
    if "error_message" in fields and fields["error_message"] is not None:
        patch["error"] = fields["error_message"][:500]
    self.session.query(WantedItem).filter(WantedItem.id == item_id).update(patch)
    self.session.commit()
```

- [ ] **Step 9: Run the full runner test file**

Run: `cd backend && python -m pytest tests/test_wanted_search_runner_backoff.py -v`
Expected: 8 passed.

- [ ] **Step 10: Commit**

```bash
git add backend/services/wanted_search_runner.py backend/db/wanted.py backend/db/repositories/wanted.py backend/tests/test_wanted_search_runner_backoff.py
git commit -m "feat(scheduler): split failure kinds, exp backoff, slow-mode instead of freeze"
```

---

## Task 7 — Wire budget gate into SearchCoordinator

**Files:**
- Modify: `backend/providers/search_coordinator.py`
- Modify: `backend/tests/test_search_coordinator.py` (extend or create)

- [ ] **Step 1: Failing test — budget-exhausted provider is skipped, not errored**

```python
# backend/tests/test_search_coordinator_budget.py
from unittest.mock import MagicMock
from providers.search_coordinator import SearchCoordinator
from services.provider_budget import BudgetDecision


def test_budget_exhausted_provider_is_skipped_silently():
    budget = MagicMock()
    budget.check.return_value = BudgetDecision(allow=False, wait_seconds=3600, reason="day limit")
    coord = SearchCoordinator(providers={"opensubtitles": MagicMock()}, budget=budget)
    query = MagicMock()
    query.languages = ["de"]
    results = coord.search(query)
    assert results == []
    # Provider search must NOT have been called
    coord._providers["opensubtitles"].search.assert_not_called()
    # Circuit breaker must NOT be tripped (this was a budget decision, not a provider failure)
    # (verify via coordinator internals — exact assertion depends on existing CB API)


def test_budget_allow_path_proceeds_normally():
    budget = MagicMock()
    budget.check.return_value = BudgetDecision(allow=True)
    provider = MagicMock()
    provider.search.return_value = []
    coord = SearchCoordinator(providers={"opensubtitles": provider}, budget=budget)
    query = MagicMock()
    query.languages = ["de"]
    coord.search(query)
    provider.search.assert_called_once()
    budget.consume.assert_called_once_with("opensubtitles")
```

- [ ] **Step 2: Run → fails**

Expected: tests fail because `SearchCoordinator.__init__` doesn't accept `budget=`.

- [ ] **Step 3: Wire the budget gate**

```python
# backend/providers/search_coordinator.py — extend __init__ + search()
class SearchCoordinator:
    def __init__(self, providers, circuit_breakers=None, settings=None, budget=None):
        # ... existing code ...
        self._budget = budget  # ProviderBudgetManager or None

    # inside search(), before submitting a provider future:
    for name, provider in self._providers.items():
        # ... existing skip checks (auto-disable, circuit breaker, rate limit) ...

        if self._budget is not None:
            tier = getattr(provider, "tier", "free")
            limits = type(provider).rate_limits.get(tier, type(provider).rate_limits.get("free"))
            decision = self._budget.check(name, limits)
            if not decision.allow:
                logger.debug(
                    "Skipping provider %s — budget: %s", name, decision.reason,
                )
                continue
            self._budget.consume(name)

        # ... existing executor.submit ...
```

- [ ] **Step 4: Wire constructor — provide budget where coordinator is built**

```python
# backend/providers/__init__.py (or wherever SearchCoordinator is instantiated)
from services.provider_budget import ProviderBudgetManager

_budget_manager = ProviderBudgetManager(redis=get_redis_client(), safety_margin_pct=20)
# pass into SearchCoordinator()
```

- [ ] **Step 5: Run tests**

Run: `cd backend && python -m pytest tests/test_search_coordinator_budget.py -v`
Expected: 2 passed.

- [ ] **Step 6: Run existing coordinator tests — no regression**

Run: `cd backend && python -m pytest tests/test_search_coordinator.py tests/test_provider_manager.py -v`
Expected: all existing tests still pass.

- [ ] **Step 7: Commit**

```bash
git add backend/providers/search_coordinator.py backend/providers/__init__.py backend/tests/test_search_coordinator_budget.py
git commit -m "feat(scheduler): integrate ProviderBudgetManager into SearchCoordinator"
```

---

## Task 8 — Scheduler calls new item selector + new config key

**Files:**
- Modify: `backend/config.py` (add `wanted_search_order`, bump `wanted_search_max_items_per_run` default)
- Modify: `backend/services/wanted_search_runner.py::run_wanted_search` (use new selector)
- Modify: `backend/tests/test_wanted_search_runner.py` (extend)

- [ ] **Step 1: Failing test**

```python
# backend/tests/test_run_wanted_search_ordering.py
from unittest.mock import patch
from services.wanted_search_runner import run_wanted_search


def test_run_wanted_search_uses_configured_order(monkeypatch):
    monkeypatch.setattr("config.get_settings",
                        lambda: _fake_settings(wanted_search_order="fair",
                                               wanted_search_max_items_per_run=100))
    captured = {}
    def fake_select(limit, order):
        captured["limit"], captured["order"] = limit, order
        return []
    monkeypatch.setattr("db.wanted.get_items_for_scheduled_search", fake_select)
    run_wanted_search()
    assert captured == {"limit": 100, "order": "fair"}
```

- [ ] **Step 2: Run → fails**

Expected: `run_wanted_search` still calls the old `get_wanted_items(page=1, ...)`.

- [ ] **Step 3: Modify `run_wanted_search` to use new selector + config key**

```python
# backend/services/wanted_search_runner.py — replace the item-fetch section
from db.wanted import get_items_for_scheduled_search

settings = get_settings()
max_items = settings.wanted_search_max_items_per_run
order = getattr(settings, "wanted_search_order", "fair")
items = get_items_for_scheduled_search(limit=max_items, order=order)
```

- [ ] **Step 4: Add new config**

```python
# backend/config.py — in the Wanted Search Scheduler section
wanted_search_order: str = "fair"   # fair | newest_first | weighted
wanted_search_max_items_per_run: int = 500   # was 50
```

- [ ] **Step 5: Run tests + regression**

Run: `cd backend && python -m pytest tests/test_run_wanted_search_ordering.py tests/test_wanted_scanner.py -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/config.py backend/services/wanted_search_runner.py backend/tests/test_run_wanted_search_ordering.py
git commit -m "feat(scheduler): config-driven order preset, bump default max_items to 500"
```

---

## Task 9 — Budget API endpoint

**Files:**
- Create: `backend/routes/system/budget.py`
- Modify: `backend/routes/system/__init__.py`
- Create: `backend/tests/test_routes_system_budget.py`

- [ ] **Step 1: Failing test**

```python
# backend/tests/test_routes_system_budget.py
def test_budget_endpoint_returns_state_for_enabled_providers(client, admin_api_key):
    resp = client.get("/api/v1/system/budget", headers={"X-API-Key": admin_api_key})
    assert resp.status_code == 200
    data = resp.get_json()
    assert "providers" in data
    for p in data["providers"]:
        assert {"name", "tier", "usage", "limits", "reset_seconds"} <= p.keys()
```

- [ ] **Step 2: Run → 404**

- [ ] **Step 3: Implement route**

```python
# backend/routes/system/budget.py
from flask import Blueprint, jsonify
from auth import require_api_key
from providers import get_provider_manager
from services.provider_budget import get_budget_manager

bp = Blueprint("system_budget", __name__)


@bp.route("/system/budget", methods=["GET"])
@require_api_key
def get_budget_state():
    mgr = get_provider_manager()
    budget = get_budget_manager()
    providers_out = []
    for name, provider in mgr._providers.items():
        tier = getattr(provider, "tier", "free")
        limits = type(provider).rate_limits.get(tier, {})
        usage = budget.get_usage(name)
        providers_out.append({
            "name": name,
            "tier": tier,
            "limits": limits,
            "usage": usage,
            "reset_seconds": {
                w: budget._seconds_until_next_window_for(w) for w in ("second", "hour", "day")
            },
        })
    return jsonify({"providers": providers_out})
```

- [ ] **Step 4: Register blueprint**

```python
# backend/routes/system/__init__.py
from routes.system.budget import bp as budget_bp
# in register_blueprints:
app.register_blueprint(budget_bp, url_prefix="/api/v1")
```

- [ ] **Step 5: Run tests**

Run: `cd backend && python -m pytest tests/test_routes_system_budget.py -v`
Expected: passing.

- [ ] **Step 6: Commit**

```bash
git add backend/routes/system/budget.py backend/routes/system/__init__.py backend/tests/test_routes_system_budget.py
git commit -m "feat(api): /api/v1/system/budget exposes per-provider budget state"
```

---

## Task 10 — Frontend: scheduler preset dropdown

**Files:**
- Modify: `frontend/src/components/Settings/WantedSettings.tsx`
- Modify: `frontend/src/types/settings.ts`
- Create: `frontend/src/components/Settings/WantedSettings.test.tsx`

- [ ] **Step 1: Failing Vitest test**

```tsx
// frontend/src/components/Settings/WantedSettings.test.tsx
import { render, screen, fireEvent } from "@testing-library/react";
import WantedSettings from "./WantedSettings";

test("scheduler order dropdown renders with three options", () => {
  render(<WantedSettings />);
  const select = screen.getByLabelText(/Suchreihenfolge/i);
  const options = Array.from(select.querySelectorAll("option")).map((o) => o.value);
  expect(options).toEqual(["fair", "newest_first", "weighted"]);
});

test("changing preset fires onChange with new value", async () => {
  const onSave = vi.fn();
  render(<WantedSettings onSave={onSave} />);
  const select = screen.getByLabelText(/Suchreihenfolge/i);
  fireEvent.change(select, { target: { value: "weighted" } });
  // ... wait for debounce ...
  expect(onSave).toHaveBeenCalledWith(
    expect.objectContaining({ wanted_search_order: "weighted" }),
  );
});
```

- [ ] **Step 2: Run → fails**

Run: `cd frontend && npx vitest run src/components/Settings/WantedSettings.test.tsx`
Expected: "Unable to find element with label Suchreihenfolge".

- [ ] **Step 3: Add dropdown to component**

```tsx
// frontend/src/components/Settings/WantedSettings.tsx — add inside the form
<FormGroup>
  <Label htmlFor="wanted-order">Suchreihenfolge</Label>
  <Select
    id="wanted-order"
    value={settings.wanted_search_order ?? "fair"}
    onChange={(e) => updateField("wanted_search_order", e.target.value)}
  >
    <option value="fair">Fair Rotation (empfohlen)</option>
    <option value="newest_first">Neueste zuerst</option>
    <option value="weighted">Gewichtet (neue Episoden priorisiert)</option>
  </Select>
  <HelpText>
    Bestimmt in welcher Reihenfolge der Auto-Scheduler die Warteschlange abarbeitet.
  </HelpText>
</FormGroup>
```

- [ ] **Step 4: Add to type definitions**

```ts
// frontend/src/types/settings.ts
export interface Settings {
  // ... existing fields ...
  wanted_search_order?: "fair" | "newest_first" | "weighted";
}
```

- [ ] **Step 5: Run tests**

Run: `cd frontend && npx vitest run src/components/Settings/WantedSettings.test.tsx`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/Settings/WantedSettings.tsx frontend/src/components/Settings/WantedSettings.test.tsx frontend/src/types/settings.ts
git commit -m "feat(ui): scheduler order preset dropdown in wanted settings"
```

---

## Task 11 — End-to-end smoke test

**Files:**
- Create: `backend/tests/test_phase1_e2e.py`

- [ ] **Step 1: Write end-to-end happy-path scenario**

```python
# backend/tests/test_phase1_e2e.py
"""End-to-end: simulate a full Phase 1 scheduler cycle."""

def test_phase1_full_cycle(db_session, fake_redis, mock_providers):
    # Seed 100 wanted items, 30 with null last_search_at, others spread across 7 days
    _seed_mixed_library(db_session, count=100)

    # Configure: fair order, max_items=20, one provider returns DE hit, one 429s
    _configure_settings(db_session, wanted_search_order="fair", max_items=20)
    mock_providers["opensubtitles"].response_cycle = [{"429": True}] * 3  # all 429
    mock_providers["animetosho"].response_cycle = ["de_hit"] * 20

    # Run the scheduler
    from services.wanted_search_runner import run_wanted_search
    summary = run_wanted_search()

    # Assert: 20 items processed, all 20 got a "found"
    assert summary["processed"] == 20
    assert summary["found"] == 20

    # Assert: the 30 never-searched items were picked first
    searched = db_session.execute(
        "SELECT id FROM wanted_items WHERE last_search_at IS NOT NULL"
    ).fetchall()
    assert len(searched) == 20

    # Assert: opensubtitles budget exhausted → decision blocked after 3 429s
    from services.provider_budget import get_budget_manager
    # ... verify learned_limits or circuit breaker state ...

    # Assert: no item has error = 'Max search attempts reached'
    frozen = db_session.execute(
        "SELECT COUNT(*) FROM wanted_items WHERE error = 'Max search attempts reached'"
    ).scalar()
    assert frozen == 0
```

- [ ] **Step 2: Run → fails (fixtures missing)**

- [ ] **Step 3: Build fixtures until test passes**

(Follow the existing fixture pattern in `tests/conftest.py` — `fake_redis` via `fakeredis`, `mock_providers` via monkeypatching `get_provider_manager`.)

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_phase1_e2e.py
git commit -m "test(scheduler): phase 1 end-to-end cycle coverage"
```

---

## Task 12 — Verify against prod dump

- [ ] **Step 1: Pull a fresh prod DB dump**

```bash
ssh root@192.168.178.36 "docker exec sublarr-postgres pg_dump -U sublarr sublarr --data-only --table=wanted_items" > /tmp/wanted_dump.sql
```

- [ ] **Step 2: Restore to a local test DB**

```bash
createdb sublarr_phase1_test
psql sublarr_phase1_test < /tmp/wanted_dump.sql
# Apply migrations
SUBLARR_DATABASE_URL=postgresql://localhost/sublarr_phase1_test \
  alembic -c backend/db/alembic.ini upgrade head
```

- [ ] **Step 3: Verify frozen items are reset**

```bash
psql sublarr_phase1_test -c \
  "SELECT COUNT(*) FROM wanted_items WHERE error = 'Max search attempts reached';"
```
Expected: `0`.

- [ ] **Step 4: Run the scheduler once against the test DB and verify rotation**

```bash
SUBLARR_DATABASE_URL=postgresql://localhost/sublarr_phase1_test \
  python -c "from services.wanted_search_runner import run_wanted_search; print(run_wanted_search())"

psql sublarr_phase1_test -c \
  "SELECT COUNT(*) FILTER (WHERE last_search_at IS NULL) AS never_searched FROM wanted_items;"
```
Expected: dropped from 3919 to ≤ 3419 (500 items processed per run).

- [ ] **Step 5: Tag the state as ready for Phase 2**

```bash
git tag phase-1-ready
```

---

## Phase 1 exit checklist

Before starting Phase 2:

- [ ] All 12 tasks merged to master
- [ ] CI green (backend + frontend)
- [ ] Prod DB dump replay succeeds without manual intervention
- [ ] Zero items with `error = 'Max search attempts reached'` in prod after deploy
- [ ] `/api/v1/system/budget` returns live data for all 10 enabled providers
- [ ] Settings page shows the preset dropdown and saving works
- [ ] Changelog entry written for V1 release notes
- [ ] Wiki page created for `wanted_search_order` + `scheduler_profile`

---

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Alembic migration fails on prod due to index name collision | Dry-run on prod dump copy (Task 12) |
| Budget gate breaks existing manual-search flow | SearchCoordinator changes gated behind `provider_budget_enabled` config (default ON but easy flip-off) |
| New indexes slow down inserts | Measure query plan on prod-dump replay; drop if >5% insert penalty |
| Redis unavailability crashes search | All budget operations wrapped in try/except; fallback to in-memory |
| Changed default (`fair` order) surprises existing users | First-run wizard in Phase 2 explains + offers revert to `newest_first` |
