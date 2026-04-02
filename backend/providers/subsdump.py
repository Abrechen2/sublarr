"""SubsDump provider — self-hosted Subscene archive API.

Searches a local SubsDump instance (https://github.com/D3lphi3r/SubsDump)
powered by a Subscene dump database. Requires a running SubsDump backend
and the subtitle dump imported into its MariaDB.

No rate limiting: SubsDump is a local service.
License: GPL-3.0
"""

import logging

from archive_utils import extract_subtitles_from_zip
from providers import register_provider
from providers.base import (
    ProviderError,
    SubtitleFormat,
    SubtitleProvider,
    SubtitleResult,
    VideoQuery,
)
from providers.http_session import create_session
from security_utils import validate_download_url

logger = logging.getLogger(__name__)

# ISO 639-1 → SubsDump language name
_LANG_MAP: dict[str, str] = {
    "ar": "arabic",
    "bn": "bengali",
    "zh": "chinese-bg-code",
    "hr": "croatian",
    "cs": "czech",
    "da": "danish",
    "nl": "dutch",
    "en": "english",
    "fa": "farsi_persian",
    "fi": "finnish",
    "fr": "french",
    "de": "german",
    "el": "greek",
    "he": "hebrew",
    "hi": "hindi",
    "hu": "hungarian",
    "id": "indonesian",
    "it": "italian",
    "ja": "japanese",
    "ko": "korean",
    "ml": "malayalam",
    "no": "norwegian",
    "pl": "polish",
    "pt": "portuguese",
    "ro": "romanian",
    "ru": "russian",
    "es": "spanish",
    "sv": "swedish",
    "th": "thai",
    "tr": "turkish",
    "ur": "urdu",
    "vi": "vietnamese",
}

_SUBTITLE_EXTENSIONS = {".ass", ".srt", ".ssa", ".vtt", ".sub"}

_FORMAT_MAP = {
    ".ass": SubtitleFormat.ASS,
    ".ssa": SubtitleFormat.SSA,
    ".srt": SubtitleFormat.SRT,
    ".vtt": SubtitleFormat.VTT,
}


def _normalize_url(url: str) -> str:
    return url.rstrip("/")


def _lang_to_api_name(lang_code: str) -> str | None:
    return _LANG_MAP.get(lang_code.lower())


def _is_hi(item: dict) -> bool:
    text = " ".join(
        [
            str(item.get("comment") or ""),
            str(item.get("releases") or ""),
            str(item.get("fileLink") or ""),
        ]
    ).lower()
    non_hi = ["hi remove", "non hi", "non-hi", "non-sdh", "nonsdh", "sdh remove"]
    if any(t in text for t in non_hi):
        return False
    hi = ["_hi_", " hi ", ".hi.", "sdh", "hearing impaired", "hearing-impaired"]
    return any(t in text for t in hi)


def _is_forced(item: dict) -> bool:
    text = " ".join(
        [
            str(item.get("comment") or ""),
            str(item.get("releases") or ""),
        ]
    ).lower()
    return any(t in text for t in ("forced", "foreign"))


def _format_from_filename(name: str) -> SubtitleFormat:
    ext = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return _FORMAT_MAP.get(ext, SubtitleFormat.UNKNOWN)


def _safe_release(query: VideoQuery) -> str:
    """Build a release name string for scoring against the dump."""
    if query.is_episode:
        parts = [query.series_title or query.title]
        if query.season is not None and query.episode is not None:
            parts.append(f"S{query.season:02d}E{query.episode:02d}")
        if query.release_group:
            parts.append(query.release_group)
        return ".".join(p for p in parts if p).strip(".")
    parts = [query.title]
    if query.year:
        parts.append(str(query.year))
    if query.release_group:
        parts.append(query.release_group)
    return ".".join(p for p in parts if p).strip(".")


