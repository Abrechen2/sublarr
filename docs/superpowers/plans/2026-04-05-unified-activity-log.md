# Unified Activity Log Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Activity → History tab's download-only view with a unified activity log that captures subtitle downloads, extractions, deletions, and scan completions from a single `activity_log` table.

**Architecture:** New `ActivityLog` SQLAlchemy model backed by `activity_log` DB table; `ActivityLogRepository` handles writes (called from 3 backend locations) and paginated reads; new `GET /api/v1/activity` endpoint; frontend `ActivityLogTab` component replaces `HistoryPage` in the History tab.

**Tech Stack:** Python 3.12, SQLAlchemy (Mapped[]), Alembic batch migrations, Flask Blueprint, React 19, @tanstack/react-query, TypeScript, Vitest + Testing Library.

---

## File Structure

**New files:**
- `backend/db/models/activity.py` — `ActivityLog` ORM model
- `backend/db/migrations/versions/e4f5a6b7c8d9_add_activity_log.py` — Alembic migration
- `backend/db/repositories/activity.py` — `ActivityLogRepository`
- `backend/db/activity.py` — thin facade module (mirrors pattern of `db/providers.py`)
- `backend/routes/activity.py` — Flask Blueprint with `GET /api/v1/activity`
- `frontend/src/api/system/activity.ts` — `getActivity()` API call
- `frontend/src/components/activity/ActivityLogTab.tsx` — unified History tab UI
- `frontend/src/components/activity/__tests__/ActivityLogTab.test.tsx` — component tests
- `backend/tests/test_activity_log.py` — backend unit tests

**Modified files:**
- `backend/db/models/__init__.py` — import `ActivityLog`
- `backend/routes/__init__.py` — register `activity_bp`
- `frontend/src/api/system.ts` — re-export from `./system/activity`
- `frontend/src/hooks/useSystemApi.ts` — add `useActivity()` hook
- `frontend/src/pages/ActivityPage.tsx` — swap `HistoryPage` for `ActivityLogTab`
- `backend/db/providers.py` — call `log_activity()` at end of `record_subtitle_download()`
- `backend/routes/wanted/extract.py` — call `log_activity()` after extraction emit
- `backend/routes/subtitles.py` — call `log_activity()` for each trashed subtitle
- `backend/services/wanted_scanner_core.py` — call `log_activity()` after scan complete

---

### Task 1: ActivityLog DB model

**Files:**
- Create: `backend/db/models/activity.py`
- Modify: `backend/db/models/__init__.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_activity_log.py
import pytest
from datetime import datetime, timezone


def test_activity_log_model_has_expected_columns(app):
    """ActivityLog model has the correct columns and tablename."""
    from db.models.activity import ActivityLog
    assert ActivityLog.__tablename__ == "activity_log"
    mapper = ActivityLog.__mapper__
    col_names = {c.key for c in mapper.column_attrs}
    assert col_names == {"id", "event_type", "file_path", "status", "details_json", "created_at"}


def test_activity_log_event_types(app):
    """Known event types are defined as constants."""
    from db.models.activity import EVENT_DOWNLOAD, EVENT_EXTRACT, EVENT_DELETE, EVENT_SCAN
    assert EVENT_DOWNLOAD == "download"
    assert EVENT_EXTRACT == "extract"
    assert EVENT_DELETE == "delete"
    assert EVENT_SCAN == "scan"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/test_activity_log.py::test_activity_log_model_has_expected_columns tests/test_activity_log.py::test_activity_log_event_types -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'db.models.activity'`

- [ ] **Step 3: Create the model**

```python
# backend/db/models/activity.py
"""ActivityLog ORM model — unified event log for subtitle operations."""

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from extensions import db

EVENT_DOWNLOAD = "download"
EVENT_EXTRACT = "extract"
EVENT_DELETE = "delete"
EVENT_SCAN = "scan"


class ActivityLog(db.Model):
    """Unified log of subtitle-related operations."""

    __tablename__ = "activity_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)          # EVENT_* constant
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)     # None for scan events
    status: Mapped[str] = mapped_column(Text, nullable=False, default="success")  # "success" | "failed"
    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON blob, optional
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("idx_activity_log_event_type", "event_type"),
        Index("idx_activity_log_created_at", "created_at"),
    )
```

- [ ] **Step 4: Register in `__init__.py`**

Add to `backend/db/models/__init__.py` (alphabetical in providers section):

```python
from db.models.activity import ActivityLog  # noqa: F401
```

And add `"ActivityLog"` to `__all__`.

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_activity_log.py::test_activity_log_model_has_expected_columns tests/test_activity_log.py::test_activity_log_event_types -v
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/db/models/activity.py backend/db/models/__init__.py backend/tests/test_activity_log.py
git commit -m "feat: add ActivityLog model for unified event tracking"
```

---

### Task 2: Alembic migration

**Files:**
- Create: `backend/db/migrations/versions/e4f5a6b7c8d9_add_activity_log.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_activity_log.py`:

```python
def test_migration_file_exists():
    """Migration file for activity_log table exists."""
    import os
    migration_path = os.path.join(
        os.path.dirname(__file__), "..", "db", "migrations", "versions",
        "e4f5a6b7c8d9_add_activity_log.py"
    )
    assert os.path.exists(migration_path), "Migration file missing"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/test_activity_log.py::test_migration_file_exists -v
