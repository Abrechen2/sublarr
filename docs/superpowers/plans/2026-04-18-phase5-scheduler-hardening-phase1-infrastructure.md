# Phase 5 / Rollout Phase 1 — Scheduler Infrastructure

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-04-18-phase5-scheduler-hardening-design.md`

**Goal:** Land the scheduler infrastructure (`SublarrScheduler` facade, `JobRun` model, migration, tick wrapper, listeners, Prometheus metrics, single-instance guard) without touching any existing `threading.Timer` sites. Phase 1 is shippable as a no-op — the facade exists but no JobSpecs are registered yet except `scheduler_history_cleanup`.

**Architecture:** New module `services/scheduler.py` owns a `BackgroundScheduler` backed by `SQLAlchemyJobStore`. `_tick_wrapper` enters Flask app_context, enforces timeout via `ThreadPoolExecutor`, writes `scheduler_job_runs` rows via event listeners and a fresh scoped session. Startup wired into `create_app()` behind a `SUBLARR_SCHEDULER_ROLE` env gate. Shutdown bounded at 25s.

**Tech Stack:** APScheduler 3.10+, SQLAlchemy 2.0, Flask 3, Alembic, pytest, freezegun.

**Dependencies:** None (first phase in series).

**Downstream phases:** Phase 2 (API + read-only UI), Phase 3 (write endpoints), Phase 4 (migrate 4 Timer sites), Phase 5 (debouncer), Phase 6 (cleanup).

---

## File Structure

### New files
- `backend/services/scheduler.py` — facade, JobSpec, registry, listeners, tick wrapper (~260 LOC)
- `backend/db/models/scheduler.py` — JobRun ORM model (~40 LOC)
- `backend/db/migrations/versions/<rev>_scheduler_infrastructure.py` — creates both tables
- `backend/utils/scheduler_retention.py` — `delete_old_job_runs()` (~30 LOC)
- `backend/tests/test_scheduler_jobspec.py`
- `backend/tests/test_scheduler_facade.py`
- `backend/tests/test_scheduler_tick_wrapper.py`
- `backend/tests/test_scheduler_listeners.py`
- `backend/tests/test_scheduler_startup_reconciliation.py`
- `backend/tests/test_scheduler_migration.py`
- `backend/tests/test_scheduler_retention.py`
- `backend/tests/test_scheduler_second_instance_guard.py`
- `backend/tests/conftest_scheduler.py` — fixtures (imported from conftest.py)

### Modified files
- `backend/requirements.txt` — add `APScheduler>=3.10,<4`
- `backend/config_settings.py` — add `scheduler_history_retention_days`
- `backend/app_schedulers.py` — wire `SublarrScheduler.start()` behind env gate
- `backend/app_shutdown.py` — wire bounded `shutdown()`
- `backend/tests/conftest.py` — import scheduler fixtures
- `backend/monitoring/metrics.py` — register Prometheus counters/histogram (create if absent)

---

## Task 1: Add APScheduler dependency

**Files:**
- Modify: `backend/requirements.txt`

- [ ] **Step 1: Add the dependency pin**

Edit `backend/requirements.txt`. Add this line in alphabetical order (between existing entries starting with `a`):

```
APScheduler>=3.10,<4
```

- [ ] **Step 2: Install in venv**

Run: `cd /d/Sublarr_Projekt/Sublarr/backend && pip install -r requirements.txt`
Expected: `Successfully installed APScheduler-3.x.x tzlocal-x.x.x` (or already-satisfied if present).

- [ ] **Step 3: Smoke-test import**

Run: `cd /d/Sublarr_Projekt/Sublarr/backend && python -c "from apscheduler.schedulers.background import BackgroundScheduler; from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore; from apscheduler.triggers.interval import IntervalTrigger; from apscheduler.triggers.cron import CronTrigger; from apscheduler.triggers.date import DateTrigger; print('ok')"`
Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
git add backend/requirements.txt
git commit -m "feat(phase5): add APScheduler dependency"
```

---

## Task 2: JobRun ORM model

**Files:**
- Create: `backend/db/models/scheduler.py`
- Test: `backend/tests/test_scheduler_model.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_scheduler_model.py`:

```python
"""Unit tests for JobRun ORM model."""

from datetime import UTC, datetime

import pytest
from db.models.scheduler import JobRun


def test_jobrun_tablename_and_columns():
    assert JobRun.__tablename__ == "scheduler_job_runs"
    cols = {c.name for c in JobRun.__table__.columns}
    assert cols == {
        "id", "job_id", "started_at", "finished_at", "duration_ms",
        "status", "triggered_by", "error_type", "error_msg",
    }


def test_jobrun_indexes():
    index_names = {ix.name for ix in JobRun.__table__.indexes}
    assert "ix_scheduler_job_runs_job_id_started_at" in index_names
    assert "ix_scheduler_job_runs_started_at" in index_names
    assert "ix_scheduler_job_runs_status" in index_names


def test_jobrun_default_triggered_by(app):
    with app.app_context():
        from extensions import db
        row = JobRun(
            job_id="x",
            started_at=datetime.now(UTC),
            status="ok",
        )
        db.session.add(row)
        db.session.flush()
        assert row.triggered_by == "schedule"
        db.session.rollback()


def test_jobrun_status_accepts_valid_values(app):
    with app.app_context():
        from extensions import db
        for status in ("ok", "error", "timeout", "missed", "skipped_overlap"):
            row = JobRun(
                job_id="x",
                started_at=datetime.now(UTC),
                status=status,
            )
            db.session.add(row)
        db.session.flush()
        db.session.rollback()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /d/Sublarr_Projekt/Sublarr/backend && python -m pytest tests/test_scheduler_model.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'db.models.scheduler'`.

- [ ] **Step 3: Create the ORM model**

Create `backend/db/models/scheduler.py`:

```python
"""JobRun ORM model — one row per scheduled job execution."""

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from extensions import db


class JobRun(db.Model):
    """One row per scheduled job execution.

    Populated by SublarrScheduler event listeners in services/scheduler.py.
    Retention controlled by ``scheduler_history_retention_days`` setting
    and swept by the ``scheduler_history_cleanup`` cron job.
    """

    __tablename__ = "scheduler_job_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    triggered_by: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="schedule", default="schedule"
    )
    error_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_scheduler_job_runs_job_id_started_at", "job_id", "started_at"),
        Index("ix_scheduler_job_runs_started_at", "started_at"),
        Index("ix_scheduler_job_runs_status", "status"),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /d/Sublarr_Projekt/Sublarr/backend && python -m pytest tests/test_scheduler_model.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/db/models/scheduler.py backend/tests/test_scheduler_model.py
git commit -m "feat(phase5): add JobRun ORM model"
```

---

## Task 3: Alembic migration for scheduler tables

**Files:**
- Create: `backend/db/migrations/versions/<autogenerated>_scheduler_infrastructure.py`
- Test: `backend/tests/test_scheduler_migration.py`

- [ ] **Step 1: Find the current Alembic head**

Run: `cd /d/Sublarr_Projekt/Sublarr/backend && python -m flask --app app db heads`
Expected: one line like `p4a_readd_wanted_sonarr_idx (head)`. Record the revision id as `<CURRENT_HEAD>` for Step 3.

- [ ] **Step 2: Generate migration skeleton**

Run: `cd /d/Sublarr_Projekt/Sublarr/backend && python -m flask --app app db revision -m "scheduler infrastructure"`
Expected: a new file created under `db/migrations/versions/`. Note the filename (starts with a hash), then open it for editing.

- [ ] **Step 3: Replace the generated content with explicit schema**

Replace the generated file's body with this (keep the auto-generated `revision` and `down_revision` at the top if Alembic set them — otherwise set `down_revision = "<CURRENT_HEAD>"` from Step 1):

```python
"""scheduler infrastructure

Revision ID: <autogenerated>
Revises: <CURRENT_HEAD>
Create Date: 2026-04-18

Creates both:
- scheduler_job_runs: run history owned by us
- apscheduler_jobs: mirrors SQLAlchemyJobStore's schema so it's
  Alembic-tracked and survives library version upgrades
"""

import sqlalchemy as sa
from alembic import op

revision = "<keep auto-generated>"
down_revision = "<CURRENT_HEAD>"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "scheduler_job_runs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("job_id", sa.String(64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column(
            "triggered_by",
            sa.String(16),
            nullable=False,
            server_default="schedule",
        ),
        sa.Column("error_type", sa.String(128), nullable=True),
        sa.Column("error_msg", sa.Text, nullable=True),
    )
    op.create_index(
        "ix_scheduler_job_runs_job_id_started_at",
        "scheduler_job_runs",
        ["job_id", "started_at"],
    )
    op.create_index(
        "ix_scheduler_job_runs_started_at",
        "scheduler_job_runs",
        ["started_at"],
    )
    op.create_index(
        "ix_scheduler_job_runs_status",
        "scheduler_job_runs",
        ["status"],
    )

    op.create_table(
        "apscheduler_jobs",
        sa.Column("id", sa.Unicode(191), primary_key=True),
        sa.Column("next_run_time", sa.Float(precision=25), nullable=True),
        sa.Column("job_state", sa.LargeBinary, nullable=False),
    )
    op.create_index(
        "ix_apscheduler_jobs_next_run_time",
        "apscheduler_jobs",
        ["next_run_time"],
    )


def downgrade():
    op.drop_index(
        "ix_apscheduler_jobs_next_run_time",
        table_name="apscheduler_jobs",
    )
    op.drop_table("apscheduler_jobs")
    op.drop_index(
        "ix_scheduler_job_runs_status",
        table_name="scheduler_job_runs",
    )
    op.drop_index(
        "ix_scheduler_job_runs_started_at",
        table_name="scheduler_job_runs",
    )
    op.drop_index(
        "ix_scheduler_job_runs_job_id_started_at",
        table_name="scheduler_job_runs",
    )
    op.drop_table("scheduler_job_runs")
```

- [ ] **Step 4: Write migration regression tests**

Create `backend/tests/test_scheduler_migration.py`:

```python
"""Migration regression tests for scheduler_infrastructure."""

import sqlalchemy as sa


def test_upgrade_creates_both_tables(migrated_db_engine):
    """After running migrations, both tables exist with expected indexes."""
    insp = sa.inspect(migrated_db_engine)
    assert "scheduler_job_runs" in insp.get_table_names()
    assert "apscheduler_jobs" in insp.get_table_names()

    run_cols = {c["name"] for c in insp.get_columns("scheduler_job_runs")}
    assert run_cols == {
        "id", "job_id", "started_at", "finished_at", "duration_ms",
        "status", "triggered_by", "error_type", "error_msg",
    }
    aps_cols = {c["name"] for c in insp.get_columns("apscheduler_jobs")}
    assert aps_cols == {"id", "next_run_time", "job_state"}

    run_ix = {ix["name"] for ix in insp.get_indexes("scheduler_job_runs")}
    assert "ix_scheduler_job_runs_job_id_started_at" in run_ix
    assert "ix_scheduler_job_runs_started_at" in run_ix
    assert "ix_scheduler_job_runs_status" in run_ix

    aps_ix = {ix["name"] for ix in insp.get_indexes("apscheduler_jobs")}
    assert "ix_apscheduler_jobs_next_run_time" in aps_ix


def test_downgrade_drops_both_tables(migrated_db_engine):
    """Downgrade -1 then upgrade head is a no-op round-trip."""
    from alembic import command
    from alembic.config import Config

    cfg = Config("backend/alembic.ini")  # test-scoped alembic config
    cfg.set_main_option("script_location", "backend/db/migrations")
    cfg.set_main_option(
        "sqlalchemy.url", str(migrated_db_engine.url)
    )
    command.downgrade(cfg, "-1")
    insp = sa.inspect(migrated_db_engine)
    assert "scheduler_job_runs" not in insp.get_table_names()
    assert "apscheduler_jobs" not in insp.get_table_names()

    command.upgrade(cfg, "head")
    insp = sa.inspect(migrated_db_engine)
    assert "scheduler_job_runs" in insp.get_table_names()
    assert "apscheduler_jobs" in insp.get_table_names()


def test_apscheduler_jobs_shape_matches_library_expectation():
    """apscheduler_jobs columns match what SQLAlchemyJobStore writes.

    If this test fails after an apscheduler upgrade, regenerate the
    migration after inspecting jobstore.tables.Jobs.__table__.
    """
    from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

    store = SQLAlchemyJobStore(url="sqlite:///:memory:", tablename="apscheduler_jobs")
    # Accessing .jobs_t creates the in-memory Table definition.
    expected_cols = {c.name for c in store.jobs_t.columns}
    assert expected_cols == {"id", "next_run_time", "job_state"}
```

Add this fixture to `backend/tests/conftest.py` (if not present):

```python
@pytest.fixture
def migrated_db_engine(tmp_path, monkeypatch):
    """Fresh SQLite DB with all migrations applied."""
    import sqlalchemy as sa
    from alembic import command
    from alembic.config import Config

    db_path = tmp_path / "test.db"
    url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", url)

    cfg = Config("backend/alembic.ini")
    cfg.set_main_option("script_location", "backend/db/migrations")
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")

    engine = sa.create_engine(url)
    try:
        yield engine
    finally:
        engine.dispose()
```

- [ ] **Step 5: Run test to verify both upgrade + downgrade work**

Run: `cd /d/Sublarr_Projekt/Sublarr/backend && python -m pytest tests/test_scheduler_migration.py -v`
Expected: 3 passed.

- [ ] **Step 6: Run full migration against dev DB**

Run: `cd /d/Sublarr_Projekt/Sublarr/backend && python -m flask --app app db upgrade`
Expected: `INFO  [alembic.runtime.migration] Running upgrade <CURRENT_HEAD> -> <new_rev>, scheduler infrastructure`.

- [ ] **Step 7: Commit**

```bash
git add backend/db/migrations/versions/*_scheduler_infrastructure.py backend/tests/test_scheduler_migration.py backend/tests/conftest.py
git commit -m "feat(phase5): migrate scheduler_job_runs + apscheduler_jobs schemas"
```

---

## Task 4: JobSpec dataclass

**Files:**
- Create: `backend/services/scheduler.py` (initial, will grow in later tasks)
- Test: `backend/tests/test_scheduler_jobspec.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_scheduler_jobspec.py`:

```python
"""JobSpec dataclass validation."""

import pytest
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from services.scheduler import JobSpec


def _noop():
    pass


def test_jobspec_minimum_fields():
    spec = JobSpec(
        id="x",
        func=_noop,
        default_trigger=IntervalTrigger(seconds=60),
    )
    assert spec.id == "x"
    assert spec.timeout_s == 300
    assert spec.max_instances == 1
    assert spec.coalesce is True
    assert spec.misfire_grace_time is None
    assert spec.description == ""


def test_jobspec_rejects_empty_id():
    with pytest.raises(ValueError, match="id must be non-empty"):
        JobSpec(id="", func=_noop, default_trigger=IntervalTrigger(seconds=60))


def test_jobspec_rejects_invalid_timeout():
    with pytest.raises(ValueError, match="timeout_s"):
        JobSpec(
            id="x", func=_noop, default_trigger=IntervalTrigger(seconds=60),
            timeout_s=0,
        )


def test_jobspec_rejects_non_callable_func():
    with pytest.raises(TypeError, match="callable"):
        JobSpec(
            id="x", func="not callable", default_trigger=IntervalTrigger(seconds=60),
        )


def test_jobspec_accepts_cron_trigger():
    spec = JobSpec(
        id="x", func=_noop,
        default_trigger=CronTrigger(hour=3, minute=0),
    )
    assert isinstance(spec.default_trigger, CronTrigger)


def test_jobspec_is_immutable():
    spec = JobSpec(id="x", func=_noop, default_trigger=IntervalTrigger(seconds=60))
    with pytest.raises((AttributeError, TypeError)):
        spec.id = "changed"


def test_compute_default_misfire_grace_time_interval():
    """Interval triggers get half-interval misfire grace by default."""
    from services.scheduler import compute_default_misfire_grace_time

    assert compute_default_misfire_grace_time(
        IntervalTrigger(seconds=120)
    ) == 60
    assert compute_default_misfire_grace_time(
        IntervalTrigger(minutes=10)
    ) == 300


def test_compute_default_misfire_grace_time_cron():
    """Cron triggers get fixed 60s default."""
    from services.scheduler import compute_default_misfire_grace_time

    assert compute_default_misfire_grace_time(
        CronTrigger(hour=3, minute=0)
    ) == 60
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /d/Sublarr_Projekt/Sublarr/backend && python -m pytest tests/test_scheduler_jobspec.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'services.scheduler'`.

- [ ] **Step 3: Create the initial services/scheduler.py with JobSpec**

Create `backend/services/scheduler.py`:

```python
"""Sublarr scheduler service — APScheduler facade + JobSpec registry.

This file will grow across Phase 1 tasks; at this point it only
contains JobSpec + compute_default_misfire_grace_time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from apscheduler.triggers.base import BaseTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger


def compute_default_misfire_grace_time(trigger: BaseTrigger) -> int:
    """Return the default misfire grace (seconds) for a trigger.

    - IntervalTrigger: half of the interval in seconds.
    - CronTrigger (and anything else): 60 seconds.
    """
    if isinstance(trigger, IntervalTrigger):
        total = int(trigger.interval.total_seconds())
        return max(1, total // 2)
    return 60


@dataclass(frozen=True)
class JobSpec:
    """Declarative spec for a recurring scheduled job.

    Fields:
      id: stable identifier; used as the JobStore row key.
      func: tick function taking no args; must be idempotent.
      default_trigger: IntervalTrigger or CronTrigger used when no
        user override exists in the JobStore.
      timeout_s: enforced by _tick_wrapper via ThreadPoolExecutor.
      max_instances: APScheduler concurrency cap (defaults to 1).
      coalesce: collapse missed fires into one on resume.
      misfire_grace_time: None means computed at registration from
        compute_default_misfire_grace_time.
      owner_module: module path shown in the UI for grouping/debug.
      description: human-readable summary shown in the UI.
    """

    id: str
    func: Callable[[], None]
    default_trigger: BaseTrigger
    timeout_s: int = 300
    max_instances: int = 1
    coalesce: bool = True
    misfire_grace_time: int | None = None
    owner_module: str = ""
    description: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("JobSpec.id must be non-empty string")
        if not callable(self.func):
            raise TypeError("JobSpec.func must be callable")
        if not isinstance(self.timeout_s, int) or self.timeout_s <= 0:
            raise ValueError(f"JobSpec.timeout_s must be > 0 (got {self.timeout_s!r})")
        if not isinstance(self.default_trigger, BaseTrigger):
            raise TypeError("JobSpec.default_trigger must be a BaseTrigger subclass")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /d/Sublarr_Projekt/Sublarr/backend && python -m pytest tests/test_scheduler_jobspec.py -v`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/services/scheduler.py backend/tests/test_scheduler_jobspec.py
git commit -m "feat(phase5): add JobSpec dataclass with validation"
```

---

## Task 5: Tick wrapper (TDD — happy path + app_context + history write)

**Files:**
- Modify: `backend/services/scheduler.py`
- Test: `backend/tests/test_scheduler_tick_wrapper.py`

- [ ] **Step 1: Write the failing tests for happy path + error + timeout + app_context**

Create `backend/tests/test_scheduler_tick_wrapper.py`:

```python
"""Tests for _tick_wrapper — timeout, error capture, app_context, history write."""

import logging
import time
from unittest.mock import MagicMock

import pytest
from apscheduler.triggers.interval import IntervalTrigger

from services.scheduler import JobSpec, _tick_wrapper


@pytest.fixture
def flask_app():
    from app import create_app
    return create_app(testing=True)


def _make_spec(fn, timeout_s=5):
    return JobSpec(
        id="test_job",
        func=fn,
        default_trigger=IntervalTrigger(seconds=60),
        timeout_s=timeout_s,
    )


