"""Shoko Server v3 REST API client.

Shoko is an AniDB-backed anime collection manager. Because Shoko already
matches every physical file to its exact AniDB anime + AniDB episode (and
therefore the AniDB absolute-episode number), it is an *authoritative*
source for the IDs Sublarr otherwise has to guess via the fuzzy AniDB
resolution chain in ``anidb_mapper`` / ``metadata_enrichers``.

This client is deliberately thin and follows the same shape as the other
metadata/media-server clients in the codebase (see ``metadata/tvdb_client.py``
and ``mediaserver/jellyfin.py``): a ``requests.Session`` with per-request
retry/429 handling, private ``_get``/``_post`` helpers that return ``None``
on failure instead of raising, and typed public methods.

Auth: Shoko v3 accepts an ``apikey`` — either supplied directly (a persistent
API key) or obtained by logging in with user/pass/device. Login goes to
``POST /api/v3/Auth/SignIn`` first and falls back to the legacy
``POST /api/auth`` for older servers. The key is sent as the ``apikey``
header on every request.

Endpoints used (Shoko Server v3):
    POST /api/v3/Auth/SignIn                        -> {"Token": "..."}
    POST /api/auth                                  -> {"apikey": "..."} (legacy fallback)
    GET  /api/v3/Init/Status                        -> server state (no auth)
    GET  /api/v3/ImportFolder                       -> auth probe + scan targets
    GET  /api/v3/File/PathEndsWith?path=&include=XRefs
    GET  /api/v3/Series/{id}                        -> IDs.AniDB
    GET  /api/v3/Episode/{id}                       -> IDs.AniDB + AniDB.EpisodeNumber
    POST /api/v3/File/{id}/Rescan
    GET  /api/v3/ImportFolder/{id}/Scan

License: GPL-3.0
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 15
MAX_RETRIES = 2
BACKOFF_BASE = 2


@dataclass
class ShokoFileIDs:
    """Authoritative AniDB identifiers Shoko holds for a physical file."""

    file_id: int | None = None
    anidb_anime_id: int | None = None
    anidb_episode_id: int | None = None
    # AniDB numbers episodes 1..N within each anime entry, so for a "Normal"
    # episode this number is the AniDB absolute-order number Sublarr wants.
    absolute_episode: int | None = None


class ShokoClient:
    """Minimal client for the Shoko Server v3 REST API."""

    def __init__(
        self,
        url: str,
        api_key: str = "",
        username: str = "",
        password: str = "",
    ):
        self.url = (url or "").rstrip("/")
        self._api_key = api_key or ""
        self._username = username or ""
        self._password = password or ""
        self.session = requests.Session()
        self.session.headers["Accept"] = "application/json"
        if self._api_key:
            self.session.headers["apikey"] = self._api_key

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------
    def _ensure_auth(self) -> bool:
        """Ensure an apikey is set, logging in with user/pass if needed.

        Tries the v3 ``Auth/SignIn`` endpoint first; older Shoko servers
        without it (404) get the legacy ``/api/auth`` call. Returns True when
        an apikey is available on the session (#193).
        """
        if self._api_key:
            return True
        if not (self._username and self._password):
            return False
        key = self._sign_in_v3() or self._sign_in_legacy()
        if key:
            self._api_key = key
            self.session.headers["apikey"] = key
            return True
        return False

    def _sign_in_v3(self) -> str | None:
        """``POST /api/v3/Auth/SignIn`` — current Shoko login, returns a token."""
        data = self._post_login(
            "/api/v3/Auth/SignIn",
            {"user": self._username, "password": self._password, "device": "Sublarr"},
        )
        if not isinstance(data, dict):
            return None
        return data.get("Token") or data.get("token")

    def _sign_in_legacy(self) -> str | None:
        """``POST /api/auth`` — legacy login kept for older Shoko servers."""
        data = self._post_login(
            "/api/auth",
            {"user": self._username, "pass": self._password, "device": "Sublarr"},
        )
        if not isinstance(data, dict):
            return None
        return data.get("apikey")

    def _post_login(self, path: str, payload: dict) -> dict | None:
        try:
            resp = self.session.post(
                f"{self.url}{path}",
                json=payload,
                timeout=REQUEST_TIMEOUT,
            )
            if resp.status_code == 404:
                # Endpoint not present on this Shoko version — caller falls back.
                logger.debug("Shoko login endpoint %s not available (404)", path)
                return None
            if resp.status_code in (400, 401):
                logger.warning(
                    "Shoko login at %s%s rejected (HTTP %d) — check username/password",
                    self.url,
                    path,
                    resp.status_code,
                )
                return None
            if resp.status_code >= 300:
                logger.warning(
                    "Shoko login at %s%s failed: HTTP %d", self.url, path, resp.status_code
                )
                return None
            return resp.json()
        except Exception as e:  # noqa: BLE001 — auth failure is non-fatal
            logger.warning("Shoko auth failed at %s%s: %s", self.url, path, e)
            return None

    # ------------------------------------------------------------------
    # HTTP helpers (return None on failure, never raise)
    # ------------------------------------------------------------------
    def _request(self, method: str, path: str, params=None, timeout=REQUEST_TIMEOUT):
        url = f"{self.url}{path}"
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = self.session.request(method, url, params=params, timeout=timeout)
                if resp.status_code == 429:
                    retry_after = resp.headers.get("Retry-After")
                    try:
                        wait_seconds = int(retry_after) if retry_after else 60
                    except ValueError:
                        wait_seconds = 60
                    logger.warning(
                        "Shoko %s %s rate limited (attempt %d), waiting %ds",
                        method,
                        path,
                        attempt,
                        wait_seconds,
                    )
                    if attempt < MAX_RETRIES:
                        time.sleep(wait_seconds)
                        continue
                    return None
                resp.raise_for_status()
                if not resp.content:
                    return {}
                return resp.json()
            except requests.ConnectionError as e:
                logger.warning("Shoko %s %s failed (attempt %d): %s", method, path, attempt, e)
            except requests.Timeout:
                logger.warning("Shoko %s %s timed out (attempt %d)", method, path, attempt)
            except Exception as e:  # noqa: BLE001 — bubble up as None
                logger.error("Shoko unexpected error on %s %s: %s", method, path, e)
                return None
            if attempt < MAX_RETRIES:
                time.sleep(BACKOFF_BASE * attempt)
        return None

    def _get(self, path, params=None, timeout=REQUEST_TIMEOUT):
        return self._request("GET", path, params=params, timeout=timeout)

    def _post(self, path, params=None, timeout=REQUEST_TIMEOUT):
        return self._request("POST", path, params=params, timeout=timeout)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def health_check(self) -> tuple[bool, str]:
        """Check that Shoko is reachable (and, if secured, that auth works).

        ``/api/v3/Init/Status`` needs no auth, so it verifies reachability.
        A subsequent authenticated call confirms the apikey when credentials
        are configured.
        """
        status = self._get("/api/v3/Init/Status")
        if status is None:
            return False, f"Cannot connect to Shoko at {self.url}"

        state = ""
        if isinstance(status, dict):
            state = status.get("State", "") or status.get("state", "")

        # Confirm auth when we have (or can obtain) an apikey.
        if self._api_key or (self._username and self._password):
            if not self._ensure_auth():
                return False, "Shoko reachable but authentication failed"
            probe_ok, probe_detail = self._probe_auth()
            if not probe_ok:
                return False, f"Shoko reachable but {probe_detail}"

        suffix = f" ({state})" if state else ""
        return True, f"Connected to Shoko at {self.url}{suffix}"

    def _probe_auth(self) -> tuple[bool, str]:
        """Verify the apikey against an authenticated endpoint.

        Uses ``/api/v3/ImportFolder`` — cheap, present on every Shoko v3, and
        already part of this client's surface. The previous probe hit
        ``/api/v3/Dashboard``, which has no root GET route and 404s on every
        server, making a valid key look rejected (#193). Only a 401/403 is
        reported as a bad key; other failures are named for what they are.
        """
        try:
            resp = self.session.get(f"{self.url}/api/v3/ImportFolder", timeout=REQUEST_TIMEOUT)
        except requests.RequestException as e:
            return False, f"auth probe failed: {e}"
        if resp.status_code in (401, 403):
            return False, "apikey rejected"
        if resp.status_code == 429:
            # Throttling says nothing about the key. This deliberately does not
            # go through _request: that would sleep out the Retry-After inside
            # a health check, and it collapses every failure into None, which
            # is the distinction this probe exists to make.
            return False, "shoko is rate limiting (try again shortly)"
        if not resp.ok:
            return False, f"auth probe got HTTP {resp.status_code}"
        return True, ""

    def get_file_ids_by_path(self, file_path: str) -> ShokoFileIDs | None:
        """Resolve a physical file to its authoritative AniDB IDs.

        Looks the file up by the tail of its path (``PathEndsWith`` matches on
        a path suffix, so it is robust to differing mount roots between Shoko
        and Sublarr). Returns ``None`` when the file is unknown to Shoko or
        Shoko is unreachable.
        """
        if not file_path:
            return None
        if not self._ensure_auth() and (self._username or self._password):
            # Credentials were given but login failed — treat as unavailable.
            return None

        # Match on filename + parent dir: specific enough to avoid collisions,
        # short enough to survive path-root differences.
        basename = os.path.basename(file_path)
        parent = os.path.basename(os.path.dirname(file_path))
        needle = f"{parent}/{basename}" if parent else basename

        files = self._get(
            "/api/v3/File/PathEndsWith",
            params={"path": needle, "include": "XRefs", "limit": 1},
        )
        if not files:
            # Retry with just the filename in case the parent dir differs.
            files = self._get(
                "/api/v3/File/PathEndsWith",
                params={"path": basename, "include": "XRefs", "limit": 1},
            )
        if not files or not isinstance(files, list):
            return None

        file_obj = files[0]
        ids = ShokoFileIDs(file_id=_as_int(file_obj.get("ID")))
        xref = _first_cross_reference(file_obj)
        if xref is None:
            return ids if ids.file_id else None

        ids.anidb_anime_id = _extract_anidb_anime_id(xref)
        ids.anidb_episode_id = _extract_anidb_episode_id(xref)

        # The AniDB episode number (== absolute order for Normal episodes) is
        # not always inlined in the file xref; fetch it from the episode when
        # we have a Shoko episode id to resolve it from.
        shoko_episode_id = _extract_shoko_episode_id(xref)
        if shoko_episode_id:
            ids.absolute_episode = self._get_anidb_episode_number(shoko_episode_id)

        return ids

    def _get_anidb_episode_number(self, shoko_episode_id: int) -> int | None:
        """Return the AniDB episode number for a Shoko episode id (Normal type only)."""
        ep = self._get(f"/api/v3/Episode/{shoko_episode_id}")
        if not isinstance(ep, dict):
            return None
        anidb = ep.get("AniDB")
        if not isinstance(anidb, dict):
            return None
        # Only "Normal" episodes carry a meaningful absolute number; specials,
        # OPs/EDs, trailers etc. are numbered in their own AniDB namespace.
        ep_type = str(anidb.get("Type", "") or "").lower()
        if ep_type and ep_type != "normal":
            return None
        return _as_int(anidb.get("EpisodeNumber"))

    def rescan_file_by_path(self, file_path: str) -> bool:
        """Trigger a rescan of the file at ``file_path`` so Shoko re-reads sidecars."""
        ids = self.get_file_ids_by_path(file_path)
        if not ids or not ids.file_id:
            return False
        result = self._post(f"/api/v3/File/{ids.file_id}/Rescan")
        return result is not None

    def refresh_library(self) -> bool:
        """Trigger a scan of every import folder (fallback when a file is unknown)."""
        if not self._ensure_auth() and (self._username or self._password):
            return False
        folders = self._get("/api/v3/ImportFolder")
        if not isinstance(folders, list) or not folders:
            return False
        ok = False
        for folder in folders:
            folder_id = _as_int(folder.get("ID"))
            if folder_id and self._get(f"/api/v3/ImportFolder/{folder_id}/Scan") is not None:
                ok = True
        return ok


# ---------------------------------------------------------------------------
# Cross-reference parsing helpers
#
# The exact nesting of a File's cross-references has shifted across Shoko
# releases, so these read defensively: they accept both a flat shape
# (``AnidbAnimeID`` / ``AnidbEpisodeID`` integers) and the nested
# ``SeriesID`` / ``EpisodeIDs`` objects that expose an ``AniDB`` field.
# ---------------------------------------------------------------------------
def _as_int(value) -> int | None:
    try:
        if value is None:
            return None
        ivalue = int(value)
        return ivalue if ivalue > 0 else None
    except (TypeError, ValueError):
        return None


def _first_cross_reference(file_obj: dict) -> dict | None:
    if not isinstance(file_obj, dict):
        return None
    xrefs = file_obj.get("SeriesIDs")
    if isinstance(xrefs, list) and xrefs and isinstance(xrefs[0], dict):
        return xrefs[0]
    return None


def _extract_anidb_anime_id(xref: dict) -> int | None:
    # Flat shape (ReleaseCrossReference): {"AnidbAnimeID": 123, ...}
    flat = _as_int(xref.get("AnidbAnimeID"))
    if flat:
        return flat
    # Nested shape: {"SeriesID": {"AniDB": 123, "ID": <shoko>}}
    series_id = xref.get("SeriesID")
    if isinstance(series_id, dict):
        return _as_int(series_id.get("AniDB"))
    # Some builds expose SeriesID as the plain AniDB int.
    return _as_int(series_id)


def _extract_anidb_episode_id(xref: dict) -> int | None:
    # Flat shape
    flat = _as_int(xref.get("AnidbEpisodeID"))
    if flat:
        return flat
    # Nested shape: {"EpisodeIDs": [{"AniDB": 456, "ID": <shoko>}]}
    episode_ids = xref.get("EpisodeIDs")
    if isinstance(episode_ids, list) and episode_ids and isinstance(episode_ids[0], dict):
        return _as_int(episode_ids[0].get("AniDB"))
    return None


def _extract_shoko_episode_id(xref: dict) -> int | None:
    episode_ids = xref.get("EpisodeIDs")
    if isinstance(episode_ids, list) and episode_ids and isinstance(episode_ids[0], dict):
        return _as_int(episode_ids[0].get("ID"))
    return None