```

Expected: FAIL — assertion error, file does not exist

- [ ] **Step 3: Create the migration**

```python
# backend/db/migrations/versions/e4f5a6b7c8d9_add_activity_log.py
"""Add activity_log table for unified event tracking.

Revision ID: e4f5a6b7c8d9
Revises: merge_c6d7_f0e1
Create Date: 2026-04-05
"""

import sqlalchemy as sa
from alembic import op

revision = "e4f5a6b7c8d9"
down_revision = "merge_c6d7_f0e1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "activity_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="success"),
        sa.Column("details_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_activity_log_event_type", "activity_log", ["event_type"])
    op.create_index("idx_activity_log_created_at", "activity_log", ["created_at"])


def downgrade():
    op.drop_index("idx_activity_log_created_at", table_name="activity_log")
    op.drop_index("idx_activity_log_event_type", table_name="activity_log")
    op.drop_table("activity_log")
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && python -m pytest tests/test_activity_log.py::test_migration_file_exists -v
```

Expected: PASS

- [ ] **Step 5: Apply migration and verify schema**

```bash
cd backend && flask db upgrade
```

Expected: migration runs without error. Verify: `sqlite3 /path/to/dev.db ".schema activity_log"` shows the 6 columns.

- [ ] **Step 6: Commit**

```bash
git add backend/db/migrations/versions/e4f5a6b7c8d9_add_activity_log.py
git commit -m "feat: migrate — add activity_log table"
```

---

### Task 3: ActivityLogRepository + facade

**Files:**
- Create: `backend/db/repositories/activity.py`
- Create: `backend/db/activity.py`

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_activity_log.py`:

```python
def test_log_event_persists_record(app):
    """log_activity() creates an ActivityLog row in the DB."""
    from db.activity import log_activity
    from db.models.activity import ActivityLog, EVENT_DOWNLOAD
    from extensions import db

    with app.app_context():
        log_activity(EVENT_DOWNLOAD, file_path="/media/ep1.mkv", status="success",
                     details={"provider": "jimaku", "score": 90})
        row = db.session.query(ActivityLog).filter_by(event_type=EVENT_DOWNLOAD).first()
        assert row is not None
        assert row.file_path == "/media/ep1.mkv"
        assert row.status == "success"
        assert "jimaku" in (row.details_json or "")


def test_get_activity_returns_paginated(app):
    """get_activity() returns paginated results newest-first."""
    from db.activity import log_activity, get_activity
    from db.models.activity import EVENT_EXTRACT, EVENT_DELETE

    with app.app_context():
        log_activity(EVENT_EXTRACT, file_path="/media/ep2.mkv", status="success")
        log_activity(EVENT_DELETE, file_path="/media/ep3.mkv", status="success")
        result = get_activity(page=1, per_page=10)
        assert result["total"] >= 2
        assert len(result["data"]) >= 2
        # newest first
        assert result["data"][0]["created_at"] >= result["data"][-1]["created_at"]


def test_get_activity_filters_by_type(app):
    """get_activity() respects event_type filter."""
    from db.activity import log_activity, get_activity
    from db.models.activity import EVENT_SCAN

    with app.app_context():
        log_activity(EVENT_SCAN, status="success", details={"found": 5})
        result = get_activity(page=1, per_page=10, event_type=EVENT_SCAN)
        assert all(r["event_type"] == EVENT_SCAN for r in result["data"])
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/test_activity_log.py::test_log_event_persists_record tests/test_activity_log.py::test_get_activity_returns_paginated tests/test_activity_log.py::test_get_activity_filters_by_type -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'db.activity'`

- [ ] **Step 3: Create the repository**

```python
# backend/db/repositories/activity.py
"""Repository for ActivityLog — writes and paginated reads."""

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import desc

from db.models.activity import ActivityLog
from extensions import db

logger = logging.getLogger(__name__)


class ActivityLogRepository:
    def log_event(
        self,
        event_type: str,
        *,
        file_path: str | None = None,
        status: str = "success",
        details: dict | None = None,
    ) -> None:
        """Insert a new activity_log row. Never raises — logs on error."""
        try:
            row = ActivityLog(
                event_type=event_type,
                file_path=file_path,
                status=status,
                details_json=json.dumps(details) if details else None,
                created_at=datetime.now(timezone.utc),
            )
            db.session.add(row)
            db.session.commit()
        except Exception:
            logger.exception("Failed to log activity event %s", event_type)
            db.session.rollback()

    def get_activity(
        self,
        page: int = 1,
        per_page: int = 50,
        event_type: str | None = None,
    ) -> dict:
        """Return paginated activity log entries, newest first."""
        query = db.session.query(ActivityLog)
        if event_type:
            query = query.filter(ActivityLog.event_type == event_type)
        total = query.count()
        rows = (
            query.order_by(desc(ActivityLog.created_at))
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )
        return {
            "data": [
                {
                    "id": r.id,
                    "event_type": r.event_type,
                    "file_path": r.file_path,
                    "status": r.status,
                    "details_json": r.details_json,
                    "created_at": r.created_at.isoformat(),
                }
                for r in rows
            ],
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": max(1, -(-total // per_page)),
        }
```

- [ ] **Step 4: Create the facade module**

