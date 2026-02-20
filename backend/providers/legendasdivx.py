"""LegendasDivx (legendasdivx.pt) subtitle provider — Portuguese/Brazilian subtitles.

HTML scraping provider for Portuguese subtitles from legendasdivx.pt.
Requires username/password authentication with PHP session cookies.
Has a strict daily search limit of 145 searches.

Handles HTML parsing with BeautifulSoup, session-based authentication with
lazy login, cookie persistence, and RAR/ZIP archive extraction.

License: GPL-3.0
"""

import io
import os
import re
import logging
import zipfile
from datetime import date
from typing import Optional
from urllib.parse import urljoin

from providers.base import (
    SubtitleProvider,
    SubtitleResult,
    SubtitleFormat,
    VideoQuery,
    ProviderError,
    ProviderAuthError,
    ProviderRateLimitError,
)
from providers import register_provider
from providers.http_session import create_session

logger = logging.getLogger(__name__)

# Conditional imports with graceful fallback
try:
    from bs4 import BeautifulSoup
    _HAS_BS4 = True
except ImportError:
    _HAS_BS4 = False
    logger.warning("LegendasDivx: beautifulsoup4 not installed, provider will be non-functional")

try:
    import guessit as _guessit_module
    _HAS_GUESSIT = True
except ImportError:
    _HAS_GUESSIT = False
    logger.debug("LegendasDivx: guessit not installed, using regex fallback for release parsing")

try:
    import rarfile
    _HAS_RARFILE = True
except ImportError:
    _HAS_RARFILE = False
    logger.debug("LegendasDivx: rarfile not installed, RAR archives will not be extractable")

BASE_URL = "https://www.legendasdivx.pt"
LOGIN_URL = f"{BASE_URL}/forum/ucp.php"
SEARCH_URL = f"{BASE_URL}/modules.php"

# Daily search limit (site enforces 145, we use 140 as safety margin)
DAILY_SEARCH_LIMIT = 140
SITE_DAILY_LIMIT = 145

_SUBTITLE_EXTENSIONS = {".srt", ".ass", ".ssa", ".sub", ".vtt"}
_FORMAT_MAP = {
    ".ass": SubtitleFormat.ASS,
    ".ssa": SubtitleFormat.SSA,
    ".srt": SubtitleFormat.SRT,
    ".vtt": SubtitleFormat.VTT,
    ".sub": SubtitleFormat.UNKNOWN,
}

_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def _can_use_lxml() -> bool:
    """Check if lxml parser is available for BeautifulSoup."""
    try:
        import lxml  # noqa: F401
        return True
    except ImportError:
        return False


def _parse_episode_info(text: str) -> dict:
    """Parse season/episode info from a release name using guessit or regex fallback."""
    if _HAS_GUESSIT:
        try:
            info = _guessit_module.guessit(text)
            return {
                "season": info.get("season"),
                "episode": info.get("episode"),
                "title": info.get("title", ""),
                "release_group": info.get("release_group", ""),
                "source": info.get("source", ""),
                "resolution": str(info.get("screen_size", "")),
            }
        except Exception:
            pass

    # Regex fallback
    result = {"season": None, "episode": None, "title": "", "release_group": "", "source": "", "resolution": ""}

    # S01E02 pattern
    m = re.search(r'[Ss](\d{1,2})[Ee](\d{1,3})', text)
    if m:
        result["season"] = int(m.group(1))
        result["episode"] = int(m.group(2))

    # Resolution
    m = re.search(r'(1080p|720p|480p|2160p|4[Kk])', text)
    if m:
        result["resolution"] = m.group(1)

    # Release group (last bracket group)
    m = re.search(r'[-\s](\w+)$', text.strip())
    if m:
        result["release_group"] = m.group(1)

    return result


def _detect_format_from_filename(filename: str) -> SubtitleFormat:
    """Detect subtitle format from filename extension."""
    ext = os.path.splitext(filename)[1].lower()
    return _FORMAT_MAP.get(ext, SubtitleFormat.SRT)


