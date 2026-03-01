"""Turkcealtyazi subtitle provider.

Turkcealtyazi.org is the largest Turkish subtitle community site.
Account registration is required for downloads.

Base URL: https://turkcealtyazi.org
Auth:     Username + Password (required)
Rate:     10 req / 60 s
License:  GPL-3.0
"""

import io
import logging
import zipfile

try:
    from bs4 import BeautifulSoup

    _HAS_BS4 = True
except ImportError:
    _HAS_BS4 = False

from providers import register_provider
from providers.base import (
    ProviderAuthError,
    SubtitleFormat,
    SubtitleProvider,
    SubtitleResult,
    VideoQuery,
)
from providers.http_session import create_session

logger = logging.getLogger(__name__)

_BASE_URL = "https://turkcealtyazi.org"
_LOGIN_URL = f"{_BASE_URL}/giris"
_SEARCH_URL = f"{_BASE_URL}/ara"
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


@register_provider
class TurkcealtyaziProvider(SubtitleProvider):
    """Turkcealtyazi subtitle provider.

    Scrapes turkcealtyazi.org for Turkish subtitles. Requires a registered
    account (username + password). Requires beautifulsoup4.
    """

    name = "turkcealtyazi"
    languages = {"tr"}
    config_fields = [
        {
            "key": "turkcealtyazi_username",
            "label": "Username",
            "type": "text",
            "required": True,
            "description": "Benutzername auf turkcealtyazi.org",
        },
        {
            "key": "turkcealtyazi_password",
            "label": "Password",
            "type": "password",
            "required": True,
        },
    ]
    rate_limit = (10, 60)
    timeout = 20
    max_retries = 2

    def __init__(self, username: str = "", password: str = "", **kwargs):
        super().__init__(**kwargs)
        self.username = username
        self.password = password
        self.session = None
        self._logged_in = False

    def initialize(self):
        if not self.username or not self.password:
            logger.warning("Turkcealtyazi: username and password are required")
            return

        self.session = create_session(
            max_retries=2,
            backoff_factor=1.5,
            timeout=self.timeout,
            user_agent=_BROWSER_UA,
        )
        self.session.headers.update(
            {
                "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
                "Referer": _BASE_URL,
            }
        )
        self._login()

    def terminate(self):
        if self.session:
            self.session.close()
            self.session = None
        self._logged_in = False

    def health_check(self) -> tuple[bool, str]:
        if not self.username or not self.password:
            return False, "Credentials not configured"
        if not self.session:
            return False, "Not initialized"
        if not _HAS_BS4:
            return False, "beautifulsoup4 not installed"
        if not self._logged_in:
            return False, "Not logged in"
        try:
            resp = self.session.get(_BASE_URL, timeout=10)
            return (True, "OK") if resp.status_code == 200 else (False, f"HTTP {resp.status_code}")
        except Exception as e:
            return False, str(e)

    def _login(self):
        """Login to turkcealtyazi.org."""
        try:
            # First, GET the login page to pick up CSRF tokens if any
            self.session.get(_LOGIN_URL, timeout=self.timeout)
            resp = self.session.post(
                _LOGIN_URL,
                data={
                    "username": self.username,
                    "password": self.password,
                    "remember": "on",
                },
                timeout=self.timeout,
            )
            # Check for logged-in indicator (profile link, username in page)
            if resp.status_code == 200 and self.username.lower() in resp.text.lower():
                self._logged_in = True
                logger.debug("Turkcealtyazi: logged in as %s", self.username)
            else:
                logger.warning(
                    "Turkcealtyazi: login failed for %s (HTTP %d)", self.username, resp.status_code
                )
        except Exception as e:
            logger.warning("Turkcealtyazi: login error: %s", e)

    def search(self, query: VideoQuery) -> list[SubtitleResult]:
        if not self.session or not self._logged_in:
            logger.debug("Turkcealtyazi: not logged in, skipping search")
            return []
        if not _HAS_BS4:
            logger.warning("Turkcealtyazi: beautifulsoup4 not installed")
            return []
        if "tr" not in (query.languages or []):
            return []

        search_title = query.series_title or query.title
        if not search_title:
            return []

        logger.debug("Turkcealtyazi: searching '%s'", search_title)

        try:
            resp = self.session.get(
                f"{_SEARCH_URL}/{search_title}",
                timeout=self.timeout,
            )
            if resp.status_code != 200:
                return []
            soup = BeautifulSoup(resp.text, "html.parser")
            results = []
            # Result rows: links to subtitle pages
            for a in soup.select("a[href*='/alt/']"):
                href = a.get("href", "")
                name = a.get_text(strip=True)
                if not href or not name:
                    continue
                url = href if href.startswith("http") else f"{_BASE_URL}{href}"
                subtitle_id = url.rstrip("/").split("/")[-1]
                results.append(
                    SubtitleResult(
                        provider_name=self.name,
                        subtitle_id=subtitle_id,
                        language="tr",
                        format=SubtitleFormat.SRT,
                        filename=f"{name}.srt",
                        download_url=url,
                        release_info=name,
                        matches={"series"} if query.series_title else set(),
                        provider_data={"detail_url": url},
                    )
                )

            logger.info("Turkcealtyazi: found %d results", len(results))
            return results
        except Exception as e:
            logger.debug("Turkcealtyazi: search error: %s", e)
            return []

    def _get_download_url(self, detail_url: str) -> str | None:
        """Follow the subtitle detail page to find the actual download link."""
        try:
            resp = self.session.get(detail_url, timeout=self.timeout)
            if resp.status_code != 200:
                return None
            soup = BeautifulSoup(resp.text, "html.parser")
            # Download button: <a class="btn" href="/indir/..."> or similar
            for a in soup.select("a[href*='/indir/'], a[href*='/download/']"):
                href = a.get("href", "")
                if href:
                    return href if href.startswith("http") else f"{_BASE_URL}{href}"
        except Exception as e:
            logger.debug("Turkcealtyazi: detail page error: %s", e)
        return None

    def download(self, result: SubtitleResult) -> bytes:
        if not self.session:
            raise RuntimeError("Turkcealtyazi not initialized")
        if not self._logged_in:
            raise ProviderAuthError("Turkcealtyazi: not logged in")

        detail_url = (result.provider_data or {}).get("detail_url") or result.download_url
        dl_url = self._get_download_url(detail_url)
        if not dl_url:
            raise RuntimeError(f"Turkcealtyazi: no download URL found on {detail_url}")

        resp = self.session.get(dl_url, headers={"Referer": detail_url}, timeout=self.timeout)
        if resp.status_code != 200:
            raise RuntimeError(f"Turkcealtyazi download failed: HTTP {resp.status_code}")

        content = resp.content

        if content[:2] == b"PK":
            try:
                with zipfile.ZipFile(io.BytesIO(content)) as zf:
                    for name in zf.namelist():
                        if name.lower().endswith((".srt", ".ass", ".ssa", ".vtt")):
                            content = zf.read(name)
                            result.filename = name
                            break
            except Exception as e:
                logger.warning("Turkcealtyazi: ZIP extraction failed: %s", e)

        result.content = content
        logger.info("Turkcealtyazi: downloaded %s (%d bytes)", result.filename, len(content))
        return content
