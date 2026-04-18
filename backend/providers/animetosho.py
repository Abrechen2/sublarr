"""AnimeTosho subtitle provider — extracts subtitles from anime releases.

AnimeTosho automatically mirrors anime torrents and extracts embedded
subtitles. Great source for high-quality fansub ASS files.

Architecture adapted from Bazarr's subliminal_patch animetosho provider (GPL-3.0).
API: https://feed.animetosho.org/
"""

import logging
import os
from typing import ClassVar

from archive_utils import extract_subtitles_from_zip
from providers import register_provider
from providers.animetosho_parsers import (  # noqa: F401 — re-exported for back-compat
    _ISO639_2_TO_1,
    _MAX_DECOMPRESSED_SIZE,
    _decompress_xz,
    _detect_language,
    _extract_episode_number,
)
from providers.base import (
    ProviderAuthError,
    ProviderRateLimitError,
    SubtitleFormat,
    SubtitleProvider,
    SubtitleResult,
    VideoQuery,
)
from providers.http_session import create_session

logger = logging.getLogger(__name__)

FEED_API = "https://feed.animetosho.org/json"
ATTACH_BASE = "https://animetosho.org/storage/attach"

_SUBTITLE_EXTENSIONS = {".ass", ".srt", ".ssa"}
_FORMAT_MAP = {
    ".ass": SubtitleFormat.ASS,
    ".ssa": SubtitleFormat.SSA,
    ".srt": SubtitleFormat.SRT,
}


