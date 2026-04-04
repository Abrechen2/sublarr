# Cleanup Rules Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the embedded CleanupTab with a dedicated first-class Settings page that provides a sidebar/detail rule management UI with 4 structured rule types, per-rule scheduling, and language/format pickers.

**Architecture:** A new `CleanupSettings` page replaces `CleanupTab` everywhere it was embedded. The backend gets 4 new rule type executors, a `schedule` column on `cleanup_rules`, and a per-rule preview endpoint. The frontend sidebar lists rules; the detail view renders type-specific config components.

**Tech Stack:** Python/Flask, SQLAlchemy, Alembic, React 19, TypeScript, React Query (TanStack Query), Vitest, pytest

---

## File Map

### Backend — New / Modified

| File | Action | Purpose |
|------|--------|---------|
| `backend/db/migrations/versions/<hash>_add_schedule_to_cleanup_rules.py` | Create | Alembic migration: add `schedule` column |
| `backend/db/models/cleanup.py` | Modify | Add `schedule` mapped column to `CleanupRule` |
| `backend/db/repositories/cleanup.py` | Modify | Include `schedule` in `create_rule`, `update_rule`, `get_rules` output |
| `backend/services/cleanup_executors.py` | Create | 4 rule type executors: `language_filter`, `format_upgrade`, `orphan_files`, `orphan_db` |
| `backend/routes/cleanup.py` | Modify | Wire `run_rule` to new executors; add `POST /rules/<id>/preview` endpoint |
| `backend/cleanup_scheduler.py` | Modify | Per-rule `schedule` field respected; dispatch to new executors |
| `backend/tests/test_cleanup_executors.py` | Create | Unit tests for all 4 executors |

### Frontend — New / Modified

| File | Action | Purpose |
|------|--------|---------|
| `frontend/src/types/system.ts` | Modify | Extend `CleanupRule` type: new `rule_type` values, add `schedule` field |
| `frontend/src/api/system/tasks.ts` | Modify | Add `previewCleanupRule(id)` API call |
| `frontend/src/hooks/useSystemApi.ts` | Modify | Add `useRulePreview` mutation hook |
| `frontend/src/pages/Settings/CleanupSettings.tsx` | Create | Full-page Cleanup Settings: sidebar + detail view + dedup section + history |
| `frontend/src/components/cleanup/RuleSidebar.tsx` | Create | Rule list sidebar with type icons, status dots, badges |
| `frontend/src/components/cleanup/RuleDetail.tsx` | Create | Detail view: header + last-run bar + config sections + preview box |
| `frontend/src/components/cleanup/LanguageFilterConfig.tsx` | Create | Tag-style language picker for `language_filter` rules |
| `frontend/src/components/cleanup/FormatUpgradeConfig.tsx` | Create | 3-card format picker for `format_upgrade` rules |
| `frontend/src/components/cleanup/SchedulePicker.tsx` | Create | Chip-style schedule selector (manual/daily/weekly/after_scan) |
| `frontend/src/components/settings/SettingsGrid.tsx` | Modify | Add `cleanup` tile to CATEGORIES |
| `frontend/src/pages/Settings/index.tsx` | Modify | Add `/settings/cleanup` route → `CleanupSettings` |
| `frontend/src/pages/Settings/SubtitlesSettings.tsx` | Modify | Remove `CleanupTab` section (Cleanup has its own page now) |
| `frontend/src/pages/Settings/__tests__/CleanupSettings.test.tsx` | Create | Component tests for the new page |

---

## Task 1: DB Migration — add `schedule` to `cleanup_rules`

**Files:**
- Create: `backend/db/migrations/versions/a1b2c3d4e5f6_add_schedule_to_cleanup_rules.py`

- [ ] **Step 1: Generate migration**

```bash
cd backend
flask db revision --autogenerate -m "add_schedule_to_cleanup_rules"
```

This creates a new file under `db/migrations/versions/`. Rename it to `a1b2c3d4e5f6_add_schedule_to_cleanup_rules.py` and replace its content:

```python
"""add schedule to cleanup_rules

Revision ID: a1b2c3d4e5f6
Revises: make_glossary_series_id_nullable
Create Date: 2026-04-04
"""

from alembic import op
import sqlalchemy as sa

revision = 'a1b2c3d4e5f6'
down_revision = 'make_glossary_series_id_nullable'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('cleanup_rules') as batch_op:
        batch_op.add_column(
            sa.Column('schedule', sa.String(20), nullable=False, server_default='manual')
        )


def downgrade():
    with op.batch_alter_table('cleanup_rules') as batch_op:
        batch_op.drop_column('schedule')
```

- [ ] **Step 2: Run migration**

```bash
cd backend
flask db upgrade
```

Expected: `Running upgrade ... -> a1b2c3d4e5f6, add schedule to cleanup_rules`

- [ ] **Step 3: Verify column exists**

```bash
cd backend
python -c "
from app import create_app
app = create_app()
with app.app_context():
    from extensions import db
    result = db.session.execute(db.text('PRAGMA table_info(cleanup_rules)')).fetchall()
    print([r[1] for r in result])
"
```

Expected output includes `'schedule'`.

- [ ] **Step 4: Commit**

```bash
git add backend/db/migrations/versions/a1b2c3d4e5f6_add_schedule_to_cleanup_rules.py
git commit -m "feat: add schedule column to cleanup_rules"
```

---

## Task 2: Backend Model + Repository

**Files:**
- Modify: `backend/db/models/cleanup.py`
- Modify: `backend/db/repositories/cleanup.py`

- [ ] **Step 1: Update CleanupRule model**

In `backend/db/models/cleanup.py`, add `schedule` to `CleanupRule`:

```python
class CleanupRule(db.Model):
    """Configurable cleanup rules."""

    __tablename__ = "cleanup_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    rule_type: Mapped[str] = mapped_column(String(50), nullable=False)
    config_json: Mapped[str] = mapped_column(Text, default="{}")
    enabled: Mapped[int] = mapped_column(Integer, default=1)
    schedule: Mapped[str] = mapped_column(String(20), default="manual")
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
```

- [ ] **Step 2: Update CleanupRepository.create_rule to accept schedule**

In `backend/db/repositories/cleanup.py`, find `create_rule` and add `schedule` parameter:

```python
def create_rule(
    self,
    name: str,
    rule_type: str,
    config_json: dict | None = None,
    enabled: bool = True,
    schedule: str = "manual",
) -> dict:
    from db.models.cleanup import CleanupRule

    now = datetime.now(UTC)
    rule = CleanupRule(
        name=name,
        rule_type=rule_type,
        config_json=json.dumps(config_json or {}),
        enabled=1 if enabled else 0,
        schedule=schedule,
        created_at=now,
        updated_at=now,
    )
    db.session.add(rule)
    db.session.commit()
    return self._rule_to_dict(rule)
```

- [ ] **Step 3: Ensure `_rule_to_dict` includes schedule and update_rule handles it**

Find or add `_rule_to_dict` helper in `CleanupRepository`. It must include `schedule`:

```python
def _rule_to_dict(self, rule) -> dict:
    import json as _json
    try:
        config = _json.loads(rule.config_json or "{}")
    except (ValueError, TypeError):
        config = {}
    return {
        "id": rule.id,
        "name": rule.name,
        "rule_type": rule.rule_type,
        "config_json": config,
        "enabled": bool(rule.enabled),
        "schedule": rule.schedule,
        "last_run_at": rule.last_run_at.isoformat() if rule.last_run_at else None,
        "created_at": rule.created_at.isoformat(),
        "updated_at": rule.updated_at.isoformat(),
    }
```

Then update `update_rule` to accept `schedule`:

```python
def update_rule(self, rule_id: int, **kwargs) -> dict | None:
    from db.models.cleanup import CleanupRule

    rule = db.session.get(CleanupRule, rule_id)
    if not rule:
        return None

    if "name" in kwargs:
        rule.name = kwargs["name"]
    if "enabled" in kwargs:
        rule.enabled = 1 if kwargs["enabled"] else 0
    if "config_json" in kwargs:
        rule.config_json = json.dumps(kwargs["config_json"])
    if "schedule" in kwargs:
        rule.schedule = kwargs["schedule"]
    rule.updated_at = datetime.now(UTC)
    db.session.commit()
    return self._rule_to_dict(rule)
```

- [ ] **Step 4: Update `get_rules` and `get_rule` to use `_rule_to_dict`**

Replace any inline dict construction in `get_rules` and `get_rule` with `self._rule_to_dict(r)`.

- [ ] **Step 5: Commit**

```bash
git add backend/db/models/cleanup.py backend/db/repositories/cleanup.py
git commit -m "feat: add schedule field to CleanupRule model and repository"
```

---

## Task 3: Rule Executors

