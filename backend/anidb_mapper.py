"""AniDB ID Resolver — resolves AniDB IDs from Sonarr Custom Fields or TVDB mappings.

Provides multiple strategies for resolving AniDB IDs:
1. Sonarr Custom Fields (highest priority)
2. Local cache (TVDB → AniDB mappings)
3. AniList external links (anilist_id → AniDB via GraphQL)
4. AniDB title dump (anime-titles.xml.gz offline lookup)

License: GPL-3.0
"""

import gzip
import logging
import os
import re
import tempfile
import threading
import time
from difflib import SequenceMatcher
from urllib.request import Request, urlopen

# defusedxml hardens against XXE / Billion-Laughs / DTD-based attacks on
# third-party XML feeds (AniDB title dump). Drop-in API replacement for
# stdlib xml.etree.ElementTree. See PENTEST_FINDINGS.md R4-02.
from defusedxml import ElementTree as ET

from config import get_settings
from db.cache import get_anidb_mapping, save_anidb_mapping

# ---------------------------------------------------------------------------
# AniDB title dump — module-level cache (populated lazily, refreshed every 36 h)
# ---------------------------------------------------------------------------
_DUMP_URL = "https://anidb.net/api/anime-titles.xml.gz"
_DUMP_TTL = 36 * 3600  # seconds
_DUMP_MIN_ENTRIES = 8_000  # sanity-check: valid dump has >8 k anime
_DUMP_CACHE_FILE = os.path.join(tempfile.gettempdir(), "sublarr_anidb_titles.xml.gz")
_DUMP_MATCH_THRESHOLD = 0.82  # SequenceMatcher ratio required for a title hit

# { normalized_title: aid }
_title_index: dict[str, int] = {}
_title_index_lock = threading.Lock()
_title_index_loaded_at: float = 0.0

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# AniList title-resolution cache — module-level (positive 6h / negative 15min)
# ---------------------------------------------------------------------------
_TITLE_RES_TTL = 6 * 3600  # positive results
# Misses get a SHORT TTL: resolve_anidb_from_anilist swallows exceptions and
# returns None, so a "miss" can be a transient AniList failure. 15 min still
# kills the per-search-round re-query storm without pinning a bad answer.
_TITLE_RES_NEG_TTL = 15 * 60
_title_res_cache: dict[str, tuple[float, int | None]] = {}
_title_res_lock = threading.Lock()


def _get_client():
    from metadata.anilist_client import get_anilist_client

    return get_anilist_client()


def extract_anidb_from_custom_fields(series: dict, custom_field_name: str = None) -> int | None:
    """Extract AniDB ID from Sonarr series Custom Fields.

    Args:
        series: Sonarr series dict (from API)
        custom_field_name: Optional custom field name to check (defaults to config)

    Returns:
        AniDB ID as int, or None if not found
    """
    if not series:
        return None

    settings = get_settings()
    field_name = custom_field_name or settings.anidb_custom_field_name

    # Check customFields dict (Sonarr v3 structure)
    custom_fields = series.get("customFields", {})
    if custom_fields:
        # Try various field name variations
        possible_names = [
            field_name,
            "anidb_id",
            "anidbId",
            "AniDB",
            "AniDB ID",
            "anidb",
        ]

        for name in possible_names:
            if not name:
                continue
            value = custom_fields.get(name)
            if value:
                try:
                    # Handle both string and int values
                    anidb_id = int(value) if isinstance(value, (int, str)) else None
                    if anidb_id and anidb_id > 0:
                        logger.debug("Found AniDB ID %d in Custom Field '%s'", anidb_id, name)
                        return anidb_id
                except (ValueError, TypeError):
                    continue

    return None


def get_anidb_id(
    tvdb_id: int | None = None, series_title: str = "", series: dict = None
) -> int | None:
    """Resolve AniDB ID from multiple sources.

    Priority order:
    1. Sonarr Custom Fields (if series dict provided)
    2. Local cache (if tvdb_id provided)
    3. Future: External mapping APIs

    Args:
        tvdb_id: Optional TVDB ID for cache lookup
        series_title: Optional series title (for logging)
        series: Optional Sonarr series dict (for Custom Fields extraction)

    Returns:
        AniDB ID as int, or None if not found
    """
    settings = get_settings()

    # Check if AniDB integration is enabled
    if not settings.anidb_enabled:
        return None

    # Strategy 1: Sonarr Custom Fields (highest priority)
    if series:
        anidb_id = extract_anidb_from_custom_fields(series)
        if anidb_id:
            # Cache the mapping if we have a TVDB ID
            if tvdb_id and settings.anidb_fallback_to_mapping:
                try:
                    save_anidb_mapping(tvdb_id, anidb_id, series_title or "")
                except Exception as e:
                    logger.warning("Failed to cache AniDB mapping: %s", e)
            return anidb_id

    # Strategy 2: Local cache (if TVDB ID available)
    if tvdb_id and settings.anidb_fallback_to_mapping:
        cached = get_anidb_mapping(tvdb_id)
        if cached:
            logger.debug("Found cached AniDB ID %d for TVDB ID %d", cached, tvdb_id)
            return cached

    # Strategy 3: AniList external links (anilist_id → AniDB URL)
    # Falls back to None if not found

    return None


