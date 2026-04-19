# Plan B / Phase B7 — Multi-Engine Sync Orchestrator

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Spec:** `docs/superpowers/specs/2026-04-19-plan-b-subtitle-delivery-quality-design.md`
**Prior:** B6 shipped as 0.69.0-beta — post-processing pipeline.

**Goal:** Replace ad-hoc `sync_with_ffsubsync` / `sync_with_alass` functions with a named-class `BaseSyncEngine` pattern behind a `SyncOrchestrator` that owns an ordered fallback chain with per-engine timeout + sanity threshold + audit trail.

**Scope deviation from spec:** The spec listed 4 engines (ffsubsync, alass, nanosync, oai-sync). `nanosync` and `oai-sync` (LLM-assisted) require research-grade algorithm development and new dependencies. B7 ships the architecture + 2 real engines (ffsubsync, alass). Future phases can drop in new engines without changing the orchestrator.

**Architecture:** New `backend/services/sync_engines/` package with `BaseSyncEngine` ABC + `SyncResult` dataclass + one file per engine. `SyncOrchestrator` in `backend/services/video_sync.py` iterates the configured engine chain, early-exits on success within sanity threshold, falls through on timeout/exception/insanity. New `sync_job_runs` table audits every engine attempt (engine, offset_ms, status, duration_ms, subtitle_id, created_at). Existing `sync_with_ffsubsync` / `sync_with_alass` remain as thin wrappers for backward-compatibility with any external callers.

**Baseline:** 0.69.0-beta → 0.70.0-beta (final Plan B minor bump).

---

## File Structure

### Create
- `backend/services/sync_engines/__init__.py` — package root + engine registry
- `backend/services/sync_engines/base.py` — `BaseSyncEngine` ABC + `SyncResult` + `EngineUnavailableError` + `SanityRejectError`
- `backend/services/sync_engines/ffsubsync_engine.py` — refactored ffsubsync logic
- `backend/services/sync_engines/alass_engine.py` — refactored alass logic
- `backend/services/sync_engines/orchestrator.py` — `SyncOrchestrator` with fallback chain
- `backend/services/sync_engines/events.py` — audit writer for `sync_job_runs`
- `backend/db/migrations/versions/2026_04_19_XXXX-<rev>_add_sync_job_runs.py`
- `backend/routes/sync_engines.py` — `/api/v1/sync/engines` + `/api/v1/sync/runs` endpoints
- `backend/tests/test_sync_engines_*.py` — per-engine + orchestrator + API tests
- `frontend/src/pages/Settings/SyncEnginesTab.tsx` — engine chain config UI

### Modify
- `backend/db/models/core.py` — add `SyncJobRun` ORM model
- `backend/services/video_sync.py` — `sync_with_ffsubsync` / `sync_with_alass` become thin wrappers; `SyncOrchestrator` becomes the canonical entry point

---

## Task 1: Alembic migration + `SyncJobRun` ORM model

- [ ] **Step 1: Find alembic head**

Run: `cd backend && python -m alembic heads` — record as `<PRIOR_HEAD>`. STOP if multiple heads.

- [ ] **Step 2: Generate revision hash**

`cd backend && python -c "import secrets; print(secrets.token_hex(6))"` — record as `<NEW_REV>`.

- [ ] **Step 3: Write migration**

Create `backend/db/migrations/versions/2026_04_19_XXXX-<NEW_REV>_add_sync_job_runs.py`:

```python
"""add sync_job_runs table

Revision ID: <NEW_REV>
Revises: <PRIOR_HEAD>
Create Date: 2026-04-19 HH:MM:SS
"""

from alembic import op
import sqlalchemy as sa

revision = "<NEW_REV>"
down_revision = "<PRIOR_HEAD>"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sync_job_runs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("engine", sa.String(length=32), nullable=False),
        sa.Column("offset_ms", sa.Integer, nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("duration_ms", sa.Integer, nullable=False),
        sa.Column("subtitle_path", sa.Text, nullable=True),
        sa.Column("video_path", sa.Text, nullable=True),
        sa.Column("reason", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("idx_sync_runs_created_at", "sync_job_runs", ["created_at"])
    op.create_index("idx_sync_runs_engine", "sync_job_runs", ["engine"])


def downgrade() -> None:
    op.drop_index("idx_sync_runs_engine", table_name="sync_job_runs")
    op.drop_index("idx_sync_runs_created_at", table_name="sync_job_runs")
    op.drop_table("sync_job_runs")
```

- [ ] **Step 4: Migration roundtrip**

`cd backend && python -m alembic upgrade head && python -m alembic downgrade -1 && python -m alembic upgrade head` — all must exit 0.

- [ ] **Step 5: Add ORM model**