@register_provider
class AnimeToshoProvider(SubtitleProvider):
    """AnimeTosho subtitle provider."""

    name = "animetosho"

    # AnimeTosho has no published limit, but each search triggers 2 API calls
    # (search feed + torrent detail per entry) so we keep the per-second bound low.
    # 10000/day is a conservative self-imposed ceiling — well above typical usage.
    rate_limits: ClassVar[dict[str, dict[str, int]]] = {
        "free": {"second": 3, "hour": 500, "day": 10000},
    }
    languages = {
        "en",
        "ja",
        "de",
        "fr",
        "es",
        "it",
        "pt",
        "ru",
        "zh",
        "ko",
        "ar",
        "nl",
        "pl",
        "sv",
        "cs",
        "hu",
        "tr",
    }

    # Plugin system attributes
    config_fields = []  # no auth needed
    rate_limit = (50, 30)
    timeout = 20
    max_retries = 2

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.session = None

    def initialize(self):
        logger.debug("AnimeTosho: initializing (no API key required)")
        self.session = create_session(
            max_retries=2,
            backoff_factor=1.0,
            timeout=20,
            user_agent="Sublarr/1.0",
        )
        logger.debug("AnimeTosho: session created successfully")

    def terminate(self):
        if self.session:
            self.session.close()
            self.session = None

    def health_check(self) -> tuple[bool, str]:
        if not self.session:
            return False, "Not initialized"
        try:
            resp = self.session.get(FEED_API, params={"q": "test", "num": 1})
            if resp.status_code == 200:
                return True, "OK"
            return False, f"HTTP {resp.status_code}"
        except Exception as e:
            return False, str(e)

    def search(self, query: VideoQuery) -> list[SubtitleResult]:
        if not self.session:
            logger.warning("AnimeTosho: cannot search - session is None")
            return []

        logger.debug(
            "AnimeTosho: searching for %s (languages: %s)", query.display_name, query.languages
        )
        results = []

        # Build search query
        search_term = ""
        if query.is_episode:
            search_term = query.series_title or query.title
            # Prefer AniDB absolute episode when available (more precise for anime)
            if query.absolute_episode is not None:
                search_term += f" {query.absolute_episode:02d}"
            elif query.episode is not None:
                # AnimeTosho works best with episode number in search
                search_term += f" {query.episode:02d}"
        elif query.is_movie:
            search_term = query.title

        if not search_term:
            logger.warning("AnimeTosho: insufficient search criteria - no search term")
            return []

        # Search AnimeTosho feed API
        try:
            params = {
                "q": search_term,
                "num": 30,  # Max results
                "aids": 0,  # Use 0 for server caching
            }

            # AniDB ID + absolute episode provides the most accurate results.
            # Only use aid+eid together — aid alone (without eid) filters to the
            # wrong season when the anidb_id maps to S2 but the query targets S1.
            if query.anidb_id and query.absolute_episode is not None:
                params["aid"] = query.anidb_id
                params["eid"] = query.absolute_episode
                logger.debug(
                    "AnimeTosho: using AniDB aid=%d eid=%d (absolute episode)",
                    query.anidb_id,
                    query.absolute_episode,
                )

            logger.debug("AnimeTosho: API request params: %s", params)
            resp = self.session.get(FEED_API, params=params)
            logger.debug("AnimeTosho: API response status: %d", resp.status_code)

            if resp.status_code != 200:
                logger.warning(
                    "AnimeTosho search failed: HTTP %d, response: %s",
                    resp.status_code,
                    resp.text[:200],
                )
                return []

            entries = resp.json()
            if not isinstance(entries, list):
                logger.warning("AnimeTosho: API returned non-list response: %s", type(entries))
                return []

            logger.debug("AnimeTosho: API returned %d entries", len(entries))

            # Pre-filter: only fetch torrent details for episode-matching entries
            # to cap secondary API calls.  Batch releases (e.g. "01~12") are
            # included when the query episode falls in their range.
            MAX_DETAIL_CALLS = 8
            detail_count = 0
            for entry in entries:
                if detail_count >= MAX_DETAIL_CALLS:
                    break
                entry_title = entry.get("title", "")
                entry_episode = _extract_episode_number(entry_title)
                # Accept if episode matches OR entry has no episode number (could be batch)
                if entry_episode is not None:
                    target_ep = (
                        query.absolute_episode
                        if query.absolute_episode is not None
                        else query.episode
                    )
                    if target_ep is not None and entry_episode != target_ep:
                        continue
                detail_count += 1
                entry_results = self._process_entry(entry, query)
                results.extend(entry_results)

        except (ProviderRateLimitError, ProviderAuthError):
            # Re-raise: the coordinator's rate-limit handler + Phase 3 learning
            # need to see these. Swallowing them here hides the 429 from the
            # budget manager and keeps us hammering the endpoint.
            raise
        except Exception as e:
            logger.error("AnimeTosho search error: %s", e, exc_info=True)

        logger.info("AnimeTosho: found %d subtitle results", len(results))
        if results:
            logger.debug(
                "AnimeTosho: top result - %s (score: %d, format: %s, language: %s)",
                results[0].filename,
                results[0].score,
                results[0].format.value,
                results[0].language,
            )
        return results

    def _fetch_torrent_detail(self, entry_id: int) -> dict | None:
        """Fetch full torrent detail including file/attachment listing.

        AnimeTosho's search feed does not include file listings.  A second
        request to ``?show=torrent&id=<entry_id>`` returns the complete
        torrent object with a ``files`` array, where each file has an
        ``attachments`` list of extracted subtitle/font tracks.
        """
        try:
            resp = self.session.get(FEED_API, params={"show": "torrent", "id": entry_id})
            if resp.status_code != 200:
                logger.debug(
                    "AnimeTosho: torrent detail request failed for id=%d: HTTP %d",
                    entry_id,
                    resp.status_code,
                )
                return None
            return resp.json()
        except Exception as e:
            logger.debug("AnimeTosho: torrent detail fetch error for id=%d: %s", entry_id, e)
            return None

    def _process_entry(self, entry: dict, query: VideoQuery) -> list[SubtitleResult]:
        """Process a single AnimeTosho entry and extract subtitle attachments.

        The search feed does not include file listings — a second request to
        ``?show=torrent&id=<id>`` is required to get the ``files`` →
        ``attachments`` structure.
        """
        results = []

        title = entry.get("title", "")
        entry_id = entry.get("id", 0)

        # Quick pre-filter: skip entries with no files at all
        if not entry.get("num_files", 0):
            return []

        # Fetch detailed torrent info to get file/attachment listing
        detail = self._fetch_torrent_detail(entry_id)
        if not detail:
            return []

        files = detail.get("files", [])
        if not files:
            return []

        # Try to match episode number against the release title
        entry_episode = _extract_episode_number(title)
        if query.absolute_episode is not None:
            episode_match = entry_episode is not None and entry_episode == query.absolute_episode
        else:
            episode_match = (
                query.episode is not None
                and entry_episode is not None
                and entry_episode == query.episode
            )

        for f in files:
            for attachment in f.get("attachments", []):
                if attachment.get("type") != "subtitle":
                    continue

                attach_id = attachment.get("id")
                if not attach_id:
                    continue

                info = attachment.get("info", {})
                lang_raw = info.get("lang", "")
                lang = _ISO639_2_TO_1.get(lang_raw.lower(), "")

                # Derive codec/extension from info.codec or attachment-level filename
                codec = info.get("codec", "").upper()
                codec_ext_map = {"ASS": ".ass", "SSA": ".ssa", "SRT": ".srt", "SUBRIP": ".srt"}
                ext = codec_ext_map.get(codec, "")
                # Fall back: check if attachment has a top-level filename field
                raw_filename = attachment.get("filename", "") or ""
                if not ext and raw_filename:
                    ext = os.path.splitext(raw_filename)[1].lower()

                if not ext:
                    continue  # unknown subtitle type — skip

                fmt = _FORMAT_MAP.get(ext, SubtitleFormat.UNKNOWN)

                # Build a descriptive filename: track_name.lang.ext
                track_name = info.get("name", f"track{info.get('tracknum', attach_id)}")
                filename = f"{track_name}.{lang_raw or lang}.{ext.lstrip('.')}"

                # Language fall back to filename heuristic if not in ISO table
                if not lang:
                    lang = _detect_language(filename, title)

                # Filter by requested languages
                if query.languages and lang not in query.languages:
                    continue

                # Download URL: XZ-compressed attachment
                hex_id = format(attach_id, "08x")
                download_url = f"{ATTACH_BASE}/{hex_id}/{attach_id}.xz"

                # Build matches
                matches = set()
                series_title = query.series_title or query.title
                if series_title and series_title.lower() in title.lower():
                    matches.add("series")
                if episode_match:
                    matches.add("episode")
                if query.anidb_id:
                    matches.add("series")  # AniDB match is a strong signal
                if query.release_group and query.release_group.lower() in title.lower():
                    matches.add("release_group")
                for res in ["1080p", "720p", "480p", "2160p"]:
                    if res in title:
                        if query.resolution == res:
                            matches.add("resolution")
                        break

                result = SubtitleResult(
                    provider_name=self.name,
                    subtitle_id=f"{entry_id}:{attach_id}",
                    language=lang,
                    format=fmt,
                    filename=filename,
                    download_url=download_url,
                    release_info=title,
                    matches=matches,
                    provider_data={
                        "entry_id": entry_id,
                        "entry_title": title,
                        "attach_id": attach_id,
                        "is_xz": True,
                    },
                )
                results.append(result)

        return results

    # _detect_language moved to providers/animetosho_parsers.py (module-level
    # function imported above). The in-class method no longer exists; call
    # sites use the imported name directly.

    def download(self, result: SubtitleResult) -> bytes:
        if not self.session:
            raise RuntimeError("AnimeTosho not initialized")

        url = result.download_url
        if not url:
            raise ValueError("No download URL")

        resp = self.session.get(url)
        if resp.status_code != 200:
            raise RuntimeError(f"AnimeTosho download failed: HTTP {resp.status_code}")

        content = resp.content

        # Handle XZ compression
        if result.provider_data.get("is_xz") or url.endswith(".xz"):
            content = _decompress_xz(content)

        # Handle ZIP if the downloaded file is actually a ZIP
        if content[:4] == b"PK\x03\x04":
            entries = extract_subtitles_from_zip(content)
            if entries:
                name, content = entries[0]
                result.filename = os.path.basename(name)
                ext = os.path.splitext(name)[1].lower()
                result.format = _FORMAT_MAP.get(ext, SubtitleFormat.UNKNOWN)

        result.content = content
        logger.info("AnimeTosho: downloaded %s (%d bytes)", result.filename, len(content))
        return content