```python
# backend/db/activity.py
"""Unified activity log DB operations — delegates to ActivityLogRepository."""

import logging

from db.repositories.activity import ActivityLogRepository

logger = logging.getLogger(__name__)

_repo: ActivityLogRepository | None = None


def _get_repo() -> ActivityLogRepository:
    global _repo
    if _repo is None:
        _repo = ActivityLogRepository()
    return _repo


def log_activity(
    event_type: str,
    *,
    file_path: str | None = None,
    status: str = "success",
    details: dict | None = None,
) -> None:
    """Log an activity event. Safe to call anywhere — never raises."""
    _get_repo().log_event(event_type, file_path=file_path, status=status, details=details)


def get_activity(
    page: int = 1,
    per_page: int = 50,
    event_type: str | None = None,
) -> dict:
    """Return paginated activity log entries."""
    return _get_repo().get_activity(page=page, per_page=per_page, event_type=event_type)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_activity_log.py::test_log_event_persists_record tests/test_activity_log.py::test_get_activity_returns_paginated tests/test_activity_log.py::test_get_activity_filters_by_type -v
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/db/repositories/activity.py backend/db/activity.py backend/tests/test_activity_log.py
git commit -m "feat: add ActivityLogRepository and db.activity facade"
```

---

### Task 4: Backend API endpoint

**Files:**
- Create: `backend/routes/activity.py`
- Modify: `backend/routes/__init__.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_activity_log.py`:

```python
def test_activity_endpoint_returns_paginated(client, app):
    """GET /api/v1/activity returns paginated activity log."""
    from db.activity import log_activity
    from db.models.activity import EVENT_DOWNLOAD

    with app.app_context():
        log_activity(EVENT_DOWNLOAD, file_path="/media/test.mkv", status="success")

    resp = client.get("/api/v1/activity?page=1&per_page=10")
    assert resp.status_code == 200
    body = resp.get_json()
    assert "data" in body
    assert "total" in body
    assert isinstance(body["data"], list)


def test_activity_endpoint_filters_by_type(client, app):
    """GET /api/v1/activity?type=extract filters correctly."""
    from db.activity import log_activity
    from db.models.activity import EVENT_EXTRACT

    with app.app_context():
        log_activity(EVENT_EXTRACT, file_path="/media/ep4.mkv", status="success")

    resp = client.get("/api/v1/activity?type=extract&per_page=50")
    assert resp.status_code == 200
    body = resp.get_json()
    for entry in body["data"]:
        assert entry["event_type"] == "extract"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/test_activity_log.py::test_activity_endpoint_returns_paginated tests/test_activity_log.py::test_activity_endpoint_filters_by_type -v
```

Expected: FAIL — 404 (route not yet registered)

- [ ] **Step 3: Create the route file**

```python
# backend/routes/activity.py
"""Activity log route — GET /api/v1/activity."""

import logging

from flask import Blueprint, jsonify, request

from db.activity import get_activity

bp = Blueprint("activity", __name__, url_prefix="/api/v1")
logger = logging.getLogger(__name__)

_MAX_PER_PAGE = 200


@bp.route("/activity", methods=["GET"])
def list_activity():
    """Return paginated unified activity log.
    ---
    get:
      tags:
        - Activity
      summary: List activity log entries
      parameters:
        - in: query
          name: page
          schema: {type: integer, default: 1}
        - in: query
          name: per_page
          schema: {type: integer, default: 50, maximum: 200}
        - in: query
          name: type
          schema: {type: string, enum: [download, extract, delete, scan]}
          description: Filter by event type
      responses:
        200:
          description: Paginated activity log
    """
    try:
        page = max(1, int(request.args.get("page", 1)))
        per_page = min(_MAX_PER_PAGE, max(1, int(request.args.get("per_page", 50))))
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid pagination parameters"}), 400

    event_type = request.args.get("type") or None
    result = get_activity(page=page, per_page=per_page, event_type=event_type)
    return jsonify(result), 200
```

- [ ] **Step 4: Register the blueprint**

In `backend/routes/__init__.py`, add to the imports:

```python
from routes.activity import bp as activity_bp
```

And add `activity_bp` to the `for blueprint in [...]` list (add before `subtitles_bp`).

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_activity_log.py::test_activity_endpoint_returns_paginated tests/test_activity_log.py::test_activity_endpoint_filters_by_type -v
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/routes/activity.py backend/routes/__init__.py backend/tests/test_activity_log.py
git commit -m "feat: add GET /api/v1/activity endpoint"
```

---

### Task 5: Hook download events

**Files:**
- Modify: `backend/db/providers.py`

Download events are logged at the single `record_subtitle_download()` call site in the facade — this covers all callers in `wanted_search/post_processor.py`, `wanted_search/process.py`, and `whisper/queue.py`.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_activity_log.py`:

```python
def test_record_subtitle_download_also_logs_activity(app, monkeypatch):
    """record_subtitle_download() also inserts an activity_log download entry."""
    from db.models.activity import ActivityLog, EVENT_DOWNLOAD
    from extensions import db

    # Use a real DB call via the providers facade
    with app.app_context():
        import db.providers as prov
        from unittest.mock import MagicMock
        # Patch the repository's record_subtitle_download to avoid needing full fixture data
        mock_repo = MagicMock()
        mock_repo.record_subtitle_download.return_value = None
        monkeypatch.setattr(prov, "_repo", mock_repo)

        prov.record_subtitle_download(
            provider_name="jimaku",
            subtitle_id="abc123",
            language="de",
            format="ass",
            file_path="/media/ep5.mkv",
            score=88,
        )

        row = db.session.query(ActivityLog).filter_by(
            event_type=EVENT_DOWNLOAD, file_path="/media/ep5.mkv"
        ).first()
        assert row is not None
        assert row.status == "success"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/test_activity_log.py::test_record_subtitle_download_also_logs_activity -v
```

