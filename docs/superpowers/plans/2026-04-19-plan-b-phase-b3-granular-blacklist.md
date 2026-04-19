# Plan B / Phase B3 — Granular Blacklist (per-provider + file-hash)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-04-19-plan-b-subtitle-delivery-quality-design.md`
**Prior:** B2 shipped as 0.65.0-beta — 29 registered providers total, 7 Subliminal flavors.

**Goal:** Add a `file_hash` dimension to the blacklist so Sublarr can suppress retries for "any subtitle with hash H from provider Y" (catches re-uploaded duplicates, known-bad content) in addition to the existing per-subtitle-ID suppression.

**Scope deviation from spec:** The spec bundled B3 as "Subzero selective merge + granular blacklist". The Subzero part (cherry-picking 3-5 providers from the `subliminal_patch` fork) turned out to be more complex than the spec's one-paragraph estimate — those providers inherit from Subzero-patched base classes, requiring either vendoring the entire `subliminal_patch` monkey-patch set or porting each provider to vanilla `subliminal.providers.Provider`. Given:

1. 29 providers registered (exceeds Bazarr's core set)
2. The Subzero-unique providers (argenteam, assrt, wizdom, subdivx, etc.) cover language niches (Spanish/Hungarian/Hebrew/Greek) that Sublarr users may not prioritize
3. Scrape-based Subzero providers (tusubtitulo, subscenter) are community-reported broken

**Decision:** Ship B3 as granular-blacklist-only. Subzero merge deferred — can re-open as post-Plan-B work, or drop if 29 providers proves sufficient.

**Architecture:** Additive schema change. `blacklist_entries` gets a new nullable `file_hash VARCHAR(64)` column. Composite partial UNIQUE index `(provider_name, file_hash) WHERE file_hash IS NOT NULL` enforces no-duplicates for hash-based entries. Repository gains `add_blacklist_entry_by_hash`, `is_blacklisted_by_hash`, and an extended `is_blacklisted(provider, subtitle_id=None, file_hash=None)` that accepts either discriminator. API + frontend extended to show/accept the hash.

**Tech Stack:** Python 3.12, SQLAlchemy 2.0 ORM, Alembic, PostgreSQL (prod) + SQLite (dev fallback), pytest, React 19 + TypeScript + React Query.

**Baseline:** 0.65.0-beta → 0.66.0-beta (minor bump).

---

## File Structure

### Create

- `backend/db/migrations/versions/2026_04_19_XXXX-<rev>_add_file_hash_to_blacklist.py` — Alembic migration
- `backend/tests/test_blacklist_file_hash.py` — migration + repository + API integration tests

### Modify

- `backend/db/models/core.py` — `BlacklistEntry` model: add `file_hash` column + partial UNIQUE index
- `backend/db/repositories/blacklist.py` — hash-aware methods
- `backend/db/blacklist.py` — delegating wrapper for new methods
- `backend/routes/blacklist/core.py` — API accepts + returns `file_hash`
- `frontend/src/pages/Blacklist.tsx` — UI shows `file_hash` column
- `frontend/src/api/blacklist.ts` (or equivalent hook file) — type + fetcher updates

---

## Task 1: Alembic migration — add `file_hash` column + partial UNIQUE index

**Files:**
- Create: `backend/db/migrations/versions/2026_04_19_XXXX-<rev>_add_file_hash_to_blacklist.py`

Use the current timestamp as prefix: run `date +%Y_%m_%d_%H%M` or check the current time manually.

- [ ] **Step 1: Find the current alembic head**

Run: `cd backend && python -m alembic heads`
Expected: single revision hash (e.g. `7e085763f714`) — record this as `down_revision`.

If multiple heads are printed, merge them first (out of B3 scope — stop and escalate).

- [ ] **Step 2: Generate a revision hash**

Run: `cd backend && python -c "import secrets; print(secrets.token_hex(6))"`
Take the 12-character hex output — record as this migration's `revision`.

- [ ] **Step 3: Write the migration file**

Create `backend/db/migrations/versions/2026_04_19_XXXX-<new_rev>_add_file_hash_to_blacklist.py` (replace `XXXX` with `HHMM` and `<new_rev>` with the hash from Step 2):

```python
"""add file_hash column to blacklist_entries

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
    op.add_column(
        "blacklist_entries",
        sa.Column("file_hash", sa.String(length=64), nullable=True),
    )
    # Partial UNIQUE: enforce no duplicates for hash-based entries,
    # allow multiple NULLs (traditional subtitle_id-based entries).
    op.create_index(
        "idx_blacklist_provider_hash",
        "blacklist_entries",
        ["provider_name", "file_hash"],
        unique=True,
        postgresql_where=sa.text("file_hash IS NOT NULL"),
        sqlite_where=sa.text("file_hash IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_blacklist_provider_hash", table_name="blacklist_entries")
    op.drop_column("blacklist_entries", "file_hash")
```

Replace `<NEW_REV>` (both in filename prefix-suffix and in `revision =`) and `<PRIOR_HEAD>` (in `down_revision =`) with the actual values. Use the HH:MM timestamp matching the filename prefix.

- [ ] **Step 4: Run the migration locally (SQLite dev DB)**

Run: `cd backend && python -m alembic upgrade head`
Expected: `INFO  [alembic.runtime.migration] Running upgrade ... -> <NEW_REV>, add file_hash column to blacklist_entries` — no errors.

- [ ] **Step 5: Verify downgrade reverses cleanly**

Run: `cd backend && python -m alembic downgrade -1 && python -m alembic upgrade head`
Expected: both commands exit 0; final state identical to step 4.

- [ ] **Step 6: Commit**

```bash
git add backend/db/migrations/versions/2026_04_19_XXXX-<new_rev>_add_file_hash_to_blacklist.py
git commit -m "feat(plan-b3): alembic migration — add file_hash to blacklist_entries"
```

---

## Task 2: Update `BlacklistEntry` ORM model

**Files:**
- Modify: `backend/db/models/core.py`

- [ ] **Step 1: Write the failing test for the new column**

Add to `backend/tests/test_blacklist_file_hash.py`:

```python
"""Tests for Plan B3 granular blacklist (file_hash dimension)."""

import pytest

from db.models.core import BlacklistEntry


def test_blacklist_entry_has_file_hash_column():
    """The BlacklistEntry ORM model exposes a file_hash attribute."""
    assert hasattr(BlacklistEntry, "file_hash"), (
        "Expected BlacklistEntry.file_hash after B3 migration"
    )


def test_blacklist_entry_file_hash_default_is_none():
    """Creating a BlacklistEntry without file_hash leaves it as None."""
    from datetime import datetime, timezone

    entry = BlacklistEntry(
        provider_name="opensubtitles",
        subtitle_id="12345",
        language="en",
        added_at=datetime.now(timezone.utc),
    )
    assert entry.file_hash is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_blacklist_file_hash.py::test_blacklist_entry_has_file_hash_column -v`
Expected: FAIL with `AttributeError` or assertion error — column doesn't exist yet on the model.

- [ ] **Step 3: Add the column to the model**

Edit `backend/db/models/core.py` — locate the `class BlacklistEntry(db.Model):` block (around line 237) and add the new column + index to `__table_args__`:

```python
class BlacklistEntry(db.Model):
    """Blacklisted subtitle provider results."""

    __tablename__ = "blacklist_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider_name: Mapped[str] = mapped_column(Text, nullable=False)
    subtitle_id: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str | None] = mapped_column(Text, default="")
    file_path: Mapped[str | None] = mapped_column(Text, default="")
    title: Mapped[str | None] = mapped_column(Text, default="")
    reason: Mapped[str | None] = mapped_column(Text, default="")
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Plan B3 — file-hash dimension for provider-agnostic retry suppression
    file_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)

    __table_args__ = (
        UniqueConstraint("provider_name", "subtitle_id"),
        Index("idx_blacklist_provider", "provider_name", "subtitle_id"),
        Index(
            "idx_blacklist_provider_hash",
            "provider_name",
            "file_hash",
            unique=True,
            postgresql_where=text("file_hash IS NOT NULL"),
            sqlite_where=text("file_hash IS NOT NULL"),
        ),
    )
```

Add the required imports at the top of the file if not already present:

```python
from sqlalchemy import String, text
```

(Both are standard SQLAlchemy imports; the file probably has `String` already — check, don't duplicate. `text` comes from the top-level `sqlalchemy` namespace.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_blacklist_file_hash.py::test_blacklist_entry_has_file_hash_column tests/test_blacklist_file_hash.py::test_blacklist_entry_file_hash_default_is_none -v`
Expected: 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/db/models/core.py backend/tests/test_blacklist_file_hash.py
git commit -m "feat(plan-b3): add file_hash column to BlacklistEntry ORM model"
```

---

## Task 3: Extend `BlacklistRepository` with hash-aware methods

**Files:**
- Modify: `backend/db/repositories/blacklist.py`
- Modify: `backend/tests/test_blacklist_file_hash.py`

- [ ] **Step 1: Write failing test for hash-aware add + check**

Append to `backend/tests/test_blacklist_file_hash.py`:

```python
def test_add_entry_with_file_hash(tmp_path, monkeypatch):
    """add_blacklist_entry() accepts a file_hash kwarg and persists it."""
    from db.repositories.blacklist import BlacklistRepository

    repo = BlacklistRepository()
    entry_id = repo.add_blacklist_entry(
        provider_name="opensubtitles",
        subtitle_id="sub_123",
        file_hash="a" * 64,
        reason="test",
    )
    assert entry_id > 0

    # Existence check by hash works
    assert repo.is_blacklisted_by_hash("opensubtitles", "a" * 64) is True

    # Wrong provider returns False
    assert repo.is_blacklisted_by_hash("gestdown", "a" * 64) is False

    # Wrong hash returns False
    assert repo.is_blacklisted_by_hash("opensubtitles", "b" * 64) is False

    # Cleanup to keep the test DB clean
    repo.remove_blacklist_entry(entry_id)


def test_add_entry_without_file_hash_still_works(tmp_path, monkeypatch):
    """Legacy add_blacklist_entry() call (no file_hash) continues to work."""
    from db.repositories.blacklist import BlacklistRepository

    repo = BlacklistRepository()
    entry_id = repo.add_blacklist_entry(
        provider_name="podnapisi",
        subtitle_id="sub_456",
        reason="legacy path",
    )
    assert entry_id > 0
    # Traditional check still works
    assert repo.is_blacklisted("podnapisi", "sub_456") is True
    repo.remove_blacklist_entry(entry_id)


def test_is_blacklisted_accepts_hash_alternative(tmp_path, monkeypatch):
    """is_blacklisted() can be called with file_hash= instead of subtitle_id."""
    from db.repositories.blacklist import BlacklistRepository

    repo = BlacklistRepository()
    entry_id = repo.add_blacklist_entry(
        provider_name="opensubtitles",
        subtitle_id="sub_999",
        file_hash="c" * 64,
    )
    # Check by subtitle_id (traditional)
    assert repo.is_blacklisted("opensubtitles", subtitle_id="sub_999") is True
    # Check by file_hash (new)
    assert repo.is_blacklisted("opensubtitles", file_hash="c" * 64) is True
    repo.remove_blacklist_entry(entry_id)
```

- [ ] **Step 2: Run tests to verify failure**

Run: `cd backend && python -m pytest tests/test_blacklist_file_hash.py -v -k "add_entry or is_blacklisted_accepts"`
Expected: 3 tests FAIL (method signatures don't yet accept `file_hash`).

- [ ] **Step 3: Update `add_blacklist_entry` to accept `file_hash`**

Edit `backend/db/repositories/blacklist.py`:

```python
    def add_blacklist_entry(
        self,
        provider_name: str,
        subtitle_id: str,
        language: str = "",
        file_path: str = "",
        title: str = "",
        reason: str = "",
        file_hash: str | None = None,
    ) -> int:
        """Add a subtitle to the blacklist. Returns the entry ID.

        If `file_hash` is provided, we also check for existing (provider, hash)
        conflicts — the partial UNIQUE index would reject the insert anyway,
        so we surface the existing ID instead of raising.
        """
        now = self._now()

        # Check by (provider, subtitle_id) first (traditional dimension)
        existing = self.session.execute(
            select(BlacklistEntry).where(
                BlacklistEntry.provider_name == provider_name,
                BlacklistEntry.subtitle_id == subtitle_id,
            )
        ).scalar_one_or_none()
        if existing:
            return existing.id

        # If a file_hash was provided, also check by (provider, file_hash)
        if file_hash is not None:
            existing_by_hash = self.session.execute(
                select(BlacklistEntry).where(
                    BlacklistEntry.provider_name == provider_name,
                    BlacklistEntry.file_hash == file_hash,
                )
            ).scalar_one_or_none()
            if existing_by_hash:
                return existing_by_hash.id

        entry = BlacklistEntry(
            provider_name=provider_name,
            subtitle_id=subtitle_id,
            language=language,
            file_path=file_path,
            title=title,
            reason=reason,
            file_hash=file_hash,
            added_at=now,
        )
        self.session.add(entry)
        self._commit()
        return entry.id or 0
```

- [ ] **Step 4: Add `is_blacklisted_by_hash` + extend `is_blacklisted`**

Replace the existing `is_blacklisted` method in `backend/db/repositories/blacklist.py`:

```python
    def is_blacklisted(
        self,
        provider_name: str,
        subtitle_id: str | None = None,
        file_hash: str | None = None,
    ) -> bool:
        """Check if a subtitle is blacklisted.

        Callers may pass either `subtitle_id` (traditional) or `file_hash`
        (Plan B3). If both are passed, ANY match returns True. If neither is
        passed, returns False (caller error — no discriminator).
        """
        if subtitle_id is None and file_hash is None:
            return False

        conditions = [BlacklistEntry.provider_name == provider_name]
        if subtitle_id is not None and file_hash is not None:
            # Either discriminator matching counts
            from sqlalchemy import or_

            conditions.append(
                or_(
                    BlacklistEntry.subtitle_id == subtitle_id,
                    BlacklistEntry.file_hash == file_hash,
                )
            )
        elif subtitle_id is not None:
            conditions.append(BlacklistEntry.subtitle_id == subtitle_id)
        else:  # file_hash is not None (enforced by the early-return above)
            conditions.append(BlacklistEntry.file_hash == file_hash)

        result = self.session.execute(
            select(BlacklistEntry.id).where(*conditions)
        ).scalar_one_or_none()
        return result is not None

    def is_blacklisted_by_hash(self, provider_name: str, file_hash: str) -> bool:
        """Check if a (provider, file_hash) pair is blacklisted.

        Convenience wrapper around is_blacklisted() for hash-only callers.
        """
        return self.is_blacklisted(provider_name=provider_name, file_hash=file_hash)
```

- [ ] **Step 5: Run all repository tests**

Run: `cd backend && python -m pytest tests/test_blacklist_file_hash.py -v`
Expected: all 5 tests PASS.

- [ ] **Step 6: Run the existing blacklist tests for regression**

Run: `cd backend && python -m pytest tests/test_routes_blacklist.py -v --tb=short`
Expected: all PASS (backward compatibility maintained — the new kwarg is optional).

- [ ] **Step 7: Commit**

```bash
git add backend/db/repositories/blacklist.py backend/tests/test_blacklist_file_hash.py
git commit -m "feat(plan-b3): repository — file_hash dimension + is_blacklisted_by_hash"
```

---

## Task 4: Update `db/blacklist.py` delegating wrapper

**Files:**
- Modify: `backend/db/blacklist.py`

- [ ] **Step 1: Write failing test for wrapper**

Append to `backend/tests/test_blacklist_file_hash.py`:

```python
def test_db_blacklist_wrapper_forwards_file_hash():
    """The db.blacklist wrapper module exposes hash-aware functions."""
    import db.blacklist as bl

    # The wrapper must expose the new function
    assert hasattr(bl, "is_blacklisted_by_hash"), (
        "Expected db.blacklist.is_blacklisted_by_hash to be exposed"
    )
    # And the existing add function should accept file_hash kwarg
    import inspect

    sig = inspect.signature(bl.add_blacklist_entry)
    assert "file_hash" in sig.parameters
```

- [ ] **Step 2: Run test to verify failure**

Run: `cd backend && python -m pytest tests/test_blacklist_file_hash.py::test_db_blacklist_wrapper_forwards_file_hash -v`
Expected: FAIL — wrapper doesn't yet expose the new function or signature.

- [ ] **Step 3: Update `backend/db/blacklist.py`**

Edit the file — add `file_hash` to `add_blacklist_entry`'s signature and pass it through, and add `is_blacklisted_by_hash`:

```python
def add_blacklist_entry(
    provider_name: str,
    subtitle_id: str,
    language: str = "",
    file_path: str = "",
    title: str = "",
    reason: str = "",
    file_hash: str | None = None,
) -> int:
    """Add a subtitle to the blacklist. Returns the entry ID."""
    return _get_repo().add_blacklist_entry(
        provider_name,
        subtitle_id,
        language,
        file_path,
        title,
        reason,
        file_hash=file_hash,
    )


def is_blacklisted_by_hash(provider_name: str, file_hash: str) -> bool:
    """Check if a (provider, file_hash) pair is blacklisted."""
    return _get_repo().is_blacklisted_by_hash(provider_name, file_hash)
```

Also extend the existing `is_blacklisted` wrapper:

```python
def is_blacklisted(
    provider_name: str,
    subtitle_id: str | None = None,
    file_hash: str | None = None,
) -> bool:
    """Check if a subtitle is blacklisted (by subtitle_id or file_hash)."""
    return _get_repo().is_blacklisted(
        provider_name, subtitle_id=subtitle_id, file_hash=file_hash
    )
```

- [ ] **Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_blacklist_file_hash.py -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/db/blacklist.py
git commit -m "feat(plan-b3): db wrapper — forward file_hash through blacklist API"
```

---

## Task 5: Update API routes to accept + expose `file_hash`

**Files:**
- Modify: `backend/routes/blacklist/core.py`
- Modify: `backend/tests/test_blacklist_file_hash.py`

- [ ] **Step 1: Inspect existing route surface**

Run: `grep -nE "(bp\.route|add_blacklist|file_hash)" backend/routes/blacklist/core.py | head -30`
Note the endpoints that already exist (POST for add, GET for list, DELETE for remove).

- [ ] **Step 2: Write failing API test**

Append to `backend/tests/test_blacklist_file_hash.py`:

```python
def test_blacklist_post_accepts_file_hash(client):
    """POST /api/v1/blacklist accepts a file_hash field and returns it in the response."""
    # `client` is the existing Flask test client fixture from conftest.py
    resp = client.post(
        "/api/v1/blacklist",
        json={
            "provider_name": "opensubtitles",
            "subtitle_id": "api_test_1",
            "file_hash": "d" * 64,
            "reason": "api test",
        },
    )
    assert resp.status_code in (200, 201), f"expected 2xx, got {resp.status_code}: {resp.get_json()}"
    body = resp.get_json()
    assert body.get("file_hash") == "d" * 64 or body.get("id"), (
        "Response must include file_hash or at least the entry id"
    )


def test_blacklist_list_returns_file_hash(client):
    """GET /api/v1/blacklist returns file_hash in each entry."""
    # Seed one entry via the POST endpoint first (or via repository directly)
    client.post(
        "/api/v1/blacklist",
        json={
            "provider_name": "opensubtitles",
            "subtitle_id": "api_test_2",
            "file_hash": "e" * 64,
        },
    )
    resp = client.get("/api/v1/blacklist")
    assert resp.status_code == 200
    entries = resp.get_json().get("data", [])
    assert any(e.get("file_hash") == "e" * 64 for e in entries), (
        "Expected the seeded entry's file_hash to appear in the list"
    )
```

- [ ] **Step 3: Run tests to verify failure**

Run: `cd backend && python -m pytest tests/test_blacklist_file_hash.py -v -k "blacklist_post or blacklist_list"`
Expected: tests FAIL — route doesn't yet accept file_hash.

- [ ] **Step 4: Update `backend/routes/blacklist/core.py`**

For the POST handler: read `file_hash` from the request JSON (optional), pass through to `add_blacklist_entry`. Return `file_hash` in the response.

For the list handler: ensure `file_hash` is included in the per-entry dict when serializing. If the repository already returns a dict with all columns (`_to_dict`), this may already work — just verify.

Concrete edit (replace the add handler body; adjust for the actual function name in your file):

```python
# Inside the POST handler for /api/v1/blacklist
data = request.get_json(force=True) or {}
provider_name = data.get("provider_name", "").strip()
subtitle_id = data.get("subtitle_id", "").strip()
file_hash = data.get("file_hash") or None
# ...validation remains unchanged...

entry_id = add_blacklist_entry(
    provider_name=provider_name,
    subtitle_id=subtitle_id,
    language=data.get("language", ""),
    file_path=data.get("file_path", ""),
    title=data.get("title", ""),
    reason=data.get("reason", ""),
    file_hash=file_hash,
)
return jsonify({"id": entry_id, "file_hash": file_hash}), 201
```

Check that the existing list endpoint's per-entry serialization includes `file_hash`. If it uses `_to_dict(entry)`, that helper likely walks columns automatically. If it hand-serializes fields, add `file_hash` to the output dict.

- [ ] **Step 5: Run tests**

Run: `cd backend && python -m pytest tests/test_blacklist_file_hash.py tests/test_routes_blacklist.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/routes/blacklist/core.py backend/tests/test_blacklist_file_hash.py
git commit -m "feat(plan-b3): api — accept + return file_hash on blacklist endpoints"
```

---

## Task 6: Frontend UI — show `file_hash` column in Blacklist page

**Files:**
- Modify: `frontend/src/pages/Blacklist.tsx`
- Possibly modify: `frontend/src/api/blacklist.ts` (or the TypeScript type for a blacklist entry)

- [ ] **Step 1: Locate the TypeScript type definition**

Run: `grep -rn "BlacklistEntry\|interface Blacklist\|type Blacklist" frontend/src/ | head -10`
Identify the interface/type that represents a blacklist row in the frontend. Add `file_hash?: string | null` to it.

Example if the type lives inline in `Blacklist.tsx`:

```typescript
interface BlacklistEntry {
  id: number
  provider_name: string
  subtitle_id: string
  language: string
  file_path: string
  title: string
  reason: string
  added_at: string
  file_hash?: string | null  // NEW — Plan B3
}
```

If the type lives in a shared `api/blacklist.ts` or `types/` file, edit it there instead.

- [ ] **Step 2: Update `Blacklist.tsx` — add a column for the hash**

In the table rendering, add a cell for `file_hash`. Truncate-with-tooltip because 64 chars is long:

```tsx
{/* existing columns... */}
<th>Hash</th>

{/* in the body row */}
<td>
  {entry.file_hash ? (
    <code
      className="font-mono text-xs text-muted"
      title={entry.file_hash}
    >
      {entry.file_hash.slice(0, 10)}…
    </code>
  ) : (
    <span className="text-muted">—</span>
  )}
</td>
```

Match the existing column patterns in the file (the rest of the rendering is already Tailwind-based per the STYLING.md policy). If a dedicated table component is used (`DataTable`, `Table`, etc.), add the column via the existing column config.

- [ ] **Step 3: Build the frontend + verify no TS errors**

Run: `cd frontend && npm run lint && npx tsc --noEmit`
Expected: both exit 0. If TS complains about the new field, revisit the type definition.

- [ ] **Step 4: Run the frontend unit tests (if any touch Blacklist page)**

Run: `cd frontend && npm run test -- --run`
Expected: all PASS. No Blacklist-specific snapshots should break because the column is additive.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Blacklist.tsx frontend/src/api/blacklist.ts
git commit -m "feat(plan-b3): frontend — show file_hash column on Blacklist page"
```

(If you edited a different api file, replace the path. `git add -u` also works if you're confident the diff is right.)

---

## Task 7: Deploy

**Files:**
- Modify: `backend/VERSION` (in deploy skill)
- Modify: `CHANGELOG.md` (in deploy skill)

- [ ] **Step 1: Pre-deploy checks**

Run:

```bash
cd backend && ruff check .
cd backend && ruff format --check .
cd backend && python -m pytest tests/test_blacklist_file_hash.py tests/test_routes_blacklist.py -v --tb=short
cd frontend && npm run lint && npx tsc --noEmit && npm run test -- --run
```

All must exit 0.

- [ ] **Step 2: Invoke the `deploy` skill**

Bumps to 0.66.0-beta, drafts a CHANGELOG entry like:

```markdown
## [0.66.0-beta] - 2026-04-19

### Added
- **Plan B Phase 3 — Granular blacklist** — Extended the subtitle blacklist with a `file_hash` (SHA-256 or OpenSubtitles hash, VARCHAR(64)) dimension so retries can be suppressed for "any subtitle with hash H from provider Y", catching re-uploaded duplicates in addition to the existing per-subtitle-ID path. Alembic migration adds the column + a partial UNIQUE index `(provider_name, file_hash) WHERE file_hash IS NOT NULL`. Repository, API, and frontend all updated; the new dimension is optional and backward-compatible with existing blacklist entries.

### Changed — Plan B scope note
- **B3 Subzero merge deferred** — Cherry-picking 3-5 providers from the `subliminal_patch` fork (argenteam, assrt, subdivx, wizdom, etc.) turned out to require vendoring the full Subzero monkey-patch set or porting each provider to vanilla Subliminal's `Provider` base class. Given 29 providers already registered (Bazarr parity on core set), the Subzero cherry-pick is deferred — language-niche providers can be added in a post-Plan-B follow-up if operators request them.

### Plan B Progress
- Phase B3 — Granular blacklist: **shipped** (Subzero merge deferred)
```

- [ ] **Step 3: Verify in prod**

Check the DB migration ran:

```bash
ssh root@192.168.178.36 "docker exec sublarr-postgres psql -U sublarr -d sublarr -c '\d blacklist_entries'" | grep file_hash
```

Expected: one row listing `file_hash | character varying(64) |`.

Check the API surfaces the new field:

```bash
curl -s -H "X-API-Key: $SUBLARR_KEY" http://192.168.178.36:5765/api/v1/blacklist | python -c "import sys,json; d=json.load(sys.stdin); keys=list(d['data'][0].keys()) if d.get('data') else []; print('file_hash in keys:', 'file_hash' in keys)"
```

Expected: `file_hash in keys: True` (or empty data list with no error).

- [ ] **Step 4: Tail prod logs for 60s**

```bash
ssh root@192.168.178.36 "docker logs sublarr --tail 200" | grep -iE "(error|traceback|alembic)" | grep -v -E "(enzyme|X-Signature|marketplace registry)" | head -15
```

Expected: no new errors (accepted pre-existing warnings filtered out).

---

## Phase B3 Acceptance Checklist

- [ ] Alembic migration upgrades + downgrades cleanly locally
- [ ] `BlacklistEntry.file_hash` column present in ORM
- [ ] Repository `is_blacklisted_by_hash` + extended `is_blacklisted` + `add_blacklist_entry(file_hash=...)` all working
- [ ] Wrapper module `db/blacklist.py` exposes the new functions
- [ ] API POST accepts + list returns `file_hash`
- [ ] Frontend Blacklist page shows a `Hash` column with truncate + tooltip
- [ ] 7+ new tests pass (migration, repo, API)
- [ ] No regression in existing blacklist tests
- [ ] Ruff + TypeScript checks clean
- [ ] 0.66.0-beta built + deployed to Cardinal
- [ ] Prod DB shows `file_hash` column
- [ ] No new errors in prod logs

## Next Phase

**B4 — Scoring penalty port.** Audit Bazarr's `subliminal_patch/score.py` (~30 rules), port into `backend/wanted_search/scoring.py` as a named-class penalty pipeline, expose in ScoringTab with Bazarr-equivalent defaults.
