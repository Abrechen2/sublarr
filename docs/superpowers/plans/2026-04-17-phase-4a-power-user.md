# Phase 4a — Power-User (Multi-Key Pools + Per-Series Overrides) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-04-17-phase-4a-power-user-design.md`

**Goal:** Add multi-API-key account pools with budget-aware selection and per-series priority + min-per-day overrides, both fully integrated into the Phase 1-3 scheduler without regressions.

**Architecture:** New `provider_account_pools` table seeded one-to-one from existing `config_entries` on alembic upgrade. New `KeySelector` service picks the key with most remaining day-budget per call. `ProviderBudgetManager` gains a per-key counter dimension alongside the existing aggregate. `series_settings` (existing table) gains two nullable-ish columns driving a priority-override in the rank CASE and a min-per-day prefix in `run_wanted_search`. The backlog-reserve gate is taught to preserve min-per-day items.

**Tech Stack:** Python 3.11, SQLAlchemy 2.x + Alembic, pytest, Flask blueprint routes, React + TypeScript + Vitest.

---

## File plan

| Action | Path | Responsibility |
|---|---|---|
| Create | `backend/db/migrations/versions/p4a_pools_and_overrides.py` | Alembic migration: create `provider_account_pools`, add 2 cols to `series_settings`, seed pool from `config_entries` |
| Modify | `backend/db/models/core.py` | Append `ProviderAccountPool` model; add `priority_override` + `min_attempts_per_day` to `SeriesSettings` |
| Create | `backend/db/repositories/provider_account_pool.py` | CRUD + `get_enabled_for` + `mark_429` + `mark_used` |
| Create | `backend/tests/test_provider_account_pool_repo.py` | Repo unit tests |
| Create | `backend/services/key_selector.py` | Budget-aware key picker (60s cache, 429-cooldown filter) |
| Create | `backend/tests/test_key_selector.py` | Selector unit tests |
| Modify | `backend/services/provider_budget.py` | Add `_counts_per_key` dict + `consume(provider, key_id=...)` + `get_usage_per_key(provider)` |
| Modify | `backend/tests/test_provider_budget.py` | Cover per-key consume/get_usage_per_key |
| Modify | `backend/providers/search_coordinator.py` | Call `KeySelector.pick()` before each `provider.search`, pass credentials; call `pool_repo.mark_429` on rate-limit |
| Modify | `backend/tests/test_search_coordinator_budget.py` | Cover multi-key selection + skip-when-all-exhausted |
| Modify | `backend/db/repositories/wanted.py` | Rank CASE uses `COALESCE(priority_override, priority)` when `series_settings` row exists |
| Create | `backend/tests/test_wanted_repo_priority_override.py` | Priority-override rank tests |
| Modify | `backend/services/wanted_search_runner.py` | `_collect_min_attempts_items` prefix before eligible, survives backlog gate |
| Create | `backend/tests/test_wanted_search_runner_min_attempts.py` | Prefix + gate-interaction tests |
| Modify | `backend/routes/system/budget.py` | Include `keys: [...]` per provider in the response |
| Modify | `backend/tests/test_routes_system_budget.py` | Assert per-key breakdown |
| Create | `backend/routes/providers_keys.py` | POST/PATCH/DELETE/GET `/providers/<name>/keys`, plus `/test-connection` |
| Create | `backend/tests/test_routes_providers_keys.py` | Endpoint tests |
| Modify | `backend/routes/library/series.py` (or new file `backend/routes/series_settings.py` if cleaner) | PATCH `/series/<id>/settings` accepting `priority_override` + `min_attempts_per_day` |
| Create | `backend/tests/test_routes_series_settings.py` | PATCH tests |
| Create | `backend/tests/test_phase4a_e2e.py` | E2E: add 2nd key → aggregate 2×; min-per-day guarantees inclusion; priority_override wins |
| Modify | `frontend/src/api/health.ts` | Extend `ProviderBudget` type with `keys` array |
| Modify | `frontend/src/api/providers.ts` *(or `src/api/config.ts` — check at implementation)* | Add `listKeys/addKey/updateKey/deleteKey/testConnection` hooks |
| Modify | `frontend/src/pages/Settings/ProvidersSettings.tsx` *(check real path)* | Render "Keys" section + Add/Edit/Delete buttons |
| Create | `frontend/src/components/settings/KeysList.tsx` | Row-per-key list |
| Create | `frontend/src/components/settings/KeyEditDialog.tsx` | Add/Edit dialog with test-connection |
| Create | `frontend/src/components/dashboard/__tests__/BudgetWidgetPerKey.test.tsx` | Extend existing widget test for the per-key expand |
| Modify | `frontend/src/components/dashboard/BudgetWidget.tsx` | Hover/click expand showing `keys[]` |
| Create | `frontend/src/components/library/SeriesOverrideSettings.tsx` | Priority override select + min-per-day input |
| Modify | `frontend/src/pages/Library/SeriesDetail.tsx` *(check path)* | Mount `SeriesOverrideSettings` |
| Modify | `frontend/src/i18n/locales/de/settings.json` + `en/settings.json` | Keys: `provider_keys.*` (list/add/edit/delete/test); `series_override.*` (priority/min) |
| Modify | `frontend/src/i18n/locales/de/dashboard.json` + `en/dashboard.json` | `budget.per_key_breakdown` label |

Tests live next to their targets or under `backend/tests/` mirroring the package layout to match the repo convention.

---

## Task 1 — Alembic migration + ORM model

**Files:**
- Create: `backend/db/migrations/versions/p4a_pools_and_overrides.py`
- Modify: `backend/db/models/core.py`

Add the new table, the two series_settings columns, and one-shot data backfill from `config_entries`. The migration must be idempotent (re-run produces no changes).

- [ ] **Step 1: Find the current alembic head**

Run: `cd backend && alembic heads`
Record the SHA printed (e.g. `b1u2d3g4e5t6`). This becomes the `down_revision` for the new migration.

- [ ] **Step 2: Create the ORM model**

Append to `backend/db/models/core.py` (after `ProviderLearnedLimit`):

```python
class ProviderAccountPool(db.Model):
    """Multi-API-key pool per provider for budget aggregation (Phase 4a)."""

    __tablename__ = "provider_account_pools"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider_name: Mapped[str] = mapped_column(String(50), nullable=False)
    account_label: Mapped[str] = mapped_column(String(100), nullable=False)
    api_key: Mapped[str] = mapped_column(String(500), nullable=False)
    username: Mapped[str | None] = mapped_column(String(200), nullable=True)
    password: Mapped[str | None] = mapped_column(String(500), nullable=True)
    tier: Mapped[str] = mapped_column(String(20), nullable=False, default="free")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_429_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    __table_args__ = (
        UniqueConstraint("provider_name", "account_label", name="uq_pool_provider_label"),
        Index("ix_pool_provider_enabled", "provider_name", "enabled"),
    )
```

Extend `SeriesSettings` in the same file — add the two columns after `processing_config`:

```python
    priority_override: Mapped[str | None] = mapped_column(String(20), nullable=True)
    min_attempts_per_day: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
```

(`priority_override` is validated at the service layer — no DB CHECK to keep SQLite/Postgres parity simple.)

- [ ] **Step 3: Create the migration file**

Create `backend/db/migrations/versions/p4a_pools_and_overrides.py`:

```python
"""Phase 4a: provider_account_pools + series_settings overrides.

Revision ID: p4a_pools_and_overrides
Revises: <CURRENT_HEAD_FROM_STEP_1>
Create Date: 2026-04-17 00:00:00
"""

from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = "p4a_pools_and_overrides"
down_revision = "<CURRENT_HEAD_FROM_STEP_1>"  # replace with the SHA from Step 1
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    if not insp.has_table("provider_account_pools"):
        op.create_table(
            "provider_account_pools",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("provider_name", sa.String(length=50), nullable=False),
            sa.Column("account_label", sa.String(length=100), nullable=False),
            sa.Column("api_key", sa.String(length=500), nullable=False),
            sa.Column("username", sa.String(length=200), nullable=True),
            sa.Column("password", sa.String(length=500), nullable=True),
            sa.Column("tier", sa.String(length=20), nullable=False, server_default="free"),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_429_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.current_timestamp(),
            ),
            sa.UniqueConstraint("provider_name", "account_label", name="uq_pool_provider_label"),
        )
        op.create_index(
            "ix_pool_provider_enabled",
            "provider_account_pools",
            ["provider_name", "enabled"],
        )

    ss_cols = {c["name"] for c in insp.get_columns("series_settings")}
    if "priority_override" not in ss_cols:
        with op.batch_alter_table("series_settings") as batch:
            batch.add_column(sa.Column("priority_override", sa.String(length=20), nullable=True))
    if "min_attempts_per_day" not in ss_cols:
        with op.batch_alter_table("series_settings") as batch:
            batch.add_column(
                sa.Column(
                    "min_attempts_per_day",
                    sa.Integer(),
                    nullable=False,
                    server_default="0",
                )
            )

    # Data backfill: one pool row per configured provider.
    # Reads config_entries (key/value pairs) and seeds a pool with account_label="primary".
    existing = bind.execute(
        sa.text("SELECT provider_name FROM provider_account_pools")
    ).fetchall()
    if existing:
        return  # idempotent — already seeded

    provider_map = [
        ("opensubtitles", "opensubtitles_api_key", "opensubtitles_username", "opensubtitles_password"),
        ("subdl", "subdl_api_key", None, None),
        ("jimaku", "jimaku_api_key", None, None),
        ("legendasdivx", "legendasdivx_api_key", "legendasdivx_username", "legendasdivx_password"),
        ("turkcealtyazi", "turkcealtyazi_api_key", "turkcealtyazi_username", "turkcealtyazi_password"),
    ]
    now = datetime.now(UTC)
    for provider, key_field, user_field, pass_field in provider_map:
        api_key = _read_config(bind, key_field)
        if not api_key:
            continue
        username = _read_config(bind, user_field) if user_field else None
        password = _read_config(bind, pass_field) if pass_field else None
        tier_field = f"{provider}_detected_tier"
        tier = _read_config(bind, tier_field) or "free"
        bind.execute(
            sa.text(
                "INSERT INTO provider_account_pools "
                "(provider_name, account_label, api_key, username, password, tier, "
                " enabled, created_at) "
                "VALUES (:p, 'primary', :k, :u, :pw, :t, 1, :now)"
            ),
            {"p": provider, "k": api_key, "u": username, "pw": password, "t": tier, "now": now},
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    ss_cols = {c["name"] for c in insp.get_columns("series_settings")}
    with op.batch_alter_table("series_settings") as batch:
        if "min_attempts_per_day" in ss_cols:
            batch.drop_column("min_attempts_per_day")
        if "priority_override" in ss_cols:
            batch.drop_column("priority_override")

    if insp.has_table("provider_account_pools"):
        op.drop_index("ix_pool_provider_enabled", table_name="provider_account_pools")
        op.drop_table("provider_account_pools")


def _read_config(bind, key: str) -> str | None:
    row = bind.execute(
        sa.text("SELECT value FROM config_entries WHERE key = :k"), {"k": key}
    ).fetchone()
    if row is None or not row[0]:
        return None
    return str(row[0])
```

Replace `<CURRENT_HEAD_FROM_STEP_1>` with the SHA from Step 1. Save.

- [ ] **Step 4: Apply + round-trip the migration**

Run:
```bash
cd backend && alembic upgrade head && alembic downgrade -1 && alembic upgrade head
```
Expected: three commands all succeed, no errors. If `alembic downgrade -1` fails on SQLite due to column-drop limitations, keep the upgrade-only form and skip the downgrade verification — note in the commit message.

- [ ] **Step 5: Smoke-test the backfill**

```bash
cd backend && python -c "
from extensions import db
from app import create_app
from db.models.core import ProviderAccountPool, SeriesSettings
a = create_app(testing=False)
with a.app_context():
    rows = db.session.query(ProviderAccountPool).all()
    print(f'Pool rows: {len(rows)}')
    for r in rows:
        print(f'  {r.provider_name}/{r.account_label} tier={r.tier} enabled={r.enabled}')
    cols = [c.name for c in SeriesSettings.__table__.columns]
    print(f'series_settings columns: {cols}')
"
```
Expected: rows for every provider with a configured API key; series_settings lists both new columns.

- [ ] **Step 6: Commit**