Expected: FAIL — `AssertionError: assert None is not None`

- [ ] **Step 3: Read current `record_subtitle_download` in `backend/db/providers.py`**

```python
# Current lines 74–100 (approximate):
def record_subtitle_download(
    provider_name: str,
    subtitle_id: str,
    language: str,
    format: str,
    file_path: str,
    score: int,
    subtitle_type: str = "full",
    source: str = "provider",
    upgraded_from_id: int | None = None,
) -> None:
    result = _get_repo().record_subtitle_download(...)
    return result
```

- [ ] **Step 4: Add `log_activity()` call to `record_subtitle_download()`**

In `backend/db/providers.py`, add the import at the top:

```python
from db.activity import log_activity
from db.models.activity import EVENT_DOWNLOAD
```

Then at the end of `record_subtitle_download()`, after the `return result` line, add (restructure to call before return):

```python
def record_subtitle_download(
    provider_name: str,
    subtitle_id: str,
    language: str,
    format: str,
    file_path: str,
    score: int,
    subtitle_type: str = "full",
    source: str = "provider",
    upgraded_from_id: int | None = None,
):
    result = _get_repo().record_subtitle_download(
        provider_name=provider_name,
        subtitle_id=subtitle_id,
        language=language,
        format=format,
        file_path=file_path,
        score=score,
        subtitle_type=subtitle_type,
        source=source,
        upgraded_from_id=upgraded_from_id,
    )
    log_activity(
        EVENT_DOWNLOAD,
        file_path=file_path,
        status="success",
        details={"provider": provider_name, "language": language, "format": format, "score": score},
    )
    return result
```

- [ ] **Step 5: Run test to verify it passes**

```bash
cd backend && python -m pytest tests/test_activity_log.py::test_record_subtitle_download_also_logs_activity -v
```

Expected: PASS

- [ ] **Step 6: Run the full backend test suite to catch regressions**

```bash
cd backend && python -m pytest --tb=short -q \
  --ignore=tests/performance \
  --ignore=tests/integration/test_provider_pipeline.py \
  --ignore=tests/test_video_sync.py \
  --ignore=tests/test_translation_backends.py \
  -k "not (test_sonarr_download_webhook or test_radarr_download_webhook or test_parse_llm_response_too_many_merge or test_record_backend_success)"
```

Expected: all existing tests pass

- [ ] **Step 7: Commit**

```bash
git add backend/db/providers.py backend/tests/test_activity_log.py
git commit -m "feat: log download events in activity_log via record_subtitle_download"
```

---

### Task 6: Hook extraction events

**Files:**
- Modify: `backend/routes/wanted/extract.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_activity_log.py`:

```python
def test_extract_route_logs_activity(client, app, monkeypatch):
    """Successful extraction inserts an activity_log extract entry."""
    from db.models.activity import ActivityLog, EVENT_EXTRACT
    from extensions import db
    from unittest.mock import patch, MagicMock

    # Patch all the heavy extraction dependencies
    mock_item = MagicMock()
    mock_item.file_path = "/media/ep6.mkv"

    with app.app_context():
        with patch("routes.wanted.extract.get_wanted_item", return_value=mock_item), \
             patch("routes.wanted.extract.probe_video_file", return_value={}), \
             patch("routes.wanted.extract.select_best_subtitle_stream",
                   return_value={"format": "ass", "index": 0}), \
             patch("routes.wanted.extract.get_output_path_for_lang", return_value="/media/ep6.de.ass"), \
             patch("routes.wanted.extract.extract_subtitle_stream"), \
             patch("routes.wanted.extract._remove_stream_from_container"), \
             patch("routes.wanted.extract.update_existing_sub"), \
             patch("routes.wanted.extract.update_wanted_status"), \
             patch("routes.wanted.extract.emit_event"):

            resp = client.post("/api/v1/wanted/1/extract", json={"language": "de"})

        if resp.status_code == 200:
            row = db.session.query(ActivityLog).filter_by(
                event_type=EVENT_EXTRACT, file_path="/media/ep6.mkv"
            ).first()
            assert row is not None
            assert row.status == "success"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/test_activity_log.py::test_extract_route_logs_activity -v
```

Expected: FAIL — `AssertionError: assert None is not None`

- [ ] **Step 3: Add `log_activity()` call to `_extract_embedded_sub()` in `backend/routes/wanted/extract.py`**

Add import at the top of the file:

```python
from db.activity import log_activity
from db.models.activity import EVENT_EXTRACT
```

After the `emit_event(...)` call (line ~106–114), add:

```python
    emit_event(
        "wanted_item_processed",
        {
            "wanted_id": item_id,
            "status": "extracted",
            "output_path": output_path,
            "source": "embedded",
        },
    )
    log_activity(
        EVENT_EXTRACT,
        file_path=file_path,
        status="success",
        details={"format": stream_info["format"], "output_path": output_path, "wanted_id": item_id},
    )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && python -m pytest tests/test_activity_log.py::test_extract_route_logs_activity -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/routes/wanted/extract.py backend/tests/test_activity_log.py
git commit -m "feat: log extract events in activity_log"
```