def test_happy_path_writes_ok_row(flask_app, db_session):
    """A successful tick writes a scheduler_job_runs row with status='ok'."""
    from db.models.scheduler import JobRun

    ran = []
    spec = _make_spec(lambda: ran.append(1))
    _tick_wrapper(flask_app, spec, triggered_by="schedule")()

    assert ran == [1]
    rows = db_session.query(JobRun).filter_by(job_id="test_job").all()
    assert len(rows) == 1
    assert rows[0].status == "ok"
    assert rows[0].triggered_by == "schedule"
    assert rows[0].finished_at is not None
    assert rows[0].duration_ms is not None
    assert rows[0].duration_ms >= 0
    assert rows[0].error_type is None


def test_exception_writes_error_row(flask_app, db_session, caplog):
    """Tick raising writes row with status='error' and captures type/msg."""
    from db.models.scheduler import JobRun

    def boom():
        raise ValueError("deliberate")

    spec = _make_spec(boom)
    with caplog.at_level(logging.ERROR, logger="services.scheduler"):
        _tick_wrapper(flask_app, spec, triggered_by="schedule")()

    rows = db_session.query(JobRun).filter_by(job_id="test_job").all()
    assert len(rows) == 1
    assert rows[0].status == "error"
    assert rows[0].error_type == "ValueError"
    assert "deliberate" in (rows[0].error_msg or "")
    # exc_info=True required per feedback_alembic_pitfalls
    assert any("deliberate" in r.message or r.exc_info for r in caplog.records)


def test_timeout_writes_timeout_row(flask_app, db_session):
    """Tick exceeding timeout_s writes row with status='timeout'."""
    from db.models.scheduler import JobRun

    def slow():
        time.sleep(3)

    spec = _make_spec(slow, timeout_s=1)
    _tick_wrapper(flask_app, spec, triggered_by="schedule")()

    rows = db_session.query(JobRun).filter_by(job_id="test_job").all()
    assert len(rows) == 1
    assert rows[0].status == "timeout"
    assert rows[0].error_type == "TimeoutError"


def test_app_context_entered_before_fn(flask_app, db_session):
    """Regression for feedback_flask_app_context_in_threads — tick must see app_context."""
    from flask import has_app_context

    observed = []

    def check_ctx():
        observed.append(has_app_context())

    spec = _make_spec(check_ctx)
    _tick_wrapper(flask_app, spec, triggered_by="schedule")()

    assert observed == [True]


def test_triggered_by_manual(flask_app, db_session):
    """Tick called from run-now must persist triggered_by='manual'."""
    from db.models.scheduler import JobRun

    spec = _make_spec(lambda: None)
    _tick_wrapper(flask_app, spec, triggered_by="manual")()

    rows = db_session.query(JobRun).filter_by(job_id="test_job").all()
    assert rows[0].triggered_by == "manual"


def test_error_msg_truncated_to_4kb(flask_app, db_session):
    """Very long error messages are truncated before write."""
    from db.models.scheduler import JobRun

    def boom():
        raise RuntimeError("x" * 10000)

    spec = _make_spec(boom)
    _tick_wrapper(flask_app, spec, triggered_by="schedule")()

    rows = db_session.query(JobRun).filter_by(job_id="test_job").all()
    assert len(rows[0].error_msg) <= 4096
```

Add to `backend/tests/conftest.py` (if not present):

```python
@pytest.fixture
def db_session(app):
    """SQLAlchemy session bound to the test app, rolled back after each test."""
    from extensions import db
    with app.app_context():
        yield db.session
        db.session.rollback()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /d/Sublarr_Projekt/Sublarr/backend && python -m pytest tests/test_scheduler_tick_wrapper.py -v`
Expected: FAIL with `ImportError: cannot import name '_tick_wrapper'`.

- [ ] **Step 3: Add _tick_wrapper to services/scheduler.py**

Append to `backend/services/scheduler.py`:

```python
import logging
import traceback
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import UTC, datetime

from flask import Flask

logger = logging.getLogger(__name__)

_MAX_ERROR_MSG_BYTES = 4096

# Single shared executor for tick timeouts. Sized to the JobSpec count;
# resized at scheduler.start() once SCHEDULED_JOBS is known.
_tick_executor: ThreadPoolExecutor | None = None


def _get_tick_executor() -> ThreadPoolExecutor:
    global _tick_executor
    if _tick_executor is None:
        _tick_executor = ThreadPoolExecutor(
            max_workers=16, thread_name_prefix="scheduler-tick"
        )
    return _tick_executor


def _write_job_run(
    *,
    job_id: str,
    started_at: datetime,
    finished_at: datetime | None,
    status: str,
    triggered_by: str,
    error_type: str | None = None,
    error_msg: str | None = None,
) -> None:
    """Write a scheduler_job_runs row using a fresh scoped session.

    A fresh session is used so a corrupted tick session can't
    destroy the error record it was just trying to persist.
    """
    from extensions import db
    from db.models.scheduler import JobRun

    duration_ms = None
    if finished_at is not None:
        duration_ms = int((finished_at - started_at).total_seconds() * 1000)

    if error_msg and len(error_msg) > _MAX_ERROR_MSG_BYTES:
        error_msg = error_msg[: _MAX_ERROR_MSG_BYTES - 3] + "..."

    row = JobRun(
        job_id=job_id,
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=duration_ms,
        status=status,
        triggered_by=triggered_by,
        error_type=error_type,
        error_msg=error_msg,
    )
    try:
        with db.session.begin_nested():
            db.session.add(row)
        db.session.commit()
    except Exception:
        logger.error(
            "scheduler: failed to write job_run for %s",
            job_id,
            exc_info=True,
        )
        db.session.rollback()


def _tick_wrapper(
    app: Flask, spec: JobSpec, *, triggered_by: str = "schedule"
) -> Callable[[], None]:
    """Wrap a JobSpec.func into a callable safe for the scheduler to invoke.

    Guarantees:
      - enters app.app_context() before calling fn
      - enforces spec.timeout_s via ThreadPoolExecutor
      - catches all exceptions, logs with exc_info, writes history row
    """

    def _runner() -> None:
        started_at = datetime.now(UTC)
        status = "ok"
        error_type: str | None = None
        error_msg: str | None = None
        finished_at: datetime | None = None

        with app.app_context():
            try:
                future = _get_tick_executor().submit(spec.func)
                future.result(timeout=spec.timeout_s)
            except FutureTimeoutError:
                status = "timeout"
                error_type = "TimeoutError"
                error_msg = f"tick exceeded {spec.timeout_s}s"
                logger.error(
                    "scheduler: %s timed out after %ds",
                    spec.id,
                    spec.timeout_s,
                    exc_info=True,
                )
            except Exception as exc:
                status = "error"
                error_type = type(exc).__name__
                error_msg = f"{exc}\n{traceback.format_exc()}"
                logger.error(
                    "scheduler: %s raised %s",
                    spec.id,
                    error_type,
                    exc_info=True,
                )
            finally:
                finished_at = datetime.now(UTC)
                _write_job_run(
                    job_id=spec.id,
                    started_at=started_at,
                    finished_at=finished_at,
                    status=status,
                    triggered_by=triggered_by,
                    error_type=error_type,
                    error_msg=error_msg,
                )

    return _runner
```

- [ ] **Step 4: Run tests — expect all 6 passing**

Run: `cd /d/Sublarr_Projekt/Sublarr/backend && python -m pytest tests/test_scheduler_tick_wrapper.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/services/scheduler.py backend/tests/test_scheduler_tick_wrapper.py backend/tests/conftest.py
git commit -m "feat(phase5): add tick wrapper with timeout + error capture"
```

---

## Task 6: SublarrScheduler facade — init + start + shutdown

**Files:**
- Modify: `backend/services/scheduler.py`
- Test: `backend/tests/test_scheduler_facade.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_scheduler_facade.py`:

```python
"""SublarrScheduler facade lifecycle tests."""

import pytest
from apscheduler.triggers.interval import IntervalTrigger

from services.scheduler import JobSpec, SublarrScheduler


@pytest.fixture
def scheduler(app, tmp_path):
    url = f"sqlite:///{tmp_path / 'aps.db'}"
    s = SublarrScheduler(db_url=url, autostart=False)
    s.attach_app(app)
    yield s
    if s.running:
        s.shutdown(timeout_s=2)


def test_not_running_before_start(scheduler):
    assert scheduler.running is False


def test_start_makes_running(scheduler):
    scheduler.start()
    assert scheduler.running is True


def test_start_is_idempotent(scheduler):
    """Regression for feedback_scheduler_timer_leak — start() on a running
    scheduler must be a no-op, not a restart."""
    scheduler.start()
    first_instance = id(scheduler._scheduler)
    scheduler.start()
    scheduler.start()
    assert scheduler.running is True
    assert id(scheduler._scheduler) == first_instance


def test_shutdown_stops_running(scheduler):
    scheduler.start()
    scheduler.shutdown(timeout_s=5)
    assert scheduler.running is False


def test_shutdown_is_idempotent(scheduler):
    scheduler.start()
    scheduler.shutdown(timeout_s=5)
    scheduler.shutdown(timeout_s=5)  # no raise


def test_shutdown_bounded_by_timeout(scheduler):
    """shutdown(timeout_s=1) returns within ~1s even if nothing happens."""
    import time

    scheduler.start()
    t0 = time.monotonic()
    scheduler.shutdown(timeout_s=1)
    assert time.monotonic() - t0 < 3.0  # generous upper bound


def test_duplicate_job_id_raises(app, tmp_path):
    """Two JobSpecs with the same id must fail fast at registration."""
    url = f"sqlite:///{tmp_path / 'aps.db'}"
    s = SublarrScheduler(db_url=url, autostart=False)
    s.attach_app(app)
    spec1 = JobSpec(id="dup", func=lambda: None,
                    default_trigger=IntervalTrigger(seconds=60))
    spec2 = JobSpec(id="dup", func=lambda: None,
                    default_trigger=IntervalTrigger(seconds=30))
    s.register_job(spec1)
    with pytest.raises(ValueError, match="already registered"):
        s.register_job(spec2)
    s.shutdown(timeout_s=2) if s.running else None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /d/Sublarr_Projekt/Sublarr/backend && python -m pytest tests/test_scheduler_facade.py -v`
Expected: FAIL with `ImportError: cannot import name 'SublarrScheduler'`.

- [ ] **Step 3: Add SublarrScheduler to services/scheduler.py**

Append to `backend/services/scheduler.py`:

```python
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.background import BackgroundScheduler


