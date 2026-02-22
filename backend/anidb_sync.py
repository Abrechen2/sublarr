"""AniDB Absolute Episode Order sync.

Fetches the anime-lists XML from GitHub and upserts the TVDB season/episode ->
AniDB absolute episode mappings into the anidb_absolute_mappings table.

Sync is triggered:
  - Manually via POST /api/v1/anidb-mapping/refresh
  - Weekly by the background scheduler (started from app.py -> _start_schedulers)

XML source:
  https://raw.githubusercontent.com/Anime-Lists/anime-lists/master/anime-list.xml
"""

import logging
import threading
import time
import xml.etree.ElementTree as ET
from typing import Optional

import requests

logger = logging.getLogger(__name__)

ANIME_LIST_URL = (
    "https://raw.githubusercontent.com/Anime-Lists/anime-lists/master/anime-list.xml"
)
REQUEST_TIMEOUT_SECONDS = 30
DEFAULT_INTERVAL_HOURS = 168  # weekly

_scheduler_lock = threading.Lock()
_scheduler: Optional["AnidbSyncScheduler"] = None

sync_state = {
    "running": False,
    "last_run": None,
    "last_result": None,
    "error": None,
}
_sync_state_lock = threading.Lock()


def _fetch_xml(url: str) -> bytes:
    """Download the anime-list XML. Raises requests.RequestException on failure."""
    response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.content


def _parse_mapping_token(token: str):
    """Parse a single anidb_ep-tvdb_ep token.

    Returns:
        (anidb_ep, tvdb_ep) tuple of ints, or None if malformed.
    """
    token = token.strip()
    if not token:
        return None
    parts = token.split("-")
    if len(parts) != 2:
        return None
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return None


def _process_xml(xml_bytes: bytes, app) -> dict:
    """Parse the anime-list XML and upsert mappings into the DB."""
    series_processed = 0
    mappings_upserted = 0
    skipped = 0

    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        return {"series_processed": 0, "mappings_upserted": 0, "skipped": 0,
                "error": f"XML parse error: {exc}"}

    with app.app_context():
        from db.repositories.anidb import AnidbRepository
        repo = AnidbRepository()

        for anime in root.findall("anime"):
            tvdb_id_str = anime.get("tvdbid", "").strip()
            if not tvdb_id_str or not tvdb_id_str.isdigit():
                skipped += 1
                continue

            tvdb_id = int(tvdb_id_str)
            series_processed += 1

            mapping_list = anime.find("mapping-list")
            if mapping_list is None:
                continue

            for mapping_el in mapping_list.findall("mapping"):
                tvdb_season_str = mapping_el.get("tvdbseason", "").strip()
                if not tvdb_season_str.lstrip("-").isdigit():
                    continue
                tvdb_season = int(tvdb_season_str)
                if tvdb_season <= 0:
                    # Season 0 specials -- skip
                    continue

                text = (mapping_el.text or "").strip()
                tokens = text.split(";")
                for token in tokens:
                    parsed = _parse_mapping_token(token)
                    if parsed is None:
                        continue
                    anidb_ep, tvdb_ep = parsed
                    if anidb_ep <= 0 or tvdb_ep <= 0:
                        continue
                    try:
                        repo.upsert_mapping(
                            tvdb_id=tvdb_id,
                            season=tvdb_season,
                            episode=tvdb_ep,
                            anidb_absolute_episode=anidb_ep,
                            source="anime-lists",
                        )
                        mappings_upserted += 1
                    except Exception as exc:
                        logger.debug(
                            "Failed to upsert mapping TVDB %d S%dE%d: %s",
                            tvdb_id, tvdb_season, tvdb_ep, exc,
                        )

    logger.info(
        "AniDB sync complete: %d series processed, %d mappings upserted, %d skipped",
        series_processed, mappings_upserted, skipped,
    )
    return {
        "series_processed": series_processed,
        "mappings_upserted": mappings_upserted,
        "skipped": skipped,
        "error": None,
    }


def run_sync(app) -> dict:
    """Execute a full AniDB sync (fetch + parse + upsert).

    Thread-safe: only one sync runs at a time.

    Returns:
        Result dict (series_processed, mappings_upserted, skipped, error).
    """
    with _sync_state_lock:
        if sync_state["running"]:
            return {"error": "Sync already running", "series_processed": 0,
                    "mappings_upserted": 0, "skipped": 0}
        sync_state["running"] = True
        sync_state["error"] = None

    start = time.monotonic()
    result = {"series_processed": 0, "mappings_upserted": 0, "skipped": 0, "error": None}
    try:
        logger.info("Starting AniDB absolute episode sync from %s", ANIME_LIST_URL)
        xml_bytes = _fetch_xml(ANIME_LIST_URL)
        result = _process_xml(xml_bytes, app)
    except requests.RequestException as exc:
        result["error"] = f"Network error fetching anime-list: {exc}"
        logger.error("AniDB sync failed: %s", exc)
    except Exception as exc:
        result["error"] = f"Unexpected error: {exc}"
        logger.exception("AniDB sync unexpected failure")
    finally:
        elapsed = time.monotonic() - start
        result["elapsed_seconds"] = round(elapsed, 1)
        with _sync_state_lock:
            sync_state["running"] = False
            sync_state["last_run"] = _now_iso()
            sync_state["last_result"] = result
            sync_state["error"] = result.get("error")

    return result


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


class AnidbSyncScheduler:
    """Periodic AniDB sync runner using threading.Timer."""

    def __init__(self, app, interval_hours: int = DEFAULT_INTERVAL_HOURS):
        self._app = app
        self._interval_hours = interval_hours
        self._timer: Optional[threading.Timer] = None
        self._running = False

    def start(self) -> None:
        """Schedule the first run after one full interval."""
        self._running = True
        self._schedule_next()
        logger.info("AniDB sync scheduler started (every %dh)", self._interval_hours)

    def stop(self) -> None:
        """Cancel any pending timer."""
        self._running = False
        if self._timer:
            self._timer.cancel()
            self._timer = None
        logger.info("AniDB sync scheduler stopped")

    def _schedule_next(self) -> None:
        if not self._running:
            return
        interval_seconds = self._interval_hours * 3600
        self._timer = threading.Timer(interval_seconds, self._run_and_reschedule)
        self._timer.daemon = True
        self._timer.start()

    def _run_and_reschedule(self) -> None:
        try:
            run_sync(self._app)
        except Exception as exc:
            logger.error("AniDB scheduled sync error: %s", exc)
        finally:
            self._schedule_next()


def start_anidb_sync_scheduler(app, interval_hours: int = DEFAULT_INTERVAL_HOURS) -> None:
    """Start the weekly AniDB sync scheduler (idempotent)."""
    global _scheduler
    with _scheduler_lock:
        if _scheduler is not None:
            return
        _scheduler = AnidbSyncScheduler(app, interval_hours)
        _scheduler.start()


def stop_anidb_sync_scheduler() -> None:
    """Stop the AniDB sync scheduler if running."""
    global _scheduler
    with _scheduler_lock:
        if _scheduler:
            _scheduler.stop()
            _scheduler = None
