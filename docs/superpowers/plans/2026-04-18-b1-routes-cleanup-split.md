# B1 — Split `backend/routes/cleanup.py` (1105 → < 100 LOC) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce `backend/routes/cleanup.py` from 1105 LOC to under 100 LOC by converting it from a single file into a Flask-blueprint package (`routes/cleanup/`) with 5 domain-scoped route submodules. All 17 URL endpoints stay at their current paths under `/api/v1/cleanup`. Public import surface from `routes.cleanup` is byte-identical: `bp`, `_scan_state`, `_orphan_state`, `_scan_lock`, `_orphan_lock` all remain accessible at `routes.cleanup.<name>`.

**Architecture:**
Flask blueprint package pattern. `routes/cleanup/__init__.py` declares the blueprint, shared state, and common helpers; submodules import `bp` from `__init__.py` and register their route handlers via `@bp.route(...)` decorators. Submodule imports at the *end* of `__init__.py` trigger decorator execution at import time, registering all routes with the blueprint. The running blueprint is a single object — zero URL changes, zero client-visible impact.

**Tech Stack:** Flask, pytest. No new dependencies.

**Cross-cutting framework (per spec §5):**
- Rollback: `git revert` per task — no schema, no data, no CI configs touched.
- Feature flag: N/A — pure file organisation, no observable behaviour change.
- Observability metric: `len(open("backend/routes/cleanup/__init__.py").readlines()) < 100` pinned by a unit test added in Task 7.
- Migration notes: none.
- Docs-with-code: `CLAUDE.md` verified in Task 7.

**Critical compatibility constraints (from caller survey):**
1. `routes/__init__.py:15` — `from routes.cleanup import bp as cleanup_bp`. Must keep `bp` accessible at package scope.
2. `tests/test_routes_cleanup.py` — uses `import routes.cleanup as cleanup_mod` and directly reads/writes `cleanup_mod._scan_state`, `cleanup_mod._orphan_state` as module-level attributes. Must keep both dicts accessible at package scope.
3. No `patch("routes.cleanup.<function>")` calls exist — no mock-path migration needed.
4. `services/cleanup_scanner.py` has ZERO live imports from `routes.cleanup` (only a comment). No service-layer migration needed.

**Why this approach over alternatives:**
- **Nested sub-blueprints** (each submodule declares its own blueprint, parent registers them) would change the URL resolution path and break Flask's blueprint-name-based `url_for` calls. Rejected.
- **Flat file with region comments** preserves the status quo problem. Rejected.
- **Package pattern with shared-state in `__init__.py` + submodules importing `bp`** is the idiomatic Flask pattern. Accepted.

---

## File structure

| File | Status | Responsibility |
|---|---|---|
| `backend/routes/cleanup.py` | **deleted** | Replaced by the `routes/cleanup/` package (Task 2). |
| `backend/routes/cleanup/__init__.py` | **created** | Blueprint declaration + shared state (`_scan_state`, `_orphan_state`, `_scan_lock`, `_orphan_lock`) + logger + submodule imports. Target: ≤ 80 LOC. |
| `backend/routes/cleanup/dedup.py` | **created** | `/scan`, `/scan/status`, `/duplicates`, `/duplicates/delete` — 4 routes. Target: ~270 LOC. |
| `backend/routes/cleanup/orphan.py` | **created** | `/orphaned/scan`, `/orphaned`, `/orphaned/delete` — 3 routes. Target: ~200 LOC. |
| `backend/routes/cleanup/rules.py` | **created** | `/rules` GET+POST, `/rules/<id>` PUT+DELETE, `/rules/<id>/run`, `/rules/<id>/preview` — 6 routes. Target: ~300 LOC. |
| `backend/routes/cleanup/stats.py` | **created** | `/stats`, `/history` — 2 routes. Target: ~100 LOC. |
| `backend/routes/cleanup/preview.py` | **created** | `/preview`, `/non-target-subs` — 2 routes. Target: ~200 LOC. |
| `backend/tests/test_routes_cleanup_refactor_safety.py` | **created** | Characterization tests added in Task 1, extended with the LOC guard in Task 7. |