```bash
cd "D:/Sublarr_Projekt/Sublarr"
git add backend/db/migrations/versions/p4a_pools_and_overrides.py backend/db/models/core.py
git commit -m "feat(scheduler): phase4a alembic migration + ORM model

New table provider_account_pools (one row per API key); adds
priority_override + min_attempts_per_day columns to series_settings.
Backfills one primary row per configured provider from config_entries."
```

---

## Task 2 — `ProviderAccountPoolRepository`

**Files:**
- Create: `backend/db/repositories/provider_account_pool.py`
- Create: `backend/tests/test_provider_account_pool_repo.py`

- [ ] **Step 1: Failing tests**

Create `backend/tests/test_provider_account_pool_repo.py`:

```python
"""Tests for ProviderAccountPoolRepository (Phase 4a)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from db.models.core import ProviderAccountPool
from db.repositories.provider_account_pool import ProviderAccountPoolRepository
from extensions import db


def _make(
    provider: str = "opensubtitles",
    label: str = "primary",
    api_key: str = "k1",
    tier: str = "free",
    enabled: bool = True,
    last_429_at=None,
) -> ProviderAccountPool:
    row = ProviderAccountPool(
        provider_name=provider,
        account_label=label,
        api_key=api_key,
        tier=tier,
        enabled=enabled,
        last_429_at=last_429_at,
    )
    db.session.add(row)
    db.session.commit()
    return row


class TestRepoCRUD:
    def test_add_and_get(self, app_ctx):
        repo = ProviderAccountPoolRepository()
        row_id = repo.add(provider="opensubtitles", label="primary", api_key="k", tier="vip")
        assert row_id > 0
        got = repo.get(row_id)
        assert got["provider_name"] == "opensubtitles"
        assert got["account_label"] == "primary"
        assert got["tier"] == "vip"
        assert got["enabled"] is True

    def test_duplicate_label_raises(self, app_ctx):
        repo = ProviderAccountPoolRepository()
        repo.add(provider="opensubtitles", label="primary", api_key="k1", tier="free")
        with pytest.raises(Exception):  # sqlalchemy IntegrityError
            repo.add(provider="opensubtitles", label="primary", api_key="k2", tier="free")

    def test_update(self, app_ctx):
        repo = ProviderAccountPoolRepository()
        row_id = repo.add(provider="subdl", label="primary", api_key="k", tier="free")
        repo.update(row_id, tier="pro", enabled=False)
        got = repo.get(row_id)
        assert got["tier"] == "pro"
        assert got["enabled"] is False

    def test_delete(self, app_ctx):
        repo = ProviderAccountPoolRepository()
        row_id = repo.add(provider="subdl", label="primary", api_key="k", tier="free")
        repo.delete(row_id)
        assert repo.get(row_id) is None


class TestRepoGetEnabledFor:
    def test_returns_only_enabled(self, app_ctx):
        _make(provider="os", label="p", enabled=True)
        _make(provider="os", label="b", enabled=False)
        repo = ProviderAccountPoolRepository()
        rows = repo.get_enabled_for("os")
        assert len(rows) == 1
        assert rows[0]["account_label"] == "p"

    def test_empty_for_unknown_provider(self, app_ctx):
        repo = ProviderAccountPoolRepository()
        assert repo.get_enabled_for("ghost") == []


class TestRepoMark429:
    def test_sets_last_429_at(self, app_ctx):
        row = _make(provider="os", label="p")
        repo = ProviderAccountPoolRepository()
        now = datetime(2026, 4, 17, 12, 0, tzinfo=UTC)
        repo.mark_429(row.id, now=now)
        got = repo.get(row.id)
        # SQLite may strip tzinfo; compare as UTC
        got_dt = got["last_429_at"]
        if got_dt.tzinfo is None:
            got_dt = got_dt.replace(tzinfo=UTC)
        assert got_dt == now


class TestRepoMarkUsed:
    def test_sets_last_used_at(self, app_ctx):
        row = _make(provider="os", label="p")
        repo = ProviderAccountPoolRepository()
        now = datetime(2026, 4, 17, 12, 0, tzinfo=UTC)
        repo.mark_used(row.id, now=now)
        got = repo.get(row.id)
        got_dt = got["last_used_at"]
        if got_dt.tzinfo is None:
            got_dt = got_dt.replace(tzinfo=UTC)
        assert got_dt == now
```

- [ ] **Step 2: Run — fails**

`cd backend && python -m pytest tests/test_provider_account_pool_repo.py -v`
Expected: `ModuleNotFoundError: No module named 'db.repositories.provider_account_pool'`.

- [ ] **Step 3: Implement the repo**

Create `backend/db/repositories/provider_account_pool.py`:

```python
"""CRUD + helpers for the provider_account_pools table (Phase 4a)."""
from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import select

from db.models.core import ProviderAccountPool
from db.repositories.base import BaseRepository
from extensions import db

logger = logging.getLogger(__name__)


def _as_utc(value):
    if value is None:
        return None
    if getattr(value, "tzinfo", None) is None:
        return value.replace(tzinfo=UTC)
    return value


class ProviderAccountPoolRepository(BaseRepository):
    """Row-per-API-key CRUD + runtime helpers."""

    def _row_to_dict(self, row: ProviderAccountPool) -> dict:
        return {
            "id": row.id,
            "provider_name": row.provider_name,
            "account_label": row.account_label,
            "api_key": row.api_key,
            "username": row.username,
            "password": row.password,
            "tier": row.tier,
            "enabled": row.enabled,
            "last_used_at": _as_utc(row.last_used_at),
            "last_429_at": _as_utc(row.last_429_at),
            "created_at": _as_utc(row.created_at),
        }

    def add(
        self,
        *,
        provider: str,
        label: str,
        api_key: str,
        tier: str = "free",
        username: str | None = None,
        password: str | None = None,
        enabled: bool = True,
    ) -> int:
        row = ProviderAccountPool(
            provider_name=provider,
            account_label=label,
            api_key=api_key,
            tier=tier,
            username=username,
            password=password,
            enabled=enabled,
        )
        self.session.add(row)
        self.session.commit()
        return row.id

    def get(self, row_id: int) -> dict | None:
        row = self.session.get(ProviderAccountPool, row_id)
        return self._row_to_dict(row) if row else None

    def get_enabled_for(self, provider: str) -> list[dict]:
        rows = (
            self.session.execute(
                select(ProviderAccountPool).where(
                    ProviderAccountPool.provider_name == provider,
                    ProviderAccountPool.enabled.is_(True),
                )
            )
            .scalars()
            .all()
        )
        return [self._row_to_dict(r) for r in rows]

    def get_all_for(self, provider: str) -> list[dict]:
        rows = (
            self.session.execute(
                select(ProviderAccountPool).where(
                    ProviderAccountPool.provider_name == provider
                )
            )
            .scalars()
            .all()
        )
        return [self._row_to_dict(r) for r in rows]

    def update(self, row_id: int, **fields) -> None:
        allowed = {
            "account_label",
            "api_key",
            "username",
            "password",
            "tier",
            "enabled",
        }
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"Unknown fields: {unknown}")
        row = self.session.get(ProviderAccountPool, row_id)
        if row is None:
            return
        for k, v in fields.items():
            setattr(row, k, v)
        self.session.commit()

    def delete(self, row_id: int) -> None:
        row = self.session.get(ProviderAccountPool, row_id)
        if row is None:
            return
        self.session.delete(row)
        self.session.commit()

    def mark_429(self, row_id: int, now: datetime | None = None) -> None:
        if now is None:
            now = datetime.now(UTC)
        row = self.session.get(ProviderAccountPool, row_id)
        if row is None:
            return
        row.last_429_at = now
        self.session.commit()

    def mark_used(self, row_id: int, now: datetime | None = None) -> None:
        if now is None:
            now = datetime.now(UTC)
        row = self.session.get(ProviderAccountPool, row_id)
        if row is None:
            return
        row.last_used_at = now
        self.session.commit()
```

- [ ] **Step 4: Run — all pass**

`cd backend && python -m pytest tests/test_provider_account_pool_repo.py -v`
Expected: all tests green.

- [ ] **Step 5: Ruff**

`cd backend && ruff check db/repositories/provider_account_pool.py tests/test_provider_account_pool_repo.py && ruff format --check db/repositories/provider_account_pool.py tests/test_provider_account_pool_repo.py`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add backend/db/repositories/provider_account_pool.py backend/tests/test_provider_account_pool_repo.py
git commit -m "feat(scheduler): ProviderAccountPoolRepository (CRUD + mark_429/mark_used)"
```

---

## Task 3 — `KeySelector` service

**Files:**
- Create: `backend/services/key_selector.py`
- Create: `backend/tests/test_key_selector.py`

Budget-aware key picker. Caches the enabled pool rows for 60s per provider. Filters rows whose `last_429_at` is within the provider's `retry_after_seconds`. Picks the row with most remaining day-budget.

- [ ] **Step 1: Failing tests**

Create `backend/tests/test_key_selector.py`:

```python
"""Tests for KeySelector (Phase 4a)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from services.key_selector import KeySelector


def _row(
    id_=1, label="primary", tier="free", api_key="k", enabled=True,
    last_429_at=None,
):
    return {
        "id": id_,
        "account_label": label,
        "api_key": api_key,
        "username": None,
        "password": None,
        "tier": tier,
        "enabled": enabled,
        "last_used_at": None,
        "last_429_at": last_429_at,
    }


def test_pick_returns_none_when_pool_empty():
    sel = KeySelector()
    with patch(
        "services.key_selector.ProviderAccountPoolRepository"
    ) as MockRepo:
        MockRepo.return_value.get_enabled_for.return_value = []
        assert sel.pick("opensubtitles", provider_rate_limits={}) is None


def test_pick_prefers_highest_remaining_day_budget():
    sel = KeySelector()
    rows = [
        _row(id_=1, label="free_key", tier="free"),
        _row(id_=2, label="vip_key", tier="vip"),
    ]
    rate_limits = {
        "free": {"day": 200, "hour": 20, "second": 1},
        "vip": {"day": 10000, "hour": 1000, "second": 10},
    }
    # usage_per_key says free_key used 100, vip_key used 500
    usage = {1: {"day": 100}, 2: {"day": 500}}
    with patch(
        "services.key_selector.ProviderAccountPoolRepository"
    ) as MockRepo, patch(
        "services.key_selector.get_budget_manager"
    ) as bm_mock:
        MockRepo.return_value.get_enabled_for.return_value = rows
        bm_mock.return_value.get_usage_per_key.return_value = usage
        picked = sel.pick("opensubtitles", provider_rate_limits=rate_limits)
    # free_key: 200 - 100 = 100; vip_key: 10000 - 500 = 9500. vip wins.
    assert picked["id"] == 2


def test_pick_excludes_row_in_429_cooldown():
    sel = KeySelector()
    now = datetime(2026, 4, 17, 12, 0, tzinfo=UTC)
    hot = _row(id_=1, label="hot", tier="vip", last_429_at=now - timedelta(seconds=30))
    cool = _row(id_=2, label="cool", tier="free")
    rate_limits = {
        "free": {"day": 200}, "vip": {"day": 10000},
    }
    with patch(
        "services.key_selector.ProviderAccountPoolRepository"
    ) as MockRepo, patch(
        "services.key_selector.get_budget_manager"
    ) as bm_mock:
        MockRepo.return_value.get_enabled_for.return_value = [hot, cool]
        bm_mock.return_value.get_usage_per_key.return_value = {}
        picked = sel.pick(
            "opensubtitles",
            provider_rate_limits=rate_limits,
            retry_after_seconds=60,
            now=now,
        )
    # hot is in cooldown; must return cool even though vip has more budget
    assert picked["id"] == 2


def test_pick_returns_none_when_all_cooling_down():
    sel = KeySelector()
    now = datetime(2026, 4, 17, 12, 0, tzinfo=UTC)
    hot1 = _row(id_=1, label="h1", last_429_at=now - timedelta(seconds=30))
    hot2 = _row(id_=2, label="h2", last_429_at=now - timedelta(seconds=30))
    with patch(
        "services.key_selector.ProviderAccountPoolRepository"
    ) as MockRepo, patch(
        "services.key_selector.get_budget_manager"
    ) as bm_mock:
        MockRepo.return_value.get_enabled_for.return_value = [hot1, hot2]
        bm_mock.return_value.get_usage_per_key.return_value = {}
        picked = sel.pick(
            "opensubtitles",
            provider_rate_limits={"free": {"day": 200}},
            retry_after_seconds=60,
            now=now,
        )
    assert picked is None


def test_cache_avoids_repeated_db_reads_within_ttl():
    sel = KeySelector()
    rows = [_row()]
    with patch(
        "services.key_selector.ProviderAccountPoolRepository"
    ) as MockRepo, patch(
        "services.key_selector.get_budget_manager"
    ) as bm_mock:
        MockRepo.return_value.get_enabled_for.return_value = rows
        bm_mock.return_value.get_usage_per_key.return_value = {}
        sel.pick("os", provider_rate_limits={"free": {"day": 200}})
        sel.pick("os", provider_rate_limits={"free": {"day": 200}})
    assert MockRepo.return_value.get_enabled_for.call_count == 1


def test_invalidate_forces_refresh():
    sel = KeySelector()
    rows = [_row()]
    with patch(
        "services.key_selector.ProviderAccountPoolRepository"
    ) as MockRepo, patch(
        "services.key_selector.get_budget_manager"
    ) as bm_mock:
        MockRepo.return_value.get_enabled_for.return_value = rows
        bm_mock.return_value.get_usage_per_key.return_value = {}
        sel.pick("os", provider_rate_limits={"free": {"day": 200}})
        sel.invalidate("os")
        sel.pick("os", provider_rate_limits={"free": {"day": 200}})
    assert MockRepo.return_value.get_enabled_for.call_count == 2
```

- [ ] **Step 2: Run — fails**

`cd backend && python -m pytest tests/test_key_selector.py -v`
Expected: `ModuleNotFoundError: No module named 'services.key_selector'`.

- [ ] **Step 3: Implement**

Create `backend/services/key_selector.py`:

```python
"""Budget-aware API key selector (Phase 4a).