**Files:**
- Create: `backend/services/cleanup_executors.py`
- Create: `backend/tests/test_cleanup_executors.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_cleanup_executors.py`:

```python
"""Tests for cleanup_executors — language_filter, format_upgrade, orphan_files, orphan_db."""

import json
import os
import pytest
from unittest.mock import MagicMock, patch


def test_language_filter_deletes_non_kept_languages(tmp_path):
    """Files not in keep_languages should be deleted; NFO files are never touched."""
    from services.cleanup_executors import execute_language_filter

    # Create test sidecar files
    (tmp_path / "show.de.ass").write_text("german sub")
    (tmp_path / "show.en.srt").write_text("english sub")
    (tmp_path / "show.fr.ass").write_text("french sub")
    (tmp_path / "show.de.nfo").write_text("nfo file")  # never deleted

    config = {"keep_languages": ["de"]}
    result = execute_language_filter(str(tmp_path), config, dry_run=False)

    assert result["deleted"] == 1  # only fr.ass
    assert result["kept"] >= 1
    assert (tmp_path / "show.de.ass").exists()
    assert (tmp_path / "show.de.nfo").exists()
    assert not (tmp_path / "show.fr.ass").exists()
    # en.srt also deleted since "en" not in keep_languages
    assert not (tmp_path / "show.en.srt").exists()


def test_language_filter_dry_run_deletes_nothing(tmp_path):
    """dry_run=True must not delete any files."""
    from services.cleanup_executors import execute_language_filter

    (tmp_path / "show.fr.ass").write_text("french sub")
    config = {"keep_languages": ["de"]}
    result = execute_language_filter(str(tmp_path), config, dry_run=True)

    assert result["would_delete"] >= 1
    assert (tmp_path / "show.fr.ass").exists()


def test_format_upgrade_removes_srt_when_ass_exists(tmp_path):
    """SRT should be deleted when ASS exists for same language."""
    from services.cleanup_executors import execute_format_upgrade

    (tmp_path / "show.de.ass").write_text("german ass")
    (tmp_path / "show.de.srt").write_text("german srt")
    (tmp_path / "show.en.srt").write_text("english srt only")  # no ASS counterpart

    config = {"keep_format": "ass"}
    result = execute_format_upgrade(str(tmp_path), config, dry_run=False)

    assert result["deleted"] == 1  # only de.srt
    assert (tmp_path / "show.de.ass").exists()
    assert not (tmp_path / "show.de.srt").exists()
    assert (tmp_path / "show.en.srt").exists()  # kept, no ASS counterpart


def test_orphan_files_deletes_subs_without_video(tmp_path):
    """Subtitle without a video file in same dir should be detected as orphan."""
    from services.cleanup_executors import execute_orphan_files

    (tmp_path / "orphan.de.ass").write_text("sub without video")
    (tmp_path / "movie.mkv").write_text("video")
    (tmp_path / "movie.de.ass").write_text("paired sub")

    result = execute_orphan_files(str(tmp_path), {}, dry_run=False)

    assert result["deleted"] == 1
    assert not (tmp_path / "orphan.de.ass").exists()
    assert (tmp_path / "movie.de.ass").exists()


def test_orphan_db_removes_stale_db_entries(tmp_path):
    """DB rows pointing to non-existent files should be removed."""
    from services.cleanup_executors import execute_orphan_db

    mock_repo = MagicMock()
    mock_repo.get_all_subtitle_paths.return_value = [
        str(tmp_path / "exists.de.ass"),
        str(tmp_path / "missing.de.ass"),
    ]
    (tmp_path / "exists.de.ass").write_text("exists")

    with patch("services.cleanup_executors.SubtitleRepository", return_value=mock_repo):
        result = execute_orphan_db({}, dry_run=False)

    assert result["deleted"] == 1
    mock_repo.delete_by_path.assert_called_once_with(str(tmp_path / "missing.de.ass"))
```

- [ ] **Step 2: Run tests — confirm they fail**

```bash
cd backend
python -m pytest tests/test_cleanup_executors.py -v 2>&1 | head -30
```

Expected: `ModuleNotFoundError: No module named 'services.cleanup_executors'`

- [ ] **Step 3: Implement cleanup_executors.py**

Create `backend/services/cleanup_executors.py`:

```python
"""Cleanup rule executors — one function per rule_type.

Each executor takes (media_path, config, dry_run) and returns a result dict.
NFO files (.nfo) are never deleted by any executor.

Rule types:
  language_filter  — delete sidecars in non-allowed languages
  format_upgrade   — delete SRT when ASS exists for same episode+language
  orphan_files     — delete subtitle sidecars with no matching video on disk
  orphan_db        — remove DB entries whose file no longer exists
"""

import logging
import os

logger = logging.getLogger(__name__)

# Subtitle extensions handled by all executors
SUBTITLE_EXTENSIONS = {".ass", ".ssa", ".srt", ".vtt", ".sub"}
# Video extensions used to find "paired" video files
VIDEO_EXTENSIONS = {".mkv", ".mp4", ".avi", ".mov", ".m4v", ".ts", ".wmv"}
# Never touch NFO files
EXCLUDED_EXTENSIONS = {".nfo"}


def _subtitle_files(root: str) -> list[str]:
    """Walk root recursively, return paths of all subtitle files."""
    found = []
    for dirpath, _, filenames in os.walk(root):
        for fname in filenames:
            ext = os.path.splitext(fname)[1].lower()
            if ext in SUBTITLE_EXTENSIONS:
                found.append(os.path.join(dirpath, fname))
    return found


def _parse_lang_from_filename(filename: str) -> str | None:
    """Extract language tag from sidecar filename.

    Expects pattern: <basename>.<lang>.<ext>
    e.g. "Movie.de.ass" → "de", "Show.S01E01.en.srt" → "en"
    Returns None if no language tag found.
    """
    parts = filename.rsplit(".", 2)
    if len(parts) == 3:
        return parts[1].lower()
    return None


def execute_language_filter(media_path: str, config: dict, dry_run: bool = False) -> dict:
    """Delete subtitle sidecars in languages not in keep_languages list.

    Args:
        media_path: Root directory to scan recursively.
        config: {"keep_languages": ["de", "en"]}
        dry_run: If True, return counts without deleting.

    Returns:
        {"deleted": int, "kept": int, "bytes_freed": int}
        In dry_run mode: {"would_delete": int, "would_keep": int}
    """
    keep_languages = {lang.lower() for lang in config.get("keep_languages", [])}
    deleted = 0
    kept = 0
    bytes_freed = 0
    would_delete = 0
    would_keep = 0

    for path in _subtitle_files(media_path):
        fname = os.path.basename(path)
        lang = _parse_lang_from_filename(fname)

        if lang is None or lang in keep_languages:
            kept += 1
            would_keep += 1
            continue

        file_size = os.path.getsize(path)
        if dry_run:
            would_delete += 1
            logger.debug("Would delete (language_filter): %s", path)
        else:
            try:
                os.remove(path)
                deleted += 1
                bytes_freed += file_size
                logger.info("Deleted (language_filter): %s", path)
            except OSError as e:
                logger.warning("Failed to delete %s: %s", path, e)

    if dry_run:
        return {"would_delete": would_delete, "would_keep": would_keep}
    return {"deleted": deleted, "kept": kept, "bytes_freed": bytes_freed}


def execute_format_upgrade(media_path: str, config: dict, dry_run: bool = False) -> dict:
    """Delete lower-quality format when higher-quality exists for same episode+language.

    Args:
        media_path: Root directory to scan recursively.
        config: {"keep_format": "ass"}  — "ass" deletes SRT when ASS exists; "srt" vice versa; "any" is a no-op.
        dry_run: If True, return counts without deleting.

    Returns:
        {"deleted": int, "bytes_freed": int}
    """
    keep_format = config.get("keep_format", "any").lower()
    if keep_format == "any":
        return {"deleted": 0, "bytes_freed": 0}

    # preferred: the format to keep; inferior: the format to delete when preferred exists
    if keep_format == "ass":
        preferred_ext, inferior_ext = ".ass", ".srt"
    else:
        preferred_ext, inferior_ext = ".srt", ".ass"

    # Build index: (dirpath, basename_without_lang_ext) → set of extensions present
    from collections import defaultdict
    index: dict[tuple[str, str], set[str]] = defaultdict(set)
    path_map: dict[tuple[str, str, str], str] = {}

    for path in _subtitle_files(media_path):
        dirpath = os.path.dirname(path)
        fname = os.path.basename(path)
        # Strip lang tag: "Movie.de.ass" → ("Movie.de", ".ass")
        base, ext = os.path.splitext(fname)
        key = (dirpath, base)
        index[key].add(ext.lower())
        path_map[(dirpath, base, ext.lower())] = path

    deleted = 0
    bytes_freed = 0
    would_delete = 0

    for (dirpath, base), exts in index.items():
        if preferred_ext in exts and inferior_ext in exts:
            inferior_path = path_map.get((dirpath, base, inferior_ext))
            if inferior_path:
                file_size = os.path.getsize(inferior_path)
                if dry_run:
                    would_delete += 1
                    logger.debug("Would delete (format_upgrade): %s", inferior_path)
                else:
                    try:
                        os.remove(inferior_path)
                        deleted += 1
                        bytes_freed += file_size
                        logger.info("Deleted (format_upgrade): %s", inferior_path)
                    except OSError as e:
                        logger.warning("Failed to delete %s: %s", inferior_path, e)

    if dry_run:
        return {"would_delete": would_delete}
    return {"deleted": deleted, "bytes_freed": bytes_freed}


def execute_orphan_files(media_path: str, config: dict, dry_run: bool = False) -> dict:
    """Delete subtitle sidecars that have no matching video file in the same directory.

    A subtitle is considered orphaned when no file with a video extension shares
    the same directory.

    Args:
        media_path: Root directory to scan recursively.
        config: {} (no configuration needed)
        dry_run: If True, return counts without deleting.

    Returns:
        {"deleted": int, "bytes_freed": int}
    """
    deleted = 0
    bytes_freed = 0
    would_delete = 0

    for path in _subtitle_files(media_path):
        dirpath = os.path.dirname(path)
        siblings = os.listdir(dirpath)
        has_video = any(
            os.path.splitext(s)[1].lower() in VIDEO_EXTENSIONS for s in siblings
        )
        if not has_video:
            file_size = os.path.getsize(path)
            if dry_run:
                would_delete += 1
                logger.debug("Would delete (orphan_files): %s", path)
            else:
                try:
                    os.remove(path)
                    deleted += 1
                    bytes_freed += file_size
                    logger.info("Deleted (orphan_files): %s", path)
                except OSError as e:
                    logger.warning("Failed to delete %s: %s", path, e)

    if dry_run:
        return {"would_delete": would_delete}
    return {"deleted": deleted, "bytes_freed": bytes_freed}


def execute_orphan_db(config: dict, dry_run: bool = False) -> dict:
    """Remove DB subtitle entries whose file no longer exists on disk.

    Args:
        config: {} (no configuration needed)
        dry_run: If True, return counts without deleting.

    Returns:
        {"deleted": int}
    """
    from db.repositories.subtitles import SubtitleRepository

    repo = SubtitleRepository()
    paths = repo.get_all_subtitle_paths()
    deleted = 0
    would_delete = 0

    for path in paths:
        if not os.path.exists(path):
            if dry_run:
                would_delete += 1
                logger.debug("Would remove DB entry (orphan_db): %s", path)
            else:
                repo.delete_by_path(path)
                deleted += 1
                logger.info("Removed DB entry (orphan_db): %s", path)

    if dry_run:
        return {"would_delete": would_delete}
    return {"deleted": deleted}
```

