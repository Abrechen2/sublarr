"""Titlovi subtitle provider — Balkan languages.

Titlovi.com specialises in Croatian, Serbian, Bosnian, Slovenian and
Macedonian subtitles. Uses the Kodi addon API, which requires a titlovi.com
account with API access enabled: username/password are exchanged for a
token via ``/gettoken`` and the token + user id are sent with every search
(#191). Without credentials the provider disables itself at startup.

API Base: https://kodi.titlovi.com/api/subtitles
Auth:     POST /gettoken?username=&password=&json=true -> {Token, UserId, ExpirationDate}
Search:   GET  /search?query=&lang=Hrvatski|Srpski&season=&token=&userid=&json=true
Rate:     20 req / 60 s
License:  GPL-3.0
"""

import logging
import re
from datetime import UTC, datetime, timedelta

from werkzeug.utils import secure_filename as _secure_filename

from archive_utils import extract_subtitles_from_zip
from providers import _stream_download, register_provider
from providers.base import (
    ProviderError,
    ProviderRateLimitError,
    SubtitleFormat,
    SubtitleProvider,
    SubtitleResult,
    VideoQuery,
)
from providers.http_session import create_session
from security_utils import validate_download_url

logger = logging.getLogger(__name__)

_API_BASE = "https://kodi.titlovi.com/api/subtitles"
_TOKEN_URL = f"{_API_BASE}/gettoken"
_SEARCH_URL = f"{_API_BASE}/search"
_MAX_PAGES = 3
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# ISO 639-1 -> Titlovi API language names (the API speaks native names,
# not English ones — "Croatian" etc. return nothing).
_LANG_MAP = {
    "hr": "Hrvatski",
    "sr": "Srpski",
    "bs": "Bosanski",
    "sl": "Slovenski",
    "mk": "Makedonski",
}
# Reverse map for parsing results; "Cirilica" is Serbian in Cyrillic script.
_LANG_REVERSE = {v: k for k, v in _LANG_MAP.items()}
_LANG_REVERSE["Cirilica"] = "sr"

_FORMAT_MAP = {
    ".ass": SubtitleFormat.ASS,
    ".ssa": SubtitleFormat.SSA,
    ".srt": SubtitleFormat.SRT,
    ".vtt": SubtitleFormat.VTT,
}

# .NET serialises fractional seconds with up to 7 digits; fromisoformat
# accepts at most 6. Trim before parsing.
_ISO_FRACTION_RE = re.compile(r"(\.\d{6})\d+")