Caches enabled pool rows per provider for 60s. On each ``pick()``:
  1. Filter rows whose ``last_429_at`` falls within ``retry_after_seconds``.
  2. Compute remaining day-budget per row using per-key usage from the
     ProviderBudgetManager + tier-specific rate_limits.
  3. Return the row with the highest remaining day-budget (or None if
     no usable row).
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from threading import Lock

logger = logging.getLogger(__name__)

_CACHE_TTL = timedelta(seconds=60)


class KeySelector:
    def __init__(self) -> None:
        self._cache: dict[str, tuple[list[dict], datetime]] = {}
        self._lock = Lock()

    def invalidate(self, provider: str | None = None) -> None:
        with self._lock:
            if provider is None:
                self._cache.clear()
            else:
                self._cache.pop(provider, None)

    def _load(self, provider: str, now: datetime) -> list[dict]:
        with self._lock:
            cached = self._cache.get(provider)
            if cached is not None and now - cached[1] < _CACHE_TTL:
                return cached[0]
        # Out of lock for the DB read (may be slow).
        from db.repositories.provider_account_pool import ProviderAccountPoolRepository

        rows = ProviderAccountPoolRepository().get_enabled_for(provider)
        with self._lock:
            self._cache[provider] = (rows, now)
        return rows

    def pick(
        self,
        provider: str,
        *,
        provider_rate_limits: dict[str, dict[str, int]],
        retry_after_seconds: int = 60,
        now: datetime | None = None,
    ) -> dict | None:
        if now is None:
            now = datetime.now(UTC)
        rows = self._load(provider, now)
        if not rows:
            return None

        cooldown = timedelta(seconds=retry_after_seconds)
        fresh: list[dict] = []
        for r in rows:
            if r["last_429_at"] is not None and (now - r["last_429_at"]) < cooldown:
                continue
            fresh.append(r)
        if not fresh:
            return None

        from services.provider_budget import get_budget_manager

        usage_per_key = get_budget_manager().get_usage_per_key(provider, now=now)

        def remaining(row: dict) -> int:
            tier_limits = provider_rate_limits.get(row["tier"]) or provider_rate_limits.get("free") or {}
            day_limit = tier_limits.get("day", 0)
            used = usage_per_key.get(row["id"], {}).get("day", 0)
            return day_limit - used

        return max(fresh, key=remaining)


_singleton_lock = Lock()
_singleton: KeySelector | None = None


def get_key_selector() -> KeySelector:
    global _singleton
    if _singleton is None:
        with _singleton_lock:
            if _singleton is None:
                _singleton = KeySelector()
    return _singleton


def reset_key_selector_for_tests() -> None:
    global _singleton
    with _singleton_lock:
        _singleton = None
```

- [ ] **Step 4: Run — all pass**

`cd backend && python -m pytest tests/test_key_selector.py -v`
Expected: 6 passed.

- [ ] **Step 5: Ruff**

`cd backend && ruff check services/key_selector.py tests/test_key_selector.py && ruff format --check services/key_selector.py tests/test_key_selector.py`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add backend/services/key_selector.py backend/tests/test_key_selector.py
git commit -m "feat(scheduler): KeySelector — budget-aware key picker with 60s cache + 429 cooldown"
```

---

## Task 4 — Per-key accounting in `ProviderBudgetManager`

**Files:**
- Modify: `backend/services/provider_budget.py`
- Modify: `backend/tests/test_provider_budget.py`

Add per-key counters alongside the existing per-provider counters. Extend `consume` with an optional `key_id` kwarg; add `get_usage_per_key(provider, now)`.

- [ ] **Step 1: Failing tests — append to `backend/tests/test_provider_budget.py`**

```python
class TestPerKeyAccounting:
    """Phase 4a: per-key counters alongside the aggregate."""

    def test_consume_with_key_id_tracks_both_aggregate_and_per_key(self):
        mgr = ProviderBudgetManager(redis=None, safety_margin_pct=0)
        now = datetime(2026, 4, 17, 12, 0, tzinfo=UTC)
        mgr.consume("opensubtitles", key_id=1, now=now)
        mgr.consume("opensubtitles", key_id=1, now=now)
        mgr.consume("opensubtitles", key_id=2, now=now)
        agg = mgr.get_usage("opensubtitles", now=now)
        per_key = mgr.get_usage_per_key("opensubtitles", now=now)
        assert agg["day"] == 3
        assert per_key[1]["day"] == 2
        assert per_key[2]["day"] == 1

    def test_consume_without_key_id_only_updates_aggregate(self):
        mgr = ProviderBudgetManager(redis=None, safety_margin_pct=0)
        now = datetime(2026, 4, 17, 12, 0, tzinfo=UTC)
        mgr.consume("opensubtitles", now=now)
        agg = mgr.get_usage("opensubtitles", now=now)
        per_key = mgr.get_usage_per_key("opensubtitles", now=now)
        assert agg["day"] == 1
        assert per_key == {}  # no per-key tracking when key_id omitted

    def test_get_usage_per_key_empty_for_unknown_provider(self):
        mgr = ProviderBudgetManager(redis=None, safety_margin_pct=0)
        assert mgr.get_usage_per_key("ghost") == {}
```

- [ ] **Step 2: Run — fails**

`cd backend && python -m pytest tests/test_provider_budget.py::TestPerKeyAccounting -v`
Expected: fails on `get_usage_per_key` / `key_id` kwarg.

- [ ] **Step 3: Implement in `backend/services/provider_budget.py`**

At the top of `ProviderBudgetManager.__init__`, add the per-key counter dict:

```python
        # Per-key counters: (provider, key_id, window_value, window_start) -> count.
        self._in_memory_counts_per_key: dict[tuple[str, int, str, datetime], int] = defaultdict(int)
```

Extend `consume`:

```python
    def consume(
        self,
        provider: str,
        now: datetime | None = None,
        *,
        key_id: int | None = None,
    ) -> None:
        """Record one call against ``provider`` — increments all three windows.

        If ``key_id`` is provided, also increments per-key counters.
        """
        if now is None:
            now = datetime.now(UTC)
        for window in BudgetWindow:
            self._increment(provider, window, now)
            if key_id is not None:
                self._increment_per_key(provider, key_id, window, now)
```

Add the private helper near `_increment`:

```python
    def _increment_per_key(
        self,
        provider: str,
        key_id: int,
        window: BudgetWindow,
        now: datetime,
    ) -> None:
        start = window_start_for(window, now)
        key = (provider, key_id, window.value, start)
        with self._lock:
            self._in_memory_counts_per_key[key] += 1
```

Add the public reader near `get_usage`:

```python
    def get_usage_per_key(
        self,
        provider: str,
        now: datetime | None = None,
    ) -> dict[int, dict[str, int]]:
        """Return ``{key_id: {window: count}}`` for all keys of ``provider``."""
        if now is None:
            now = datetime.now(UTC)
        out: dict[int, dict[str, int]] = {}
        with self._lock:
            for (p, kid, wname, wstart), cnt in self._in_memory_counts_per_key.items():
                if p != provider:
                    continue
                if wstart != window_start_for(BudgetWindow(wname), now):
                    continue  # stale window
                out.setdefault(kid, {})[wname] = cnt
        return out
```

- [ ] **Step 4: Run — all pass**

`cd backend && python -m pytest tests/test_provider_budget.py tests/test_provider_budget_learning.py tests/test_provider_budget_modes.py -v`
Expected: all tests green (existing + 3 new).

- [ ] **Step 5: Ruff**

`cd backend && ruff check services/provider_budget.py tests/test_provider_budget.py && ruff format --check services/provider_budget.py tests/test_provider_budget.py`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add backend/services/provider_budget.py backend/tests/test_provider_budget.py
git commit -m "feat(scheduler): per-key counters + get_usage_per_key in ProviderBudgetManager"
```

---

## Task 5 — Integrate `KeySelector` into `SearchCoordinator`

**Files:**
- Modify: `backend/providers/search_coordinator.py`
- Modify: `backend/tests/test_search_coordinator_budget.py`

Before every `provider.search()`, ask the KeySelector for a key. If None → skip provider. On success → `consume(provider, key_id=...)` and `pool_repo.mark_used`. On `ProviderRateLimitError` → `pool_repo.mark_429` in addition to the existing Phase 3 hook.

- [ ] **Step 1: Failing tests — append to `backend/tests/test_search_coordinator_budget.py`**

```python
class TestKeySelectorIntegration:
    """Phase 4a: SearchCoordinator uses KeySelector + tracks per-key usage."""

    def test_allowed_budget_consumes_with_key_id(
        self, app_ctx, monkeypatch, budget_allows
    ):
        provider = _make_provider("opensubtitles")
        manager = _build_manager(monkeypatch, provider)
        monkeypatch.setattr(
            "providers.search_coordinator.get_budget_manager", lambda: budget_allows
        )
        ks_mock = MagicMock()
        ks_mock.pick.return_value = {"id": 42, "api_key": "k", "username": None, "password": None}
        monkeypatch.setattr(
            "providers.search_coordinator.get_key_selector", lambda: ks_mock
        )

        manager.search(_make_query())

        budget_allows.consume.assert_called_once_with("opensubtitles", key_id=42)

    def test_selector_returns_none_skips_provider(
        self, app_ctx, monkeypatch, budget_allows
    ):
        provider = _make_provider("opensubtitles")
        manager = _build_manager(monkeypatch, provider)
        monkeypatch.setattr(
            "providers.search_coordinator.get_budget_manager", lambda: budget_allows
        )
        ks_mock = MagicMock()
        ks_mock.pick.return_value = None
        monkeypatch.setattr(
            "providers.search_coordinator.get_key_selector", lambda: ks_mock
        )

        manager.search(_make_query())

        provider.search.assert_not_called()
        budget_allows.consume.assert_not_called()
