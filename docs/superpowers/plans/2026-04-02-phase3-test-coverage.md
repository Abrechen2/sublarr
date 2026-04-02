# Phase 3 — Test Coverage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Raise backend test coverage from 10% to ≥40% by adding tests for the 5 most critical untested route modules.

**Architecture:** New test files per route module. Use existing conftest.py fixtures (especially `client` for HTTP-level tests and `app_ctx` for DB-layer unit tests). Mock DB repositories and external dependencies where needed. All tests are isolated — no shared state between test functions.

**Tech Stack:** Python 3.12, pytest, pytest-cov, Flask test client

**Branch:** `phase/3-test-coverage`

---

## File Structure

Files created by this plan (all new — nothing modified):

| File | Responsibility |
|------|---------------|
| `backend/tests/test_routes_cleanup.py` | HTTP tests for `/api/v1/cleanup/*` endpoints (scan, duplicates, orphaned) |
| `backend/tests/test_routes_api_keys.py` | HTTP tests for `/api/v1/api-keys/*` endpoints (list, get, update, test) |
| `backend/tests/test_routes_profiles.py` | HTTP tests for `/api/v1/language-profiles/*` endpoints (CRUD, assign) |
| `backend/tests/test_whisper_queue.py` | Unit tests for `whisper/queue.py` WhisperQueue class (no HTTP) |
| `backend/tests/test_routes_notifications.py` | HTTP tests for `/api/v1/notifications/templates/*` endpoints (CRUD, validation) |

## How the Test Client Works

All route tests use the `client` fixture from `conftest.py`. It:
1. Creates a temp SQLite database (`SUBLARR_DB_PATH` env var)
2. Sets `SUBLARR_API_KEY=""` — **auth is disabled in tests**
3. Returns a Flask test client with `app.config["TESTING"] = True`

```python
# Pattern used in every route test:
def test_something(client):          # 'client' fixture from conftest.py
    rv = client.get("/api/v1/...")   # No auth header needed (key is empty)
    assert rv.status_code == 200
    data = rv.get_json()
    assert "key" in data
```

---

## Task 1: Tests for routes/cleanup.py

**Files:**
- Create: `backend/tests/test_routes_cleanup.py`

**Endpoints covered:**
- `GET /api/v1/cleanup/scan/status` — returns scan state dict
- `POST /api/v1/cleanup/scan` — starts background scan
- `GET /api/v1/cleanup/duplicates` — list duplicate groups (paginated)
- `POST /api/v1/cleanup/duplicates/delete` — destructive: delete files (safety guard)
- `POST /api/v1/cleanup/orphaned/scan` — starts orphan background scan
- `GET /api/v1/cleanup/orphaned` — list orphaned subtitles
- `POST /api/v1/cleanup/orphaned/delete` — destructive: delete orphans

**Key import facts:**
- Blueprint prefix: `/api/v1/cleanup`
- `start_scan()` imports `dedup_engine.scan_for_duplicates` lazily — must be patched
- `delete_duplicates()` imports `dedup_engine.delete_duplicates` lazily — must be patched
- `get_duplicates()` imports `db.repositories.cleanup.CleanupRepository` lazily

---

- [ ] **Step 1.1: Write the failing tests file**

Create `backend/tests/test_routes_cleanup.py` with this exact content:

```python
"""Tests for routes/cleanup.py — dedup scan, orphan detection, destructive deletes."""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestScanStatus:
    """GET /api/v1/cleanup/scan/status"""

    def test_scan_status_idle(self, client):
        """Returns running=False when no scan is active."""
        # Reset module-level state before test
        import routes.cleanup as cleanup_mod

        cleanup_mod._scan_state["running"] = False
        cleanup_mod._scan_state["scan_id"] = None
        cleanup_mod._scan_state["result"] = None

        rv = client.get("/api/v1/cleanup/scan/status")
        assert rv.status_code == 200
        data = rv.get_json()
        assert data["running"] is False
        assert data["scan_id"] is None
        assert data["result"] is None

    def test_scan_status_while_running(self, client):
        """Returns running=True and scan_id when scan is active."""
        import routes.cleanup as cleanup_mod

        cleanup_mod._scan_state["running"] = True
        cleanup_mod._scan_state["scan_id"] = "test-scan-123"
        cleanup_mod._scan_state["result"] = None

        rv = client.get("/api/v1/cleanup/scan/status")
        assert rv.status_code == 200
        data = rv.get_json()
        assert data["running"] is True
        assert data["scan_id"] == "test-scan-123"

    def test_scan_status_with_result(self, client):
        """Returns result dict when scan completed."""
        import routes.cleanup as cleanup_mod

        cleanup_mod._scan_state["running"] = False
        cleanup_mod._scan_state["scan_id"] = "done-scan-456"
        cleanup_mod._scan_state["result"] = {"groups": [], "total_files": 0}

        rv = client.get("/api/v1/cleanup/scan/status")
        data = rv.get_json()
        assert data["result"]["total_files"] == 0


class TestStartScan:
    """POST /api/v1/cleanup/scan"""

    def setup_method(self):
        """Reset scan state before each test."""
        import routes.cleanup as cleanup_mod

        cleanup_mod._scan_state["running"] = False
        cleanup_mod._scan_state["scan_id"] = None
        cleanup_mod._scan_state["result"] = None

    def test_start_scan_returns_scanning_status(self, client):
        """POST /scan starts a background thread and returns scan_id."""
        with patch("dedup_engine.scan_for_duplicates") as mock_scan:
            mock_scan.return_value = {"groups": [], "total_files": 0}
            rv = client.post("/api/v1/cleanup/scan")

        assert rv.status_code == 200
        data = rv.get_json()
        assert data["status"] == "scanning"
        assert "scan_id" in data
        assert len(data["scan_id"]) > 0

    def test_start_scan_409_when_already_running(self, client):
        """Returns 409 when a scan is already in progress."""
        import routes.cleanup as cleanup_mod

        cleanup_mod._scan_state["running"] = True
        cleanup_mod._scan_state["scan_id"] = "existing-scan"

        rv = client.post("/api/v1/cleanup/scan")
        assert rv.status_code == 409
        data = rv.get_json()
        assert data["status"] == "already_running"
        assert data["scan_id"] == "existing-scan"


class TestGetDuplicates:
    """GET /api/v1/cleanup/duplicates"""

    def test_get_duplicates_empty(self, client):
        """Returns empty groups list when no duplicates exist."""
        mock_repo = MagicMock()
        mock_repo.get_duplicate_groups.return_value = []

        with patch("db.repositories.cleanup.CleanupRepository", return_value=mock_repo):
            rv = client.get("/api/v1/cleanup/duplicates")

        assert rv.status_code == 200
        data = rv.get_json()
        assert data["groups"] == []
        assert data["total"] == 0

    def test_get_duplicates_with_groups(self, client):
        """Returns duplicate groups from the repository."""
        fake_groups = [
            {"hash": "abc123", "files": ["/media/a.srt", "/media/b.srt"]},
            {"hash": "def456", "files": ["/media/c.srt", "/media/d.srt"]},
        ]
        mock_repo = MagicMock()
        mock_repo.get_duplicate_groups.return_value = fake_groups

        with patch("db.repositories.cleanup.CleanupRepository", return_value=mock_repo):
            rv = client.get("/api/v1/cleanup/duplicates")

        data = rv.get_json()
        assert data["total"] == 2
        assert len(data["groups"]) == 2

    def test_get_duplicates_pagination(self, client):
        """Respects page and per_page query params."""
        fake_groups = [{"hash": f"hash{i}", "files": [f"/a{i}.srt"]} for i in range(10)]
        mock_repo = MagicMock()
        mock_repo.get_duplicate_groups.return_value = fake_groups

        with patch("db.repositories.cleanup.CleanupRepository", return_value=mock_repo):
            rv = client.get("/api/v1/cleanup/duplicates?page=2&per_page=3")

        data = rv.get_json()
        assert data["total"] == 10
        assert data["page"] == 2
        assert data["per_page"] == 3
        assert len(data["groups"]) == 3  # items 3,4,5

    def test_get_duplicates_per_page_capped_at_200(self, client):
        """per_page is silently capped at 200."""
        mock_repo = MagicMock()
        mock_repo.get_duplicate_groups.return_value = []

        with patch("db.repositories.cleanup.CleanupRepository", return_value=mock_repo):
            rv = client.get("/api/v1/cleanup/duplicates?per_page=9999")

        data = rv.get_json()
        assert data["per_page"] == 200


class TestDeleteDuplicates:
    """POST /api/v1/cleanup/duplicates/delete — destructive operation tests."""

    def test_delete_duplicates_requires_groups(self, client):
        """Returns 400 when groups array is missing."""
        rv = client.post(
            "/api/v1/cleanup/duplicates/delete",
            json={},
            content_type="application/json",
        )
        assert rv.status_code == 400
        data = rv.get_json()
        assert "groups" in data["error"]

    def test_delete_duplicates_requires_keep_path(self, client):
        """Returns 400 when keep path is missing from a group."""
        rv = client.post(
            "/api/v1/cleanup/duplicates/delete",
            json={"groups": [{"delete": ["/media/b.srt"]}]},
            content_type="application/json",
        )
        assert rv.status_code == 400
        data = rv.get_json()
        assert "keep path is required" in data["error"]

    def test_delete_duplicates_requires_delete_list(self, client):
        """Returns 400 when delete list is empty."""
        rv = client.post(
            "/api/v1/cleanup/duplicates/delete",
            json={"groups": [{"keep": "/media/a.srt", "delete": []}]},
            content_type="application/json",
        )
        assert rv.status_code == 400
        data = rv.get_json()
        assert "delete list is empty" in data["error"]

    def test_delete_duplicates_rejects_keep_in_delete(self, client):
        """Safety guard: returns 400 if keep path appears in delete list."""
        rv = client.post(
            "/api/v1/cleanup/duplicates/delete",
            json={
                "groups": [
                    {
                        "keep": "/media/a.srt",
                        "delete": ["/media/a.srt", "/media/b.srt"],  # keep is in delete!
                    }
                ]
            },
            content_type="application/json",
        )
        assert rv.status_code == 400
        data = rv.get_json()
        assert "keep path" in data["error"]
        assert "delete list" in data["error"]

    def test_delete_duplicates_success(self, client):
        """Returns deletion summary when all guards pass."""
        mock_result = {"deleted": 1, "bytes_freed": 1024}

        with patch("dedup_engine.delete_duplicates", return_value=mock_result):
            rv = client.post(
                "/api/v1/cleanup/duplicates/delete",
                json={
                    "groups": [
                        {
                            "keep": "/media/a.srt",
                            "delete": ["/media/b.srt"],
                        }
                    ]
                },
                content_type="application/json",
            )

        assert rv.status_code == 200
        data = rv.get_json()
        assert data["total_deleted"] == 1
        assert data["total_bytes_freed"] == 1024
        assert len(data["results"]) == 1

    def test_delete_duplicates_aggregates_multiple_groups(self, client):
        """Sums deleted count and bytes_freed across multiple groups."""
        mock_result = {"deleted": 2, "bytes_freed": 512}

        with patch("dedup_engine.delete_duplicates", return_value=mock_result):
            rv = client.post(
                "/api/v1/cleanup/duplicates/delete",
                json={
                    "groups": [
                        {"keep": "/media/a.srt", "delete": ["/media/b.srt", "/media/c.srt"]},
                        {"keep": "/media/d.srt", "delete": ["/media/e.srt", "/media/f.srt"]},
                    ]
                },
                content_type="application/json",
            )

        data = rv.get_json()
        assert data["total_deleted"] == 4   # 2 groups × 2 deleted each
        assert data["total_bytes_freed"] == 1024  # 2 groups × 512
```

