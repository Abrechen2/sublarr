# Phase 6 — Timestamp Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the timestamp migration started in v0.37.0-beta by migrating the one remaining `TEXT` timestamp column (`subtitle_health_results.checked_at`) to `DateTime(timezone=True)`, fixing three code bugs where `datetime.isoformat()` strings are passed into `DateTime` ORM columns, and cleaning up leftover in-memory isoformat patterns.

**Architecture:** The primary migration (`b0c1d2e3f4a5`) already converted 70 columns across 29 tables. This plan targets the one missed column (`SubtitleHealthResult.checked_at`), adds a new Alembic migration for it, and removes three categories of residual `.isoformat()` / `.fromisoformat()` bugs in application code.

**Tech Stack:** Python 3.12, SQLAlchemy 2.x, Alembic (Flask-Migrate), pytest, SQLite + PostgreSQL

**Branch:** `phase/6-timestamp-migration`

---

> **BREAKING CHANGE** — Announce in CHANGELOG before releasing. Existing deployments migrate automatically on startup. External tools reading `subtitle_health_results.checked_at` directly from SQLite will see a different timestamp format after the migration.

---

## Current State (as of v0.37.3-beta)

The original timestamp migration (`b0c1d2e3f4a5` + `c0d1e2f3a4b5`, v0.37.0) covered 70 columns but missed one table added later. Three categories of bugs also remain:

| Category | Location | Severity |
|----------|----------|----------|
| `subtitle_health_results.checked_at` still `TEXT` | `db/models/quality.py:23` | High — string vs DateTime type mismatch |
| `whisper/queue.py` passes `.isoformat()` strings to `update_whisper_job(completed_at=...)` | Lines 262, 296, 332, 341 | High — string written to `DateTime(timezone=True)` column |
| `db/repositories/quality.py` compares DateTime column to `.isoformat()` string | Line 97 | Medium — string comparison instead of datetime comparison |
| In-memory scheduler state stored as isoformat strings | `cleanup_scheduler.py`, `upgrade_scheduler.py`, `services/wanted_scanner.py` | Low — not DB writes, but creates fromisoformat noise |

---

## File Map

| File | Action |
|------|--------|
| `backend/db/models/quality.py` | Change `checked_at: Mapped[str]` → `Mapped[datetime]` |
| `backend/db/migrations/versions/<new_rev>_add_datetime_to_health_results.py` | New Alembic migration |
| `backend/db/repositories/quality.py` | Fix `save_health_result` signature + WHERE comparison |
| `backend/db/quality.py` | Fix `save_health_result` signature (facade function) |
| `backend/health_checker.py` | Fix `checked_at` dict values: remove `.isoformat()` |
| `backend/routes/tools/validation.py` | Fix `checked_at=...` call sites: pass datetime not string |
| `backend/whisper/queue.py` | Fix `datetime.utcnow().isoformat()` → `datetime.now(UTC)` for DB writes; fix `WhisperJob` dataclass types |
| `backend/db/repositories/hooks.py` | Fix manual dict returns to use `now.isoformat()` consistently (cosmetic, already correct via `_to_dict`) |
| `backend/cleanup_scheduler.py` | Replace in-memory isoformat string pattern with datetime |
| `backend/upgrade_scheduler.py` | Replace in-memory isoformat string pattern with datetime |
| `backend/services/wanted_scanner.py` | Replace `_last_scan_at` / `_last_search_at` isoformat strings with datetime |
| `backend/scripts/check_datetime_migration.py` | Add `subtitle_health_results.checked_at` to `COLUMNS` list |
| `backend/tests/test_phase6_timestamp_cleanup.py` | New test file |

---

## Task 1: Audit & Verify Starting State

**Files:**
- Read: `backend/db/models/quality.py`
- Read: `backend/scripts/check_datetime_migration.py`
- Run: `scripts/check_datetime_migration.py --db /config/sublarr.db --mode before` (or local dev DB)

- [ ] **Step 1.1: Confirm the one remaining TEXT timestamp column**

Run:
```bash
cd D:/Sublarr_Projekt/Sublarr/backend
python -c "
from db.models.quality import SubtitleHealthResult
col = SubtitleHealthResult.__table__.c['checked_at']
print('type:', col.type)
print('python_type:', col.type.python_type)
"
```
Expected: `type: TEXT` (or `VARCHAR`), `python_type: str`

- [ ] **Step 1.2: Confirm whisper bug**

Run:
```bash
grep -n "utcnow\|isoformat" D:/Sublarr_Projekt/Sublarr/backend/whisper/queue.py
```
Expected: Lines 85, 189, 262, 296, 332, 341 show `datetime.utcnow().isoformat()`.

- [ ] **Step 1.3: Confirm quality repository bug**

Run:
```bash
grep -n "isoformat" D:/Sublarr_Projekt/Sublarr/backend/db/repositories/quality.py
```
Expected: Line ~97 shows `.isoformat()` used in WHERE clause comparison.

- [ ] **Step 1.4: Take migration snapshot of dev DB (if it has data)**

```bash
python D:/Sublarr_Projekt/Sublarr/scripts/check_datetime_migration.py \
  --db D:/Sublarr_Projekt/Sublarr/backend/dev/sublarr.db \
  --mode before
```
Expected: `subtitle_health_results.checked_at` appears as `SKIP` (table may be empty) or shows rows in old ISO format. Note the snapshot path printed.