```

- [ ] **Step 2: Run — fails** (coordinator doesn't call `get_key_selector` yet).

- [ ] **Step 3: Implement**

In `backend/providers/search_coordinator.py`:

1. Add a local import inside the relevant handler OR module-level near other service imports:
   ```python
   from services.key_selector import get_key_selector
   ```
2. Inside the inner loop that runs each provider (the block where `provider.search(...)` is called — around the budget gate), replace the existing call path with a KeySelector-aware version. Find the section that reads something like:
   ```python
   # Existing budget gate: if allow -> provider.search; consume
   ```
   Replace with:
   ```python
   # Phase 4a: key selection before the network call
   rate_limits = getattr(type(provider_obj), "rate_limits", {}) or {}
   key = get_key_selector().pick(name, provider_rate_limits=rate_limits)
   if key is None:
       logger.info(
           "%s: no usable key in pool (all exhausted or 429-cooling); skip",
           name,
       )
       continue
   # Inject credentials onto the provider for this call (providers read from self.session / self.api_key)
   provider_obj.api_key = key["api_key"]
   if key.get("username"):
       provider_obj.username = key["username"]
   if key.get("password"):
       provider_obj.password = key["password"]
   # ... existing search call ...
   results = provider_obj.search(query)
   # Existing consume -> extend with key_id
   get_budget_manager().consume(name, key_id=key["id"])
   ```
   (The exact line numbers depend on the current coordinator layout — the implementer finds the corresponding lines.)

3. In the `ProviderRateLimitError` handler (added in Phase 3), add one line after the existing `record_429` call:
   ```python
   try:
       from db.repositories.provider_account_pool import ProviderAccountPoolRepository
       # key_id is available in the local scope because the selector ran earlier
       if key is not None:
           ProviderAccountPoolRepository().mark_429(key["id"])
   except Exception as _pe:
       logger.warning("mark_429 failed for %s key_id=%s: %s", name, key.get("id") if key else None, _pe)
   ```

4. On success path, call `mark_used`:
   ```python
   try:
       ProviderAccountPoolRepository().mark_used(key["id"])
   except Exception as _pe:
       logger.debug("mark_used failed for %s key_id=%s: %s", name, key["id"], _pe)
   ```

- [ ] **Step 4: Run tests**

```bash
cd backend && python -m pytest tests/test_search_coordinator_budget.py tests/test_provider_budget.py tests/test_key_selector.py -v
```
Expected: all green.

- [ ] **Step 5: Ruff**

`cd backend && ruff check providers/search_coordinator.py tests/test_search_coordinator_budget.py && ruff format --check providers/search_coordinator.py tests/test_search_coordinator_budget.py`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add backend/providers/search_coordinator.py backend/tests/test_search_coordinator_budget.py
git commit -m "feat(scheduler): SearchCoordinator routes calls through KeySelector + per-key 429 tracking"
```

---

## Task 6 — Priority override in `get_items_for_scheduled_search`

**Files:**
- Modify: `backend/db/repositories/wanted.py`
- Create: `backend/tests/test_wanted_repo_priority_override.py`

Replace the direct `WantedItem.priority` in `_PRIORITY_RANK` with `COALESCE(series_settings.priority_override, WantedItem.priority)`.

- [ ] **Step 1: Failing tests**

Create `backend/tests/test_wanted_repo_priority_override.py`:

```python
"""Per-series priority_override tests (Phase 4a)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from db.models.core import SeriesSettings, WantedItem
from db.repositories.wanted import WantedRepository
from extensions import db


def _make_item(file_path: str, sonarr_series_id: int | None = None, priority: str = "standard"):
    now = datetime(2026, 4, 17, tzinfo=UTC)
    item = WantedItem(
        item_type="episode",
        file_path=file_path,
        title=file_path,
        season_episode="S01E01",
        status="wanted",
        target_language="de",
        subtitle_type="full",
        priority=priority,
        sonarr_series_id=sonarr_series_id,
        added_at=now,
        updated_at=now,
    )
    db.session.add(item)
    db.session.commit()
    return item


def _make_settings(sonarr_series_id: int, override: str | None, min_per_day: int = 0):
    s = SeriesSettings(
        sonarr_series_id=sonarr_series_id,
        absolute_order=0,
        priority_override=override,
        min_attempts_per_day=min_per_day,
        updated_at=datetime(2026, 4, 17, tzinfo=UTC),
    )
    db.session.add(s)
    db.session.commit()
    return s


def test_priority_override_wins_over_item_priority(app_ctx):
    # Item priority says backlog, override says premium — override wins.
    _make_settings(sonarr_series_id=100, override="premium")
    boss = _make_item("/m/boss.mkv", sonarr_series_id=100, priority="backlog")
    other = _make_item("/m/other.mkv", sonarr_series_id=None, priority="standard")
    repo = WantedRepository()
    rows = repo.get_items_for_scheduled_search(limit=10, order="fair")
    ids = [r["id"] for r in rows]
    assert ids.index(boss.id) < ids.index(other.id)


def test_null_override_does_not_affect_ranking(app_ctx):
    _make_settings(sonarr_series_id=100, override=None)
    a = _make_item("/m/a.mkv", sonarr_series_id=100, priority="backlog")
    b = _make_item("/m/b.mkv", sonarr_series_id=None, priority="premium")
    repo = WantedRepository()
    rows = repo.get_items_for_scheduled_search(limit=10, order="fair")
    # b (premium) wins over a (backlog) — normal order
    assert [r["id"] for r in rows] == [b.id, a.id]


def test_override_on_standalone_series_has_no_effect(app_ctx):
    # sonarr_series_id is None -> no LEFT JOIN match -> override column absent -> fall back
    a = _make_item("/m/a.mkv", sonarr_series_id=None, priority="backlog")
    repo = WantedRepository()
    rows = repo.get_items_for_scheduled_search(limit=10, order="fair")
    assert rows[0]["id"] == a.id  # still returns, unaffected
```

- [ ] **Step 2: Run — fails**

`cd backend && python -m pytest tests/test_wanted_repo_priority_override.py -v`
Expected: priority_override has no effect yet (fails first test).

- [ ] **Step 3: Update `_PRIORITY_RANK` + `get_items_for_scheduled_search`**

In `backend/db/repositories/wanted.py`:

1. Import `SeriesSettings` at the top:
   ```python
   from db.models.core import SeriesSettings, WantedItem
   ```
2. Change `_PRIORITY_RANK` from a module-level constant to a class-method helper (because it now references a LEFT JOIN expression):

   Replace:
   ```python
   _PRIORITY_RANK = case(
       (WantedItem.priority == "premium", 0),
       (WantedItem.priority == "backlog", 2),
       else_=1,
   )
   ```
   With a function:
   ```python
   def _priority_rank_expr():
       """Rank expression: premium=0, backlog=2, standard=1.

       Uses COALESCE(series_settings.priority_override, WantedItem.priority) so
       a per-series override wins over the item's intrinsic priority. Requires
       an outer join on SeriesSettings.
       """
       effective = func.coalesce(SeriesSettings.priority_override, WantedItem.priority)
       return case(
           (effective == "premium", 0),
           (effective == "backlog", 2),
           else_=1,
       )
   ```

3. Inside `get_items_for_scheduled_search`, add the LEFT JOIN when `priority_weighting` is True:
   ```python
   stmt = select(WantedItem).where(WantedItem.status == "wanted")
   if priority_weighting:
       stmt = stmt.outerjoin(
           SeriesSettings, SeriesSettings.sonarr_series_id == WantedItem.sonarr_series_id
       )
   order_clauses: list = []
   if priority_weighting:
       order_clauses.append(_priority_rank_expr().asc())
   ```

4. Remove the old `_PRIORITY_RANK` constant and its usage lower in the function.

- [ ] **Step 4: Run — all pass**

```bash
cd backend && python -m pytest tests/test_wanted_repo_priority_override.py tests/test_wanted_repo_priority_weighting.py tests/test_wanted_repo_scheduled_search.py -v
```
Expected: all green.

- [ ] **Step 5: Ruff**

`cd backend && ruff check db/repositories/wanted.py tests/test_wanted_repo_priority_override.py && ruff format --check db/repositories/wanted.py tests/test_wanted_repo_priority_override.py`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add backend/db/repositories/wanted.py backend/tests/test_wanted_repo_priority_override.py
git commit -m "feat(wanted): priority_override from series_settings wins over item.priority"
```

---

## Task 7 — `min_attempts_per_day` prefix in `run_wanted_search`

**Files:**
- Modify: `backend/services/wanted_search_runner.py`
- Create: `backend/tests/test_wanted_search_runner_min_attempts.py`

Before the regular eligible list is built, collect "must-include" items from series whose `min_attempts_per_day` quota for today isn't met yet. Prefix these to `eligible` so they survive the backlog-reserve gate.

- [ ] **Step 1: Failing tests**

Create `backend/tests/test_wanted_search_runner_min_attempts.py`:

```python
"""Tests for min_attempts_per_day prefix (Phase 4a)."""
from __future__ import annotations

from unittest.mock import patch

from services.wanted_search_runner import _collect_min_attempts_items


def test_prefix_returns_oldest_searched_per_series():
    candidates = {
        100: [  # series_id -> items (must be oldest-searched first)
            {"id": 1, "sonarr_series_id": 100, "last_search_at": None},
            {"id": 2, "sonarr_series_id": 100, "last_search_at": "2026-04-17T10:00:00+00:00"},
            {"id": 3, "sonarr_series_id": 100, "last_search_at": "2026-04-17T11:00:00+00:00"},
        ]
    }
    with patch(
        "services.wanted_search_runner._series_min_attempts_config",
        return_value={100: 2},
    ), patch(
        "services.wanted_search_runner._series_searches_today",
        return_value={100: 0},
    ), patch(
        "services.wanted_search_runner._wanted_items_by_series",
        return_value=candidates,
    ):
        out = _collect_min_attempts_items()
    assert [i["id"] for i in out] == [1, 2]


def test_prefix_clamped_when_fewer_items_than_min():
    candidates = {100: [{"id": 1, "sonarr_series_id": 100, "last_search_at": None}]}
    with patch(
        "services.wanted_search_runner._series_min_attempts_config",
        return_value={100: 5},
    ), patch(
        "services.wanted_search_runner._series_searches_today",
        return_value={100: 0},
    ), patch(
        "services.wanted_search_runner._wanted_items_by_series",
        return_value=candidates,
    ):
        out = _collect_min_attempts_items()
    assert len(out) == 1


def test_prefix_subtracts_already_searched_today():
    candidates = {100: [
        {"id": 1, "sonarr_series_id": 100, "last_search_at": None},
        {"id": 2, "sonarr_series_id": 100, "last_search_at": None},
    ]}
    with patch(
        "services.wanted_search_runner._series_min_attempts_config",
        return_value={100: 3},
    ), patch(
        "services.wanted_search_runner._series_searches_today",
        return_value={100: 2},
    ), patch(
        "services.wanted_search_runner._wanted_items_by_series",
        return_value=candidates,
    ):
        out = _collect_min_attempts_items()
    # 3 wanted - 2 already searched today = 1 slot remaining
    assert len(out) == 1


def test_empty_when_no_series_have_min_configured():
    with patch(
        "services.wanted_search_runner._series_min_attempts_config",
        return_value={},
    ):
        assert _collect_min_attempts_items() == []
```

- [ ] **Step 2: Run — fails** (functions don't exist).

- [ ] **Step 3: Implement**

In `backend/services/wanted_search_runner.py`:

1. Add the three helpers at module level (near other private helpers):

```python
def _series_min_attempts_config() -> dict[int, int]:
    """Return ``{sonarr_series_id: min_attempts_per_day}`` for series with min > 0."""
    from sqlalchemy import select as _select

    from db.models.core import SeriesSettings
    from extensions import db as _db

    try:
        rows = _db.session.execute(
            _select(
                SeriesSettings.sonarr_series_id,
                SeriesSettings.min_attempts_per_day,
            ).where(SeriesSettings.min_attempts_per_day > 0)
        ).all()
    except Exception as exc:  # noqa: BLE001
        logger.warning("series_min_attempts_config fetch failed: %s", exc)
        return {}
    return {sid: count for sid, count in rows}


def _series_searches_today(series_ids: list[int]) -> dict[int, int]:
    """Count wanted_item searches performed today per series.

    Defined as rows with ``last_search_at`` within the current UTC day.
    """
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import func as _func, select as _select

    from db.models.core import WantedItem
    from extensions import db as _db

    if not series_ids:
        return {}
    day_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    try:
        rows = _db.session.execute(
            _select(
                WantedItem.sonarr_series_id,
                _func.count(WantedItem.id),
            )
            .where(
                WantedItem.sonarr_series_id.in_(series_ids),
                WantedItem.last_search_at >= day_start,
            )
            .group_by(WantedItem.sonarr_series_id)
        ).all()
    except Exception as exc:  # noqa: BLE001
        logger.warning("series_searches_today fetch failed: %s", exc)
        return {}
    return {sid: count for sid, count in rows}