---

## Task 1: Add characterization tests pinning module-level public API

Existing test coverage: `backend/tests/test_routes_cleanup.py` (801 LOC) exhaustively covers all 17 endpoints via Flask test-client + direct access to `cleanup_mod._scan_state` / `_orphan_state`. That is the main regression harness for this refactor — every extraction task must keep it green.

What is NOT yet pinned and must be covered by the new file:
1. `from routes.cleanup import bp` works AND returns a `flask.Blueprint` instance.
2. `routes.cleanup._scan_state` is a dict with the 5 expected keys (`running`, `scan_id`, `progress`, `total`, `result`).
3. `routes.cleanup._orphan_state` is a dict with the 2 expected keys (`running`, `result`).
4. `routes.cleanup._scan_lock` and `_orphan_lock` are `threading.Lock` instances.
5. After package conversion, the blueprint has all 17 expected rules registered (URL-path assertion, not full handler test).

**Files:**
- Create: `backend/tests/test_routes_cleanup_refactor_safety.py`

- [ ] **Step 1: Write the test file**

```python
"""Characterization tests pinning the module-level public API of routes.cleanup.

These tests must continue to pass across every extraction step of plan
2026-04-18-b1-routes-cleanup-split.md. They characterise the package-level
surface that existing callers (routes/__init__.py and test_routes_cleanup.py)
depend on.
"""

import threading

import pytest
from flask import Blueprint


def test_bp_importable_from_routes_cleanup():
    from routes.cleanup import bp

    assert isinstance(bp, Blueprint)
    assert bp.name == "cleanup"
    assert bp.url_prefix == "/api/v1/cleanup"


def test_scan_state_accessible_at_package_scope():
    import routes.cleanup as cleanup_mod

    assert hasattr(cleanup_mod, "_scan_state")
    assert isinstance(cleanup_mod._scan_state, dict)
    for key in ("running", "scan_id", "progress", "total", "result"):
        assert key in cleanup_mod._scan_state, f"_scan_state missing key: {key}"


def test_orphan_state_accessible_at_package_scope():
    import routes.cleanup as cleanup_mod

    assert hasattr(cleanup_mod, "_orphan_state")
    assert isinstance(cleanup_mod._orphan_state, dict)
    for key in ("running", "result"):
        assert key in cleanup_mod._orphan_state, f"_orphan_state missing key: {key}"


def test_scan_lock_accessible_at_package_scope():
    import routes.cleanup as cleanup_mod

    assert hasattr(cleanup_mod, "_scan_lock")
    # threading.Lock() returns a _thread.lock — not isinstance-checkable against Lock directly
    assert hasattr(cleanup_mod._scan_lock, "acquire")
    assert hasattr(cleanup_mod._scan_lock, "release")


def test_orphan_lock_accessible_at_package_scope():
    import routes.cleanup as cleanup_mod

    assert hasattr(cleanup_mod, "_orphan_lock")
    assert hasattr(cleanup_mod._orphan_lock, "acquire")
    assert hasattr(cleanup_mod._orphan_lock, "release")


def test_all_17_routes_registered_on_blueprint():
    """Pin that every URL currently served by /api/v1/cleanup stays served after the split."""
    from routes.cleanup import bp

    expected_rules = {
        ("POST", "/api/v1/cleanup/scan"),
        ("GET", "/api/v1/cleanup/scan/status"),
        ("GET", "/api/v1/cleanup/duplicates"),
        ("POST", "/api/v1/cleanup/duplicates/delete"),
        ("POST", "/api/v1/cleanup/orphaned/scan"),
        ("GET", "/api/v1/cleanup/orphaned"),
        ("POST", "/api/v1/cleanup/orphaned/delete"),
        ("GET", "/api/v1/cleanup/rules"),
        ("POST", "/api/v1/cleanup/rules"),
        ("PUT", "/api/v1/cleanup/rules/<int:rule_id>"),
        ("DELETE", "/api/v1/cleanup/rules/<int:rule_id>"),
        ("POST", "/api/v1/cleanup/rules/<int:rule_id>/run"),
        ("POST", "/api/v1/cleanup/rules/<int:rule_id>/preview"),
        ("GET", "/api/v1/cleanup/stats"),
        ("GET", "/api/v1/cleanup/history"),
        ("POST", "/api/v1/cleanup/preview"),
        ("POST", "/api/v1/cleanup/non-target-subs"),
    }

    # Flask stores rules with a *deferred* prefix on the blueprint itself; to resolve
    # the final URL we need to apply the blueprint to a throwaway Flask app.
    from flask import Flask

    app = Flask(__name__)
    app.register_blueprint(bp)

    actual_rules = set()
    for rule in app.url_map.iter_rules():
        if rule.endpoint.startswith("cleanup."):
            # Each rule has a methods set — expand to one (method, path) pair per method
            for method in rule.methods - {"HEAD", "OPTIONS"}:
                actual_rules.add((method, rule.rule))

    missing = expected_rules - actual_rules
    extra = actual_rules - expected_rules
    assert not missing, f"Missing routes: {missing}"
    assert not extra, f"Unexpected routes: {extra}"


def test_scan_state_is_mutable():
    """Existing tests write to _scan_state directly. Confirm the attribute supports it."""
    import routes.cleanup as cleanup_mod

    original = cleanup_mod._scan_state["running"]
    try:
        cleanup_mod._scan_state["running"] = not original
        assert cleanup_mod._scan_state["running"] != original
    finally:
        cleanup_mod._scan_state["running"] = original
```

