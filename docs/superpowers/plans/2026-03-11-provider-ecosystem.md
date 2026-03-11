# Provider Ecosystem Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the community plugin marketplace by adding GitHub topic discovery, SHA256 integrity, capability warnings, DB persistence, Official/Community badges, and integrating the marketplace into Settings → Providers.

**Architecture:** The backend plugin loader and hot-reload system are already complete. This plan builds the marketplace layer on top: GitHub API discovery cached in DB, SHA256 hash verification on zip install, capability declarations in manifests, and official registry for trust badges. Frontend moves from standalone Plugins page to a Marketplace tab inside Settings → Providers.

**Tech Stack:** Flask, SQLAlchemy (DB migrations), GitHub REST API v3, React 19 + TypeScript, TanStack Query

**Spec:** `docs/superpowers/specs/2026-03-11-provider-ecosystem-design.md`

---

## Existing Foundation (do NOT rewrite)

These are already implemented and working:
- `backend/providers/plugins/__init__.py` — PluginManager (discover/reload/unload)
- `backend/providers/plugins/loader.py` — importlib-based .py loading
- `backend/providers/plugins/manifest.py` — PluginManifest dataclass + validation
- `backend/providers/plugins/watcher.py` — watchdog hot-reload
- `backend/routes/plugins.py` — `GET /plugins`, `POST /plugins/reload`
- `backend/routes/marketplace.py` — marketplace routes skeleton
- `backend/services/marketplace.py` — PluginMarketplace service skeleton
- `frontend/src/pages/Plugins.tsx` — standalone Plugins page (will be replaced by tab)
- `frontend/src/api/client.ts` — marketplace API functions
- `frontend/src/hooks/useApi.ts` — marketplace hooks

---

## File Map

### New Files
- `backend/db/migrations/add_marketplace_tables.py` — DB tables: `marketplace_cache`, `installed_plugins`
- `backend/services/github_registry.py` — GitHub API topic search + DB cache
- `backend/tests/test_github_registry.py`
- `backend/tests/test_marketplace_service.py`
- `frontend/src/components/providers/MarketplaceTab.tsx` — new Marketplace tab
- `frontend/src/components/providers/CapabilityWarningModal.tsx`
- `frontend/src/test/MarketplaceTab.test.tsx`
- `official-registry.json` — curated provider list (repo root)

### Modified Files
- `backend/services/marketplace.py` — add GitHub search, SHA256 verify, capability support, DB persistence
- `backend/routes/marketplace.py` — add `GET /marketplace/refresh`, `GET /marketplace/installed`, `POST /marketplace/install` (extend with SHA256/capabilities)
- `backend/providers/plugins/manifest.py` — add `capabilities`, `sha256` fields to `PluginManifest`
- `backend/config.py` — add `github_token` setting
- `frontend/src/pages/Settings.tsx` (or Providers settings component) — add Marketplace tab
- `frontend/src/api/client.ts` — extend types + add refresh/installed endpoints
- `frontend/src/hooks/useApi.ts` — add hooks for new endpoints

---

## Chunk 1: DB Tables + Config

### Task 1: DB migration — `marketplace_cache` and `installed_plugins`

**Files:**
- Create: `backend/db/migrations/add_marketplace_tables.py`
- Modify: `backend/db/migrations/__init__.py` (register migration)

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_marketplace_db.py
def test_marketplace_tables_exist(test_db):
    conn = test_db
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cursor.fetchall()}
    assert "marketplace_cache" in tables
    assert "installed_plugins" in tables