Append to `backend/db/models/core.py`:

```python
class SyncJobRun(db.Model):
    """Audit row for one sync engine attempt."""

    __tablename__ = "sync_job_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    engine: Mapped[str] = mapped_column(String(32), nullable=False)
    offset_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    subtitle_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    video_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
```

- [ ] **Step 6: Test + commit**

Create `backend/tests/test_sync_job_run_model.py` with a simple attribute-existence test (copy B6's `test_post_processing_model.py` pattern).

Run: `cd backend && python -m pytest tests/test_sync_job_run_model.py -v`
Expected: PASS.

```bash
git add backend/db/migrations/versions/2026_04_19_*_add_sync_job_runs.py backend/db/models/core.py backend/tests/test_sync_job_run_model.py
git commit -m "feat(plan-b7): alembic + ORM — sync_job_runs table"
```

---

## Task 2: `BaseSyncEngine` ABC + `SyncOrchestrator` + audit writer

**Files:** `backend/services/sync_engines/__init__.py`, `base.py`, `orchestrator.py`, `events.py`, `backend/tests/test_sync_orchestrator.py`.

- [ ] **Step 1: Failing test**

```python
# backend/tests/test_sync_orchestrator.py
"""Plan B7 — orchestrator fallback chain tests."""

import pytest


def test_base_sync_engine_abc():
    from services.sync_engines.base import BaseSyncEngine, SyncResult

    with pytest.raises(TypeError):
        BaseSyncEngine()

    r = SyncResult(engine="x", ok=True, offset_ms=42, duration_ms=5, output_path="/o.srt")
    assert r.ok


def test_orchestrator_fires_engines_in_order_and_exits_on_first_success():
    from unittest.mock import MagicMock

    from services.sync_engines.base import SyncResult
    from services.sync_engines.orchestrator import SyncOrchestrator

    engine_a = MagicMock()
    engine_a.name = "a"
    engine_a.is_available.return_value = True
    engine_a.sync.return_value = SyncResult(engine="a", ok=True, offset_ms=20, duration_ms=5, output_path="/o.srt")

    engine_b = MagicMock()
    engine_b.name = "b"
    engine_b.is_available.return_value = True

    orch = SyncOrchestrator(engines=[engine_a, engine_b], sanity_threshold_ms=60_000)
    result = orch.sync(subtitle_path="/s.srt", video_path="/v.mkv")

    assert result.ok
    assert result.engine == "a"
    # b must NOT be called because a succeeded
    engine_b.sync.assert_not_called()


def test_orchestrator_falls_through_on_exception():
    from unittest.mock import MagicMock

    from services.sync_engines.base import SyncResult
    from services.sync_engines.orchestrator import SyncOrchestrator

    engine_a = MagicMock()
    engine_a.name = "a"
    engine_a.is_available.return_value = True
    engine_a.sync.side_effect = RuntimeError("boom")

    engine_b = MagicMock()
    engine_b.name = "b"
    engine_b.is_available.return_value = True
    engine_b.sync.return_value = SyncResult(engine="b", ok=True, offset_ms=0, duration_ms=3, output_path="/o.srt")

    orch = SyncOrchestrator(engines=[engine_a, engine_b], sanity_threshold_ms=60_000)
    result = orch.sync(subtitle_path="/s.srt", video_path="/v.mkv")

    assert result.ok
    assert result.engine == "b"
    engine_a.sync.assert_called_once()
    engine_b.sync.assert_called_once()


def test_orchestrator_rejects_insane_offset_and_falls_through():
    """Engine returns a huge offset beyond sanity threshold — orchestrator treats it as failure."""
    from unittest.mock import MagicMock

    from services.sync_engines.base import SyncResult
    from services.sync_engines.orchestrator import SyncOrchestrator

    engine_a = MagicMock()
    engine_a.name = "a"
    engine_a.is_available.return_value = True
    engine_a.sync.return_value = SyncResult(engine="a", ok=True, offset_ms=500_000, duration_ms=5, output_path="/o.srt")

    engine_b = MagicMock()
    engine_b.name = "b"
    engine_b.is_available.return_value = True
    engine_b.sync.return_value = SyncResult(engine="b", ok=True, offset_ms=50, duration_ms=5, output_path="/o.srt")

    orch = SyncOrchestrator(engines=[engine_a, engine_b], sanity_threshold_ms=60_000)
    result = orch.sync(subtitle_path="/s.srt", video_path="/v.mkv")

    assert result.ok
    assert result.engine == "b"


def test_orchestrator_skips_unavailable_engines():
    from unittest.mock import MagicMock

    from services.sync_engines.base import SyncResult
    from services.sync_engines.orchestrator import SyncOrchestrator

    engine_a = MagicMock()
    engine_a.name = "a"
    engine_a.is_available.return_value = False  # Not installed

    engine_b = MagicMock()
    engine_b.name = "b"
    engine_b.is_available.return_value = True
    engine_b.sync.return_value = SyncResult(engine="b", ok=True, offset_ms=10, duration_ms=3, output_path="/o.srt")

    orch = SyncOrchestrator(engines=[engine_a, engine_b], sanity_threshold_ms=60_000)
    result = orch.sync(subtitle_path="/s.srt", video_path="/v.mkv")

    assert result.ok
    assert result.engine == "b"
    engine_a.sync.assert_not_called()


def test_orchestrator_returns_failure_when_all_engines_fail():
    from unittest.mock import MagicMock

    from services.sync_engines.orchestrator import SyncOrchestrator

    engine_a = MagicMock()
    engine_a.name = "a"
    engine_a.is_available.return_value = True
    engine_a.sync.side_effect = RuntimeError("boom")

    engine_b = MagicMock()
    engine_b.name = "b"
    engine_b.is_available.return_value = True
    engine_b.sync.side_effect = RuntimeError("also broke")

    orch = SyncOrchestrator(engines=[engine_a, engine_b], sanity_threshold_ms=60_000)
    result = orch.sync(subtitle_path="/s.srt", video_path="/v.mkv")

    assert result.ok is False
    assert result.engine in {"a", "b", "none"}
```

- [ ] **Step 2: Implement the package**

`backend/services/sync_engines/__init__.py`:

```python
"""Multi-engine subtitle sync orchestrator package."""

from services.sync_engines.base import BaseSyncEngine, SyncResult  # noqa: F401
from services.sync_engines.orchestrator import SyncOrchestrator, get_default_orchestrator  # noqa: F401
```

`backend/services/sync_engines/base.py`:

```python
"""Base class + result dataclass for sync engines."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import ClassVar


@dataclass
class SyncResult:
    """Outcome of one sync engine attempt."""

    engine: str
    ok: bool
    offset_ms: int
    duration_ms: int
    output_path: str = ""
    reason: str = ""
    extra: dict = field(default_factory=dict)


class EngineUnavailableError(Exception):
    """Raised when the engine's CLI/module isn't installed."""


class BaseSyncEngine(ABC):
    """Base class for a subtitle sync engine."""

    name: ClassVar[str] = ""
    timeout_s: ClassVar[int] = 600

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if the engine can run (CLI installed, deps present)."""

    @abstractmethod
    def sync(self, subtitle_path: str, video_path: str) -> SyncResult:
        """Run the sync. Returns a SyncResult (ok=False on caught errors).

        May raise on truly unexpected failures — orchestrator catches those.
        """
```

`backend/services/sync_engines/events.py`:

```python
"""Audit-row writer for sync_job_runs."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def write_sync_job_run(
    engine: str,
    status: str,
    offset_ms: int | None,
    duration_ms: int,
    subtitle_path: str,
    video_path: str,
    reason: str = "",
) -> None:
    """Insert one audit row. Never raises."""
    try:
        from extensions import db
        from db.models.core import SyncJobRun

        row = SyncJobRun(
            engine=engine,
            status=status,
            offset_ms=offset_ms,
            duration_ms=duration_ms,
            subtitle_path=subtitle_path,
            video_path=video_path,
            reason=reason[:64] if reason else None,
            created_at=datetime.now(timezone.utc),
        )
        db.session.add(row)
        db.session.commit()
    except Exception as e:
        logger.warning("sync_job_runs audit write failed: %s", e)
```

`backend/services/sync_engines/orchestrator.py`:

```python
"""SyncOrchestrator — iterate configured engine chain with fallback + audit."""

from __future__ import annotations

import logging
import time

from services.sync_engines.base import BaseSyncEngine, SyncResult
from services.sync_engines.events import write_sync_job_run

logger = logging.getLogger(__name__)


class SyncOrchestrator:
    """Runs a sequence of engines, early-exiting on the first sane success.

    An engine's result is rejected (fall-through) if:
      - is_available() returns False
      - sync() raises
      - abs(offset_ms) exceeds sanity_threshold_ms
    """

    def __init__(self, engines: list[BaseSyncEngine], sanity_threshold_ms: int = 60_000):
        self.engines = engines
        self.sanity_threshold_ms = sanity_threshold_ms

    def sync(self, subtitle_path: str, video_path: str) -> SyncResult:
        last_reason = ""
        last_engine = "none"

        for engine in self.engines:
            name = getattr(engine, "name", engine.__class__.__name__)
            start = time.monotonic()

            if not engine.is_available():
                logger.debug("sync engine %s unavailable, skipping", name)
                last_engine = name
                last_reason = "unavailable"
                write_sync_job_run(
                    engine=name, status="skipped", offset_ms=None,
                    duration_ms=0, subtitle_path=subtitle_path, video_path=video_path,
                    reason="unavailable",
                )
                continue

            try:
                result = engine.sync(subtitle_path, video_path)
            except Exception as e:
                elapsed = int((time.monotonic() - start) * 1000)
                logger.warning("sync engine %s raised: %s", name, e)
                last_engine = name
                last_reason = f"exception: {e}"[:64]
                write_sync_job_run(
                    engine=name, status="error", offset_ms=None,
                    duration_ms=elapsed, subtitle_path=subtitle_path,
                    video_path=video_path, reason=last_reason,
                )
                continue

            # Sanity check
            if result.ok and abs(result.offset_ms) > self.sanity_threshold_ms:
                logger.warning(
                    "sync engine %s returned insane offset %dms (>%dms), falling through",
                    name, result.offset_ms, self.sanity_threshold_ms,
                )
                last_engine = name
                last_reason = f"insanity:{result.offset_ms}"
                write_sync_job_run(
                    engine=name, status="insanity_reject", offset_ms=result.offset_ms,
                    duration_ms=result.duration_ms, subtitle_path=subtitle_path,
                    video_path=video_path, reason=last_reason,
                )
                continue

            # Success or engine-reported failure
            write_sync_job_run(
                engine=name,
                status="ok" if result.ok else "failure",
                offset_ms=result.offset_ms,
                duration_ms=result.duration_ms,
                subtitle_path=subtitle_path,
                video_path=video_path,
                reason=result.reason,
            )
            if result.ok:
                return result

            last_engine = name
            last_reason = result.reason or "engine failure"

        # All engines failed
        return SyncResult(
            engine=last_engine, ok=False, offset_ms=0, duration_ms=0,
            reason=last_reason or "all engines failed",
        )


_default_orchestrator: SyncOrchestrator | None = None


def get_default_orchestrator() -> SyncOrchestrator:
    """Lazy-initialize the default orchestrator with the configured engine chain."""
    global _default_orchestrator
    if _default_orchestrator is None:
        # Import here to avoid circular imports
        from services.sync_engines.ffsubsync_engine import FfsubsyncEngine
        from services.sync_engines.alass_engine import AlassEngine

        _default_orchestrator = SyncOrchestrator(
            engines=[FfsubsyncEngine(), AlassEngine()],
            sanity_threshold_ms=60_000,
        )
    return _default_orchestrator
```

- [ ] **Step 3: Run tests**

`cd backend && python -m pytest tests/test_sync_orchestrator.py -v`
Expected: 6 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/services/sync_engines/ backend/tests/test_sync_orchestrator.py
git commit -m "feat(plan-b7): BaseSyncEngine ABC + SyncOrchestrator fallback chain"
```

---

## Task 3: `FfsubsyncEngine` + `AlassEngine` (refactor existing logic)

**Files:** `backend/services/sync_engines/ffsubsync_engine.py`, `alass_engine.py`, `backend/tests/test_sync_engines_concrete.py`.

- [ ] **Step 1: Failing test**

```python
# backend/tests/test_sync_engines_concrete.py
"""Plan B7 — concrete engine tests (ffsubsync + alass)."""

from unittest.mock import patch


def test_ffsubsync_engine_is_available_uses_shutil_which():
    from services.sync_engines.ffsubsync_engine import FfsubsyncEngine

    with patch("services.sync_engines.ffsubsync_engine.shutil.which", return_value=None), \
         patch("services.sync_engines.ffsubsync_engine._check_module", return_value=False):
        assert FfsubsyncEngine().is_available() is False

    with patch("services.sync_engines.ffsubsync_engine.shutil.which", return_value="/usr/bin/ffsubsync"):
        assert FfsubsyncEngine().is_available() is True


def test_alass_engine_is_available_uses_shutil_which():
    from services.sync_engines.alass_engine import AlassEngine

    with patch("services.sync_engines.alass_engine.shutil.which", return_value=None):
        assert AlassEngine().is_available() is False

    with patch("services.sync_engines.alass_engine.shutil.which", return_value="/usr/bin/alass"):
        assert AlassEngine().is_available() is True


def test_ffsubsync_engine_sync_returns_sync_result_on_success(tmp_path):
    from services.sync_engines.ffsubsync_engine import FfsubsyncEngine
    from services.sync_engines.base import SyncResult

    sub = tmp_path / "in.srt"
    sub.write_text("1\n00:00:01,000 --> 00:00:02,000\nHi\n")

    fake_proc = type("P", (), {
        "returncode": 0,
        "stdout": "estimated shift: 0.123 s",
        "stderr": "",
    })()

    with patch("services.sync_engines.ffsubsync_engine.shutil.which", return_value="ffsubsync"), \
         patch("services.sync_engines.ffsubsync_engine.subprocess.run", return_value=fake_proc), \
         patch("services.sync_engines.ffsubsync_engine._fire_after_sync_trigger"), \
         patch("services.sync_engines.ffsubsync_engine.shutil.copy2"):
        result = FfsubsyncEngine().sync(str(sub), "/v.mkv")

    assert isinstance(result, SyncResult)
    assert result.engine == "ffsubsync"
    assert result.ok is True
```

- [ ] **Step 2: Implement the engines**

`backend/services/sync_engines/ffsubsync_engine.py`:

```python
"""ffsubsync engine — speech-detection sync against video.

Refactored from services/video_sync.py::sync_with_ffsubsync.
"""

from __future__ import annotations

import importlib.util
import logging
import shutil
import subprocess
import time
from pathlib import Path

from services.sync_engines.base import BaseSyncEngine, SyncResult

logger = logging.getLogger(__name__)


def _check_module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def _parse_ffsubsync_shift(output: str) -> int:
    """Extract estimated shift in milliseconds from ffsubsync stdout/stderr."""
    import re

    match = re.search(r"(?:estimated shift|shift:?)\s*:?\s*(-?\d+(?:\.\d+)?)\s*s", output, re.IGNORECASE)
    if not match:
        return 0
    try:
        return int(float(match.group(1)) * 1000)
    except ValueError:
        return 0


def _fire_after_sync_trigger(subtitle_path: str, video_or_ref: str, engine: str) -> None:
    """Fire B6 post-processing after_sync trigger. Local import to avoid circular deps."""
    try:
        from post_processing.config_store import get_trigger_ops
        from post_processing.pipeline import run_trigger

        ops = get_trigger_ops("after_sync")
        if ops:
            run_trigger("after_sync", ops, {
                "subtitle_path": subtitle_path,
                "video_path": video_or_ref,
                "lang": "",
                "score": 0,
                "trigger": "after_sync",
            })
    except Exception as e:
        logger.debug("after_sync trigger skipped: %s", e)


class FfsubsyncEngine(BaseSyncEngine):
    name = "ffsubsync"
    timeout_s = 600

    def is_available(self) -> bool:
        return bool(shutil.which("ffsubsync") or _check_module("ffsubsync"))

    def sync(self, subtitle_path: str, video_path: str) -> SyncResult:
        start = time.monotonic()

        if not self.is_available():
            return SyncResult(engine=self.name, ok=False, offset_ms=0,
                              duration_ms=int((time.monotonic() - start) * 1000),
                              reason="ffsubsync not installed")

        src = Path(subtitle_path)
        backup = src.with_suffix(src.suffix + ".bak")
        try:
            shutil.copy2(src, backup)
        except Exception:
            pass

        out_path = str(src)
        cmd = ["ffsubsync", video_path, "-i", subtitle_path, "-o", out_path]
        logger.info("ffsubsync: syncing %s against %s", subtitle_path, video_path)

        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout_s)
        except subprocess.TimeoutExpired:
            return SyncResult(engine=self.name, ok=False, offset_ms=0,
                              duration_ms=int((time.monotonic() - start) * 1000),
                              reason=f"timeout {self.timeout_s}s")

        if proc.returncode != 0:
            return SyncResult(engine=self.name, ok=False, offset_ms=0,
                              duration_ms=int((time.monotonic() - start) * 1000),
                              reason=(proc.stderr or "").strip()[:64] or "non-zero exit")

        offset_ms = _parse_ffsubsync_shift((proc.stderr or "") + (proc.stdout or ""))
        _fire_after_sync_trigger(subtitle_path, video_path, self.name)

        return SyncResult(
            engine=self.name, ok=True, offset_ms=offset_ms,
            duration_ms=int((time.monotonic() - start) * 1000),
            output_path=out_path,
        )
