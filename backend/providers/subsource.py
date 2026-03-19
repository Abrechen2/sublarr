"""Subsource subtitle provider.

Subsource.net offers a public JSON API for subtitle search and download.
No authentication required. Returns subtitles as ZIP archives.

API Base: https://subsource.net/api
Auth:     None required
Rate:     20 req / 60 s
"""

import logging

from archive_utils import extract_subtitles_from_zip
from providers import register_provider
from providers.base import SubtitleFormat, SubtitleProvider, SubtitleResult, VideoQuery
from providers.http_session import create_session

logger = logging.getLogger(__name__)

_API_BASE = "https://subsource.net/api"
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

_LANG_MAP = {
    "en": "english", "de": "german", "fr": "french", "es": "spanish",
    "it": "italian", "pt": "portuguese", "nl": "dutch", "pl": "polish",
    "ro": "romanian", "cs": "czech", "sk": "slovak", "hu": "hungarian",
    "hr": "croatian", "sr": "serbian", "bg": "bulgarian", "ru": "russian",
    "uk": "ukrainian", "tr": "turkish", "ar": "arabic", "fa": "farsi_persian",
    "zh": "chinese_simplified", "zh-hans": "chinese_simplified",
    "zh-hant": "chinese_traditional", "ja": "japanese", "ko": "korean",
    "vi": "vietnamese", "id": "indonesian", "he": "hebrew", "el": "greek",
    "sv": "swedish", "da": "danish", "no": "norwegian", "fi": "finnish",
    "th": "thai", "hi": "hindi", "bn": "bengali", "ms": "malay",
}

_FORMAT_MAP = {
    ".ass": SubtitleFormat.ASS, ".ssa": SubtitleFormat.SSA,
    ".srt": SubtitleFormat.SRT, ".vtt": SubtitleFormat.VTT,
}


@register_provider
class SubsourceProvider(SubtitleProvider):
    name = "subsource"
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
            max_retries=2, backoff_factor=1.0, timeout=self.timeout, user_agent=_BROWSER_UA,
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
            resp = self.session.get(f"{_API_BASE}/search", timeout=8)
            return (True, "OK") if resp.status_code in (200, 400) else (False, f"HTTP {resp.status_code}")
        except Exception as e:
            return False, str(e)

    def search(self, query: VideoQuery) -> list[SubtitleResult]:
        if not self.session:
            return []

        valid_langs = [lc for lc in (query.languages or ["en"]) if lc in _LANG_MAP]
        if not valid_langs:
            return []

        title = query.series_title or query.title
        if not title:
            return []

        payload: dict = {"title": title}
        if query.is_episode and query.season and query.episode:
            payload["season"] = str(query.season)
            payload["episode"] = str(query.episode)

        try:
            resp = self.session.post(f"{_API_BASE}/search", json=payload, timeout=self.timeout)
            if resp.status_code != 200:
                return []
            data = resp.json()
        except Exception as e:
            logger.debug("Subsource search error: %s", e)
            return []

        results = []
        for sub in (data.get("subs") or []):
            sub_lang_name = (sub.get("lang") or "").lower()
            matched_lang = next(
                (lc for lc in valid_langs if _LANG_MAP[lc] == sub_lang_name), None
            )
            if not matched_lang:
                continue
            link_name = sub.get("linkName") or ""
            release = sub.get("releaseName") or link_name
            if not link_name:
                continue
            results.append(SubtitleResult(
                provider_name=self.name,
                subtitle_id=link_name,
                language=matched_lang,
                format=SubtitleFormat.SRT,
                filename=f"{release}.srt",
                download_url=f"{_API_BASE}/getDownloadLink",
                release_info=release,
                matches={"series", "season", "episode"} if query.is_episode else {"title"},
                provider_data={"link_name": link_name},
            ))

        return results

    def download(self, result: SubtitleResult) -> bytes:
        if not self.session:
            raise RuntimeError("Subsource not initialized")

        link_name = (result.provider_data or {}).get("link_name") or result.subtitle_id
        try:
            resp = self.session.post(
                f"{_API_BASE}/getDownloadLink", json={"link": link_name}, timeout=self.timeout,
            )
            if resp.status_code != 200:
                raise RuntimeError(f"Subsource download link failed: HTTP {resp.status_code}")
            data = resp.json()
            dl_url = data.get("link") or data.get("downloadLink") or ""
            if not dl_url:
                raise RuntimeError("Subsource: no download URL in response")
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"Subsource download link error: {e}") from e

        try:
            resp2 = self.session.get(dl_url, timeout=self.timeout)
            if resp2.status_code != 200:
                raise RuntimeError(f"Subsource file download failed: HTTP {resp2.status_code}")
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"Subsource file download error: {e}") from e

        content = resp2.content
        if content[:2] == b"PK":
            try:
                entries = extract_subtitles_from_zip(content)
                if entries:
                    name, content = entries[0]
                    result.filename = name
                    ext = name.lower().rsplit(".", 1)[-1] if "." in name else ""
                    result.format = _FORMAT_MAP.get(f".{ext}", SubtitleFormat.SRT)
            except Exception as e:
                raise RuntimeError(f"Subsource: archive error: {e}") from e

        result.content = content
        return content