def test_marketplace_cache_insert(test_db):
    test_db.execute("""
        INSERT INTO marketplace_cache
          (name, display_name, author, version, description,
           github_url, zip_url, sha256, capabilities,
           min_sublarr_version, is_official, last_fetched)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, ("test-plugin", "Test Plugin", "author", "1.0.0",
          "desc", "https://github.com/a/b", "https://github.com/a/b/releases/download/v1.0.0/plugin.zip",
          "abc123", '["network"]', "0.22.0", 0,
          "2026-03-11T00:00:00"))
    test_db.commit()
    row = test_db.execute(
        "SELECT name FROM marketplace_cache WHERE name=?", ("test-plugin",)
    ).fetchone()
    assert row is not None

def test_installed_plugins_insert(test_db):
    test_db.execute("""
        INSERT INTO installed_plugins
          (name, display_name, version, plugin_dir, sha256, capabilities, enabled, installed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, ("test-plugin", "Test Plugin", "1.0.0", "/config/plugins/test-plugin",
          "abc123", '["network"]', 1, "2026-03-11T00:00:00"))
    test_db.commit()
    row = test_db.execute(
        "SELECT name FROM installed_plugins WHERE name=?", ("test-plugin",)
    ).fetchone()
    assert row is not None
```

- [ ] **Step 2: Run test — expect FAIL** (`no such table: marketplace_cache`)

```bash
cd backend && python -m pytest tests/test_marketplace_db.py -v
```

- [ ] **Step 3: Write migration**

```python
# backend/db/migrations/add_marketplace_tables.py
"""Add marketplace_cache and installed_plugins tables."""

MIGRATION_ID = "add_marketplace_tables"


def up(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS marketplace_cache (
            name                TEXT PRIMARY KEY,
            display_name        TEXT NOT NULL,
            author              TEXT NOT NULL DEFAULT '',
            version             TEXT NOT NULL DEFAULT '0.0.0',
            description         TEXT NOT NULL DEFAULT '',
            github_url          TEXT NOT NULL DEFAULT '',
            zip_url             TEXT NOT NULL DEFAULT '',
            sha256              TEXT NOT NULL DEFAULT '',
            capabilities        TEXT NOT NULL DEFAULT '[]',
            min_sublarr_version TEXT NOT NULL DEFAULT '',
            is_official         INTEGER NOT NULL DEFAULT 0,
            last_fetched        TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS installed_plugins (
            name            TEXT PRIMARY KEY,
            display_name    TEXT NOT NULL DEFAULT '',
            version         TEXT NOT NULL DEFAULT '0.0.0',
            plugin_dir      TEXT NOT NULL DEFAULT '',
            sha256          TEXT NOT NULL DEFAULT '',
            capabilities    TEXT NOT NULL DEFAULT '[]',
            enabled         INTEGER NOT NULL DEFAULT 1,
            installed_at    TEXT NOT NULL
        );
    """)


def down(conn):
    conn.executescript("""
        DROP TABLE IF EXISTS marketplace_cache;
        DROP TABLE IF EXISTS installed_plugins;
    """)
```

- [ ] **Step 4: Register migration** (follow existing pattern in `backend/db/migrations/__init__.py`)

- [ ] **Step 5: Run test — expect PASS**

```bash
cd backend && python -m pytest tests/test_marketplace_db.py -v
```

- [ ] **Step 6: Commit**

```bash
git add backend/db/migrations/add_marketplace_tables.py backend/tests/test_marketplace_db.py
git commit -m "feat: add marketplace_cache and installed_plugins DB tables"
```

---

### Task 2: Add `github_token` setting to config

**Files:**
- Modify: `backend/config.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_config.py (add to existing)
def test_github_token_setting():
    from config import Settings
    s = Settings()
    # default is empty string -- no token required
    assert hasattr(s, "github_token")
    assert s.github_token == ""
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
cd backend && python -m pytest tests/test_config.py::test_github_token_setting -v
```

- [ ] **Step 3: Add setting to `config.py`**

Find the providers/plugins section in `config.py` and add:

```python
github_token: str = ""  # Optional GitHub API token for higher rate limits (5000/h vs 60/h)
```

With `SUBLARR_` prefix convention this becomes `SUBLARR_GITHUB_TOKEN`.

- [ ] **Step 4: Run test — expect PASS**

```bash
cd backend && python -m pytest tests/test_config.py::test_github_token_setting -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/config.py backend/tests/test_config.py
git commit -m "feat: add SUBLARR_GITHUB_TOKEN setting for GitHub API rate limits"
```

---

## Chunk 2: GitHub Registry Service

### Task 3: `github_registry.py` — GitHub topic search + DB cache

**Files:**
- Create: `backend/services/github_registry.py`
- Create: `backend/tests/test_github_registry.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_github_registry.py
from unittest.mock import patch, MagicMock
import json

def test_search_returns_plugins(mock_db):
    """GitHub API response is parsed and stored in DB cache."""
    from services.github_registry import GitHubRegistry

    mock_response = {
        "items": [
            {
                "name": "sublarr-opensubtitles",
                "full_name": "user/sublarr-opensubtitles",
                "html_url": "https://github.com/user/sublarr-opensubtitles",
                "description": "OpenSubtitles provider",
                "owner": {"login": "user"},
            }
        ]
    }

    manifest = {
        "name": "opensubtitles-enhanced",
        "display_name": "OpenSubtitles Enhanced",
        "version": "1.0.0",
        "author": "user",
        "description": "OpenSubtitles provider",
        "entry_point": "provider.py",
        "class_name": "OpenSubtitlesEnhancedProvider",
        "capabilities": ["network", "external_api"],
        "min_sublarr_version": "0.22.0",
        "sha256": "abc123",
    }

    with patch("requests.Session.get") as mock_get:
        # First call: GitHub search API
        resp1 = MagicMock()
        resp1.json.return_value = mock_response
        resp1.status_code = 200
        resp1.raise_for_status = MagicMock()

        # Second call: manifest.json from repo
        resp2 = MagicMock()
        resp2.json.return_value = manifest
        resp2.status_code = 200
        resp2.raise_for_status = MagicMock()

        mock_get.side_effect = [resp1, resp2]

        registry = GitHubRegistry(mock_db)
        plugins = registry.search(force_refresh=True)

    assert len(plugins) == 1
    assert plugins[0]["name"] == "opensubtitles-enhanced"
    assert plugins[0]["capabilities"] == ["network", "external_api"]


def test_cache_ttl_respected(mock_db):
    """Second call within TTL window uses DB cache, not GitHub API."""
    from services.github_registry import GitHubRegistry
    from datetime import UTC, datetime, timedelta

    # Pre-populate cache with recent entry
    mock_db.execute("""
        INSERT INTO marketplace_cache
          (name, display_name, author, version, description,
           github_url, zip_url, sha256, capabilities, min_sublarr_version,
           is_official, last_fetched)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, ("cached-plugin", "Cached Plugin", "user", "1.0.0", "desc",
          "https://github.com/user/cached", "https://github.com/user/cached/releases/download/v1.0.0/plugin.zip",
          "abc", '["network"]', "0.22.0", 0,
          datetime.now(UTC).isoformat()))
    mock_db.commit()

    with patch("requests.Session.get") as mock_get:
        registry = GitHubRegistry(mock_db)
        plugins = registry.search(force_refresh=False)
        # Should NOT have called GitHub API
        mock_get.assert_not_called()

    assert len(plugins) == 1
    assert plugins[0]["name"] == "cached-plugin"


def test_sha256_included_in_result(mock_db):
    """Plugin result includes sha256 from manifest."""
    from services.github_registry import GitHubRegistry

    mock_search_response = {"items": [
        {"name": "sublarr-test", "full_name": "user/sublarr-test",
         "html_url": "https://github.com/user/sublarr-test",
         "description": "Test", "owner": {"login": "user"}}
    ]}
    mock_manifest = {
        "name": "test-provider", "display_name": "Test Provider",
        "version": "1.0.0", "author": "user", "description": "Test",
        "entry_point": "provider.py", "class_name": "TestProvider",
        "capabilities": ["network"], "min_sublarr_version": "0.22.0",
        "sha256": "deadbeef123",
    }

    with patch("requests.Session.get") as mock_get:
        r1, r2 = MagicMock(), MagicMock()
        r1.json.return_value = mock_search_response
        r1.raise_for_status = MagicMock()
        r2.json.return_value = mock_manifest
        r2.raise_for_status = MagicMock()
        mock_get.side_effect = [r1, r2]

        registry = GitHubRegistry(mock_db)
        plugins = registry.search(force_refresh=True)

    assert plugins[0]["sha256"] == "deadbeef123"
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
cd backend && python -m pytest tests/test_github_registry.py -v
```

- [ ] **Step 3: Implement `github_registry.py`**

```python
# backend/services/github_registry.py
"""GitHub-based plugin registry with DB cache.

Searches GitHub for repos with topic 'sublarr-provider', fetches their
manifest.json, and caches results in the marketplace_cache DB table with
a 1h TTL. Respects SUBLARR_GITHUB_TOKEN for higher API rate limits.
"""

import json
import logging
from datetime import UTC, datetime, timedelta

import requests

logger = logging.getLogger(__name__)

GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"
CACHE_TTL_HOURS = 1


class GitHubRegistry:
    """Discovers community plugins via GitHub topic search."""

    def __init__(self, db_conn, github_token: str = ""):
        self.db = db_conn
        self.session = requests.Session()
        self.session.headers["Accept"] = "application/vnd.github+json"
        self.session.headers["X-GitHub-Api-Version"] = "2022-11-28"
        if github_token:
            self.session.headers["Authorization"] = f"Bearer {github_token}"

    def search(self, force_refresh: bool = False) -> list[dict]:
        """Return list of available plugins.

        Uses DB cache unless force_refresh=True or cache is stale (>1h).
        """
        if not force_refresh:
            cached = self._load_from_cache()
            if cached:
                return cached

        return self._fetch_from_github()

    def _load_from_cache(self) -> list[dict] | None:
        """Load from DB cache if fresh (within CACHE_TTL_HOURS)."""
        cutoff = (datetime.now(UTC) - timedelta(hours=CACHE_TTL_HOURS)).isoformat()
        rows = self.db.execute(
            "SELECT * FROM marketplace_cache WHERE last_fetched > ?", (cutoff,)
        ).fetchall()
        if not rows:
            return None
        return [self._row_to_dict(row) for row in rows]

    def _fetch_from_github(self) -> list[dict]:
        """Fetch from GitHub API and update DB cache."""
        try:
            resp = self.session.get(
                GITHUB_SEARCH_URL,
                params={"q": "topic:sublarr-provider", "per_page": 100},
                timeout=10,
            )
            resp.raise_for_status()
            repos = resp.json().get("items", [])
        except Exception as e:
            logger.warning("GitHub registry fetch failed: %s", e)
            # Fall back to stale cache
            rows = self.db.execute("SELECT * FROM marketplace_cache").fetchall()
            return [self._row_to_dict(row) for row in rows]

        plugins = []
        for repo in repos:
            manifest = self._fetch_manifest(repo)
            if manifest is None:
                continue
            plugin = self._store_plugin(repo, manifest)
            if plugin:
                plugins.append(plugin)

        return plugins

    def _fetch_manifest(self, repo: dict) -> dict | None:
        """Fetch manifest.json from repo default branch."""
        full_name = repo.get("full_name", "")
        url = f"https://raw.githubusercontent.com/{full_name}/main/manifest.json"
        try:
            resp = self.session.get(url, timeout=5)
            resp.raise_for_status()
            return resp.json()
        except Exception:
            # Try master branch fallback
            try:
                url = f"https://raw.githubusercontent.com/{full_name}/master/manifest.json"
                resp = self.session.get(url, timeout=5)
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                logger.debug("No manifest.json in %s: %s", full_name, e)
                return None

    def _store_plugin(self, repo: dict, manifest: dict) -> dict | None:
        """Validate manifest, write to DB cache, return plugin dict."""
        required = ["name", "display_name", "version", "entry_point", "class_name"]
        for field in required:
            if not manifest.get(field):
                logger.debug(
                    "Skipping %s: missing manifest field '%s'",
                    repo.get("full_name"), field
                )
                return None

        capabilities = manifest.get("capabilities", [])
        now = datetime.now(UTC).isoformat()

        try:
            self.db.execute("""
                INSERT INTO marketplace_cache
                  (name, display_name, author, version, description,
                   github_url, zip_url, sha256, capabilities,
                   min_sublarr_version, is_official, last_fetched)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                  display_name=excluded.display_name,
                  version=excluded.version,
                  description=excluded.description,
                  github_url=excluded.github_url,
                  zip_url=excluded.zip_url,
                  sha256=excluded.sha256,
                  capabilities=excluded.capabilities,
                  min_sublarr_version=excluded.min_sublarr_version,
                  last_fetched=excluded.last_fetched
            """, (
                manifest["name"],
                manifest["display_name"],
                manifest.get("author", repo["owner"]["login"]),
                manifest["version"],
                manifest.get("description", repo.get("description", "")),
                repo["html_url"],
                manifest.get("zip_url", ""),
                manifest.get("sha256", ""),
                json.dumps(capabilities),
                manifest.get("min_sublarr_version", ""),
                0,  # is_official set separately
                now,
            ))
            self.db.commit()
        except Exception as e:
            logger.error("Failed to cache plugin %s: %s", manifest["name"], e)
            return None

        return self._row_to_dict(self.db.execute(
            "SELECT * FROM marketplace_cache WHERE name=?", (manifest["name"],)
        ).fetchone())

    def _row_to_dict(self, row) -> dict:
        cols = [
            "name", "display_name", "author", "version", "description",
            "github_url", "zip_url", "sha256", "capabilities",
            "min_sublarr_version", "is_official", "last_fetched",
        ]
        d = dict(zip(cols, row))
        d["capabilities"] = json.loads(d.get("capabilities", "[]"))
        d["is_official"] = bool(d.get("is_official", 0))
        return d
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
cd backend && python -m pytest tests/test_github_registry.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/services/github_registry.py backend/tests/test_github_registry.py
git commit -m "feat: GitHub topic-based plugin registry with DB cache"
```

---

## Chunk 3: SHA256 + Capabilities + Official Registry

### Task 4: SHA256 integrity verification in marketplace service

**Files:**
- Modify: `backend/services/marketplace.py`
- Create: `backend/tests/test_marketplace_service.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_marketplace_service.py
import hashlib
import io
import zipfile
from unittest.mock import patch, MagicMock

def make_zip_bytes(content: bytes = b"print('hello')") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("provider.py", content)
    return buf.getvalue()

def test_sha256_check_passes_on_match(tmp_path):
    from services.marketplace import verify_zip_sha256
    data = make_zip_bytes()
    expected = hashlib.sha256(data).hexdigest()
    assert verify_zip_sha256(data, expected) is True

def test_sha256_check_fails_on_mismatch(tmp_path):
    from services.marketplace import verify_zip_sha256
    data = make_zip_bytes()
    assert verify_zip_sha256(data, "wrong_hash") is False

def test_install_rejects_tampered_zip(tmp_path, mock_db):
    from services.marketplace import PluginMarketplace
    data = make_zip_bytes()
    wrong_sha = "0" * 64

    with patch("requests.get") as mock_get:
        resp = MagicMock()
        resp.content = data
        resp.raise_for_status = MagicMock()
        mock_get.return_value = resp

        marketplace = PluginMarketplace(db=mock_db)
        with pytest.raises(RuntimeError, match="SHA256 mismatch"):
            marketplace.install_plugin_from_zip(
                plugin_name="test",
                zip_url="https://example.com/plugin.zip",
                expected_sha256=wrong_sha,
                plugins_dir=str(tmp_path),
            )
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
cd backend && python -m pytest tests/test_marketplace_service.py -v
```

- [ ] **Step 3: Add `verify_zip_sha256` + update install flow**

In `backend/services/marketplace.py`, add at the top:

```python
import hashlib

def verify_zip_sha256(data: bytes, expected_sha256: str) -> bool:
    """Return True if SHA256 of data matches expected_sha256."""
    if not expected_sha256:
        return True  # No hash provided — skip check (community plugins without hash)
    actual = hashlib.sha256(data).hexdigest()
    return actual.lower() == expected_sha256.lower()
```

Add `install_plugin_from_zip` method to `PluginMarketplace`:

```python
def install_plugin_from_zip(
    self,
    plugin_name: str,
    zip_url: str,
    expected_sha256: str,
    plugins_dir: str,
) -> dict:
    """Download zip, verify SHA256, extract to plugins_dir/<plugin_name>."""
    import io, zipfile, shutil
    from security_utils import safe_zip_extract

    resp = requests.get(zip_url, timeout=60)
    resp.raise_for_status()
    data = resp.content

    if not verify_zip_sha256(data, expected_sha256):
        raise RuntimeError(
            f"SHA256 mismatch for {plugin_name}: expected {expected_sha256[:12]}..."
        )

    plugin_path = os.path.join(plugins_dir, plugin_name)
    if os.path.exists(plugin_path):
        shutil.rmtree(plugin_path)
    os.makedirs(plugin_path, exist_ok=True)

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        safe_zip_extract(zf, plugin_path)

    return {"status": "installed", "path": plugin_path}
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
cd backend && python -m pytest tests/test_marketplace_service.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/services/marketplace.py backend/tests/test_marketplace_service.py
git commit -m "feat: SHA256 integrity check on plugin zip install"
```

---

### Task 5: `official-registry.json` + mark official plugins in cache

**Files:**
- Create: `official-registry.json` (repo root)
- Modify: `backend/services/github_registry.py`

- [ ] **Step 1: Create `official-registry.json`**

```json
{
  "_comment": "Curated list of official Sublarr provider plugins. Names must match manifest.json 'name' field.",
  "official_plugins": []
}
```

_(Empty for now — gets populated as community providers are curated)_

- [ ] **Step 2: Update `GitHubRegistry` to mark official plugins**

In `_store_plugin`, after the UPSERT, check official registry:

```python
def _load_official_names(self) -> set[str]:
    """Load official plugin names from official-registry.json."""
    import pathlib
    registry_path = pathlib.Path(__file__).parent.parent.parent / "official-registry.json"
    try:
        data = json.loads(registry_path.read_text())
        return set(data.get("official_plugins", []))
    except Exception:
        return set()
```

In `_fetch_from_github`, before the loop:
```python
official_names = self._load_official_names()
```

In `_store_plugin`, pass `is_official` based on name membership:
```python
is_official=1 if manifest["name"] in official_names else 0,
```

- [ ] **Step 3: Write test**

```python
# backend/tests/test_github_registry.py (add)
def test_official_badge_set_from_registry(mock_db, tmp_path, monkeypatch):
    """Plugin in official-registry.json gets is_official=True."""
    import json, pathlib
    official_reg = tmp_path / "official-registry.json"
    official_reg.write_text(json.dumps({"official_plugins": ["opensubtitles-enhanced"]}))

    monkeypatch.setattr(
        "services.github_registry.GitHubRegistry._load_official_names",
        lambda self: {"opensubtitles-enhanced"},
    )

    from services.github_registry import GitHubRegistry
    # ... mock GitHub API returning opensubtitles-enhanced manifest
    # verify plugins[0]["is_official"] is True
```

- [ ] **Step 4: Run test — expect PASS**

```bash
cd backend && python -m pytest tests/test_github_registry.py::test_official_badge_set_from_registry -v
```

- [ ] **Step 5: Commit**

```bash
git add official-registry.json backend/services/github_registry.py backend/tests/test_github_registry.py
git commit -m "feat: official-registry.json + Official badge marking in plugin cache"
```

---

## Chunk 4: Marketplace Routes

### Task 6: Update marketplace routes — refresh, installed, SHA256-aware install

**Files:**
- Modify: `backend/routes/marketplace.py`
- Modify: `backend/services/marketplace.py`

- [ ] **Step 1: Write failing tests for new routes**

```python
# backend/tests/test_marketplace_routes.py
def test_get_installed_returns_db_entries(client, mock_db):
    """GET /marketplace/installed reads from installed_plugins table."""
    mock_db.execute("""
        INSERT INTO installed_plugins
          (name, display_name, version, plugin_dir, sha256, capabilities, enabled, installed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, ("my-plugin", "My Plugin", "1.0.0", "/config/plugins/my-plugin",
          "abc", '["network"]', 1, "2026-03-11T00:00:00"))
    mock_db.commit()

    resp = client.get("/api/v1/marketplace/installed")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["installed"]) == 1
    assert data["installed"][0]["name"] == "my-plugin"

def test_refresh_triggers_github_fetch(client):
    """POST /marketplace/refresh calls GitHubRegistry.search(force_refresh=True)."""
    with patch("routes.marketplace.GitHubRegistry") as MockRegistry:
        instance = MockRegistry.return_value
        instance.search.return_value = []
        resp = client.post("/api/v1/marketplace/refresh")
        assert resp.status_code == 200
        instance.search.assert_called_once_with(force_refresh=True)

def test_install_verifies_sha256(client, mock_db, tmp_path):
    """POST /marketplace/install calls install_plugin_from_zip with sha256."""
    with patch("routes.marketplace.PluginMarketplace") as MockMP:
        instance = MockMP.return_value
        instance.install_plugin_from_zip.return_value = {"status": "installed"}
        resp = client.post("/api/v1/marketplace/install", json={
            "name": "test-plugin",
            "zip_url": "https://example.com/plugin.zip",
            "sha256": "abc123",
        })
        assert resp.status_code == 200
        instance.install_plugin_from_zip.assert_called_once()
        call_kwargs = instance.install_plugin_from_zip.call_args
        assert call_kwargs.kwargs.get("expected_sha256") == "abc123" or \
               "abc123" in call_kwargs.args
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
cd backend && python -m pytest tests/test_marketplace_routes.py -v
```

- [ ] **Step 3: Update `routes/marketplace.py`**

Add three new route handlers to the existing blueprint:

```python
# Add to routes/marketplace.py

@bp.route("/marketplace/installed", methods=["GET"])
def get_installed_plugins():
    """List installed plugins from DB."""
    from database import get_db, _db_lock
    import json
    with _db_lock:
        conn = get_db()
        rows = conn.execute("SELECT * FROM installed_plugins ORDER BY name").fetchall()
    cols = ["name", "display_name", "version", "plugin_dir", "sha256",
            "capabilities", "enabled", "installed_at"]
    installed = []
    for row in rows:
        d = dict(zip(cols, row))
        d["capabilities"] = json.loads(d.get("capabilities", "[]"))
        d["enabled"] = bool(d.get("enabled", 1))
        installed.append(d)
    return jsonify({"installed": installed})


@bp.route("/marketplace/refresh", methods=["POST"])
def refresh_marketplace():
    """Force-refresh plugin cache from GitHub."""
    from database import get_db, _db_lock
    from services.github_registry import GitHubRegistry
    settings = get_settings()
    with _db_lock:
        conn = get_db()
        registry = GitHubRegistry(conn, getattr(settings, "github_token", ""))
        plugins = registry.search(force_refresh=True)
    return jsonify({"plugins": plugins, "count": len(plugins)})


@bp.route("/marketplace/install", methods=["POST"])
def install_plugin():
    """Install plugin with SHA256 verification + DB persistence."""
    import json
    from datetime import UTC, datetime
    from database import get_db, _db_lock
    from providers import invalidate_manager
    from providers.plugins import get_plugin_manager
    from services.marketplace import PluginMarketplace

    data = request.get_json(silent=True) or {}
    name = data.get("name")
    zip_url = data.get("zip_url")
    sha256 = data.get("sha256", "")

    if not name or not zip_url:
        return jsonify({"error": "name and zip_url are required"}), 400

    try:
        settings = get_settings()
        plugins_dir = getattr(settings, "plugins_dir", "/config/plugins")
        marketplace = PluginMarketplace()
        result = marketplace.install_plugin_from_zip(
            plugin_name=name,
            zip_url=zip_url,
            expected_sha256=sha256,
            plugins_dir=plugins_dir,
        )

        # Persist to DB
        capabilities = json.dumps(data.get("capabilities", []))
        with _db_lock:
            conn = get_db()
            conn.execute("""
                INSERT INTO installed_plugins
                  (name, display_name, version, plugin_dir, sha256, capabilities, enabled, installed_at)
                VALUES (?, ?, ?, ?, ?, ?, 1, ?)
                ON CONFLICT(name) DO UPDATE SET
                  version=excluded.version, plugin_dir=excluded.plugin_dir,
                  sha256=excluded.sha256, capabilities=excluded.capabilities,
                  installed_at=excluded.installed_at
            """, (name, data.get("display_name", name),
                  data.get("version", "0.0.0"),
                  result["path"], sha256, capabilities,
                  datetime.now(UTC).isoformat()))
            conn.commit()

        # Hot-reload plugins
        manager = get_plugin_manager()
        if manager:
            manager.reload()
            invalidate_manager()

        return jsonify({"status": "installed", "name": name})
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500
    except Exception:
        logger.exception("Plugin install failed")
        return jsonify({"error": "Internal error"}), 500
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
cd backend && python -m pytest tests/test_marketplace_routes.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/routes/marketplace.py backend/tests/test_marketplace_routes.py
git commit -m "feat: marketplace routes — refresh, installed, SHA256-aware install"
```

---

## Chunk 5: Frontend

### Task 7: `MarketplaceTab.tsx` — browse, install, uninstall with badges and warning modal

**Files:**
- Create: `frontend/src/components/providers/MarketplaceTab.tsx`
- Create: `frontend/src/components/providers/CapabilityWarningModal.tsx`
- Modify: `frontend/src/api/client.ts` — add types + new endpoints
- Modify: `frontend/src/hooks/useApi.ts` — add hooks

- [ ] **Step 1: Add types and API functions to `client.ts`**

```typescript
// Add to frontend/src/api/client.ts

export interface MarketplacePlugin {
  name: string
  display_name: string
  author: string
  version: string
  description: string
  github_url: string
  zip_url: string
  sha256: string
  capabilities: string[]
  min_sublarr_version: string
  is_official: boolean
}

export interface InstalledPlugin {
  name: string
  display_name: string
  version: string
  capabilities: string[]
  enabled: boolean
  installed_at: string
}

export async function getMarketplaceBrowse(): Promise<{ plugins: MarketplacePlugin[] }> {
  const { data } = await api.get('/marketplace/plugins')
  return data
}

export async function refreshMarketplace(): Promise<{ plugins: MarketplacePlugin[]; count: number }> {
  const { data } = await api.post('/marketplace/refresh')
  return data
}

export async function getInstalledPlugins(): Promise<{ installed: InstalledPlugin[] }> {
  const { data } = await api.get('/marketplace/installed')
  return data
}

export async function installPlugin(plugin: MarketplacePlugin): Promise<{ status: string }> {
  const { data } = await api.post('/marketplace/install', {
    name: plugin.name,
    display_name: plugin.display_name,
    version: plugin.version,
    zip_url: plugin.zip_url,
    sha256: plugin.sha256,
    capabilities: plugin.capabilities,
  })
  return data
}

export async function uninstallPlugin(name: string): Promise<{ status: string }> {
  const { data } = await api.post('/marketplace/uninstall', { plugin_name: name })
  return data
}
```

- [ ] **Step 2: Add hooks to `useApi.ts`**

```typescript
// Add to frontend/src/hooks/useApi.ts

export function useMarketplaceBrowse() {
  return useQuery({
    queryKey: ['marketplace', 'browse'],
    queryFn: getMarketplaceBrowse,
    staleTime: 1000 * 60 * 60, // 1h — matches backend cache TTL
  })
}

export function useInstalledPlugins() {
  return useQuery({
    queryKey: ['marketplace', 'installed'],
    queryFn: getInstalledPlugins,
  })
}

export function useInstallPlugin() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: installPlugin,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['marketplace', 'installed'] })
    },
  })
}

export function useUninstallPlugin() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: uninstallPlugin,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['marketplace', 'installed'] })
    },
  })
}

export function useRefreshMarketplace() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: refreshMarketplace,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['marketplace', 'browse'] })
    },
  })
}
```

- [ ] **Step 3: Create `CapabilityWarningModal.tsx`**

```tsx
// frontend/src/components/providers/CapabilityWarningModal.tsx
import { AlertTriangle } from 'lucide-react'

const HIGH_RISK = new Set(['filesystem', 'subprocess'])

interface Props {
  plugin: { name: string; display_name: string; capabilities: string[] }
  onConfirm: () => void
  onCancel: () => void
}

export function CapabilityWarningModal({ plugin, onConfirm, onCancel }: Props) {
  const risky = plugin.capabilities.filter((c) => HIGH_RISK.has(c))

  return (
    <div
      className="fixed inset-0 bg-black/60 flex items-center justify-center z-50"
      onClick={onCancel}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="cap-warning-title"
        className="bg-gray-900 border border-yellow-600 rounded-lg p-6 max-w-md w-full mx-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-3 mb-4">
          <AlertTriangle className="w-6 h-6 text-yellow-400 shrink-0" />
          <h2 id="cap-warning-title" className="text-lg font-semibold">
            Community Plugin — Elevated Permissions
          </h2>
        </div>
        <p className="text-gray-300 text-sm mb-3">
          <strong>{plugin.display_name}</strong> declares the following capabilities:
        </p>
        <ul className="mb-4 space-y-1">
          {risky.map((cap) => (
            <li key={cap} className="text-yellow-400 text-sm font-mono bg-yellow-400/10 px-2 py-1 rounded">
              {cap}
            </li>
          ))}
        </ul>
        <p className="text-gray-400 text-sm mb-6">
          Community code runs inside the Sublarr process. Only install if you trust the source.
        </p>
        <div className="flex gap-3 justify-end">
          <button
            autoFocus
            onClick={onCancel}
            className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            className="px-4 py-2 bg-yellow-600 hover:bg-yellow-500 text-white rounded"
          >
            Install anyway
          </button>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Create `MarketplaceTab.tsx`**

```tsx
// frontend/src/components/providers/MarketplaceTab.tsx
import { useState, useCallback } from 'react'
import { Search, RefreshCw, Download, Trash2, ExternalLink, Loader2, Package, ShieldCheck } from 'lucide-react'
import { toast } from '@/components/shared/Toast'
import {
  useMarketplaceBrowse,
  useInstalledPlugins,
  useInstallPlugin,
  useUninstallPlugin,
  useRefreshMarketplace,
} from '@/hooks/useApi'
import { CapabilityWarningModal } from './CapabilityWarningModal'
import type { MarketplacePlugin } from '@/api/client'

const HIGH_RISK = new Set(['filesystem', 'subprocess'])

function hasRiskyCapabilities(capabilities: string[]): boolean {
  return capabilities.some((c) => HIGH_RISK.has(c))
}

export function MarketplaceTab() {
  const [search, setSearch] = useState('')
  const [onlyInstalled, setOnlyInstalled] = useState(false)
  const [pendingInstall, setPendingInstall] = useState<MarketplacePlugin | null>(null)

  const { data: browseData, isLoading: isBrowseLoading } = useMarketplaceBrowse()
  const { data: installedData } = useInstalledPlugins()
  const installMutation = useInstallPlugin()
  const uninstallMutation = useUninstallPlugin()
  const refreshMutation = useRefreshMarketplace()

  const installedNames = new Set(installedData?.installed.map((p) => p.name) ?? [])
  const installedVersions = Object.fromEntries(
    installedData?.installed.map((p) => [p.name, p.version]) ?? []
  )
  const allPlugins = browseData?.plugins ?? []

  const filtered = allPlugins.filter((p) => {
    const matchSearch =
      p.name.toLowerCase().includes(search.toLowerCase()) ||
      p.display_name.toLowerCase().includes(search.toLowerCase()) ||
      p.description.toLowerCase().includes(search.toLowerCase())
    const matchInstalled = !onlyInstalled || installedNames.has(p.name)
    return matchSearch && matchInstalled
  })

  const handleInstallRequest = useCallback((plugin: MarketplacePlugin) => {
    if (!plugin.is_official && hasRiskyCapabilities(plugin.capabilities)) {
      setPendingInstall(plugin)
    } else {
      doInstall(plugin)
    }
  }, [])

  const doInstall = useCallback(async (plugin: MarketplacePlugin) => {
    setPendingInstall(null)
    try {
      await installMutation.mutateAsync(plugin)
      toast(`"${plugin.display_name}" installed`, 'success')
    } catch {
      toast(`Failed to install "${plugin.display_name}"`, 'error')
    }
  }, [installMutation])

  const handleUninstall = useCallback(async (name: string, displayName: string) => {
    try {
      await uninstallMutation.mutateAsync(name)
      toast(`"${displayName}" removed`, 'success')
    } catch {
      toast(`Failed to remove "${displayName}"`, 'error')
    }
  }, [uninstallMutation])

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex gap-3 items-center">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            placeholder="Search plugins..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-10 pr-4 py-2 bg-gray-800 border border-gray-700 rounded text-white placeholder-gray-500"
          />
        </div>
        <label className="flex items-center gap-2 text-sm text-gray-400 cursor-pointer">
          <input
            type="checkbox"
            checked={onlyInstalled}
            onChange={(e) => setOnlyInstalled(e.target.checked)}
            className="rounded"
          />
          Installed only
        </label>
        <button
          onClick={() => refreshMutation.mutate()}
          disabled={refreshMutation.isPending}
          className="px-3 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded flex items-center gap-2 text-sm"
          title="Refresh from GitHub"
        >
          <RefreshCw className={`w-4 h-4 ${refreshMutation.isPending ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Plugin list */}
      {isBrowseLoading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-teal-500" />
        </div>
      ) : (
        <div className="space-y-2">
          {filtered.map((plugin) => {
            const installed = installedNames.has(plugin.name)
            const currentVersion = installedVersions[plugin.name]
            const hasUpdate = installed && currentVersion && currentVersion !== plugin.version
            const isInstalling = installMutation.isPending &&
              (installMutation.variables as MarketplacePlugin)?.name === plugin.name

            return (
              <div
                key={plugin.name}
                className="flex items-start gap-4 p-4 bg-gray-800 rounded-lg border border-gray-700"
              >
                <Package className="w-6 h-6 text-teal-500 shrink-0 mt-0.5" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-semibold text-white">{plugin.display_name}</span>
                    <span className="text-xs text-gray-400">v{plugin.version}</span>
                    {plugin.is_official && (
                      <span className="flex items-center gap-1 text-xs bg-green-600/20 text-green-400 px-2 py-0.5 rounded-full">
                        <ShieldCheck className="w-3 h-3" /> Official
                      </span>
                    )}
                    {!plugin.is_official && (
                      <span className="text-xs bg-gray-700 text-gray-400 px-2 py-0.5 rounded-full">
                        Community
                      </span>
                    )}
                    {hasUpdate && (
                      <span className="text-xs bg-yellow-600/20 text-yellow-400 px-2 py-0.5 rounded-full">
                        Update available → v{plugin.version}
                      </span>
                    )}
                  </div>
                  <p className="text-sm text-gray-400 mt-1">{plugin.description}</p>
                  <p className="text-xs text-gray-500 mt-1">by {plugin.author}</p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <a
                    href={plugin.github_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="p-2 text-gray-400 hover:text-white"
                    title="View on GitHub"
                  >
                    <ExternalLink className="w-4 h-4" />
                  </a>
                  {installed ? (
                    <button
                      onClick={() => handleUninstall(plugin.name, plugin.display_name)}
                      className="px-3 py-1.5 text-sm bg-red-500/20 hover:bg-red-500/30 text-red-400 rounded flex items-center gap-1"
                    >
                      <Trash2 className="w-4 h-4" />
                      Remove
                    </button>
                  ) : (
                    <button
                      onClick={() => handleInstallRequest(plugin)}
                      disabled={isInstalling}
                      className="px-3 py-1.5 text-sm bg-teal-600 hover:bg-teal-500 text-white rounded flex items-center gap-1 disabled:opacity-50"
                    >
                      {isInstalling ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <Download className="w-4 h-4" />
                      )}
                      Install
                    </button>
                  )}
                </div>
              </div>
            )
          })}
          {!isBrowseLoading && filtered.length === 0 && (
            <div className="text-center py-12 text-gray-400">
              <Package className="w-10 h-10 mx-auto mb-3 opacity-50" />
              <p>No plugins found.</p>
            </div>
          )}
        </div>
      )}

      {pendingInstall && (
        <CapabilityWarningModal
          plugin={pendingInstall}
          onConfirm={() => doInstall(pendingInstall)}
          onCancel={() => setPendingInstall(null)}
        />
      )}
    </div>
  )
}
```

- [ ] **Step 5: Integrate into Settings → Providers**

Find the Providers settings page (likely `frontend/src/pages/Settings.tsx` or a `ProvidersTab` component). Add `MarketplaceTab` as the third tab after Configured and Available:

```tsx
// In the providers tab panel, add:
{ label: 'Marketplace', component: <MarketplaceTab /> }
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/providers/ frontend/src/api/client.ts frontend/src/hooks/useApi.ts
git commit -m "feat: Marketplace tab in Providers settings — browse, install, Official/Community badges, capability warning modal"
```

---

## Chunk 6: Tests + Final Wiring

### Task 8: Frontend tests

**Files:**
- Create: `frontend/src/test/MarketplaceTab.test.tsx`

- [ ] **Step 1: Write tests**

```tsx
// frontend/src/test/MarketplaceTab.test.tsx
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import { MarketplaceTab } from '@/components/providers/MarketplaceTab'

const mockPlugin = {
  name: 'test-provider',
  display_name: 'Test Provider',
  author: 'testuser',
  version: '1.0.0',
  description: 'A test provider',
  github_url: 'https://github.com/testuser/test-provider',
  zip_url: 'https://github.com/testuser/test-provider/releases/download/v1.0.0/plugin.zip',
  sha256: 'abc123',
  capabilities: ['network'],
  min_sublarr_version: '0.22.0',
  is_official: false,
}

const mockRiskyPlugin = { ...mockPlugin, name: 'risky-provider', capabilities: ['network', 'filesystem'] }

vi.mock('@/hooks/useApi', () => ({
  useMarketplaceBrowse: () => ({ data: { plugins: [mockPlugin, mockRiskyPlugin] }, isLoading: false }),
  useInstalledPlugins: () => ({ data: { installed: [] } }),
  useInstallPlugin: () => ({ mutateAsync: vi.fn(), isPending: false, variables: null }),
  useUninstallPlugin: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useRefreshMarketplace: () => ({ mutate: vi.fn(), isPending: false }),
}))

describe('MarketplaceTab', () => {
  it('renders plugin cards', () => {
    render(<MarketplaceTab />)
    expect(screen.getByText('Test Provider')).toBeInTheDocument()
    expect(screen.getByText('Risky Provider')).toBeInTheDocument()
  })

  it('shows Community badge for non-official plugins', () => {
    render(<MarketplaceTab />)
    const communityBadges = screen.getAllByText('Community')
    expect(communityBadges.length).toBeGreaterThan(0)
  })

  it('shows capability warning modal for risky community plugins', async () => {
    render(<MarketplaceTab />)
    const installButtons = screen.getAllByText('Install')
    // Click Install on the risky plugin (second card)
    fireEvent.click(installButtons[1])
    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument()
      expect(screen.getByText(/Elevated Permissions/i)).toBeInTheDocument()
    })
  })

  it('does NOT show capability warning modal for safe plugins', async () => {
    render(<MarketplaceTab />)
    const installButtons = screen.getAllByText('Install')
    fireEvent.click(installButtons[0]) // safe plugin
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('filters plugins by search text', () => {
    render(<MarketplaceTab />)
    const searchInput = screen.getByPlaceholderText('Search plugins...')
    fireEvent.change(searchInput, { target: { value: 'risky' } })
    expect(screen.queryByText('Test Provider')).not.toBeInTheDocument()
    expect(screen.getByText('Risky Provider')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run linting + type check**

```bash
cd frontend && npm run lint && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/test/MarketplaceTab.test.tsx
git commit -m "test: MarketplaceTab — render, badges, capability warning, search filter"
```

---

### Task 9: Full backend test run

- [ ] **Step 1: Run all new tests together**

```bash
cd backend && python -m pytest tests/test_marketplace_db.py tests/test_github_registry.py tests/test_marketplace_service.py tests/test_marketplace_routes.py -v
```

Expected: all PASS.

- [ ] **Step 2: Run full test suite (with standard ignores)**

```bash
cd backend && python -m pytest --tb=short -q \
  --ignore=tests/performance \
  --ignore=tests/integration/test_translator_pipeline.py \
  --ignore=tests/integration/test_provider_pipeline.py \
  --ignore=tests/test_video_sync.py \
  --ignore=tests/test_translation_backends.py \
  --ignore=tests/test_wanted_search_reliability.py \
  -k "not (test_sonarr_download_webhook or test_radarr_download_webhook or test_parse_llm_response_too_many_merge or test_record_backend_success)"
```

Expected: green.

- [ ] **Step 3: Run ruff linting**

```bash
cd backend && ruff check . && ruff format --check .
```

- [ ] **Step 4: Final commit**

```bash
git add -u
git commit -m "chore: provider ecosystem v0.22.0 — all tests green"
```

---

## Post-Implementation

After all tasks complete:

1. **Update MEMORY.md** — add v0.22.0 status
2. **Invoke `superpowers:finishing-a-development-branch`** — create PR, bump version to 0.22.0-beta, update CHANGELOG