```

`backend/services/sync_engines/alass_engine.py`:

```python
"""alass engine — reference-subtitle-based sync.

Refactored from services/video_sync.py::sync_with_alass.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import time
from pathlib import Path

from services.sync_engines.base import BaseSyncEngine, SyncResult

logger = logging.getLogger(__name__)


def _fire_after_sync_trigger(subtitle_path: str, video_or_ref: str, engine: str) -> None:
    try:
        from post_processing.config_store import get_trigger_ops
        from post_processing.pipeline import run_trigger

        ops = get_trigger_ops("after_sync")
        if ops:
            run_trigger("after_sync", ops, {
                "subtitle_path": subtitle_path,
                "video_path": video_or_ref,
                "lang": "",
                "score": 0,
                "trigger": "after_sync",
            })
    except Exception as e:
        logger.debug("after_sync trigger skipped: %s", e)


class AlassEngine(BaseSyncEngine):
    name = "alass"
    timeout_s = 300

    def is_available(self) -> bool:
        return bool(shutil.which("alass"))

    def sync(self, subtitle_path: str, reference_path: str) -> SyncResult:
        start = time.monotonic()

        if not self.is_available():
            return SyncResult(engine=self.name, ok=False, offset_ms=0,
                              duration_ms=int((time.monotonic() - start) * 1000),
                              reason="alass not installed")

        src = Path(subtitle_path)
        backup = src.with_suffix(src.suffix + ".bak")
        try:
            shutil.copy2(src, backup)
        except Exception:
            pass

        out_path = str(src)
        cmd = ["alass", reference_path, subtitle_path, out_path]
        logger.info("alass: syncing %s against %s", subtitle_path, reference_path)

        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout_s)
        except subprocess.TimeoutExpired:
            return SyncResult(engine=self.name, ok=False, offset_ms=0,
                              duration_ms=int((time.monotonic() - start) * 1000),
                              reason=f"timeout {self.timeout_s}s")

        if proc.returncode != 0:
            return SyncResult(engine=self.name, ok=False, offset_ms=0,
                              duration_ms=int((time.monotonic() - start) * 1000),
                              reason=(proc.stderr or "").strip()[:64] or "non-zero exit")

        _fire_after_sync_trigger(subtitle_path, reference_path, self.name)

        # alass doesn't report offset in stdout — caller can diff timestamps if needed
        return SyncResult(
            engine=self.name, ok=True, offset_ms=0,
            duration_ms=int((time.monotonic() - start) * 1000),
            output_path=out_path,
        )
```

- [ ] **Step 3: Run tests**

`cd backend && python -m pytest tests/test_sync_engines_concrete.py -v`
Expected: 3 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/services/sync_engines/ffsubsync_engine.py backend/services/sync_engines/alass_engine.py backend/tests/test_sync_engines_concrete.py
git commit -m "feat(plan-b7): FfsubsyncEngine + AlassEngine — refactor existing logic"
```

---

## Task 4: Keep legacy `sync_with_ffsubsync` / `sync_with_alass` as thin wrappers

**Files:** `backend/services/video_sync.py`.

- [ ] **Step 1: Write failing compat test**

```python
# Append to backend/tests/test_sync_orchestrator.py

def test_legacy_sync_with_ffsubsync_delegates_to_engine(tmp_path):
    """The legacy sync_with_ffsubsync function still works — it now delegates."""
    from unittest.mock import patch

    from services.sync_engines.base import SyncResult

    # Stub the engine's sync
    fake_result = SyncResult(engine="ffsubsync", ok=True, offset_ms=100, duration_ms=5, output_path=str(tmp_path / "o.srt"))

    with patch("services.sync_engines.ffsubsync_engine.FfsubsyncEngine.sync", return_value=fake_result), \
         patch("services.sync_engines.ffsubsync_engine.FfsubsyncEngine.is_available", return_value=True):
        from services.video_sync import sync_with_ffsubsync

        result_dict = sync_with_ffsubsync(str(tmp_path / "s.srt"), "/v.mkv")

    # Legacy API: returns a dict
    assert result_dict["engine"] == "ffsubsync"
    assert result_dict["success"] is True or result_dict.get("ok") is True
```

- [ ] **Step 2: Replace the existing implementations with thin wrappers**

Replace the bodies of `sync_with_ffsubsync` and `sync_with_alass` in `backend/services/video_sync.py` with calls through the engine classes. Keep the dict-shaped return for backward compat:

```python
# backend/services/video_sync.py — replace the two top-level functions

def sync_with_ffsubsync(subtitle_path: str, video_path: str) -> dict:
    """Legacy compat wrapper — delegates to FfsubsyncEngine."""
    from services.sync_engines.ffsubsync_engine import FfsubsyncEngine

    engine = FfsubsyncEngine()
    if not engine.is_available():
        raise SyncUnavailableError(
            "ffsubsync is not installed. Install with: pip install ffsubsync"
        )
    result = engine.sync(subtitle_path, video_path)
    if not result.ok:
        raise RuntimeError(f"ffsubsync failed: {result.reason}")
    return {
        "engine": result.engine,
        "success": result.ok,
        "offset_ms": result.offset_ms,
        "duration_ms": result.duration_ms,
        "output_path": result.output_path,
    }


def sync_with_alass(subtitle_path: str, reference_path: str) -> dict:
    """Legacy compat wrapper — delegates to AlassEngine."""
    from services.sync_engines.alass_engine import AlassEngine

    engine = AlassEngine()
    if not engine.is_available():
        raise SyncUnavailableError(
            "alass is not installed. Download from: https://github.com/kaegi/alass/releases"
        )
    result = engine.sync(subtitle_path, reference_path)
    if not result.ok:
        raise RuntimeError(f"alass failed: {result.reason}")
    return {
        "engine": result.engine,
        "success": result.ok,
        "offset_ms": result.offset_ms,
        "duration_ms": result.duration_ms,
        "output_path": result.output_path,
    }
```

Keep the existing `SyncUnavailableError` class and `_fire_after_sync_trigger` helper in the file (the engines now own firing the trigger themselves, but the wrapper module may also be imported from legacy code — keep both paths stable).

- [ ] **Step 3: Run tests**

```bash
cd backend && python -m pytest tests/test_sync_orchestrator.py tests/test_sync_engines_concrete.py -v --tb=short
```

Also run regression:

```bash
cd backend && grep -l 'sync_with_ffsubsync\|sync_with_alass' tests/ | xargs python -m pytest -v --tb=short
```

Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/services/video_sync.py backend/tests/test_sync_orchestrator.py
git commit -m "feat(plan-b7): sync_with_ffsubsync/alass become thin engine wrappers"
```

---

## Task 5: API endpoints + Settings UI

**Files:** `backend/routes/sync_engines.py`, `frontend/src/pages/Settings/SyncEnginesTab.tsx`, `frontend/src/api/syncEngines.ts`.

- [ ] **Step 1: API endpoints**

Create `backend/routes/sync_engines.py`:

```python
"""Plan B7 — sync engines API."""

from flask import Blueprint, jsonify, request

sync_engines_bp = Blueprint("sync_engines", __name__, url_prefix="/api/v1/sync")


@sync_engines_bp.route("/engines", methods=["GET"])
def list_engines():
    from services.sync_engines.orchestrator import get_default_orchestrator

    orch = get_default_orchestrator()
    return jsonify({
        "engines": [
            {
                "name": e.name,
                "available": e.is_available(),
                "timeout_s": e.timeout_s,
            }
            for e in orch.engines
        ],
        "sanity_threshold_ms": orch.sanity_threshold_ms,
    })


@sync_engines_bp.route("/runs", methods=["GET"])
def list_runs():
    from db.models.core import SyncJobRun

    limit = min(int(request.args.get("limit", 50)), 500)
    rows = SyncJobRun.query.order_by(SyncJobRun.id.desc()).limit(limit).all()
    return jsonify({
        "runs": [
            {
                "id": r.id,
                "engine": r.engine,
                "status": r.status,
                "offset_ms": r.offset_ms,
                "duration_ms": r.duration_ms,
                "subtitle_path": r.subtitle_path,
                "video_path": r.video_path,
                "reason": r.reason,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    })
```

Register the blueprint wherever other blueprints are registered (`grep register_blueprint backend/app.py` to confirm).

- [ ] **Step 2: API tests**

Append to `backend/tests/test_sync_orchestrator.py`:

```python
def test_api_list_engines(client):
    resp = client.get("/api/v1/sync/engines")
    assert resp.status_code == 200
    body = resp.get_json()
    names = [e["name"] for e in body["engines"]]
    assert "ffsubsync" in names
    assert "alass" in names
    assert body["sanity_threshold_ms"] == 60_000


def test_api_list_runs(client):
    resp = client.get("/api/v1/sync/runs")
    assert resp.status_code == 200
    body = resp.get_json()
    assert "runs" in body
```

- [ ] **Step 3: Frontend (minimal — informational tab)**

Create `frontend/src/api/syncEngines.ts`:

```typescript
export interface SyncEngineInfo {
  name: string
  available: boolean
  timeout_s: number
}

export interface SyncEnginesResponse {
  engines: SyncEngineInfo[]
  sanity_threshold_ms: number
}

export async function fetchSyncEngines(): Promise<SyncEnginesResponse> {
  const resp = await fetch('/api/v1/sync/engines', { headers: { 'X-API-Key': getApiKey() } })
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
  return resp.json()
}
```

Create `frontend/src/pages/Settings/SyncEnginesTab.tsx` as an informational tab that lists engines + their availability status + the sanity threshold. (Users can't reorder yet — that's a follow-up.)

- [ ] **Step 4: Run tests + ruff + tsc**

```bash
cd backend && python -m pytest tests/test_sync_orchestrator.py -v --tb=short
cd backend && ruff check . && ruff format --check .
cd frontend && npm run lint && npx tsc --noEmit
```

All must exit 0.

- [ ] **Step 5: Commit**

```bash
git add backend/routes/sync_engines.py backend/tests/test_sync_orchestrator.py frontend/src/api/syncEngines.ts frontend/src/pages/Settings/SyncEnginesTab.tsx
git commit -m "feat(plan-b7): API + Settings UI — sync engines + runs audit"
```

---

## Task 6: Deploy

- [ ] **Step 1: Pre-deploy checks**

```bash
cd backend && ruff check . && ruff format --check .
cd backend && python -m pytest tests/test_sync_orchestrator.py tests/test_sync_engines_concrete.py tests/test_sync_job_run_model.py -v --tb=short
cd frontend && npm run lint && npx tsc --noEmit
```

All must exit 0.

- [ ] **Step 2: Invoke deploy skill**

Bumps to 0.70.0-beta. Expected CHANGELOG:

```markdown
## [0.70.0-beta] - 2026-04-19

### Added
- **Plan B Phase 7 — Multi-engine sync orchestrator** — New `backend/services/sync_engines/` package with `BaseSyncEngine` ABC + `SyncOrchestrator` fallback chain + per-engine timeout + sanity threshold (60 s by default). Existing ffsubsync + alass logic refactored into named engine classes; legacy `sync_with_ffsubsync` / `sync_with_alass` functions remain as thin wrappers for backward compat. New `sync_job_runs` audit table records every engine attempt (engine, status, offset_ms, duration_ms, subtitle_path, video_path, reason, created_at) — queryable via `/api/v1/sync/runs`. New Settings → Sync Engines tab shows engine availability + sanity threshold. Opens the door for dropping in new engines (nanosync, LLM-assisted) without changing the orchestrator.

### Changed — Plan B scope note
- **B7 engines scope reduced** — The spec listed 4 engines (ffsubsync, alass, nanosync, LLM-assisted). `nanosync` and the LLM-assisted engine require research-grade algorithm development; B7 ships the architecture + the 2 existing engines refactored into the pattern. Future phases can drop in new engines without touching the orchestrator.

### Plan B Progress — COMPLETE 🎉
- Phase B1 — Subliminal vendor foundation: **shipped (0.64.0-beta)**
- Phase B2 — Full Subliminal provider adoption: **shipped (0.65.0-beta)**
- Phase B3 — Granular blacklist: **shipped (0.66.0-beta)** (Subzero merge deferred)
- Phase B4 — Scoring penalty pipeline: **shipped (0.67.0-beta)**
- Phase B5 — SRT repair + embedded hardening: **shipped (0.68.0-beta)**
- Phase B6 — Post-processing pipeline: **shipped (0.69.0-beta)**
- Phase B7 — Multi-engine sync orchestrator: **shipped (0.70.0-beta)** — Plan B complete.
```

- [ ] **Step 3: Verify in prod**

```bash
curl -s -H "X-API-Key: $SUBLARR_KEY" http://192.168.178.36:5765/api/v1/sync/engines \
  | python -c "import sys,json; d=json.load(sys.stdin); [print(f'  {e[\"name\"]}: available={e[\"available\"]}') for e in d['engines']]"
# Expected: 2 engines listed (ffsubsync + alass)

ssh root@192.168.178.36 "docker exec sublarr-postgres psql -U sublarr -d sublarr -c '\d sync_job_runs'" | head -15
# Expected: table with 9 columns

ssh root@192.168.178.36 "docker logs sublarr --since 2m 2>&1" \
  | grep -iE "(error|traceback|sync_engines|alembic)" \
  | grep -vE "(enzyme|X-Signature|marketplace registry)" | head -15
# Expected: only the alembic upgrade INFO line
```

---

## Phase B7 Acceptance Checklist

- [ ] `sync_job_runs` table created + ORM model
- [ ] `BaseSyncEngine` ABC + `SyncOrchestrator` with fallback chain + sanity threshold
- [ ] `FfsubsyncEngine` + `AlassEngine` refactored from existing logic
- [ ] Legacy `sync_with_ffsubsync` / `sync_with_alass` remain as thin wrappers
- [ ] `/api/v1/sync/engines` + `/api/v1/sync/runs` endpoints
- [ ] Settings → Sync Engines tab
- [ ] ~12+ new tests pass (orchestrator fallback + concrete engines + API)
- [ ] No regression (grep-based audit of `sync_with_*` callers)
- [ ] Ruff + tsc clean
- [ ] 0.70.0-beta deployed; 2 engines + audit table verified in prod

## Plan B COMPLETE after B7

After this phase, Plan B's 7-phase Bazarr-delivery-parity roadmap is fully shipped (with two documented deferrals: Subzero selective merge in B3, nanosync/oai-sync engines in B7). Sublarr now has: 29 subtitle providers, named-class penalty scoring, SRT repair, embedded track-selection hardening, post-processing pipeline with 8 ops + shell escape, multi-engine sync with fallback + audit.