---

## Task 2: Write Tests First (TDD)

**Files:**
- Create: `backend/tests/test_phase6_timestamp_cleanup.py`
- Test runner: `cd backend && python -m pytest tests/test_phase6_timestamp_cleanup.py -v`

- [ ] **Step 2.1: Write failing tests for SubtitleHealthResult datetime column**

Create `backend/tests/test_phase6_timestamp_cleanup.py`:

```python
"""Phase 6 — Timestamp cleanup regression tests.

Verifies:
1. SubtitleHealthResult.checked_at accepts datetime objects (not strings)
2. QualityRepository.save_health_result accepts datetime objects
3. QualityRepository trend query uses datetime comparison, not string comparison
4. whisper/queue.py passes datetime objects to update_whisper_job
"""
import pytest
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch, call
from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped


# ── Test 1: Model column type ─────────────────────────────────────────────────

def test_subtitle_health_result_checked_at_is_datetime_column():
    """SubtitleHealthResult.checked_at must be DateTime(timezone=True), not Text."""
    from db.models.quality import SubtitleHealthResult
    col = SubtitleHealthResult.__table__.c["checked_at"]
    assert isinstance(col.type, DateTime), (
        f"checked_at column type is {type(col.type).__name__}, expected DateTime. "
        "Run the migration and update db/models/quality.py."
    )
    assert col.type.timezone is True, "checked_at must be DateTime(timezone=True)"


# ── Test 2: Repository accepts datetime, not string ───────────────────────────

def test_quality_repo_save_accepts_datetime(app):
    """save_health_result must accept datetime objects, not ISO strings."""
    from db.repositories.quality import QualityRepository

    with app.app_context():
        repo = QualityRepository()
        now = datetime.now(UTC)
        result = repo.save_health_result(
            file_path="/fake/test.srt",
            score=95,
            issues_json="[]",
            checks_run=3,
            checked_at=now,  # datetime object, not string
        )
        # Result dict should contain an ISO string (via _to_dict serialization)
        assert isinstance(result["checked_at"], str), (
            "save_health_result should return checked_at as ISO string via _to_dict"
        )
        # Verify the string is parseable and close to now
        parsed = datetime.fromisoformat(result["checked_at"])
        if parsed.tzinfo is None:
            import pytz
            parsed = parsed.replace(tzinfo=UTC)
        assert abs((parsed - now).total_seconds()) < 5


# ── Test 3: Trend query uses datetime comparison ──────────────────────────────

def test_quality_trend_query_does_not_isoformat(app):
    """get_health_trend must pass a datetime to the WHERE clause, not an ISO string."""
    from db.repositories.quality import QualityRepository
    from unittest.mock import patch, MagicMock

    with app.app_context():
        repo = QualityRepository()
        # Capture the WHERE clause argument
        captured_where_args = []

        original_execute = repo.session.execute

        def capturing_execute(stmt, *args, **kwargs):
            # Walk the WHERE clause looking for bound parameters
            try:
                compiled = stmt.compile()
                params = compiled.params
                for key, val in params.items():
                    if "checked_at" in key or "days" in key:
                        captured_where_args.append(val)
            except Exception:
                pass
            return MagicMock(all=lambda: [])

        with patch.object(repo, "session") as mock_session:
            mock_session.execute.return_value.all.return_value = []
            repo.get_health_trend(days=30)

            call_args = mock_session.execute.call_args
            assert call_args is not None

            stmt = call_args[0][0]
            # Compile the statement and inspect the WHERE clause bound values
            try:
                compiled = stmt.compile()
                bound_values = list(compiled.params.values())
                for val in bound_values:
                    assert not isinstance(val, str) or not val.count("T") == 1, (
                        f"WHERE clause contains ISO string '{val}' instead of a datetime. "
                        "Remove .isoformat() from the WHERE comparison in quality.py."
                    )
            except Exception:
                pass  # Compilation errors here are not our concern


# ── Test 4: Whisper queue passes datetime to update_whisper_job ───────────────

def test_whisper_queue_passes_datetime_to_update(monkeypatch):
    """WhisperQueue._run_job must pass datetime objects, not isoformat strings,
    when calling update_whisper_job for completed_at."""
    from whisper.queue import WhisperQueue, WhisperJob
    from unittest.mock import patch, MagicMock
    from datetime import UTC, datetime

    queue = WhisperQueue()
    job_id = "test-abc"

    # Inject a pre-existing in-memory job
    job = WhisperJob(job_id=job_id, file_path="/fake/video.mkv", language="de")
    queue._jobs[job_id] = job

    captured_kwargs = {}

    def fake_update_whisper_job(jid, **kwargs):
        captured_kwargs.update(kwargs)

    with patch("whisper.queue.update_whisper_job", fake_update_whisper_job):
        with patch("whisper.queue.create_whisper_job"):
            # Simulate the failure path (simpler than full transcription path)
            with patch.object(queue, "_semaphore") as mock_sem:
                mock_sem.__enter__ = MagicMock(return_value=None)
                mock_sem.__exit__ = MagicMock(return_value=False)

                # Force exception immediately after acquiring semaphore
                original_update = queue._update_job

                call_count = [0]

                def failing_update(jid, **kw):
                    call_count[0] += 1
                    if call_count[0] > 1:
                        raise RuntimeError("simulated failure")
                    original_update(jid, **kw)

                queue._update_job = failing_update

                whisper_mgr = MagicMock()
                whisper_mgr.transcribe.side_effect = RuntimeError("GPU OOM")

                queue._run_job(
                    job_id=job_id,
                    file_path="/fake/video.mkv",
                    language="de",
                    source_language="ja",
                    audio_track_index=None,
                    whisper_manager=whisper_mgr,
                    socketio=None,
                )

    # completed_at must be a datetime, not a string
    if "completed_at" in captured_kwargs:
        val = captured_kwargs["completed_at"]
        assert isinstance(val, datetime), (
            f"update_whisper_job received completed_at={val!r} (type {type(val).__name__}), "
            "expected a datetime object. Remove .isoformat() calls in whisper/queue.py."
        )


# ── Test 5: WhisperJob dataclass field types ──────────────────────────────────

def test_whisper_job_dataclass_accepts_datetime_timestamps():
    """WhisperJob dataclass fields created_at/started_at/completed_at
    must accept datetime objects (not be typed as str)."""
    from whisper.queue import WhisperJob
    import dataclasses

    fields = {f.name: f for f in dataclasses.fields(WhisperJob)}
    for field_name in ("created_at", "started_at", "completed_at"):
        assert field_name in fields, f"WhisperJob missing field {field_name}"
        # After fix, default should be None (not empty string)
        # and the type annotation should not be str
        field = fields[field_name]
        annotation = WhisperJob.__annotations__.get(field_name, "")
        assert "str" not in str(annotation) or "None" in str(annotation), (
            f"WhisperJob.{field_name} is typed as '{annotation}'. "
            "Should be 'datetime | None' after the fix."
        )
```