- [ ] **Step 2: Run the new test file alone**

`cd backend && python -m pytest tests/test_routes_cleanup_refactor_safety.py -v`
Expected: 7 tests PASS on the current unmodified code.

- [ ] **Step 3: Run the existing cleanup test suite to confirm baseline**

`cd backend && python -m pytest tests/test_routes_cleanup.py tests/test_routes_cleanup_refactor_safety.py -v`
Expected: both files green.

- [ ] **Step 4: Ruff**

`cd backend && ruff check tests/test_routes_cleanup_refactor_safety.py && ruff format --check tests/test_routes_cleanup_refactor_safety.py`

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_routes_cleanup_refactor_safety.py
git commit -m "test(cleanup): characterization tests pinning bp + state dicts + 17 routes (B1/cleanup prep)"
```

---

## Task 2: Convert `routes/cleanup.py` to package + extract dedup domain

This is the biggest, riskiest single step. It does two things atomically:
1. Converts `backend/routes/cleanup.py` (single file) into the `backend/routes/cleanup/` package.
2. Extracts the dedup routes (4 endpoints: `/scan`, `/scan/status`, `/duplicates`, `/duplicates/delete`) into `routes/cleanup/dedup.py`.

Doing the conversion + first extraction in a single commit avoids an intermediate "package with giant `__init__.py`" state that would be immediately undone.

**Files:**
- Delete: `backend/routes/cleanup.py`
- Create: `backend/routes/cleanup/__init__.py`
- Create: `backend/routes/cleanup/dedup.py`

- [ ] **Step 1: Read the current `backend/routes/cleanup.py`**

Identify:
- Lines 1-43: imports + blueprint + module-level state dicts + locks + logger + initial helper section
- Lines 43-307: dedup routes (`/scan`, `/scan/status`, `/duplicates`, `/duplicates/delete`) and any dedup-specific helpers

Everything from lines 308 onward stays in `__init__.py` during Task 2 — will be progressively extracted in Tasks 3-6.

- [ ] **Step 2: Create `backend/routes/cleanup/__init__.py`**

Content: lines 1-42 of the current file (blueprint + shared state + helpers) PLUS a submodule import block at the bottom:

```python
"""Cleanup API endpoints package.

Blueprint: /api/v1/cleanup

The package hosts the Blueprint object, shared scan state, and locks.
Route handlers live in domain-scoped submodules that import `bp` from
this package and register routes via @bp.route decorators.

Current submodules:
- dedup: dedup scan + duplicate management
- orphan: orphan subtitle scan + deletion  (from Task 3)
- rules: cleanup-rule CRUD + run + preview  (from Task 4)
- stats: cleanup stats + history  (from Task 5)
- preview: generic dry-run + non-target-subs  (from Task 6)
"""