class SublarrScheduler:
    """Facade wrapping a BackgroundScheduler bound to a SQLAlchemyJobStore."""

    def __init__(self, db_url: str, autostart: bool = True) -> None:
        self._db_url = db_url
        self._autostart = autostart
        self._app: Flask | None = None
        self._scheduler: BackgroundScheduler | None = None
        self._shutting_down = False
        self._registered_ids: set[str] = set()

    @property
    def running(self) -> bool:
        return self._scheduler is not None and self._scheduler.running

    def attach_app(self, app: Flask) -> None:
        self._app = app

    def _ensure_scheduler(self) -> BackgroundScheduler:
        if self._scheduler is None:
            jobstore = SQLAlchemyJobStore(
                url=self._db_url,
                tablename="apscheduler_jobs",
                engine_options={"pool_pre_ping": True},
            )
            self._scheduler = BackgroundScheduler(
                jobstores={"default": jobstore},
                timezone="UTC",
            )
        return self._scheduler

    def start(self) -> None:
        """Idempotent start. Safe to call multiple times; no-op if running.

        Fixes feedback_scheduler_timer_leak by removing the "restart on
        every settings save" behaviour of the legacy threading.Timer
        schedulers.
        """
        if self._app is None:
            raise RuntimeError("attach_app() must be called before start()")
        scheduler = self._ensure_scheduler()
        if scheduler.running:
            return
        scheduler.start()
        logger.info("SublarrScheduler: started (%d job(s) registered)",
                    len(self._registered_ids))

    def shutdown(self, timeout_s: int = 25) -> None:
        """Bounded shutdown. Safe to call multiple times."""
        if self._shutting_down:
            return
        self._shutting_down = True
        scheduler = self._scheduler
        if scheduler is None or not scheduler.running:
            return
        try:
            # APScheduler's shutdown(wait=True) is unbounded; we rely on
            # the executor's own timeout cooperatively by forcing a
            # shutdown on it after timeout_s.
            import threading

            done = threading.Event()

            def _do_shutdown():
                try:
                    scheduler.shutdown(wait=True)
                finally:
                    done.set()

            t = threading.Thread(target=_do_shutdown, name="scheduler-shutdown")
            t.start()
            if not done.wait(timeout=timeout_s):
                logger.warning(
                    "SublarrScheduler: shutdown exceeded %ds; forcing non-wait",
                    timeout_s,
                )
                try:
                    scheduler.shutdown(wait=False)
                except Exception:
                    logger.error("forced shutdown failed", exc_info=True)
        finally:
            logger.info("SublarrScheduler: shut down")

    def register_job(self, spec: JobSpec) -> None:
        """Add a JobSpec to the internal registry.

        Fails fast on duplicate id. Does NOT yet add to the JobStore;
        that happens in start_registered_jobs() (added in a later task).
        """
        if spec.id in self._registered_ids:
            raise ValueError(f"JobSpec id {spec.id!r} already registered")
        self._registered_ids.add(spec.id)
```

- [ ] **Step 4: Run tests**

Run: `cd /d/Sublarr_Projekt/Sublarr/backend && python -m pytest tests/test_scheduler_facade.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/services/scheduler.py backend/tests/test_scheduler_facade.py
git commit -m "feat(phase5): add SublarrScheduler facade with bounded shutdown"
```

---

## Task 7: register_job respects JobStore state + purge_orphans

**Files:**
- Modify: `backend/services/scheduler.py`
- Test: `backend/tests/test_scheduler_facade.py` (extend)

- [ ] **Step 1: Extend the test file**

Append to `backend/tests/test_scheduler_facade.py`:

```python
def test_register_adds_to_jobstore_on_first_run(scheduler):
    spec = JobSpec(
        id="first", func=lambda: None,
        default_trigger=IntervalTrigger(minutes=15),
    )
    scheduler.register_job(spec)
    scheduler.start_registered_jobs()
    scheduler.start()

    job = scheduler._scheduler.get_job("first")
    assert job is not None
    # Interval: 15*60 = 900s
    assert job.trigger.interval.total_seconds() == 900


def test_register_preserves_user_override(scheduler):
    """If JobStore already has a row for the id, start_registered_jobs
    must NOT overwrite it (user edits win)."""
    spec = JobSpec(
        id="user_edited", func=lambda: None,
        default_trigger=IntervalTrigger(minutes=15),
    )
    scheduler.register_job(spec)
    scheduler.start_registered_jobs()
    scheduler.start()

    # Simulate a user edit via reschedule_job
    scheduler._scheduler.reschedule_job(
        "user_edited", trigger=IntervalTrigger(minutes=5),
    )
    scheduler.shutdown(timeout_s=2)

    # Second startup: ensure user's 5-minute interval is preserved
    scheduler._scheduler = None
    scheduler._shutting_down = False
    scheduler._registered_ids.clear()
    scheduler.register_job(spec)
    scheduler.start_registered_jobs()
    scheduler.start()
    job = scheduler._scheduler.get_job("user_edited")
    assert job.trigger.interval.total_seconds() == 300


def test_purge_orphans_deletes_missing_ids(scheduler):
    """JobStore rows whose id is not in the current registry are removed."""
    old = JobSpec(
        id="old_one", func=lambda: None,
        default_trigger=IntervalTrigger(minutes=5),
    )
    scheduler.register_job(old)
    scheduler.start_registered_jobs()
    scheduler.start()
    scheduler.shutdown(timeout_s=2)

    # Second boot: "old_one" is no longer in the registry
    scheduler._scheduler = None
    scheduler._shutting_down = False
    scheduler._registered_ids.clear()

    new = JobSpec(
        id="new_one", func=lambda: None,
        default_trigger=IntervalTrigger(minutes=5),
    )
    scheduler.register_job(new)
    scheduler.start_registered_jobs()
    scheduler.purge_orphans()
    scheduler.start()

    assert scheduler._scheduler.get_job("old_one") is None
    assert scheduler._scheduler.get_job("new_one") is not None


def test_purge_orphans_preserves_registered(scheduler):
    spec = JobSpec(
        id="keep", func=lambda: None,
        default_trigger=IntervalTrigger(minutes=5),
    )
    scheduler.register_job(spec)
    scheduler.start_registered_jobs()
    scheduler.purge_orphans()
    scheduler.start()
    assert scheduler._scheduler.get_job("keep") is not None
```

- [ ] **Step 2: Run tests — expect failures**

Run: `cd /d/Sublarr_Projekt/Sublarr/backend && python -m pytest tests/test_scheduler_facade.py -v`
Expected: 4 new failures with `AttributeError: ... 'start_registered_jobs'` / `'purge_orphans'`.

- [ ] **Step 3: Add methods to SublarrScheduler**

Append to the `SublarrScheduler` class body in `backend/services/scheduler.py`:

```python
    def start_registered_jobs(self) -> None:
        """Walk the registry and add_job() for specs not yet in JobStore.

        Existing JobStore rows (user overrides) are left untouched.
        Must be called after register_job() for all specs and before start().
        """
        if self._app is None:
            raise RuntimeError("attach_app() required before start_registered_jobs()")

        scheduler = self._ensure_scheduler()
        # Internal registry: {id: JobSpec}
        for spec_id in list(self._registered_ids):
            spec = self._spec_by_id(spec_id)
            existing = scheduler.get_job(spec_id)
            if existing is not None:
                continue
            grace = (
                spec.misfire_grace_time
                if spec.misfire_grace_time is not None
                else compute_default_misfire_grace_time(spec.default_trigger)
            )
            scheduler.add_job(
                func=_tick_wrapper(self._app, spec, triggered_by="schedule"),
                trigger=spec.default_trigger,
                id=spec.id,
                replace_existing=False,
                max_instances=spec.max_instances,
                coalesce=spec.coalesce,
                misfire_grace_time=grace,
            )

    def purge_orphans(self) -> None:
        """Remove JobStore rows whose id is not in the current registry.

        Also sweeps stale one-shot rows whose next_run_time is in the past
        (they come from crashed run-now invocations; the scheduler would
        otherwise fire them all at startup).
        """
        scheduler = self._ensure_scheduler()
        for job in list(scheduler.get_jobs()):
            base_id = job.id.split("_oneshot_")[0]
            if base_id not in self._registered_ids:
                scheduler.remove_job(job.id)
                logger.info("purge_orphans: removed %s", job.id)
                continue
            # One-shot with stale next_run_time
            if "_oneshot_" in job.id:
                if job.next_run_time is None or job.next_run_time < datetime.now(UTC):
                    scheduler.remove_job(job.id)
                    logger.info("purge_orphans: removed stale oneshot %s", job.id)
```

And update `register_job` to keep a spec-by-id map (replace the existing `register_job`):

```python
    def __init__(self, db_url: str, autostart: bool = True) -> None:
        self._db_url = db_url
        self._autostart = autostart
        self._app: Flask | None = None
        self._scheduler: BackgroundScheduler | None = None
        self._shutting_down = False
        self._registered_ids: set[str] = set()
        self._specs: dict[str, JobSpec] = {}

    def _spec_by_id(self, spec_id: str) -> JobSpec:
        return self._specs[spec_id]

    def register_job(self, spec: JobSpec) -> None:
        if spec.id in self._registered_ids:
            raise ValueError(f"JobSpec id {spec.id!r} already registered")
        self._registered_ids.add(spec.id)
        self._specs[spec.id] = spec
