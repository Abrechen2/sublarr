# B1 — Split `backend/routes/standalone.py` (816 → < 80 LOC) Implementation Plan

**Goal:** Reduce `backend/routes/standalone.py` from 816 LOC to a Flask blueprint
package (`routes/standalone/`) with 4 domain submodules. All 16 URL endpoints
stay at their current paths under `/api/v1/standalone`. Public import surface
(`from routes.standalone import bp`) remains byte-identical.

**Architecture:** Flask blueprint package — `routes/standalone/__init__.py`
declares the blueprint + logger; submodules import `bp` + `logger` and register
their route handlers. Submodule imports at the end of `__init__.py` trigger
decorator execution at import time.

**Why simpler than B1C:** Unlike `cleanup.py`, `standalone.py` has zero module-
level shared state (no `_scan_state` dict, no `_lock`). Only `bp` + `logger` are
exposed. This makes the split purely mechanical — no caller-visible state migration.

**Caller survey:**
1. `routes/__init__.py:38` — `from routes.standalone import bp as standalone_bp`.
   Must keep `bp` accessible at package scope.
2. `services/standalone_manager.py` — only a docstring reference, no import.
3. Test suite — 47 tests in `test_routes_standalone.py` + `test_standalone_scan.py`
   (Flask test-client only, no `patch("routes.standalone.<x>")` calls).

**Rollback:** `git revert` per task — pure file organisation, no schema/data touched.

---

## File structure

| File | Status | Responsibility |
|---|---|---|
| `backend/routes/standalone.py` | **deleted** | Replaced by the package (Task 2). |
| `backend/routes/standalone/__init__.py` | **created** | `bp` + `logger` + submodule imports. Target: ≤ 50 LOC. |
| `backend/routes/standalone/folders.py` | **created** | `/folders` GET/POST/PUT/DELETE — 4 routes. ~240 LOC. |
| `backend/routes/standalone/series.py` | **created** | `/series` GET+detail+poster+DELETE, `/series/<id>/scan`, `/series/<id>/refresh-metadata` — 6 routes. ~215 LOC. |
| `backend/routes/standalone/movies.py` | **created** | `/movies` GET+detail+poster+DELETE — 4 routes. ~155 LOC. |
| `backend/routes/standalone/scan.py` | **created** | `/scan`, `/scan/<folder_id>`, `/status` — 3 routes. ~130 LOC. |
| `backend/tests/test_routes_standalone_refactor_safety.py` | **created** | Pin public surface + expected URL rules. |

---

## Tasks

- [ ] **Task 1:** Add `test_routes_standalone_refactor_safety.py` pinning
  `from routes.standalone import bp` works, `bp` is a `flask.Blueprint`, and all
  16 expected URL paths are registered.
- [ ] **Task 2:** Convert file → package (create `__init__.py` with bp + logger;
  delete `standalone.py`; extract **folders** routes to `folders.py`). Safety
  tests + existing 47 route tests must stay green.
- [ ] **Task 3:** Extract **series** routes (list/detail/poster/delete/scan/
  refresh-metadata) to `series.py`. Tests green.
- [ ] **Task 4:** Extract **movies** routes to `movies.py`. Tests green.
- [ ] **Task 5:** Extract **scan** routes (scan_all, scan_folder, status) to
  `scan.py`. Tests green.
- [ ] **Task 6:** Pin `__init__.py` < 50 LOC via the safety test. Verify
  `backend/` ruff-clean + full test suite.

---

## Verification per task

After each task:
1. `cd backend && python -m pytest tests/test_routes_standalone.py tests/test_standalone_scan.py tests/test_routes_standalone_refactor_safety.py --tb=short -q`
2. `cd backend && ruff check routes/standalone/ tests/test_routes_standalone_refactor_safety.py`

Final (after Task 6): full backend suite + ruff on all of `backend/`.
