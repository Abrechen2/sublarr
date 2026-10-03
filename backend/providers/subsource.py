"""Subsource subtitle provider.

Subsource.net offers a public JSON API for subtitle search and download.
Requires an API key. Returns subtitles as ZIP archives.
Contract: https://subsource.net/api-docs (verified 2026-09-15).

API Base: https://api.subsource.net/api/v1
Auth:     X-API-Key header
Rate:     20 req / 60 s
"""

import logging
from typing import ClassVar

from guessit import guessit

from archive_utils import extract_subtitles_from_zip
from providers import _stream_download, register_provider
from providers.base import (
    ProviderAuthError,
    ProviderError,
    SubtitleFormat,
    SubtitleProvider,
    SubtitleResult,
    VideoQuery,
)
from providers.http_session import create_session
from security_utils import validate_download_url

logger = logging.getLogger(__name__)

_API_BASE = "https://api.subsource.net/api/v1"
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

_LANG_MAP = {
    "en": "english",
    "de": "german",
    "fr": "french",
    "es": "spanish",
    "it": "italian",
    "pt": "portuguese",
    "nl": "dutch",
    "pl": "polish",
    "ro": "romanian",
    "cs": "czech",
    "sk": "slovak",
    "hu": "hungarian",
    "hr": "croatian",
    "sr": "serbian",
    "bg": "bulgarian",
    "ru": "russian",
    "uk": "ukrainian",
    "tr": "turkish",
    "ar": "arabic",
    "fa": "farsi_persian",
    "zh": "chinese_simplified",
    "zh-hans": "chinese_simplified",
    "zh-hant": "chinese_traditional",
    "ja": "japanese",
    "ko": "korean",
    "vi": "vietnamese",
    "id": "indonesian",
    "he": "hebrew",
    "el": "greek",
    "sv": "swedish",
    "da": "danish",
    "no": "norwegian",
    "fi": "finnish",
    "th": "thai",
    "hi": "hindi",
    "bn": "bengali",
    "ms": "malay",
}

_FORMAT_MAP = {
    ".ass": SubtitleFormat.ASS,
    ".ssa": SubtitleFormat.SSA,
    ".srt": SubtitleFormat.SRT,
    ".vtt": SubtitleFormat.VTT,
}