- [ ] **Step 4: Run tests — confirm they pass**

```bash
cd backend
python -m pytest tests/test_cleanup_executors.py -v
```

Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add backend/services/cleanup_executors.py backend/tests/test_cleanup_executors.py
git commit -m "feat: add language_filter, format_upgrade, orphan_files, orphan_db executors"
```

---

## Task 4: Backend Routes — wire executors + add preview endpoint

**Files:**
- Modify: `backend/routes/cleanup.py`

- [ ] **Step 1: Update `run_rule` to dispatch to new executors**

Find the `run_rule` function (around line 682). Replace the rule execution section:

```python
@bp.route("/rules/<int:rule_id>/run", methods=["POST"])
def run_rule(rule_id: int):
    """Execute a cleanup rule immediately."""
    from config import get_settings
    from db.repositories.cleanup import CleanupRepository
    from services.cleanup_executors import (
        execute_language_filter,
        execute_format_upgrade,
        execute_orphan_files,
        execute_orphan_db,
    )

    repo = CleanupRepository()
    rule = repo.get_rule(rule_id)
    if not rule:
        return jsonify({"error": "Rule not found"}), 404

    settings = get_settings()
    media_path = settings.media_path
    rule_type = rule["rule_type"]
    config = rule.get("config_json", {})

    try:
        if rule_type == "language_filter":
            result = execute_language_filter(media_path, config, dry_run=False)
        elif rule_type == "format_upgrade":
            result = execute_format_upgrade(media_path, config, dry_run=False)
        elif rule_type == "orphan_files":
            result = execute_orphan_files(media_path, config, dry_run=False)
        elif rule_type == "orphan_db":
            result = execute_orphan_db(config, dry_run=False)
        else:
            return jsonify({"error": f"Unknown rule type: {rule_type}"}), 400

        repo.update_rule_last_run(rule_id)
        repo.log_cleanup(
            action_type=rule_type,
            rule_id=rule_id,
            files_deleted=result.get("deleted", 0),
            bytes_freed=result.get("bytes_freed", 0),
        )
        return jsonify({"status": "ok", "result": result})
    except Exception as e:
        logger.error("Rule %d (%s) failed: %s", rule_id, rule_type, e)
        return jsonify({"error": str(e)}), 500
```

- [ ] **Step 2: Add `POST /rules/<id>/preview` endpoint**

Add after the `run_rule` function:

```python
@bp.route("/rules/<int:rule_id>/preview", methods=["POST"])
def preview_rule(rule_id: int):
    """Dry-run a cleanup rule — return what would be deleted without deleting.
    ---
    post:
      tags: [Cleanup]
      summary: Preview rule execution (dry-run)
      responses:
        200:
          description: Preview result
        404:
          description: Rule not found
    """
    from config import get_settings
    from db.repositories.cleanup import CleanupRepository
    from services.cleanup_executors import (
        execute_language_filter,
        execute_format_upgrade,
        execute_orphan_files,
        execute_orphan_db,
    )

    repo = CleanupRepository()
    rule = repo.get_rule(rule_id)
    if not rule:
        return jsonify({"error": "Rule not found"}), 404

    settings = get_settings()
    media_path = settings.media_path
    rule_type = rule["rule_type"]
    config = rule.get("config_json", {})

    try:
        if rule_type == "language_filter":
            result = execute_language_filter(media_path, config, dry_run=True)
        elif rule_type == "format_upgrade":
            result = execute_format_upgrade(media_path, config, dry_run=True)
        elif rule_type == "orphan_files":
            result = execute_orphan_files(media_path, config, dry_run=True)
        elif rule_type == "orphan_db":
            result = execute_orphan_db(config, dry_run=True)
        else:
            return jsonify({"error": f"Unknown rule type: {rule_type}"}), 400

        return jsonify({"rule_id": rule_id, "rule_type": rule_type, "preview": result})
    except Exception as e:
        logger.error("Preview for rule %d failed: %s", rule_id, e)
        return jsonify({"error": str(e)}), 500
```

- [ ] **Step 3: Update `create_rule` route to pass `schedule`**

Find `create_rule` route (around line 518). In the call to `repo.create_rule(...)`, add:

```python
schedule = data.get("schedule", "manual")
# ... existing validation ...
rule = repo.create_rule(
    name=name,
    rule_type=rule_type,
    config_json=config_json,
    enabled=enabled,
    schedule=schedule,
)
```

- [ ] **Step 4: Update `update_rule` route to pass `schedule`**

Find `update_rule` route (around line 590). Add handling for `schedule`:

```python
update_kwargs = {}
if "name" in data:
    update_kwargs["name"] = data["name"]
if "enabled" in data:
    update_kwargs["enabled"] = data["enabled"]
if "config_json" in data:
    update_kwargs["config_json"] = data["config_json"]
if "schedule" in data:
    update_kwargs["schedule"] = data["schedule"]
updated = repo.update_rule(rule_id, **update_kwargs)
```

- [ ] **Step 5: Run pre-PR backend check**

```bash
cd backend
ruff check . && ruff format --check .
python -m pytest tests/test_cleanup_executors.py -v --tb=short -q
```

Expected: ruff clean, 4 tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/routes/cleanup.py
git commit -m "feat: wire new rule executors in cleanup routes, add preview endpoint"
```

---

## Task 5: Scheduler — per-rule schedule + new executors

**Files:**
- Modify: `backend/cleanup_scheduler.py`

- [ ] **Step 1: Update `_execute_cleanup` to dispatch per rule type and respect schedule**

Find `_execute_cleanup` method. Replace the rule-type dispatch loop:

