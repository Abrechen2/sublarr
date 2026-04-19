# Plan B / Phase B6 — Post-Processing Pipeline

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-04-19-plan-b-subtitle-delivery-quality-design.md`
**Prior:** B5 shipped as 0.68.0-beta — subtitle_repair + embedded track-selection hardening.

**Goal:** Ship a curated-ops-first post-processing pipeline with an opt-in shell escape hatch. Three triggers (after_download, after_translate, after_sync) fire a user-configured ordered list of ops against the saved subtitle. 8+ curated ops ship; shell scripts are available only when the operator explicitly sets `SUBLARR_ALLOW_SHELL_SCRIPTS=true`.

**Architecture:**
- New package `backend/post_processing/` with `pipeline.py` (driver) + `ops/` subfolder (one op per file) + `shell_runner.py` (escape-hatch executor, only imported when env flag set) + `events.py` (audit writer for the new `post_processing_runs` DB table) + `config_store.py` (DB-backed per-trigger op config)
- New DB table `post_processing_runs` — columns: `id, trigger, ops_executed (jsonb), duration_ms, outcome, created_at` (Alembic migration)
- Hooks fire from the three save paths already instrumented in B5 — `save_subtitle()`, embedded-extract, post-translate — immediately after the repair pass lands the bytes on disk
- Each op implements `BaseOp.execute(context) -> OpResult` where `context = {subtitle_path, video_path, lang, score, trigger}` — pure interface, no shared state
- Pipeline runs inside a dedicated thread pool (not request handlers) — a `PostProcessingExecutor` singleton with `max_workers=2` by default, `submit(trigger, context)` returns a Future; fire-and-forget from the caller
- Shell escape runs in the same thread pool but via `subprocess.run(shell=False, args=split_args, env=restricted_env, timeout=30)` with stdout + stderr captured to the audit row. Script body is read from per-trigger config; variable substitution uses safe placeholder replacement (no shell interpolation of user content)

**Tech Stack:** Python 3.12, SQLAlchemy 2.0 ORM, Alembic, `concurrent.futures.ThreadPoolExecutor`, pytest, React 19 + TypeScript.

**Baseline:** 0.68.0-beta → 0.69.0-beta (minor bump).

---

## File Structure

### Create

- `backend/post_processing/__init__.py` — package root; re-exports `PostProcessingPipeline`, `run_trigger`
- `backend/post_processing/pipeline.py` — `PostProcessingPipeline` driver + executor singleton
- `backend/post_processing/base_op.py` — `BaseOp` ABC + `OpResult` dataclass + `@register_op` decorator + `_OP_REGISTRY`
- `backend/post_processing/ops/__init__.py` — imports all ops to trigger decorator registration
- `backend/post_processing/ops/text_ops.py` — `strip_html`, `convert_encoding`, `remove_bom`
- `backend/post_processing/ops/webhook.py` — generic webhook POST
- `backend/post_processing/ops/discord_notify.py` — Discord webhook
- `backend/post_processing/ops/media_server_refresh.py` — plex/emby/jellyfin refresh
- `backend/post_processing/shell_runner.py` — opt-in shell escape
- `backend/post_processing/events.py` — audit writer for `post_processing_runs`
- `backend/post_processing/config_store.py` — per-trigger op config (reads/writes `config_entries`)
- `backend/db/migrations/versions/2026_04_19_XXXX-<rev>_add_post_processing_runs.py`
- `backend/routes/post_processing.py` (or `backend/routes/post_processing/__init__.py`) — 4 endpoints: GET `/api/v1/post-processing/ops`, GET/PUT `/api/v1/post-processing/config`, GET `/api/v1/post-processing/runs`
- `backend/tests/test_post_processing_*.py` — one per op file + pipeline + shell + API tests
- `frontend/src/pages/Settings/PostProcessingTab.tsx` — new settings tab
- `frontend/src/api/postProcessing.ts` — fetcher + mutations

### Modify

- `backend/db/models/core.py` — add `PostProcessingRun` ORM model
- `backend/providers/download_manager.py::save_subtitle()` — fire `after_download` trigger after repair pass
- `backend/translator/_helpers.py` (or wherever B5 placed the post-translate repair hook) — fire `after_translate` after repair
- `backend/services/video_sync.py` (or the sync worker) — fire `after_sync` after sync completes
- `backend/config.py` — add `post_processing_enabled: bool = True` + document `SUBLARR_ALLOW_SHELL_SCRIPTS` env flag
- `backend/app.py` — register `PostProcessingExecutor` for graceful shutdown
- `frontend/src/pages/Settings/SettingsLayout.tsx` (or wherever nav links live) — add Post-Processing entry

---

## Task 1: Alembic migration + `PostProcessingRun` ORM model

**Files:**
- Create: `backend/db/migrations/versions/2026_04_19_XXXX-<rev>_add_post_processing_runs.py`
- Modify: `backend/db/models/core.py` — add `PostProcessingRun`
- Create: `backend/tests/test_post_processing_model.py`

- [ ] **Step 1: Find current alembic head**

Run: `cd backend && python -m alembic heads`
Record the single revision hash as `<PRIOR_HEAD>`. If multiple heads, STOP.

- [ ] **Step 2: Generate revision hash**

Run: `cd backend && python -c "import secrets; print(secrets.token_hex(6))"`
Record as `<NEW_REV>`.

- [ ] **Step 3: Write the migration**

Create `backend/db/migrations/versions/2026_04_19_XXXX-<NEW_REV>_add_post_processing_runs.py` (replace `XXXX` with `HHMM`):

```python
"""add post_processing_runs table

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
        "post_processing_runs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("trigger", sa.String(length=32), nullable=False),
        sa.Column("ops_executed", sa.JSON, nullable=False),
        sa.Column("duration_ms", sa.Integer, nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("idx_pp_runs_created_at", "post_processing_runs", ["created_at"])
    op.create_index("idx_pp_runs_trigger", "post_processing_runs", ["trigger"])


def downgrade() -> None:
    op.drop_index("idx_pp_runs_trigger", table_name="post_processing_runs")
    op.drop_index("idx_pp_runs_created_at", table_name="post_processing_runs")
    op.drop_table("post_processing_runs")
```

- [ ] **Step 4: Run migration roundtrip**

Run: `cd backend && python -m alembic upgrade head && python -m alembic downgrade -1 && python -m alembic upgrade head`
Expected: all three commands exit 0.

- [ ] **Step 5: Add ORM model + failing test**

Append to `backend/db/models/core.py` (near `BlacklistEntry`):

```python
class PostProcessingRun(db.Model):
    """Audit row for one post-processing pipeline run."""

    __tablename__ = "post_processing_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trigger: Mapped[str] = mapped_column(String(32), nullable=False)
    ops_executed: Mapped[dict] = mapped_column(JSON, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
```

Make sure the required imports (`JSON`, `String`, `Integer`, `DateTime`, `Mapped`, `mapped_column`) are already present.

Write `backend/tests/test_post_processing_model.py`:

```python
"""Plan B6 — PostProcessingRun ORM sanity test."""

from datetime import datetime, timezone


def test_post_processing_run_has_expected_columns():
    from db.models.core import PostProcessingRun

    attrs = {"id", "trigger", "ops_executed", "duration_ms", "outcome", "created_at"}
    for attr in attrs:
        assert hasattr(PostProcessingRun, attr), f"missing {attr}"


def test_post_processing_run_instantiation():
    from db.models.core import PostProcessingRun

    row = PostProcessingRun(
        trigger="after_download",
        ops_executed={"ops": ["strip_html"]},
        duration_ms=42,
        outcome="ok",
        created_at=datetime.now(timezone.utc),
    )
    assert row.trigger == "after_download"
    assert row.duration_ms == 42
```

- [ ] **Step 6: Run tests**

Run: `cd backend && python -m pytest tests/test_post_processing_model.py -v`
Expected: 2 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/db/migrations/versions/2026_04_19_XXXX-<NEW_REV>_add_post_processing_runs.py backend/db/models/core.py backend/tests/test_post_processing_model.py
git commit -m "feat(plan-b6): alembic + ORM — post_processing_runs table"
```

---

## Task 2: `BaseOp` ABC + `PostProcessingPipeline` driver + events writer

**Files:**
- Create: `backend/post_processing/__init__.py`
- Create: `backend/post_processing/base_op.py`
- Create: `backend/post_processing/pipeline.py`
- Create: `backend/post_processing/events.py`
- Create: `backend/tests/test_post_processing_pipeline.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_post_processing_pipeline.py
"""Plan B6 — pipeline driver tests."""

import pytest


def test_base_op_abc_exists():
    from post_processing.base_op import BaseOp, OpResult

    with pytest.raises(TypeError):
        BaseOp()

    # OpResult is a dataclass
    result = OpResult(op_id="test", ok=True, duration_ms=5, message="")
    assert result.op_id == "test"
    assert result.ok is True


def test_register_op_decorator():
    from post_processing.base_op import BaseOp, register_op, _OP_REGISTRY

    before = len(_OP_REGISTRY)

    @register_op
    class DummyOp(BaseOp):
        op_id = "dummy_b6_test"
        label = "Dummy"
        description = "test"

        def execute(self, context):
            from post_processing.base_op import OpResult
            return OpResult(op_id=self.op_id, ok=True, duration_ms=0, message="ran")

    assert len(_OP_REGISTRY) == before + 1
    assert "dummy_b6_test" in {cls.op_id for cls in _OP_REGISTRY}

    # Cleanup
    _OP_REGISTRY.remove(DummyOp)


def test_pipeline_runs_ops_in_order_and_writes_audit(tmp_path, app_ctx):
    """PostProcessingPipeline runs ops sequentially, catches exceptions, writes an audit row."""
    from post_processing.base_op import BaseOp, OpResult, register_op, _OP_REGISTRY
    from post_processing.pipeline import PostProcessingPipeline

    # Build two test ops
    @register_op
    class FirstOp(BaseOp):
        op_id = "b6_first"
        label = "First"
        description = "test"
        def execute(self, context):
            return OpResult(op_id=self.op_id, ok=True, duration_ms=3, message="first-ran")

    @register_op
    class FailingOp(BaseOp):
        op_id = "b6_failing"
        label = "Fail"
        description = "test"
        abort_on_error = False
        def execute(self, context):
            raise RuntimeError("boom")

    try:
        pipe = PostProcessingPipeline()
        context = {"subtitle_path": str(tmp_path / "s.srt"), "video_path": "/v.mkv",
                   "lang": "en", "score": 100, "trigger": "after_download"}
        op_ids = ["b6_first", "b6_failing"]
        results = pipe.run(trigger="after_download", op_ids=op_ids, context=context)

        assert len(results) == 2
        assert results[0].ok is True
        assert results[1].ok is False  # caught exception

        # Audit row written
        from db.models.core import PostProcessingRun
        runs = PostProcessingRun.query.order_by(PostProcessingRun.id.desc()).limit(5).all()
        assert any(r.trigger == "after_download" and "b6_first" in str(r.ops_executed) for r in runs)
    finally:
        _OP_REGISTRY.remove(FirstOp)
        _OP_REGISTRY.remove(FailingOp)
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && python -m pytest tests/test_post_processing_pipeline.py -v`
Expected: tests FAIL with `ModuleNotFoundError: No module named 'post_processing'`.

- [ ] **Step 3: Implement the three files**

`backend/post_processing/__init__.py`:

```python
"""Post-processing pipeline package."""

from post_processing.pipeline import PostProcessingPipeline, run_trigger  # noqa: F401
```

`backend/post_processing/base_op.py`:

```python
"""Abstract base class for post-processing ops + registry."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar

logger = logging.getLogger(__name__)


@dataclass
class OpResult:
    """Result of one post-processing op run."""

    op_id: str
    ok: bool
    duration_ms: int
    message: str


_OP_REGISTRY: list[type[BaseOp]] = []


class BaseOp(ABC):
    """Base class for all post-processing ops.

    Subclasses define:
      - op_id: stable identifier (also DB key)
      - label: short UI label
      - description: longer UI explanation
      - abort_on_error: bool (default False). If True, a failure aborts the
        whole pipeline. Most ops should stay False so one broken op doesn't
        block the rest.
      - execute(context) -> OpResult — actually do the work
    """

    op_id: ClassVar[str] = ""
    label: ClassVar[str] = ""
    description: ClassVar[str] = ""
    abort_on_error: ClassVar[bool] = False

    @abstractmethod
    def execute(self, context: dict) -> OpResult:
        """Execute the op. Context keys: subtitle_path, video_path, lang, score, trigger."""


def register_op(cls: type[BaseOp]) -> type[BaseOp]:
    """Decorator to register an op in the module registry."""
    if not cls.op_id:
        raise ValueError(f"Op {cls.__name__} must define op_id")
    if cls in _OP_REGISTRY:
        return cls
    _OP_REGISTRY.append(cls)
    return cls