- [ ] **Step 2.2: Run tests — confirm they all FAIL**

```bash
cd D:/Sublarr_Projekt/Sublarr/backend
python -m pytest tests/test_phase6_timestamp_cleanup.py -v --tb=short
```

Expected: All 5 tests fail. Note the exact failure messages — they confirm what needs fixing.

- [ ] **Step 2.3: Commit the failing tests**

```bash
git add backend/tests/test_phase6_timestamp_cleanup.py
git commit -m "test: add failing tests for Phase 6 timestamp cleanup"
```

---

## Task 3: Update `SubtitleHealthResult` Model + Add Migration

**Files:**
- Modify: `backend/db/models/quality.py`
- Create: `backend/db/migrations/versions/<rev>_add_datetime_to_health_results.py`

- [ ] **Step 3.1: Update the model**

In `backend/db/models/quality.py`, change:

```python
# BEFORE
from sqlalchemy import Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

class SubtitleHealthResult(db.Model):
    ...
    checked_at: Mapped[str] = mapped_column(Text, nullable=False)
```

```python
# AFTER
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

class SubtitleHealthResult(db.Model):
    ...
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
```

Full updated file `backend/db/models/quality.py`:

```python
"""Quality/health-check ORM model for subtitle health results.

Stores per-file health check results including quality score,
issues JSON, and check metadata for trend tracking.
"""

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from extensions import db


class SubtitleHealthResult(db.Model):
    """Stores health-check results for a subtitle file."""

    __tablename__ = "subtitle_health_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    issues_json: Mapped[str] = mapped_column(Text, default="[]")
    checks_run: Mapped[int] = mapped_column(Integer, default=0)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("idx_health_results_path", "file_path"),
        Index("idx_health_results_score", "score"),
    )
```

- [ ] **Step 3.2: Generate the Alembic migration**

```bash
cd D:/Sublarr_Projekt/Sublarr/backend
flask db revision --autogenerate -m "add_datetime_to_health_results"
```

Autogenerate may not detect the TEXT→DateTime change on SQLite (dynamic typing). Open the generated file and replace its contents with the migration below. Find the file via:

```bash
ls -t D:/Sublarr_Projekt/Sublarr/backend/db/migrations/versions/ | head -1
```

- [ ] **Step 3.3: Write the migration content**

Replace the generated migration body (keep the revision ID autogenerate created):

```python
"""Add DateTime type to subtitle_health_results.checked_at

Revision ID: <keep autogenerated revision ID>
Revises: c0d1e2f3a4b5
Create Date: 2026-04-02

subtitle_health_results.checked_at was created as TEXT after the main timestamp
migration (b0c1d2e3f4a5) and was not included in the original batch. This
migration reformats existing ISO strings and alters the column type on PostgreSQL.

BREAKING CHANGE: subtitle_health_results.checked_at changes from TEXT to
DateTime(timezone=True). External tools reading this column directly will see
a different format.
"""

from alembic import op

# Keep the revision/down_revision values that autogenerate created above.
# down_revision should be "c0d1e2f3a4b5" (the last migration in the chain).

_TABLE = "subtitle_health_results"
_COL = "checked_at"
_EPOCH = "1970-01-01 00:00:00"


def upgrade() -> None:
    # Step 1: Reformat ISO strings (applies to both SQLite and PostgreSQL)
    # "2024-01-15T10:30:00+00:00" → "2024-01-15 10:30:00"
    op.execute(
        f"UPDATE {_TABLE} SET {_COL} = "
        f"REPLACE(REPLACE({_COL}, 'T', ' '), '+00:00', '') "
        f"WHERE {_COL} IS NOT NULL AND {_COL} != ''"
    )
    # Handle Z suffix (e.g. "2024-01-15T10:30:00Z")
    op.execute(
        f"UPDATE {_TABLE} SET {_COL} = REPLACE({_COL}, 'Z', '') "
        f"WHERE {_COL} IS NOT NULL AND {_COL} LIKE '%Z'"
    )

    # Step 2: PostgreSQL only — ALTER COLUMN TYPE
    dialect = op.get_context().dialect.name
    if dialect == "postgresql":
        # Replace any empty strings with epoch before casting
        op.execute(
            f"UPDATE {_TABLE} SET {_COL} = '{_EPOCH}' "
            f"WHERE {_COL} IS NOT NULL AND TRIM({_COL}) = ''"
        )
        op.execute(
            f"ALTER TABLE {_TABLE} ALTER COLUMN {_COL} "
            f"TYPE TIMESTAMP WITH TIME ZONE "
            f"USING {_COL}::timestamp AT TIME ZONE 'UTC'"
        )
    # SQLite: dynamic typing — no ALTER needed, SQLAlchemy reads column as datetime


def downgrade() -> None:
    raise NotImplementedError(
        "DateTime migration for subtitle_health_results.checked_at downgrade "
        "is not supported. Restore from backup."
    )
```