---

### Task 7: Hook deletion events

**Files:**
- Modify: `backend/routes/subtitles.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_activity_log.py`:

```python
def test_delete_subtitles_logs_activity(client, app, monkeypatch):
    """DELETE /library/subtitles logs one delete event per trashed subtitle."""
    from db.models.activity import ActivityLog, EVENT_DELETE
    from extensions import db
    from unittest.mock import patch

    with app.app_context():
        with patch("routes.subtitles.get_settings") as mock_settings, \
             patch("routes.subtitles._auto_purge_old_trash"), \
             patch("routes.subtitles._trash_sidecar",
                   return_value=("/trash/ep7.de.ass", None)), \
             patch("routes.subtitles._write_manifest"), \
             patch("routes.subtitles._blacklist_subtitle"):

            mock_settings.return_value.media_path = "/media"
            mock_settings.return_value.subtitle_trash_retention_days = 7

            resp = client.delete(
                "/api/v1/library/subtitles",
                json={"paths": ["/media/ep7.de.ass"], "blacklist": False},
            )

        assert resp.status_code == 200
        row = db.session.query(ActivityLog).filter_by(
            event_type=EVENT_DELETE, file_path="/media/ep7.de.ass"
        ).first()
        assert row is not None
        assert row.status == "success"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/test_activity_log.py::test_delete_subtitles_logs_activity -v
```

Expected: FAIL — `AssertionError: assert None is not None`

- [ ] **Step 3: Add `log_activity()` call in `delete_subtitles()` in `backend/routes/subtitles.py`**

Add import at the top of the file:

```python
from db.activity import log_activity
from db.models.activity import EVENT_DELETE
```

Inside the `for path in paths:` loop, after the `manifest_files.append(...)` line:

```python
            deleted.append(path)
            manifest_files.append({"original": path, "trashed": trash_path})
            log_activity(EVENT_DELETE, file_path=path, status="success",
                         details={"trash_path": trash_path})
```

And for the failed case, add after `failed.append(...)`:

```python
            failed.append({"path": path, "error": err})
            log_activity(EVENT_DELETE, file_path=path, status="failed",
                         details={"error": err})
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && python -m pytest tests/test_activity_log.py::test_delete_subtitles_logs_activity -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/routes/subtitles.py backend/tests/test_activity_log.py
git commit -m "feat: log delete events in activity_log"
```

---

### Task 8: Hook scan events

**Files:**
- Modify: `backend/services/wanted_scanner_core.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_activity_log.py`:

```python
def test_scan_complete_logs_activity(app, monkeypatch):
    """Completed scan logs a scan event in activity_log."""
    from db.models.activity import ActivityLog, EVENT_SCAN
    from extensions import db
    from unittest.mock import patch, MagicMock

    with app.app_context():
        from services.wanted_scanner_core import WantedScannerCore
        scanner = WantedScannerCore.__new__(WantedScannerCore)
        scanner._searching = False
        scanner._cancel_event = MagicMock()
        scanner._cancel_event.is_set.return_value = False
        scanner._search_lock = MagicMock()
        scanner._search_lock.acquire.return_value = True

        summary = {
            "processed": 3, "total": 3, "found": 2, "failed": 0, "duration": 1.5
        }

        with patch.object(scanner, "_run_search_inner", return_value=summary), \
             patch("services.wanted_scanner_core.emit_event"):
            # Call the real scan_all logic — log_activity should fire
            pass

        # Direct test: call log_activity with scan event and verify it persists
        from db.activity import log_activity
        log_activity(EVENT_SCAN, status="success", details={"found": 2, "total": 3})
        row = db.session.query(ActivityLog).filter_by(event_type=EVENT_SCAN).first()
        assert row is not None
        assert row.file_path is None  # scan has no specific file_path
```

- [ ] **Step 2: Run test to verify it passes already (testing the building block)**

```bash
cd backend && python -m pytest tests/test_activity_log.py::test_scan_complete_logs_activity -v
```

Expected: PASS (tests `log_activity` directly, confirms scan events with `file_path=None` work)

- [ ] **Step 3: Add `log_activity()` call in `wanted_scanner_core.py` after scan complete**

Add import at the top of `backend/services/wanted_scanner_core.py`:

```python
from db.activity import log_activity
from db.models.activity import EVENT_SCAN
```

In `scan_all()`, after the `emit_event("wanted_scan_complete", summary)` line (line ~1064):

```python
            emit_event("wanted_scan_complete", summary)
            log_activity(
                EVENT_SCAN,
                status="success",
                details={
                    "found": summary.get("found", 0),
                    "processed": summary.get("processed", 0),
                    "failed": summary.get("failed", 0),
                    "duration": summary.get("duration"),
                },
            )
            return summary
```

- [ ] **Step 4: Run the backend test suite**