```python
def _execute_cleanup(self):
    """Run enabled cleanup rules that match 'daily' or 'weekly' schedule."""
    from config import get_settings
    from db.repositories.cleanup import CleanupRepository
    from dedup_engine import scan_for_duplicates
    from services.cleanup_executors import (
        execute_language_filter,
        execute_format_upgrade,
        execute_orphan_files,
        execute_orphan_db,
    )

    self._executing = True
    try:
        self._expire_zombie_jobs()

        repo = CleanupRepository()
        rules = repo.get_rules()
        settings = get_settings()
        media_path = settings.media_path

        scheduled_rules = [
            r for r in rules
            if r.get("enabled") and r.get("schedule") in ("daily", "weekly", "after_scan")
        ]

        if not scheduled_rules:
            logger.info("No scheduled cleanup rules to execute")
            return

        logger.info("Executing %d scheduled cleanup rules", len(scheduled_rules))

        for rule in scheduled_rules:
            rule_type = rule["rule_type"]
            rule_id = rule["id"]
            config = rule.get("config_json", {})
            try:
                if rule_type == "language_filter":
                    result = execute_language_filter(media_path, config, dry_run=False)
                elif rule_type == "format_upgrade":
                    result = execute_format_upgrade(media_path, config, dry_run=False)
                elif rule_type == "orphan_files":
                    result = execute_orphan_files(media_path, config, dry_run=False)
                elif rule_type == "orphan_db":
                    result = execute_orphan_db(config, dry_run=False)
                elif rule_type == "dedup":
                    result = scan_for_duplicates(media_path, socketio=self._socketio)
                else:
                    logger.warning("Unknown rule type in scheduler: %s", rule_type)
                    continue

                repo.update_rule_last_run(rule_id)
                repo.log_cleanup(
                    action_type=rule_type,
                    rule_id=rule_id,
                    files_deleted=result.get("deleted", 0),
                    bytes_freed=result.get("bytes_freed", 0),
                )
                logger.info("Rule %d (%s) completed: %s", rule_id, rule_type, result)
            except Exception as e:
                logger.error("Rule %d (%s) failed: %s", rule_id, rule_type, e)
    finally:
        self._executing = False
```

- [ ] **Step 2: Run tests**

```bash
cd backend
python -m pytest tests/test_cleanup_executors.py -v --tb=short -q
```

Expected: 4 PASSED (scheduler code has no dedicated test — covered by executor tests)

- [ ] **Step 3: Commit**

```bash
git add backend/cleanup_scheduler.py
git commit -m "feat: cleanup scheduler dispatches per-rule type with schedule field"
```

---

## Task 6: Frontend Types + API

**Files:**
- Modify: `frontend/src/types/system.ts`
- Modify: `frontend/src/api/system/tasks.ts`
- Modify: `frontend/src/hooks/useSystemApi.ts`

- [ ] **Step 1: Update CleanupRule type**

In `frontend/src/types/system.ts`, find `interface CleanupRule` (line 371) and replace:

```typescript
export interface CleanupRule {
  id: number
  name: string
  rule_type: 'dedup' | 'orphaned' | 'old_backups' | 'language_filter' | 'format_upgrade' | 'orphan_files' | 'orphan_db'
  config_json: Record<string, unknown>
  enabled: boolean
  schedule: 'manual' | 'daily' | 'weekly' | 'after_scan'
  last_run_at: string | null
  created_at: string
}
```

- [ ] **Step 2: Add previewCleanupRule API call**

In `frontend/src/api/system/tasks.ts`, add after `runCleanupRule`:

```typescript
export async function previewCleanupRule(id: number): Promise<{
  rule_id: number
  rule_type: string
  preview: Record<string, number>
}> {
  const response = await client.post(`/api/v1/cleanup/rules/${id}/preview`)
  return response.data
}
```

Also update `createCleanupRule` to include `schedule` in the type:

```typescript
export async function createCleanupRule(rule: Omit<CleanupRule, 'id' | 'last_run_at' | 'created_at'>): Promise<CleanupRule> {
  const response = await client.post('/api/v1/cleanup/rules', rule)
  return response.data
}
```

- [ ] **Step 3: Add useRulePreview hook**

In `frontend/src/hooks/useSystemApi.ts`, add after `useRunCleanupRule`:

```typescript
export function useRulePreview() {
  return useMutation({
    mutationFn: (id: number) => previewCleanupRule(id),
  })
}
```

Add `previewCleanupRule` to the import from `@/api/system/tasks`.

- [ ] **Step 4: Check TypeScript compiles**

```bash
cd frontend
npx tsc --noEmit 2>&1 | head -20
```

Expected: No errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/system.ts frontend/src/api/system/tasks.ts frontend/src/hooks/useSystemApi.ts
git commit -m "feat: extend CleanupRule type with schedule and new rule types, add preview hook"
```

---

## Task 7: Frontend — Config Sub-Components

**Files:**
- Create: `frontend/src/components/cleanup/LanguageFilterConfig.tsx`
- Create: `frontend/src/components/cleanup/FormatUpgradeConfig.tsx`
- Create: `frontend/src/components/cleanup/SchedulePicker.tsx`

- [ ] **Step 1: Create LanguageFilterConfig**

Create `frontend/src/components/cleanup/LanguageFilterConfig.tsx`:

```typescript
import { useState } from 'react'
import { X } from 'lucide-react'

// Common languages for the picker dropdown
const COMMON_LANGUAGES = [
  { code: 'de', label: 'Deutsch', flag: '🇩🇪' },
  { code: 'en', label: 'Englisch', flag: '🇬🇧' },
  { code: 'ja', label: 'Japanisch', flag: '🇯🇵' },
  { code: 'fr', label: 'Französisch', flag: '🇫🇷' },
  { code: 'es', label: 'Spanisch', flag: '🇪🇸' },
  { code: 'it', label: 'Italienisch', flag: '🇮🇹' },
  { code: 'pt', label: 'Portugiesisch', flag: '🇵🇹' },
  { code: 'ru', label: 'Russisch', flag: '🇷🇺' },
  { code: 'ar', label: 'Arabisch', flag: '🇸🇦' },
  { code: 'zh', label: 'Chinesisch', flag: '🇨🇳' },
  { code: 'ko', label: 'Koreanisch', flag: '🇰🇷' },
  { code: 'pl', label: 'Polnisch', flag: '🇵🇱' },
]

interface LanguageFilterConfigProps {
  value: string[]
  onChange: (langs: string[]) => void
}