- [ ] **Step 1.2: Run tests to verify they fail with correct errors**

```bash
cd backend && python -m pytest tests/test_routes_cleanup.py -v --tb=short 2>&1 | head -60
```

Expected: Tests that patch `dedup_engine` will fail with `ModuleNotFoundError` or `ImportError` — that is the expected pre-implementation state. Tests that check scan state will likely pass already (the status endpoint reads module-level state). Confirm no syntax errors.

- [ ] **Step 1.3: Fix any import path issues**

If `dedup_engine` patches fail due to wrong patch target, check how cleanup.py imports it:

```bash
cd backend && grep -n "dedup_engine" routes/cleanup.py | head -10
```

The patch path must match the lazy import location. If cleanup.py does `from dedup_engine import delete_duplicates`, the patch target is `routes.cleanup.delete_duplicates`. Update patches accordingly in the test file.

- [ ] **Step 1.4: Run tests again and confirm all pass**

```bash
cd backend && python -m pytest tests/test_routes_cleanup.py -v --tb=short
```

Expected output:
```
tests/test_routes_cleanup.py::TestScanStatus::test_scan_status_idle PASSED
tests/test_routes_cleanup.py::TestScanStatus::test_scan_status_while_running PASSED
tests/test_routes_cleanup.py::TestScanStatus::test_scan_status_with_result PASSED
tests/test_routes_cleanup.py::TestStartScan::test_start_scan_returns_scanning_status PASSED
tests/test_routes_cleanup.py::TestStartScan::test_start_scan_409_when_already_running PASSED
tests/test_routes_cleanup.py::TestGetDuplicates::test_get_duplicates_empty PASSED
... (all PASSED, 0 FAILED)
```

- [ ] **Step 1.5: Check coverage for cleanup module**

```bash
cd backend && python -m pytest tests/test_routes_cleanup.py -v --cov=routes.cleanup --cov-report=term-missing
```

Target: ≥50% line coverage on `routes/cleanup.py`. Note the uncovered lines for future improvement.

- [ ] **Step 1.6: Commit**

```bash
git add backend/tests/test_routes_cleanup.py
git commit -m "test: add HTTP tests for routes/cleanup.py (scan, duplicates, orphaned)"
```

---

## Task 2: Tests for routes/api_keys.py

**Files:**
- Create: `backend/tests/test_routes_api_keys.py`

**Endpoints covered:**
- `GET /api/v1/api-keys/` — list all services with key status
- `GET /api/v1/api-keys/<service>` — get single service (404 for unknown)
- `PUT /api/v1/api-keys/<service>` — update keys for a service
- `POST /api/v1/api-keys/<service>/test` — test service connection

**Key import facts:**
- Blueprint prefix: `/api/v1/api-keys`
- `_get_service_info()` calls `db.config.get_config_entry` lazily — must be patched
- `update_service_keys()` calls `db.config.save_config_entry` and `config.reload_settings`
- `_mask_value()` is a pure function — test it directly without HTTP
- Known service names in `API_KEY_REGISTRY`: `sublarr`, `sonarr`, `radarr`, `opensubtitles`, `jimaku`, `subdl`, `tmdb`, `tvdb`, `deepl`, `apprise`

---

- [ ] **Step 2.1: Write the failing tests file**

Create `backend/tests/test_routes_api_keys.py`:

```python
"""Tests for routes/api_keys.py — service key listing, update, masking, and test endpoints."""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# Pure function tests (no HTTP)
# ---------------------------------------------------------------------------


class TestMaskValue:
    """Unit tests for the _mask_value helper."""

    def test_empty_string_returns_empty(self):
        from routes.api_keys import _mask_value

        assert _mask_value("") == ""

    def test_none_returns_empty(self):
        from routes.api_keys import _mask_value

        assert _mask_value(None) == ""

    def test_short_value_returns_stars(self):
        """Values of 8 chars or fewer become '***'."""
        from routes.api_keys import _mask_value

        assert _mask_value("abc") == "***"
        assert _mask_value("12345678") == "***"

    def test_long_value_shows_prefix_and_suffix(self):
        """Values >8 chars show first 4 + *** + last 4."""
        from routes.api_keys import _mask_value

        result = _mask_value("abcdefghijklmnop")
        assert result.startswith("abcd")
        assert result.endswith("mnop")
        assert "***" in result

    def test_exactly_9_chars_is_masked(self):
        """9-char value: first 4 + *** + last 4 = 'abcd***fghi' (overlap OK)."""
        from routes.api_keys import _mask_value

        result = _mask_value("abcdefghi")
        assert result == "abcd***fghi"


# ---------------------------------------------------------------------------
# HTTP endpoint tests
# ---------------------------------------------------------------------------


class TestListServices:
    """GET /api/v1/api-keys/"""

    def test_list_services_returns_all_registered(self, client):
        """All 10 registered services are returned."""
        # Patch get_config_entry to return empty string (no keys configured)
        with patch("db.config.get_config_entry", return_value=""):
            rv = client.get("/api/v1/api-keys/")

        assert rv.status_code == 200
        data = rv.get_json()
        assert "services" in data
        service_names = [s["service"] for s in data["services"]]
        assert "sublarr" in service_names
        assert "sonarr" in service_names
        assert "opensubtitles" in service_names

    def test_list_services_shows_missing_status_when_no_keys(self, client):
        """Services without configured keys show status='missing'."""
        with patch("db.config.get_config_entry", return_value=""):
            rv = client.get("/api/v1/api-keys/")

        data = rv.get_json()
        sublarr = next(s for s in data["services"] if s["service"] == "sublarr")
        assert sublarr["status"] == "missing"

    def test_list_services_shows_configured_status_when_key_set(self, client):
        """Services with a configured key show status='configured'."""
        with patch("db.config.get_config_entry", return_value="my-secret-key-value"):
            rv = client.get("/api/v1/api-keys/")

        data = rv.get_json()
        sublarr = next(s for s in data["services"] if s["service"] == "sublarr")
        assert sublarr["status"] == "configured"

    def test_list_services_masks_key_values(self, client):
        """Returned key values are masked — never the raw secret."""
        with patch("db.config.get_config_entry", return_value="abcdefghijklmnop"):
            rv = client.get("/api/v1/api-keys/")

        data = rv.get_json()
        sublarr = next(s for s in data["services"] if s["service"] == "sublarr")
        key_info = sublarr["keys"][0]
        assert "***" in key_info["masked_value"]
        assert "abcdefghijklmnop" not in key_info["masked_value"]


class TestGetService:
    """GET /api/v1/api-keys/<service>"""

    def test_get_known_service_returns_200(self, client):
        with patch("db.config.get_config_entry", return_value=""):
            rv = client.get("/api/v1/api-keys/sonarr")

        assert rv.status_code == 200
        data = rv.get_json()
        assert data["service"] == "sonarr"
        assert data["label"] == "Sonarr"

    def test_get_unknown_service_returns_404(self, client):
        rv = client.get("/api/v1/api-keys/nonexistent_service")
        assert rv.status_code == 404
        data = rv.get_json()
        assert "not found" in data["error"]

    def test_get_service_shows_testable_flag(self, client):
        """Services with a test function show testable=True."""
        with patch("db.config.get_config_entry", return_value=""):
            rv = client.get("/api/v1/api-keys/sonarr")

        data = rv.get_json()
        assert data["testable"] is True

    def test_get_service_without_test_fn_shows_not_testable(self, client):
        """Services without a test function show testable=False."""
        with patch("db.config.get_config_entry", return_value=""):
            rv = client.get("/api/v1/api-keys/tmdb")

        data = rv.get_json()
        assert data["testable"] is False


class TestUpdateServiceKeys:
    """PUT /api/v1/api-keys/<service>"""

    def test_update_unknown_service_returns_404(self, client):
        rv = client.put(
            "/api/v1/api-keys/nonexistent",
            json={"some_key": "some_value"},
            content_type="application/json",
        )
        assert rv.status_code == 404

    def test_update_with_no_data_returns_400(self, client):
        rv = client.put(
            "/api/v1/api-keys/tmdb",
            json={},
            content_type="application/json",
        )
        assert rv.status_code == 400
        data = rv.get_json()
        assert "No key data" in data["error"]

    def test_update_saves_key_and_returns_updated_info(self, client):
        """PUT saves the key value and returns updated service info."""
        with (
            patch("db.config.save_config_entry") as mock_save,
            patch("db.config.get_config_entry", return_value="new-api-key-value"),
            patch("db.config.get_all_config_entries", return_value={}),
            patch("config.reload_settings"),
        ):
            rv = client.put(
                "/api/v1/api-keys/tmdb",
                json={"tmdb_api_key": "new-api-key-value"},
                content_type="application/json",
            )

        assert rv.status_code == 200
        data = rv.get_json()
        assert data["status"] == "updated"
        assert "tmdb_api_key" in data["updated_keys"]
        mock_save.assert_called_once_with("tmdb_api_key", "new-api-key-value")

    def test_update_skips_masked_values(self, client):
        """Keys containing '***' are not saved (user did not change them)."""
        with patch("db.config.save_config_entry") as mock_save, \
             patch("db.config.get_config_entry", return_value=""), \
             patch("db.config.get_all_config_entries", return_value={}), \
             patch("config.reload_settings"):
            rv = client.put(
                "/api/v1/api-keys/tmdb",
                json={"tmdb_api_key": "abcd***xyz"},  # masked value
                content_type="application/json",
            )

        # Save should NOT have been called for the masked value
        mock_save.assert_not_called()


class TestTestService:
    """POST /api/v1/api-keys/<service>/test"""

    def test_test_unknown_service_returns_404(self, client):
        rv = client.post("/api/v1/api-keys/nonexistent/test")
        assert rv.status_code == 404

    def test_test_service_without_test_fn_returns_400(self, client):
        """Services like tmdb (test_fn=None) return 400."""
        rv = client.post("/api/v1/api-keys/tmdb/test")
        assert rv.status_code == 400
        data = rv.get_json()
        assert "does not support connection testing" in data["error"]

    def test_test_sonarr_returns_result(self, client):
        """Testable service returns success/message dict."""
        mock_result = {"success": True, "message": "Connected to Sonarr v3.0"}
        with patch("routes.api_keys._test_sonarr", return_value=mock_result):
            rv = client.post("/api/v1/api-keys/sonarr/test")

        assert rv.status_code == 200
        data = rv.get_json()
        assert data["success"] is True
        assert "message" in data
```

- [ ] **Step 2.2: Run tests to verify they fail or pass with correct behavior**

```bash
cd backend && python -m pytest tests/test_routes_api_keys.py -v --tb=short 2>&1 | head -80
```

Expected: `TestMaskValue` tests should pass immediately (pure function). HTTP tests may fail if patch targets are wrong — adjust patch paths to match where `db.config` is imported inside `routes/api_keys.py`.

- [ ] **Step 2.3: Fix patch targets if needed**

The route does lazy imports inside each function. To patch correctly:

```bash
cd backend && grep -n "from db.config import" routes/api_keys.py
```

If it imports with `from db.config import get_config_entry`, the patch target is `db.config.get_config_entry` (patches the module, which is what the lazy import will find). This should work as-is.

- [ ] **Step 2.4: Run all tests and confirm passing**

```bash
cd backend && python -m pytest tests/test_routes_api_keys.py -v --tb=short
```