```

- [ ] **Step 4: Run tests**

Run: `cd /d/Sublarr_Projekt/Sublarr/backend && python -m pytest tests/test_scheduler_facade.py -v`
Expected: 11 passed (7 prior + 4 new).

- [ ] **Step 5: Commit**

```bash
git add backend/services/scheduler.py backend/tests/test_scheduler_facade.py
git commit -m "feat(phase5): register_job preserves user overrides; purge_orphans sweeps registry + stale oneshots"
```

---

## Task 8: Event listeners — executed / error / missed / overlap

**Files:**
- Modify: `backend/services/scheduler.py`
- Test: `backend/tests/test_scheduler_listeners.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_scheduler_listeners.py`:

```python
"""Event listener tests — EVENT_JOB_MISSED / EVENT_JOB_ERROR synthetic rows."""

import time
from datetime import UTC, datetime

import pytest
from apscheduler.events import (
    EVENT_JOB_ERROR,
    EVENT_JOB_MISSED,
    JobExecutionEvent,
    JobSubmissionEvent,
)
from apscheduler.triggers.interval import IntervalTrigger

from services.scheduler import JobSpec, SublarrScheduler


@pytest.fixture
def scheduler(app, tmp_path):
    url = f"sqlite:///{tmp_path / 'aps.db'}"
    s = SublarrScheduler(db_url=url, autostart=False)
    s.attach_app(app)
    yield s
    if s.running:
        s.shutdown(timeout_s=2)


def test_missed_event_writes_missed_row(scheduler, db_session):
    from db.models.scheduler import JobRun

    spec = JobSpec(
        id="j_missed", func=lambda: None,
        default_trigger=IntervalTrigger(seconds=60),
    )
    scheduler.register_job(spec)
    scheduler.start_registered_jobs()
    scheduler.attach_listeners()
    scheduler.start()

    # Fabricate a missed event — APScheduler emits these naturally when
    # misfire_grace_time is exceeded.
    event = JobExecutionEvent(
        code=EVENT_JOB_MISSED,
        job_id="j_missed",
        jobstore="default",
        scheduled_run_time=datetime.now(UTC),
    )
    scheduler._scheduler._dispatch_event(event)
    time.sleep(0.1)

    rows = db_session.query(JobRun).filter_by(job_id="j_missed").all()
    assert len(rows) == 1
    assert rows[0].status == "missed"
    assert rows[0].finished_at is None


def test_max_instances_overlap_writes_skipped_row(scheduler, db_session):
    from apscheduler.executors.base import MaxInstancesReachedError
    from db.models.scheduler import JobRun

    spec = JobSpec(
        id="j_overlap", func=lambda: None,
        default_trigger=IntervalTrigger(seconds=60),
    )
    scheduler.register_job(spec)
    scheduler.start_registered_jobs()
    scheduler.attach_listeners()
    scheduler.start()

    exc = MaxInstancesReachedError("j_overlap")
    event = JobExecutionEvent(
        code=EVENT_JOB_ERROR,
        job_id="j_overlap",
        jobstore="default",
        scheduled_run_time=datetime.now(UTC),
        exception=exc,
    )
    scheduler._scheduler._dispatch_event(event)
    time.sleep(0.1)

    rows = db_session.query(JobRun).filter_by(job_id="j_overlap").all()
    assert len(rows) == 1
    assert rows[0].status == "skipped_overlap"


def test_listener_error_does_not_crash_scheduler(scheduler, caplog):
    """If writing the synthetic row fails, the listener must swallow it."""
    import logging
    from unittest.mock import patch

    spec = JobSpec(
        id="j_err", func=lambda: None,
        default_trigger=IntervalTrigger(seconds=60),
    )
    scheduler.register_job(spec)
    scheduler.start_registered_jobs()
    scheduler.attach_listeners()
    scheduler.start()

    event = JobExecutionEvent(
        code=EVENT_JOB_MISSED,
        job_id="j_err",
        jobstore="default",
        scheduled_run_time=datetime.now(UTC),
    )
    with patch(
        "services.scheduler._write_job_run",
        side_effect=RuntimeError("db down"),
    ):
        with caplog.at_level(logging.ERROR, logger="services.scheduler"):
            scheduler._scheduler._dispatch_event(event)
    assert scheduler.running is True
    assert any("listener failed" in r.message for r in caplog.records)
```

- [ ] **Step 2: Run tests — expect failures**

Run: `cd /d/Sublarr_Projekt/Sublarr/backend && python -m pytest tests/test_scheduler_listeners.py -v`
Expected: FAIL with `AttributeError: ... 'attach_listeners'`.

- [ ] **Step 3: Add attach_listeners to SublarrScheduler**

Append to the `SublarrScheduler` class body in `backend/services/scheduler.py`:

```python
    def attach_listeners(self) -> None:
        """Wire EVENT_JOB_MISSED + EVENT_JOB_ERROR to history writes.

        EVENT_JOB_EXECUTED is NOT wired — _tick_wrapper already writes the
        ok row synchronously. Listening twice would double-write.
        """
        from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_MISSED
        from apscheduler.executors.base import MaxInstancesReachedError

        scheduler = self._ensure_scheduler()

        def _on_missed(event) -> None:
            try:
                _write_job_run(
                    job_id=event.job_id,
                    started_at=event.scheduled_run_time,
                    finished_at=None,
                    status="missed",
                    triggered_by="schedule",
                )
            except Exception:
                logger.error("scheduler: missed-listener failed", exc_info=True)

        def _on_error(event) -> None:
            try:
                exc = event.exception
                if isinstance(exc, MaxInstancesReachedError):
                    _write_job_run(
                        job_id=event.job_id,
                        started_at=event.scheduled_run_time,
                        finished_at=event.scheduled_run_time,
                        status="skipped_overlap",
                        triggered_by="schedule",
                    )
                # Other errors are handled by _tick_wrapper directly;
                # this listener only covers MaxInstancesReachedError.
            except Exception:
                logger.error("scheduler: error-listener failed", exc_info=True)

        scheduler.add_listener(_on_missed, EVENT_JOB_MISSED)
        scheduler.add_listener(_on_error, EVENT_JOB_ERROR)
```

- [ ] **Step 4: Run tests**

Run: `cd /d/Sublarr_Projekt/Sublarr/backend && python -m pytest tests/test_scheduler_listeners.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/services/scheduler.py backend/tests/test_scheduler_listeners.py
git commit -m "feat(phase5): add EVENT_JOB_MISSED + EVENT_JOB_ERROR listeners"
```

---

## Task 9: run_now one-shot + 409-on-duplicate

**Files:**
- Modify: `backend/services/scheduler.py`
- Test: `backend/tests/test_scheduler_facade.py` (extend)

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_scheduler_facade.py`:

```python
def test_run_now_queues_oneshot(scheduler):
    spec = JobSpec(
        id="rn_job", func=lambda: None,
        default_trigger=IntervalTrigger(minutes=15),
    )
    scheduler.register_job(spec)
    scheduler.start_registered_jobs()
    scheduler.start()

    oneshot_id = scheduler.run_now("rn_job")
    assert oneshot_id.startswith("rn_job_oneshot_")
    assert scheduler._scheduler.get_job(oneshot_id) is not None


def test_run_now_duplicate_raises_conflict(scheduler):
    from services.scheduler import OneshotAlreadyPendingError

    spec = JobSpec(
        id="rn_dup", func=lambda: None,
        default_trigger=IntervalTrigger(minutes=15),
    )
    scheduler.register_job(spec)
    scheduler.start_registered_jobs()
    scheduler.start()

    scheduler.run_now("rn_dup")
    with pytest.raises(OneshotAlreadyPendingError):
        scheduler.run_now("rn_dup")


def test_run_now_unknown_id_raises(scheduler):
    from services.scheduler import JobNotRegisteredError

    scheduler.start()
    with pytest.raises(JobNotRegisteredError):
        scheduler.run_now("nope")
```

- [ ] **Step 2: Run tests — expect failure**

Run: `cd /d/Sublarr_Projekt/Sublarr/backend && python -m pytest tests/test_scheduler_facade.py -v`
Expected: 3 new failures.

- [ ] **Step 3: Add run_now + exception classes to services/scheduler.py**

Append to `backend/services/scheduler.py`:

```python
class JobNotRegisteredError(KeyError):
    """Raised when operating on an unknown JobSpec id."""


class OneshotAlreadyPendingError(RuntimeError):
    """Raised by run_now when a prior one-shot for the same job is still pending."""
```

And add to the `SublarrScheduler` class body:

```python
    def run_now(self, job_id: str) -> str:
        """Queue a one-shot immediate fire. Returns the one-shot id.

        Raises:
          JobNotRegisteredError: job_id not in registry
          OneshotAlreadyPendingError: another one-shot is pending/running
        """
        from apscheduler.triggers.date import DateTrigger

        if job_id not in self._registered_ids:
            raise JobNotRegisteredError(job_id)

        scheduler = self._ensure_scheduler()
        prefix = f"{job_id}_oneshot_"
        for j in scheduler.get_jobs():
            if j.id.startswith(prefix):
                raise OneshotAlreadyPendingError(
                    f"{job_id} already has a pending one-shot: {j.id}"
                )

        spec = self._spec_by_id(job_id)
        ts = int(datetime.now(UTC).timestamp())
        oneshot_id = f"{prefix}{ts}"
        scheduler.add_job(
            func=_tick_wrapper(self._app, spec, triggered_by="manual"),
            trigger=DateTrigger(run_date=datetime.now(UTC)),
            id=oneshot_id,
            replace_existing=False,
            max_instances=1,
        )
        return oneshot_id
```

- [ ] **Step 4: Run tests**

Run: `cd /d/Sublarr_Projekt/Sublarr/backend && python -m pytest tests/test_scheduler_facade.py -v`
Expected: 14 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/services/scheduler.py backend/tests/test_scheduler_facade.py
git commit -m "feat(phase5): add run_now with oneshot + duplicate guard"
```

---

## Task 10: reset_to_default + pause + resume + reschedule

**Files:**
- Modify: `backend/services/scheduler.py`
- Test: `backend/tests/test_scheduler_facade.py` (extend)

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_scheduler_facade.py`:

```python
def test_reset_to_default_removes_and_readds(scheduler):
    spec = JobSpec(
        id="rst", func=lambda: None,
        default_trigger=IntervalTrigger(minutes=15),
    )
    scheduler.register_job(spec)
    scheduler.start_registered_jobs()
    scheduler.start()

    scheduler._scheduler.reschedule_job("rst", trigger=IntervalTrigger(minutes=5))
    scheduler.reset_to_default("rst")

    job = scheduler._scheduler.get_job("rst")
    assert job.trigger.interval.total_seconds() == 900  # 15m default back


def test_pause_and_resume(scheduler):
    spec = JobSpec(
        id="pr", func=lambda: None,
        default_trigger=IntervalTrigger(minutes=5),
    )
    scheduler.register_job(spec)
    scheduler.start_registered_jobs()
    scheduler.start()

    scheduler.pause_job("pr")
    assert scheduler._scheduler.get_job("pr").next_run_time is None

    scheduler.resume_job("pr")
    assert scheduler._scheduler.get_job("pr").next_run_time is not None


def test_modify_trigger(scheduler):
    from apscheduler.triggers.cron import CronTrigger

    spec = JobSpec(
        id="mod", func=lambda: None,
        default_trigger=IntervalTrigger(minutes=15),
    )
    scheduler.register_job(spec)
    scheduler.start_registered_jobs()
    scheduler.start()

    new_trigger = CronTrigger(hour=3, minute=0)
    scheduler.modify_trigger("mod", new_trigger)
    job = scheduler._scheduler.get_job("mod")
    assert isinstance(job.trigger, CronTrigger)


def test_pause_unknown_raises(scheduler):
    from services.scheduler import JobNotRegisteredError

    scheduler.start()
    with pytest.raises(JobNotRegisteredError):
        scheduler.pause_job("nope")


def test_trigger_is_default_check(scheduler):
    spec = JobSpec(
        id="deflt", func=lambda: None,
        default_trigger=IntervalTrigger(minutes=15),
    )
    scheduler.register_job(spec)
    scheduler.start_registered_jobs()
    scheduler.start()

    assert scheduler.trigger_is_default("deflt") is True

    scheduler.modify_trigger("deflt", IntervalTrigger(minutes=30))
    assert scheduler.trigger_is_default("deflt") is False

    scheduler.reset_to_default("deflt")
    assert scheduler.trigger_is_default("deflt") is True
```

- [ ] **Step 2: Run tests**

Run: `cd /d/Sublarr_Projekt/Sublarr/backend && python -m pytest tests/test_scheduler_facade.py -v`
Expected: 5 new failures.

- [ ] **Step 3: Add methods to SublarrScheduler**

Append to the `SublarrScheduler` class body:

```python
    def _require_registered(self, job_id: str) -> None:
        if job_id not in self._registered_ids:
            raise JobNotRegisteredError(job_id)

    def reset_to_default(self, job_id: str) -> None:
        """Remove the JobStore row and re-register from code default."""
        self._require_registered(job_id)
        spec = self._spec_by_id(job_id)
        scheduler = self._ensure_scheduler()
        try:
            scheduler.remove_job(job_id)
        except Exception:
            logger.warning("reset_to_default: remove_job miss for %s", job_id)
        grace = (
            spec.misfire_grace_time
            if spec.misfire_grace_time is not None
            else compute_default_misfire_grace_time(spec.default_trigger)
        )
        scheduler.add_job(
            func=_tick_wrapper(self._app, spec, triggered_by="schedule"),
            trigger=spec.default_trigger,
            id=spec.id,
            replace_existing=False,
            max_instances=spec.max_instances,
            coalesce=spec.coalesce,
            misfire_grace_time=grace,
        )

    def pause_job(self, job_id: str) -> None:
        self._require_registered(job_id)
        self._ensure_scheduler().pause_job(job_id)

    def resume_job(self, job_id: str) -> None:
        self._require_registered(job_id)
        self._ensure_scheduler().resume_job(job_id)

    def modify_trigger(self, job_id: str, trigger: BaseTrigger) -> None:
        self._require_registered(job_id)
        self._ensure_scheduler().reschedule_job(job_id, trigger=trigger)

    def trigger_is_default(self, job_id: str) -> bool:
        """Return True iff the current job's trigger matches the spec default.

        Comparison uses repr() — APScheduler's BaseTrigger subclasses define
        __getstate__ but not __eq__, so repr is the stable surrogate.
        """
        self._require_registered(job_id)
        job = self._ensure_scheduler().get_job(job_id)
        if job is None:
            return False
        default = self._spec_by_id(job_id).default_trigger
        return repr(job.trigger) == repr(default)
```

- [ ] **Step 4: Run tests**

Run: `cd /d/Sublarr_Projekt/Sublarr/backend && python -m pytest tests/test_scheduler_facade.py -v`
Expected: 19 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/services/scheduler.py backend/tests/test_scheduler_facade.py
git commit -m "feat(phase5): add pause/resume/modify/reset_to_default with trigger_is_default check"
```

---

## Task 11: Stale-run reconciliation

**Files:**
- Modify: `backend/services/scheduler.py`
- Test: `backend/tests/test_scheduler_startup_reconciliation.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_scheduler_startup_reconciliation.py`:

```python
"""Stale-run reconciliation — abandoned rows after SIGKILL / shutdown timeout."""

from datetime import UTC, datetime, timedelta


def test_abandoned_row_marked_interrupted(app, db_session):
    from db.models.scheduler import JobRun
    from services.scheduler import reconcile_stale_runs

    old = JobRun(
        job_id="x",
        started_at=datetime.now(UTC) - timedelta(hours=1),
        finished_at=None,
        status="ok",  # was set at row-insert time by a buggy path
    )
    db_session.add(old)
    db_session.commit()

    reconcile_stale_runs(grace_minutes=10)

    db_session.expire_all()
    row = db_session.query(JobRun).filter_by(job_id="x").first()
    assert row.status == "error"
    assert row.error_type == "InterruptedByShutdown"
    assert row.finished_at is not None


def test_in_flight_row_not_touched(app, db_session):
    """A row started 30s ago must NOT be marked interrupted."""
    from db.models.scheduler import JobRun
    from services.scheduler import reconcile_stale_runs

    fresh = JobRun(
        job_id="y",
        started_at=datetime.now(UTC) - timedelta(seconds=30),
        finished_at=None,
        status="ok",
    )
    db_session.add(fresh)
    db_session.commit()

    reconcile_stale_runs(grace_minutes=10)

    db_session.expire_all()
    row = db_session.query(JobRun).filter_by(job_id="y").first()
    assert row.status == "ok"  # untouched
    assert row.finished_at is None


def test_finished_row_not_touched(app, db_session):
    from db.models.scheduler import JobRun
    from services.scheduler import reconcile_stale_runs

    done = JobRun(
        job_id="z",
        started_at=datetime.now(UTC) - timedelta(hours=2),
        finished_at=datetime.now(UTC) - timedelta(hours=2),
        status="ok",
    )
    db_session.add(done)
    db_session.commit()

    reconcile_stale_runs(grace_minutes=10)

    db_session.expire_all()
    row = db_session.query(JobRun).filter_by(job_id="z").first()
    assert row.status == "ok"
```

- [ ] **Step 2: Run tests — expect failure**

Run: `cd /d/Sublarr_Projekt/Sublarr/backend && python -m pytest tests/test_scheduler_startup_reconciliation.py -v`
Expected: FAIL with `ImportError: cannot import name 'reconcile_stale_runs'`.

- [ ] **Step 3: Add reconcile_stale_runs function**

Append to `backend/services/scheduler.py`:

```python
def reconcile_stale_runs(grace_minutes: int = 10) -> int:
    """Mark abandoned rows (no finished_at, started_at older than grace) as interrupted.

    Called once at scheduler startup. Returns the number of rows updated.
    """
    from datetime import timedelta

    from extensions import db
    from db.models.scheduler import JobRun

    cutoff = datetime.now(UTC) - timedelta(minutes=grace_minutes)
    now = datetime.now(UTC)

    with db.session.begin():
        stale = (
            db.session.query(JobRun)
            .filter(JobRun.finished_at.is_(None))
            .filter(JobRun.started_at < cutoff)
            .all()
        )
        for row in stale:
            row.status = "error"
            row.error_type = "InterruptedByShutdown"
            row.error_msg = (
                f"Row abandoned without finished_at after {grace_minutes}m grace; "
                "likely SIGKILL or shutdown-timeout."
            )
            row.finished_at = now
            row.duration_ms = int((now - row.started_at).total_seconds() * 1000)

    if stale:
        logger.warning(
            "scheduler: reconciled %d abandoned job_run rows", len(stale)
        )
    return len(stale)
```

- [ ] **Step 4: Run tests**

Run: `cd /d/Sublarr_Projekt/Sublarr/backend && python -m pytest tests/test_scheduler_startup_reconciliation.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/services/scheduler.py backend/tests/test_scheduler_startup_reconciliation.py
git commit -m "feat(phase5): add stale-run reconciliation on startup"
```

---

## Task 12: Retention cleanup + config field

**Files:**
- Create: `backend/utils/scheduler_retention.py`
- Modify: `backend/config_settings.py`
- Test: `backend/tests/test_scheduler_retention.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_scheduler_retention.py`:

```python
"""Retention cleanup — delete_old_job_runs."""

from datetime import UTC, datetime, timedelta


def test_deletes_rows_older_than_retention(app, db_session):
    from db.models.scheduler import JobRun
    from utils.scheduler_retention import delete_old_job_runs

    old = JobRun(
        job_id="x",
        started_at=datetime.now(UTC) - timedelta(days=60),
        finished_at=datetime.now(UTC) - timedelta(days=60),
        status="ok",
    )
    fresh = JobRun(
        job_id="x",
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
        status="ok",
    )
    db_session.add_all([old, fresh])
    db_session.commit()

    deleted = delete_old_job_runs(retention_days=30)
    assert deleted == 1

    remaining = db_session.query(JobRun).filter_by(job_id="x").all()
    assert len(remaining) == 1


