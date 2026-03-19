"""YIFY Subtitles provider — movies only, IMDB-based JSON API."""

import logging

from archive_utils import extract_subtitles_from_zip
from providers import register_provider
from providers.base import SubtitleFormat, SubtitleProvider, SubtitleResult, VideoQuery
from providers.http_session import create_session

logger = logging.getLogger(__name__)

_BASE_URL = "https://yifysubtitles.ch"
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

_YIFY_LANG_TO_ISO = {
    "english": "en",
    "german": "de",
    "french": "fr",
    "spanish": "es",
    "italian": "it",
    "portuguese": "pt",
    "dutch": "nl",
    "polish": "pl",
    "romanian": "ro",
    "czech": "cs",
    "slovak": "sk",
    "hungarian": "hu",
    "croatian": "hr",
    "serbian": "sr",
    "bulgarian": "bg",
    "russian": "ru",
    "ukrainian": "uk",
    "turkish": "tr",
    "arabic": "ar",
    "chinese": "zh",
    "chinese simplified": "zh-hans",
    "chinese traditional": "zh-hant",
    "japanese": "ja",
    "korean": "ko",
    "vietnamese": "vi",
    "indonesian": "id",
    "hebrew": "he",
    "greek": "el",
    "swedish": "sv",
    "danish": "da",
    "norwegian": "no",
    "finnish": "fi",
    "thai": "th",
    "hindi": "hi",
    "farsi/persian": "fa",
    "persian": "fa",
}

_FORMAT_MAP = {
    ".ass": SubtitleFormat.ASS,
    ".ssa": SubtitleFormat.SSA,
    ".srt": SubtitleFormat.SRT,
    ".vtt": SubtitleFormat.VTT,
}


@register_provider
class YifySubtitlesProvider(SubtitleProvider):
    name = "yifysubtitles"
    languages = set(_YIFY_LANG_TO_ISO.values())
    config_fields = []
    rate_limit = (20, 60)
    timeout = 15
    max_retries = 2
    movies_only = True

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.session = None

    def initialize(self):
        self.session = create_session(
            max_retries=2,
            backoff_factor=1.0,
            timeout=self.timeout,
            user_agent=_BROWSER_UA,
        )

    def terminate(self):
        if self.session:
            self.session.close()
            self.session = None

    def health_check(self) -> tuple[bool, str]:
        if not self.session:
            return False, "Not initialized"
        try:
            resp = self.session.get(_BASE_URL, timeout=8)
            return (True, "OK") if resp.status_code == 200 else (False, f"HTTP {resp.status_code}")
        except Exception as e:
            return False, str(e)

    def search(self, query: VideoQuery) -> list[SubtitleResult]:
        if not self.session:
            return []
        # Movies only — skip if it's a TV episode
        if query.is_episode:
            return []
        imdb_id = getattr(query, "imdb_id", None)
        if not imdb_id:
            logger.debug("YifySubtitles: no IMDB ID, skipping (title: %s)", query.title)
            return []
        if not imdb_id.startswith("tt"):
            imdb_id = f"tt{imdb_id}"
        try:
            resp = self.session.get(
                f"{_BASE_URL}/movie-imdb/{imdb_id}",
                headers={"Accept": "application/json"},
                timeout=self.timeout,
            )
            if resp.status_code != 200:
                return []
            data = resp.json()
        except Exception as e:
            logger.debug("YifySubtitles: API error: %s", e)
            return []

        search_langs = set(query.languages or ["en"])
        results = []
        for sub in data.get("subtitles") or []:
            yify_lang = (sub.get("lang") or "").lower().strip()
            iso_lang = _YIFY_LANG_TO_ISO.get(yify_lang)
            if not iso_lang or iso_lang not in search_langs:
                continue
            url_path = sub.get("url") or ""
            if not url_path:
                continue
            dl_url = f"{_BASE_URL}{url_path}" if url_path.startswith("/") else url_path
            sub_id = url_path.rstrip("/").split("/")[-1]
            results.append(
                SubtitleResult(
                    provider_name=self.name,
                    subtitle_id=sub_id,
                    language=iso_lang,
                    format=SubtitleFormat.SRT,
                    filename=f"{sub_id}.srt",
                    download_url=dl_url,
                    release_info=sub.get("release") or query.title or "",
                    matches={"title"},
                    provider_data={"rating": sub.get("rating") or 0},
                )
            )
        return results

    def download(self, result: SubtitleResult) -> bytes:
        if not self.session:
            raise RuntimeError("YifySubtitles not initialized")
        try:
            resp = self.session.get(
                result.download_url,
                headers={"Referer": _BASE_URL},
                timeout=self.timeout,
            )
            if resp.status_code != 200:
                raise RuntimeError(f"YifySubtitles download failed: HTTP {resp.status_code}")
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"YifySubtitles download error: {e}") from e

        content = resp.content
        if content[:2] == b"PK":
            try:
                entries = extract_subtitles_from_zip(content)
                if entries:
                    name, content = entries[0]
                    result.filename = name
                    ext = f".{name.lower().rsplit('.', 1)[-1]}" if "." in name else ""
                    result.format = _FORMAT_MAP.get(ext, SubtitleFormat.SRT)
            except Exception as e:
                raise RuntimeError(f"YifySubtitles: archive error: {e}") from e

        result.content = content
        return content