def resolve_anidb_from_anilist(anilist_id: int, tvdb_id: int | None = None) -> int | None:
    """Resolve AniDB ID from AniList external links.

    Fetches the AniList media details for *anilist_id* and extracts the AniDB
    entry ID from the ``externalLinks`` field (site == "AniDB").  Caches the
    result in ``anidb_mappings`` when *tvdb_id* is provided so subsequent
    lookups hit the local DB instead of calling the API again.

    Returns:
        AniDB series ID as int, or None if not found / API unavailable.
    """
    try:
        client = _get_client()
        details = client.get_details(anilist_id)
        if not details:
            return None

        for link in details.get("externalLinks", []):
            if link.get("site") == "AniDB":
                url = link.get("url", "")
                m = re.search(r"/anime/(\d+)", url)
                if m:
                    anidb_id = int(m.group(1))
                    logger.debug(
                        "Resolved AniDB ID %d from AniList %d external link",
                        anidb_id,
                        anilist_id,
                    )
                    if tvdb_id:
                        try:
                            save_anidb_mapping(tvdb_id, anidb_id)
                        except Exception as _cache_err:
                            logger.debug("Failed to cache AniDB mapping: %s", _cache_err)
                    return anidb_id

        logger.debug("No AniDB external link found for AniList %d", anilist_id)
    except Exception as e:
        logger.debug("AniList → AniDB resolution failed for AniList %d: %s", anilist_id, e)
    return None


def _normalize(title: str) -> str:
    """Lowercase + collapse whitespace for fuzzy matching."""
    return re.sub(r"\s+", " ", title.lower().strip())


def _fetch_dump() -> bool:
    """Download anime-titles.xml.gz to the local cache file.

    Returns True on success, False on failure.
    """
    # Size caps so a hostile/misbehaving endpoint (or a MITM) cannot OOM the
    # process: bound both the compressed download and the decompressed XML.
    _max_compressed = 100 * 1024 * 1024  # 100 MB
    _max_decompressed = 200 * 1024 * 1024  # 200 MB
    try:
        req = Request(_DUMP_URL, headers={"User-Agent": "Sublarr/1.0"})
        with urlopen(req, timeout=30) as resp:
            data = resp.read(_max_compressed + 1)
        if len(data) > _max_compressed:
            logger.warning("AniDB dump exceeds %d bytes — refusing", _max_compressed)
            return False
        # Validate: must be valid gzip with ≥ _DUMP_MIN_ENTRIES entries
        try:
            import io

            with gzip.GzipFile(fileobj=io.BytesIO(data)) as gz:
                xml_bytes = gz.read(_max_decompressed + 1)
            if len(xml_bytes) > _max_decompressed:
                logger.warning("AniDB dump decompresses beyond cap — refusing")
                return False
            root = ET.fromstring(xml_bytes)
        except Exception as parse_err:
            logger.debug("AniDB dump validation failed (parse error): %s", parse_err)
            return False
        if len(root.findall("anime")) < _DUMP_MIN_ENTRIES:
            logger.debug("AniDB dump too small — likely an error page, skipping")
            return False
        with open(_DUMP_CACHE_FILE, "wb") as f:
            f.write(data)
        logger.debug("AniDB title dump downloaded and cached (%d bytes)", len(data))
        return True
    except Exception as e:
        logger.debug("AniDB dump download failed: %s", e)
        return False