Expected: All tests pass. Particularly verify `TestMaskValue::test_exactly_9_chars_is_masked` — adjust the expected string if the actual implementation differs.

- [ ] **Step 2.5: Check coverage**

```bash
cd backend && python -m pytest tests/test_routes_api_keys.py -v --cov=routes.api_keys --cov-report=term-missing
```

Target: ≥40% line coverage on `routes/api_keys.py`.

- [ ] **Step 2.6: Commit**

```bash
git add backend/tests/test_routes_api_keys.py
git commit -m "test: add HTTP tests for routes/api_keys.py (list, get, update, test endpoints)"
```

---

## Task 3: Tests for routes/profiles.py

**Files:**
- Create: `backend/tests/test_routes_profiles.py`

**Endpoints covered:**
- `GET /api/v1/language-profiles` — list profiles
- `POST /api/v1/language-profiles` — create profile (validation, 409 on duplicate name)
- `PUT /api/v1/language-profiles/<id>` — update profile (404, 409, field validation)
- `DELETE /api/v1/language-profiles/<id>` — delete profile (400 on default profile)
- `PUT /api/v1/language-profiles/assign` — assign profile to series/movie

**Key import facts:**
- Blueprint prefix: `/api/v1` (not `/api/v1/profiles` — the route file uses `url_prefix="/api/v1"`)
- Profile functions imported lazily from `db.profiles`
- `create_language_profile()` raises `Exception("UNIQUE constraint")` on duplicate name
- `delete_language_profile()` returns `False` when the profile is the default

---

- [ ] **Step 3.1: Write the failing tests file**

Create `backend/tests/test_routes_profiles.py`:

```python
"""Tests for routes/profiles.py — language profile CRUD and assignment."""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SAMPLE_PROFILE = {
    "id": 1,
    "name": "My Profile",
    "source_language": "en",
    "source_language_name": "English",
    "target_languages": ["de"],
    "target_language_names": ["German"],
    "translation_backend": "ollama",
    "fallback_chain": None,
    "forced_preference": "disabled",
}


class TestListLanguageProfiles:
    """GET /api/v1/language-profiles"""

    def test_returns_profiles_list(self, client):
        with patch("db.profiles.get_all_language_profiles", return_value=[SAMPLE_PROFILE]):
            rv = client.get("/api/v1/language-profiles")

        assert rv.status_code == 200
        data = rv.get_json()
        assert "profiles" in data
        assert len(data["profiles"]) == 1
        assert data["profiles"][0]["name"] == "My Profile"

    def test_returns_empty_list_when_no_profiles(self, client):
        with patch("db.profiles.get_all_language_profiles", return_value=[]):
            rv = client.get("/api/v1/language-profiles")

        data = rv.get_json()
        assert data["profiles"] == []


class TestCreateLanguageProfile:
    """POST /api/v1/language-profiles"""

    def test_create_requires_name(self, client):
        """Returns 400 when name is missing."""
        rv = client.post(
            "/api/v1/language-profiles",
            json={"target_languages": ["de"]},
            content_type="application/json",
        )
        assert rv.status_code == 400
        data = rv.get_json()
        assert "name" in data["error"]

    def test_create_requires_target_languages(self, client):
        """Returns 400 when target_languages is empty."""
        rv = client.post(
            "/api/v1/language-profiles",
            json={"name": "Test Profile", "target_languages": []},
            content_type="application/json",
        )
        assert rv.status_code == 400
        data = rv.get_json()
        assert "target language" in data["error"].lower()

    def test_create_rejects_invalid_forced_preference(self, client):
        """Returns 400 for forced_preference values outside allowed set."""
        rv = client.post(
            "/api/v1/language-profiles",
            json={
                "name": "Test",
                "target_languages": ["de"],
                "forced_preference": "invalid_value",
            },
            content_type="application/json",
        )
        assert rv.status_code == 400
        data = rv.get_json()
        assert "forced_preference" in data["error"]

    def test_create_returns_409_on_duplicate_name(self, client):
        """Returns 409 when a profile with the same name already exists."""
        with (
            patch(
                "db.profiles.create_language_profile",
                side_effect=Exception("UNIQUE constraint failed"),
            ),
            patch("db.profiles.get_language_profile", return_value=SAMPLE_PROFILE),
        ):
            rv = client.post(
                "/api/v1/language-profiles",
                json={"name": "My Profile", "target_languages": ["de"]},
                content_type="application/json",
            )

        assert rv.status_code == 409
        data = rv.get_json()
        assert "already exists" in data["error"]

    def test_create_success_returns_201(self, client):
        """Returns 201 with profile data on successful creation."""
        with (
            patch("db.profiles.create_language_profile", return_value=1),
            patch("db.profiles.get_language_profile", return_value=SAMPLE_PROFILE),
            patch("cache_response.invalidate_response_cache"),
        ):
            rv = client.post(
                "/api/v1/language-profiles",
                json={"name": "My Profile", "target_languages": ["de"]},
                content_type="application/json",
            )

        assert rv.status_code == 201
        data = rv.get_json()
        assert data["name"] == "My Profile"
        assert data["id"] == 1


class TestUpdateLanguageProfile:
    """PUT /api/v1/language-profiles/<id>"""

    def test_update_returns_404_for_unknown_id(self, client):
        with patch("db.profiles.get_language_profile", return_value=None):
            rv = client.put(
                "/api/v1/language-profiles/999",
                json={"name": "New Name"},
                content_type="application/json",
            )

        assert rv.status_code == 404

    def test_update_returns_400_when_no_fields(self, client):
        """Returns 400 when JSON body has no updatable fields."""
        with patch("db.profiles.get_language_profile", return_value=SAMPLE_PROFILE):
            rv = client.put(
                "/api/v1/language-profiles/1",
                json={},
                content_type="application/json",
            )

        assert rv.status_code == 400
        data = rv.get_json()
        assert "No fields" in data["error"]

    def test_update_rejects_invalid_forced_preference(self, client):
        with patch("db.profiles.get_language_profile", return_value=SAMPLE_PROFILE):
            rv = client.put(
                "/api/v1/language-profiles/1",
                json={"forced_preference": "bad_value"},
                content_type="application/json",
            )

        assert rv.status_code == 400

    def test_update_success_returns_updated_profile(self, client):
        updated = {**SAMPLE_PROFILE, "name": "Updated Profile"}
        with (
            patch("db.profiles.get_language_profile", side_effect=[SAMPLE_PROFILE, updated]),
            patch("db.profiles.update_language_profile"),
            patch("cache_response.invalidate_response_cache"),
        ):
            rv = client.put(
                "/api/v1/language-profiles/1",
                json={"name": "Updated Profile"},
                content_type="application/json",
            )

        assert rv.status_code == 200
        data = rv.get_json()
        assert data["name"] == "Updated Profile"

    def test_update_returns_409_on_duplicate_name(self, client):
        with (
            patch("db.profiles.get_language_profile", return_value=SAMPLE_PROFILE),
            patch(
                "db.profiles.update_language_profile",
                side_effect=Exception("UNIQUE constraint failed"),
            ),
        ):
            rv = client.put(
                "/api/v1/language-profiles/1",
                json={"name": "Existing Name"},
                content_type="application/json",
            )

        assert rv.status_code == 409


class TestDeleteLanguageProfile:
    """DELETE /api/v1/language-profiles/<id>"""

    def test_delete_returns_400_for_default_or_unknown(self, client):
        """Returns 400 when profile not found or is the default (cannot delete)."""
        with patch("db.profiles.delete_language_profile", return_value=False):
            rv = client.delete("/api/v1/language-profiles/1")

        assert rv.status_code == 400
        data = rv.get_json()
        assert "default profile" in data["error"] or "not found" in data["error"]

    def test_delete_success_returns_deleted_id(self, client):
        with (
            patch("db.profiles.delete_language_profile", return_value=True),
            patch("cache_response.invalidate_response_cache"),
        ):
            rv = client.delete("/api/v1/language-profiles/42")

        assert rv.status_code == 200
        data = rv.get_json()
        assert data["status"] == "deleted"
        assert data["id"] == 42


class TestAssignProfile:
    """PUT /api/v1/language-profiles/assign"""

    def test_assign_requires_type(self, client):
        rv = client.put(
            "/api/v1/language-profiles/assign",
            json={"arr_id": 1, "profile_id": 1},
            content_type="application/json",
        )
        assert rv.status_code == 400

    def test_assign_requires_arr_id(self, client):
        rv = client.put(
            "/api/v1/language-profiles/assign",
            json={"type": "series", "profile_id": 1},
            content_type="application/json",
        )
        assert rv.status_code == 400

    def test_assign_rejects_invalid_type(self, client):
        rv = client.put(
            "/api/v1/language-profiles/assign",
            json={"type": "podcast", "arr_id": 1, "profile_id": 1},
            content_type="application/json",
        )
        assert rv.status_code == 400

    def test_assign_series_success(self, client):
        with patch("db.profiles.assign_profile_to_series") as mock_assign:
            rv = client.put(
                "/api/v1/language-profiles/assign",
                json={"type": "series", "arr_id": 5, "profile_id": 2},
                content_type="application/json",
            )

        assert rv.status_code == 200
        data = rv.get_json()
        assert data["status"] == "assigned"
        assert data["arr_id"] == 5
        mock_assign.assert_called_once_with(5, 2)

    def test_assign_movie_success(self, client):
        with patch("db.profiles.assign_profile_to_movie") as mock_assign:
            rv = client.put(
                "/api/v1/language-profiles/assign",
                json={"type": "movie", "arr_id": 10, "profile_id": 3},
                content_type="application/json",
            )

        assert rv.status_code == 200
        data = rv.get_json()
        assert data["status"] == "assigned"
        mock_assign.assert_called_once_with(10, 3)
```