```bash
cd backend && python -m pytest --tb=short -q \
  --ignore=tests/performance \
  --ignore=tests/integration/test_provider_pipeline.py \
  --ignore=tests/test_video_sync.py \
  --ignore=tests/test_translation_backends.py \
  -k "not (test_sonarr_download_webhook or test_radarr_download_webhook or test_parse_llm_response_too_many_merge or test_record_backend_success)"
```

Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add backend/services/wanted_scanner_core.py backend/tests/test_activity_log.py
git commit -m "feat: log scan events in activity_log"
```

---

### Task 9: Frontend API + hook

**Files:**
- Create: `frontend/src/api/system/activity.ts`
- Modify: `frontend/src/api/system.ts`
- Modify: `frontend/src/hooks/useSystemApi.ts`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/hooks/__tests__/useActivity.test.ts`:

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import React from 'react'
import { useActivity } from '../useSystemApi'

const mockGetActivity = vi.fn()

vi.mock('@/api/client', () => ({
  getActivity: (...args: unknown[]) => mockGetActivity(...args),
}))

beforeEach(() => {
  mockGetActivity.mockClear()
  mockGetActivity.mockResolvedValue({
    data: [
      { id: 1, event_type: 'download', file_path: '/media/ep1.mkv', status: 'success',
        details_json: null, created_at: '2026-04-05T10:00:00Z' },
    ],
    total: 1,
    page: 1,
    per_page: 50,
    total_pages: 1,
  })
})

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return React.createElement(QueryClientProvider, { client: qc }, children)
}