def test_idempotent_on_empty(app):
    from utils.scheduler_retention import delete_old_job_runs

    assert delete_old_job_runs(retention_days=30) == 0
    assert delete_old_job_runs(retention_days=30) == 0


def test_reads_retention_from_settings_when_none(app, monkeypatch):
    from config import get_settings
    from utils.scheduler_retention import delete_old_job_runs

    s = get_settings()
    monkeypatch.setattr(s, "scheduler_history_retention_days", 7)

    # smoke — no exceptions; actual deletion behaviour tested above.
    delete_old_job_runs()
```

- [ ] **Step 2: Run tests — expect failure**

Run: `cd /d/Sublarr_Projekt/Sublarr/backend && python -m pytest tests/test_scheduler_retention.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'utils.scheduler_retention'`.

- [ ] **Step 3: Add config field**

Edit `backend/config_settings.py`. Find a reasonable grouping (near other `scheduler_*` fields or in a miscellaneous block) and insert:

```python
scheduler_history_retention_days: int = Field(
    default=30, ge=1, le=365,
    description="Keep scheduler job-run history for this many days before "
                "the scheduler_history_cleanup cron deletes old rows.",
)
```

- [ ] **Step 4: Create the retention utility**

Create `backend/utils/scheduler_retention.py`:

```python
"""Scheduler history retention cleanup.

Registered as the ``scheduler_history_cleanup`` JobSpec. Reads
``settings.scheduler_history_retention_days`` at tick time so
runtime settings changes take effect on next fire without restart.
"""

import logging
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa

from config import get_settings
from db.models.scheduler import JobRun
from extensions import db

logger = logging.getLogger(__name__)


def delete_old_job_runs(retention_days: int | None = None) -> int:
    """Delete scheduler_job_runs rows older than retention_days.

    Returns the number of rows deleted.
    """
    if retention_days is None:
        retention_days = getattr(
            get_settings(), "scheduler_history_retention_days", 30
        )
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    with db.session.begin():
        deleted = db.session.execute(
            sa.delete(JobRun).where(JobRun.started_at < cutoff)
        ).rowcount
    logger.info(
        "scheduler_history_cleanup: deleted %d rows older than %s",
        deleted, cutoff,
    )
    return deleted or 0
```

- [ ] **Step 5: Run tests**

Run: `cd /d/Sublarr_Projekt/Sublarr/backend && python -m pytest tests/test_scheduler_retention.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/utils/scheduler_retention.py backend/config_settings.py backend/tests/test_scheduler_retention.py
git commit -m "feat(phase5): add scheduler_history_retention_days setting + delete_old_job_runs"
```

---

## Task 13: Single-instance guard + startup wiring (SUBLARR_SCHEDULER_ROLE)

**Files:**
- Modify: `backend/services/scheduler.py`
- Modify: `backend/app_schedulers.py`
- Test: `backend/tests/test_scheduler_second_instance_guard.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_scheduler_second_instance_guard.py`:

```python
"""SUBLARR_SCHEDULER_ROLE env var guard."""

import logging

import pytest


def test_role_primary_starts_scheduler(monkeypatch, caplog):
    from services.scheduler import bootstrap_scheduler

    monkeypatch.setenv("SUBLARR_SCHEDULER_ROLE", "primary")

    from app import create_app
    app = create_app(testing=True)
    with caplog.at_level(logging.INFO, logger="services.scheduler"):
        s = bootstrap_scheduler(app)
    assert s is not None
    assert s.running is True
    s.shutdown(timeout_s=2)


def test_role_disabled_skips_scheduler(monkeypatch, caplog):
    from services.scheduler import bootstrap_scheduler

    monkeypatch.setenv("SUBLARR_SCHEDULER_ROLE", "disabled")

    from app import create_app
    app = create_app(testing=True)
    with caplog.at_level(logging.INFO, logger="services.scheduler"):
        s = bootstrap_scheduler(app)
    assert s is None
    assert any(
        "skipping scheduler" in r.message.lower() for r in caplog.records
    )


def test_role_default_is_primary(monkeypatch):
    from services.scheduler import bootstrap_scheduler

    monkeypatch.delenv("SUBLARR_SCHEDULER_ROLE", raising=False)

    from app import create_app
    app = create_app(testing=True)
    s = bootstrap_scheduler(app)
    assert s is not None
    s.shutdown(timeout_s=2)


def test_role_invalid_raises(monkeypatch):
    from services.scheduler import bootstrap_scheduler

    monkeypatch.setenv("SUBLARR_SCHEDULER_ROLE", "garbage")

    from app import create_app
    app = create_app(testing=True)
    with pytest.raises(ValueError, match="SUBLARR_SCHEDULER_ROLE"):
        bootstrap_scheduler(app)
```

- [ ] **Step 2: Run tests — expect failure**

Run: `cd /d/Sublarr_Projekt/Sublarr/backend && python -m pytest tests/test_scheduler_second_instance_guard.py -v`
Expected: FAIL with `ImportError: cannot import name 'bootstrap_scheduler'`.

- [ ] **Step 3: Add bootstrap_scheduler + SCHEDULED_JOBS placeholder**

Append to `backend/services/scheduler.py`:

```python
import os

_VALID_ROLES = {"primary", "disabled"}

# Phase-1 placeholder. Populated with real JobSpecs during Phase 4
# (one per retiring Timer site). scheduler_history_cleanup is the
# only real job this phase registers.
SCHEDULED_JOBS: list[JobSpec] = []


def _build_default_jobs() -> list[JobSpec]:
    """Build the canonical JobSpec list. Imports are lazy to avoid
    import-time cycles against modules that themselves import scheduler."""
    from utils.scheduler_retention import delete_old_job_runs

    return [
        JobSpec(
            id="scheduler_history_cleanup",
            func=delete_old_job_runs,
            default_trigger=CronTrigger(hour=3, minute=15),
            timeout_s=60,
            owner_module="services.scheduler",
            description="Delete old scheduler_job_runs rows per retention policy.",
        ),
    ]


def bootstrap_scheduler(app: Flask) -> SublarrScheduler | None:
    """Full startup: honour SUBLARR_SCHEDULER_ROLE env, reconcile,
    register jobs, start.

    Returns the scheduler instance or None if this replica is disabled.
    """
    role = os.environ.get("SUBLARR_SCHEDULER_ROLE", "primary").strip().lower()
    if role not in _VALID_ROLES:
        raise ValueError(
            f"SUBLARR_SCHEDULER_ROLE={role!r} is invalid; "
            f"expected one of {sorted(_VALID_ROLES)}"
        )
    if role == "disabled":
        logger.info(
            "SUBLARR_SCHEDULER_ROLE=disabled — skipping scheduler on this replica"
        )
        return None

    db_url = app.config["SQLALCHEMY_DATABASE_URI"]
    s = SublarrScheduler(db_url=db_url, autostart=False)
    s.attach_app(app)

    reconcile_stale_runs(grace_minutes=10)

    global SCHEDULED_JOBS
    if not SCHEDULED_JOBS:
        SCHEDULED_JOBS = _build_default_jobs()
    for spec in SCHEDULED_JOBS:
        s.register_job(spec)

    s.start_registered_jobs()
    s.purge_orphans()
    s.attach_listeners()
    s.start()
    app.extensions["scheduler"] = s
    return s
```

- [ ] **Step 4: Run tests**

Run: `cd /d/Sublarr_Projekt/Sublarr/backend && python -m pytest tests/test_scheduler_second_instance_guard.py -v`
Expected: 4 passed.

- [ ] **Step 5: Wire into app_schedulers.py**

Read `backend/app_schedulers.py` first. Find the function that `create_app` calls after DB init (likely `_start_schedulers(app)` or similar). Add this near the end of that function:

```python
    from services.scheduler import bootstrap_scheduler

    try:
        bootstrap_scheduler(app)
    except Exception:
        logger.error("scheduler: bootstrap failed", exc_info=True)
        app.extensions["scheduler"] = None
```

- [ ] **Step 6: Smoke-test full app startup**

Run: `cd /d/Sublarr_Projekt/Sublarr/backend && SUBLARR_SCHEDULER_ROLE=primary python -c "from app import create_app; app = create_app(); print('scheduler:', app.extensions.get('scheduler'))"`
Expected: prints `scheduler: <services.scheduler.SublarrScheduler object at …>`.

- [ ] **Step 7: Commit**

```bash
git add backend/services/scheduler.py backend/app_schedulers.py backend/tests/test_scheduler_second_instance_guard.py
git commit -m "feat(phase5): wire bootstrap_scheduler into create_app with SUBLARR_SCHEDULER_ROLE gate"
```

---

## Task 14: Bounded shutdown wiring

**Files:**
- Modify: `backend/app_shutdown.py`

- [ ] **Step 1: Read the existing shutdown file**

Run: `cd /d/Sublarr_Projekt/Sublarr/backend && python -c "import inspect, app_shutdown; print(inspect.getsource(app_shutdown))" | head -80`
Note which function is registered as the atexit / signal handler.

- [ ] **Step 2: Add scheduler shutdown to the existing handler**

In `backend/app_shutdown.py`, locate the main shutdown function (likely `_shutdown_handlers(app)` or similar). Add this block **before** the DB-pool-close step:

```python
    scheduler = app.extensions.get("scheduler")
    if scheduler is not None:
        try:
            scheduler.shutdown(timeout_s=25)
        except Exception:
            logger.error("scheduler: shutdown raised", exc_info=True)
```

- [ ] **Step 3: Smoke test**

Run: `cd /d/Sublarr_Projekt/Sublarr/backend && python -c "
from app import create_app
from app_shutdown import _shutdown_handlers
app = create_app()
# Simulate shutdown
import atexit
# Call any exit handlers that were registered — scheduler should shut down cleanly
print('running:', app.extensions['scheduler'].running)
app.extensions['scheduler'].shutdown(timeout_s=5)
print('after shutdown:', app.extensions['scheduler'].running)
"`
Expected: `running: True` then `after shutdown: False`.

