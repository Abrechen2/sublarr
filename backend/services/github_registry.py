"""GitHub-based plugin registry with DB cache.

Searches GitHub for repos with topic 'sublarr-provider', fetches each
repo's manifest.json, and caches results in marketplace_cache with 1h TTL.
Uses SUBLARR_GITHUB_TOKEN for higher rate limits when configured.
"""

import json
import logging
import pathlib
from datetime import UTC, datetime, timedelta

import requests
from sqlalchemy import select

from db.models.plugins import MarketplaceCache
from extensions import db

logger = logging.getLogger(__name__)

GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"
CACHE_TTL_HOURS = 1


class GitHubRegistry:
    def __init__(self, github_token: str = ""):
        self.session = requests.Session()
        self.session.headers["Accept"] = "application/vnd.github+json"
        self.session.headers["X-GitHub-Api-Version"] = "2022-11-28"
        if github_token:
            self.session.headers["Authorization"] = f"Bearer {github_token}"

    def search(self, force_refresh: bool = False) -> list[dict]:
        """Return plugins from cache (if fresh) or GitHub API."""
        if not force_refresh:
            cached = self._load_from_cache()
            if cached is not None:
                return cached
        return self._fetch_from_github()

    def _load_from_cache(self) -> list[dict] | None:
        """Return cached entries if any are fresher than CACHE_TTL_HOURS. None = stale/empty."""
        cutoff = (datetime.now(UTC) - timedelta(hours=CACHE_TTL_HOURS)).isoformat()
        stmt = select(MarketplaceCache).where(MarketplaceCache.last_fetched > cutoff)
        rows = db.session.execute(stmt).scalars().all()
        if not rows:
            return None
        return [self._model_to_dict(row) for row in rows]

    def _fetch_from_github(self) -> list[dict]:
        """Fetch from GitHub and store in cache. Falls back to stale cache on error."""
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
            rows = db.session.execute(select(MarketplaceCache)).scalars().all()
            return [self._model_to_dict(row) for row in rows]

        official_names = self._load_official_names()
        plugins = []
        for repo in repos:
            manifest = self._fetch_manifest(repo)
            if manifest is None:
                continue
            plugin = self._store_plugin(repo, manifest, official_names)
            if plugin:
                plugins.append(plugin)
        return plugins

    def _fetch_manifest(self, repo: dict) -> dict | None:
        """Fetch manifest.json from repo's main or master branch."""
        full_name = repo.get("full_name", "")
        for branch in ("main", "master"):
            url = f"https://raw.githubusercontent.com/{full_name}/{branch}/manifest.json"
            try:
                resp = self.session.get(url, timeout=5)
                resp.raise_for_status()
                return resp.json()
            except Exception:
                continue
        logger.debug("No manifest.json found in %s", full_name)
        return None

    def _store_plugin(self, repo: dict, manifest: dict, official_names: set[str]) -> dict | None:
        """Validate manifest fields, upsert into marketplace_cache, return dict."""
        required = ["name", "display_name", "version", "entry_point", "class_name"]
        for field in required:
            if not manifest.get(field):
                logger.debug(
                    "Skipping %s: missing manifest field '%s'",
                    repo.get("full_name"),
                    field,
                )
                return None

        now = datetime.now(UTC).isoformat()
        capabilities = manifest.get("capabilities", [])
        is_official = 1 if manifest["name"] in official_names else 0

        try:
            existing = db.session.get(MarketplaceCache, manifest["name"])
            if existing is not None:
                existing.display_name = manifest["display_name"]
                existing.author = manifest.get("author", repo.get("owner", {}).get("login", ""))
                existing.version = manifest["version"]
                existing.description = manifest.get("description", repo.get("description", ""))
                existing.github_url = repo.get("html_url", "")
                existing.zip_url = manifest.get("zip_url", "")
                existing.sha256 = manifest.get("sha256", "")
                existing.capabilities = json.dumps(capabilities)
                existing.min_sublarr_version = manifest.get("min_sublarr_version", "")
                existing.is_official = is_official
                existing.last_fetched = now
                entry = existing
            else:
                entry = MarketplaceCache(
                    name=manifest["name"],
                    display_name=manifest["display_name"],
                    author=manifest.get("author", repo.get("owner", {}).get("login", "")),
                    version=manifest["version"],
                    description=manifest.get("description", repo.get("description", "")),
                    github_url=repo.get("html_url", ""),
                    zip_url=manifest.get("zip_url", ""),
                    sha256=manifest.get("sha256", ""),
                    capabilities=json.dumps(capabilities),
                    min_sublarr_version=manifest.get("min_sublarr_version", ""),
                    is_official=is_official,
                    last_fetched=now,
                )
                db.session.add(entry)
            db.session.commit()
        except Exception as e:
            logger.error("Failed to cache plugin %s: %s", manifest["name"], e)
            db.session.rollback()
            return None

        row = db.session.get(MarketplaceCache, manifest["name"])
        return self._model_to_dict(row)

    def _load_official_names(self) -> set[str]:
        """Load curated official plugin names from official-registry.json at repo root."""
        root = pathlib.Path(__file__).parent.parent.parent
        registry_path = root / "official-registry.json"
        try:
            data = json.loads(registry_path.read_text())
            return set(data.get("official_plugins", []))
        except Exception:
            return set()

    def _model_to_dict(self, row: MarketplaceCache) -> dict:
        d = {
            "name": row.name,
            "display_name": row.display_name,
            "author": row.author,
            "version": row.version,
            "description": row.description,
            "github_url": row.github_url,
            "zip_url": row.zip_url,
            "sha256": row.sha256,
            "capabilities": json.loads(row.capabilities or "[]"),
            "min_sublarr_version": row.min_sublarr_version,
            "is_official": bool(row.is_official),
            "last_fetched": row.last_fetched,
        }
        return d