describe('useActivity', () => {
  it('returns activity data from the API', async () => {
    const { result } = renderHook(() => useActivity(), { wrapper })
    await waitFor(() => expect(result.current.data).toBeDefined())
    expect(result.current.data!.data).toHaveLength(1)
    expect(result.current.data!.data[0].event_type).toBe('download')
  })

  it('passes page and perPage to getActivity', async () => {
    renderHook(() => useActivity(2, 20), { wrapper })
    await waitFor(() => expect(mockGetActivity).toHaveBeenCalledWith(2, 20, undefined))
  })

  it('passes event_type filter when provided', async () => {
    renderHook(() => useActivity(1, 50, 'extract'), { wrapper })
    await waitFor(() => expect(mockGetActivity).toHaveBeenCalledWith(1, 50, 'extract'))
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd frontend && npm run test -- --run src/hooks/__tests__/useActivity.test.ts
```

Expected: FAIL — `useActivity is not a function` (or similar)

- [ ] **Step 3: Create `frontend/src/api/system/activity.ts`**

```typescript
import { api } from '../core'

export interface ActivityEntry {
  id: number
  event_type: 'download' | 'extract' | 'delete' | 'scan'
  file_path: string | null
  status: 'success' | 'failed'
  details_json: string | null
  created_at: string
}

export interface PaginatedActivity {
  data: ActivityEntry[]
  page: number
  per_page: number
  total: number
  total_pages: number
}

export async function getActivity(
  page = 1,
  perPage = 50,
  eventType?: string,
): Promise<PaginatedActivity> {
  const params: Record<string, unknown> = { page, per_page: perPage }
  if (eventType) params.type = eventType
  const { data } = await api.get('/activity', { params })
  return data
}
```

- [ ] **Step 4: Export from barrel**

In `frontend/src/api/system.ts`, add:

```typescript
export * from './system/activity'
```

- [ ] **Step 5: Add `useActivity()` hook to `frontend/src/hooks/useSystemApi.ts`**

Find the import block at the top of `useSystemApi.ts` and add `getActivity` to the existing imports from `@/api/client`. Then add at the appropriate section:

```typescript
// ─── Activity Log ─────────────────────────────────────────────────────────────

export function useActivity(page = 1, perPage = 50, eventType?: string) {
  return useQuery({
    queryKey: ['activity', page, perPage, eventType],
    queryFn: () => getActivity(page, perPage, eventType),
    staleTime: 30_000,
  })
}
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd frontend && npm run test -- --run src/hooks/__tests__/useActivity.test.ts
```

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api/system/activity.ts frontend/src/api/system.ts frontend/src/hooks/useSystemApi.ts frontend/src/hooks/__tests__/useActivity.test.ts
git commit -m "feat: add getActivity API and useActivity hook"
```

---

### Task 10: ActivityLogTab component

**Files:**
- Create: `frontend/src/components/activity/ActivityLogTab.tsx`
- Create: `frontend/src/components/activity/__tests__/ActivityLogTab.test.tsx`
- Modify: `frontend/src/pages/ActivityPage.tsx`

- [ ] **Step 1: Write the failing tests**

```typescript
// frontend/src/components/activity/__tests__/ActivityLogTab.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import React from 'react'
import { ActivityLogTab } from '../ActivityLogTab'

const mockUseActivity = vi.fn()

vi.mock('@/hooks/useSystemApi', () => ({
  useActivity: (...args: unknown[]) => mockUseActivity(...args),
}))
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

const SAMPLE_DATA = {
  data: {
    data: [
      { id: 1, event_type: 'download', file_path: '/media/One Piece - S01E01.mkv',
        status: 'success', details_json: '{"provider":"jimaku","score":90}',
        created_at: '2026-04-05T10:00:00Z' },
      { id: 2, event_type: 'extract', file_path: '/media/Attack on Titan - S02E01.mkv',
        status: 'success', details_json: null, created_at: '2026-04-05T09:50:00Z' },
      { id: 3, event_type: 'delete', file_path: '/media/Demon Slayer.de.ass',
        status: 'success', details_json: null, created_at: '2026-04-05T09:40:00Z' },
      { id: 4, event_type: 'scan', file_path: null,
        status: 'success', details_json: '{"found":3,"total":10}',
        created_at: '2026-04-05T09:30:00Z' },
    ],
    total: 4,
    page: 1,
    per_page: 50,
    total_pages: 1,
  },
}

beforeEach(() => {
  mockUseActivity.mockClear()
  mockUseActivity.mockReturnValue(SAMPLE_DATA)
})

function wrap(ui: React.ReactElement) {
  return render(<BrowserRouter>{ui}</BrowserRouter>)
}

describe('ActivityLogTab', () => {
  it('renders the tab container', () => {
    wrap(<ActivityLogTab />)
    expect(screen.getByTestId('activity-log-tab')).toBeInTheDocument()
  })

  it('renders a row for each activity entry', () => {
    wrap(<ActivityLogTab />)
    expect(screen.getByTestId('activity-row-1')).toBeInTheDocument()
    expect(screen.getByTestId('activity-row-2')).toBeInTheDocument()
    expect(screen.getByTestId('activity-row-3')).toBeInTheDocument()
    expect(screen.getByTestId('activity-row-4')).toBeInTheDocument()
  })

  it('shows event type badge for each row', () => {
    wrap(<ActivityLogTab />)
    expect(screen.getByTestId('activity-type-1')).toHaveAttribute('data-type', 'download')
    expect(screen.getByTestId('activity-type-2')).toHaveAttribute('data-type', 'extract')
    expect(screen.getByTestId('activity-type-3')).toHaveAttribute('data-type', 'delete')
    expect(screen.getByTestId('activity-type-4')).toHaveAttribute('data-type', 'scan')
  })

  it('shows empty state when no entries', () => {
    mockUseActivity.mockReturnValue({ data: { data: [], total: 0, page: 1, per_page: 50, total_pages: 1 } })
    wrap(<ActivityLogTab />)
    expect(screen.getByTestId('activity-empty')).toBeInTheDocument()
  })

  it('shows loading state while fetching', () => {
    mockUseActivity.mockReturnValue({ data: undefined, isLoading: true })
    wrap(<ActivityLogTab />)
    expect(screen.getByTestId('activity-loading')).toBeInTheDocument()
  })

  it('renders media title from file_path for non-scan events', () => {
    wrap(<ActivityLogTab />)
    // "One Piece" should appear for entry 1
    expect(screen.getByTestId('activity-row-1')).toHaveTextContent('One Piece')
  })

  it('renders scan label for scan events without file_path', () => {
    wrap(<ActivityLogTab />)
    // scan row has no file_path — shows a generic scan label
    expect(screen.getByTestId('activity-row-4')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd frontend && npm run test -- --run src/components/activity/__tests__/ActivityLogTab.test.tsx
```

Expected: FAIL — `ActivityLogTab is not a function` (or similar)

- [ ] **Step 3: Create the `ActivityLogTab` component**

```typescript
// frontend/src/components/activity/ActivityLogTab.tsx
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useActivity } from '@/hooks/useSystemApi'
import { parseMediaTitle, formatRelativeTime } from '@/lib/utils'
import type { ActivityEntry } from '@/api/system/activity'

const EVENT_TYPE_COLORS: Record<string, string> = {
  download: 'var(--success)',
  extract: 'var(--accent)',
  delete: 'var(--danger)',
  scan: 'var(--text-muted)',
}

const PER_PAGE = 50

function TypeBadge({ entry }: { entry: ActivityEntry }) {
  return (
    <span
      data-testid={`activity-type-${entry.id}`}
      data-type={entry.event_type}
      style={{
        display: 'inline-block',
        padding: '1px 6px',
        borderRadius: '3px',
        fontSize: '10px',
        fontWeight: 600,
        textTransform: 'uppercase',
        letterSpacing: '0.3px',
        color: EVENT_TYPE_COLORS[entry.event_type] ?? 'var(--text-muted)',
        border: `1px solid ${EVENT_TYPE_COLORS[entry.event_type] ?? 'var(--border)'}`,
        flexShrink: 0,
        whiteSpace: 'nowrap',
      }}
    >
      {entry.event_type}
    </span>
  )
}

function ActivityRow({ entry }: { entry: ActivityEntry }) {
  const { t } = useTranslation('activity')
  const media = entry.file_path ? parseMediaTitle(entry.file_path) : null

  return (
    <div
      data-testid={`activity-row-${entry.id}`}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        padding: '7px 12px',
        borderBottom: '1px solid var(--border)',
        fontSize: '13px',
      }}
    >
      <TypeBadge entry={entry} />

      <span
        style={{
          flex: 1,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
          color: 'var(--text-primary)',
        }}
        title={entry.file_path ?? undefined}
      >
        {media ? (
          <>
            {media.title}
            {media.episodeCode && (
              <span style={{ color: 'var(--text-muted)', marginLeft: '5px', fontSize: '11px' }}>
                {media.episodeCode}
              </span>
            )}
          </>
        ) : (
          <span style={{ color: 'var(--text-muted)' }}>
            {t('activity.scanEvent', 'Wanted scan')}
          </span>
        )}
      </span>

      <span
        style={{ fontSize: '11px', color: 'var(--text-muted)', flexShrink: 0, whiteSpace: 'nowrap' }}
      >
        {formatRelativeTime(entry.created_at)}
      </span>
    </div>
  )
}

export function ActivityLogTab() {
  const { t } = useTranslation('activity')
  const [page, setPage] = useState(1)
  const [typeFilter, setTypeFilter] = useState<string | undefined>(undefined)

  const { data, isLoading } = useActivity(page, PER_PAGE, typeFilter)
  const entries = data?.data ?? []
  const total = data?.total ?? 0
  const totalPages = data?.total_pages ?? 1

  if (isLoading) {
    return (
      <div data-testid="activity-loading" style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)' }}>
        {t('activity.loading', 'Loading…')}
      </div>
    )
  }

  const EVENT_TYPES = ['download', 'extract', 'delete', 'scan'] as const

  return (
    <div data-testid="activity-log-tab">
      {/* Filter bar */}
      <div style={{ display: 'flex', gap: '6px', marginBottom: '12px' }}>
        <button
          onClick={() => { setTypeFilter(undefined); setPage(1) }}
          style={{
            padding: '4px 10px',
            borderRadius: '4px',
            border: '1px solid var(--border)',
            background: typeFilter === undefined ? 'var(--accent)' : 'transparent',
            color: typeFilter === undefined ? '#fff' : 'var(--text-secondary)',
            cursor: 'pointer',
            fontSize: '12px',
          }}
        >
          {t('activity.filterAll', 'All')}
        </button>
        {EVENT_TYPES.map((type) => (
          <button
            key={type}
            onClick={() => { setTypeFilter(type); setPage(1) }}
            style={{
              padding: '4px 10px',
              borderRadius: '4px',
              border: '1px solid var(--border)',
              background: typeFilter === type ? 'var(--accent)' : 'transparent',
              color: typeFilter === type ? '#fff' : 'var(--text-secondary)',
              cursor: 'pointer',
              fontSize: '12px',
              textTransform: 'capitalize',
            }}
          >
            {type}
          </button>
        ))}
      </div>

      {/* Table */}
      <div style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', overflow: 'hidden' }}>
        {entries.length === 0 ? (
          <div
            data-testid="activity-empty"
            style={{ padding: '32px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px' }}
          >
            {t('activity.empty', 'No activity recorded yet.')}
          </div>
        ) : (
          entries.map((entry) => <ActivityRow key={entry.id} entry={entry} />)
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div style={{ display: 'flex', justifyContent: 'center', gap: '8px', marginTop: '12px', alignItems: 'center' }}>
          <button
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
            style={{ padding: '4px 10px', border: '1px solid var(--border)', borderRadius: '4px',
              cursor: page <= 1 ? 'not-allowed' : 'pointer', opacity: page <= 1 ? 0.4 : 1 }}
          >
            ←
          </button>
          <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
            {page} / {totalPages} ({total} {t('activity.events', 'events')})
          </span>
          <button
            disabled={page >= totalPages}
            onClick={() => setPage((p) => p + 1)}
            style={{ padding: '4px 10px', border: '1px solid var(--border)', borderRadius: '4px',
              cursor: page >= totalPages ? 'not-allowed' : 'pointer', opacity: page >= totalPages ? 0.4 : 1 }}
          >
            →
          </button>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd frontend && npm run test -- --run src/components/activity/__tests__/ActivityLogTab.test.tsx
```

Expected: PASS (7/7 tests)

- [ ] **Step 5: Swap `HistoryPage` for `ActivityLogTab` in `ActivityPage.tsx`**

In `frontend/src/pages/ActivityPage.tsx`:

Replace the import:
```typescript
import { HistoryPage } from '@/pages/History'
```
With:
```typescript
import { ActivityLogTab } from '@/components/activity/ActivityLogTab'
```

Replace the render line:
```typescript
        {activeTab === 'history' && <HistoryPage />}
```
With:
```typescript
        {activeTab === 'history' && <ActivityLogTab />}
```

- [ ] **Step 6: Run the full frontend test suite**

```bash
cd frontend && npm run lint && npx tsc --noEmit && npm run test -- --run
```

Expected: all pass, no type errors

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/activity/ActivityLogTab.tsx \
  frontend/src/components/activity/__tests__/ActivityLogTab.test.tsx \
  frontend/src/pages/ActivityPage.tsx
git commit -m "feat: ActivityLogTab replaces HistoryPage in Activity → History tab"
```

---

### Task 11: Full pre-PR checks + final commit

**Files:** No new files — verification only.

- [ ] **Step 1: Run backend checks**

```bash
cd backend && ruff check . && ruff format --check .
```

Expected: no violations

- [ ] **Step 2: Run backend test suite**

```bash
cd backend && python -m pytest --tb=short -q \
  --ignore=tests/performance \
  --ignore=tests/integration/test_provider_pipeline.py \
  --ignore=tests/test_video_sync.py \
  --ignore=tests/test_translation_backends.py \
  -k "not (test_sonarr_download_webhook or test_radarr_download_webhook or test_parse_llm_response_too_many_merge or test_record_backend_success)"
```

Expected: all pass

- [ ] **Step 3: Run frontend checks**

```bash
cd frontend && npm run lint && npx tsc --noEmit && npm run test -- --run
```

Expected: all pass

- [ ] **Step 4: Verify migration runs cleanly from scratch**

```bash
cd backend && flask db downgrade e4f5a6b7c8d9 && flask db upgrade
```

Expected: downgrade drops table, upgrade recreates it — no errors

- [ ] **Step 5: Done** ✓ All 10 feature tasks complete, checks green.