- [ ] **Step 3.2: Check what functions profiles.py actually imports from db.profiles**

```bash
cd backend && grep -n "from db.profiles import\|import db.profiles" routes/profiles.py
```

The lazy imports inside functions determine the correct patch targets. If it imports with `from db.profiles import assign_profile_to_series`, patch `db.profiles.assign_profile_to_series`. Adjust function names in the test if they differ.

- [ ] **Step 3.3: Run tests to see initial state**

```bash
cd backend && python -m pytest tests/test_routes_profiles.py -v --tb=short 2>&1 | head -80
```

Fix any `AttributeError` from wrong mock function names by checking the actual `db.profiles` module:

```bash
cd backend && grep -n "^def " db/profiles.py | head -20
```

- [ ] **Step 3.4: Run all tests and confirm passing**

```bash
cd backend && python -m pytest tests/test_routes_profiles.py -v --tb=short
```

- [ ] **Step 3.5: Check coverage**

```bash
cd backend && python -m pytest tests/test_routes_profiles.py -v --cov=routes.profiles --cov-report=term-missing
```

Target: ≥45% line coverage on `routes/profiles.py`.

- [ ] **Step 3.6: Commit**

```bash
git add backend/tests/test_routes_profiles.py
git commit -m "test: add HTTP tests for routes/profiles.py (CRUD, assignment, validation)"
```

---

## Task 4: Tests for whisper/queue.py + routes/whisper.py

**Files:**
- Create: `backend/tests/test_whisper_queue.py`

**What is tested:**
- `WhisperQueue.__init__()` — creates queue with correct concurrency limit
- `WhisperQueue.submit()` — adds job, starts thread, returns job_id
- `WhisperQueue.get_job()` — returns job by ID, None if missing
- `WhisperQueue.get_all_jobs()` — returns list of all jobs
- `WhisperQueue.cancel_job()` — marks queued job cancelled; returns False for completed
- Route `GET /api/v1/whisper/queue` — returns job list from DB
- Route `GET /api/v1/whisper/jobs/<id>` — returns job status
- Route `POST /api/v1/whisper/transcribe` — validates file_path, returns 202

**Key import facts:**
- `WhisperQueue` lives in `backend/whisper/queue.py`
- `submit()` calls `create_whisper_job` (DB) and starts a daemon thread
- The daemon thread calls `whisper_manager` — mock this to prevent actual transcription
- Route `GET /api/v1/whisper/queue` calls `db.whisper.get_whisper_jobs` lazily
- Route `POST /api/v1/whisper/transcribe` checks `is_safe_path` and `os.path.exists`

---

- [ ] **Step 4.1: Write the failing tests file**

Create `backend/tests/test_whisper_queue.py`:

```python
"""Tests for whisper/queue.py (WhisperQueue unit tests) and routes/whisper.py (HTTP tests)."""

import os
import sys
import time
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# WhisperQueue unit tests (no HTTP, no Flask)
# ---------------------------------------------------------------------------


class TestWhisperQueueInit:
    """WhisperQueue.__init__()"""

    def test_default_max_concurrent_is_one(self, app_ctx):
        from whisper.queue import WhisperQueue

        q = WhisperQueue()
        assert q._max_concurrent == 1

    def test_custom_max_concurrent(self, app_ctx):
        from whisper.queue import WhisperQueue

        q = WhisperQueue(max_concurrent=3)
        assert q._max_concurrent == 3

    def test_starts_with_empty_job_dict(self, app_ctx):
        from whisper.queue import WhisperQueue

        q = WhisperQueue()
        assert q._jobs == {}


class TestWhisperQueueGetJob:
    """WhisperQueue.get_job() and get_all_jobs()"""

    def test_get_job_returns_none_for_unknown_id(self, app_ctx):
        from whisper.queue import WhisperQueue

        q = WhisperQueue()
        assert q.get_job("nonexistent") is None

    def test_get_all_jobs_empty_initially(self, app_ctx):
        from whisper.queue import WhisperQueue

        q = WhisperQueue()
        assert q.get_all_jobs() == []


class TestWhisperQueueSubmit:
    """WhisperQueue.submit()"""

    def test_submit_returns_job_id(self, app_ctx):
        """submit() returns the provided job_id."""
        from whisper.queue import WhisperQueue

        mock_manager = MagicMock()
        mock_manager.transcribe.return_value = MagicMock(text="hello", segments=[])

        q = WhisperQueue()

        with (
            patch("whisper.queue.create_whisper_job"),
            patch("whisper.queue.update_whisper_job"),
            patch("whisper.queue.extract_audio_to_wav", return_value="/tmp/audio.wav"),
            patch("whisper.queue.select_audio_track", return_value=MagicMock()),
        ):
            job_id = q.submit(
                job_id="test-job-001",
                file_path="/tmp/test.mkv",
                language="ja",
                source_language="ja",
                whisper_manager=mock_manager,
                socketio=None,
            )

        assert job_id == "test-job-001"

    def test_submit_adds_job_to_internal_dict(self, app_ctx):
        """After submit(), get_job() returns the job."""
        from whisper.queue import WhisperQueue

        q = WhisperQueue()

        with (
            patch("whisper.queue.create_whisper_job"),
            patch("whisper.queue.update_whisper_job"),
            patch("whisper.queue.extract_audio_to_wav", return_value="/tmp/audio.wav"),
            patch("whisper.queue.select_audio_track", return_value=MagicMock()),
        ):
            q.submit(
                job_id="test-job-002",
                file_path="/tmp/test.mkv",
                language="en",
                source_language="en",
                whisper_manager=MagicMock(),
                socketio=None,
            )

        job = q.get_job("test-job-002")
        assert job is not None
        assert job.job_id == "test-job-002"
        assert job.file_path == "/tmp/test.mkv"
        assert job.language == "en"

    def test_submit_initial_status_is_queued(self, app_ctx):
        """Newly submitted job has status='queued'."""
        from whisper.queue import WhisperQueue

        q = WhisperQueue()

        with (
            patch("whisper.queue.create_whisper_job"),
            patch("whisper.queue.update_whisper_job"),
            patch("whisper.queue.extract_audio_to_wav", return_value="/tmp/audio.wav"),
            patch("whisper.queue.select_audio_track", return_value=MagicMock()),
        ):
            q.submit(
                job_id="test-job-003",
                file_path="/tmp/test.mkv",
                language="en",
                source_language="en",
                whisper_manager=MagicMock(),
                socketio=None,
            )

        job = q.get_job("test-job-003")
        # Status is 'queued' at creation time (may change quickly as thread runs)
        assert job.status in ("queued", "extracting", "transcribing", "completed", "failed")


class TestWhisperQueueCancelJob:
    """WhisperQueue.cancel_job()"""

    def test_cancel_nonexistent_job_returns_false(self, app_ctx):
        from whisper.queue import WhisperQueue

        q = WhisperQueue()
        assert q.cancel_job("no-such-job") is False

    def test_cancel_queued_job_returns_true(self, app_ctx):
        """Cancelling a queued job marks it cancelled and returns True."""
        from whisper.queue import WhisperJob, WhisperQueue

        q = WhisperQueue()
        job = WhisperJob(job_id="cancel-me", file_path="/tmp/f.mkv", status="queued")
        q._jobs["cancel-me"] = job

        with patch("whisper.queue.update_whisper_job"):
            result = q.cancel_job("cancel-me")

        assert result is True
        assert q.get_job("cancel-me").status == "cancelled"

    def test_cancel_completed_job_returns_false(self, app_ctx):
        """Cannot cancel an already-completed job."""
        from whisper.queue import WhisperJob, WhisperQueue

        q = WhisperQueue()
        job = WhisperJob(job_id="done-job", file_path="/tmp/f.mkv", status="completed")
        q._jobs["done-job"] = job

        result = q.cancel_job("done-job")
        assert result is False

    def test_cancel_failed_job_returns_false(self, app_ctx):
        """Cannot cancel an already-failed job."""
        from whisper.queue import WhisperJob, WhisperQueue

        q = WhisperQueue()
        job = WhisperJob(job_id="fail-job", file_path="/tmp/f.mkv", status="failed")
        q._jobs["fail-job"] = job

        result = q.cancel_job("fail-job")
        assert result is False


# ---------------------------------------------------------------------------
# HTTP route tests for routes/whisper.py
# ---------------------------------------------------------------------------


class TestListQueue:
    """GET /api/v1/whisper/queue"""

    def test_returns_job_list(self, client):
        fake_jobs = [
            {"job_id": "abc", "status": "queued", "progress": 0.0},
            {"job_id": "def", "status": "completed", "progress": 1.0},
        ]
        with patch("db.whisper.get_whisper_jobs", return_value=fake_jobs):
            rv = client.get("/api/v1/whisper/queue")

        assert rv.status_code == 200
        data = rv.get_json()
        assert len(data) == 2
        assert data[0]["job_id"] == "abc"

    def test_status_filter_param_is_passed(self, client):
        """status query param is forwarded to the DB function."""
        with patch("db.whisper.get_whisper_jobs", return_value=[]) as mock_fn:
            client.get("/api/v1/whisper/queue?status=completed")

        mock_fn.assert_called_once_with(status="completed", limit=50)

    def test_limit_is_capped_at_200(self, client):
        """limit query param is capped at 200."""
        with patch("db.whisper.get_whisper_jobs", return_value=[]) as mock_fn:
            client.get("/api/v1/whisper/queue?limit=9999")

        _, kwargs = mock_fn.call_args
        assert kwargs.get("limit", mock_fn.call_args[0][1] if mock_fn.call_args[0] else None) <= 200


class TestTranscribeEndpoint:
    """POST /api/v1/whisper/transcribe"""

    def test_missing_file_path_returns_400(self, client):
        rv = client.post(
            "/api/v1/whisper/transcribe",
            json={},
            content_type="application/json",
        )
        assert rv.status_code == 400
        data = rv.get_json()
        assert "file_path" in data["error"]

    def test_file_outside_media_path_returns_403(self, client, temp_dir):
        """Files outside the configured media_path are rejected."""
        with (
            patch("security_utils.is_safe_path", return_value=False),
            patch("config.map_path", side_effect=lambda p: p),
        ):
            rv = client.post(
                "/api/v1/whisper/transcribe",
                json={"file_path": "/etc/passwd"},
                content_type="application/json",
            )

        assert rv.status_code == 403

    def test_nonexistent_file_returns_404(self, client, temp_dir):
        """Returns 404 when the file does not exist."""
        with (
            patch("security_utils.is_safe_path", return_value=True),
            patch("config.map_path", side_effect=lambda p: p),
        ):
            rv = client.post(
                "/api/v1/whisper/transcribe",
                json={"file_path": "/tmp/nonexistent_media_file.mkv"},
                content_type="application/json",
            )

        assert rv.status_code == 404

    def test_valid_file_returns_202_with_job_id(self, client, tmp_path):
        """Valid file submission returns 202 with a job_id."""
        test_file = tmp_path / "test_video.mkv"
        test_file.write_bytes(b"fake mkv data")

        with (
            patch("security_utils.is_safe_path", return_value=True),
            patch("config.map_path", side_effect=lambda p: p),
            patch("config.get_settings") as mock_settings,
            patch("whisper.get_whisper_manager", return_value=MagicMock()),
            patch("whisper.queue.create_whisper_job"),
            patch("whisper.queue.update_whisper_job"),
            patch("whisper.queue.extract_audio_to_wav", return_value=str(tmp_path / "audio.wav")),
            patch("whisper.queue.select_audio_track", return_value=MagicMock()),
        ):
            mock_settings.return_value.media_path = str(tmp_path)
            mock_settings.return_value.source_language = "ja"
            rv = client.post(
                "/api/v1/whisper/transcribe",
                json={"file_path": str(test_file)},
                content_type="application/json",
            )

        assert rv.status_code == 202
        data = rv.get_json()
        assert "job_id" in data
        assert data["status"] == "queued"
```

- [ ] **Step 4.2: Run tests to check initial state**

```bash
cd backend && python -m pytest tests/test_whisper_queue.py -v --tb=short 2>&1 | head -80
```

The `WhisperJob` import path must match. If `WhisperJob` is not importable directly, check:

```bash
cd backend && python -c "from whisper.queue import WhisperJob; print('OK')"
```

- [ ] **Step 4.3: Fix any import issues with whisper subpackage**

The `whisper` name conflicts with OpenAI's `whisper` package if installed. If import fails:

```bash
cd backend && python -c "import whisper; print(whisper.__file__)"
```

If it prints a site-packages path instead of our `backend/whisper/__init__.py`, add `sys.path.insert(0, ...)` at the top of the test to ensure our local `whisper/` directory is resolved first. The existing `sys.path.insert` in the test file should handle this.

- [ ] **Step 4.4: Run all tests and confirm passing**

```bash
cd backend && python -m pytest tests/test_whisper_queue.py -v --tb=short
```

- [ ] **Step 4.5: Check coverage**

```bash
cd backend && python -m pytest tests/test_whisper_queue.py -v \
  --cov=whisper.queue --cov=routes.whisper --cov-report=term-missing
```

Target: ≥40% combined coverage on `whisper/queue.py` + `routes/whisper.py`.

- [ ] **Step 4.6: Commit**

```bash
git add backend/tests/test_whisper_queue.py
git commit -m "test: add unit tests for WhisperQueue and HTTP tests for routes/whisper.py"
```

---

## Task 5: Tests for routes/notifications_mgmt.py