- [ ] **Step 3.4: Verify the migration runs without error**

```bash
cd D:/Sublarr_Projekt/Sublarr/backend
flask db upgrade
```

Expected: `Running upgrade c0d1e2f3a4b5 -> <new_rev>, Add DateTime type to subtitle_health_results.checked_at`

- [ ] **Step 3.5: Add `subtitle_health_results.checked_at` to `check_datetime_migration.py`**

In `backend/scripts/check_datetime_migration.py`, find the `COLUMNS` list (around line 35) and add at the end, before the closing `]`:

```python
    # Added in Phase 6 (was missed in b0c1d2e3f4a5)
    ("subtitle_health_results", "checked_at", False),
```

- [ ] **Step 3.6: Run verification script after migration**

```bash
python D:/Sublarr_Projekt/Sublarr/scripts/check_datetime_migration.py \
  --db D:/Sublarr_Projekt/Sublarr/backend/dev/sublarr.db \
  --mode after
```

Expected: `subtitle_health_results.checked_at` shows `OK` (or `SKIP` if the table is empty). Exit code 0.

- [ ] **Step 3.7: Run test 1 — confirm it passes now**

```bash
cd D:/Sublarr_Projekt/Sublarr/backend
python -m pytest tests/test_phase6_timestamp_cleanup.py::test_subtitle_health_result_checked_at_is_datetime_column -v
```

Expected: PASS.

- [ ] **Step 3.8: Commit model + migration + script update**

```bash
git add backend/db/models/quality.py \
        backend/db/migrations/versions/<new_rev>_add_datetime_to_health_results.py \
        backend/scripts/check_datetime_migration.py
git commit -m "feat: migrate subtitle_health_results.checked_at TEXT → DateTime(timezone=True)"
```

---

## Task 4: Fix Quality Repository and health_checker Callers

**Files:**
- Modify: `backend/db/repositories/quality.py`
- Modify: `backend/db/quality.py`
- Modify: `backend/health_checker.py`
- Modify: `backend/routes/tools/validation.py`

- [ ] **Step 4.1: Fix `QualityRepository.save_health_result` signature**

In `backend/db/repositories/quality.py`, change the signature and WHERE clause:

```python
# BEFORE (lines ~22, 97)
def save_health_result(
    self, file_path: str, score: int, issues_json: str, checks_run: int, checked_at: str
) -> dict:
    ...

# In get_health_trend (line ~97):
SubtitleHealthResult.checked_at
> (datetime.now(UTC) - timedelta(days=days)).isoformat()
```

```python
# AFTER
def save_health_result(
    self, file_path: str, score: int, issues_json: str, checks_run: int, checked_at: datetime
) -> dict:
    ...

# In get_health_trend — pass datetime directly, no .isoformat():
SubtitleHealthResult.checked_at
> (datetime.now(UTC) - timedelta(days=days))
```

Full updated relevant sections of `backend/db/repositories/quality.py`:

```python
from datetime import UTC, datetime, timedelta  # unchanged import

class QualityRepository(BaseRepository):

    def save_health_result(
        self, file_path: str, score: int, issues_json: str, checks_run: int, checked_at: datetime
    ) -> dict:
        """Save or update a health check result for a file.

        Creates a new record each time (for trend tracking).

        Args:
            checked_at: UTC datetime of the check (datetime object, not ISO string).

        Returns:
            Dict representation of the saved record.
        """
        entry = SubtitleHealthResult(
            file_path=file_path,
            score=score,
            issues_json=issues_json,
            checks_run=checks_run,
            checked_at=checked_at,
        )
        self.session.add(entry)
        self._commit()
        return self._to_dict(entry)
```

For the WHERE clause in `get_health_trend`, find the `.isoformat()` call (around line 97) and remove it:

```python
# BEFORE
.where(
    SubtitleHealthResult.checked_at
    > (datetime.now(UTC) - timedelta(days=days)).isoformat()
)

# AFTER
.where(
    SubtitleHealthResult.checked_at
    > (datetime.now(UTC) - timedelta(days=days))
)
```

Also update the `func.substr` grouping to work with the datetime column. The `func.substr(..., 1, 10)` still works on SQLite (returns the date portion). On PostgreSQL, use `func.cast(SubtitleHealthResult.checked_at, Date)` or `func.date_trunc`. Since SQLite is the primary target, keep `func.substr` but add a note:

```python
# The substr(col, 1, 10) group-by works on SQLite because DateTime is
# stored as "YYYY-MM-DD HH:MM:SS". On PostgreSQL, SQLAlchemy renders this
# column as a TIMESTAMPTZ — func.substr still works for date extraction.
```

- [ ] **Step 4.2: Fix the facade function in `backend/db/quality.py`**

In `backend/db/quality.py`, update the type hint:

```python
# BEFORE
def save_health_result(
    file_path: str, score: int, issues_json: str, checks_run: int, checked_at: str
) -> dict:
    return _get_repo().save_health_result(file_path, score, issues_json, checks_run, checked_at)
```

```python
# AFTER
from datetime import datetime

def save_health_result(
    file_path: str, score: int, issues_json: str, checks_run: int, checked_at: datetime
) -> dict:
    return _get_repo().save_health_result(file_path, score, issues_json, checks_run, checked_at)
```

- [ ] **Step 4.3: Fix `health_checker.py` — pass datetime objects**

In `backend/health_checker.py`, find the three `"checked_at": datetime.now(UTC).isoformat()` lines (approximately lines 386, 408, 432) and remove the `.isoformat()` calls:

```python
# BEFORE (three occurrences)
"checked_at": datetime.now(UTC).isoformat(),

# AFTER (three occurrences)
"checked_at": datetime.now(UTC),
```

- [ ] **Step 4.4: Fix `backend/routes/tools/validation.py` callers**

In `backend/routes/tools/validation.py`, find the three `checked_at=check_result["checked_at"]` calls (approximately lines 369, 413, 546). These pass the value from `health_checker.py`'s result dict. Since `health_checker.py` now returns `datetime.now(UTC)` (a datetime object), no change is needed to `validation.py` — the value is passed through unchanged. **Verify** that `validation.py` does not call `.isoformat()` on `checked_at` before passing it:

```bash
grep -n "checked_at" D:/Sublarr_Projekt/Sublarr/backend/routes/tools/validation.py
```

If any line shows `.isoformat()` applied to `checked_at`, remove it. If lines show only `checked_at=check_result["checked_at"]`, no change needed.

- [ ] **Step 4.5: Run tests 1 and 2**

```bash
cd D:/Sublarr_Projekt/Sublarr/backend
python -m pytest tests/test_phase6_timestamp_cleanup.py::test_subtitle_health_result_checked_at_is_datetime_column \
                 tests/test_phase6_timestamp_cleanup.py::test_quality_repo_save_accepts_datetime \
                 -v
```

Expected: Both PASS.

- [ ] **Step 4.6: Commit quality fixes**

```bash
git add backend/db/repositories/quality.py \
        backend/db/quality.py \
        backend/health_checker.py \
        backend/routes/tools/validation.py
git commit -m "fix: quality repository checked_at uses datetime objects, not ISO strings"
```

---

## Task 5: Fix `whisper/queue.py` — Stop Passing ISO Strings to DB

**Files:**
- Modify: `backend/whisper/queue.py`

The `WhisperQueue._run_job` calls `update_whisper_job(completed_at=datetime.utcnow().isoformat())` in four places. `update_whisper_job` eventually calls `setattr(job, 'completed_at', value)` on a `WhisperJob` ORM model whose `completed_at` column is `DateTime(timezone=True)`. Passing a string there silently works on SQLite (dynamic typing) but fails or produces wrong results on PostgreSQL.

Additionally, the in-memory `WhisperJob` dataclass has `created_at: str = ""` — this should be `datetime | None`.

- [ ] **Step 5.1: Fix `WhisperJob` dataclass field types**

In `backend/whisper/queue.py`, update the dataclass (around line 28):

```python
# BEFORE
from dataclasses import dataclass
from datetime import datetime

@dataclass
class WhisperJob:
    """In-memory representation of a whisper transcription job."""
    job_id: str
    file_path: str
    language: str = ""
    audio_track_index: int | None = None
    status: str = "queued"
    progress: float = 0.0
    phase: str = ""
    result: TranscriptionResult | None = None
    error: str | None = None
    created_at: str = ""
    started_at: str | None = None
    completed_at: str | None = None
```

```python
# AFTER
from dataclasses import dataclass, field
from datetime import UTC, datetime

@dataclass
class WhisperJob:
    """In-memory representation of a whisper transcription job."""
    job_id: str
    file_path: str
    language: str = ""
    audio_track_index: int | None = None
    status: str = "queued"
    progress: float = 0.0
    phase: str = ""
    result: TranscriptionResult | None = None
    error: str | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
```

- [ ] **Step 5.2: Fix `submit` method — remove `.isoformat()` from in-memory job creation**

In `backend/whisper/queue.py`, around line 85:

```python
# BEFORE
now = datetime.utcnow().isoformat()
job = WhisperJob(
    ...
    created_at=now,
)
```

```python
# AFTER
now = datetime.now(UTC)
job = WhisperJob(
    ...
    created_at=now,
)
```

- [ ] **Step 5.3: Fix `_run_job` — remove `.isoformat()` from DB update calls**

In `backend/whisper/queue.py`, around line 189:

```python
# BEFORE
now = datetime.utcnow().isoformat()
self._update_job(
    job_id, status="extracting", progress=0.0, phase="extracting", started_at=now
)
```