def _load_title_index() -> None:
    """Build in-memory title → AID index from the cached dump file.

    Downloads the dump if missing or stale (>36 h).  Falls back to stale cache
    on download failure.  No-ops if the index was populated within _DUMP_TTL.
    """
    global _title_index, _title_index_loaded_at

    with _title_index_lock:
        now = time.monotonic()
        if _title_index and (now - _title_index_loaded_at) < _DUMP_TTL:
            return  # still fresh

        # Decide whether we need a fresh download
        needs_download = True
        if os.path.exists(_DUMP_CACHE_FILE):
            age = time.time() - os.path.getmtime(_DUMP_CACHE_FILE)
            if age < _DUMP_TTL:
                needs_download = False

        if needs_download:
            ok = _fetch_dump()
            if not ok and not os.path.exists(_DUMP_CACHE_FILE):
                logger.debug("AniDB dump unavailable and no local cache — skipping title index")
                return

        # Parse the (possibly stale) cache file
        try:
            with gzip.open(_DUMP_CACHE_FILE, "rb") as f:
                root = ET.parse(f).getroot()
        except Exception as e:
            logger.debug("Failed to parse AniDB dump cache: %s", e)
            return

        index: dict[str, int] = {}
        for anime_el in root.findall("anime"):
            try:
                aid = int(anime_el.get("aid", "0"))
            except ValueError:
                continue
            if not aid:
                continue
            for title_el in anime_el.findall("title"):
                text = title_el.text
                if text:
                    index[_normalize(text)] = aid

        _title_index = index
        _title_index_loaded_at = now
        logger.debug("AniDB title index loaded: %d title entries", len(index))


def resolve_anidb_from_title_dump(series_title: str, tvdb_id: int | None = None) -> int | None:
    """Resolve AniDB ID via the offline anime-titles.xml.gz dump.

    Tries exact match first, then fuzzy (SequenceMatcher ≥ 0.82).  Caches the
    result in ``anidb_mappings`` when *tvdb_id* is provided.

    Returns:
        AniDB series ID as int, or None if not found.
    """
    if not series_title:
        return None
    _load_title_index()
    if not _title_index:
        return None

    needle = _normalize(series_title)

    # Exact match
    if needle in _title_index:
        aid = _title_index[needle]
        logger.debug("AniDB dump exact match: %r → AID %d", series_title, aid)
        if tvdb_id:
            try:
                save_anidb_mapping(tvdb_id, aid)
            except Exception:
                logger.warning(
                    "Failed to cache AniDB mapping tvdb=%s aid=%s", tvdb_id, aid, exc_info=True
                )
        return aid

    # Fuzzy match — find best scoring entry
    best_aid: int | None = None
    best_score = 0.0
    for title, aid in _title_index.items():
        score = SequenceMatcher(None, needle, title).ratio()
        if score > best_score:
            best_score = score
            best_aid = aid

    if best_score >= _DUMP_MATCH_THRESHOLD and best_aid:
        logger.debug(
            "AniDB dump fuzzy match: %r → AID %d (score=%.2f)", series_title, best_aid, best_score
        )
        if tvdb_id:
            try:
                save_anidb_mapping(tvdb_id, best_aid)
            except Exception:
                logger.warning(
                    "Failed to cache AniDB mapping tvdb=%s aid=%s", tvdb_id, best_aid, exc_info=True
                )
        return best_aid

    logger.debug(
        "AniDB dump: no match for %r (best score=%.2f < %.2f)",
        series_title,
        best_score,
        _DUMP_MATCH_THRESHOLD,
    )
    return None


def resolve_anidb_from_title(series_title: str, tvdb_id: int | None = None) -> int | None:
    """Resolve AniDB ID by searching AniList with a series title.

    Used as last-resort fallback when neither tvdb_id nor anilist_id is known
    (e.g. standalone items scanned without external ID metadata).  Performs
    an AniList title search, then fetches the AniDB external link from the
    best match.  Caches the result so subsequent calls are instant.

    Returns:
        AniDB series ID as int, or None if not found / API unavailable.
    """
    if not series_title:
        return None

    cache_key = _normalize(series_title)
    now = time.monotonic()
    with _title_res_lock:
        entry = _title_res_cache.get(cache_key)
        if entry:
            ttl = _TITLE_RES_TTL if entry[1] is not None else _TITLE_RES_NEG_TTL
            if (now - entry[0]) < ttl:
                return entry[1]

    resolved: int | None = None
    try:
        client = _get_client()
        match = client.search_anime(series_title)
        if match and match.get("id"):
            anilist_id = match["id"]
            logger.debug(
                "AniList title search: %r → AniList %d (%s)",
                series_title,
                anilist_id,
                match.get("title", {}).get("romaji", ""),
            )
            resolved = resolve_anidb_from_anilist(anilist_id, tvdb_id=tvdb_id)
        else:
            logger.debug("AniList title search returned no results for %r", series_title)
    except Exception as e:
        logger.debug("AniList title search failed for %r: %s", series_title, e)
        return None  # transient failure — do NOT negative-cache

    with _title_res_lock:
        _title_res_cache[cache_key] = (now, resolved)
    return resolved