import json
import logging
import threading
import uuid

from flask import Blueprint, jsonify, request

from error_utils import handle_api_error

bp = Blueprint("cleanup", __name__, url_prefix="/api/v1/cleanup")
logger = logging.getLogger(__name__)

# Module-level scan state (same pattern as wanted_scanner)
_scan_state = {
    "running": False,
    "scan_id": None,
    "progress": 0,
    "total": 0,
    "result": None,
}
_scan_lock = threading.Lock()

# Module-level orphan state
_orphan_state = {
    "running": False,
    "result": None,
}
_orphan_lock = threading.Lock()


# ---- Temporary: remaining routes before Tasks 3-6 extract them --------------
# (will be moved out progressively; everything below will land in a submodule)

# === PASTE LINES 308-1105 of the current routes/cleanup.py VERBATIM HERE ===

# ---- Submodule imports (trigger @bp.route decorator registration) ----------
from routes.cleanup import dedup  # noqa: E402, F401
```

**IMPORTANT for the implementer:**
- The `# === PASTE LINES 308-1105 VERBATIM HERE ===` placeholder must be replaced with the actual content from the current file. Open `backend/routes/cleanup.py`, copy lines 308 through the end of the file, paste in place of the placeholder.
- Some of the imports listed at the top of the current file might only be used by routes that remain in `__init__.py` temporarily. Keep them for now; they'll be moved to submodules in later tasks.
- The submodule import (`from routes.cleanup import dedup`) MUST be the LAST executable line in `__init__.py`. Putting it earlier causes `dedup.py` to try to import `bp` from an as-yet-uninitialised package.

- [ ] **Step 3: Create `backend/routes/cleanup/dedup.py`**

```python
"""Dedup scan + duplicate management routes."""

import json
import logging
import threading
import uuid

from flask import jsonify, request

from error_utils import handle_api_error
from routes.cleanup import _scan_lock, _scan_state, bp

logger = logging.getLogger(__name__)


# === PASTE LINES 43-307 of the current routes/cleanup.py VERBATIM HERE ===
# Contains the 4 dedup routes and any helpers that only those 4 routes call.
```

**IMPORTANT for the implementer:**
- The route handlers inside the pasted content reference `_scan_state`, `_scan_lock` as module-local names (because they were declared at the top of the original file). After the move, those names resolve to the imports at the top of `dedup.py` — no body change needed.
- If a handler references `handle_api_error` or any other name that was imported at the original file's top, that import is already present in the new `dedup.py` top-level imports.
- **Do NOT modify any handler body.** The move is byte-identical.

- [ ] **Step 4: Delete the old `backend/routes/cleanup.py`**

`git rm backend/routes/cleanup.py`

- [ ] **Step 5: Run the full cleanup test suite**

```bash
cd backend && python -m pytest tests/test_routes_cleanup.py tests/test_routes_cleanup_refactor_safety.py -v
```

Expected: all tests pass. The 7 safety tests pin the package structure; the 801-LOC existing test file validates every endpoint end-to-end.