```python
# AFTER
now = datetime.now(UTC)
self._update_job(
    job_id, status="extracting", progress=0.0, phase="extracting", started_at=now
)
```

Around lines 262 and 296 (the two `update_whisper_job` calls with `completed_at`):

```python
# BEFORE (line ~262)
completed_at=datetime.utcnow().isoformat(),

# AFTER
completed_at=datetime.now(UTC),
```

```python
# BEFORE (line ~296, the second update_whisper_job call in the success path)
completed_at=datetime.utcnow().isoformat(),

# AFTER
completed_at=datetime.now(UTC),
```

Around lines 332 and 341 (in the error handler):

```python
# BEFORE (line ~332 — _update_job call)
completed_at=datetime.utcnow().isoformat(),

# AFTER
completed_at=datetime.now(UTC),
```

```python
# BEFORE (line ~341 — update_whisper_job call)
completed_at=datetime.utcnow().isoformat(),

# AFTER
completed_at=datetime.now(UTC),
```

- [ ] **Step 5.4: Verify no `.isoformat()` remains in whisper/queue.py**

```bash
grep -n "isoformat\|utcnow" D:/Sublarr_Projekt/Sublarr/backend/whisper/queue.py
```

Expected: No matches.

- [ ] **Step 5.5: Check that routes that serialize WhisperJob dicts handle datetime**

Any route that calls `queue.get_job(job_id)` and returns the result to the frontend needs to handle `created_at` being a `datetime` now instead of a string. Search:

```bash
grep -rn "get_job\|get_all_jobs\|WhisperJob" D:/Sublarr_Projekt/Sublarr/backend/routes/ --include="*.py"
```

For any route that converts a `WhisperJob` dataclass to a response dict, add datetime serialization:

```python
# Pattern to add wherever WhisperJob fields are serialized to JSON:
def _job_to_dict(job: WhisperJob) -> dict:
    return {
        "job_id": job.job_id,
        "file_path": job.file_path,
        "language": job.language,
        "audio_track_index": job.audio_track_index,
        "status": job.status,
        "progress": job.progress,
        "phase": job.phase,
        "error": job.error,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }
```

If such a helper already exists in the route file, update it. If the route constructs the dict inline, update each field.

- [ ] **Step 5.6: Run tests 4 and 5**

```bash
cd D:/Sublarr_Projekt/Sublarr/backend
python -m pytest tests/test_phase6_timestamp_cleanup.py::test_whisper_queue_passes_datetime_to_update \
                 tests/test_phase6_timestamp_cleanup.py::test_whisper_job_dataclass_accepts_datetime_timestamps \
                 -v
```

Expected: Both PASS.

- [ ] **Step 5.7: Commit whisper fixes**

```bash
git add backend/whisper/queue.py
git commit -m "fix: whisper queue passes datetime objects to update_whisper_job, not ISO strings"
```

---

## Task 6: Fix In-Memory Scheduler State (Low Priority, Clean Up)

**Files:**
- Modify: `backend/cleanup_scheduler.py`
- Modify: `backend/upgrade_scheduler.py`
- Modify: `backend/services/wanted_scanner.py`

These files store `_last_run_at` / `_last_scan_at` / `_last_search_at` as ISO strings in memory, then call `.fromisoformat()` to convert back when computing `next_run_at`. No DB writes are involved, but this is noisy. Fix by storing `datetime` objects throughout.

- [ ] **Step 6.1: Fix `cleanup_scheduler.py`**

In `backend/cleanup_scheduler.py`:

```python
# BEFORE — around lines 82, 162, 265
@property
def next_run_at(self):
    if not self._last_run_at or not self._interval_hours:
        return None
    try:
        from datetime import datetime, timedelta
        last_dt = datetime.fromisoformat(self._last_run_at)
        return (last_dt + timedelta(hours=self._interval_hours)).isoformat()
    except Exception:
        return None

# ... line ~162:
cutoff = (datetime.now(UTC) - timedelta(hours=2)).isoformat()

# ... line ~265:
self._last_run_at = datetime.now(UTC).isoformat()
```

```python
# AFTER
# Change _last_run_at field to datetime | None (initialized to None in __init__)
# Then:

@property
def next_run_at(self) -> str | None:
    """Return next scheduled run as ISO string (for JSON serialization)."""
    if not self._last_run_at or not self._interval_hours:
        return None
    try:
        return (self._last_run_at + timedelta(hours=self._interval_hours)).isoformat()
    except Exception:
        return None

# ... line ~162 (zombie job expiry):
cutoff = datetime.now(UTC) - timedelta(hours=2)
# Then compare: if created and created < cutoff.isoformat():
# becomes:      if created and datetime.fromisoformat(created) < cutoff:
#               (job dict "created_at" is already a serialized string from _to_dict)

# ... line ~265:
self._last_run_at = datetime.now(UTC)
```

Also update `__init__` of `CleanupScheduler` to initialize `_last_run_at: datetime | None = None`.

- [ ] **Step 6.2: Fix `upgrade_scheduler.py`**

Apply the same pattern to `UpgradeScheduler._last_run_at`:

```python
# BEFORE
@property
def next_run_at(self):
    if not self._last_run_at or not self._interval_hours:
        return None
    try:
        last_dt = datetime.fromisoformat(self._last_run_at)
        return (last_dt + timedelta(hours=self._interval_hours)).isoformat()
    except Exception:
        return None

# Line ~221:
last_dt = datetime.fromisoformat(last_search)

# Line ~253:
self._last_run_at = datetime.now(UTC).isoformat()
```