@register_provider
class SubsourceProvider(SubtitleProvider):
    name = "subsource"
    languages = set(_LANG_MAP.keys())
    config_fields = [
        {"key": "subsource_api_key", "label": "API Key", "type": "password", "required": True},
    ]
    rate_limits: ClassVar[dict[str, dict[str, int]]] = {
        "free": {"second": 1, "hour": 1800, "day": 7200},
    }
    rate_limit = (20, 60)
    timeout = 15
    max_retries = 2

    def __init__(self, api_key: str = "", **kwargs):
        super().__init__(**kwargs)
        self.api_key = api_key.strip()
        self.session = None

    def initialize(self):
        self.session = create_session(
            max_retries=2, backoff_factor=1.0, timeout=self.timeout, user_agent=_BROWSER_UA
        )
        self.session.headers.update({"Accept": "application/json"})

    def terminate(self):
        if self.session:
            self.session.close()
            self.session = None

    def _api_get(self, path: str, params: dict) -> list[dict]:
        if not self.api_key:
            raise ProviderAuthError("SubSource API key not configured")
        resp = self.session.get(
            f"{_API_BASE}/{path}",
            params=params,
            headers={"X-API-Key": self.api_key},
            timeout=self.timeout,
            allow_redirects=False,
        )
        # RetryingSession propagates auth and rate-limit exceptions. Do not
        # hide endpoint/schema failures as a successful search with no results.
        if resp.status_code != 200:
            raise ProviderError(f"SubSource {path} returned HTTP {resp.status_code}")
        data = resp.json()
        if (
            not isinstance(data, dict)
            or data.get("success") is not True
            or not isinstance(data.get("data"), list)
        ):
            raise ProviderError(f"SubSource {path} returned an invalid response")
        return data["data"]

    def health_check(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, "API key not configured"
        if not self.session:
            return False, "Not initialized"
        try:
            self._api_get("movies/search", {"searchType": "text", "q": "test"})
            return True, "OK"
        except Exception as exc:
            return False, str(exc)

    def search(self, query: VideoQuery) -> list[SubtitleResult]:
        if not self.session:
            return []
        valid_langs = [lc for lc in (query.languages or ["en"]) if lc in _LANG_MAP]
        title = query.series_title or query.title
        if not valid_langs or not title:
            return []
        params = {"type": "series" if query.is_episode else "movie"}
        if query.is_episode:
            params["season"] = query.season
        elif query.year:
            params["year"] = query.year
        if query.imdb_id:
            search_params = {**params, "searchType": "imdb", "imdb": query.imdb_id}
        else:
            search_params = {**params, "searchType": "text", "q": title}
        movies = self._api_get("movies/search", search_params)
        if not movies and query.imdb_id:
            movies = self._api_get("movies/search", {**params, "searchType": "text", "q": title})
        movie = next((m for m in movies if _matches_movie(m, query)), None)
        if movie is None:
            return []

        results = []
        for language in valid_langs:
            params = {"movieId": movie["movieId"], "language": _LANG_MAP[language], "limit": 100}
            if query.is_episode:
                params.update(seasonNumber=query.season, episodeNumber=query.episode)
            for sub in self._api_get("subtitles", params):
                if (sub.get("language") or "").lower() != _LANG_MAP[language]:
                    continue
                subtitle_id = str(sub.get("subtitleId") or "")
                if not subtitle_id.isdecimal():
                    continue
                releases = sub.get("releaseInfo") or []
                if isinstance(releases, str):
                    releases = [releases]
                matches = {"series", "season"} if query.is_episode else {"title"}
                if query.is_episode:
                    # The API may return season packs. Keep their context so
                    # download selects the requested episode, never entries[0].
                    if not any(
                        _matches_episode(release, query.season, query.episode, allow_pack=True)
                        for release in releases
                    ):
                        continue
                    if any(
                        _matches_episode(release, query.season, query.episode)
                        for release in releases
                    ):
                        matches.add("episode")
                release = " / ".join(releases)
                results.append(
                    SubtitleResult(
                        provider_name=self.name,
                        subtitle_id=subtitle_id,
                        language=language,
                        format=SubtitleFormat.UNKNOWN,
                        filename=release or subtitle_id,
                        download_url=f"{_API_BASE}/subtitles/{subtitle_id}/download",
                        release_info=release,
                        matches=matches,
                        hearing_impaired=sub.get("hearingImpaired") is True,
                        forced=sub.get("foreignParts") is True,
                        provider_data={"season": query.season, "episode": query.episode},
                    )
                )
        return results

    def download(self, result: SubtitleResult) -> bytes:
        if not self.session:
            raise RuntimeError("SubSource not initialized")
        if not self.api_key:
            raise ProviderAuthError("SubSource API key not configured")
        # Old linkName history ids cannot be guessed into new numeric ids.
        if not result.subtitle_id.isdecimal():
            raise ProviderError(
                "SubSource requires a new search to resolve this legacy subtitle id"
            )
        url = f"{_API_BASE}/subtitles/{result.subtitle_id}/download"
        url_ok, url_err = validate_download_url(url, self.name)
        if not url_ok:
            raise ProviderError(f"SubSource download URL rejected: {url_err}")
        archive = _stream_download(
            self.session,
            url,
            timeout=self.timeout,
            provider_name=self.name,
            headers={"X-API-Key": self.api_key},
            allow_redirects=False,
        )
        if not archive.startswith(b"PK"):
            raise ProviderError("SubSource download did not return a subtitle ZIP archive")
        entries = extract_subtitles_from_zip(archive)
        season = result.provider_data.get("season")
        episode = result.provider_data.get("episode")
        if episode is not None:
            matched = [e for e in entries if _matches_episode(e[0], season, episode)]
            if matched:
                entries = matched
            elif len(entries) != 1 or "episode" not in result.matches:
                raise ProviderError("SubSource archive contains no matching episode")
            else:
                # A generic single filename can inherit a proven release match;
                # an explicitly different episode cannot.
                parsed = guessit(entries[0][0], options={"type": "episode"})
                if parsed.get("episode") is not None or parsed.get("season") is not None:
                    raise ProviderError("SubSource archive contains a different episode")
        if len(entries) != 1:
            raise ProviderError("SubSource archive has no unambiguous subtitle file")
        name, content = entries[0]
        result.filename = name
        result.format = _FORMAT_MAP.get(
            "." + name.rsplit(".", 1)[-1].lower(), SubtitleFormat.UNKNOWN
        )
        result.content = content
        return content


def _matches_movie(movie: dict, query: VideoQuery) -> bool:
    if not movie.get("movieId"):
        return False
    if movie.get("type") != ("series" if query.is_episode else "movie"):
        return False
    if query.is_episode and movie.get("season") is not None and movie["season"] != query.season:
        return False
    if not query.is_episode and query.year and str(movie.get("releaseYear")) != str(query.year):
        return False
    if query.imdb_id and movie.get("imdbId"):
        return movie["imdbId"] == query.imdb_id

    def normalise(text: str) -> str:
        return "".join(c for c in text.casefold() if c.isalnum())

    return normalise(query.series_title or query.title) in {
        normalise(movie.get("title") or ""),
        normalise(movie.get("alternateTitle") or ""),
    }


def _matches_episode(release: str, season: int, episode: int, *, allow_pack: bool = False) -> bool:
    parsed = guessit(release, options={"type": "episode"})
    if parsed.get("season") != season:
        return False
    return parsed.get("episode") == episode or (allow_pack and parsed.get("episode") is None)