If any test fails, the most likely causes in order of probability:
1. A handler references `_scan_state` but the new `dedup.py` didn't import it.
2. A helper function was in lines 43-307 (dedup region) but a handler OUTSIDE the dedup region calls it — breaks cross-module reference.
3. The `from routes.cleanup import dedup` at the end of `__init__.py` hits a circular import (shouldn't — `dedup.py` imports from the already-initialised `routes.cleanup` namespace).

- [ ] **Step 6: Run the full backend test suite**

`cd backend && python -m pytest --tb=short -q --ignore=tests/performance`
Expected: no new failures.

- [ ] **Step 7: Ruff**

`cd backend && ruff check . && ruff format --check .`

- [ ] **Step 8: Commit**

```bash
git add backend/routes/cleanup.py backend/routes/cleanup/__init__.py backend/routes/cleanup/dedup.py
git commit -m "refactor(cleanup): convert to package + extract dedup routes (B1/cleanup step 1/5)"
```

---

## Task 3: Extract orphan routes to `routes/cleanup/orphan.py`

Three routes: `/orphaned/scan` POST, `/orphaned` GET, `/orphaned/delete` POST.

**Files:**
- Create: `backend/routes/cleanup/orphan.py`
- Modify: `backend/routes/cleanup/__init__.py` (delete the 3 orphan routes; add submodule import)

- [ ] **Step 1: Create `backend/routes/cleanup/orphan.py`**

Same structure as `dedup.py`:

```python
"""Orphan subtitle scan + deletion routes."""

import json
import logging
import threading

from flask import jsonify, request

from error_utils import handle_api_error
from routes.cleanup import _orphan_lock, _orphan_state, bp

logger = logging.getLogger(__name__)


# === PASTE the 3 orphan routes VERBATIM from current routes/cleanup/__init__.py ===
# Find them by searching for @bp.route("/orphaned/...")
```

- [ ] **Step 2: Remove the 3 orphan routes from `__init__.py`**

Delete the 3 `@bp.route("/orphaned...")` handlers and any helpers exclusively used by them.

- [ ] **Step 3: Add submodule import at bottom of `__init__.py`**

```python
from routes.cleanup import dedup, orphan  # noqa: E402, F401
```

- [ ] **Step 4: Run tests**

`cd backend && python -m pytest tests/test_routes_cleanup.py tests/test_routes_cleanup_refactor_safety.py -v`
Expected: all green.

- [ ] **Step 5: Full suite + ruff**

- [ ] **Step 6: Commit**

```bash
git add backend/routes/cleanup/orphan.py backend/routes/cleanup/__init__.py
git commit -m "refactor(cleanup): extract orphan routes to orphan.py (B1/cleanup step 2/5)"
```

---

## Task 4: Extract rules routes to `routes/cleanup/rules.py`

Six routes: `/rules` GET+POST, `/rules/<int:rule_id>` PUT+DELETE, `/rules/<int:rule_id>/run` POST, `/rules/<int:rule_id>/preview` POST.

**Files:**
- Create: `backend/routes/cleanup/rules.py`
- Modify: `backend/routes/cleanup/__init__.py` (delete 6 routes + update submodule-import list)

- [ ] **Step 1: Create `backend/routes/cleanup/rules.py`** with the 6 routes + required helpers, following the `dedup.py` / `orphan.py` template.

- [ ] **Step 2: Remove the 6 `rules` routes from `__init__.py`**.

- [ ] **Step 3: Update `__init__.py` submodule import**: `from routes.cleanup import dedup, orphan, rules`.

- [ ] **Step 4: Run tests + full suite + ruff**.

- [ ] **Step 5: Commit**

```bash
git commit -m "refactor(cleanup): extract rules routes to rules.py (B1/cleanup step 3/5)"
```

---

## Task 5: Extract stats routes to `routes/cleanup/stats.py`

Two routes: `/stats` GET, `/history` GET.

**Files:**
- Create: `backend/routes/cleanup/stats.py`
- Modify: `__init__.py`

- [ ] Same pattern as Tasks 3-4.

- [ ] Commit:

```bash
git commit -m "refactor(cleanup): extract stats + history to stats.py (B1/cleanup step 4/5)"
```

---

## Task 6: Extract preview routes to `routes/cleanup/preview.py`

Two routes: `/preview` POST, `/non-target-subs` POST.

After this task, `__init__.py` should contain ONLY: module docstring + imports + bp declaration + shared state + submodule imports. Expected LOC: ~60-80.

**Files:**
- Create: `backend/routes/cleanup/preview.py`
- Modify: `__init__.py`

- [ ] Same pattern.

- [ ] Commit:

```bash
git commit -m "refactor(cleanup): extract preview routes to preview.py (B1/cleanup step 5/5)"
```

---

## Task 7: Pin LOC guard, verify CLAUDE.md, frontend smoke

Analogous to config.py/providers plan's final tasks.

**Files:**
- Modify: `backend/tests/test_routes_cleanup_refactor_safety.py` (append LOC guard)
- Verify (read-only): both `CLAUDE.md` files

- [ ] **Step 1: Append LOC-guard test**

```python
def test_routes_cleanup_init_py_under_100_loc():
    """Pin B1/cleanup achievement: routes/cleanup/__init__.py must stay below 100 LOC.

    If you are adding dedup routes, put them in routes/cleanup/dedup.py.
    If you are adding orphan routes, put them in routes/cleanup/orphan.py.
    If you are adding rule-management routes, put them in routes/cleanup/rules.py.
    If you are adding stats/history routes, put them in routes/cleanup/stats.py.
    If you are adding preview / non-target-subs routes, put them in routes/cleanup/preview.py.
    routes/cleanup/__init__.py is intentionally a thin package façade with only
    the blueprint declaration, shared state, and submodule imports.
    """
    from pathlib import Path

    path = Path(__file__).parent.parent / "routes" / "cleanup" / "__init__.py"
    assert path.exists(), f"routes/cleanup/__init__.py not found at {path}"
    line_count = sum(1 for _ in path.open(encoding="utf-8"))
    assert line_count < 100, (
        f"backend/routes/cleanup/__init__.py is {line_count} LOC, must stay below 100. "
        "Move new routes into the appropriate submodule (see docstring)."
    )
```

- [ ] **Step 2: CLAUDE.md audit**

Read both CLAUDE.md files. Look for references to `routes/cleanup.py` as a single file. The file is now a package — if CLAUDE.md says "the single cleanup route file" or similar, update. If it just says "cleanup routes" or doesn't describe internal structure, no edit.

- [ ] **Step 3: Frontend smoke**

`cd frontend && npm run test -- --run`
Expected: 824/824 pass (no UI change; cleanup routes power the Cleanup tab).

- [ ] **Step 4: Full backend + ruff**

`cd backend && python -m pytest --tb=short -q --ignore=tests/performance && ruff check . && ruff format --check .`

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_routes_cleanup_refactor_safety.py
# Conditionally add CLAUDE.md changes from Step 2 only if edits were made
git commit -m "test(cleanup): pin routes/cleanup/__init__.py <100 LOC + verify docs (B1/cleanup complete)"
```

---

## Acceptance criteria

After all 7 tasks:

- `backend/routes/cleanup/__init__.py` ≤ 100 LOC (target: ~70).
- The 5 domain submodules (`dedup.py`, `orphan.py`, `rules.py`, `stats.py`, `preview.py`) exist, each under 400 LOC.
- `backend/routes/cleanup.py` no longer exists.
- `from routes.cleanup import bp` still works; `routes.cleanup._scan_state`, `_orphan_state`, `_scan_lock`, `_orphan_lock` still accessible.
- All 17 URL endpoints under `/api/v1/cleanup` respond identically — verified by the unchanged `tests/test_routes_cleanup.py` (801 LOC of endpoint tests).
- `test_routes_cleanup_refactor_safety.py` has 8 tests (7 characterization + 1 LOC guard), all passing.
- Full backend suite + frontend suite green.
- Ruff clean.

---

## Out of scope

- `backend/routes/wanted/extract.py` (863 LOC), `backend/routes/standalone.py` (816 LOC), the frontend god-files — each gets its own plan in subsequent cycles.
- Consolidating dedup scan state into a proper service class (pre-existing state, not introduced here).
- Changing any URL path or the `bp.name = "cleanup"` endpoint prefix — both would break existing clients and tests.
