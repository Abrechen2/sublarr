"""SubDL subtitle provider — Subscene successor.

SubDL provides broad subtitle coverage with a REST API. Supports
search by IMDB/TMDB ID and text queries. Downloads are ZIP (sometimes RAR)
archives, addressed by the ``url`` field of each subtitle object.

API docs: https://subdl.com/api-doc
Free tier (as reported by /api/v2/me, #212): 2000 searches and 50 downloads per day.
License: GPL-3.0

Response shape (captured from the live v1 API, #212): each ``subtitles[]``
object carries author, episode, episode_end, episode_from, fps, framerate,
full_season, hi, lang (display name), language (code, e.g. "EN"), name,
release_name, season, subtitlePage and url. ``sd_id`` and ``year`` exist only
on ``results[]`` — the show or movie — never on a subtitle.

The v1 search endpoint only accepts the API key as a query parameter, so
every URL and exception text of a search carries it. Nothing this module logs
or raises may contain it: see ``_redact`` and ``http_session.redact_url_secrets``.
"""

import logging
import os
import re
from typing import ClassVar
from urllib.parse import urlsplit

import requests

from archive_utils import extract_subtitles_from_rar, extract_subtitles_from_zip
from config_language_data import normalize_language_code
from providers import _stream_download, register_provider
from providers.base import (
    ProviderAuthError,
    ProviderError,
    ProviderNotApplicableError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    SubtitleFormat,
    SubtitleProvider,
    SubtitleResult,
    VideoQuery,
)
from providers.http_session import create_session, redact_url_secrets
from security_utils import validate_download_url

logger = logging.getLogger(__name__)

API_BASE = "https://api.subdl.com/api/v1/subtitles"
DOWNLOAD_HOST = "https://dl.subdl.com"

_SUBTITLE_EXTENSIONS = {".ass", ".srt", ".ssa", ".vtt"}

_FORMAT_MAP = {
    ".ass": SubtitleFormat.ASS,
    ".ssa": SubtitleFormat.SSA,
    ".srt": SubtitleFormat.SRT,
    ".vtt": SubtitleFormat.VTT,
}

# Preference among files of an archive: ASS keeps styling, SRT is the baseline.
_FORMAT_RANK = {".ass": 2, ".ssa": 2, ".srt": 1}

# SubDL language codes that are not plain ISO 639-1 once lower-cased.
_SUBDL_LANGUAGE_CODES = {"br_pt": "pt", "zh_bg": "zh"}

# A subtitle's download path: "/subtitle/3389884-8312959.zip" -> "3389884-8312959".
_DOWNLOAD_PATH_RE = re.compile(r"^/subtitle/([A-Za-z0-9_-]+)(?:\.(?:zip|rar))?$", re.IGNORECASE)

_RAR_MAGIC = b"Rar!\x1a\x07"

# Regex to extract release group from release name (e.g. "[SubGroup] Title" or "Title-SubGroup")
_RELEASE_GROUP_RE = re.compile(r"^\[([^\]]+)\]|[-.]([A-Za-z0-9]+)$")

# Episode number extraction from release name
_EPISODE_RE = re.compile(r"(?:S\d{1,2}E|E|EP|Episode[.\s_]?)(\d{1,3})\b", re.IGNORECASE)

# Episode markers in archive member names, strongest first. Every number is
# bounded by (?!\d) so "E10" never matches inside "E100", and letter/digit
# look-behinds keep "keep 3" or "1920x1080" from reading as episodes.
_FILE_SXE_RE = re.compile(
    r"(?<![a-z0-9])s(\d{1,2})[ ._-]?e(\d{1,4})(?:[-_]?e(\d{1,4}))?(?!\d)", re.IGNORECASE
)
_FILE_NXN_RE = re.compile(r"(?<![a-z0-9])(\d{1,2})x(\d{2,3})(?!\d)", re.IGNORECASE)
_FILE_EP_RE = re.compile(
    r"(?<![a-z0-9])(?:ep(?:isode)?|e)[ ._-]?(\d{1,4})(?:v\d)?(?!\d)", re.IGNORECASE
)
# archive_utils sanitises member names, so "Show - 03" arrives as "Show_-_03".
_FILE_DASH_RE = re.compile(r"(?<=[\s_]-[\s_])(\d{1,4})(?:v\d)?(?!\d)")
_FILE_TRAILING_RE = re.compile(r"[\s_](\d{1,3})(?:v\d)?$")