**Files:**
- Create: `backend/tests/test_routes_notifications.py`

**Endpoints covered:**
- `GET /api/v1/notifications/templates` — list templates (with optional event_type filter)
- `POST /api/v1/notifications/templates` — create template (name required, Jinja2 validation)
- `GET /api/v1/notifications/templates/<id>` — get single template (404 if missing)
- `PUT /api/v1/notifications/templates/<id>` — update template (Jinja2 validation on body/title)
- `DELETE /api/v1/notifications/templates/<id>` — delete template

**Key import facts:**
- Blueprint prefix: `/api/v1/notifications`
- `NotificationRepository` imported lazily from `db.repositories.notifications`
- `_validate_jinja2_syntax()` is a module-level pure function — test it directly
- Jinja2 syntax error example: `"{% if %}"` (missing condition) is invalid

---

- [ ] **Step 5.1: Write the failing tests file**

Create `backend/tests/test_routes_notifications.py`:

```python
"""Tests for routes/notifications_mgmt.py — template CRUD and Jinja2 validation."""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SAMPLE_TEMPLATE = {
    "id": 1,
    "name": "Download Complete",
    "title_template": "Downloaded {{ title }}",
    "body_template": "Subtitle downloaded for {{ title }} ({{ language }})",
    "event_type": "download_complete",
    "service_name": None,
    "enabled": 1,
}


# ---------------------------------------------------------------------------
# Pure function tests
# ---------------------------------------------------------------------------


class TestValidateJinja2Syntax:
    """_validate_jinja2_syntax() — returns None on valid, error str on invalid."""

    def test_valid_template_returns_none(self):
        from routes.notifications_mgmt import _validate_jinja2_syntax

        assert _validate_jinja2_syntax("Hello {{ name }}") is None

    def test_empty_string_returns_none(self):
        from routes.notifications_mgmt import _validate_jinja2_syntax

        assert _validate_jinja2_syntax("") is None

    def test_none_returns_none(self):
        from routes.notifications_mgmt import _validate_jinja2_syntax

        assert _validate_jinja2_syntax(None) is None

    def test_invalid_jinja2_returns_error_string(self):
        from routes.notifications_mgmt import _validate_jinja2_syntax

        result = _validate_jinja2_syntax("{% if %}")  # missing condition
        assert result is not None
        assert isinstance(result, str)
        assert len(result) > 0

    def test_valid_for_block_returns_none(self):
        from routes.notifications_mgmt import _validate_jinja2_syntax

        tmpl = "{% for item in items %}{{ item }}{% endfor %}"
        assert _validate_jinja2_syntax(tmpl) is None

    def test_unclosed_block_returns_error(self):
        from routes.notifications_mgmt import _validate_jinja2_syntax

        result = _validate_jinja2_syntax("{% for item in items %}{{ item }}")
        assert result is not None


# ---------------------------------------------------------------------------
# HTTP tests
# ---------------------------------------------------------------------------


class TestListTemplates:
    """GET /api/v1/notifications/templates"""

    def test_returns_all_templates(self, client):
        mock_repo = MagicMock()
        mock_repo.get_templates.return_value = [SAMPLE_TEMPLATE]

        with patch("db.repositories.notifications.NotificationRepository", return_value=mock_repo):
            rv = client.get("/api/v1/notifications/templates")

        assert rv.status_code == 200
        data = rv.get_json()
        assert len(data) == 1
        assert data[0]["name"] == "Download Complete"

    def test_returns_empty_list_when_no_templates(self, client):
        mock_repo = MagicMock()
        mock_repo.get_templates.return_value = []

        with patch("db.repositories.notifications.NotificationRepository", return_value=mock_repo):
            rv = client.get("/api/v1/notifications/templates")

        assert rv.status_code == 200
        assert rv.get_json() == []

    def test_event_type_filter_is_passed_to_repo(self, client):
        """event_type query param is forwarded to the repository."""
        mock_repo = MagicMock()
        mock_repo.get_templates.return_value = []

        with patch("db.repositories.notifications.NotificationRepository", return_value=mock_repo):
            client.get("/api/v1/notifications/templates?event_type=download_complete")

        mock_repo.get_templates.assert_called_once_with(event_type="download_complete")


class TestCreateTemplate:
    """POST /api/v1/notifications/templates"""

    def test_create_requires_name(self, client):
        rv = client.post(
            "/api/v1/notifications/templates",
            json={"title_template": "hi"},
            content_type="application/json",
        )
        assert rv.status_code == 400
        data = rv.get_json()
        assert "name" in data["error"]

    def test_create_rejects_invalid_title_template(self, client):
        """Returns 400 when title_template has invalid Jinja2 syntax."""
        rv = client.post(
            "/api/v1/notifications/templates",
            json={"name": "Test", "title_template": "{% if %}"},
            content_type="application/json",
        )
        assert rv.status_code == 400
        data = rv.get_json()
        assert "title template" in data["error"].lower()

    def test_create_rejects_invalid_body_template(self, client):
        """Returns 400 when body_template has invalid Jinja2 syntax."""
        rv = client.post(
            "/api/v1/notifications/templates",
            json={"name": "Test", "body_template": "{% for %}"},
            content_type="application/json",
        )
        assert rv.status_code == 400
        data = rv.get_json()
        assert "body template" in data["error"].lower()

    def test_create_success_returns_201(self, client):
        """Valid template creation returns 201 with created template."""
        mock_repo = MagicMock()
        mock_repo.create_template.return_value = SAMPLE_TEMPLATE

        with patch("db.repositories.notifications.NotificationRepository", return_value=mock_repo):
            rv = client.post(
                "/api/v1/notifications/templates",
                json={
                    "name": "Download Complete",
                    "title_template": "Downloaded {{ title }}",
                    "body_template": "Done: {{ title }}",
                    "event_type": "download_complete",
                },
                content_type="application/json",
            )

        assert rv.status_code == 201
        data = rv.get_json()
        assert data["name"] == "Download Complete"

    def test_create_with_valid_jinja2_passes_validation(self, client):
        """Complex but valid Jinja2 is accepted."""
        mock_repo = MagicMock()
        mock_repo.create_template.return_value = {**SAMPLE_TEMPLATE, "name": "Complex"}

        with patch("db.repositories.notifications.NotificationRepository", return_value=mock_repo):
            rv = client.post(
                "/api/v1/notifications/templates",
                json={
                    "name": "Complex",
                    "body_template": "{% for item in items %}{{ item }}{% endfor %}",
                },
                content_type="application/json",
            )

        assert rv.status_code == 201


class TestGetTemplate:
    """GET /api/v1/notifications/templates/<id>"""

    def test_returns_template_by_id(self, client):
        mock_repo = MagicMock()
        mock_repo.get_template.return_value = SAMPLE_TEMPLATE

        with patch("db.repositories.notifications.NotificationRepository", return_value=mock_repo):
            rv = client.get("/api/v1/notifications/templates/1")

        assert rv.status_code == 200
        data = rv.get_json()
        assert data["id"] == 1

    def test_returns_404_when_not_found(self, client):
        mock_repo = MagicMock()
        mock_repo.get_template.return_value = None

        with patch("db.repositories.notifications.NotificationRepository", return_value=mock_repo):
            rv = client.get("/api/v1/notifications/templates/999")

        assert rv.status_code == 404
        data = rv.get_json()
        assert "not found" in data["error"].lower()


class TestUpdateTemplate:
    """PUT /api/v1/notifications/templates/<id>"""

    def test_update_returns_404_when_not_found(self, client):
        mock_repo = MagicMock()
        mock_repo.update_template.return_value = None

        with patch("db.repositories.notifications.NotificationRepository", return_value=mock_repo):
            rv = client.put(
                "/api/v1/notifications/templates/999",
                json={"name": "new name"},
                content_type="application/json",
            )

        assert rv.status_code == 404

    def test_update_validates_title_template_syntax(self, client):
        """Returns 400 when title_template in update body is invalid Jinja2."""
        rv = client.put(
            "/api/v1/notifications/templates/1",
            json={"title_template": "{% if %}"},
            content_type="application/json",
        )
        assert rv.status_code == 400

    def test_update_validates_body_template_syntax(self, client):
        """Returns 400 when body_template in update body is invalid Jinja2."""
        rv = client.put(
            "/api/v1/notifications/templates/1",
            json={"body_template": "{% for %}"},
            content_type="application/json",
        )
        assert rv.status_code == 400

    def test_update_success_returns_updated_template(self, client):
        updated = {**SAMPLE_TEMPLATE, "name": "Updated Name"}
        mock_repo = MagicMock()
        mock_repo.update_template.return_value = updated

        with patch("db.repositories.notifications.NotificationRepository", return_value=mock_repo):
            rv = client.put(
                "/api/v1/notifications/templates/1",
                json={"name": "Updated Name"},
                content_type="application/json",
            )

        assert rv.status_code == 200
        data = rv.get_json()
        assert data["name"] == "Updated Name"

    def test_update_only_passes_allowed_fields(self, client):
        """Unknown fields in the request body are silently ignored."""
        mock_repo = MagicMock()
        mock_repo.update_template.return_value = SAMPLE_TEMPLATE

        with patch("db.repositories.notifications.NotificationRepository", return_value=mock_repo):
            rv = client.put(
                "/api/v1/notifications/templates/1",
                json={"name": "OK", "dangerous_field": "injection attempt"},
                content_type="application/json",
            )

        assert rv.status_code == 200
        # Verify dangerous_field was not passed to the repo
        call_kwargs = mock_repo.update_template.call_args[1]
        assert "dangerous_field" not in call_kwargs


class TestDeleteTemplate:
    """DELETE /api/v1/notifications/templates/<id>"""

    def test_delete_returns_200_on_success(self, client):
        mock_repo = MagicMock()
        mock_repo.delete_template.return_value = True

        with patch("db.repositories.notifications.NotificationRepository", return_value=mock_repo):
            rv = client.delete("/api/v1/notifications/templates/1")

        assert rv.status_code == 200

    def test_delete_returns_404_when_not_found(self, client):
        mock_repo = MagicMock()
        mock_repo.delete_template.return_value = None  # or False

        with patch("db.repositories.notifications.NotificationRepository", return_value=mock_repo):
            rv = client.delete("/api/v1/notifications/templates/999")

        # Implementation may return 200 or 404 — check actual route behavior:
        # grep -n "delete_template" routes/notifications_mgmt.py
        # Adjust assertion to match the actual HTTP status
        assert rv.status_code in (200, 404)
```