def _extract_subtitle_from_archive(content: bytes) -> Optional[tuple[str, bytes]]:
    """Extract the first subtitle file from a ZIP or RAR archive.

    Returns (filename, content) or None if no subtitle found.
    """
    # ZIP detection
    if content[:4] == b'PK\x03\x04':
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                for name in zf.namelist():
                    ext = os.path.splitext(name)[1].lower()
                    if ext in _SUBTITLE_EXTENSIONS:
                        return (os.path.basename(name), zf.read(name))
        except zipfile.BadZipFile:
            logger.warning("LegendasDivx: bad ZIP archive")
        return None

    # RAR detection
    if content[:4] == b'Rar!':
        if not _HAS_RARFILE:
            logger.warning("LegendasDivx: RAR archive detected but rarfile not installed")
            return None
        try:
            with rarfile.RarFile(io.BytesIO(content)) as rf:
                for name in rf.namelist():
                    ext = os.path.splitext(name)[1].lower()
                    if ext in _SUBTITLE_EXTENSIONS:
                        return (os.path.basename(name), rf.read(name))
        except Exception as e:
            logger.warning("LegendasDivx: RAR extraction failed: %s", e)
        return None

    # Not an archive
    return None


@register_provider
class LegendasDivxProvider(SubtitleProvider):
    """LegendasDivx subtitle provider — Portuguese/Brazilian subtitles via HTML scraping with session auth."""

    name = "legendasdivx"
    languages = {"pt"}

    # Plugin system attributes
    config_fields = [
        {"key": "username", "label": "Username", "type": "text", "required": True},
        {"key": "password", "label": "Password", "type": "password", "required": True},
    ]
    rate_limit = (5, 60)  # very conservative due to daily search limit
    timeout = 20
    max_retries = 1  # do not waste rate limit on retries

    def __init__(self, username: str = "", password: str = "", **kwargs):
        super().__init__(**kwargs)
        self.username = username
        self.password = password
        self.session = None
        self._logged_in = False
        self._search_count = 0
        self._last_reset_date = date.today()

    def initialize(self):
        """Initialize HTTP session. Login is deferred to first search (lazy auth)."""
        if not self.username or not self.password:
            logger.warning("LegendasDivx: no credentials configured, provider will be disabled")
            return

        logger.debug("LegendasDivx: initializing (lazy auth — login deferred to first search)")
        self.session = create_session(
            max_retries=1,
            backoff_factor=1.0,
            timeout=20,
            user_agent=_BROWSER_UA,
        )
        self.session.headers.update({
            "Accept-Language": "pt-PT,pt;q=0.9,en;q=0.8",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })
        logger.debug("LegendasDivx: session created successfully (not yet authenticated)")

    def terminate(self):
        """Close session, clear cookies, reset counters."""
        if self.session:
            self.session.close()
            self.session = None
        self._logged_in = False
        self._search_count = 0
        self._last_reset_date = date.today()

    def _login(self):
        """Perform login to legendasdivx.pt via the phpBB login form.

        Parses the login page for hidden CSRF fields, submits credentials,
        and validates successful login by checking for logout link.
        """
        if not self.session:
            raise ProviderError("LegendasDivx: session not initialized")
        if not _HAS_BS4:
            raise ProviderError("LegendasDivx: beautifulsoup4 required for login")

        logger.debug("LegendasDivx: logging in as '%s'", self.username)

        try:
            # Step 1: GET the login page to extract hidden fields
            resp = self.session.get(LOGIN_URL, params={"mode": "login"})
            if resp.status_code != 200:
                raise ProviderAuthError(
                    f"LegendasDivx: failed to load login page (HTTP {resp.status_code})"
                )

            parser = "lxml" if _can_use_lxml() else "html.parser"
            soup = BeautifulSoup(resp.text, parser)

            # Step 2: Extract hidden form fields (sid, form_token, creation_time, etc.)
            login_form = soup.find("form", {"id": "login"}) or soup.find("form")
            form_data = {
                "username": self.username,
                "password": self.password,
                "login": "Login",
                "autologin": "on",
            }

            if login_form:
                for hidden in login_form.find_all("input", {"type": "hidden"}):
                    name = hidden.get("name")
                    value = hidden.get("value", "")
                    if name:
                        form_data[name] = value

            # Step 3: POST the login form
            resp = self.session.post(
                LOGIN_URL,
                params={"mode": "login"},
                data=form_data,
                allow_redirects=True,
            )

            # Step 4: Check if login succeeded
            if resp.status_code == 200:
                page_text = resp.text.lower()
                if "logout" in page_text or "ucp.php?mode=logout" in page_text:
                    self._logged_in = True
                    logger.info("LegendasDivx: login successful for '%s'", self.username)
                    return
                # Check for error messages
                if "invalid" in page_text or "incorrect" in page_text or "erro" in page_text:
                    raise ProviderAuthError(
                        "LegendasDivx: login failed — invalid username or password"
                    )

            raise ProviderAuthError(
                f"LegendasDivx: login failed (HTTP {resp.status_code}) — "
                "could not verify successful authentication"
            )

        except ProviderAuthError:
            raise
        except Exception as e:
            raise ProviderAuthError(f"LegendasDivx: login error: {e}") from e

    def _ensure_authenticated(self):
        """Check daily limit and session validity, re-login if needed.

        1. Resets daily counter at midnight boundary (date comparison).
        2. Checks daily search limit (140/145 safety margin).
        3. Re-authenticates if session cookies expired (302 redirect detection).
        """
        # Step 1: Check daily limit reset
        today = date.today()
        if today > self._last_reset_date:
            self._search_count = 0
            self._last_reset_date = today
            logger.info("LegendasDivx: daily search counter reset (new day)")

        # Step 2: Check daily limit
        if self._search_count >= DAILY_SEARCH_LIMIT:
            raise ProviderRateLimitError(
                f"Daily search limit reached ({DAILY_SEARCH_LIMIT}/{SITE_DAILY_LIMIT}). "
                "Resets at midnight."
            )

        # Step 3: Check if already logged in
        if self._logged_in:
            return

        # Step 4: Login (first time or session expired)
        self._login()

    def health_check(self) -> tuple[bool, str]:
        """Check if legendasdivx.pt is reachable.

        Does NOT login during health check to avoid wasting sessions.
        Checks for presence of login form (site is up and functional).
        """
        if not self.session:
            if not self.username or not self.password:
                return False, "Credentials not configured"
            return False, "Not initialized"
        try:
            resp = self.session.get(BASE_URL, timeout=10)
            if resp.status_code == 200:
                if _HAS_BS4:
                    parser = "lxml" if _can_use_lxml() else "html.parser"
                    soup = BeautifulSoup(resp.text, parser)
                    if soup.find("form") or soup.find("input"):
                        return True, "OK"
                    return True, "OK (structure unclear)"
                return True, "OK (no HTML parsing available)"
            return False, f"HTTP {resp.status_code}"
        except Exception as e:
            return False, str(e)

    def search(self, query: VideoQuery) -> list[SubtitleResult]:
        """Search legendasdivx.pt for Portuguese subtitles matching the query."""
        if not _HAS_BS4:
            logger.warning("LegendasDivx: beautifulsoup4 not available, cannot search")
            return []

        if not self.session:
            logger.warning("LegendasDivx: cannot search — session is None (missing credentials?)")
            return []

        # Only search for Portuguese
        if query.languages and "pt" not in query.languages:
            return []

        # Ensure we're authenticated and within daily limits
        try:
            self._ensure_authenticated()
        except ProviderRateLimitError:
            raise
        except ProviderAuthError as e:
            logger.error("LegendasDivx: authentication failed: %s", e)
            raise
        except Exception as e:
            logger.error("LegendasDivx: authentication error: %s", e)
            return []

        # Build search term
        if query.is_episode:
            search_term = f"{query.series_title or query.title} S{query.season:02d}E{query.episode:02d}"
        elif query.is_movie:
            search_term = query.title
            if query.year:
                search_term += f" {query.year}"
        else:
            search_term = query.title or query.series_title
            if not search_term:
                logger.warning("LegendasDivx: no search term available")
                return []

        logger.debug("LegendasDivx: searching for '%s' (count: %d/%d)",
                      search_term, self._search_count, DAILY_SEARCH_LIMIT)

        try:
            resp = self.session.post(
                SEARCH_URL,
                params={"name": "Downloads", "d_op": "search"},
                data={
                    "pesession": search_term,
                    "selession": "",  # empty = all subtitle types
                },
                allow_redirects=True,
            )

            # Increment search count
            self._search_count += 1

            # Detect session expiry (302 redirect to login)
            if resp.url and "ucp.php" in resp.url and "mode=login" in resp.url:
                logger.info("LegendasDivx: session expired, re-authenticating")
                self._logged_in = False
                self._login()
                # Retry the search
                resp = self.session.post(
                    SEARCH_URL,
                    params={"name": "Downloads", "d_op": "search"},
                    data={
                        "pesession": search_term,
                        "selession": "",
                    },
                    allow_redirects=True,
                )
                self._search_count += 1

            if resp.status_code != 200:
                logger.warning("LegendasDivx: search failed with HTTP %d", resp.status_code)
                return []

            return self._parse_search_results(resp.text, query)

        except (ProviderAuthError, ProviderRateLimitError):
            raise
        except Exception as e:
            logger.error("LegendasDivx: search error: %s", e, exc_info=True)
            return []

    def _parse_search_results(self, html: str, query: VideoQuery) -> list[SubtitleResult]:
        """Parse HTML search results page into SubtitleResult objects."""
        results = []
        parser = "lxml" if _can_use_lxml() else "html.parser"
        soup = BeautifulSoup(html, parser)

        # LegendasDivx renders results in list/table format
        # Try multiple selectors for resilience
        rows = soup.find_all("tr")
        if not rows:
            rows = soup.find_all("div", class_=re.compile(r"result|subtitle|entry|download", re.I))

        if not rows:
            logger.debug("LegendasDivx: no result rows found in HTML")
            return []

        for row in rows:
            try:
                result = self._parse_result_row(row, query)
                if result:
                    results.append(result)
            except Exception as e:
                logger.warning("LegendasDivx: failed to parse result row: %s", e)
                continue

        logger.info("LegendasDivx: found %d results", len(results))
        return results

    def _parse_result_row(self, row, query: VideoQuery) -> Optional[SubtitleResult]:
        """Parse a single result row into a SubtitleResult.

        Returns None if the row is not a valid subtitle result.
        """
        links = row.find_all("a", href=True)
        if not links:
            return None

        download_url = ""
        detail_url = ""
        release_name = ""

        for link in links:
            href = link.get("href", "")
            text = link.get_text(strip=True)

            if "download" in href.lower() or any(href.lower().endswith(ext) for ext in [".zip", ".rar", ".srt"]):
                download_url = urljoin(BASE_URL, href)
            elif href and text and len(text) > 3:
                detail_url = urljoin(BASE_URL, href)
                if not release_name:
                    release_name = text

        if not download_url and not detail_url:
            return None

        effective_url = download_url or detail_url

        row_text = row.get_text(" ", strip=True)
        if not release_name:
            release_name = row_text[:200]

        # Skip header/navigation rows
        if len(release_name) < 3 or release_name.lower() in ("titulo", "descricao", "download", "idioma"):
            return None

        # Detect format
        fmt = SubtitleFormat.SRT
        for ext_str in [".ass", ".ssa", ".srt", ".sub"]:
            if ext_str in release_name.lower():
                fmt = _FORMAT_MAP.get(ext_str, SubtitleFormat.SRT)
                break

        # Build matches
        matches = set()
        parsed = _parse_episode_info(release_name)

        if query.is_episode:
            series_title = query.series_title or query.title
            if series_title and series_title.lower() in release_name.lower():
                matches.add("series")
            if parsed.get("season") == query.season:
                matches.add("season")
            if parsed.get("episode") == query.episode:
                matches.add("episode")
        elif query.is_movie:
            if query.title and query.title.lower() in release_name.lower():
                matches.add("title")
            if query.year and str(query.year) in release_name:
                matches.add("year")

        if query.release_group and query.release_group.lower() in release_name.lower():
            matches.add("release_group")
        if query.resolution and parsed.get("resolution") == query.resolution:
            matches.add("resolution")

        subtitle_id = effective_url.split("/")[-1] if "/" in effective_url else effective_url

        return SubtitleResult(
            provider_name=self.name,
            subtitle_id=f"legendasdivx:{subtitle_id}",
            language="pt",
            format=fmt,
            filename=release_name[:100],
            download_url=effective_url,
            release_info=release_name,
            matches=matches,
            provider_data={
                "is_detail_page": not download_url,
                "detail_url": detail_url,
            },
        )

    def download(self, result: SubtitleResult) -> bytes:
        """Download a subtitle from legendasdivx.pt.

        Ensures authentication before download, handles detail page resolution,
        and extracts from RAR/ZIP archives.
        """
        if not self.session:
            raise RuntimeError("LegendasDivx not initialized")

        # Ensure we're still authenticated for the download
        try:
            self._ensure_authenticated()
        except ProviderRateLimitError:
            raise
        except ProviderAuthError:
            raise

        url = result.download_url
        if not url:
            raise ValueError("No download URL")

        # If the URL points to a detail page, resolve the actual download link
        if result.provider_data.get("is_detail_page"):
            url = self._resolve_download_url(url)
            if not url:
                raise ProviderError("LegendasDivx: could not find download link on detail page")

        resp = self.session.get(url)

        # Detect session expiry during download
        if resp.url and "ucp.php" in resp.url and "mode=login" in resp.url:
            logger.info("LegendasDivx: session expired during download, re-authenticating")
            self._logged_in = False
            self._login()
            resp = self.session.get(url)

        if resp.status_code != 200:
            raise RuntimeError(f"LegendasDivx download failed: HTTP {resp.status_code}")

        content = resp.content

        # Try to extract from archive
        extracted = _extract_subtitle_from_archive(content)
        if extracted:
            filename, content = extracted
            result.filename = filename
            result.format = _detect_format_from_filename(filename)

        result.content = content
        logger.info("LegendasDivx: downloaded %s (%d bytes)", result.filename, len(content))
        return content

    def _resolve_download_url(self, detail_url: str) -> Optional[str]:
        """Fetch a detail page and extract the actual download link."""
        if not _HAS_BS4:
            return None

        try:
            resp = self.session.get(detail_url)
            if resp.status_code != 200:
                return None

            parser = "lxml" if _can_use_lxml() else "html.parser"
            soup = BeautifulSoup(resp.text, parser)

            # Look for download links
            for link in soup.find_all("a", href=True):
                href = link.get("href", "")
                text = (link.get_text(strip=True) or "").lower()
                if "download" in href.lower() or "descarregar" in text or "baixar" in text:
                    return urljoin(BASE_URL, href)

            # Fallback: look for links to archive files
            for link in soup.find_all("a", href=True):
                href = link.get("href", "")
                if any(href.lower().endswith(ext) for ext in [".zip", ".rar", ".srt", ".ass"]):
                    return urljoin(BASE_URL, href)

        except Exception as e:
            logger.warning("LegendasDivx: failed to resolve download URL: %s", e)

        return None