_MATCH, _UNKNOWN, _CONFLICT = "match", "unknown", "conflict"


def _positive_int(value) -> int | None:
    """``value`` as a positive int, or None (SubDL sends null, 0 and strings)."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _wanted_episodes(query: VideoQuery) -> set[int]:
    wanted = {query.episode} if query.episode is not None else set()
    if query.absolute_episode:
        wanted.add(query.absolute_episode)
    return wanted


def _parse_file_episode(stem: str) -> tuple[int | None, set[int]]:
    """Return (season, episodes) named by an archive member, strongest marker first."""
    m = _FILE_SXE_RE.search(stem)
    if m:
        episodes = {int(m.group(2))}
        if m.group(3):
            episodes.add(int(m.group(3)))
        return int(m.group(1)), episodes
    m = _FILE_NXN_RE.search(stem)
    if m:
        return int(m.group(1)), {int(m.group(2))}
    for pattern in (_FILE_EP_RE, _FILE_DASH_RE, _FILE_TRAILING_RE):
        m = pattern.search(stem)
        if m:
            return None, {int(m.group(1))}
    return None, set()


def _classify_file(filename: str, query: VideoQuery) -> str:
    """Whether an archive member is the queried episode, another one, or unnumbered."""
    stem = os.path.splitext(os.path.basename(filename))[0]
    season, episodes = _parse_file_episode(stem)
    if not episodes:
        return _UNKNOWN
    if season is not None and query.season is not None and season != query.season:
        # Absolute-numbered releases sometimes tag everything S01 — accept the
        # absolute number there, but never the per-season one (S02E03 != S01E03).
        absolute = query.absolute_episode
        if absolute and absolute != query.episode and absolute in episodes:
            return _MATCH
        return _CONFLICT
    return _MATCH if episodes & _wanted_episodes(query) else _CONFLICT


def _format_rank(filename: str) -> int:
    return _FORMAT_RANK.get(os.path.splitext(filename)[1].lower(), 0)


def _pick_best_subtitle(
    files: list[tuple[str, bytes]], query: VideoQuery, exact_episode: bool = False
) -> tuple[str, bytes] | None:
    """Pick the subtitle file to use from an extracted archive.

    For an episode query only a file naming that episode (or its absolute
    number) qualifies; a season pack without it yields None rather than an
    arbitrary episode. ``exact_episode`` marks a result SubDL itself labelled
    as the queried episode — then an unnumbered file is acceptable too, a file
    naming another episode still is not. Among candidates ASS beats SRT.
    """
    if not files:
        return None

    if query.episode is None:
        candidates = files
    else:
        classified = [(name, content, _classify_file(name, query)) for name, content in files]
        candidates = [(n, c) for n, c, kind in classified if kind == _MATCH]
        if not candidates and exact_episode:
            candidates = [(n, c) for n, c, kind in classified if kind == _UNKNOWN]
        if not candidates:
            return None

    return max(candidates, key=lambda item: _format_rank(item[0]))


def _parse_release_group(release_name: str) -> str:
    """Extract release group from a release name."""
    m = _RELEASE_GROUP_RE.search(release_name)
    if m:
        return m.group(1) or m.group(2) or ""
    return ""


def _iso_language(sub: dict) -> str:
    """ISO 639-1 code of a subtitle; "" when neither field maps to one.

    ``language`` holds the code ("EN"), ``lang`` the display name ("English").
    The display name is only a fallback and never returned as-is: the search
    coordinator keeps a result only if its language is one of the query's codes.
    """
    for raw in (sub.get("language"), sub.get("lang")):
        if not isinstance(raw, str) or not raw.strip():
            continue
        key = raw.strip().lower()
        code = _SUBDL_LANGUAGE_CODES.get(key) or normalize_language_code(key)
        if len(code) == 2 and code.isalpha():
            return code
    return ""


def _download_path(raw) -> str:
    """The key-free "/subtitle/<id>.zip" path of a subtitle's ``url``, or ""."""
    if not isinstance(raw, str) or not raw.strip():
        return ""
    path = urlsplit(raw.strip()).path
    return path if _DOWNLOAD_PATH_RE.match(path) else ""