def _wanted_items_by_series(series_ids: list[int]) -> dict[int, list[dict]]:
    """Return ``{series_id: [wanted_item_dict, ...]}`` ordered by oldest-searched first."""
    from db.repositories.wanted import WantedRepository

    if not series_ids:
        return {}
    repo = WantedRepository()
    out: dict[int, list[dict]] = {}
    for sid in series_ids:
        items = repo.get_wanted_by_series(sid)  # MAY NOT EXIST — see Step 3b
        items.sort(
            key=lambda it: (
                it.get("last_search_at") or "",  # NULLs first
                it.get("search_count", 0),
            )
        )
        out[sid] = items
    return out


def _collect_min_attempts_items() -> list[dict]:
    """Return the list of wanted items that must be included this tick to honor
    ``series_settings.min_attempts_per_day``. Items are prefixed to the eligible
    list by the caller, so they survive the backlog-reserve gate."""
    config = _series_min_attempts_config()
    if not config:
        return []
    series_ids = list(config.keys())
    already = _series_searches_today(series_ids)
    by_series = _wanted_items_by_series(series_ids)
    out: list[dict] = []
    for sid, min_n in config.items():
        remaining = max(0, min_n - already.get(sid, 0))
        if remaining <= 0:
            continue
        items = by_series.get(sid, [])
        out.extend(items[:remaining])
    return out
```

- [ ] **Step 3b: Ensure `get_wanted_by_series` exists on `WantedRepository`**

Add to `backend/db/repositories/wanted.py` if not present:

```python
    def get_wanted_by_series(self, sonarr_series_id: int) -> list[dict]:
        """Return all wanted-status items for a Sonarr series id, unordered."""
        rows = (
            self.session.execute(
                select(WantedItem).where(
                    WantedItem.status == "wanted",
                    WantedItem.sonarr_series_id == sonarr_series_id,
                )
            )
            .scalars()
            .all()
        )
        return [self._row_to_wanted(r) for r in rows]
```

(If the method already exists under a different name, reuse it instead.)

- [ ] **Step 4: Wire the prefix into `run_wanted_search`**

Inside `run_wanted_search()`, after the existing `eligible = _filter_eligible(items, settings)` line and BEFORE the backlog-reserve gate:

```python
# Phase 4a: min-per-day prefix — must-include items that survive the backlog gate.
try:
    min_prefix = _collect_min_attempts_items()
except Exception as exc:  # noqa: BLE001
    logger.warning("min_attempts prefix failed (non-blocking): %s", exc)
    min_prefix = []
if min_prefix:
    # Dedup by id while preserving order (prefix first, then original eligible).
    seen = {i["id"] for i in min_prefix}
    eligible = min_prefix + [i for i in eligible if i["id"] not in seen]
```

The backlog-reserve gate already runs next. The critical behaviour — prefix items survive — comes from the dedup keeping prefix items at positions 0..N-1 where the gate filters on `priority`, and prefix items retain their original `priority` which may still be backlog. To make min-per-day truly a hard floor, modify the backlog-reserve gate call to skip items whose id is in `seen`:

In `_apply_backlog_reserve_gate`, add an optional `exempt_ids: set[int] | None = None` param (default None) and skip backlog filtering for exempt ids. Update the call site:

```python
exempt = {i["id"] for i in min_prefix}
eligible = _apply_backlog_reserve_gate(eligible, budget_states, reserve_pct, exempt_ids=exempt)
```

Implementation delta in `_apply_backlog_reserve_gate`:

```python
    return [
        i
        for i in items
        if (exempt_ids and i.get("id") in exempt_ids)
        or (i.get("priority") or "standard") != "backlog"
    ]
```

- [ ] **Step 5: Run tests**

```bash
cd backend && python -m pytest tests/test_wanted_search_runner_min_attempts.py tests/test_wanted_search_runner_backlog_gate.py -v
```
Expected: all green.

Add one regression test to `test_wanted_search_runner_backlog_gate.py`:

```python
def test_min_prefix_items_survive_backlog_gate():
    items = [
        {"id": 10, "priority": "backlog"},  # normally dropped
        {"id": 20, "priority": "premium"},
    ]
    budget_states = [{"usage": {"day": 600}, "limits": {"day": 1000}}]  # above 50%
    result = _apply_backlog_reserve_gate(
        items, budget_states, reserve_pct=50, exempt_ids={10}
    )
    assert [i["id"] for i in result] == [10, 20]
```

- [ ] **Step 6: Ruff + commit**

```bash
cd backend && ruff check services/wanted_search_runner.py db/repositories/wanted.py tests/test_wanted_search_runner_min_attempts.py tests/test_wanted_search_runner_backlog_gate.py && ruff format --check services/wanted_search_runner.py db/repositories/wanted.py tests/test_wanted_search_runner_min_attempts.py tests/test_wanted_search_runner_backlog_gate.py
```
```bash
git add backend/services/wanted_search_runner.py backend/db/repositories/wanted.py backend/tests/test_wanted_search_runner_min_attempts.py backend/tests/test_wanted_search_runner_backlog_gate.py
git commit -m "feat(wanted): min_attempts_per_day prefix that survives backlog reserve gate"
```

---

## Task 8 — `/api/v1/system/budget` per-key breakdown

**Files:**
- Modify: `backend/routes/system/budget.py`
- Modify: `backend/tests/test_routes_system_budget.py`

Extend the response with a `keys` array per provider + aggregate `limits` across keys.

- [ ] **Step 1: Failing test**

Append to `backend/tests/test_routes_system_budget.py`:

```python
def test_budget_endpoint_returns_keys_breakdown(client, app_ctx):
    """After adding 2 pool rows, /system/budget reports aggregate + per-key."""
    from db.repositories.provider_account_pool import ProviderAccountPoolRepository

    repo = ProviderAccountPoolRepository()
    k1 = repo.add(provider="opensubtitles", label="primary", api_key="a", tier="free")
    k2 = repo.add(provider="opensubtitles", label="backup", api_key="b", tier="vip")

    p = _fake_provider("opensubtitles")
    mgr = MagicMock()
    mgr._providers = {"opensubtitles": p}

    with patch("routes.system.budget.get_provider_manager", return_value=mgr):
        resp = client.get("/api/v1/system/budget")

    body = resp.get_json()
    os_row = next(r for r in body["providers"] if r["name"] == "opensubtitles")
    assert os_row["tier"] == "vip"  # highest tier wins
    # free=1000 + vip=10000 aggregated
    assert os_row["limits"]["day"] == 11000
    assert len(os_row["keys"]) == 2
    labels = {k["label"] for k in os_row["keys"]}
    assert labels == {"primary", "backup"}
```

- [ ] **Step 2: Run — fails**.

- [ ] **Step 3: Update `get_budget_state`**

In `backend/routes/system/budget.py`:

```python
from db.repositories.provider_account_pool import ProviderAccountPoolRepository

_TIER_RANK = {"vip+": 2, "vip": 1, "free": 0}


def _aggregate_tier(keys: list[dict]) -> str:
    if not keys:
        return "free"
    return max(keys, key=lambda k: _TIER_RANK.get(k["tier"], 0))["tier"]


def _aggregate_limits(keys: list[dict], rate_limits: dict) -> dict:
    out = {"second": 0, "hour": 0, "day": 0}
    for k in keys:
        tier_limits = rate_limits.get(k["tier"]) or rate_limits.get("free") or {}
        for w in ("second", "hour", "day"):
            out[w] += tier_limits.get(w, 0)
    return out
```

Update the per-provider block inside `get_budget_state`:

```python
for name in sorted(mgr._providers.keys()):
    provider = mgr._providers[name]
    rate_limits = getattr(type(provider), "rate_limits", None) or {}
    pool_rows = ProviderAccountPoolRepository().get_enabled_for(name)
    per_key = budget.get_usage_per_key(name)
    if pool_rows:
        tier = _aggregate_tier(pool_rows)
        limits = _aggregate_limits(pool_rows, rate_limits)
    else:
        # Legacy fallback when pool is empty
        tier = getattr(provider, "tier", "free")
        limits = rate_limits.get(tier) or rate_limits.get("free") or {}
    keys_out = [
        {
            "id": r["id"],
            "label": r["account_label"],
            "tier": r["tier"],
            "used": per_key.get(r["id"], {"second": 0, "hour": 0, "day": 0}),
            "limit": rate_limits.get(r["tier"]) or rate_limits.get("free") or {},
            "last_429_at": r["last_429_at"].isoformat() if r["last_429_at"] else None,
            "last_used_at": r["last_used_at"].isoformat() if r["last_used_at"] else None,
        }
        for r in pool_rows
    ]
    usage = budget.get_usage(name)
    reset_seconds = {
        window: budget.seconds_until_next_window(window) for window in ("second", "hour", "day")
    }
    providers_out.append(
        {
            "name": name,
            "tier": tier,
            "limits": limits,
            "usage": usage,
            "reset_seconds": reset_seconds,
            "learning": learned_by_provider.get(name),
            "keys": keys_out,
        }
    )
```

- [ ] **Step 4: Run tests**

`cd backend && python -m pytest tests/test_routes_system_budget.py -v`
Expected: all green (existing + new).

- [ ] **Step 5: Ruff + commit**

```bash
cd backend && ruff check routes/system/budget.py tests/test_routes_system_budget.py && ruff format --check routes/system/budget.py tests/test_routes_system_budget.py
git add backend/routes/system/budget.py backend/tests/test_routes_system_budget.py
git commit -m "feat(api): /system/budget exposes per-key breakdown + aggregate limits"
```

---

## Task 9 — `/api/v1/providers/<name>/keys` CRUD + test-connection

**Files:**
- Create: `backend/routes/providers_keys.py`
- Create: `backend/tests/test_routes_providers_keys.py`

- [ ] **Step 1: Failing tests**

Create `backend/tests/test_routes_providers_keys.py`:

```python
"""Tests for /api/v1/providers/<name>/keys (Phase 4a)."""
from __future__ import annotations

from unittest.mock import patch


def test_list_keys_empty(client, app_ctx):
    resp = client.get("/api/v1/providers/opensubtitles/keys")
    assert resp.status_code == 200
    assert resp.get_json() == {"keys": []}


def test_add_key_and_list(client, app_ctx):
    payload = {"label": "primary", "api_key": "k", "tier": "vip"}
    resp = client.post("/api/v1/providers/opensubtitles/keys", json=payload)
    assert resp.status_code == 201
    created = resp.get_json()
    assert created["label"] == "primary"
    assert created["tier"] == "vip"
    assert "id" in created

    resp = client.get("/api/v1/providers/opensubtitles/keys")
    assert len(resp.get_json()["keys"]) == 1


def test_add_duplicate_label_conflict(client, app_ctx):
    client.post(
        "/api/v1/providers/opensubtitles/keys",
        json={"label": "primary", "api_key": "k", "tier": "free"},
    )
    resp = client.post(
        "/api/v1/providers/opensubtitles/keys",
        json={"label": "primary", "api_key": "k2", "tier": "free"},
    )
    assert resp.status_code == 409


def test_patch_key_updates_fields(client, app_ctx):
    r = client.post(
        "/api/v1/providers/opensubtitles/keys",
        json={"label": "primary", "api_key": "k", "tier": "free"},
    )
    kid = r.get_json()["id"]
    resp = client.patch(
        f"/api/v1/providers/opensubtitles/keys/{kid}",
        json={"tier": "vip", "enabled": False},
    )
    assert resp.status_code == 200
    assert resp.get_json()["tier"] == "vip"
    assert resp.get_json()["enabled"] is False


def test_delete_key(client, app_ctx):
    r = client.post(
        "/api/v1/providers/opensubtitles/keys",
        json={"label": "primary", "api_key": "k", "tier": "free"},
    )
    kid = r.get_json()["id"]
    resp = client.delete(f"/api/v1/providers/opensubtitles/keys/{kid}")
    assert resp.status_code == 204
    # Confirm gone
    resp = client.get("/api/v1/providers/opensubtitles/keys")
    assert resp.get_json()["keys"] == []


def test_test_connection_endpoint(client, app_ctx):
    with patch(
        "routes.providers_keys._probe_provider",
        return_value={"ok": True, "message": "Test OK"},
    ):
        resp = client.post(
            "/api/v1/providers/opensubtitles/keys/test-connection",
            json={"api_key": "k"},
        )
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True
```

- [ ] **Step 2: Run — fails**.

- [ ] **Step 3: Implement**

Create `backend/routes/providers_keys.py`:

```python
"""Pool key management — POST/PATCH/DELETE/GET /api/v1/providers/<name>/keys."""
from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request
from sqlalchemy.exc import IntegrityError

