"""Titlovi subtitle provider — Balkan languages.

Titlovi.com specialises in Croatian, Serbian, Bosnian, Slovenian and
Macedonian subtitles. Uses the unofficial Kodi API endpoint.

API Base: https://kodi.titlovi.com/api/subtitles
Auth:     None required
Rate:     20 req / 60 s
License:  GPL-3.0
"""

import logging

from archive_utils import extract_subtitles_from_zip
from providers import register_provider
from providers.base import (
    SubtitleFormat,
    SubtitleProvider,
    SubtitleResult,
    VideoQuery,
)
from providers.http_session import create_session

logger = logging.getLogger(__name__)

_API_BASE = "https://kodi.titlovi.com/api/subtitles"
_DOWNLOAD_BASE = "https://titlovi.com/download"
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

_LANG_MAP = {
    "hr": "Croatian",
    "sr": "Serbian",
    "bs": "Bosnian",
    "sl": "Slovenian",
    "mk": "Macedonian",
}

_FORMAT_MAP = {
    ".ass": SubtitleFormat.ASS,
    ".ssa": SubtitleFormat.SSA,
    ".srt": SubtitleFormat.SRT,
    ".vtt": SubtitleFormat.VTT,
}


@register_provider
class TitloviProvider(SubtitleProvider):
    """Titlovi Balkan subtitle provider.

    Covers Croatian, Serbian, Bosnian, Slovenian, and Macedonian.
    No authentication required.
    """

    name = "titlovi"
    languages = set(_LANG_MAP.keys())
    config_fields = []
    rate_limit = (20, 60)
    timeout = 15
    max_retries = 2

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
        self.session.headers.update({"Accept": "application/json"})

    def terminate(self):
        if self.session:
            self.session.close()
            self.session = None

    def health_check(self) -> tuple[bool, str]:
        if not self.session:
            return False, "Not initialized"
        try:
            resp = self.session.get(
                f"{_API_BASE}/search",
                params={"title": "test", "lang": "Croatian"},
                timeout=8,
            )
            return (
                (True, "OK")
                if resp.status_code in (200, 400)
                else (False, f"HTTP {resp.status_code}")
            )
        except Exception as e:
            return False, str(e)

    def search(self, query: VideoQuery) -> list[SubtitleResult]:
        if not self.session:
            return []

        search_langs = query.languages or []
        valid_langs = [lc for lc in search_langs if lc in _LANG_MAP]
        if not valid_langs:
            return []

        title = query.series_title or query.title
        if not title:
            return []

        logger.debug("Titlovi: searching '%s' (langs: %s)", title, valid_langs)

        results = []

        for lang_code in valid_langs:
            lang_name = _LANG_MAP[lang_code]
            params: dict = {"title": title, "lang": lang_name}
            if query.is_episode and query.season and query.episode:
                params["season"] = query.season
                params["episode"] = query.episode

            try:
                resp = self.session.get(
                    f"{_API_BASE}/search",
                    params=params,
                    timeout=self.timeout,
                )
                if resp.status_code != 200:
                    logger.debug("Titlovi: HTTP %d for lang=%s", resp.status_code, lang_code)
                    continue
                data = resp.json()
            except Exception as e:
                logger.debug("Titlovi: search error (lang=%s): %s", lang_code, e)
                continue

            subs = data.get("subtitles") or (data if isinstance(data, list) else [])
            for sub in subs[:8]:
                sub_id = str(sub.get("id") or "")
                dl_url = sub.get("download") or f"{_DOWNLOAD_BASE}/{sub_id}"
                release = sub.get("release") or sub.get("title") or title
                if not sub_id:
                    continue
                results.append(
                    SubtitleResult(
                        provider_name=self.name,
                        subtitle_id=sub_id,
                        language=lang_code,
                        format=SubtitleFormat.SRT,
                        filename=f"{release}.srt",
                        download_url=dl_url,
                        release_info=release,
                        matches={"series", "season", "episode"} if query.is_episode else {"title"},
                    )
                )

        logger.info("Titlovi: found %d results", len(results))
        return results

    def download(self, result: SubtitleResult) -> bytes:
        if not self.session:
            raise RuntimeError("Titlovi not initialized")

        try:
            resp = self.session.get(result.download_url, timeout=self.timeout)
            if resp.status_code != 200:
                raise RuntimeError(f"Titlovi download failed: HTTP {resp.status_code}")
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"Titlovi download error: {e}") from e

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
                raise RuntimeError(f"Titlovi: archive extraction failed: {e}") from e

        result.content = content
        logger.info("Titlovi: downloaded %s (%d bytes)", result.filename, len(content))
        return content