def _parse_expiration(value) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(_ISO_FRACTION_RE.sub(r"\1", value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


@register_provider
class TitloviProvider(SubtitleProvider):
    """Titlovi Balkan subtitle provider.

    Covers Croatian, Serbian, Bosnian, Slovenian, and Macedonian.
    Requires a titlovi.com account with API access (#191).
    """

    name = "titlovi"
    languages = set(_LANG_MAP.keys())
    config_fields = [
        {
            "key": "titlovi_username",
            "label": "Username",
            "type": "text",
            "required": True,
            "description": "titlovi.com-Account mit API-Zugang (im Profil freischalten)",
        },
        {
            "key": "titlovi_password",
            "label": "Password",
            "type": "password",
            "required": True,
        },
    ]
    rate_limit = (20, 60)
    timeout = 15
    max_retries = 2

    def __init__(self, username: str = "", password: str = "", **kwargs):
        super().__init__(**kwargs)
        self.username = username
        self.password = password
        self.session = None
        self._token: str | None = None
        self._user_id: int | None = None
        self._token_expires: datetime | None = None

    def initialize(self):
        if not (self.username and self.password):
            logger.info(
                "Titlovi: no credentials configured — provider disabled "
                "(titlovi.com account with API access required)"
            )
            return
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
        self._token = None
        self._user_id = None
        self._token_expires = None

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------
    def _ensure_token(self) -> bool:
        """Ensure a usable API token, logging in when absent or expired.

        A token without a parseable expiry is trusted until the API answers
        401 (the search path re-logs-in once on that).
        """
        if self._token and (
            self._token_expires is None
            or datetime.now(UTC) < self._token_expires - timedelta(seconds=60)
        ):
            return True
        return self._login()

    def _login(self) -> bool:
        if not self.session:
            return False
        try:
            resp = self.session.post(
                _TOKEN_URL,
                params={"username": self.username, "password": self.password, "json": True},
                timeout=self.timeout,
            )
        except Exception as e:
            logger.warning("Titlovi: login request failed: %s", e)
            return False
        if resp.status_code == 429:
            raise ProviderRateLimitError("Titlovi login rate limited", retry_after=60)
        if resp.status_code in (401, 403):
            logger.warning(
                "Titlovi: login rejected (HTTP %d) — check username/password and "
                "that API access is enabled for the account",
                resp.status_code,
            )
            self._token = None
            return False
        if resp.status_code != 200:
            logger.warning("Titlovi: login failed: HTTP %d", resp.status_code)
            return False
        try:
            data = resp.json()
        except Exception as e:
            logger.warning("Titlovi: login response unreadable: %s", e)
            return False
        token = data.get("Token") if isinstance(data, dict) else None
        if not token:
            logger.warning("Titlovi: login response carried no token")
            return False
        self._token = token
        self._user_id = data.get("UserId")
        self._token_expires = _parse_expiration(data.get("ExpirationDate"))
        logger.debug("Titlovi: obtained API token (expires %s)", self._token_expires)
        return True

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------
    def health_check(self) -> tuple[bool, str]:
        if not self.session:
            return False, "Not initialized (username/password required)"
        try:
            if self._ensure_token():
                return True, "OK"
            return False, "Login failed — check username/password and API access"
        except ProviderRateLimitError:
            return False, "Rate limited"
        except Exception as e:
            return False, str(e)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------
    def search(self, query: VideoQuery) -> list[SubtitleResult]:
        if not self.session:
            return []

        valid_langs = [lc for lc in (query.languages or []) if lc in _LANG_MAP]
        if not valid_langs:
            return []

        title = query.series_title or query.title
        if not title:
            return []

        if not self._ensure_token():
            logger.warning("Titlovi: skipping search — no API token")
            return []

        logger.debug("Titlovi: searching '%s' (langs: %s)", title, valid_langs)

        params: dict = {
            "query": title,
            "lang": "|".join(_LANG_MAP[lc] for lc in valid_langs),
            "json": True,
        }
        if query.is_episode and query.season:
            params["season"] = query.season
        if query.imdb_id:
            params["imdbID"] = query.imdb_id

        raw_results = self._fetch_all_pages(params)

        results = []
        for sub in raw_results:
            result = self._parse_result(sub, query)
            if result:
                results.append(result)

        logger.info("Titlovi: found %d results", len(results))
        return results

    def _fetch_all_pages(self, params: dict) -> list[dict]:
        """Fetch up to ``_MAX_PAGES`` result pages; re-login once on 401."""
        collected: list[dict] = []
        page = 1
        relogged_in = False
        while page <= _MAX_PAGES:
            request_params = {
                **params,
                "token": self._token,
                "userid": self._user_id,
            }
            if page > 1:
                request_params["pg"] = page
            try:
                resp = self.session.get(_SEARCH_URL, params=request_params, timeout=self.timeout)
            except Exception as e:
                logger.debug("Titlovi: search request failed: %s", e)
                break
            if resp.status_code == 429:
                raise ProviderRateLimitError("Titlovi rate limited", retry_after=60)
            if resp.status_code in (401, 403):
                if relogged_in or not self._login():
                    logger.warning(
                        "Titlovi: search unauthorized (HTTP %d) even after re-login",
                        resp.status_code,
                    )
                    break
                relogged_in = True
                continue  # retry same page with the fresh token
            if resp.status_code != 200:
                logger.debug("Titlovi: search HTTP %d", resp.status_code)
                break
            try:
                data = resp.json()
            except Exception as e:
                logger.debug("Titlovi: search response unreadable: %s", e)
                break
            page_results = data.get("SubtitleResults") if isinstance(data, dict) else None
            if not page_results:
                break
            collected.extend(page_results)
            if page >= int(data.get("PagesAvailable") or 1):
                break
            page += 1
        return collected

    def _parse_result(self, sub: dict, query: VideoQuery) -> SubtitleResult | None:
        if not isinstance(sub, dict):
            return None
        sub_id = sub.get("Id")
        dl_url = sub.get("Link") or ""
        lang_code = _LANG_REVERSE.get(str(sub.get("Lang") or ""))
        if not sub_id or not dl_url or not lang_code:
            return None
        if lang_code not in (query.languages or []):
            return None

        is_pack = False
        if query.is_episode:
            season = sub.get("Season")
            episode = sub.get("Episode")
            if query.season and season and season != query.season:
                return None
            if query.episode and episode not in (None, 0, query.episode):
                return None
            is_pack = episode == 0

        release = sub.get("Release") or sub.get("Title") or ""
        matches = {"series", "season", "episode"} if query.is_episode else {"title"}
        provider_data = {}
        if is_pack:
            # Remember what to pull out of the archive at download time.
            provider_data = {"is_pack": True, "season": query.season, "episode": query.episode}

        return SubtitleResult(
            provider_name=self.name,
            subtitle_id=str(sub_id),
            language=lang_code,
            format=SubtitleFormat.SRT,
            filename=f"{release or 'subtitle'}.srt",
            download_url=dl_url,
            release_info=release,
            matches=matches,
            provider_data=provider_data,
        )

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------
    def download(self, result: SubtitleResult) -> bytes:
        if not self.session:
            raise ProviderError("Titlovi not initialized")

        # P1: Validate download URL against allowed domains before fetching
        url_ok, url_err = validate_download_url(result.download_url or "", self.name)
        if not url_ok:
            raise ProviderError(f"Titlovi download URL rejected: {url_err}")

        try:
            # P5: 50 MB streaming cap
            content = _stream_download(
                self.session, result.download_url, timeout=self.timeout, provider_name=self.name
            )
        except ProviderError:
            raise
        except Exception as e:
            raise ProviderError(f"Titlovi download error: {e}") from e

        if content[:2] == b"PK":
            content = self._extract_from_zip(content, result)

        result.content = content
        logger.info("Titlovi: downloaded %s (%d bytes)", result.filename, len(content))
        return content

    def _extract_from_zip(self, content: bytes, result: SubtitleResult) -> bytes:
        try:
            entries = extract_subtitles_from_zip(content)
        except ProviderError:
            raise
        except Exception as e:
            raise ProviderError(f"Titlovi: archive extraction failed: {e}") from e
        if not entries:
            raise ProviderError("Titlovi: archive contains no subtitle files")

        name, data = self._pick_entry(entries, result)
        # P2: Sanitize archive-extracted filename to prevent path traversal
        result.filename = _secure_filename(name) or "subtitle"
        safe_name = result.filename
        ext = f".{safe_name.lower().rsplit('.', 1)[-1]}" if "." in safe_name else ""
        result.format = _FORMAT_MAP.get(ext, SubtitleFormat.SRT)
        return data

    @staticmethod
    def _pick_entry(entries: list[tuple[str, bytes]], result: SubtitleResult) -> tuple[str, bytes]:
        """Pick the right file from a season-pack archive.

        Packs (``Episode == 0`` in the API) bundle a whole season; the wanted
        episode is identified by the usual ``s01e03`` / ``1x03`` name patterns.
        Falls back to the first entry for single-subtitle archives or when no
        pattern matches.
        """
        season = result.provider_data.get("season")
        episode = result.provider_data.get("episode")
        if len(entries) > 1 and season and episode:
            needles = (f"s{season:02d}e{episode:02d}", f"{season:02d}x{episode:02d}")
            for name, data in entries:
                lowered = name.lower()
                if any(needle in lowered for needle in needles):
                    return name, data
            logger.warning(
                "Titlovi: pack archive has no entry matching S%02dE%02d — using first file",
                season,
                episode,
            )
        return entries[0]