@register_provider
class SubsDumpProvider(SubtitleProvider):
    """Self-hosted SubsDump subtitle archive provider.

    Requires:
    - A running SubsDump backend (https://github.com/D3lphi3r/SubsDump)
    - The Subscene dump imported into SubsDump's MariaDB
    - IMDB ID on the video (required for accurate search)
    """

    name = "subsdump"
    languages = set(_LANG_MAP.keys())

    config_fields = [
        {
            "key": "subsdump_url",
            "label": "SubsDump URL",
            "type": "text",
            "required": True,
            "default": "http://192.168.178.195",
        },
        {
            "key": "subsdump_api_key",
            "label": "SubsDump API Key",
            "type": "password",
            "required": False,
            "default": "",
        },
    ]

    rate_limit = (0, 0)
    timeout = 30

    def __init__(self, **config):
        super().__init__(**config)
        self._session = None

    def initialize(self):
        from config import get_settings

        settings = get_settings()
        url = (
            self.config.get("subsdump_url")
            or getattr(settings, "subsdump_url", "")
            or "http://192.168.178.195"
        )
        api_key = self.config.get("subsdump_api_key") or getattr(settings, "subsdump_api_key", "")

        self._base = _normalize_url(url) + "/api/v1"
        self._session = create_session()
        self._session.headers.update({"Accept": "application/json"})
        if api_key:
            self._session.headers["X-API-Key"] = api_key

    def terminate(self):
        if self._session:
            self._session.close()
            self._session = None

    def health_check(self) -> tuple[bool, str]:
        try:
            r = self._session.get(self._base.replace("/api/v1", "/healthz"), timeout=5)
            r.raise_for_status()
            data = r.json()
            if data.get("ok"):
                return True, "OK"
            return False, str(data)
        except Exception as exc:
            return False, str(exc)

    def search(self, query: VideoQuery) -> list[SubtitleResult]:
        if not query.imdb_id:
            logger.debug("subsdump: no imdb_id — skipping")
            return []

        imdb = query.imdb_id
        if imdb.isdigit():
            imdb = "tt" + imdb

        release = _safe_release(query)
        results: list[SubtitleResult] = []

        for lang_code in query.languages:
            lang_name = _lang_to_api_name(lang_code)
            if not lang_name:
                logger.debug("subsdump: unsupported language %r", lang_code)
                continue

            params: dict = {
                "imdb": imdb,
                "lang": lang_name,
                "release": release,
                "limit": 50,
            }
            if query.is_episode:
                if query.season is not None:
                    params["season"] = query.season
                if query.episode is not None:
                    params["episode"] = query.episode

            try:
                r = self._session.get(
                    f"{self._base}/subtitles/search",
                    params=params,
                    timeout=self.timeout,
                )
                r.raise_for_status()
                data = r.json() or {}
            except Exception as exc:
                logger.warning(
                    "subsdump: search failed imdb=%s lang=%s: %s",
                    imdb,
                    lang_name,
                    exc,
                )
                continue

            for item in data.get("results") or []:
                sub_id = item.get("id")
                dl = item.get("download_url") or ""
                if not sub_id or not dl:
                    continue

                # Build absolute download URL
                if not dl.startswith("http"):
                    base_root = self._base.replace("/api/v1", "")
                    dl = base_root.rstrip("/") + "/" + dl.lstrip("/")

                releases = item.get("releases") or []
                if not isinstance(releases, list):
                    releases = [str(releases)] if releases else []
                release_info = ", ".join(str(r).strip() for r in releases if str(r).strip())

                hi = _is_hi(item)
                forced = _is_forced(item)

                result = SubtitleResult(
                    provider_name=self.name,
                    subtitle_id=str(sub_id),
                    language=lang_code,
                    format=SubtitleFormat.UNKNOWN,  # resolved on download
                    filename=item.get("fileLink") or "",
                    download_url=dl,
                    release_info=release_info,
                    hearing_impaired=hi,
                    forced=forced,
                    provider_data={
                        "item": item,
                        "season": item.get("season"),
                        "episode": item.get("episode"),
                    },
                )
                results.append(result)

        return results

    def download(self, result: SubtitleResult) -> bytes:
        if not result.download_url:
            raise ProviderError(f"subsdump: no download_url for {result.subtitle_id}")

        # P1: Validate download URL against allowed domains before fetching
        url_ok, url_err = validate_download_url(result.download_url, self.name)
        if not url_ok:
            raise ProviderError(f"subsdump: download URL rejected: {url_err}")

        try:
            r = self._session.get(result.download_url, timeout=60)
            r.raise_for_status()
        except Exception as exc:
            raise ProviderError(f"subsdump: download failed: {exc}") from exc

        # SubsDump returns ZIP archives containing the actual subtitle file
        try:
            files = extract_subtitles_from_zip(r.content)
        except Exception:
            # Not a ZIP — might already be a raw subtitle
            return r.content

        if not files:
            raise ProviderError(
                f"subsdump: no subtitle file found in archive for {result.subtitle_id}"
            )

        # Prefer ASS/SSA, fall back to SRT
        for filename, content in files:
            ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
            if ext in (".ass", ".ssa"):
                result.format = _FORMAT_MAP.get(ext, SubtitleFormat.ASS)
                return content

        filename, content = files[0]
        ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        result.format = _FORMAT_MAP.get(ext, SubtitleFormat.UNKNOWN)
        return content