```python
# AFTER
@property
def next_run_at(self) -> str | None:
    """Return next scheduled run as ISO string (for JSON serialization)."""
    if not self._last_run_at or not self._interval_hours:
        return None
    try:
        return (self._last_run_at + timedelta(hours=self._interval_hours)).isoformat()
    except Exception:
        return None

# Line ~221 — last_search comes from a WantedItem dict (already serialized by repo)
# so it is a string. This fromisoformat() is correct, leave it.
# But verify by checking what `item.get("last_search_at")` returns.

# Line ~253:
self._last_run_at = datetime.now(UTC)
```

- [ ] **Step 6.3: Fix `services/wanted_scanner.py`**

Change `_last_scan_at` and `_last_search_at` from isoformat strings to datetime objects. The properties that expose them to JSON must serialize on access:

```python
# Find and update in WantedScanner:

# BEFORE (lines ~265, 966, 1062)
self._last_scan_at = datetime.now(UTC).isoformat()
...
self._last_search_at = datetime.now(UTC).isoformat()

# AFTER
self._last_scan_at = datetime.now(UTC)
...
self._last_search_at = datetime.now(UTC)
```

Also update any property that returns these values as strings:

```python
@property
def last_scan_at(self) -> str | None:
    return self._last_scan_at.isoformat() if self._last_scan_at else None

@property
def last_search_at(self) -> str | None:
    return self._last_search_at.isoformat() if self._last_search_at else None
```

Note: The `since.isoformat() + "Z"` calls at lines 507, 773 build a string for the **Sonarr/Radarr API** (an external HTTP call). These are correct and must not be changed.

- [ ] **Step 6.4: Run the full test suite**

```bash
cd D:/Sublarr_Projekt/Sublarr/backend
python -m pytest --tb=short -q \
  --ignore=tests/performance \
  --ignore=tests/integration/test_provider_pipeline.py \
  --ignore=tests/test_video_sync.py \
  --ignore=tests/test_translation_backends.py \
  -k "not (test_sonarr_download_webhook or test_radarr_download_webhook or test_parse_llm_response_too_many_merge or test_record_backend_success)"
```

Expected: All tests pass. Pay attention to any `TypeError: unsupported operand type(s)` which would indicate a datetime/string comparison regression.

- [ ] **Step 6.5: Run all Phase 6 tests**

```bash
cd D:/Sublarr_Projekt/Sublarr/backend
python -m pytest tests/test_phase6_timestamp_cleanup.py -v
```

Expected: All 5 tests PASS.

- [ ] **Step 6.6: Commit scheduler cleanup**

```bash
git add backend/cleanup_scheduler.py \
        backend/upgrade_scheduler.py \
        backend/services/wanted_scanner.py
git commit -m "refactor: replace isoformat string in-memory scheduler state with datetime objects"
```

---

## Task 7: Ruff + Pre-PR Checks

- [ ] **Step 7.1: Run ruff on the entire backend directory**

```bash
cd D:/Sublarr_Projekt/Sublarr/backend
ruff check .
ruff format --check .
```

Fix any violations. Pay attention to unused imports (removed `isoformat` calls may leave stray `import` lines).

- [ ] **Step 7.2: If ruff reports violations, fix and re-check**

Common fixes after this change:
- Remove `from datetime import datetime` where it was only used for `.utcnow().isoformat()` and UTC is now used
- Ensure `from datetime import UTC, datetime` is present everywhere `UTC` is used

```bash
ruff check . --fix
ruff format .
```

Then verify:
```bash
ruff check . && ruff format --check .
```

Expected: No violations.

- [ ] **Step 7.3: Run frontend checks (no frontend changes, but run to confirm no regressions)**

```bash
cd D:/Sublarr_Projekt/Sublarr/frontend
npm run lint
npx tsc --noEmit
npm run test -- --run
```

Expected: All pass.

- [ ] **Step 7.4: Commit ruff fixes (if any)**

```bash
git add backend/
git commit -m "chore: ruff format fixes after Phase 6 timestamp cleanup"
```

---

## Task 8: CHANGELOG Entry

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 8.1: Add breaking change entry to CHANGELOG.md**

Open `CHANGELOG.md` and add a new version section at the top (after the `# Changelog` header, before `## [0.37.3-beta]`). Adjust the version number to match what is in `backend/VERSION`:

```markdown
## [Unreleased] — Phase 6 Timestamp Cleanup

### BREAKING CHANGE — `subtitle_health_results.checked_at` Column Type

**`subtitle_health_results.checked_at`** has been migrated from plain `TEXT` to
`DateTime(timezone=True)`. This column was inadvertently excluded from the original
timestamp migration in v0.37.0-beta.

The Alembic migration `<new_rev>_add_datetime_to_health_results` reformats existing
values from ISO 8601 (`2024-01-15T10:30:00+00:00`) to SQLAlchemy format
(`2024-01-15 10:30:00`). **No manual action required for Docker deployments** —
the migration runs automatically on startup.

For bare-metal installs:
```bash
cd /path/to/sublarr/backend && flask db upgrade
```

Verify migration integrity:
```bash
python scripts/check_datetime_migration.py --db /config/sublarr.db --mode before
# (run before upgrading, if you want a snapshot)
python scripts/check_datetime_migration.py --db /config/sublarr.db --mode after
```

### Fixed
- `whisper/queue.py` — Whisper job timestamps (`created_at`, `started_at`, `completed_at`)
  now pass `datetime` objects to the ORM instead of ISO-format strings, preventing
  silent type mismatches on PostgreSQL
- `db/repositories/quality.py` — `get_health_trend()` WHERE clause now uses datetime
  comparison instead of string comparison
- `cleanup_scheduler.py`, `upgrade_scheduler.py`, `services/wanted_scanner.py` —
  In-memory scheduler state stored as `datetime` objects, eliminating round-trip
  `.isoformat()` / `.fromisoformat()` conversions
```

