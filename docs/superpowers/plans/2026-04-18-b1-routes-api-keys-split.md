# B1A — Split `backend/routes/api_keys.py` (796 → < 80 LOC) Implementation Plan

**Goal:** Reduce `backend/routes/api_keys.py` from 796 LOC to a Flask
blueprint package with 4 domain submodules (helpers / testing / routes / io).
All 8 URL endpoints stay at their current paths under `/api/v1/api-keys`.

**Architecture:** Flask blueprint package — `routes/api_keys/__init__.py`
declares `bp` and re-exports the public names the test suite needs. Route
handlers live in `routes.py`; their helper `_invalidate_for_service` lives
beside them. Static data (`API_KEY_REGISTRY`, mask helper, service-info
builder) lives in `helpers.py`. Connectivity test functions
(`_test_sonarr`, `_test_radarr`, `_test_provider`, `_test_deepl`,
`_test_apprise`) + `_TEST_DISPATCH` move to `testing.py`. Export/Import
endpoints + ZIP/CSV/Bazarr helpers go to `io.py`.

**Caller survey:**
1. `routes/__init__.py:12` — `from routes.api_keys import bp as api_keys_bp`.
2. `tests/test_routes_api_keys.py:16` — `from routes.api_keys import _mask_value`.
3. Tests patch four internal symbols at `routes.api_keys.<name>`:
   - `routes.api_keys._invalidate_for_service` (4x)
   - `routes.api_keys._test_sonarr` (2x)
   - `routes.api_keys._TEST_DISPATCH` (3x via `patch.dict`)

**Rollback:** `git revert` — pure module reorganisation, no schema/data touched.

---

## File structure

| File | Status | Responsibility | Target LOC |
|---|---|---|---|
| `backend/routes/api_keys.py` | **deleted** | Replaced by the package. | — |
| `backend/routes/api_keys/__init__.py` | **created** | `bp` + public re-exports for `_mask_value`, `_TEST_DISPATCH`, `_test_*`, `_invalidate_for_service`. | ≤ 40 |
| `backend/routes/api_keys/helpers.py` | **created** | `API_KEY_REGISTRY`, `_mask_value`, `_get_service_info`. | ~140 |
| `backend/routes/api_keys/testing.py` | **created** | `_test_arr_client`, `_test_sonarr`, `_test_radarr`, `_test_provider`, `_test_deepl`, `_test_apprise`, `_TEST_DISPATCH`. | ~95 |
| `backend/routes/api_keys/routes.py` | **created** | `list_services`, `get_service`, `update_service_keys`, `_invalidate_for_service`, `test_service`. | ~240 |
| `backend/routes/api_keys/io.py` | **created** | `export_keys`, `import_keys`, `_import_zip`, `_import_csv`, `import_bazarr`. | ~330 |
| `backend/tests/test_routes_api_keys_refactor_safety.py` | **created** | Pin bp + 8 URL rules + public re-exports. | ~80 |

---

## Patch-path constraint

The `patch.dict("routes.api_keys._TEST_DISPATCH", …)` calls work unchanged
because the re-export in `__init__.py` binds the **same dict object** that
`testing.py` defines — `patch.dict` operates on the object via the import
path, and every reference sees the same mutation.

The `patch("routes.api_keys._test_sonarr", …)` calls work unchanged for the
same reason: the tests also update `_TEST_DISPATCH` with the mock, and the
dispatch table is what actually determines dispatch — the auxiliary name
patch is for symmetry.

The `patch("routes.api_keys._invalidate_for_service")` calls are the ONLY
ones that need test-path updates: that helper is called by name from
`update_service_keys` in the same module; once both move to
`routes.api_keys.routes`, the patch target must become
`routes.api_keys.routes._invalidate_for_service`. **4 strings to update in
tests/test_routes_api_keys.py (lines 170, 187, 201, 216).**

---

## Tasks

- [ ] **Task 1:** Add `test_routes_api_keys_refactor_safety.py` pinning
  `bp` is a Blueprint, name/url_prefix match, all 8 URL rules registered,
  `_mask_value`/`_TEST_DISPATCH`/`_invalidate_for_service` remain accessible
  at `routes.api_keys.<name>` (import surface).
- [ ] **Task 2:** Convert file → package. Create `helpers.py`, `testing.py`,
  `routes.py`, `io.py` + `__init__.py` with re-exports. Delete
  `routes/api_keys.py`.
- [ ] **Task 3:** Update 4 patch strings in `test_routes_api_keys.py` from
  `routes.api_keys._invalidate_for_service` to
  `routes.api_keys.routes._invalidate_for_service`. Run 25 existing tests
  + new safety tests → must be green.
- [ ] **Task 4:** Verify LOC pin (`__init__.py` < 80) + ruff clean on the
  new package.

---

## Verification

After Task 3/4:
1. `cd backend && python -m pytest tests/test_routes_api_keys.py tests/test_routes_api_keys_refactor_safety.py --tb=short -q`
2. `cd backend && ruff check routes/api_keys/ tests/test_routes_api_keys_refactor_safety.py`