export function LanguageFilterConfig({ value, onChange }: LanguageFilterConfigProps) {
  const [showDropdown, setShowDropdown] = useState(false)

  const addLang = (code: string) => {
    if (!value.includes(code)) onChange([...value, code])
    setShowDropdown(false)
  }

  const removeLang = (code: string) => onChange(value.filter((l) => l !== code))

  const getLang = (code: string) =>
    COMMON_LANGUAGES.find((l) => l.code === code) ?? { code, label: code.toUpperCase(), flag: '🌐' }

  const available = COMMON_LANGUAGES.filter((l) => !value.includes(l.code))

  return (
    <div className="space-y-3">
      <div className="text-[10px] font-semibold uppercase tracking-wide" style={{ color: 'var(--text-muted)' }}>
        Behalten
      </div>
      <div className="flex flex-wrap gap-2">
        {value.map((code) => {
          const lang = getLang(code)
          return (
            <span
              key={code}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium"
              style={{ background: 'var(--accent-bg)', border: '1px solid var(--accent)', color: 'var(--accent)' }}
            >
              <span>{lang.flag}</span>
              {lang.label} ({code})
              <button
                onClick={() => removeLang(code)}
                className="ml-0.5 opacity-70 hover:opacity-100"
              >
                <X size={10} />
              </button>
            </span>
          )
        })}

        <div className="relative">
          <button
            onClick={() => setShowDropdown(!showDropdown)}
            className="flex items-center gap-1 px-2.5 py-1 rounded-md text-xs border border-dashed"
            style={{ borderColor: 'var(--border)', color: 'var(--text-muted)' }}
          >
            + Sprache hinzufügen
          </button>
          {showDropdown && available.length > 0 && (
            <div
              className="absolute top-8 left-0 z-10 rounded-lg shadow-lg py-1 min-w-[180px]"
              style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)' }}
            >
              {available.map((lang) => (
                <button
                  key={lang.code}
                  onClick={() => addLang(lang.code)}
                  className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-left hover:opacity-80"
                  style={{ color: 'var(--text-primary)' }}
                >
                  <span>{lang.flag}</span> {lang.label}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
      <div className="text-xs" style={{ color: 'var(--text-muted)' }}>
        NFO-Dateien (.nfo) werden nie angefasst.
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Create FormatUpgradeConfig**

Create `frontend/src/components/cleanup/FormatUpgradeConfig.tsx`:

```typescript
type KeepFormat = 'any' | 'ass' | 'srt'

interface FormatUpgradeConfigProps {
  value: KeepFormat
  onChange: (format: KeepFormat) => void
}

const OPTIONS: { value: KeepFormat; label: string; desc: string }[] = [
  { value: 'any', label: 'Beide behalten', desc: 'SRT und ASS gleichzeitig' },
  { value: 'ass', label: 'ASS bevorzugen', desc: 'SRT löschen wenn ASS vorhanden' },
  { value: 'srt', label: 'SRT bevorzugen', desc: 'ASS löschen wenn SRT vorhanden' },
]

export function FormatUpgradeConfig({ value, onChange }: FormatUpgradeConfigProps) {
  return (
    <div className="flex gap-3">
      {OPTIONS.map((opt) => (
        <button
          key={opt.value}
          onClick={() => onChange(opt.value)}
          className="flex-1 p-3 rounded-lg text-left transition-all"
          style={{
            background: value === opt.value ? 'var(--accent-bg)' : 'var(--bg-primary)',
            border: `1px solid ${value === opt.value ? 'var(--accent)' : 'var(--border)'}`,
          }}
        >
          <div
            className="text-xs font-semibold mb-0.5"
            style={{ color: value === opt.value ? 'var(--accent)' : 'var(--text-primary)' }}
          >
            {opt.label}
          </div>
          <div className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
            {opt.desc}
          </div>
        </button>
      ))}
    </div>
  )
}
```

- [ ] **Step 3: Create SchedulePicker**

Create `frontend/src/components/cleanup/SchedulePicker.tsx`:

```typescript
type Schedule = 'manual' | 'daily' | 'weekly' | 'after_scan'

interface SchedulePickerProps {
  value: Schedule
  onChange: (schedule: Schedule) => void
}

const OPTIONS: { value: Schedule; label: string }[] = [
  { value: 'manual', label: 'Manuell' },
  { value: 'daily', label: 'Täglich (03:00)' },
  { value: 'weekly', label: 'Wöchentlich' },
  { value: 'after_scan', label: 'Nach jedem Scan' },
]

export function SchedulePicker({ value, onChange }: SchedulePickerProps) {
  return (
    <div className="flex flex-wrap gap-2">
      {OPTIONS.map((opt) => (
        <button
          key={opt.value}
          onClick={() => onChange(opt.value)}
          className="px-3 py-1.5 rounded-full text-xs font-medium transition-all"
          style={{
            background: value === opt.value ? 'var(--accent-bg)' : 'var(--bg-primary)',
            border: `1px solid ${value === opt.value ? 'var(--accent)' : 'var(--border)'}`,
            color: value === opt.value ? 'var(--accent)' : 'var(--text-muted)',
          }}
        >
          {opt.label}
        </button>
      ))}
    </div>
  )
}
```

- [ ] **Step 4: TypeScript check**

```bash
cd frontend
npx tsc --noEmit 2>&1 | head -20
```

Expected: No errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/cleanup/LanguageFilterConfig.tsx \
        frontend/src/components/cleanup/FormatUpgradeConfig.tsx \
        frontend/src/components/cleanup/SchedulePicker.tsx
git commit -m "feat: add LanguageFilterConfig, FormatUpgradeConfig, SchedulePicker components"
```

---

## Task 8: Frontend — RuleSidebar + RuleDetail

**Files:**
- Create: `frontend/src/components/cleanup/RuleSidebar.tsx`
- Create: `frontend/src/components/cleanup/RuleDetail.tsx`

- [ ] **Step 1: Create RuleSidebar**

Create `frontend/src/components/cleanup/RuleSidebar.tsx`:

```typescript
import { Plus } from 'lucide-react'
import type { CleanupRule } from '@/types/system'

const TYPE_META: Record<string, { icon: string; label: string; colorClass: string }> = {
  language_filter: { icon: '🌐', label: 'Sprache', colorClass: 'type-lang' },
  format_upgrade:  { icon: '⬆️', label: 'Qualität', colorClass: 'type-quality' },
  orphan_files:    { icon: '🗑️', label: 'Orphan',  colorClass: 'type-orphan' },
  orphan_db:       { icon: '🗄️', label: 'Datenbank', colorClass: 'type-db' },
  dedup:           { icon: '🔍', label: 'Dedup',   colorClass: 'type-dedup' },
}

const SCHEDULE_LABELS: Record<string, string> = {
  manual: 'Manuell',
  daily: '🕐 Täglich',
  weekly: '🕐 Wöchentlich',
  after_scan: '🕐 Nach Scan',
}

interface RuleSidebarProps {
  rules: CleanupRule[]
  selectedId: number | null
  onSelect: (id: number) => void
  onNew: () => void
}

export function RuleSidebar({ rules, selectedId, onSelect, onNew }: RuleSidebarProps) {
  return (
    <div
      className="flex flex-col flex-shrink-0"
      style={{ width: 260, background: 'var(--bg-surface)', borderRight: '1px solid var(--border)' }}
    >
      <div className="flex items-center justify-between px-4 py-3">
        <span className="text-[10px] font-semibold uppercase tracking-wide" style={{ color: 'var(--text-muted)' }}>
          Regeln
        </span>
        <button
          onClick={onNew}
          className="flex items-center gap-1 px-2.5 py-1 rounded text-xs font-medium"
          style={{ border: '1px solid var(--accent)', color: 'var(--accent)' }}
        >
          <Plus size={10} /> Neu
        </button>
      </div>

      <div className="flex flex-col gap-1 px-2 overflow-y-auto">
        {rules.map((rule) => {
          const meta = TYPE_META[rule.rule_type] ?? { icon: '⚙️', label: rule.rule_type, colorClass: '' }
          const isActive = rule.id === selectedId
          return (
            <button
              key={rule.id}
              onClick={() => onSelect(rule.id)}
              className="w-full text-left rounded-lg p-2.5 transition-all"
              style={{
                background: isActive ? 'var(--accent-bg)' : 'transparent',
                border: `1px solid ${isActive ? 'var(--accent)' : 'transparent'}`,
              }}
            >
              <div className="flex items-center gap-2 mb-1">
                <span
                  className="flex items-center justify-center rounded-md text-sm flex-shrink-0"
                  style={{ width: 28, height: 28, background: 'var(--bg-primary)' }}
                >
                  {meta.icon}
                </span>
                <span className="flex-1 text-sm font-medium truncate" style={{ color: 'var(--text-primary)' }}>
                  {rule.name}
                </span>
                <span
                  className="w-2 h-2 rounded-full flex-shrink-0"
                  style={{ background: rule.enabled ? 'var(--success)' : 'var(--border)' }}
                />
              </div>
              <div className="flex items-center gap-1.5 pl-9">
                <span
                  className="text-[10px] font-medium px-1.5 py-0.5 rounded uppercase"
                  style={{ background: 'var(--bg-primary)', color: 'var(--accent)' }}
                >
                  {meta.label}
                </span>
                <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
                  {SCHEDULE_LABELS[rule.schedule] ?? rule.schedule}
                </span>
              </div>
            </button>
          )
        })}

        {rules.length === 0 && (
          <div className="px-3 py-6 text-xs text-center" style={{ color: 'var(--text-muted)' }}>
            Noch keine Regeln. Erstelle eine um loszulegen.
          </div>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Create RuleDetail**

Create `frontend/src/components/cleanup/RuleDetail.tsx`:

```typescript
import { Play, Eye, Trash2, Power } from 'lucide-react'
import type { CleanupRule } from '@/types/system'
import { LanguageFilterConfig } from './LanguageFilterConfig'
import { FormatUpgradeConfig } from './FormatUpgradeConfig'
import { SchedulePicker } from './SchedulePicker'

interface PreviewResult {
  would_delete?: number
  would_keep?: number
  would_free_bytes?: number
}

interface RuleDetailProps {
  rule: CleanupRule
  previewResult: PreviewResult | null
  isRunning: boolean
  isPreviewing: boolean
  onRun: () => void
  onPreview: () => void
  onDelete: () => void
  onUpdate: (patch: Partial<CleanupRule>) => void
}

const TYPE_DESCRIPTIONS: Record<string, string> = {
  language_filter: 'Löscht Sidecar-Dateien in nicht erlaubten Sprachen',
  format_upgrade:  'Löscht SRT wenn ASS für dieselbe Episode existiert',
  orphan_files:    'Löscht Subtitle-Sidecars ohne zugehörige Videodatei auf Disk',
  orphan_db:       'Entfernt DB-Einträge deren Datei auf Disk fehlt',
  dedup:           'Findet und löscht doppelte Untertitel-Dateien',
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${units[i]}`
}

export function RuleDetail({
  rule, previewResult, isRunning, isPreviewing,
  onRun, onPreview, onDelete, onUpdate,
}: RuleDetailProps) {
  const config = rule.config_json as Record<string, unknown>

  const updateConfig = (patch: Record<string, unknown>) =>
    onUpdate({ config_json: { ...config, ...patch } })

  return (
    <div className="flex flex-col gap-5 p-6 overflow-y-auto flex-1">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div
            className="flex items-center justify-center rounded-xl text-2xl flex-shrink-0"
            style={{ width: 44, height: 44, background: 'var(--accent-bg)' }}
          >
            {rule.rule_type === 'language_filter' ? '🌐' :
             rule.rule_type === 'format_upgrade' ? '⬆️' :
             rule.rule_type === 'orphan_files' ? '🗑️' :
             rule.rule_type === 'orphan_db' ? '🗄️' : '⚙️'}
          </div>
          <div>
            <div className="text-lg font-semibold" style={{ color: 'var(--text-primary)' }}>{rule.name}</div>
            <div className="text-xs" style={{ color: 'var(--text-muted)' }}>
              {TYPE_DESCRIPTIONS[rule.rule_type] ?? rule.rule_type}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => onUpdate({ enabled: !rule.enabled })}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium"
            style={{
              border: '1px solid var(--border)',
              color: rule.enabled ? 'var(--success)' : 'var(--text-muted)',
            }}
          >
            <Power size={12} />
            {rule.enabled ? 'Aktiv' : 'Deaktiviert'}
          </button>
          <button
            onClick={onPreview}
            disabled={isPreviewing}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium"
            style={{ border: '1px solid var(--border)', color: 'var(--text-secondary)' }}
          >
            <Eye size={12} />
            {isPreviewing ? 'Lädt...' : 'Vorschau'}
          </button>
          <button
            onClick={onRun}
            disabled={isRunning}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-white"
            style={{ background: 'var(--accent)' }}
          >
            <Play size={12} />
            {isRunning ? 'Läuft...' : 'Jetzt ausführen'}
          </button>
          <button
            onClick={onDelete}
            className="flex items-center gap-1.5 px-2 py-1.5 rounded-lg text-xs"
            style={{ border: '1px solid var(--error-dim, #3a1a1a)', color: 'var(--error)' }}
          >
            <Trash2 size={12} />
          </button>
        </div>
      </div>

      {/* Last run bar */}
      {rule.last_run_at && (
        <div
          className="flex items-center gap-2 px-3 py-2 rounded-lg text-xs"
          style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)' }}
        >
          <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: 'var(--success)' }} />
          <span style={{ color: 'var(--success)' }}>Letzter Lauf erfolgreich</span>
          <span className="ml-auto" style={{ color: 'var(--text-muted)' }}>
            {new Date(rule.last_run_at).toLocaleString('de-DE')}
          </span>
        </div>
      )}

      {/* Config sections */}
      {rule.rule_type === 'language_filter' && (
        <ConfigSection title="Erlaubte Sprachen" icon="🌐">
          <LanguageFilterConfig
            value={(config.keep_languages as string[]) ?? []}
            onChange={(langs) => updateConfig({ keep_languages: langs })}
          />
        </ConfigSection>
      )}

      {rule.rule_type === 'format_upgrade' && (
        <ConfigSection title="Format-Präferenz" icon="📄">
          <FormatUpgradeConfig
            value={(config.keep_format as 'any' | 'ass' | 'srt') ?? 'any'}
            onChange={(fmt) => updateConfig({ keep_format: fmt })}
          />
        </ConfigSection>
      )}

      <ConfigSection title="Zeitplan" icon="🕐">
        <SchedulePicker
          value={rule.schedule}
          onChange={(s) => onUpdate({ schedule: s })}
        />
      </ConfigSection>

      {/* Preview result */}
      {previewResult && (
        <ConfigSection title="Vorschau" icon="👁️">
          <div className="space-y-1.5">
            {Object.entries(previewResult).map(([key, val]) => (
              <div key={key} className="flex justify-between text-xs">
                <span style={{ color: 'var(--text-muted)' }}>{key}</span>
                <span style={{ color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>
                  {typeof val === 'number' && key.includes('byte') ? formatBytes(val) : val}
                </span>
              </div>
            ))}
          </div>
        </ConfigSection>
      )}
    </div>
  )
}

function ConfigSection({ title, icon, children }: { title: string; icon: string; children: React.ReactNode }) {
  return (
    <div
      className="rounded-xl overflow-hidden"
      style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)' }}
    >
      <div
        className="flex items-center gap-2.5 px-4 py-3"
        style={{ borderBottom: '1px solid var(--border)' }}
      >
        <span
          className="flex items-center justify-center rounded-md text-sm"
          style={{ width: 26, height: 26, background: 'var(--accent-bg)' }}
        >
          {icon}
        </span>
        <span className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{title}</span>
      </div>
      <div className="p-4">{children}</div>
    </div>
  )
}
```

- [ ] **Step 3: TypeScript check**

```bash
cd frontend
npx tsc --noEmit 2>&1 | head -20
```

Expected: No errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/cleanup/RuleSidebar.tsx \
        frontend/src/components/cleanup/RuleDetail.tsx
git commit -m "feat: add RuleSidebar and RuleDetail components"
```

---

## Task 9: Frontend — CleanupSettings page

**Files:**
- Create: `frontend/src/pages/Settings/CleanupSettings.tsx`
- Create: `frontend/src/pages/Settings/__tests__/CleanupSettings.test.tsx`

- [ ] **Step 1: Write failing tests**

Create `frontend/src/pages/Settings/__tests__/CleanupSettings.test.tsx`:

```typescript
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

vi.mock('@/hooks/useSystemApi', () => ({
  useCleanupRules: () => ({ data: [], isLoading: false }),
  useCreateCleanupRule: () => ({ mutate: vi.fn(), isPending: false }),
  useUpdateCleanupRule: () => ({ mutate: vi.fn() }),
  useDeleteCleanupRule: () => ({ mutate: vi.fn() }),
  useRunCleanupRule: () => ({ mutate: vi.fn(), isPending: false }),
  useRulePreview: () => ({ mutate: vi.fn(), isPending: false }),
  useCleanupStats: () => ({ data: null, isLoading: false }),
  useStartCleanupScan: () => ({ mutate: vi.fn(), isPending: false }),
  useCleanupScanStatus: () => ({ data: null }),
  useDuplicates: () => ({ data: null, refetch: vi.fn() }),
  useDeleteDuplicates: () => ({ mutate: vi.fn(), isPending: false }),
  useOrphanedScan: () => ({ mutate: vi.fn(), isPending: false }),
  useOrphanedFiles: () => ({ data: null, refetch: vi.fn() }),
  useDeleteOrphaned: () => ({ mutate: vi.fn(), isPending: false }),
  useCleanupHistory: () => ({ data: null }),
  useCleanupPreview: () => ({ mutate: vi.fn() }),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string, fb: string) => fb ?? k }),
}))

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('CleanupSettings', () => {
  it('renders the page heading', async () => {
    const { CleanupSettings } = await import('../CleanupSettings')
    wrap(<CleanupSettings />)
    expect(screen.getByText(/Cleanup Rules/i)).toBeTruthy()
  })

  it('shows empty state when no rules exist', async () => {
    const { CleanupSettings } = await import('../CleanupSettings')
    wrap(<CleanupSettings />)
    expect(screen.getByText(/Noch keine Regeln/i)).toBeTruthy()
  })

  it('shows "+ Neu" button in sidebar', async () => {
    const { CleanupSettings } = await import('../CleanupSettings')
    wrap(<CleanupSettings />)
    expect(screen.getByText('Neu')).toBeTruthy()
  })
})
```

- [ ] **Step 2: Run tests — confirm they fail**

```bash
cd frontend
npm run test -- --run src/pages/Settings/__tests__/CleanupSettings.test.tsx 2>&1 | tail -10
```

Expected: FAIL — `CleanupSettings` not found.

- [ ] **Step 3: Create CleanupSettings page**

Create `frontend/src/pages/Settings/CleanupSettings.tsx`:

```typescript
/**
 * CleanupSettings — dedicated Settings page for subtitle cleanup rule management.
 *
 * Layout:
 *   Left sidebar: rule list + new rule button
 *   Right main: disk space widget, rule detail, dedup section, history
 */
import { useState, useCallback, useEffect, lazy, Suspense } from 'react'
import { useTranslation } from 'react-i18next'
import { Loader2 } from 'lucide-react'
import { PageHeader } from '@/components/layout/PageHeader'
import { RuleSidebar } from '@/components/cleanup/RuleSidebar'
import { RuleDetail } from '@/components/cleanup/RuleDetail'
import { DiskSpaceWidget } from '@/components/cleanup/DiskSpaceWidget'
import { DedupGroupList } from '@/components/cleanup/DedupGroupList'
import { CleanupPreview } from '@/components/cleanup/CleanupPreview'
import { toast } from '@/components/shared/Toast'
import {
  useCleanupRules, useCreateCleanupRule, useUpdateCleanupRule,
  useDeleteCleanupRule, useRunCleanupRule, useRulePreview,
  useCleanupStats, useStartCleanupScan, useCleanupScanStatus,
  useDuplicates, useDeleteDuplicates, useOrphanedScan, useOrphanedFiles,
  useDeleteOrphaned, useCleanupHistory, useCleanupPreview,
} from '@/hooks/useSystemApi'
import type { CleanupRule, CleanupPreviewData } from '@/types/system'

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${units[i]}`
}

// ─── New Rule Modal ──────────────────────────────────────────────────────────

const RULE_TYPES = [
  { value: 'language_filter', label: 'Sprach-Filter', desc: 'Löscht Sidecars in nicht erlaubten Sprachen' },
  { value: 'format_upgrade',  label: 'Format-Upgrade', desc: 'Löscht SRT wenn ASS für gleiche Episode existiert' },
  { value: 'orphan_files',    label: 'Verwaiste Dateien', desc: 'Löscht Subtitle-Sidecars ohne Video auf Disk' },
  { value: 'orphan_db',       label: 'DB-Bereinigung', desc: 'Entfernt DB-Einträge ohne Datei auf Disk' },
]

function NewRuleModal({ onClose, onCreate }: {
  onClose: () => void
  onCreate: (name: string, rule_type: string) => void
}) {
  const [name, setName] = useState('')
  const [ruleType, setRuleType] = useState('language_filter')

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div
        className="rounded-xl p-6 w-96 space-y-4"
        style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)' }}
      >
        <h3 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
          Neue Cleanup-Regel
        </h3>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Regelname"
          className="w-full px-3 py-2 rounded-lg text-sm focus:outline-none"
          style={{ background: 'var(--bg-primary)', border: '1px solid var(--border)', color: 'var(--text-primary)' }}
        />
        <div className="space-y-2">
          {RULE_TYPES.map((rt) => (
            <label
              key={rt.value}
              className="flex items-start gap-3 p-3 rounded-lg cursor-pointer"
              style={{
                background: ruleType === rt.value ? 'var(--accent-bg)' : 'var(--bg-primary)',
                border: `1px solid ${ruleType === rt.value ? 'var(--accent)' : 'var(--border)'}`,
              }}
            >
              <input
                type="radio"
                name="ruleType"
                value={rt.value}
                checked={ruleType === rt.value}
                onChange={() => setRuleType(rt.value)}
                className="mt-0.5"
              />
              <div>
                <div className="text-xs font-semibold" style={{ color: 'var(--text-primary)' }}>{rt.label}</div>
                <div className="text-[11px]" style={{ color: 'var(--text-muted)' }}>{rt.desc}</div>
              </div>
            </label>
          ))}
        </div>
        <div className="flex gap-2 justify-end">
          <button
            onClick={onClose}
            className="px-3 py-1.5 rounded text-xs"
            style={{ color: 'var(--text-muted)' }}
          >
            Abbrechen
          </button>
          <button
            onClick={() => { if (name.trim()) onCreate(name.trim(), ruleType) }}
            disabled={!name.trim()}
            className="px-4 py-1.5 rounded text-xs font-medium text-white disabled:opacity-50"
            style={{ background: 'var(--accent)' }}
          >
            Erstellen
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── History Section ─────────────────────────────────────────────────────────

function HistorySection() {
  const { t } = useTranslation('settings')
  const [page, setPage] = useState(1)
  const { data: historyData } = useCleanupHistory(page)
  const entries = historyData?.entries ?? []
  const total = historyData?.total ?? 0

  if (entries.length === 0) return null

  return (
    <div
      className="rounded-xl overflow-hidden"
      style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)' }}
    >
      <div className="px-4 py-3" style={{ borderBottom: '1px solid var(--border)' }}>
        <span className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
          {t('cleanup.history.title', 'Cleanup History')}
        </span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr style={{ borderBottom: '1px solid var(--border)' }}>
              {['Datum', 'Aktion', 'Verarbeitet', 'Gelöscht', 'Freigegeben'].map((h) => (
                <th key={h} className="py-2 px-3 text-left font-medium" style={{ color: 'var(--text-muted)' }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {entries.map((entry) => (
              <tr key={entry.id} style={{ borderBottom: '1px solid var(--border)' }}>
                <td className="py-2 px-3" style={{ color: 'var(--text-secondary)' }}>
                  {new Date(entry.performed_at).toLocaleString('de-DE')}
                </td>
                <td className="py-2 px-3">
                  <span
                    className="px-1.5 py-0.5 rounded text-[10px] font-medium"
                    style={{ background: 'var(--accent-bg)', color: 'var(--accent)' }}
                  >
                    {entry.action_type}
                  </span>
                </td>
                <td className="py-2 px-3 tabular-nums" style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
                  {entry.files_processed}
                </td>
                <td className="py-2 px-3 tabular-nums" style={{ fontFamily: 'var(--font-mono)', color: 'var(--error)' }}>
                  {entry.files_deleted}
                </td>
                <td className="py-2 px-3 tabular-nums" style={{ fontFamily: 'var(--font-mono)', color: 'var(--success)' }}>
                  {formatBytes(entry.bytes_freed)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {total > 50 && (
        <div className="flex items-center justify-center gap-2 p-3">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page <= 1}
            className="px-2 py-1 rounded text-xs disabled:opacity-40"
            style={{ border: '1px solid var(--border)', color: 'var(--text-muted)' }}
          >
            Zurück
          </button>
          <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
            {page} / {Math.ceil(total / 50)}
          </span>
          <button
            onClick={() => setPage((p) => p + 1)}
            disabled={page >= Math.ceil(total / 50)}
            className="px-2 py-1 rounded text-xs disabled:opacity-40"
            style={{ border: '1px solid var(--border)', color: 'var(--text-muted)' }}
          >
            Weiter
          </button>
        </div>
      )}
    </div>
  )
}

// ─── Main Page ───────────────────────────────────────────────────────────────

export function CleanupSettings() {
  const { t } = useTranslation('settings')
  const { data: rules = [], isLoading } = useCleanupRules()
  const { data: stats } = useCleanupStats()
  const createRule = useCreateCleanupRule()
  const updateRule = useUpdateCleanupRule()
  const deleteRule = useDeleteCleanupRule()
  const runRule = useRunCleanupRule()
  const rulePreview = useRulePreview()
  const startScan = useStartCleanupScan()
  const [isScanning, setIsScanning] = useState(false)
  const scanStatus = useCleanupScanStatus(isScanning)
  const { data: duplicatesData, refetch: refetchDuplicates } = useDuplicates()
  const deleteDuplicates = useDeleteDuplicates()
  const cleanupPreview = useCleanupPreview()

  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [showNewModal, setShowNewModal] = useState(false)
  const [previewResult, setPreviewResult] = useState<Record<string, number> | null>(null)
  const [dedupPreviewData, setDedupPreviewData] = useState<CleanupPreviewData | null>(null)
  const [pendingDeleteSelections, setPendingDeleteSelections] = useState<{ keep: string; delete: string[] }[] | null>(null)

  const selectedRule = rules.find((r) => r.id === selectedId) ?? null

  // Auto-select first rule
  useEffect(() => {
    if (rules.length > 0 && selectedId === null) setSelectedId(rules[0].id)
  }, [rules, selectedId])

  // Stop scan polling when done
  useEffect(() => {
    if (scanStatus.data?.status === 'idle' && isScanning) {
      setIsScanning(false)
      void refetchDuplicates()
    }
  }, [scanStatus.data, isScanning, refetchDuplicates])

  const handleCreate = useCallback((name: string, rule_type: string) => {
    createRule.mutate(
      { name, rule_type: rule_type as CleanupRule['rule_type'], config_json: {}, enabled: true, schedule: 'manual' },
      {
        onSuccess: (rule) => { setSelectedId(rule.id); setShowNewModal(false) },
        onError: () => toast('Fehler beim Erstellen der Regel', 'error'),
      }
    )
  }, [createRule])

  const handleUpdate = useCallback((patch: Partial<CleanupRule>) => {
    if (!selectedId) return
    updateRule.mutate({ id: selectedId, data: patch }, {
      onError: () => toast('Fehler beim Speichern', 'error'),
    })
  }, [selectedId, updateRule])

  const handleDelete = useCallback(() => {
    if (!selectedId) return
    deleteRule.mutate(selectedId, {
      onSuccess: () => { setSelectedId(null); toast('Regel gelöscht') },
      onError: () => toast('Fehler beim Löschen', 'error'),
    })
  }, [selectedId, deleteRule])

  const handleRun = useCallback(() => {
    if (!selectedId) return
    runRule.mutate(selectedId, {
      onSuccess: () => toast('Regel erfolgreich ausgeführt'),
      onError: () => toast('Fehler beim Ausführen', 'error'),
    })
  }, [selectedId, runRule])

  const handlePreview = useCallback(() => {
    if (!selectedId) return
    rulePreview.mutate(selectedId, {
      onSuccess: (data) => setPreviewResult(data.preview),
      onError: () => toast('Vorschau fehlgeschlagen', 'error'),
    })
  }, [selectedId, rulePreview])

  const handleStartScan = useCallback(() => {
    startScan.mutate(undefined, {
      onSuccess: () => setIsScanning(true),
      onError: () => toast('Scan fehlgeschlagen', 'error'),
    })
  }, [startScan])

  const handleDeleteDuplicates = useCallback((selections: { keep: string; delete: string[] }[]) => {
    setPendingDeleteSelections(selections)
    cleanupPreview.mutate(undefined, {
      onSuccess: (data) => setDedupPreviewData(data),
      onError: () => {
        deleteDuplicates.mutate(selections, {
          onSuccess: (result) => {
            toast(`${result.deleted} Dateien gelöscht, ${formatBytes(result.bytes_freed)} freigegeben`)
            setPendingDeleteSelections(null)
          },
          onError: () => toast('Fehler beim Löschen', 'error'),
        })
      },
    })
  }, [cleanupPreview, deleteDuplicates])

  const handleConfirmDedupDelete = useCallback(() => {
    if (!pendingDeleteSelections) return
    deleteDuplicates.mutate(pendingDeleteSelections, {
      onSuccess: (result) => {
        toast(`${result.deleted} Dateien gelöscht, ${formatBytes(result.bytes_freed)} freigegeben`)
        setPendingDeleteSelections(null)
        setDedupPreviewData(null)
      },
      onError: () => toast('Fehler beim Löschen', 'error'),
    })
  }, [pendingDeleteSelections, deleteDuplicates])

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 size={28} className="animate-spin" style={{ color: 'var(--accent)' }} />
      </div>
    )
  }

  const groups = duplicatesData?.groups ?? []

  return (
    <div className="flex flex-col h-full">
      <div className="px-6 py-5" style={{ borderBottom: '1px solid var(--border)' }}>
        <PageHeader
          title={t('cleanup.page.title', 'Cleanup Rules')}
          subtitle={t('cleanup.page.subtitle', 'Automatisierte Bereinigung von Sidecar-Dateien und Datenbankeinträgen')}
        />
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar */}
        <RuleSidebar
          rules={rules}
          selectedId={selectedId}
          onSelect={(id) => { setSelectedId(id); setPreviewResult(null) }}
          onNew={() => setShowNewModal(true)}
        />

        {/* Main content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-5">
          {/* Disk space */}
          {stats && <DiskSpaceWidget stats={stats} />}

          {/* Rule detail */}
          {selectedRule ? (
            <RuleDetail
              rule={selectedRule}
              previewResult={previewResult}
              isRunning={runRule.isPending}
              isPreviewing={rulePreview.isPending}
              onRun={handleRun}
              onPreview={handlePreview}
              onDelete={handleDelete}
              onUpdate={handleUpdate}
            />
          ) : (
            <div
              className="rounded-xl p-12 text-center text-sm"
              style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', color: 'var(--text-muted)' }}
            >
              Wähle eine Regel aus der Sidebar oder erstelle eine neue.
            </div>
          )}

          {/* Dedup section */}
          <div
            className="rounded-xl overflow-hidden"
            style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)' }}
          >
            <div className="flex items-center justify-between px-4 py-3" style={{ borderBottom: '1px solid var(--border)' }}>
              <span className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
                {t('cleanup.dedup.title', 'Deduplication')}
              </span>
              <button
                onClick={handleStartScan}
                disabled={isScanning || startScan.isPending}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium text-white disabled:opacity-50"
                style={{ background: 'var(--accent)' }}
              >
                {isScanning ? <Loader2 size={12} className="animate-spin" /> : null}
                {isScanning ? 'Scannt...' : t('cleanup.dedup.scanButton', 'Scan for Duplicates')}
              </button>
            </div>
            <div className="p-4">
              {dedupPreviewData ? (
                <CleanupPreview
                  preview={dedupPreviewData}
                  onConfirm={handleConfirmDedupDelete}
                  onCancel={() => { setDedupPreviewData(null); setPendingDeleteSelections(null) }}
                  isConfirming={deleteDuplicates.isPending}
                />
              ) : groups.length > 0 ? (
                <DedupGroupList groups={groups} onDelete={handleDeleteDuplicates} isDeleting={deleteDuplicates.isPending} />
              ) : (
                <div className="text-sm text-center py-4" style={{ color: 'var(--text-muted)' }}>
                  {t('cleanup.dedup.noResults', 'No duplicates found. Run a scan to check.')}
                </div>
              )}
            </div>
          </div>

          <HistorySection />
        </div>
      </div>

      {showNewModal && (
        <NewRuleModal
          onClose={() => setShowNewModal(false)}
          onCreate={handleCreate}
        />
      )}
    </div>
  )
}
```

- [ ] **Step 4: Run tests — confirm they pass**

```bash
cd frontend
npm run test -- --run src/pages/Settings/__tests__/CleanupSettings.test.tsx 2>&1 | tail -15
```

Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Settings/CleanupSettings.tsx \
        frontend/src/pages/Settings/__tests__/CleanupSettings.test.tsx
git commit -m "feat: add CleanupSettings page with sidebar/detail layout"
```

---

## Task 10: Wire Navigation — Settings tile + route + remove from SubtitlesSettings

**Files:**
- Modify: `frontend/src/components/settings/SettingsGrid.tsx`
- Modify: `frontend/src/pages/Settings/index.tsx`
- Modify: `frontend/src/pages/Settings/SubtitlesSettings.tsx`

- [ ] **Step 1: Add cleanup tile to SettingsGrid**

In `frontend/src/components/settings/SettingsGrid.tsx`, add `Trash2` to the lucide imports, then add to `CATEGORIES` array (before `about`):

```typescript
import {
  Settings, Plug, Subtitles, Globe, Zap, Languages, Bell, Shield, Heart, Trash2,
} from 'lucide-react'
```

```typescript
  {
    id: 'cleanup',
    icon: Trash2,
    titleKey: 'settings.categories.cleanup.title',
    descKey: 'settings.categories.cleanup.description',
    badge: 'Cleanup',
  },
```

Also add to `CATEGORY_FALLBACKS`:

```typescript
  cleanup: { title: 'Cleanup', description: 'Language filters, format upgrades, orphan removal' },
```

- [ ] **Step 2: Add route in Settings/index.tsx**

In `frontend/src/pages/Settings/index.tsx`, add the import:

```typescript
const CleanupSettings = lazy(() =>
  import('./CleanupSettings').then((m) => ({ default: m.CleanupSettings }))
)
```

Add the route inside `<Routes>`:

```typescript
<Route path="cleanup" element={<Suspense fallback={<FormSkeleton />}><CleanupSettings /></Suspense>} />
```

- [ ] **Step 3: Remove CleanupTab from SubtitlesSettings**

In `frontend/src/pages/Settings/SubtitlesSettings.tsx`:

1. Remove the lazy import of `CleanupTab` (lines ~35-37)
2. Remove the `<div data-testid="section-cleanup">` block (and its contents) — the entire section including the `<SettingsSection>` wrapper and `<CleanupTab />`

- [ ] **Step 4: Run full frontend checks**

```bash
cd frontend
npm run lint && npx tsc --noEmit && npm run test -- --run 2>&1 | tail -20
```

Expected: lint clean, no type errors, all tests pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/settings/SettingsGrid.tsx \
        frontend/src/pages/Settings/index.tsx \
        frontend/src/pages/Settings/SubtitlesSettings.tsx
git commit -m "feat: add cleanup settings tile and route, remove CleanupTab from SubtitlesSettings"
```

---

## Task 11: Final Pre-PR Check

- [ ] **Step 1: Run full backend test suite**

```bash
cd backend
python -m pytest --tb=short -q \
  --ignore=tests/performance \
  --ignore=tests/integration/test_provider_pipeline.py \
  --ignore=tests/test_video_sync.py \
  --ignore=tests/test_translation_backends.py \
  -k "not (test_sonarr_download_webhook or test_radarr_download_webhook or test_parse_llm_response_too_many_merge or test_record_backend_success)"
```

Expected: All pass.

- [ ] **Step 2: Run full frontend checks**

```bash
cd frontend
npm run lint && npx tsc --noEmit && npm run test -- --run
```

Expected: lint clean, no type errors, all tests pass.

- [ ] **Step 3: Run ruff on full backend**

```bash
cd backend
ruff check . && ruff format --check .
```

Expected: Clean.

- [ ] **Step 4: Final commit if any fixes were needed, then push**

```bash
git push
```