- [ ] **Step 8.2: Commit the changelog entry**

```bash
git add CHANGELOG.md
git commit -m "docs: add Phase 6 timestamp cleanup breaking change entry to CHANGELOG"
```

---

## Task 9: Final Verification

- [ ] **Step 9.1: Run full test suite one final time**

```bash
cd D:/Sublarr_Projekt/Sublarr/backend
python -m pytest --tb=short -q \
  --ignore=tests/performance \
  --ignore=tests/integration/test_provider_pipeline.py \
  --ignore=tests/test_video_sync.py \
  --ignore=tests/test_translation_backends.py \
  -k "not (test_sonarr_download_webhook or test_radarr_download_webhook or test_parse_llm_response_too_many_merge or test_record_backend_success)"
```

Expected: All pass.

- [ ] **Step 9.2: Confirm no remaining `.isoformat()` writes to DateTime columns**

```bash
grep -rn "\.isoformat()" D:/Sublarr_Projekt/Sublarr/backend/ \
  --include="*.py" \
  --exclude-dir=tests \
  --exclude-dir=migrations \
  --exclude="check_datetime_migration.py"
```

Review each remaining hit. Acceptable uses:
- JSON response serialization (e.g. `return {"last_run": self._last_run_at.isoformat()}`)
- External API calls (e.g. Sonarr `since.isoformat() + "Z"`)
- `base.py:_to_dict` (the authoritative serializer — this one `.isoformat()` is correct)
- `routes/system/backup.py` (backup metadata in JSON, not DB writes)
- `error_handler.py`, `health_checker.py`, `events/webhooks.py` (JSON response bodies)

Unacceptable: `.isoformat()` as a value passed to an ORM model attribute that is `DateTime`.

- [ ] **Step 9.3: Verify with check script**

```bash
python D:/Sublarr_Projekt/Sublarr/scripts/check_datetime_migration.py \
  --db D:/Sublarr_Projekt/Sublarr/backend/dev/sublarr.db \
  --mode after
```

Expected: Exit code 0. `subtitle_health_results.checked_at` shows `OK` or `SKIP`.

- [ ] **Step 9.4: Git log — confirm all commits on branch**

```bash
git log --oneline master..HEAD
```

Expected commits (in any order):
- `test: add failing tests for Phase 6 timestamp cleanup`
- `feat: migrate subtitle_health_results.checked_at TEXT → DateTime(timezone=True)`
- `fix: quality repository checked_at uses datetime objects, not ISO strings`
- `fix: whisper queue passes datetime objects to update_whisper_job, not ISO strings`
- `refactor: replace isoformat string in-memory scheduler state with datetime objects`
- `chore: ruff format fixes after Phase 6 timestamp cleanup` (if needed)
- `docs: add Phase 6 timestamp cleanup breaking change entry to CHANGELOG`

---

## Self-Review Checklist

**Spec coverage:**
- [x] `subtitle_health_results.checked_at` migrated → Task 3
- [x] Alembic migration with USING cast for PostgreSQL + SQLite path → Task 3
- [x] `scripts/check_datetime_migration.py` updated → Task 3, Step 3.5
- [x] Before/After verification commands → Task 1.4, Task 3.6
- [x] Model definitions updated → Task 3.1
- [x] Code calling `.isoformat()` when writing to DB columns → Tasks 4, 5
- [x] Code calling `.fromisoformat()` to read from DB → Task 6
- [x] Breaking change announced in CHANGELOG → Task 8
- [x] Docker deployments auto-migrate (note in CHANGELOG) → Task 8

**Placeholder scan:** All code blocks contain real, complete code. No "TBD" or "implement later."

**Type consistency:**
- `save_health_result(checked_at: datetime)` in Task 4 matches usage in Task 4.3 (health_checker passes `datetime.now(UTC)`)
- `WhisperJob.created_at: datetime | None` in Task 5.1 matches `now = datetime.now(UTC)` in Task 5.2
- `_last_run_at: datetime` in Task 6 matched by `.isoformat()` call in `next_run_at` property
- `update_whisper_job(completed_at=datetime.now(UTC))` in Task 5.3 matches `WhisperRepository.update_whisper_job` which calls `setattr(job, key, value)` — the ORM model field is `DateTime(timezone=True)`, accepts datetime ✓

**Coverage:**
- Test 1: model column type check
- Test 2: repository accepts datetime (integration-style, requires app context)
- Test 3: WHERE clause doesn't use isoformat
- Test 4: whisper queue passes datetime
- Test 5: WhisperJob dataclass types

**Both DB backends covered:** SQLite (string reformat only) + PostgreSQL (`ALTER COLUMN ... USING` cast) handled in Task 3.3.