def _covers_episode(sub: dict, query: VideoQuery) -> bool:
    """False when SubDL's own episode fields say the result is another episode."""
    if not query.is_episode:
        return True
    wanted = _wanted_episodes(query)
    ep_from = _positive_int(sub.get("episode_from"))
    ep_end = _positive_int(sub.get("episode_end"))
    if ep_from and ep_end and ep_end >= ep_from:
        return any(ep_from <= ep <= ep_end for ep in wanted)
    episode = _positive_int(sub.get("episode"))
    if episode and not sub.get("full_season"):
        return episode in wanted
    return True


def _is_exact_episode(sub: dict, query: VideoQuery) -> bool:
    """SubDL labels this result as exactly the queried episode."""
    if not query.is_episode or sub.get("full_season"):
        return False
    wanted = _wanted_episodes(query)
    episode = _positive_int(sub.get("episode"))
    ep_from = _positive_int(sub.get("episode_from"))
    ep_end = _positive_int(sub.get("episode_end"))
    if ep_from and ep_end and ep_from != ep_end:
        return False
    return (episode or ep_from) in wanted


def _show_year(data: dict) -> int | None:
    shows = data.get("results")
    if isinstance(shows, list) and shows and isinstance(shows[0], dict):
        return _positive_int(shows[0].get("year"))
    return None