from db.repositories.provider_account_pool import ProviderAccountPoolRepository
from extensions import db

logger = logging.getLogger(__name__)

bp = Blueprint("providers_keys", __name__, url_prefix="/api/v1/providers")


def _serialize(row: dict) -> dict:
    return {
        "id": row["id"],
        "label": row["account_label"],
        "tier": row["tier"],
        "enabled": row["enabled"],
        "last_used_at": row["last_used_at"].isoformat() if row["last_used_at"] else None,
        "last_429_at": row["last_429_at"].isoformat() if row["last_429_at"] else None,
    }


@bp.route("/<name>/keys", methods=["GET"])
def list_keys(name: str):
    repo = ProviderAccountPoolRepository()
    return jsonify({"keys": [_serialize(r) for r in repo.get_all_for(name)]})


@bp.route("/<name>/keys", methods=["POST"])
def add_key(name: str):
    data = request.get_json(silent=True) or {}
    label = data.get("label")
    api_key = data.get("api_key")
    if not label or not api_key:
        return jsonify({"error": "label and api_key are required"}), 400
    repo = ProviderAccountPoolRepository()
    try:
        row_id = repo.add(
            provider=name,
            label=label,
            api_key=api_key,
            tier=data.get("tier", "free"),
            username=data.get("username"),
            password=data.get("password"),
            enabled=bool(data.get("enabled", True)),
        )
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "label already exists for this provider"}), 409
    # Invalidate KeySelector cache so the new key is picked up immediately.
    try:
        from services.key_selector import get_key_selector
        get_key_selector().invalidate(name)
    except Exception as _exc:  # noqa: BLE001
        logger.debug("KeySelector.invalidate failed: %s", _exc)
    return jsonify(_serialize(repo.get(row_id))), 201


@bp.route("/<name>/keys/<int:row_id>", methods=["PATCH"])
def update_key(name: str, row_id: int):
    repo = ProviderAccountPoolRepository()
    data = request.get_json(silent=True) or {}
    allowed = {"api_key", "tier", "enabled", "username", "password", "account_label"}
    fields = {k: v for k, v in data.items() if k in allowed}
    # Map incoming "label" -> DB "account_label"
    if "label" in data:
        fields["account_label"] = data["label"]
    try:
        repo.update(row_id, **fields)
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    updated = repo.get(row_id)
    if updated is None:
        return jsonify({"error": "not found"}), 404
    try:
        from services.key_selector import get_key_selector
        get_key_selector().invalidate(name)
    except Exception as _exc:  # noqa: BLE001
        logger.debug("KeySelector.invalidate failed: %s", _exc)
    return jsonify(_serialize(updated)), 200


@bp.route("/<name>/keys/<int:row_id>", methods=["DELETE"])
def delete_key(name: str, row_id: int):
    repo = ProviderAccountPoolRepository()
    repo.delete(row_id)
    try:
        from services.key_selector import get_key_selector
        get_key_selector().invalidate(name)
    except Exception as _exc:  # noqa: BLE001
        logger.debug("KeySelector.invalidate failed: %s", _exc)
    return ("", 204)


@bp.route("/<name>/keys/test-connection", methods=["POST"])
def test_connection(name: str):
    data = request.get_json(silent=True) or {}
    result = _probe_provider(
        name,
        api_key=data.get("api_key", ""),
        username=data.get("username"),
        password=data.get("password"),
    )
    return jsonify(result), (200 if result["ok"] else 400)


def _probe_provider(
    name: str,
    *,
    api_key: str,
    username: str | None = None,
    password: str | None = None,
) -> dict:
    """Provider-specific cheap probe. Returns {ok: bool, message: str}.

    Isolated so tests can patch. Kept small — extend per-provider as needed.
    """
    try:
        if name == "opensubtitles":
            import requests
            r = requests.get(
                "https://api.opensubtitles.com/api/v1/infos/formats",
                headers={"Api-Key": api_key, "User-Agent": "Sublarr/0.52.0-beta"},
                timeout=10,
            )
            return {"ok": r.status_code == 200, "message": f"HTTP {r.status_code}"}
        if name == "subdl":
            import requests
            r = requests.get(
                f"https://api.subdl.com/api/v1/subtitles?api_key={api_key}&type=movie&tmdb_id=1",
                timeout=10,
            )
            # Any 2xx / 4xx not-401 means the key was accepted.
            return {"ok": r.status_code != 401, "message": f"HTTP {r.status_code}"}
        return {"ok": True, "message": "No probe configured — saved as-is"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "message": f"Probe failed: {exc}"}
```

- [ ] **Step 3b: Register the blueprint**

In `backend/app.py`'s `create_app()` (where other blueprints are registered):

```python
from routes.providers_keys import bp as providers_keys_bp
app.register_blueprint(providers_keys_bp)
```

- [ ] **Step 4: Run tests**

`cd backend && python -m pytest tests/test_routes_providers_keys.py -v`
Expected: all green.

- [ ] **Step 5: Ruff + commit**

```bash
cd backend && ruff check routes/providers_keys.py tests/test_routes_providers_keys.py app.py && ruff format --check routes/providers_keys.py tests/test_routes_providers_keys.py app.py
git add backend/routes/providers_keys.py backend/tests/test_routes_providers_keys.py backend/app.py
git commit -m "feat(api): /providers/<name>/keys CRUD + test-connection probe"
```

---

## Task 10 — `/api/v1/series/<id>/settings` PATCH for overrides

**Files:**
- Create: `backend/routes/series_settings_overrides.py` (isolates the new route from any existing series files to keep the diff small)
- Create: `backend/tests/test_routes_series_overrides.py`

- [ ] **Step 1: Failing tests**

```python
"""Tests for PATCH /api/v1/series/<id>/settings (Phase 4a)."""
from __future__ import annotations


