"""LegendasDivx (legendasdivx.pt) subtitle provider — Portuguese/Brazilian subtitles.

HTML scraping provider for Portuguese subtitles from legendasdivx.pt.
Requires username/password authentication with PHP session cookies.
Has a strict daily search limit of 145 searches.

Handles HTML parsing with BeautifulSoup, session-based authentication with
lazy login, cookie persistence, and RAR/ZIP archive extraction.

License: GPL-3.0
"""

import logging
from datetime import date
from urllib.parse import urljoin

from archive_utils import extract_subtitles_from_rar, extract_subtitles_from_zip
from providers import register_provider
from providers.base import (
    ProviderAuthError,
    ProviderError,
    ProviderRateLimitError,
    SubtitleProvider,
    SubtitleResult,
    VideoQuery,
)
from providers.download_manager import _MAX_SUBTITLE_SIZE
from providers.http_session import create_session
from providers.legendasdivx_html_parser import _LegendasDivxParseMixin  # noqa: F401
from providers.legendasdivx_parsers import (  # noqa: F401 — re-exported for back-compat
    _BROWSER_UA,
    _FORMAT_MAP,
    _HAS_BS4,
    _HAS_GUESSIT,
    _SUBTITLE_EXTENSIONS,
    BASE_URL,
    DAILY_SEARCH_LIMIT,
    LOGIN_URL,
    SEARCH_URL,
    SITE_DAILY_LIMIT,
    _can_use_lxml,
    _detect_format_from_filename,
    _parse_episode_info,
)
from security_utils import validate_download_url

logger = logging.getLogger(__name__)

if _HAS_BS4:
    from bs4 import BeautifulSoup


@register_provider
class LegendasDivxProvider(SubtitleProvider, _LegendasDivxParseMixin):
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
            logger.info("LegendasDivx: no credentials configured, provider will be disabled")
            return

        logger.debug("LegendasDivx: initializing (lazy auth — login deferred to first search)")
        self.session = create_session(
            max_retries=1,
            backoff_factor=1.0,
            timeout=20,
            user_agent=_BROWSER_UA,
        )
        self.session.headers.update(
            {
                "Accept-Language": "pt-PT,pt;q=0.9,en;q=0.8",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
        )
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
            search_term = (
                f"{query.series_title or query.title} S{query.season:02d}E{query.episode:02d}"
            )
        elif query.is_movie:
            search_term = query.title
            if query.year:
                search_term += f" {query.year}"
        else:
            search_term = query.title or query.series_title
            if not search_term:
                logger.warning("LegendasDivx: no search term available")
                return []

        logger.debug(
            "LegendasDivx: searching for '%s' (count: %d/%d)",
            search_term,
            self._search_count,
            DAILY_SEARCH_LIMIT,
        )

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

    # _parse_search_results + _parse_result_row live on _LegendasDivxParseMixin
    # (see legendasdivx_html_parser.py).

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

        # P1 (detail-page pre-validation) — validate BEFORE the detail fetch
        if result.provider_data.get("is_detail_page") and url:
            ok_detail, err_detail = validate_download_url(url, self.name)
            if not ok_detail:
                raise ProviderError(f"LegendasDivx detail URL rejected: {err_detail}")

        # If the URL points to a detail page, resolve the actual download link
        if result.provider_data.get("is_detail_page"):
            url = self._resolve_download_url(url)
            if not url:
                raise ProviderError("LegendasDivx: could not find download link on detail page")

        # P1: Validate resolved download URL
        url_ok, url_err = validate_download_url(url, self.name)
        if not url_ok:
            raise ProviderError(f"LegendasDivx download URL rejected: {url_err}")

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
        # P5: Enforce 50 MB cap (post-fetch; the session.get path is kept intact
        # so session-expiry redirect detection can run)
        if len(content) > _MAX_SUBTITLE_SIZE:
            raise RuntimeError(
                f"LegendasDivx: subtitle exceeded size limit "
                f"({len(content)} > {_MAX_SUBTITLE_SIZE})"
            )

        # Try to extract from archive
        extracted = None
        if content[:4] == b"PK\x03\x04":
            entries = extract_subtitles_from_zip(content)
            extracted = entries[0] if entries else None
        elif content[:4] == b"Rar!":
            try:
                entries = extract_subtitles_from_rar(content)
                extracted = entries[0] if entries else None
            except ImportError:
                logger.warning("LegendasDivx: rarfile not installed, cannot extract RAR archive")
        if extracted:
            filename, content = extracted
            result.filename = filename
            result.format = _detect_format_from_filename(filename)

        result.content = content
        logger.info("LegendasDivx: downloaded %s (%d bytes)", result.filename, len(content))
        return content

    def _resolve_download_url(self, detail_url: str) -> str | None:
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