@register_provider
class SubDLProvider(SubtitleProvider):
    """SubDL subtitle provider (Subscene successor)."""

    name = "subdl"

    # Search budget. The free tier allows 2000 searches/day (#212); 500 leaves
    # generous headroom. Pro tier is effectively unthrottled — 5000 is a cushioned soft cap.
    rate_limits: ClassVar[dict[str, dict[str, int]]] = {
        "free": {"second": 2, "hour": 100, "day": 500},
        "pro": {"second": 5, "hour": 500, "day": 5000},
    }
    languages = {
        "en",
        "de",
        "fr",
        "es",
        "it",
        "pt",
        "ru",
        "ja",
        "zh",
        "ko",
        "ar",
        "nl",
        "pl",
        "sv",
        "da",
        "no",
        "fi",
        "cs",
        "hu",
        "tr",
        "th",
        "vi",
        "id",
        "hi",
        "ms",
        "ro",
        "bg",
        "hr",
        "el",
        "he",
        "uk",
        "sk",
        "sl",
        "sr",
        "lt",
        "lv",
        "et",
        "fa",
        "bn",
        "ta",
        "te",
        "ml",
        "kn",
        "mr",
        "gu",
        "ur",
        "my",
        "km",
        "lo",
    }

    # Plugin system attributes
    config_fields = [
        {"key": "subdl_api_key", "label": "API Key", "type": "password", "required": True},
    ]
    rate_limit = (30, 10)
    timeout = 15
    max_retries = 2

    def __init__(self, api_key: str = "", **kwargs):
        super().__init__(**kwargs)
        self.api_key = api_key
        self.session = None

    def initialize(self):
        if not self.api_key:
            logger.info("SubDL: no API key configured, provider will be disabled")
            return

        logger.debug("SubDL: initializing with API key (length: %d)", len(self.api_key))
        self.session = create_session(
            max_retries=2,
            backoff_factor=1.0,
            timeout=20,
            user_agent="Sublarr/1.0",
        )
        logger.debug("SubDL: session created successfully")

    def terminate(self):
        if self.session:
            self.session.close()
            self.session = None

    def _redact(self, value) -> str:
        """``str(value)`` with the API key removed, however it is embedded."""
        text = redact_url_secrets(str(value))
        if self.api_key:
            text = text.replace(self.api_key, "***")
        return text

    def health_check(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, "API key not configured"
        if not self.session:
            return False, "Not initialized"
        try:
            resp = self.session.get(
                API_BASE,
                params={
                    "api_key": self.api_key,
                    "film_name": "test",
                    "subs_per_page": 1,
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status"):
                    return True, "OK"
                return False, self._redact(data.get("error", "Unknown error"))
            if resp.status_code == 401:
                return False, "Invalid API key"
            return False, f"HTTP {resp.status_code}"
        except Exception as e:
            return False, self._redact(e)

    def _build_params(self, query: VideoQuery) -> dict | None:
        """Request parameters for ``query``; None when there is nothing to search by."""
        params = {
            "api_key": self.api_key,
            "subs_per_page": 30,
        }
        if query.languages:
            params["languages"] = ",".join(query.languages)
        if query.imdb_id:
            params["imdb_id"] = query.imdb_id

        if query.is_episode:
            params["type"] = "tv"
            if query.season is not None:
                params["season_number"] = query.season
            if query.episode is not None:
                params["episode_number"] = query.episode
        elif query.is_movie:
            params["type"] = "movie"

        if not query.imdb_id:
            search_term = query.series_title or query.title
            if not search_term:
                return None
            params["film_name"] = search_term
            # SubDL answers a title search with the subtitles of the FIRST
            # matching title only — without a year, City Hunter (1987) came
            # back as the 2011 drama (#212).
            if query.year:
                params["year"] = query.year
        return params

    def _fetch(self, params: dict) -> dict:
        """Run the search request. Any failure raises; "no results" never hides an outage."""
        try:
            resp = self.session.get(API_BASE, params=params)
        except ProviderError:
            raise
        except requests.Timeout as e:
            raise ProviderTimeoutError(f"SubDL search timed out: {self._redact(e)}") from None
        except Exception as e:
            # ``from None``: the original exception text holds the full URL with
            # the key, and a chained traceback would print it.
            raise ProviderError(f"SubDL search failed: {self._redact(e)}") from None

        logger.debug("SubDL: API response status: %d", resp.status_code)
        if resp.status_code in (401, 403):
            error_msg = f"SubDL authentication failed: HTTP {resp.status_code}"
            logger.error(error_msg)
            raise ProviderAuthError(error_msg, status_code=resp.status_code)
        if resp.status_code == 429:
            error_msg = f"SubDL rate limit exceeded: HTTP {resp.status_code}"
            logger.warning(error_msg)
            raise ProviderRateLimitError(error_msg)
        if resp.status_code != 200:
            raise ProviderError(f"SubDL search returned HTTP {resp.status_code}")

        try:
            data = resp.json()
        except ValueError:
            raise ProviderError("SubDL search returned a non-JSON body") from None
        if not isinstance(data, dict):
            raise ProviderError("SubDL search returned an unexpected body")
        return data

    def search(self, query: VideoQuery) -> list[SubtitleResult]:
        if not self.session or not self.api_key:
            logger.warning(
                "SubDL: cannot search - session=%s, api_key=%s",
                self.session is not None,
                bool(self.api_key),
            )
            return []

        logger.debug("SubDL: searching for %s (languages: %s)", query.display_name, query.languages)
        params = self._build_params(query)
        if params is None:
            logger.warning("SubDL: insufficient search criteria - no IMDB ID and no title")
            return []

        logger.debug(
            "SubDL: API request params: %s", {k: v for k, v in params.items() if k != "api_key"}
        )
        data = self._fetch(params)
        if not data.get("status"):
            # status=false is SubDL's normal "can't find movie or tv" answer.
            error_msg = self._redact(data.get("error", "Unknown error"))
            logger.info("SubDL: API returned status=false, error: %s", error_msg)
            return []

        subtitles = data.get("subtitles") or []
        logger.debug("SubDL: API returned %d subtitles", len(subtitles))
        show_year = _show_year(data)
        results = []
        for sub in subtitles:
            if not isinstance(sub, dict):
                continue
            result = self._to_result(sub, query, show_year)
            if result is not None:
                results.append(result)

        logger.info("SubDL: found %d results", len(results))
        if results:
            logger.debug(
                "SubDL: top result - %s (score: %d, format: %s, language: %s)",
                results[0].filename,
                results[0].score,
                results[0].format.value,
                results[0].language,
            )
        return results

    def _to_result(
        self, sub: dict, query: VideoQuery, show_year: int | None
    ) -> SubtitleResult | None:
        """Map one ``subtitles[]`` entry; None when it is unusable for ``query``."""
        release_name = sub.get("release_name") or ""
        subtitle_name = sub.get("name") or ""

        path = _download_path(sub.get("url"))
        if not path:
            logger.debug("SubDL: skipping %r - no usable download url", release_name)
            return None
        language = _iso_language(sub)
        if not language:
            logger.debug("SubDL: skipping %r - unmapped language %r", release_name, sub.get("lang"))
            return None
        if not _covers_episode(sub, query):
            logger.debug("SubDL: skipping %r - does not cover the episode", release_name)
            return None

        fmt = _FORMAT_MAP.get(os.path.splitext(subtitle_name)[1].lower(), SubtitleFormat.UNKNOWN)
        exact_episode = _is_exact_episode(sub, query)

        matches = set()
        if query.imdb_id:
            matches.add("series" if query.is_episode else "title")
        if query.is_episode:
            sub_season = _positive_int(sub.get("season"))
            if sub_season and sub_season == query.season:
                matches.add("season")
            if exact_episode:
                matches.add("episode")
            elif query.episode is not None:
                # Fallback: parse episode from release_name
                ep_match = _EPISODE_RE.search(release_name)
                if ep_match and int(ep_match.group(1)) == query.episode:
                    matches.add("episode")
        if query.year and show_year == query.year:
            matches.add("year")
        sub_group = _parse_release_group(release_name)
        if sub_group and query.release_group:
            if sub_group.lower() == query.release_group.lower():
                matches.add("release_group")

        return SubtitleResult(
            provider_name=self.name,
            subtitle_id=_DOWNLOAD_PATH_RE.match(path).group(1),
            language=language,
            format=fmt,
            filename=subtitle_name,
            download_url=f"{DOWNLOAD_HOST}{path}",
            release_info=release_name,
            hearing_impaired=bool(sub.get("hi")),
            matches=matches,
            provider_data={
                "download_path": path,
                "exact_episode": exact_episode,
                "query_episode": query.episode,
                "query_season": query.season,
                "query_absolute_episode": query.absolute_episode,
            },
        )

    def download(self, result: SubtitleResult) -> bytes:
        if not self.session:
            raise RuntimeError("SubDL not initialized")

        path = result.provider_data.get("download_path") or ""
        if not _DOWNLOAD_PATH_RE.match(path):
            raise ProviderError("SubDL result carries no download path")
        url = f"{DOWNLOAD_HOST}{path}"

        # P1: Validate download URL against allowlist
        url_ok, url_err = validate_download_url(url, self.name)
        if not url_ok:
            raise ProviderError(f"SubDL download URL rejected: {url_err}")

        try:
            # P5: 50 MB streaming cap
            archive_content = _stream_download(
                self.session, url, timeout=self.timeout, provider_name=self.name
            )
        except Exception as e:
            raise RuntimeError(f"SubDL download failed: {self._redact(e)}") from None

        extracted = self._extract(archive_content)
        if not extracted:
            raise RuntimeError("No subtitle files found in SubDL archive")

        # Build query with episode context for correct archive file selection
        query = VideoQuery(
            episode=result.provider_data.get("query_episode"),
            season=result.provider_data.get("query_season"),
            absolute_episode=result.provider_data.get("query_absolute_episode"),
        )
        best = _pick_best_subtitle(
            extracted, query, exact_episode=bool(result.provider_data.get("exact_episode"))
        )
        if not best:
            raise ProviderNotApplicableError(
                f"SubDL archive holds no file for episode {query.episode} "
                f"({len(extracted)} subtitle files)"
            )

        best_name, best_content = best

        # Update result metadata with actual file info
        result.filename = best_name
        ext = os.path.splitext(best_name)[1].lower()
        result.format = _FORMAT_MAP.get(ext, SubtitleFormat.UNKNOWN)

        result.content = best_content
        logger.info("SubDL: downloaded %s (%d bytes)", result.filename, len(best_content))
        return best_content

    @staticmethod
    def _extract(archive_content: bytes) -> list[tuple[str, bytes]]:
        """Extract subtitle members, choosing the format by magic bytes, not extension."""
        if archive_content.startswith(_RAR_MAGIC):
            try:
                return extract_subtitles_from_rar(archive_content)
            except ImportError as e:
                raise RuntimeError(f"SubDL RAR archive needs rarfile: {e}") from e
        return extract_subtitles_from_zip(archive_content)