def test_patch_creates_settings_row_if_missing(client, app_ctx):
    resp = client.patch(
        "/api/v1/series/101/settings",
        json={"priority_override": "premium", "min_attempts_per_day": 3},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["priority_override"] == "premium"
    assert body["min_attempts_per_day"] == 3


def test_patch_invalid_priority_rejected(client, app_ctx):
    resp = client.patch(
        "/api/v1/series/101/settings",
        json={"priority_override": "bogus"},
    )
    assert resp.status_code == 400


def test_patch_clear_override_with_null(client, app_ctx):
    client.patch(
        "/api/v1/series/101/settings",
        json={"priority_override": "premium"},
    )
    resp = client.patch(
        "/api/v1/series/101/settings",
        json={"priority_override": None},
    )
    assert resp.status_code == 200
    assert resp.get_json()["priority_override"] is None


def test_patch_min_attempts_clamped_to_nonneg(client, app_ctx):
    resp = client.patch(
        "/api/v1/series/101/settings",
        json={"min_attempts_per_day": -5},
    )
    assert resp.status_code == 400
```

- [ ] **Step 2: Run — fails**.

- [ ] **Step 3: Implement**

Create `backend/routes/series_settings_overrides.py`:

```python
"""PATCH /api/v1/series/<id>/settings — priority_override + min_attempts_per_day."""
from __future__ import annotations

from datetime import UTC, datetime

from flask import Blueprint, jsonify, request

from db.models.core import SeriesSettings
from extensions import db

bp = Blueprint("series_settings_overrides", __name__, url_prefix="/api/v1/series")

_ALLOWED_PRIORITY = {"premium", "standard", "backlog"}


@bp.route("/<int:series_id>/settings", methods=["PATCH"])
def patch_series_settings(series_id: int):
    data = request.get_json(silent=True) or {}
    # Validate
    if "priority_override" in data:
        pv = data["priority_override"]
        if pv is not None and pv not in _ALLOWED_PRIORITY:
            return jsonify({"error": f"priority_override must be one of {sorted(_ALLOWED_PRIORITY)} or null"}), 400
    if "min_attempts_per_day" in data:
        try:
            mv = int(data["min_attempts_per_day"])
        except (TypeError, ValueError):
            return jsonify({"error": "min_attempts_per_day must be an integer"}), 400
        if mv < 0 or mv > 50:
            return jsonify({"error": "min_attempts_per_day must be in [0, 50]"}), 400

    now = datetime.now(UTC)
    row = db.session.get(SeriesSettings, series_id)
    if row is None:
        row = SeriesSettings(
            sonarr_series_id=series_id,
            absolute_order=0,
            min_attempts_per_day=0,
            updated_at=now,
        )
        db.session.add(row)
    if "priority_override" in data:
        row.priority_override = data["priority_override"]
    if "min_attempts_per_day" in data:
        row.min_attempts_per_day = int(data["min_attempts_per_day"])
    row.updated_at = now
    db.session.commit()

    return jsonify(
        {
            "sonarr_series_id": row.sonarr_series_id,
            "priority_override": row.priority_override,
            "min_attempts_per_day": row.min_attempts_per_day,
        }
    ), 200
```

Register in `app.py`:

```python
from routes.series_settings_overrides import bp as series_settings_bp
app.register_blueprint(series_settings_bp)
```

- [ ] **Step 4: Run tests + commit**

```bash
cd backend && python -m pytest tests/test_routes_series_overrides.py -v
cd backend && ruff check routes/series_settings_overrides.py tests/test_routes_series_overrides.py app.py && ruff format --check routes/series_settings_overrides.py tests/test_routes_series_overrides.py app.py
git add backend/routes/series_settings_overrides.py backend/tests/test_routes_series_overrides.py backend/app.py
git commit -m "feat(api): PATCH /series/<id>/settings for priority_override + min_attempts_per_day"
```

---

## Task 11 — Frontend: types + provider keys page

**Files:**
- Modify: `frontend/src/api/health.ts`
- Create: `frontend/src/api/providerKeys.ts`
- Create: `frontend/src/components/settings/KeysList.tsx`
- Create: `frontend/src/components/settings/KeyEditDialog.tsx`
- Create: `frontend/src/components/settings/__tests__/KeysList.test.tsx`
- Create: `frontend/src/components/settings/__tests__/KeyEditDialog.test.tsx`
- Modify: the existing provider settings page (locate via `grep "Providers" frontend/src/pages/Settings/ -l`)
- Modify: `frontend/src/i18n/locales/{de,en}/settings.json`

- [ ] **Step 1: Extend `ProviderBudget` type**

In `frontend/src/api/health.ts`, add the `keys` optional array:

```ts
export interface ProviderBudgetKey {
  id: number
  label: string
  tier: string
  used: { second: number; hour: number; day: number }
  limit: { second: number; hour: number; day: number }
  last_429_at: string | null
  last_used_at: string | null
}

export interface ProviderBudget {
  name: string
  tier: string
  limits: BudgetWindow
  usage: BudgetWindow
  reset_seconds: BudgetWindow
  learning?: ProviderBudgetLearning | null
  keys?: ProviderBudgetKey[]
}
```

- [ ] **Step 2: Create the API client**

Create `frontend/src/api/providerKeys.ts`:

```ts
import { api } from './client'

export interface ProviderKey {
  id: number
  label: string
  tier: string
  enabled: boolean
  last_used_at: string | null
  last_429_at: string | null
}

export async function listKeys(provider: string): Promise<ProviderKey[]> {
  const { data } = await api.get(`/providers/${encodeURIComponent(provider)}/keys`)
  return data.keys
}

export async function addKey(
  provider: string,
  payload: { label: string; api_key: string; tier: string; username?: string; password?: string }
): Promise<ProviderKey> {
  const { data } = await api.post(`/providers/${encodeURIComponent(provider)}/keys`, payload)
  return data
}

export async function updateKey(
  provider: string,
  id: number,
  payload: Partial<{ label: string; api_key: string; tier: string; enabled: boolean; username: string; password: string }>
): Promise<ProviderKey> {
  const { data } = await api.patch(
    `/providers/${encodeURIComponent(provider)}/keys/${id}`,
    payload
  )
  return data
}

export async function deleteKey(provider: string, id: number): Promise<void> {
  await api.delete(`/providers/${encodeURIComponent(provider)}/keys/${id}`)
}

export async function testConnection(
  provider: string,
  payload: { api_key: string; username?: string; password?: string }
): Promise<{ ok: boolean; message: string }> {
  const { data } = await api.post(
    `/providers/${encodeURIComponent(provider)}/keys/test-connection`,
    payload
  )
  return data
}
```

- [ ] **Step 3: Failing Vitest for KeysList**

Create `frontend/src/components/settings/__tests__/KeysList.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'
import KeysList, { type KeysListProps } from '../KeysList'

const makeProps = (overrides: Partial<KeysListProps> = {}): KeysListProps => ({
  provider: 'opensubtitles',
  keys: [
    { id: 1, label: 'primary', tier: 'vip', enabled: true, last_used_at: null, last_429_at: null },
    { id: 2, label: 'backup', tier: 'free', enabled: false, last_used_at: null, last_429_at: null },
  ],
  onAdd: vi.fn(),
  onEdit: vi.fn(),
  onDelete: vi.fn(),
  ...overrides,
})

describe('KeysList', () => {
  test('renders a row per key with label + tier', () => {
    render(<KeysList {...makeProps()} />)
    expect(screen.getByTestId('key-row-1')).toHaveTextContent('primary')
    expect(screen.getByTestId('key-row-1')).toHaveTextContent('vip')
    expect(screen.getByTestId('key-row-2')).toHaveTextContent('backup')
  })

  test('delete-last triggers confirmation label on button aria', () => {
    render(
      <KeysList
        {...makeProps({ keys: [makeProps().keys[0]] })}
      />,
    )
    const del = screen.getByTestId('delete-key-1')
    expect(del.getAttribute('aria-label')).toContain('last')
  })
})
```

- [ ] **Step 4: Create KeysList component**

Create `frontend/src/components/settings/KeysList.tsx`:

```tsx
import { useTranslation } from 'react-i18next'
import type { ProviderKey } from '@/api/providerKeys'

export interface KeysListProps {
  provider: string
  keys: ProviderKey[]
  onAdd: () => void
  onEdit: (key: ProviderKey) => void
  onDelete: (key: ProviderKey) => void
}

export default function KeysList({ provider, keys, onAdd, onEdit, onDelete }: KeysListProps) {
  const { t } = useTranslation('settings')
  const isLast = keys.length === 1

  return (
    <div data-testid={`keys-list-${provider}`}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h4>{t('provider_keys.title')}</h4>
        <button onClick={onAdd} data-testid="add-key">{t('provider_keys.add')}</button>
      </div>
      {keys.length === 0 && <p>{t('provider_keys.empty')}</p>}
      <ul style={{ listStyle: 'none', padding: 0 }}>
        {keys.map(k => (
          <li
            key={k.id}
            data-testid={`key-row-${k.id}`}
            style={{ display: 'flex', gap: '8px', alignItems: 'center', padding: '8px 0', borderBottom: '1px solid var(--border)' }}
          >
            <span style={{ flex: '1' }}>{k.label}</span>
            <span style={{ color: 'var(--text-secondary)' }}>{k.tier}</span>
            <span style={{ color: k.enabled ? 'var(--success)' : 'var(--warning)' }}>
              {k.enabled ? t('provider_keys.enabled') : t('provider_keys.disabled')}
            </span>
            <button onClick={() => onEdit(k)} data-testid={`edit-key-${k.id}`}>
              {t('provider_keys.edit')}
            </button>
            <button
              onClick={() => onDelete(k)}
              data-testid={`delete-key-${k.id}`}
              aria-label={isLast ? t('provider_keys.delete_last_aria') : t('provider_keys.delete_aria')}
            >
              {t('provider_keys.delete')}
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}
```

- [ ] **Step 5: KeyEditDialog + its tests**

Create `frontend/src/components/settings/KeyEditDialog.tsx`:

```tsx
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { ProviderKey } from '@/api/providerKeys'
import { testConnection } from '@/api/providerKeys'

export interface KeyEditDialogProps {
  provider: string
  initial?: ProviderKey | null
  onSave: (payload: { label: string; api_key: string; tier: string; enabled: boolean; username?: string; password?: string }) => void
  onCancel: () => void
}

export default function KeyEditDialog({ provider, initial, onSave, onCancel }: KeyEditDialogProps) {
  const { t } = useTranslation('settings')
  const [label, setLabel] = useState(initial?.label ?? 'primary')
  const [apiKey, setApiKey] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [tier, setTier] = useState(initial?.tier ?? 'free')
  const [enabled, setEnabled] = useState(initial?.enabled ?? true)
  const [probeResult, setProbeResult] = useState<{ ok: boolean; message: string } | null>(null)

  const handleTest = async () => {
    try {
      const res = await testConnection(provider, { api_key: apiKey, username: username || undefined, password: password || undefined })
      setProbeResult(res)
    } catch (e) {
      setProbeResult({ ok: false, message: String(e) })
    }
  }

  const handleSave = () => {
    onSave({
      label,
      api_key: apiKey,
      tier,
      enabled,
      username: username || undefined,
      password: password || undefined,
    })
  }

  const canSave = label.length > 0 && apiKey.length > 0

  return (
    <div role="dialog" data-testid="key-edit-dialog">
      <h3>{initial ? t('provider_keys.edit_title') : t('provider_keys.add_title')}</h3>
      <label>{t('provider_keys.label_field')} <input data-testid="field-label" value={label} onChange={e => setLabel(e.target.value)} /></label>
      <label>{t('provider_keys.api_key_field')} <input type="password" data-testid="field-api-key" value={apiKey} onChange={e => setApiKey(e.target.value)} /></label>
      <label>{t('provider_keys.tier_field')}
        <select data-testid="field-tier" value={tier} onChange={e => setTier(e.target.value)}>
          <option value="free">free</option>
          <option value="vip">vip</option>
          <option value="vip+">vip+</option>
        </select>
      </label>
      <label>{t('provider_keys.username_field')} <input data-testid="field-username" value={username} onChange={e => setUsername(e.target.value)} /></label>
      <label>{t('provider_keys.password_field')} <input type="password" data-testid="field-password" value={password} onChange={e => setPassword(e.target.value)} /></label>
      <label>{t('provider_keys.enabled_field')} <input type="checkbox" data-testid="field-enabled" checked={enabled} onChange={e => setEnabled(e.target.checked)} /></label>
      <div>
        <button onClick={handleTest} data-testid="test-connection">{t('provider_keys.test_connection')}</button>
        {probeResult && (
          <span data-testid="probe-result" style={{ color: probeResult.ok ? 'var(--success)' : 'var(--warning)' }}>
            {probeResult.message}
          </span>
        )}
      </div>
      <button onClick={handleSave} disabled={!canSave} data-testid="save-key">{t('provider_keys.save')}</button>
      <button onClick={onCancel} data-testid="cancel-key">{t('provider_keys.cancel')}</button>
    </div>
  )
}
```

Create `frontend/src/components/settings/__tests__/KeyEditDialog.test.tsx`:

```tsx
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'
import KeyEditDialog from '../KeyEditDialog'

describe('KeyEditDialog', () => {
  test('save button disabled until required fields filled', () => {
    render(<KeyEditDialog provider="opensubtitles" onSave={vi.fn()} onCancel={vi.fn()} />)
    const save = screen.getByTestId('save-key') as HTMLButtonElement
    // Default label is "primary" so only api_key is missing
    expect(save.disabled).toBe(true)
    fireEvent.change(screen.getByTestId('field-api-key'), { target: { value: 'abc' } })
    expect((screen.getByTestId('save-key') as HTMLButtonElement).disabled).toBe(false)
  })

  test('save invokes onSave with payload', () => {
    const onSave = vi.fn()
    render(<KeyEditDialog provider="opensubtitles" onSave={onSave} onCancel={vi.fn()} />)
    fireEvent.change(screen.getByTestId('field-api-key'), { target: { value: 'abc' } })
    fireEvent.click(screen.getByTestId('save-key'))
    expect(onSave).toHaveBeenCalledWith(
      expect.objectContaining({ label: 'primary', api_key: 'abc', tier: 'free', enabled: true })
    )
  })
})
```

- [ ] **Step 6: Mount in the provider settings page**

Locate the provider-config page (`grep -rn "Provider & Zugangsdaten" frontend/src` should find it). Add a new section below the existing provider-credentials form that, for each configured provider, renders:

```tsx
<KeysList
  provider={name}
  keys={keysQuery.data ?? []}
  onAdd={() => setDialog({ open: true, provider: name, initial: null })}
  onEdit={(k) => setDialog({ open: true, provider: name, initial: k })}
  onDelete={(k) => handleDelete(name, k)}
/>
```

with state management for the dialog and React Query hooks bound to `listKeys(name)`. Keep the existing legacy input fields visible for backwards compatibility (the migration already populated the pool from those fields).

- [ ] **Step 7: i18n keys**

In both `frontend/src/i18n/locales/de/settings.json` and `en/settings.json`, add inside the provider section:

```json
"provider_keys": {
  "title": "API-Schlüssel",
  "title_en": "API keys",
  "add": "Schlüssel hinzufügen",
  "empty": "Keine Schlüssel konfiguriert.",
  "enabled": "Aktiv",
  "disabled": "Deaktiviert",
  "edit": "Bearbeiten",
  "delete": "Löschen",
  "delete_aria": "Schlüssel löschen",
  "delete_last_aria": "Letzten Schlüssel löschen — Provider wird deaktiviert",
  "edit_title": "Schlüssel bearbeiten",
  "add_title": "Schlüssel hinzufügen",
  "label_field": "Label",
  "api_key_field": "API-Schlüssel",
  "tier_field": "Tier",
  "username_field": "Username (optional)",
  "password_field": "Passwort (optional)",
  "enabled_field": "Aktiv",
  "test_connection": "Verbindung testen",
  "save": "Speichern",
  "cancel": "Abbrechen"
}
```

EN mirror (same keys, English values). Update the DE strings to remove the `"title_en"` helper once the actual EN file is created — the `"title_en"` key in the DE snippet is a scaffolding hint and should NOT be shipped.

- [ ] **Step 8: Run frontend tests + tsc + lint**

```bash
cd frontend && npx vitest run src/components/settings src/api/providerKeys && npx tsc --noEmit && npm run lint
```
Expected: green across all three.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/api/providerKeys.ts frontend/src/api/health.ts frontend/src/components/settings/ frontend/src/i18n/locales/
git commit -m "feat(ui): multi-key pool management UI (list + add/edit dialog + test-connection)"
```

---

## Task 12 — Frontend: per-series override settings + budget widget expand

**Files:**
- Create: `frontend/src/components/library/SeriesOverrideSettings.tsx`
- Create: `frontend/src/components/library/__tests__/SeriesOverrideSettings.test.tsx`
- Modify: `frontend/src/pages/Library/SeriesDetail.tsx` (or equivalent — locate via `grep -rn "SeriesDetail" frontend/src`)
- Modify: `frontend/src/components/dashboard/BudgetWidget.tsx`
- Modify: `frontend/src/components/dashboard/__tests__/BudgetWidget.test.tsx`
- Modify: `frontend/src/i18n/locales/{de,en}/settings.json`
- Modify: `frontend/src/i18n/locales/{de,en}/dashboard.json`

- [ ] **Step 1: Failing test — SeriesOverrideSettings**

Create `frontend/src/components/library/__tests__/SeriesOverrideSettings.test.tsx`:

```tsx
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'
import SeriesOverrideSettings from '../SeriesOverrideSettings'

describe('SeriesOverrideSettings', () => {
  test('save disabled until a field changes', () => {
    render(
      <SeriesOverrideSettings
        seriesId={1}
        initial={{ priority_override: null, min_attempts_per_day: 0 }}
        onSave={vi.fn()}
      />,
    )
    expect((screen.getByTestId('save-override') as HTMLButtonElement).disabled).toBe(true)
    fireEvent.change(screen.getByTestId('priority-override-select'), { target: { value: 'premium' } })
    expect((screen.getByTestId('save-override') as HTMLButtonElement).disabled).toBe(false)
  })

  test('onSave receives current values', () => {
    const onSave = vi.fn()
    render(
      <SeriesOverrideSettings
        seriesId={1}
        initial={{ priority_override: null, min_attempts_per_day: 0 }}
        onSave={onSave}
      />,
    )
    fireEvent.change(screen.getByTestId('priority-override-select'), { target: { value: 'premium' } })
    fireEvent.change(screen.getByTestId('min-attempts-input'), { target: { value: '5' } })
    fireEvent.click(screen.getByTestId('save-override'))
    expect(onSave).toHaveBeenCalledWith({ priority_override: 'premium', min_attempts_per_day: 5 })
  })
})
```

- [ ] **Step 2: Run — fails**.

- [ ] **Step 3: Implement**

Create `frontend/src/components/library/SeriesOverrideSettings.tsx`:

```tsx
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

export interface SeriesOverrideSettingsProps {
  seriesId: number
  initial: { priority_override: string | null; min_attempts_per_day: number }
  onSave: (payload: { priority_override: string | null; min_attempts_per_day: number }) => void
}

export default function SeriesOverrideSettings({ seriesId, initial, onSave }: SeriesOverrideSettingsProps) {
  const { t } = useTranslation('settings')
  const [priority, setPriority] = useState<string>(initial.priority_override ?? '')
  const [min, setMin] = useState(initial.min_attempts_per_day)

  const dirty = priority !== (initial.priority_override ?? '') || min !== initial.min_attempts_per_day

  const handleSave = () => {
    onSave({
      priority_override: priority === '' ? null : priority,
      min_attempts_per_day: min,
    })
  }

  return (
    <section data-testid={`series-override-${seriesId}`}>
      <h4>{t('series_override.title')}</h4>
      <label>
        {t('series_override.priority')}
        <select
          data-testid="priority-override-select"
          value={priority}
          onChange={e => setPriority(e.target.value)}
        >
          <option value="">{t('series_override.inherit')}</option>
          <option value="premium">{t('series_override.premium')}</option>
          <option value="standard">{t('series_override.standard')}</option>
          <option value="backlog">{t('series_override.backlog')}</option>
        </select>
      </label>
      <label>
        {t('series_override.min_attempts')}
        <input
          type="number"
          data-testid="min-attempts-input"
          min={0}
          max={50}
          value={min}
          onChange={e => {
            const v = Number(e.target.value)
            const clamped = Math.max(0, Math.min(50, Number.isFinite(v) ? v : 0))
            setMin(clamped)
          }}
        />
      </label>
      <button data-testid="save-override" disabled={!dirty} onClick={handleSave}>
        {t('series_override.save')}
      </button>
    </section>
  )
}
```

- [ ] **Step 4: Add to SeriesDetail page**

Locate the series detail page and mount `SeriesOverrideSettings` in a new "Settings" panel. Bind save to a React Query mutation calling `PATCH /api/v1/series/<id>/settings`. Invalidate the relevant queries on success. Keep the diff tight — one new section.

- [ ] **Step 5: i18n keys**

Add to `frontend/src/i18n/locales/{de,en}/settings.json`:

```json
"series_override": {
  "title": "Planer-Override",
  "priority": "Priorität",
  "inherit": "Erben",
  "premium": "Premium",
  "standard": "Standard",
  "backlog": "Backlog",
  "min_attempts": "Mindestversuche pro Tag",
  "save": "Speichern"
}
```

EN mirror with English values.

- [ ] **Step 6: Budget widget per-key expand**

In `frontend/src/components/dashboard/BudgetWidget.tsx`, inside `BudgetRow`, add expandable per-key content:

1. Add local state: `const [expanded, setExpanded] = useState(false)`.
2. Wrap the existing row in a clickable container that toggles `expanded` when `provider.keys && provider.keys.length > 1`.
3. When `expanded`, render a `<ul>` below the progress bar showing each key's label + usage bar.

Extend the test file with:

```tsx
test('clicking a row with 2+ keys reveals per-key breakdown', async () => {
  renderWithBudget({
    enabled: true,
    providers: [{
      name: 'opensubtitles', tier: 'vip',
      limits: { second: 10, hour: 1000, day: 11000 },
      usage: { second: 0, hour: 0, day: 100 },
      reset_seconds: { second: 1, hour: 60, day: 36000 },
      keys: [
        { id: 1, label: 'primary', tier: 'vip',
          used: { second: 0, hour: 0, day: 90 },
          limit: { second: 10, hour: 1000, day: 10000 },
          last_429_at: null, last_used_at: null },
        { id: 2, label: 'backup', tier: 'free',
          used: { second: 0, hour: 0, day: 10 },
          limit: { second: 1, hour: 20, day: 200 },
          last_429_at: null, last_used_at: null },
      ],
    }],
  })
  const row = screen.getByTestId('budget-row-opensubtitles')
  fireEvent.click(row)
  expect(screen.getByTestId('key-detail-1')).toHaveTextContent('primary')
  expect(screen.getByTestId('key-detail-2')).toHaveTextContent('backup')
})
```

Add to `frontend/src/i18n/locales/{de,en}/dashboard.json`:

```json
"budget": {
  "...": "...",
  "per_key_breakdown": "Schlüssel-Aufschlüsselung"
}
```

EN: `"Per-key breakdown"`. Leave existing keys untouched; append inside the `budget` object.

- [ ] **Step 7: Run tests + tsc + lint**

```bash
cd frontend && npx vitest run src/components/library src/components/dashboard && npx tsc --noEmit && npm run lint
```
Expected: all green.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/library/ frontend/src/components/dashboard/BudgetWidget.tsx frontend/src/components/dashboard/__tests__/BudgetWidget.test.tsx frontend/src/pages/Library/ frontend/src/i18n/locales/
git commit -m "feat(ui): per-series overrides panel + budget widget per-key expand"
```

---

## Task 13 — End-to-end: aggregate budget + min-per-day guarantee + priority override

**Files:**
- Create: `backend/tests/test_phase4a_e2e.py`

- [ ] **Step 1: Write the E2E scenarios**

Create `backend/tests/test_phase4a_e2e.py`:

```python
"""Phase 4a end-to-end tests: multi-key aggregate, min-per-day, priority override."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from db.models.core import SeriesSettings, WantedItem
from db.repositories.provider_account_pool import ProviderAccountPoolRepository
from db.repositories.wanted import WantedRepository
from extensions import db


def _make_item(**kwargs):
    now = datetime(2026, 4, 17, tzinfo=UTC)
    defaults = dict(
        item_type="episode",
        file_path=f"/m/{kwargs.get('title', 'x')}.mkv",
        title=kwargs.get("title", "x"),
        season_episode="S01E01",
        status="wanted",
        target_language="de",
        subtitle_type="full",
        added_at=now,
        updated_at=now,
        priority="standard",
    )
    defaults.update(kwargs)
    it = WantedItem(**defaults)
    db.session.add(it)
    db.session.commit()
    return it


def test_aggregate_budget_doubles_with_two_vip_keys(app_ctx, client):
    repo = ProviderAccountPoolRepository()
    repo.add(provider="opensubtitles", label="primary", api_key="a", tier="vip")
    repo.add(provider="opensubtitles", label="backup", api_key="b", tier="vip")

    from unittest.mock import MagicMock, patch

    p = MagicMock()
    p.name = "opensubtitles"
    p.tier = "vip"
    type(p).rate_limits = {
        "free": {"second": 5, "hour": 200, "day": 1000},
        "vip": {"second": 10, "hour": 1000, "day": 10000},
    }
    mgr = MagicMock()
    mgr._providers = {"opensubtitles": p}
    with patch("routes.system.budget.get_provider_manager", return_value=mgr):
        resp = client.get("/api/v1/system/budget")
    body = resp.get_json()
    os_row = next(r for r in body["providers"] if r["name"] == "opensubtitles")
    assert os_row["limits"]["day"] == 20000
    assert len(os_row["keys"]) == 2


def test_min_attempts_per_day_guarantees_inclusion(app_ctx):
    # Series 100 has min=3; 5 wanted items for it. 10 unrelated items also wanted.
    s = SeriesSettings(
        sonarr_series_id=100,
        absolute_order=0,
        min_attempts_per_day=3,
        priority_override=None,
        updated_at=datetime(2026, 4, 17, tzinfo=UTC),
    )
    db.session.add(s)
    db.session.commit()

    boss = [_make_item(title=f"boss-{i}", sonarr_series_id=100) for i in range(5)]
    _ = [_make_item(title=f"other-{i}") for i in range(10)]

    from services.wanted_search_runner import _collect_min_attempts_items

    prefix = _collect_min_attempts_items()
    prefix_ids = [p["id"] for p in prefix]
    # Exactly 3 boss items (the first 3 oldest-searched for series 100).
    assert len(prefix_ids) == 3
    assert set(prefix_ids).issubset({b.id for b in boss})


def test_priority_override_wins_over_item_priority(app_ctx):
    s = SeriesSettings(
        sonarr_series_id=200,
        absolute_order=0,
        min_attempts_per_day=0,
        priority_override="premium",
        updated_at=datetime(2026, 4, 17, tzinfo=UTC),
    )
    db.session.add(s)
    db.session.commit()

    override_item = _make_item(title="override", sonarr_series_id=200, priority="backlog")
    _make_item(title="other", sonarr_series_id=None, priority="standard")

    rows = WantedRepository().get_items_for_scheduled_search(limit=10, order="fair")
    ids = [r["id"] for r in rows]
    assert ids[0] == override_item.id  # override promotes backlog -> premium -> top rank
```

- [ ] **Step 2: Run — expect green on first try (pure integration of Tasks 1-10)**

`cd backend && python -m pytest tests/test_phase4a_e2e.py -v`
Expected: 3 passed.

- [ ] **Step 3: Ruff + commit**

```bash
cd backend && ruff check tests/test_phase4a_e2e.py && ruff format --check tests/test_phase4a_e2e.py
git add backend/tests/test_phase4a_e2e.py
git commit -m "test(scheduler): phase 4a e2e — aggregate budget + min-per-day + override"
```

---

## Task 14 — Pre-release verification

- [ ] **Step 1: Backend full suite**

```bash
cd backend && python -m pytest --tb=short -q --ignore=tests/performance
```
Expected: no regressions. All Phase 4a new tests green.

- [ ] **Step 2: Backend ruff**

```bash
cd backend && ruff check . && ruff format --check .
```
Expected: clean (same pre-existing violations as phase-3-ready tag — document and skip; none introduced by Phase 4a).

- [ ] **Step 3: Frontend checks**

```bash
cd frontend && npm run lint && npx tsc --noEmit && npm run test -- --run
```
Expected: 0 errors; vitest all green.

- [ ] **Step 4: Dev-server smoke**

Start `npm run dev`, navigate to:
1. Dashboard → budget widget shows per-key breakdown on click for providers with 2+ keys.
2. Settings → Provider config → Keys section lists the auto-migrated primary key.
3. Library → Series detail → Settings panel has priority-override + min-attempts controls.

Verify `/api/v1/system/budget` via curl shows `keys[]` array populated.

- [ ] **Step 5: Tag**

```bash
cd "D:/Sublarr_Projekt/Sublarr" && git tag phase-4a-ready && git tag --list | grep phase-4
```

---

## Phase 4a exit checklist

Before running `/deploy`:

- [ ] All 14 implementation tasks committed to master
- [ ] Backend + frontend test suites green locally (no new failures vs `phase-3-ready` tag)
- [ ] `/api/v1/system/budget` returns `keys[]` populated for every provider that has a pool row
- [ ] Adding a 2nd enabled key via the Settings UI immediately shows up on the dashboard widget
- [ ] Creating a series with `priority_override="premium"` + `min_attempts_per_day=5` produces inclusion in every scheduler tick until the daily quota is met
- [ ] Migration idempotent: `alembic upgrade head` + `alembic downgrade -1` + `alembic upgrade head` completes without error (SQLite batch mode)
- [ ] CHANGELOG entry queued for the next release

---

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Auto-migration seeds wrong tier for OS (e.g. detects vip but user downgraded) | After migration, user can edit the primary key via the UI; detection is best-effort |
| Concurrent searches double-consume a key that's just hit its cap | Budget gate (aggregate) is checked BEFORE key selection; key selector only picks among keys with remaining budget; worst case one extra call per key per window boundary |
| KeySelector cache staleness after a UI edit | Every key-CRUD endpoint invalidates the selector cache for the affected provider |
| Backlog gate silently drops a min-per-day item | `exempt_ids` parameter threads through; E2E test in Task 13 verifies the invariant |
| series_settings PK is sonarr_series_id only (no standalone) | Documented as known limitation for Phase 4a; standalone support deferred until a real need arises |
| Two min-per-day series compete for budget | Warning log on shortfall; caller sees the warning in application logs; no crash |