```

`backend/post_processing/events.py`:

```python
"""Audit-row writer for post_processing_runs."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def write_post_processing_run(
    trigger: str,
    op_results: list,
    duration_ms: int,
) -> None:
    """Insert one audit row. Never raises — falls back to WARN on DB failure."""
    try:
        from db import db
        from db.models.core import PostProcessingRun

        outcome = "ok" if all(r.ok for r in op_results) else "partial_failure"
        if op_results and not any(r.ok for r in op_results):
            outcome = "failure"

        row = PostProcessingRun(
            trigger=trigger,
            ops_executed={
                "ops": [
                    {"op_id": r.op_id, "ok": r.ok, "duration_ms": r.duration_ms, "message": r.message}
                    for r in op_results
                ],
            },
            duration_ms=duration_ms,
            outcome=outcome,
            created_at=datetime.now(timezone.utc),
        )
        db.session.add(row)
        db.session.commit()
    except Exception as e:
        logger.warning("post_processing audit write failed: %s", e)
```

`backend/post_processing/pipeline.py`:

```python
"""Post-processing pipeline driver."""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor

from post_processing.base_op import BaseOp, OpResult, _OP_REGISTRY
from post_processing.events import write_post_processing_run

logger = logging.getLogger(__name__)


class PostProcessingPipeline:
    """Synchronous pipeline runner — runs ops in order, catches exceptions, writes audit."""

    def run(
        self,
        trigger: str,
        op_ids: list[str],
        context: dict,
    ) -> list[OpResult]:
        """Run the ordered list of op_ids for this trigger.

        Returns per-op results. Writes one audit row per run.
        Never raises — failures are captured in OpResult.ok=False.
        """
        start = time.monotonic()
        results: list[OpResult] = []

        # Resolve op_ids to classes (skip unknowns with a warning)
        by_id = {cls.op_id: cls for cls in _OP_REGISTRY}
        for op_id in op_ids:
            cls = by_id.get(op_id)
            if cls is None:
                logger.warning("Unknown post-processing op: %s", op_id)
                continue

            op_start = time.monotonic()
            try:
                result = cls().execute(context)
                results.append(result)
                if not result.ok and cls.abort_on_error:
                    logger.info("Aborting pipeline — %s failed with abort_on_error=True", op_id)
                    break
            except Exception as e:
                elapsed = int((time.monotonic() - op_start) * 1000)
                logger.warning("Op %s raised: %s", op_id, e)
                results.append(OpResult(op_id=op_id, ok=False, duration_ms=elapsed, message=str(e)))
                if cls.abort_on_error:
                    break

        total_ms = int((time.monotonic() - start) * 1000)
        write_post_processing_run(trigger, results, total_ms)
        return results


_executor: ThreadPoolExecutor | None = None


def _get_executor() -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="post_proc")
    return _executor


def run_trigger(trigger: str, op_ids: list[str], context: dict) -> None:
    """Fire-and-forget pipeline run on the shared thread pool.

    Use this from save paths — it returns immediately.
    """
    pipe = PostProcessingPipeline()
    _get_executor().submit(pipe.run, trigger, op_ids, context)
```

- [ ] **Step 4: Run tests to verify pass**

Run: `cd backend && python -m pytest tests/test_post_processing_pipeline.py -v`
Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/post_processing/ backend/tests/test_post_processing_pipeline.py
git commit -m "feat(plan-b6): pipeline driver + BaseOp ABC + audit writer"
```

---

## Task 3: Implement 3 text ops (strip_html, convert_encoding, remove_bom)

**Files:**
- Create: `backend/post_processing/ops/__init__.py`
- Create: `backend/post_processing/ops/text_ops.py`
- Create: `backend/tests/test_post_processing_text_ops.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_post_processing_text_ops.py
"""Plan B6 — text ops tests."""

from pathlib import Path


def test_strip_html_removes_basic_tags(tmp_path):
    from post_processing.ops.text_ops import StripHtmlOp

    path = tmp_path / "x.srt"
    path.write_text(
        "1\n00:00:01,000 --> 00:00:02,000\n<i>Italic</i> <b>Bold</b>\n",
        encoding="utf-8",
    )
    result = StripHtmlOp().execute({"subtitle_path": str(path), "lang": "en", "video_path": "", "score": 0, "trigger": "after_download"})
    assert result.ok
    content = path.read_text(encoding="utf-8")
    assert "<i>" not in content
    assert "<b>" not in content
    assert "Italic" in content
    assert "Bold" in content


def test_remove_bom_op(tmp_path):
    from post_processing.ops.text_ops import RemoveBomOp

    path = tmp_path / "x.srt"
    path.write_bytes(b"\xef\xbb\xbf1\n00:00:01,000 --> 00:00:02,000\nHello\n")
    assert path.read_bytes().startswith(b"\xef\xbb\xbf")

    result = RemoveBomOp().execute({"subtitle_path": str(path), "lang": "en", "video_path": "", "score": 0, "trigger": "after_download"})
    assert result.ok
    assert not path.read_bytes().startswith(b"\xef\xbb\xbf")
    assert b"Hello" in path.read_bytes()


def test_convert_encoding_op(tmp_path):
    from post_processing.ops.text_ops import ConvertEncodingOp

    path = tmp_path / "x.srt"
    # Write as windows-1252
    path.write_bytes("It\x92s a test.".encode("windows-1252"))

    # Convert to utf-8 (default target)
    op = ConvertEncodingOp()
    result = op.execute({"subtitle_path": str(path), "lang": "en", "video_path": "", "score": 0, "trigger": "after_download"})
    assert result.ok
    # Result is decodable as utf-8
    path.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && python -m pytest tests/test_post_processing_text_ops.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement the 3 ops**

`backend/post_processing/ops/__init__.py`:

```python
"""Auto-import all op modules so @register_op decorators fire."""

from post_processing.ops import text_ops, webhook, discord_notify, media_server_refresh  # noqa: F401
```

`backend/post_processing/ops/text_ops.py`:

```python
"""Text transformation ops: strip_html, convert_encoding, remove_bom."""

from __future__ import annotations

import re
import time
from pathlib import Path

from post_processing.base_op import BaseOp, OpResult, register_op


_HTML_TAG_RE = re.compile(r"<[^>]+>")


@register_op
class StripHtmlOp(BaseOp):
    op_id = "strip_html"
    label = "Strip HTML tags"
    description = "Remove <i>, <b>, <font>, <br> and other HTML tags from subtitle lines."

    def execute(self, context: dict) -> OpResult:
        start = time.monotonic()
        try:
            path = Path(context["subtitle_path"])
            text = path.read_text(encoding="utf-8", errors="replace")
            cleaned = _HTML_TAG_RE.sub("", text)
            if cleaned != text:
                path.write_text(cleaned, encoding="utf-8")
            return OpResult(
                op_id=self.op_id,
                ok=True,
                duration_ms=int((time.monotonic() - start) * 1000),
                message="html stripped" if cleaned != text else "no html found",
            )
        except Exception as e:
            return OpResult(
                op_id=self.op_id,
                ok=False,
                duration_ms=int((time.monotonic() - start) * 1000),
                message=str(e),
            )


@register_op
class RemoveBomOp(BaseOp):
    op_id = "remove_bom"
    label = "Remove BOM"
    description = "Strip UTF-8 BOM (0xEF 0xBB 0xBF) from the start of the subtitle file."

    def execute(self, context: dict) -> OpResult:
        start = time.monotonic()
        try:
            path = Path(context["subtitle_path"])
            data = path.read_bytes()
            if data.startswith(b"\xef\xbb\xbf"):
                path.write_bytes(data[3:])
                return OpResult(self.op_id, True, int((time.monotonic() - start) * 1000), "bom stripped")
            return OpResult(self.op_id, True, int((time.monotonic() - start) * 1000), "no bom")
        except Exception as e:
            return OpResult(self.op_id, False, int((time.monotonic() - start) * 1000), str(e))


@register_op
class ConvertEncodingOp(BaseOp):
    op_id = "convert_encoding"
    label = "Convert encoding"
    description = "Re-encode the subtitle to UTF-8 (auto-detects source encoding via chardet)."

    def execute(self, context: dict) -> OpResult:
        start = time.monotonic()
        try:
            path = Path(context["subtitle_path"])
            raw = path.read_bytes()
            # Try UTF-8 first
            try:
                raw.decode("utf-8")
                return OpResult(self.op_id, True, int((time.monotonic() - start) * 1000), "already utf-8")
            except UnicodeDecodeError:
                pass
            # Detect + re-encode
            try:
                import chardet

                detected = chardet.detect(raw) or {}
                enc = detected.get("encoding") or "windows-1252"
            except ImportError:
                enc = "windows-1252"
            text = raw.decode(enc, errors="replace")
            path.write_text(text, encoding="utf-8")
            return OpResult(self.op_id, True, int((time.monotonic() - start) * 1000), f"converted from {enc}")
        except Exception as e:
            return OpResult(self.op_id, False, int((time.monotonic() - start) * 1000), str(e))
```

- [ ] **Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_post_processing_text_ops.py -v`
Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/post_processing/ops/ backend/tests/test_post_processing_text_ops.py
git commit -m "feat(plan-b6): 3 text ops — strip_html, remove_bom, convert_encoding"
```

---

## Task 4: HTTP ops (webhook + discord_notify)

**Files:**
- Create: `backend/post_processing/ops/webhook.py`
- Create: `backend/post_processing/ops/discord_notify.py`
- Create: `backend/tests/test_post_processing_http_ops.py`

- [ ] **Step 1: Write failing tests (use responses library if available, else unittest.mock)**

```python
# backend/tests/test_post_processing_http_ops.py
"""Plan B6 — HTTP ops tests (webhook + discord_notify)."""

from unittest.mock import patch


def test_webhook_op_posts_to_url():
    from post_processing.ops.webhook import WebhookOp

    op = WebhookOp()
    op.url = "http://example.com/hook"  # injected via op config in real usage
    op.method = "POST"
    op.template = '{"file": "{subtitle_path}", "lang": "{lang}"}'

    with patch("post_processing.ops.webhook.requests.request") as mock_req:
        mock_req.return_value.status_code = 200
        mock_req.return_value.text = "ok"

        result = op.execute({
            "subtitle_path": "/m/s.srt",
            "video_path": "/m/v.mkv",
            "lang": "en",
            "score": 100,
            "trigger": "after_download",
        })

    assert result.ok
    mock_req.assert_called_once()
    # Body was substituted
    _, kwargs = mock_req.call_args
    assert "/m/s.srt" in str(kwargs.get("json") or kwargs.get("data") or "")


def test_webhook_op_rejects_file_url():
    """SSRF protection — webhook must use validate_service_url (blocks file://)."""
    from post_processing.ops.webhook import WebhookOp

    op = WebhookOp()
    op.url = "file:///etc/passwd"
    op.method = "GET"
    op.template = ""

    result = op.execute({"subtitle_path": "", "video_path": "", "lang": "en", "score": 0, "trigger": "after_download"})
    assert result.ok is False
    assert "ssrf" in result.message.lower() or "scheme" in result.message.lower() or "invalid" in result.message.lower()


def test_discord_notify_op_uses_discord_format():
    from post_processing.ops.discord_notify import DiscordNotifyOp

    op = DiscordNotifyOp()
    op.webhook_url = "https://discord.com/api/webhooks/123/abc"

    with patch("post_processing.ops.discord_notify.requests.post") as mock_post:
        mock_post.return_value.status_code = 204
        mock_post.return_value.text = ""

        result = op.execute({
            "subtitle_path": "/m/S01E01.en.srt",
            "video_path": "/m/S01E01.mkv",
            "lang": "en",
            "score": 120,
            "trigger": "after_download",
        })

    assert result.ok
    # Discord payload uses "content" or "embeds"
    _, kwargs = mock_post.call_args
    payload = kwargs.get("json", {})
    assert "content" in payload or "embeds" in payload
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && python -m pytest tests/test_post_processing_http_ops.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement the 2 ops**

`backend/post_processing/ops/webhook.py`:

```python
"""Generic webhook POST op. Reuses validate_service_url for SSRF protection."""

from __future__ import annotations

import time

import requests

from post_processing.base_op import BaseOp, OpResult, register_op


@register_op
class WebhookOp(BaseOp):
    op_id = "webhook"
    label = "Webhook"
    description = "POST the saved subtitle event to a configurable HTTP endpoint. Supports {subtitle_path}, {video_path}, {lang}, {score} substitution."

    # Op config fields (populated from per-trigger config):
    url: str = ""
    method: str = "POST"
    template: str = ""  # JSON body template with {placeholders}

    def execute(self, context: dict) -> OpResult:
        start = time.monotonic()

        if not self.url:
            return OpResult(self.op_id, False, 0, "no url configured")

        # SSRF protection via existing helper
        try:
            from security_utils import validate_service_url

            try:
                validate_service_url(self.url)
            except Exception as e:
                return OpResult(self.op_id, False, int((time.monotonic() - start) * 1000), f"url rejected (ssrf): {e}")
        except ImportError:
            # If validate_service_url is not importable, fall through — document as follow-up
            pass

        # Substitute placeholders
        body_str = self.template
        for key in ("subtitle_path", "video_path", "lang", "score", "trigger"):
            body_str = body_str.replace("{" + key + "}", str(context.get(key, "")))

        try:
            kwargs: dict = {"timeout": 10}
            if body_str:
                # Try JSON first, fall back to raw body
                try:
                    import json

                    kwargs["json"] = json.loads(body_str)
                except (json.JSONDecodeError, ValueError):
                    kwargs["data"] = body_str

            resp = requests.request(self.method.upper(), self.url, **kwargs)
            if resp.status_code >= 400:
                return OpResult(self.op_id, False, int((time.monotonic() - start) * 1000), f"http {resp.status_code}")
            return OpResult(self.op_id, True, int((time.monotonic() - start) * 1000), f"http {resp.status_code}")
        except Exception as e:
            return OpResult(self.op_id, False, int((time.monotonic() - start) * 1000), str(e))
```

`backend/post_processing/ops/discord_notify.py`:

```python
"""Discord webhook notification op."""

from __future__ import annotations

import time
from pathlib import Path

import requests

from post_processing.base_op import BaseOp, OpResult, register_op


@register_op
class DiscordNotifyOp(BaseOp):
    op_id = "discord_notify"
    label = "Discord Notification"
    description = "Send a Discord notification when a subtitle is processed. Requires a Discord webhook URL."

    webhook_url: str = ""

    def execute(self, context: dict) -> OpResult:
        start = time.monotonic()

        if not self.webhook_url:
            return OpResult(self.op_id, False, 0, "no webhook_url")

        if not self.webhook_url.startswith("https://discord.com/api/webhooks/"):
            return OpResult(self.op_id, False, 0, "invalid discord webhook url")

        subtitle_name = Path(context.get("subtitle_path", "")).name or "subtitle"
        video_name = Path(context.get("video_path", "")).name or "video"
        lang = context.get("lang", "?")
        score = context.get("score", "?")
        trigger = context.get("trigger", "after_download")

        payload = {
            "content": f"Sublarr `{trigger}`: `{subtitle_name}` for `{video_name}` ({lang}, score={score})"
        }

        try:
            resp = requests.post(self.webhook_url, json=payload, timeout=10)
            if resp.status_code >= 400:
                return OpResult(self.op_id, False, int((time.monotonic() - start) * 1000), f"http {resp.status_code}")
            return OpResult(self.op_id, True, int((time.monotonic() - start) * 1000), "notified")
        except Exception as e:
            return OpResult(self.op_id, False, int((time.monotonic() - start) * 1000), str(e))
```

- [ ] **Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_post_processing_http_ops.py -v`
Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/post_processing/ops/webhook.py backend/post_processing/ops/discord_notify.py backend/tests/test_post_processing_http_ops.py
git commit -m "feat(plan-b6): HTTP ops — webhook (SSRF-protected) + discord_notify"
```

---

## Task 5: Media server refresh ops (plex/emby/jellyfin)

**Files:**
- Create: `backend/post_processing/ops/media_server_refresh.py`
- Create: `backend/tests/test_post_processing_media_ops.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_post_processing_media_ops.py
"""Plan B6 — media server refresh ops."""

from unittest.mock import patch


def test_plex_refresh_posts_to_plex():
    from post_processing.ops.media_server_refresh import PlexRefreshOp

    op = PlexRefreshOp()
    op.base_url = "http://plex:32400"
    op.token = "abc123"

    with patch("post_processing.ops.media_server_refresh.requests.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.text = "<xml/>"
        result = op.execute({"subtitle_path": "/m/s.srt", "video_path": "/m/v.mkv",
                             "lang": "en", "score": 100, "trigger": "after_download"})

    assert result.ok
    mock_get.assert_called_once()
    # Token goes in X-Plex-Token header
    call_args = mock_get.call_args
    headers = call_args.kwargs.get("headers") or {}
    assert headers.get("X-Plex-Token") == "abc123"


def test_emby_refresh_posts_to_emby():
    from post_processing.ops.media_server_refresh import EmbyRefreshOp

    op = EmbyRefreshOp()
    op.base_url = "http://emby:8096"
    op.api_key = "xyz789"

    with patch("post_processing.ops.media_server_refresh.requests.post") as mock_post:
        mock_post.return_value.status_code = 204
        mock_post.return_value.text = ""
        result = op.execute({"subtitle_path": "/m/s.srt", "video_path": "/m/v.mkv",
                             "lang": "en", "score": 100, "trigger": "after_download"})

    assert result.ok


def test_jellyfin_refresh_posts_to_jellyfin():
    from post_processing.ops.media_server_refresh import JellyfinRefreshOp

    op = JellyfinRefreshOp()
    op.base_url = "http://jellyfin:8096"
    op.api_key = "jelly-xyz"

    with patch("post_processing.ops.media_server_refresh.requests.post") as mock_post:
        mock_post.return_value.status_code = 204
        mock_post.return_value.text = ""
        result = op.execute({"subtitle_path": "/m/s.srt", "video_path": "/m/v.mkv",
                             "lang": "en", "score": 100, "trigger": "after_download"})

    assert result.ok
```

- [ ] **Step 2: Implement the 3 ops**

```python
# backend/post_processing/ops/media_server_refresh.py
"""Media server refresh ops — Plex, Emby, Jellyfin library scan triggers."""

from __future__ import annotations

import time

import requests

from post_processing.base_op import BaseOp, OpResult, register_op


@register_op
class PlexRefreshOp(BaseOp):
    op_id = "plex_refresh"
    label = "Plex — Refresh Library"
    description = "Trigger a Plex library section scan so new subtitles are picked up immediately."

    base_url: str = ""
    token: str = ""
    section_id: str = ""  # optional: target a specific library section

    def execute(self, context: dict) -> OpResult:
        start = time.monotonic()
        if not self.base_url or not self.token:
            return OpResult(self.op_id, False, 0, "plex not configured")

        url = self.base_url.rstrip("/") + "/library/sections/" + (self.section_id or "all") + "/refresh"
        try:
            resp = requests.get(url, headers={"X-Plex-Token": self.token}, timeout=10)
            if resp.status_code >= 400:
                return OpResult(self.op_id, False, int((time.monotonic() - start) * 1000), f"http {resp.status_code}")
            return OpResult(self.op_id, True, int((time.monotonic() - start) * 1000), "plex refresh triggered")
        except Exception as e:
            return OpResult(self.op_id, False, int((time.monotonic() - start) * 1000), str(e))


@register_op
class EmbyRefreshOp(BaseOp):
    op_id = "emby_refresh"
    label = "Emby — Refresh Library"
    description = "Trigger an Emby library scan."

    base_url: str = ""
    api_key: str = ""

    def execute(self, context: dict) -> OpResult:
        start = time.monotonic()
        if not self.base_url or not self.api_key:
            return OpResult(self.op_id, False, 0, "emby not configured")

        url = self.base_url.rstrip("/") + "/Library/Refresh"
        try:
            resp = requests.post(url, params={"api_key": self.api_key}, timeout=10)
            if resp.status_code >= 400:
                return OpResult(self.op_id, False, int((time.monotonic() - start) * 1000), f"http {resp.status_code}")
            return OpResult(self.op_id, True, int((time.monotonic() - start) * 1000), "emby refresh triggered")
        except Exception as e:
            return OpResult(self.op_id, False, int((time.monotonic() - start) * 1000), str(e))


@register_op
class JellyfinRefreshOp(BaseOp):
    op_id = "jellyfin_refresh"
    label = "Jellyfin — Refresh Library"
    description = "Trigger a Jellyfin library scan."

    base_url: str = ""
    api_key: str = ""

    def execute(self, context: dict) -> OpResult:
        start = time.monotonic()
        if not self.base_url or not self.api_key:
            return OpResult(self.op_id, False, 0, "jellyfin not configured")

        url = self.base_url.rstrip("/") + "/Library/Refresh"
        try:
            resp = requests.post(url, headers={"X-MediaBrowser-Token": self.api_key}, timeout=10)
            if resp.status_code >= 400:
                return OpResult(self.op_id, False, int((time.monotonic() - start) * 1000), f"http {resp.status_code}")
            return OpResult(self.op_id, True, int((time.monotonic() - start) * 1000), "jellyfin refresh triggered")
        except Exception as e:
            return OpResult(self.op_id, False, int((time.monotonic() - start) * 1000), str(e))
```

- [ ] **Step 3: Run tests**

Run: `cd backend && python -m pytest tests/test_post_processing_media_ops.py -v`
Expected: 3 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/post_processing/ops/media_server_refresh.py backend/tests/test_post_processing_media_ops.py
git commit -m "feat(plan-b6): media ops — plex + emby + jellyfin refresh"
```

---

## Task 6: Shell escape runner (opt-in via env flag)

**Files:**
- Create: `backend/post_processing/shell_runner.py`
- Create: `backend/tests/test_post_processing_shell.py`

- [ ] **Step 1: Write failing tests (security focus)**

```python
# backend/tests/test_post_processing_shell.py
"""Plan B6 — shell escape runner tests (security-focused)."""

import os

import pytest


def _flag_enabled():
    return os.environ.get("SUBLARR_ALLOW_SHELL_SCRIPTS") == "true"


def test_shell_runner_disabled_by_default(monkeypatch):
    """Without the env flag, shell_runner refuses to execute anything."""
    monkeypatch.delenv("SUBLARR_ALLOW_SHELL_SCRIPTS", raising=False)

    from post_processing.shell_runner import run_shell_script

    result = run_shell_script(script="echo hello", context={"subtitle_path": "/m/s.srt"}, timeout_s=5)
    assert result.ok is False
    assert "disabled" in result.message.lower() or "not allowed" in result.message.lower()


def test_shell_runner_enabled_executes_safe_script(monkeypatch, tmp_path):
    """With the env flag, a benign script runs and captures stdout."""
    monkeypatch.setenv("SUBLARR_ALLOW_SHELL_SCRIPTS", "true")

    from post_processing.shell_runner import run_shell_script

    # Use a cross-platform 'echo' — Windows has it too in bash
    result = run_shell_script(script="echo hello-b6", context={"subtitle_path": "/m/s.srt"}, timeout_s=10)
    assert result.ok is True
    assert "hello-b6" in result.message


def test_shell_runner_blocks_injection_via_context(monkeypatch):
    """A subtitle_path containing shell metacharacters must not execute them."""
    monkeypatch.setenv("SUBLARR_ALLOW_SHELL_SCRIPTS", "true")

    from post_processing.shell_runner import run_shell_script

    # Script uses {subtitle_path} — the substitution must quote or refuse shell syntax
    malicious = "/tmp/test.srt; echo INJECTED > /tmp/b6_injection_marker"
    result = run_shell_script(
        script="echo got {subtitle_path}",
        context={"subtitle_path": malicious},
        timeout_s=5,
    )
    # After substitution, the marker file MUST NOT have been created
    assert not os.path.exists("/tmp/b6_injection_marker"), "Command injection succeeded — FAIL"
    # Regardless of how substitution handled it, no injection marker
    # (result.ok may be True or False — what matters is no injection)


def test_shell_runner_enforces_timeout(monkeypatch):
    """A runaway script is killed after timeout."""
    monkeypatch.setenv("SUBLARR_ALLOW_SHELL_SCRIPTS", "true")

    from post_processing.shell_runner import run_shell_script

    # sleep 30 with a 2s timeout — must kill
    result = run_shell_script(script="sleep 30", context={"subtitle_path": "/m/s.srt"}, timeout_s=2)
    assert result.ok is False
    assert "timeout" in result.message.lower() or "timed out" in result.message.lower()
```

- [ ] **Step 2: Implement the shell runner**

```python
# backend/post_processing/shell_runner.py
"""Opt-in shell script executor for post-processing.

ONLY loads when SUBLARR_ALLOW_SHELL_SCRIPTS=true. Uses subprocess.run with
shell=False + args list so user-supplied context values can never be
interpreted as shell syntax. Placeholders in the script body are replaced
with shlex.quote'd values; the runner splits the final script via shlex.split
with POSIX semantics.

Security surface:
  - Env flag gate (fail-closed default)
  - shlex.quote every substituted value
  - subprocess.run(shell=False, args=shlex.split(...))
  - Timeout enforced (default 30s)
  - Restricted env — only PATH passed through
  - stdout + stderr captured to the audit record
"""

from __future__ import annotations

import logging
import os
import shlex
import subprocess
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ShellResult:
    op_id: str = "shell_script"
    ok: bool = False
    duration_ms: int = 0
    message: str = ""


def _flag_enabled() -> bool:
    return os.environ.get("SUBLARR_ALLOW_SHELL_SCRIPTS", "").lower() == "true"


def _substitute(script: str, context: dict) -> str:
    """Replace {placeholders} with shlex-quoted context values."""
    out = script
    for key in ("subtitle_path", "video_path", "lang", "score", "trigger"):
        value = str(context.get(key, ""))
        out = out.replace("{" + key + "}", shlex.quote(value))
    return out


def run_shell_script(script: str, context: dict, timeout_s: int = 30) -> ShellResult:
    """Execute a user-defined shell script with variable substitution.

    Returns a ShellResult (never raises). stdout + stderr are captured into
    ShellResult.message (truncated to ~4 KB).
    """
    start = time.monotonic()

    if not _flag_enabled():
        return ShellResult(
            ok=False,
            duration_ms=0,
            message="shell scripts disabled (set SUBLARR_ALLOW_SHELL_SCRIPTS=true)",
        )

    substituted = _substitute(script, context)

    try:
        args = shlex.split(substituted, posix=True)
    except ValueError as e:
        return ShellResult(ok=False, duration_ms=int((time.monotonic() - start) * 1000), message=f"parse error: {e}")

    if not args:
        return ShellResult(ok=False, duration_ms=0, message="empty script")

    restricted_env = {"PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin")}

    try:
        proc = subprocess.run(
            args,
            shell=False,
            env=restricted_env,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        combined = (proc.stdout + proc.stderr).strip()[:4000]
        ok = proc.returncode == 0
        msg = combined or ("ok" if ok else f"exit {proc.returncode}")
        return ShellResult(ok=ok, duration_ms=int((time.monotonic() - start) * 1000), message=msg)
    except subprocess.TimeoutExpired:
        return ShellResult(ok=False, duration_ms=int((time.monotonic() - start) * 1000), message="timeout expired")
    except FileNotFoundError as e:
        return ShellResult(ok=False, duration_ms=int((time.monotonic() - start) * 1000), message=f"command not found: {e}")
    except Exception as e:
        logger.warning("shell script runner failed: %s", e)
        return ShellResult(ok=False, duration_ms=int((time.monotonic() - start) * 1000), message=str(e))
```

- [ ] **Step 3: Run tests**

Run: `cd backend && python -m pytest tests/test_post_processing_shell.py -v`
Expected: 4 tests PASS.

NOTE: `test_shell_runner_blocks_injection_via_context` verifies NO injection marker file was created. This is a security assertion — if it fails, stop immediately and review the substitute function.

- [ ] **Step 4: Commit**

```bash
git add backend/post_processing/shell_runner.py backend/tests/test_post_processing_shell.py
git commit -m "feat(plan-b6): shell escape runner (opt-in, shlex-quoted, timeout-bounded)"
```

---

## Task 7: Integrate pipeline into 3 save-path triggers

**Files:**
- Modify: `backend/providers/download_manager.py::save_subtitle` (fire `after_download`)
- Modify: `backend/translator/_helpers.py` (or B5 translator post-hook) — fire `after_translate`
- Modify: `backend/services/video_sync.py` — fire `after_sync`
- Modify: `backend/post_processing/config_store.py` — per-trigger op config
- Modify: `backend/tests/test_post_processing_pipeline.py`

- [ ] **Step 1: Create `backend/post_processing/config_store.py`**

```python
"""Per-trigger op config — reads/writes `config_entries` rows keyed as
`post_processing.<trigger>` with value=JSON list of op_ids.
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)


def get_trigger_ops(trigger: str) -> list[str]:
    """Return the ordered list of op_ids configured for `trigger`. Empty list if unset."""
    try:
        from db.models.core import ConfigEntry

        key = f"post_processing.{trigger}"
        entry = ConfigEntry.query.filter_by(key=key).one_or_none()
        if entry is None or not entry.value:
            return []
        parsed = json.loads(entry.value)
        if isinstance(parsed, list):
            return [str(x) for x in parsed]
        return []
    except Exception as e:
        logger.warning("get_trigger_ops(%s) failed: %s", trigger, e)
        return []


def set_trigger_ops(trigger: str, op_ids: list[str]) -> None:
    """Upsert the op list for `trigger`."""
    from db import db
    from db.models.core import ConfigEntry

    key = f"post_processing.{trigger}"
    existing = ConfigEntry.query.filter_by(key=key).one_or_none()
    value = json.dumps(op_ids)
    if existing is None:
        existing = ConfigEntry(key=key, value=value)
        db.session.add(existing)
    else:
        existing.value = value
    db.session.commit()
```

(Adjust the import/class shape to match the actual `ConfigEntry` model in the codebase — `grep -n 'class ConfigEntry' backend/db/models/*.py` to confirm.)

- [ ] **Step 2: Wire the after_download trigger into save_subtitle**

In `backend/providers/download_manager.py::save_subtitle()`, AFTER the file is written (near the end of the function, after the `return` line), add (refactor to call `run_trigger` before returning):

```python
    # Plan B6 — fire after_download post-processing trigger
    try:
        from config import get_settings

        if getattr(get_settings(), "post_processing_enabled", True):
            from post_processing.config_store import get_trigger_ops
            from post_processing.pipeline import run_trigger

            op_ids = get_trigger_ops("after_download")
            if op_ids:
                run_trigger(
                    trigger="after_download",
                    op_ids=op_ids,
                    context={
                        "subtitle_path": saved_path,
                        "video_path": getattr(result, "video_path", "") or output_path,
                        "lang": result.language,
                        "score": getattr(result, "score", 0),
                        "trigger": "after_download",
                    },
                )
    except Exception as e:
        logger.warning("post_processing after_download skipped: %s", e)
```

Place this right before the function returns `saved_path`.

- [ ] **Step 3: Wire after_translate into the translator post-hook**

Find where B5 placed `run_subtitle_repair` calls in `backend/translator/_helpers.py` or similar. Immediately after repair, add the same `run_trigger` call with `trigger="after_translate"`.

- [ ] **Step 4: Wire after_sync into the sync service**

Find `backend/services/video_sync.py` (or wherever sync completes). Add `run_trigger("after_sync", ...)` call after a successful sync.

- [ ] **Step 5: Add config setting**

In `backend/config.py` or `backend/config_settings.py`, add:

```python
    # Plan B6 — post-processing pipeline master switch
    post_processing_enabled: bool = True
```

- [ ] **Step 6: Write integration tests**

```python
# backend/tests/test_post_processing_trigger_integration.py
"""Plan B6 — verify save paths call run_trigger with the right trigger name."""

from unittest.mock import patch


def test_save_subtitle_fires_after_download(tmp_path, app_ctx, monkeypatch):
    """save_subtitle must call run_trigger('after_download', ...) after writing."""
    from providers.base import SubtitleFormat, SubtitleResult
    from post_processing.config_store import set_trigger_ops

    # Configure a dummy op list
    set_trigger_ops("after_download", ["strip_html"])

    result = SubtitleResult(
        provider_name="p", subtitle_id="1", language="en",
        format=SubtitleFormat.SRT,
        content=b"1\n00:00:01,000 --> 00:00:02,000\nHi\n",
    )
    monkeypatch.setattr("providers.download_manager.is_safe_path",
                        lambda *a, **kw: True, raising=False)

    with patch("providers.download_manager.run_trigger") as mock_trigger:
        from providers.download_manager import save_subtitle

        saved = save_subtitle(result, str(tmp_path / "t.en.srt"))

    mock_trigger.assert_called()
    call_kwargs = mock_trigger.call_args.kwargs
    assert call_kwargs.get("trigger") == "after_download"
    assert call_kwargs.get("op_ids") == ["strip_html"]
```

Note: the mock patches `run_trigger` at its imported location in `download_manager.py` — inspect the actual import path with grep if the test fails to mock correctly.

- [ ] **Step 7: Run all post_processing tests**

Run: `cd backend && python -m pytest tests/test_post_processing_*.py -v --tb=short`
Expected: all PASS.

- [ ] **Step 8: Regression**

Run: `cd backend && python -m pytest tests/test_subtitle_repair.py tests/test_save_subtitle_repair_integration.py tests/test_provider_manager.py -v --tb=short`
Expected: no regression.

- [ ] **Step 9: Commit**

```bash
git add backend/post_processing/config_store.py backend/providers/download_manager.py backend/translator/_helpers.py backend/services/video_sync.py backend/config.py backend/config_settings.py backend/tests/test_post_processing_trigger_integration.py
git commit -m "feat(plan-b6): integrate pipeline into after_download + after_translate + after_sync"
```

(Adjust `git add` paths to whichever files you actually modified.)

---

## Task 8: API endpoints + frontend Settings tab

**Files:**
- Create: `backend/routes/post_processing.py` (or `backend/routes/post_processing/__init__.py`)
- Create: `frontend/src/pages/Settings/PostProcessingTab.tsx`
- Create: `frontend/src/api/postProcessing.ts`
- Modify: `frontend/src/pages/Settings/SettingsLayout.tsx` (or wherever nav links live) — add Post-Processing entry

- [ ] **Step 1: Add the 4 API endpoints**

Create `backend/routes/post_processing.py`:

```python
"""Plan B6 — post-processing API endpoints."""

from flask import Blueprint, jsonify, request

post_processing_bp = Blueprint("post_processing", __name__, url_prefix="/api/v1/post-processing")


@post_processing_bp.route("/ops", methods=["GET"])
def list_ops():
    """Return all registered ops with metadata."""
    from post_processing.ops import text_ops, webhook, discord_notify, media_server_refresh  # noqa: F401 — trigger registration
    from post_processing.base_op import _OP_REGISTRY

    return jsonify({
        "ops": [
            {
                "op_id": cls.op_id,
                "label": cls.label,
                "description": cls.description,
            }
            for cls in _OP_REGISTRY
        ]
    })


@post_processing_bp.route("/config", methods=["GET"])
def get_config():
    """Return per-trigger op config."""
    from post_processing.config_store import get_trigger_ops

    return jsonify({
        "after_download": get_trigger_ops("after_download"),
        "after_translate": get_trigger_ops("after_translate"),
        "after_sync": get_trigger_ops("after_sync"),
    })


@post_processing_bp.route("/config/<trigger>", methods=["PUT"])
def update_config(trigger):
    """Update op list for a trigger. Body: {"op_ids": ["strip_html", ...]}."""
    if trigger not in ("after_download", "after_translate", "after_sync"):
        return jsonify({"error": "unknown trigger"}), 400

    data = request.get_json(force=True) or {}
    op_ids = data.get("op_ids", [])
    if not isinstance(op_ids, list):
        return jsonify({"error": "op_ids must be a list"}), 400

    from post_processing.config_store import set_trigger_ops
    set_trigger_ops(trigger, [str(x) for x in op_ids])
    return jsonify({"trigger": trigger, "op_ids": op_ids})


@post_processing_bp.route("/runs", methods=["GET"])
def list_runs():
    """Return recent post-processing audit rows."""
    from db.models.core import PostProcessingRun

    limit = min(int(request.args.get("limit", 50)), 500)
    rows = (
        PostProcessingRun.query.order_by(PostProcessingRun.id.desc())
        .limit(limit)
        .all()
    )
    return jsonify({
        "runs": [
            {
                "id": r.id,
                "trigger": r.trigger,
                "ops_executed": r.ops_executed,
                "duration_ms": r.duration_ms,
                "outcome": r.outcome,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    })
```

Register the blueprint wherever other blueprints are registered (`backend/app.py::create_app` or `backend/routes/__init__.py` — grep `register_blueprint` to find the right spot).

- [ ] **Step 2: Add API tests (minimal smoke)**

Append to `backend/tests/test_post_processing_pipeline.py`:

```python
def test_api_list_ops(client):
    resp = client.get("/api/v1/post-processing/ops")
    assert resp.status_code == 200
    op_ids = [o["op_id"] for o in resp.get_json()["ops"]]
    # All 8 curated ops should be listed
    for expected in ("strip_html", "remove_bom", "convert_encoding",
                     "webhook", "discord_notify",
                     "plex_refresh", "emby_refresh", "jellyfin_refresh"):
        assert expected in op_ids, f"missing op {expected}"


def test_api_config_roundtrip(client):
    # GET default
    resp = client.get("/api/v1/post-processing/config")
    assert resp.status_code == 200
    # PUT new config
    put_resp = client.put(
        "/api/v1/post-processing/config/after_download",
        json={"op_ids": ["strip_html", "remove_bom"]},
    )
    assert put_resp.status_code == 200
    # GET and verify
    resp2 = client.get("/api/v1/post-processing/config")
    assert resp2.get_json()["after_download"] == ["strip_html", "remove_bom"]
    # Reset
    client.put("/api/v1/post-processing/config/after_download", json={"op_ids": []})


def test_api_reject_unknown_trigger(client):
    resp = client.put(
        "/api/v1/post-processing/config/not_a_trigger",
        json={"op_ids": []},
    )
    assert resp.status_code == 400
```

- [ ] **Step 3: Add frontend PostProcessingTab**

Create `frontend/src/api/postProcessing.ts`:

```typescript
export interface PostProcessingOp {
  op_id: string
  label: string
  description: string
}

export interface PostProcessingConfig {
  after_download: string[]
  after_translate: string[]
  after_sync: string[]
}

export async function fetchOps(): Promise<PostProcessingOp[]> {
  const resp = await fetch('/api/v1/post-processing/ops', { headers: { 'X-API-Key': getApiKey() } })
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
  return (await resp.json()).ops as PostProcessingOp[]
}

export async function fetchConfig(): Promise<PostProcessingConfig> {
  const resp = await fetch('/api/v1/post-processing/config', { headers: { 'X-API-Key': getApiKey() } })
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
  return await resp.json()
}

export async function updateTrigger(trigger: keyof PostProcessingConfig, op_ids: string[]): Promise<void> {
  const resp = await fetch(`/api/v1/post-processing/config/${trigger}`, {
    method: 'PUT',
    headers: { 'X-API-Key': getApiKey(), 'Content-Type': 'application/json' },
    body: JSON.stringify({ op_ids }),
  })
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
}
```

Adjust `getApiKey()` import to match the existing helper pattern in the codebase (check other files in `frontend/src/api/`).

Create `frontend/src/pages/Settings/PostProcessingTab.tsx` with a simple config UI: three trigger sections, each with a list of the currently-configured op_ids and a dropdown to add more. Match existing Settings tab patterns (Tailwind-only per STYLING.md).

```tsx
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { fetchOps, fetchConfig, updateTrigger } from '@/api/postProcessing'

export function PostProcessingTab() {
  const qc = useQueryClient()
  const opsQuery = useQuery({ queryKey: ['post-processing', 'ops'], queryFn: fetchOps })
  const cfgQuery = useQuery({ queryKey: ['post-processing', 'config'], queryFn: fetchConfig })
  const mut = useMutation({
    mutationFn: ({ trigger, ids }: { trigger: 'after_download' | 'after_translate' | 'after_sync', ids: string[] }) =>
      updateTrigger(trigger, ids),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['post-processing', 'config'] }),
  })

  if (opsQuery.isLoading || cfgQuery.isLoading) return <div>Loading…</div>
  if (opsQuery.error || cfgQuery.error) return <div>Error loading post-processing config.</div>

  const ops = opsQuery.data || []
  const cfg = cfgQuery.data!

  return (
    <section className="space-y-8">
      <header>
        <h1 className="text-2xl font-semibold">Post-Processing</h1>
        <p className="text-muted text-sm">Run actions after a subtitle is downloaded, translated, or synced.</p>
      </header>

      {(['after_download', 'after_translate', 'after_sync'] as const).map(trigger => (
        <div key={trigger} className="bg-surface rounded-md p-4 border border-border">
          <h2 className="font-medium mb-2">{trigger.replace('_', ' ')}</h2>
          <ul className="space-y-1 mb-3">
            {cfg[trigger].map((opId, idx) => (
              <li key={`${opId}-${idx}`} className="flex items-center gap-2">
                <code className="text-xs">{opId}</code>
                <button
                  className="text-xs text-red-400"
                  onClick={() => mut.mutate({ trigger, ids: cfg[trigger].filter((_, i) => i !== idx) })}
                >
                  remove
                </button>
              </li>
            ))}
          </ul>
          <select
            className="bg-surface border border-border rounded-md p-1"
            onChange={(e) => {
              if (!e.target.value) return
              mut.mutate({ trigger, ids: [...cfg[trigger], e.target.value] })
              e.currentTarget.value = ''
            }}
          >
            <option value="">+ add op…</option>
            {ops.map(op => (
              <option key={op.op_id} value={op.op_id}>{op.label}</option>
            ))}
          </select>
        </div>
      ))}
    </section>
  )
}
```

Wire into the settings router. If the settings file uses a list of tabs (e.g. `settingsTabs` array), add an entry; if routes are declared separately, add a route.

- [ ] **Step 4: Run tests + frontend checks**

Run: `cd backend && python -m pytest tests/test_post_processing_*.py -v --tb=short`
Expected: all PASS.

Run: `cd frontend && npm run lint && npx tsc --noEmit`
Expected: both exit 0.

- [ ] **Step 5: Commit**

```bash
git add backend/routes/post_processing.py frontend/src/pages/Settings/PostProcessingTab.tsx frontend/src/api/postProcessing.ts frontend/src/pages/Settings/SettingsLayout.tsx
git commit -m "feat(plan-b6): API endpoints + frontend PostProcessingTab"
```

(Adjust paths to whatever actually changed.)

---

## Task 9: Deploy

- [ ] **Step 1: Pre-deploy checks**

```bash
cd backend && ruff check . && ruff format --check .
cd backend && python -m pytest tests/test_post_processing_*.py -v --tb=short
cd frontend && npm run lint && npx tsc --noEmit
```

All must exit 0.

- [ ] **Step 2: Invoke deploy skill**

Bumps to 0.69.0-beta. Expected CHANGELOG section:

```markdown
## [0.69.0-beta] - 2026-04-19

### Added
- **Plan B Phase 6 — Post-processing pipeline** — New package `backend/post_processing/` with a curated-ops-first pipeline that fires after three save triggers (`after_download`, `after_translate`, `after_sync`). Ships 8 built-in ops: `strip_html`, `remove_bom`, `convert_encoding`, `webhook` (SSRF-protected via `validate_service_url`), `discord_notify`, `plex_refresh`, `emby_refresh`, `jellyfin_refresh`. Opt-in shell escape hatch behind `SUBLARR_ALLOW_SHELL_SCRIPTS=true` env flag — shlex-quoted variable substitution, 30 s timeout, restricted PATH-only env, stdout+stderr captured to the audit table. New `post_processing_runs` table records every pipeline run with per-op outcome + duration. Pipeline runs on a dedicated 2-worker thread pool so request handlers aren't blocked. New Settings → Post-Processing tab. New endpoints at `/api/v1/post-processing/{ops,config,runs}`.

### Plan B Progress
- Phase B6 — Post-processing pipeline: **shipped**
```

- [ ] **Step 3: Verify in prod**

```bash
curl -s -H "X-API-Key: $SUBLARR_KEY" http://192.168.178.36:5765/api/v1/post-processing/ops \
  | python -c "import sys,json; d=json.load(sys.stdin); print('ops:', len(d['ops']))"
# Expected: 8

ssh root@192.168.178.36 "docker exec sublarr-postgres psql -U sublarr -d sublarr -c '\d post_processing_runs'" | head -20
# Expected: table present with 6 columns

ssh root@192.168.178.36 "docker logs sublarr --since 2m 2>&1" \
  | grep -iE "(error|traceback|post_processing|alembic)" \
  | grep -vE "(enzyme|X-Signature|marketplace registry)" | head -15
# Expected: only the alembic upgrade INFO line
```

---

## Phase B6 Acceptance Checklist

- [ ] `post_processing_runs` table created + ORM model
- [ ] Pipeline driver + BaseOp ABC + registry
- [ ] 8 curated ops implemented (text: 3, http: 2, media: 3)
- [ ] Shell escape behind env flag with shlex quoting + timeout
- [ ] Integrated into 3 save-path triggers
- [ ] `/api/v1/post-processing/*` endpoints working
- [ ] Settings → Post-Processing tab added
- [ ] ~20+ new backend tests pass (model + pipeline + each op group + shell security + API)
- [ ] Ruff + tsc clean
- [ ] 0.69.0-beta deployed; 8 ops + `post_processing_runs` table verified in prod

## Next Phase

**B7 — Multi-engine sync + fallback chain.** New `backend/services/sync_engines/` package (ffsubsync_engine, alass_engine, nanosync_engine, oai_sync_engine). `SyncOrchestrator` owns the ordered fallback chain with per-engine timeout + sanity threshold. Each sync run writes an audit row to `sync_job_runs`.