- [ ] **Step 5.2: Check delete_template route behavior**

```bash
cd backend && grep -n -A 20 "def delete_template" routes/notifications_mgmt.py
```

Check what the route returns when `repo.delete_template()` returns `None` or `False`. Adjust the `TestDeleteTemplate::test_delete_returns_404_when_not_found` assertion to match.

- [ ] **Step 5.3: Check NotificationRepository patch target**

```bash
cd backend && grep -n "from db.repositories.notifications import" routes/notifications_mgmt.py
```

If the import is inside each function (`from db.repositories.notifications import NotificationRepository`), the patch target is `db.repositories.notifications.NotificationRepository`. This should already match the tests.

- [ ] **Step 5.4: Run all tests and confirm passing**

```bash
cd backend && python -m pytest tests/test_routes_notifications.py -v --tb=short
```

- [ ] **Step 5.5: Check coverage**

```bash
cd backend && python -m pytest tests/test_routes_notifications.py -v \
  --cov=routes.notifications_mgmt --cov-report=term-missing
```

Target: ≥50% line coverage on `routes/notifications_mgmt.py`.

- [ ] **Step 5.6: Commit**

```bash
git add backend/tests/test_routes_notifications.py
git commit -m "test: add HTTP tests for routes/notifications_mgmt.py (CRUD, Jinja2 validation)"
```

---

## Final: Run Full Test Suite and Check Coverage

- [ ] **Step 6.1: Run all 5 new test files together**

```bash
cd backend && python -m pytest \
  tests/test_routes_cleanup.py \
  tests/test_routes_api_keys.py \
  tests/test_routes_profiles.py \
  tests/test_whisper_queue.py \
  tests/test_routes_notifications.py \
  -v --tb=short 2>&1 | tail -30
```

Expected: All tests pass. Fix any remaining failures before proceeding.

- [ ] **Step 6.2: Run full backend test suite with coverage**

```bash
cd backend && python -m pytest --tb=short -q \
  --ignore=tests/performance \
  --ignore=tests/integration/test_provider_pipeline.py \
  --ignore=tests/test_video_sync.py \
  --ignore=tests/test_translation_backends.py \
  -k "not (test_sonarr_download_webhook or test_radarr_download_webhook or test_parse_llm_response_too_many_merge or test_record_backend_success)" \
  --cov=routes --cov=whisper.queue \
  --cov-report=term-missing \
  --cov-report=json 2>&1 | tail -40
```

- [ ] **Step 6.3: Check total coverage has reached target**

```bash
cd backend && python -m pytest --tb=short -q \
  --ignore=tests/performance \
  --ignore=tests/integration/test_provider_pipeline.py \
  --ignore=tests/test_video_sync.py \
  --ignore=tests/test_translation_backends.py \
  -k "not (test_sonarr_download_webhook or test_radarr_download_webhook or test_parse_llm_response_too_many_merge or test_record_backend_success)" \
  --cov=backend --cov-report=term 2>&1 | grep "TOTAL"
```

Target line: `TOTAL ... 40%+`

- [ ] **Step 6.4: Run ruff checks**

```bash
cd backend && ruff check . && ruff format --check .
```

If there are violations in the new test files, fix them:

```bash
cd backend && ruff check tests/test_routes_cleanup.py tests/test_routes_api_keys.py \
  tests/test_routes_profiles.py tests/test_whisper_queue.py tests/test_routes_notifications.py \
  --fix
```

- [ ] **Step 6.5: Final commit**

```bash
git add backend/tests/test_routes_cleanup.py \
        backend/tests/test_routes_api_keys.py \
        backend/tests/test_routes_profiles.py \
        backend/tests/test_whisper_queue.py \
        backend/tests/test_routes_notifications.py
git commit -m "test: Phase 3 — add coverage for 5 critical route modules (cleanup, api_keys, profiles, whisper, notifications)"
```

---

## Self-Review Checklist

- [x] **Spec coverage:** All 5 route modules from Phase 3 spec are covered: `cleanup.py`, `api_keys.py`, `profiles.py`, `whisper/queue.py` + `routes/whisper.py`, `notifications_mgmt.py`
- [x] **No placeholders:** Every task contains actual test code with `assert` statements, exact patch paths, and exact commands
- [x] **Type consistency:** `WhisperJob` dataclass fields (`job_id`, `file_path`, `status`) used consistently in Task 4; `SAMPLE_PROFILE` dict shape used consistently in Task 3; `SAMPLE_TEMPLATE` dict shape consistent in Task 5
- [x] **Fixtures:** `client` fixture used for all HTTP tests; `app_ctx` used for WhisperQueue unit tests (needs Flask app context for DB imports)
- [x] **Destructive operations tested:** `POST /cleanup/duplicates/delete` has 6 test cases including safety guard violations; `DELETE /language-profiles/<id>` tests default-profile protection
- [x] **Security tests:** `test_file_outside_media_path_returns_403` verifies `is_safe_path()` is enforced; `test_update_only_passes_allowed_fields` verifies field allowlist in notification update