- [ ] **Step 4: Commit**

```bash
git add backend/app_shutdown.py
git commit -m "feat(phase5): bounded scheduler shutdown in app_shutdown"
```

---

## Task 15: Prometheus metrics

**Files:**
- Modify: `backend/services/scheduler.py` (add metric emit in tick wrapper + listeners)
- Modify: `backend/monitoring/metrics.py` (declare counters / histogram)
- Test: extend `backend/tests/test_scheduler_tick_wrapper.py`

- [ ] **Step 1: Write failing metric tests**

Append to `backend/tests/test_scheduler_tick_wrapper.py`:

```python
def test_prometheus_counter_incremented_on_ok(flask_app, db_session):
    from monitoring.metrics import scheduler_job_runs_total

    before = scheduler_job_runs_total.labels(job_id="test_job", status="ok")._value.get()
    spec = JobSpec(
        id="test_job", func=lambda: None,
        default_trigger=IntervalTrigger(seconds=60),
    )
    _tick_wrapper(flask_app, spec, triggered_by="schedule")()
    after = scheduler_job_runs_total.labels(job_id="test_job", status="ok")._value.get()
    assert after == before + 1


def test_prometheus_counter_incremented_on_error(flask_app, db_session):
    from monitoring.metrics import scheduler_job_runs_total

    def boom():
        raise RuntimeError("x")

    before = scheduler_job_runs_total.labels(job_id="test_job", status="error")._value.get()
    spec = JobSpec(
        id="test_job", func=boom,
        default_trigger=IntervalTrigger(seconds=60),
    )
    _tick_wrapper(flask_app, spec, triggered_by="schedule")()
    after = scheduler_job_runs_total.labels(job_id="test_job", status="error")._value.get()
    assert after == before + 1


def test_prometheus_histogram_observed(flask_app, db_session):
    from monitoring.metrics import scheduler_job_duration_seconds

    h = scheduler_job_duration_seconds.labels(job_id="test_job")
    before_count = h._sum.get()  # sum of observations
    spec = JobSpec(
        id="test_job", func=lambda: None,
        default_trigger=IntervalTrigger(seconds=60),
    )
    _tick_wrapper(flask_app, spec, triggered_by="schedule")()
    after_count = h._sum.get()
    assert after_count > before_count
```

- [ ] **Step 2: Add metrics**

Open `backend/monitoring/metrics.py`. Add (or create the file if missing):

```python
from prometheus_client import Counter, Histogram

scheduler_job_runs_total = Counter(
    "scheduler_job_runs_total",
    "Total scheduler job executions by id and final status.",
    labelnames=["job_id", "status"],
)

scheduler_job_duration_seconds = Histogram(
    "scheduler_job_duration_seconds",
    "Scheduler job execution duration in seconds.",
    labelnames=["job_id"],
    buckets=(0.1, 0.5, 1, 5, 10, 30, 60, 120, 300, 600, 1800, 3600),
)

scheduler_interrupted_runs_total = Counter(
    "scheduler_interrupted_runs_total",
    "Rows reconciled as InterruptedByShutdown at startup (SIGKILL indicator).",
)
```

- [ ] **Step 3: Emit metrics from _tick_wrapper**

In `backend/services/scheduler.py`, modify the `finally` branch of `_tick_wrapper._runner`:

```python
            finally:
                finished_at = datetime.now(UTC)
                duration_s = (finished_at - started_at).total_seconds()
                try:
                    from monitoring.metrics import (
                        scheduler_job_duration_seconds,
                        scheduler_job_runs_total,
                    )
                    scheduler_job_runs_total.labels(
                        job_id=spec.id, status=status
                    ).inc()
                    scheduler_job_duration_seconds.labels(job_id=spec.id).observe(
                        duration_s
                    )
                except Exception:
                    logger.warning("scheduler: metrics emit failed", exc_info=True)
                _write_job_run(
                    job_id=spec.id,
                    started_at=started_at,
                    finished_at=finished_at,
                    status=status,
                    triggered_by=triggered_by,
                    error_type=error_type,
                    error_msg=error_msg,
                )
```

- [ ] **Step 4: Emit metric in reconcile_stale_runs**

In `backend/services/scheduler.py`, update `reconcile_stale_runs` to increment the counter:

```python
    if stale:
        logger.warning(
            "scheduler: reconciled %d abandoned job_run rows", len(stale)
        )
        try:
            from monitoring.metrics import scheduler_interrupted_runs_total
            scheduler_interrupted_runs_total.inc(len(stale))
        except Exception:
            pass
```

- [ ] **Step 5: Run tests**

Run: `cd /d/Sublarr_Projekt/Sublarr/backend && python -m pytest tests/test_scheduler_tick_wrapper.py -v`
Expected: 9 passed (6 prior + 3 new).

- [ ] **Step 6: Commit**

```bash
git add backend/services/scheduler.py backend/monitoring/metrics.py backend/tests/test_scheduler_tick_wrapper.py
git commit -m "feat(phase5): emit Prometheus counters + histogram for scheduler runs"
```

---

## Task 16: Smoke test the entire Phase 1 stack end-to-end

**Files:**
- Test: `backend/tests/test_scheduler_smoke.py`

- [ ] **Step 1: Write the smoke test**

Create `backend/tests/test_scheduler_smoke.py`:

```python
"""Phase 1 smoke test — full bootstrap_scheduler stack."""

import time


def test_full_bootstrap_and_history_write(monkeypatch, tmp_path):
    """bootstrap_scheduler registers scheduler_history_cleanup; run-now it
    and verify a row is written."""
    monkeypatch.setenv("SUBLARR_SCHEDULER_ROLE", "primary")

    from app import create_app

    app = create_app(testing=True)
    try:
        from db.models.scheduler import JobRun
        from extensions import db

        scheduler = app.extensions.get("scheduler")
        assert scheduler is not None
        assert scheduler.running is True

        with app.app_context():
            db.session.query(JobRun).delete()
            db.session.commit()

        oneshot_id = scheduler.run_now("scheduler_history_cleanup")
        assert oneshot_id.startswith("scheduler_history_cleanup_oneshot_")

        # Wait up to 5s for the one-shot to execute
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            with app.app_context():
                n = db.session.query(JobRun).count()
            if n > 0:
                break
            time.sleep(0.1)

        with app.app_context():
            rows = db.session.query(JobRun).all()
        assert len(rows) >= 1
        assert rows[0].job_id == "scheduler_history_cleanup"
        assert rows[0].triggered_by == "manual"
    finally:
        if app.extensions.get("scheduler"):
            app.extensions["scheduler"].shutdown(timeout_s=2)
```

- [ ] **Step 2: Run the smoke test**

Run: `cd /d/Sublarr_Projekt/Sublarr/backend && python -m pytest tests/test_scheduler_smoke.py -v`
Expected: 1 passed.

- [ ] **Step 3: Run the full scheduler test suite**

Run: `cd /d/Sublarr_Projekt/Sublarr/backend && python -m pytest tests/test_scheduler_*.py -v`
Expected: all tests pass. Count baseline for regression tracking.

- [ ] **Step 4: Run the full backend test suite to check for regressions**

Run: `cd /d/Sublarr_Projekt/Sublarr/backend && python -m pytest --tb=short -q --ignore=tests/performance`
Expected: no new failures compared to master.

- [ ] **Step 5: Ruff + format check**

Run: `cd /d/Sublarr_Projekt/Sublarr/backend && ruff check . && ruff format --check .`
Expected: both pass.

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_scheduler_smoke.py
git commit -m "test(phase5): smoke test for full scheduler bootstrap + run-now"
```

---

## Phase 1 acceptance checklist

- [ ] `APScheduler>=3.10,<4` pinned in `requirements.txt`
- [ ] `scheduler_job_runs` + `apscheduler_jobs` tables exist in dev DB
- [ ] `SublarrScheduler` facade with lifecycle + job registry + orphan purge + run_now + pause/resume/modify/reset
- [ ] `_tick_wrapper` covers app_context + timeout + error capture + history write
- [ ] Listeners cover EVENT_JOB_MISSED + MaxInstancesReachedError
- [ ] `bootstrap_scheduler()` honours `SUBLARR_SCHEDULER_ROLE` env
- [ ] Stale-run reconciliation runs on startup
- [ ] `scheduler_history_cleanup` JobSpec registered and ticks at 03:15 UTC
- [ ] Prometheus counters + histogram exposed
- [ ] Shutdown bounded at 25s via `app_shutdown.py`
- [ ] All Phase 1 tests green
- [ ] Full backend suite has no regressions
- [ ] Ruff clean

---

## Phase 2 preview (separate plan file)

Phase 2 adds the API blueprint (`routes/system/scheduler.py`) and the frontend read-only SchedulerPage. Phase 1 ships independently — the scheduler runs, writes history, emits metrics, but isn't yet visible to the user.

## Self-review notes (writing-plans)

- Spec coverage: All Section 1–3 + 6–7 items of the spec are covered by Tasks 1–16. Section 4 (API) and Section 5 (UI) deferred to Phase 2/3 plans.
- No placeholders: every step has runnable code or exact commands. `<CURRENT_HEAD>` in Task 3 is an operator lookup, not a plan-writer placeholder.
- Type consistency: `JobSpec` fields (`id`, `func`, `default_trigger`, `timeout_s`, `max_instances`, `coalesce`, `misfire_grace_time`, `owner_module`, `description`) are consistent across Tasks 4, 7, 9, 10, 13.
- Function names stable: `_tick_wrapper`, `_write_job_run`, `bootstrap_scheduler`, `reconcile_stale_runs`, `delete_old_job_runs`, `compute_default_misfire_grace_time`, `SublarrScheduler.{start, shutdown, register_job, start_registered_jobs, purge_orphans, run_now, pause_job, resume_job, modify_trigger, reset_to_default, trigger_is_default, attach_listeners, attach_app, _require_registered, _spec_by_id, _ensure_scheduler}`.
- Exception classes: `JobNotRegisteredError`, `OneshotAlreadyPendingError` introduced in Task 9; used in Task 10 tests.
