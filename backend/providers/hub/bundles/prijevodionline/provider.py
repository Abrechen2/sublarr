"""Prijevodi-Online provider for the Bazarr+ Provider Hub catalog.

The site relaunched in September 2026 as a browser app backed by a JSON API at
https://www.prijevodi-online.org/api/v1/, and this provider talks to that API
only. The old HTML routes now redirect to the app shell.

It works without an account: search always runs, and downloads work wherever
the site lets visitors download. An optional account, signed in with a
username and password or with a pasted browser session cookie, adds member
downloads. Token-priced downloads are bought only when the user has turned
them on, only at or below the per-download cap, only after a fresh price quote
from the site, and never twice for the same subtitle.

How the host treats errors shapes the design. Any exception from download()
pauses the whole provider for at least ten minutes and drops it from the rest
of the search run; returning nothing fails without telling the user why. So
search hides candidates the current settings cannot download or pay for, and
download raises a named error only when the user has to act.
"""

import base64
import contextlib
import email.message
import hashlib
import hmac
import http.client
import io
import json
import logging
import math
import os
import re
import secrets
import socket
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections import OrderedDict
from http.cookiejar import Cookie, CookieJar

PROVIDER_ID = "prijevodionline"
SITE_ORIGIN = "https://www.prijevodi-online.org"
API_ROOT = SITE_ORIGIN + "/api/v1"
AUTH_ME_URL = API_ROOT + "/auth/me"
SITE_DOMAIN = "prijevodi-online.org"
COOKIE_DOMAIN = "." + SITE_DOMAIN
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 BazarrProviderHub"
)
ACCEPT_LANGUAGE = "hr-HR,hr;q=0.9,sr;q=0.8,en-US;q=0.7,en;q=0.6"
LOGGER = logging.getLogger("prijevodionline")

API_TIMEOUT_SECONDS = 10
DOWNLOAD_TIMEOUT_SECONDS = 20
HTTP_ATTEMPTS = 3
QUOTE_ATTEMPTS = 2
RETRY_BACKOFF_SECONDS = 0.5
RETRY_BACKOFF_CAP_SECONDS = 8.0
# A 429 or a nearly spent rate window is waited out inline only when the wait
# is this short; anything longer is handed to the host as APIThrottled.
INLINE_WAIT_MAX_SECONDS = 5.0
DEFAULT_RETRY_AFTER_SECONDS = 60
MAX_RESPONSE_BYTES = 16 * 1024 * 1024

# The host's default worker timeout is 120 seconds
# (general.provider_hub_worker_timeout), but a provider cannot see the value
# configured on a given install, and this one declares no *_timeout_seconds
# setting that would raise it. So every search and download call keeps its own
# conservative 30 second budget, with a safety margin to hand the result over.
WORKER_DEADLINE_SECONDS = 30
DEADLINE_SAFETY_SECONDS = 2
# FlareSolverr is only a fallback: the site shows no challenge today. A solve
# must leave room for the replay, and the solver HTTP call gets maxTimeout plus
# a transport buffer, which comes out of the solve window.
REPLAY_RESERVE_SECONDS = 5
SOLVER_TRANSPORT_BUFFER_SECONDS = 2
MIN_SOLVE_WINDOW_MS = 5000
DEFAULT_FLARESOLVERR_TIMEOUT_MS = 25000

# Every API response carries x-ratelimit-* headers (200 requests in about a
# minute). The provider keeps a reserve for the user's own browsing from the
# same address, and a purchase needs a few requests of headroom above it.
RATE_RESERVE = 20
SPEND_MIN_REQUESTS = 5
SPEND_MIN_SECONDS = 12
CONFIRM_TIMEOUT_SECONDS = 15

SNAPSHOT_TTL_SECONDS = 30 * 60
SERIES_TTL_SECONDS = 6 * 60 * 60
SERIES_MISS_TTL_SECONDS = 30 * 60
SEASONS_TTL_SECONDS = 6 * 60 * 60
TRANSLATIONS_TTL_SECONDS = 10 * 60
MOVIE_DETAIL_TTL_SECONDS = 24 * 60 * 60
CAPTCHA_TTL_SECONDS = 12 * 60 * 60
COOKIE_INVALID_TTL_SECONDS = 30 * 60
WARNING_TTL_SECONDS = 30 * 60
ANONYMOUS_GRANT_REFUSED_TTL_SECONDS = 6 * 60 * 60
GRANT_UNRELIABLE_TTL_SECONDS = 12 * 60 * 60
LEDGER_TTL_SECONDS = 24 * 60 * 60
LEDGER_MAX_ENTRIES = 500
LOGIN_SUPPRESSION_SECONDS = {
    "captcha_required": 12 * 60 * 60,
    "invalid_credentials": 60 * 60,
    "no_session": 12 * 60 * 60,
    "rate_limited": 10 * 60,
    "unavailable": 5 * 60,
    "unknown": 60 * 60,
}

SEARCH_PER_PAGE = 20
SERIES_TRANSLATIONS_PER_PAGE = 1000
MOVIE_TRANSLATIONS_PER_PAGE = 100
MAX_PAGES = 3
MAX_MOVIE_HITS = 2
SPECIALS_SEASON = 99

CAP_CHOICES = (1, 2, 3, 5, 10)
DEFAULT_CAP = "1"
# The site's own client treats a list-priced translation as free for anyone
# holding <kind>.translations.downloadFree, and visitors hold it for series.
# Visitors have no tokens, so such a download can never spend anything. A live
# visitor download of a 1-token series translation (2026-09-26) returned the
# file. Set this to False to treat every list-priced item as paid for visitors.
ANONYMOUS_TRUSTS_GRANT = True

ACCESS_CLASSES = ("free", "granted", "priced", "owned", "account_required")
HIDDEN_REASONS = ("spending_off", "over_cap", "low_balance", "needs_account")

LANGUAGES = {
    "hrv": {"alpha3": "hrv", "alpha2": "hr"},
    "srp": {"alpha3": "srp", "alpha2": "sr"},
    "srp-Cyrl": {"alpha3": "srp", "alpha2": "sr", "script": "Cyrl"},
    "bos": {"alpha3": "bos", "alpha2": "bs"},
    "cnr": {"alpha3": "cnr", "alpha2": "me"},
    "mkd": {"alpha3": "mkd", "alpha2": "mk"},
    "hbs": {"alpha3": "hbs", "alpha2": "sh"},
}
# Site language code to language key. "mix", "??", "en" and "sl" are never
# emitted: the first two are ambiguous and the last two are not advertised.
SITE_LANGUAGES = {
    "hr": "hrv",
    "sr": "srp",
    "sr-cyr": "srp-Cyrl",
    "bs": "bos",
    "cnr": "cnr",
    "mk": "mkd",
}
# A broad Serbo-Croatian request takes these rows when they were not asked for
# under their own code.
HBS_SITE_CODES = frozenset({"hr", "sr", "cnr"})
ALPHA2_TO_ALPHA3 = {
    "hr": "hrv",
    "scr": "hrv",
    "sr": "srp",
    "scc": "srp",
    "bs": "bos",
    "me": "cnr",
    "cg": "cnr",
    "mk": "mkd",
    "mac": "mkd",
    "sh": "hbs",
}

SUBTITLE_EXTENSIONS = (".srt", ".sub", ".ssa", ".ass", ".vtt")
# Cookies that must never be replayed from a pasted browser header: Cloudflare
# clearance is bound to the browser's address and User-Agent, and the rest are
# analytics or a one-off OAuth state.
DROPPED_COOKIE_RE = re.compile(r"^(__cf|_cfuvid|cf_|_ga|_gid|_gat|__utm|_fbp|po_oauth_state)", re.I)
CLOUDFLARE_COOKIE_RE = re.compile(r"^(__cf|_cfuvid|cf_)", re.I)
COOKIE_NAME_RE = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")
COOKIE_VALUE_RE = re.compile(r'^(?:[\x21\x23-\x2b\x2d-\x3a\x3c-\x5b\x5d-\x7e]*|"[\x21\x23-\x2b\x2d-\x3a\x3c-\x5b\x5d-\x7e]*")$')
MAX_COOKIE_HEADER_CHARS = 4096
# Cookie values shorter than this are not scrubbed from text: a real session
# value is long, and short ones (a "theme=dark" preference pasted with the
# header) would otherwise be starred out of public release names.
MIN_COOKIE_SECRET_CHARS = 8
MAX_USER_AGENT_CHARS = 512
CAPTCHA_RE = re.compile(r"captcha|turnstile|robot", re.I)
PERMISSION_RE = re.compile(r"^[A-Za-z.]+( or [A-Za-z.]+)*$")
ERROR_CODE_RE = re.compile(r"^[A-Za-z0-9_./-]{1,64}$")
YEAR_SUFFIX_RE = re.compile(r"\s*\((\d{4})\)\s*$")
IMDB_RE = re.compile(r"^tt\d{5,10}$")

CLOUDFLARE_STATUS_CODES = {403, 503}
CLOUDFLARE_CHECK_STATUSES = {403, 429, 503}
# Challenge-specific markers only: Cloudflare's generic error template and the
# WAF block page ("Attention Required!") are not challenges no solver clears.
CLOUDFLARE_BODY_MARKERS = (
    "just a moment",
    "cf-challenge",
    "cf_chl_opt",
    "enable javascript and cookies to continue",
    "checking your browser before accessing",
)

SPENDING_OFF_MESSAGE = (
    "Prijevodi-Online: token-priced downloads are off. Turn on 'Allow token-priced downloads' "
    "in the provider settings to allow them; nothing was spent"
)
CAP_INVALID_MESSAGE = (
    "Prijevodi-Online: the maximum tokens per download setting is not valid, "
    "so no token-priced download is allowed; nothing was spent"
)
BUDGET_MESSAGE = (
    "Prijevodi-Online: not enough time or request budget left to buy safely; nothing was spent"
)
OVERCHARGED_MESSAGE = (
    "Prijevodi-Online charged more than its quote on an earlier purchase, so Bazarr buys "
    "nothing on this account for up to 24 hours; check Purchases on prijevodi-online.org; "
    "nothing was spent"
)
ALREADY_BOUGHT_MESSAGE = (
    "Prijevodi-Online asks for tokens again for a subtitle Bazarr already bought; it is not "
    "bought twice. Check Purchases on prijevodi-online.org"
)
UNCERTAIN_MESSAGE = (
    "Prijevodi-Online: the purchase result is unknown; check Purchases on "
    "prijevodi-online.org; Bazarr will not buy this subtitle again for up to 24 hours"
)
ANONYMOUS_REFUSED_MESSAGE = (
    "Prijevodi-Online does not let visitors download this subtitle. "
    "Add an account in the provider settings."
)
ACCOUNT_NEEDED_MESSAGE = (
    "Prijevodi-Online needs an account to download this subtitle. "
    "Add one in the provider settings."
)
LOGIN_FAILURE_MESSAGES = {
    "captcha_required": (
        "Prijevodi-Online sign-in failed because the site asked for a captcha. "
        "Paste a session cookie in the provider settings instead."
    ),
    "invalid_credentials": (
        "Prijevodi-Online sign-in failed because the site rejected the username or "
        "password. Check them in the provider settings."
    ),
    "no_session": (
        "Prijevodi-Online sign-in did not start a session. Paste a session cookie in "
        "the provider settings instead."
    ),
    "rate_limited": "Prijevodi-Online sign-in was rate limited. Bazarr tries again in a few minutes.",
    "unavailable": (
        "Prijevodi-Online sign-in failed because the site did not answer. "
        "Bazarr tries again in a few minutes."
    ),
    "unknown": "Prijevodi-Online sign-in failed for an unrecognised reason. Bazarr tries again in an hour.",
    "cookie_invalid": "Prijevodi-Online: the session cookie is no longer signed in; paste a fresh one.",
    "partial_credentials": "Prijevodi-Online sign-in needs both a username and a password.",
    "session_refused": (
        "Prijevodi-Online keeps refusing the signed-in account even after a fresh "
        "sign-in. Check the account on prijevodi-online.org."
    ),
}


# Exception names that cross the worker boundary. Only ServiceUnavailable and
# APIThrottled map to host exceptions (20 and 10 minute pauses). The others are
# deliberately unmapped: the host shows their message and pauses the provider
# for its default ten minutes. AuthenticationError, ConfigurationError,
# DownloadLimitExceeded and TooManyRequests are never raised, because they
# park the whole provider, anonymous search included, for hours.
class ServiceUnavailable(RuntimeError):
    """The site did not answer usefully, or its API changed shape."""


class APIThrottled(RuntimeError):
    """The site's request budget is spent; retry_after says for how long."""

    def __init__(self, message, retry_after=None):
        super().__init__(message)
        self.retry_after = retry_after


class CloudflareBlockedError(RuntimeError):
    """Cloudflare answered with a challenge that could not be cleared."""


class AccountRequired(RuntimeError):
    """The subtitle needs an account, or a member permission the account lacks."""


class AccountLoginFailed(RuntimeError):
    """The download needs the configured account, and signing in failed."""


class PaidDownloadRefused(RuntimeError):
    """A token-priced download was not allowed by the settings; nothing was spent."""


class InsufficientTokens(RuntimeError):
    """The account does not hold enough tokens; nothing was spent."""


class PurchaseUncertain(RuntimeError):
    """A purchase may have gone through; Bazarr will not buy it again for a day."""


class DownloadBlocked(RuntimeError):
    """The site withholds the subtitle, for example after a copyright notice."""


class ApiError(ValueError):
    """An unexpected API error answer (status and error code only)."""

    def __init__(self, message, status=None, code=None):
        super().__init__(message)
        self.status = status
        self.code = code


class _DeadlineExceeded(ServiceUnavailable):
    """The call ran out of its time budget before a request was sent."""


class _DownloadRefused(Exception):
    """Internal: the site refused a file download. Always converted."""

    def __init__(self, status, code=None, message="", html=False):
        super().__init__(code or f"HTTP {status}")
        self.status = status
        self.code = code
        self.message = message
        self.html = html


class _SessionRenewed(Exception):
    """Internal: an expired session was replaced; restart the download once."""

    def __init__(self, identity):
        super().__init__("session renewed")
        self.identity = identity


_MISSING = object()
_MISS = object()
_UNKNOWN = object()


class _TTLCache:
    """A small bounded LRU with per-entry expiry on an injectable clock."""

    def __init__(self, clock, maxsize=256):
        self._clock = clock
        self._maxsize = maxsize
        self._items = OrderedDict()

    def get(self, key, default=None):
        entry = self._items.get(key)
        if entry is None:
            return default
        expires, value = entry
        if self._clock() >= expires:
            self._items.pop(key, None)
            return default
        self._items.move_to_end(key)
        return value

    def set(self, key, value, ttl):
        self._items[key] = (self._clock() + ttl, value)
        self._items.move_to_end(key)
        while len(self._items) > self._maxsize:
            self._items.popitem(last=False)

    def pop(self, key):
        self._items.pop(key, None)

    def clear(self):
        self._items.clear()

    def drop_where(self, predicate):
        for key in [key for key in self._items if predicate(key)]:
            self._items.pop(key, None)

    def drop_values(self, predicate):
        for key in [key for key, (_expires, value) in self._items.items() if predicate(value)]:
            self._items.pop(key, None)

    def __len__(self):
        return len(self._items)

    def __repr__(self):
        return f"<cache of {len(self._items)} entries>"


class _Session:
    """One identity's cookie jar, User-Agent and permission snapshot."""

    __slots__ = ("digest", "mode", "jar", "user_agent", "snapshot")

    def __init__(self, digest, mode, user_agent=USER_AGENT):
        self.digest = digest
        self.mode = mode
        self.jar = CookieJar()
        self.user_agent = user_agent
        self.snapshot = None

    def __repr__(self):
        return "<Session redacted>"


class _Identity:
    """The identity a call runs under, and why the account is not live if not."""

    __slots__ = ("session", "failure")

    def __init__(self, session, failure=None):
        self.session = session
        self.failure = failure

    @property
    def snapshot(self):
        return self.session.snapshot or {}

    @property
    def member(self):
        return bool(self.snapshot.get("member"))

    @property
    def digest(self):
        return self.session.digest

    @property
    def account_key(self):
        """The site's member id, so that state about purchases outlives a fresh
        cookie or a switch between the cookie and the password for one account."""
        member_id = self.snapshot.get("member_id")
        return ("member", member_id) if member_id else ("digest", self.digest)

    @property
    def mode(self):
        return self.session.mode

    def __repr__(self):
        return "<Identity redacted>"


class _Call:
    """Per-call state. Holds secret values only while the call runs."""

    __slots__ = (
        "deadline",
        "secrets",
        "flaresolverr_url",
        "flaresolverr_timeout_ms",
        "delay_seconds",
        "rechecked",
    )

    def __repr__(self):
        return "<Call redacted>"


# Pure functions: matching


def normalize_title(value):
    """Fold to ASCII, lowercase, '&' to 'and', drop punctuation, collapse spaces."""
    if value is None:
        return ""
    folded = unicodedata.normalize("NFKD", str(value))
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    folded = folded.encode("ascii", "ignore").decode("ascii").lower()
    folded = folded.replace("&", " and ").replace("_", " ")
    folded = re.sub(r"[^\w\s]", "", folded)
    return re.sub(r"\s+", " ", folded).strip()


def strip_year_suffix(title):
    """Split a trailing '(YYYY)' off a title: ('Show', 2011) or ('Show', None)."""
    text = str(title or "")
    match = YEAR_SUFFIX_RE.search(text)
    if not match:
        return text.strip(), None
    return text[: match.start()].strip(), int(match.group(1))


def _titles_equal(wanted, candidate):
    wanted = normalize_title(wanted)
    candidate = normalize_title(candidate)
    if not wanted or not candidate:
        return False
    return candidate == wanted or candidate.replace(" ", "") == wanted.replace(" ", "")


def _item_title_matches(item, title):
    return _titles_equal(title, item.get("title")) or _titles_equal(title, item.get("originalTitle"))


def match_series(items, title, year):
    """The one series whose title or original title equals the query, or None.

    The query also matches without a trailing '(YYYY)'. Several exact hits are
    narrowed by premiere year (the video's year, or the year of the suffix).
    Anything other than exactly one left is None.
    """
    stripped, suffix_year = strip_year_suffix(title)
    if year is None:
        year = suffix_year
    exact = []
    seen = set()
    for item in items or []:
        if not isinstance(item, dict) or item.get("type") not in (None, "series"):
            continue
        series_id = _as_int(item.get("id"))
        if series_id is None or series_id <= 0 or series_id in seen:
            continue
        if _item_title_matches(item, title) or (stripped != title and _item_title_matches(item, stripped)):
            seen.add(series_id)
            exact.append(item)
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1 and year is not None:
        same_year = [item for item in exact if _as_int(item.get("premiereYear")) == year]
        if len(same_year) == 1:
            return same_year[0]
    return None


def match_movies(items, title, year):
    """Exact-title movie hits of the requested year.

    With no hit of that year, a single exact-title hit one year off is kept.
    With no year to compare, every exact-title hit is returned.
    """
    exact = []
    seen = set()
    for item in items or []:
        if not isinstance(item, dict) or item.get("type") not in (None, "movie"):
            continue
        movie_id = _as_int(item.get("id"))
        if movie_id is None or movie_id <= 0 or movie_id in seen:
            continue
        if _item_title_matches(item, title):
            seen.add(movie_id)
            exact.append(item)
    if year is None:
        return exact
    same_year = [item for item in exact if _as_int(item.get("year")) == year]
    if same_year:
        return same_year
    if len(exact) == 1:
        item_year = _as_int(exact[0].get("year"))
        if item_year is not None and abs(item_year - year) == 1:
            return exact
    return []


def season_id_for(seasons, season):
    """The site's season id for a season number. Season 0 is the 'Season 99' bucket."""
    wanted = _as_int(season)
    if wanted is None:
        return None
    if wanted == 0:
        wanted = SPECIALS_SEASON
    for item in seasons or []:
        if isinstance(item, dict) and _as_int(item.get("seasonNumber")) == wanted:
            season_id = _as_int(item.get("id"))
            if season_id is not None and season_id > 0:
                return season_id
    return None


# Pure functions: languages


def _language_key(language):
    script = None
    if isinstance(language, dict):
        raw = str(language.get("alpha3") or "").strip()
        if not raw:
            raw = str(language.get("alpha2") or "").strip()
        script = language.get("script")
    else:
        raw = str(language or "").strip()
    base, _, suffix = raw.partition("-")
    base = base.lower()
    code = ALPHA2_TO_ALPHA3.get(base, base)
    if suffix and suffix.lower() in ("cyrl", "cyr"):
        script = "Cyrl"
    if code == "srp" and isinstance(script, str) and script.strip().lower() == "cyrl":
        return "srp-Cyrl"
    if code in LANGUAGES and code != "srp-Cyrl":
        return code
    return None


def requested_languages(languages):
    """Language keys the provider can serve for the host's requested languages."""
    keys = set()
    for language in languages or []:
        key = _language_key(language)
        if key:
            keys.add(key)
    return keys


def language_for_row(code, requested):
    """The language key a row with site language `code` is emitted under, or None."""
    code = str(code or "").strip().lower()
    key = SITE_LANGUAGES.get(code)
    if key is None:
        return None
    if key in requested:
        return key
    if "hbs" in requested and code in HBS_SITE_CODES:
        return "hbs"
    return None


def language_payload(key):
    """The candidate language dict for a language key."""
    entry = LANGUAGES[key]
    payload = {"alpha3": entry["alpha3"], "alpha2": entry["alpha2"], "hi": False, "forced": False}
    if entry.get("script"):
        payload["script"] = entry["script"]
    return payload


# Pure functions: access and spending


def _item_price(item):
    """(valid, price): price is 0 for free, an int >= 1 when priced.

    Only an explicit 0 is free. A missing, null or unreadable price is unknown,
    so the row is not valid and never taken as free: a free member row is
    downloaded without a price quote. The site's detail route answers null for
    rows its lists price at 1.
    """
    if not isinstance(item, dict) or "price" not in item:
        return False, None
    raw = item.get("price")
    if raw is None:
        return False, None
    price = _as_int(raw)
    if price is None or price < 0:
        return False, None
    return True, price


def classify_access(item, kind, snapshot, learned=()):
    """Classify one translation row for the identity in `snapshot`.

    `kind` is the permission prefix ("series" or "movies"). `learned` holds
    the kinds whose downloadFree grant is currently distrusted.
    """
    item = item or {}
    snapshot = snapshot or {}
    if item.get("fileId") is None or item.get("isPublished") is not True or item.get("status") != "approved":
        return "skip"
    member = bool(snapshot.get("member"))
    permissions = snapshot.get("permissions") or frozenset()
    # Owned comes before the price: an owned row is downloaded directly and is
    # never quoted or bought, so an unreadable price cannot make it spend.
    if member and item.get("isPurchased") is True and item.get("isRevoked") is not True:
        return "owned"
    valid, price = _item_price(item)
    if not valid:
        return "skip"
    can_download = f"{kind}.translations.download" in permissions
    can_download_free = f"{kind}.translations.downloadFree" in permissions
    if not can_download and not can_download_free:
        return "account_required"
    if not price:
        return "free"
    if can_download_free and kind not in (learned or ()) and (member or ANONYMOUS_TRUSTS_GRANT):
        return "granted"
    if member and can_download:
        return "priced"
    return "account_required"


def parse_cap(value):
    """The per-download token cap as an int from CAP_CHOICES, or None if invalid."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        cap = value
    elif isinstance(value, str) and value.strip().isdigit():
        cap = int(value.strip())
    else:
        return None
    return cap if cap in CAP_CHOICES else None


def hidden_reason(access, price, member, spending_on, cap, balance):
    """Why a candidate is hidden from search for the current settings, or None."""
    if access in ("owned", "free", "granted"):
        return None
    if access == "priced":
        if not member:
            return "needs_account"
        if not spending_on:
            return "spending_off"
        if cap is None or price is None or price > cap:
            return "over_cap"
        if balance is not None and balance < price:
            return "low_balance"
        return None
    if access == "account_required" and not price:
        return None
    return "needs_account"


# Pure functions: candidates


def _item_texts(item, kind):
    first = item.get("name") if kind == "series" else item.get("title")
    return [
        value
        for value in (first, item.get("description"), item.get("fileName"), item.get("releaseFormatName"))
        if isinstance(value, str) and value.strip()
    ]


def release_tokens(item, kind="series"):
    """Normalized release tokens of a row, plus adjacent-pair joins (web+dl, blu+ray)."""
    tokens = set()
    for text in _item_texts(item or {}, kind):
        parts = _tokens(text)
        tokens.update(parts)
        tokens.update(left + right for left, right in zip(parts, parts[1:]))
    return tokens


def derive_matches(video, item, kind, verified=False, year=None):
    """Subliminal match keys actually present for this row."""
    video = video or {}
    item = item or {}
    matches = []
    video_year = _as_int(video.get("year"))
    if kind == "series":
        wanted = str(video.get("series") or "")
        stripped = strip_year_suffix(wanted)[0]
        titles = (item.get("seriesTitle"), item.get("seriesOriginalTitle"))
        if any(_titles_equal(wanted, title) or _titles_equal(stripped, title) for title in titles):
            matches.append("series")
        season = _as_int(video.get("season"))
        if season is not None:
            site_season = SPECIALS_SEASON if season == 0 else season
            if _as_int(item.get("seasonNumber")) == site_season:
                matches.append("season")
        episode = _as_int(video.get("episode"))
        if episode is not None and _as_int(item.get("episodeNumber")) == episode:
            matches.append("episode")
        if video_year is not None and year is not None and video_year == year:
            matches.append("year")
    else:
        wanted = str(video.get("title") or "")
        titles = (item.get("movieTitle"), item.get("movieOriginalTitle"))
        if any(_titles_equal(wanted, title) for title in titles):
            matches.append("title")
        item_year = year if year is not None else _as_int(item.get("movieYear"))
        if video_year is not None and item_year is not None and video_year == item_year:
            matches.append("year")
        if verified:
            matches.append("imdb_id")
    tokens = release_tokens(item, kind)
    for key in ("release_group", "source", "resolution"):
        value = _squash(video.get(key))
        if value and value in tokens:
            matches.append(key)
    return matches


SCORE_WEIGHTS = {
    "series": {"series": 20, "season": 15, "episode": 15, "release_group": 5, "source": 3, "resolution": 2},
    "movies": {"title": 20, "year": 15, "imdb_id": 15, "release_group": 5, "source": 3, "resolution": 2},
}
SCORE_BASE = 40


def score_for(matches, kind):
    weights = SCORE_WEIGHTS["series" if kind == "series" else "movies"]
    score = SCORE_BASE + sum(weights.get(key, 0) for key in set(matches or ()))
    return min(score, 100)


def _adds_text(text, existing):
    wanted = normalize_title(text).replace(" ", "")
    return bool(wanted) and wanted not in normalize_title(existing).replace(" ", "")


def tokens_text(count):
    return f"{count} token" if count == 1 else f"{count} tokens"


def release_info_for(item, access, price, member=False, kind=None, may_cost=None):
    """The release line: name, extra description, format, flags and the access tag.

    `may_cost` is set for a member's granted row when spending is on: its quote
    may still ask for tokens, and the provider would then pay up to that price.
    """
    item = item or {}
    if kind is None:
        kind = "series" if "seriesId" in item or "episodeNumber" in item else "movies"
    first = item.get("name") if kind == "series" else item.get("title")
    parts = []
    if isinstance(first, str) and first.strip():
        parts.append(first.strip())
    description = item.get("description")
    if isinstance(description, str) and description.strip() and _adds_text(description, " ".join(parts)):
        parts.append(description.strip())
    release_format = item.get("releaseFormatName")
    if isinstance(release_format, str) and release_format.strip():
        parts.append(release_format.strip())
    if item.get("hearingImpaired"):
        parts.append("HI")
    if item.get("machineTranslated"):
        parts.append("machine translated")
    if access == "priced" and price:
        parts.append(f"costs {tokens_text(price)}")
    elif access == "granted" and may_cost:
        parts.append(f"may cost {tokens_text(may_cost)}")
    elif access == "owned":
        parts.append("owned")
    elif access == "account_required":
        parts.append("needs a member permission" if member else "needs an account")
    return " | ".join(parts)[:300]


# Pure functions: parsing


def parse_error(body):
    """{code, message, validation, data} from an API error envelope, or None."""
    data = body if isinstance(body, dict) else _json_dict(body)
    if not isinstance(data, dict):
        return None
    error = data.get("error")
    if not isinstance(error, dict):
        return None
    code = error.get("code")
    code = code if isinstance(code, str) and ERROR_CODE_RE.match(code) else ""
    message = error.get("message")
    message = message if isinstance(message, str) else ""
    validation = error.get("validation")
    validation = validation if isinstance(validation, list) else []
    extra = error.get("data")
    if not isinstance(extra, dict):
        extra = data.get("data") if isinstance(data.get("data"), dict) else {}
    return {"code": code, "message": message, "validation": validation, "data": extra}


def _header_value(headers, name):
    if not headers:
        return None
    wanted = name.lower()
    for key, value in _header_pairs(headers):
        if str(key).lower() == wanted:
            return value
    return None


def _header_seconds(value):
    try:
        seconds = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    if seconds != seconds or seconds < 0 or seconds == float("inf"):
        return None
    # A value this large is an epoch timestamp, not a delta.
    if seconds > 1_000_000_000:
        seconds = max(0.0, seconds - time.time())
    return seconds


def parse_rate_headers(headers):
    """{limit, remaining, reset, retry_after}: counts as ints, times as seconds from now."""
    limit = _as_int(_header_value(headers, "x-ratelimit-limit"))
    remaining = _as_int(_header_value(headers, "x-ratelimit-remaining"))
    reset = _header_value(headers, "x-ratelimit-reset")
    retry_after = _header_value(headers, "retry-after")
    return {
        "limit": limit if limit is not None and limit >= 0 else None,
        "remaining": remaining if remaining is not None and remaining >= 0 else None,
        "reset": _header_seconds(reset) if reset is not None else None,
        "retry_after": _header_seconds(retry_after) if retry_after is not None else None,
    }


def classify_login_failure(status, body, captcha_enabled=None):
    """A failure class for a sign-in answer that did not start a session."""
    status = _as_int(status) or 0
    if 300 <= status < 400 or status >= 500 or _is_html_body(body if isinstance(body, bytes) else None):
        return "unavailable"
    if status == 429:
        return "rate_limited"
    envelope = parse_error(body)
    code = envelope["code"] if envelope else ""
    if envelope:
        if code == "VALIDATION_ERROR":
            for entry in envelope["validation"]:
                path = entry.get("path") if isinstance(entry, dict) else None
                if isinstance(path, list) and "captchaToken" in path:
                    return "captcha_required"
        if CAPTCHA_RE.search(code) or CAPTCHA_RE.search(envelope["message"]):
            return "captcha_required"
    if 200 <= status < 300:
        return "no_session"
    if status in (401, 403) or code.startswith("Auth/"):
        return "invalid_credentials"
    if status in (400, 422) and captcha_enabled:
        return "captcha_required"
    return "unknown"


def parse_session_cookie(text):
    """Cookie pairs to replay from a pasted Cookie header, or None to ignore it.

    The whole field is rejected on a line break, a NUL or an oversized value.
    Cloudflare and analytics cookies are dropped, malformed pairs are skipped,
    and every other cookie is kept, because the name of the site's session
    cookie is not known.
    """
    if not isinstance(text, str):
        return None
    value = text.strip()
    if not value or len(value) > MAX_COOKIE_HEADER_CHARS or any(ch in value for ch in "\r\n\x00"):
        return None
    if value[:7].lower() == "cookie:":
        value = value[7:].strip()
    pairs = []
    seen = set()
    for segment in value.split(";"):
        segment = segment.strip()
        if not segment or "=" not in segment:
            continue
        name, _, cookie_value = segment.partition("=")
        name = name.strip()
        cookie_value = cookie_value.strip()
        if not COOKIE_NAME_RE.match(name) or DROPPED_COOKIE_RE.match(name):
            continue
        if not COOKIE_VALUE_RE.match(cookie_value) or name in seen:
            continue
        seen.add(name)
        pairs.append((name, cookie_value))
    return pairs or None


def classify_confirm_outcome(status, body, exc=None, headers=None):
    """(outcome, detail) for a purchase confirmation.

    Outcomes: bought, insufficient, auth, refused, challenge, throttled,
    not_sent and uncertain. Only a parseable 4xx error envelope (not 408 or
    429) is a definite refusal; anything unreadable is uncertain.
    """
    if exc is not None:
        if isinstance(exc, _DeadlineExceeded):
            return "not_sent", None
        reason = getattr(exc, "reason", None)
        if isinstance(exc, urllib.error.URLError) and isinstance(reason, (socket.gaierror, ConnectionRefusedError)):
            return "not_sent", None
        return "uncertain", None
    status = _as_int(status) or 0
    raw = body if isinstance(body, bytes) else None
    if headers is not None and _is_cloudflare_challenge(status, headers, raw or b""):
        return "challenge", None
    if 200 <= status < 300:
        data = _json_dict(body)
        purchase = data.get("purchase") if isinstance(data, dict) else None
        if isinstance(purchase, dict):
            purchase_id = purchase.get("id")
            cost = purchase.get("tokenCost")
            if _is_plain_int(purchase_id) and _is_plain_int(cost):
                return "bought", {"id": purchase_id, "tokenCost": cost}
        return "uncertain", None
    if status == 429:
        return "throttled", None
    envelope = parse_error(body)
    if envelope and 400 <= status < 500 and status != 408:
        code = envelope["code"]
        if code == "Tokens/InsufficientBalance":
            return "insufficient", code
        if status in (401, 403):
            return "auth", envelope
        return "refused", code
    return "uncertain", None


# The provider


class PrijevodiOnlineProvider:
    def __init__(self):
        # Test seams: every request goes through _send, and the clock and the
        # sleep are instance attributes so TTLs and pacing are testable.
        self._monotonic = time.monotonic
        self._sleep = time.sleep
        self._opener = urllib.request.build_opener(_NoRedirectHandler())
        clock = lambda: self._monotonic()  # noqa: E731, follows a patched clock
        self._call = None
        self._sessions = {}
        self._anonymous = _Session(_digest("anonymous", ""), "anonymous")
        self._credential_fingerprint = None
        self._spend_lock = threading.RLock()
        self._last_request_at = None
        self._rate_remaining = None
        self._rate_reset_at = None
        self._series_cache = _TTLCache(clock, 512)
        self._seasons_cache = _TTLCache(clock, 256)
        self._translations_cache = _TTLCache(clock, 256)
        self._movie_detail_cache = _TTLCache(clock, 256)
        self._captcha_cache = _TTLCache(clock, 4)
        self._cookie_invalid = _TTLCache(clock, 16)
        self._login_suppressed = _TTLCache(clock, 16)
        self._warned = _TTLCache(clock, 64)
        self._anonymous_grant_refused = _TTLCache(clock, 4)
        self._grant_unreliable = _TTLCache(clock, 32)
        self._ledger = _TTLCache(clock, LEDGER_MAX_ENTRIES)
        self._overcharged = _TTLCache(clock, 16)

    # Entry points

    def search(self, video, languages, config):
        video = dict(video or {})
        kind = video.get("kind")
        requested = requested_languages(languages)
        if not requested or kind not in ("episode", "movie"):
            return []
        if kind == "episode":
            if not str(video.get("series") or "").strip():
                return []
            if video.get("season") is None or video.get("episode") is None:
                return []
            season = _as_int(video.get("season"))
            episode = _as_int(video.get("episode"))
            if season is None or episode is None or season < 0 or episode < 0:
                return []
            # Specials live in the site's "Season 99" bucket, whose episode
            # numbering is not known, so they also need the episode title.
            if season == 0 and not _episode_title(video):
                return []
        elif not str(video.get("title") or "").strip():
            return []
        config = dict(config or {})
        with self._call_scope(config):
            identity = self._identity(config)
            if kind == "episode":
                candidates, hidden = self._search_episode(video, requested, identity, config)
            else:
                candidates, hidden = self._search_movie(video, requested, identity, config)
            self._log(
                logging.INFO,
                "Prijevodi-Online %s search: %d candidates; hidden spending_off=%d "
                "over_cap=%d low_balance=%d needs_account=%d",
                kind,
                len(candidates),
                *(hidden[reason] for reason in HIDDEN_REASONS),
            )
            return sorted(candidates, key=lambda item: item["score"], reverse=True)

    def download(self, provider_payload, language, config):
        del language
        payload = _validated_payload(provider_payload)
        config = dict(config or {})
        with self._call_scope(config):
            identity = self._identity(config, anonymous_snapshot=False)
            for _ in range(2):
                try:
                    return self._dispatch(identity, payload, config)
                except _SessionRenewed as renewed:
                    identity = renewed.identity
            raise AccountLoginFailed(LOGIN_FAILURE_MESSAGES["session_refused"])

    # Call scope, scrubbing and logging

    @contextlib.contextmanager
    def _call_scope(self, config):
        previous = self._call
        call = _Call()
        call.deadline = self._monotonic() + WORKER_DEADLINE_SECONDS - DEADLINE_SAFETY_SECONDS
        call.secrets = _config_secrets(config)
        call.flaresolverr_url = _flaresolverr_url(config)
        call.flaresolverr_timeout_ms = _flaresolverr_timeout_ms(config)
        call.delay_seconds = _request_delay_seconds(config)
        call.rechecked = False
        self._call = call
        try:
            yield call
        except _DeadlineExceeded as exc:
            # The host maps exceptions by class name, so the internal subclass
            # would cross unmapped and lose the ServiceUnavailable pause.
            raise ServiceUnavailable(self._scrub(str(exc))) from None
        except Exception as exc:
            self._scrub_exception(exc)
            raise
        finally:
            self._call = previous

    def _secret_values(self):
        values = set()
        if self._call is not None:
            values.update(self._call.secrets)
        for session in list(self._sessions.values()) + [self._anonymous]:
            for cookie in session.jar:
                if cookie.value and len(str(cookie.value)) >= MIN_COOKIE_SECRET_CHARS:
                    values.add(str(cookie.value))
        return sorted((value for value in values if len(value) >= 3), key=len, reverse=True)

    def _scrub(self, text, limit=300):
        text = "" if text is None else str(text)
        for value in self._secret_values():
            text = text.replace(value, "***")
        return text[:limit] if limit else text

    def _scrub_exception(self, exc):
        """Scrub the exception and every exception chained to it.

        The worker prints the whole traceback, chained causes included.
        """
        seen = set()
        pending = [exc]
        while pending:
            current = pending.pop()
            if current is None or id(current) in seen:
                continue
            seen.add(id(current))
            try:
                text = str(current)
            except Exception:  # pragma: no cover, defensive
                text = None
            if text is not None:
                scrubbed = self._scrub(text, limit=None)
                if scrubbed != text:
                    current.args = (scrubbed[:300],)
            pending.extend((current.__cause__, current.__context__))

    def _log(self, level, message, *args):
        if LOGGER.isEnabledFor(level):
            LOGGER.log(level, "%s", self._scrub(message % args if args else message))

    def _warn_once(self, key, message):
        if self._warned.get(key):
            return
        self._warned.set(key, True, WARNING_TTL_SECONDS)
        self._log(logging.WARNING, message)

    # Identity

    def _identity(self, config, anonymous_snapshot=True):
        cookie_text = _text(config.get("session_cookie"))
        user_agent_setting = _text(config.get("session_user_agent")).strip()
        username = _text(config.get("account_name")).strip()
        password = _text(config.get("account_password"))
        self._reset_on_credential_change(
            _digest("config", "\0".join((cookie_text, user_agent_setting, username, password)))
        )
        failure = None
        if cookie_text.strip():
            identity, failure = self._cookie_identity(cookie_text, user_agent_setting)
            if identity is not None:
                return identity
        if username and password:
            identity, login_failure = self._password_identity(username, password)
            if identity is not None:
                return identity
            failure = login_failure
        elif username or password:
            self._warn_once(
                ("partial", _digest("partial", username + "\0" + password)),
                "Prijevodi-Online needs both a username and a password to sign in; "
                "searching without an account",
            )
            failure = failure or "partial_credentials"
        # A visitor download decides from the search result alone, so only
        # search needs the visitor permissions.
        if anonymous_snapshot:
            self._ensure_snapshot(self._anonymous)
        return _Identity(self._anonymous, failure)

    def _reset_on_credential_change(self, fingerprint):
        if self._credential_fingerprint == fingerprint:
            return
        self._credential_fingerprint = fingerprint
        for session in self._sessions.values():
            session.jar.clear()
        self._sessions.clear()
        self._translations_cache.clear()
        self._anonymous_grant_refused.clear()
        self._grant_unreliable.clear()

    def _cookie_identity(self, cookie_text, user_agent_setting):
        pairs = parse_session_cookie(cookie_text)
        if pairs is None:
            self._warn_once(
                ("cookie_rejected", _digest("cookie_rejected", cookie_text)),
                "Prijevodi-Online session cookie setting is not a usable Cookie header; ignoring it",
            )
            return None, "cookie_invalid"
        user_agent = _valid_user_agent(user_agent_setting)
        if user_agent_setting and user_agent is None:
            self._warn_once(
                ("user_agent_rejected", _digest("ua", user_agent_setting)),
                "Prijevodi-Online browser User-Agent setting is not usable; using the default one",
            )
        user_agent = user_agent or USER_AGENT
        material = "; ".join(f"{name}={value}" for name, value in pairs) + "\0" + user_agent
        digest = _digest("cookie", material)
        if self._cookie_invalid.get(digest):
            return None, "cookie_invalid"
        session = self._sessions.get(digest)
        if session is None:
            session = _Session(digest, "cookie", user_agent)
            for name, value in pairs:
                session.jar.set_cookie(_jar_cookie(name, value))
            self._sessions[digest] = session
        if self._ensure_member(session):
            return _Identity(session), None
        self._drop_session(session)
        self._cookie_invalid.set(digest, True, COOKIE_INVALID_TTL_SECONDS)
        self._log(
            logging.WARNING,
            "Prijevodi-Online session cookie is not signed in; trying the other sign-in "
            "settings, or searching without an account",
        )
        return None, "cookie_invalid"

    def _password_identity(self, username, password):
        digest = _digest("password", username + "\0" + password)
        suppressed = self._login_suppressed.get(digest)
        if suppressed:
            return None, suppressed
        session = self._sessions.get(digest)
        if session is not None:
            if self._ensure_member(session):
                return _Identity(session), None
            self._drop_session(session)
        session, failure = self._login(digest, username, password)
        if session is None:
            return None, failure
        return _Identity(session), None

    def _drop_session(self, session):
        self._sessions.pop(session.digest, None)
        session.jar.clear()
        session.snapshot = None

    def _snapshot_fresh(self, session):
        snapshot = session.snapshot
        return bool(snapshot) and self._monotonic() - snapshot["fetched_at"] < SNAPSHOT_TTL_SECONDS

    def _ensure_snapshot(self, session, force=False):
        if force or not self._snapshot_fresh(session):
            session.snapshot = self._auth_me(session)
        return session.snapshot

    def _ensure_member(self, session, force=False):
        return bool(self._ensure_snapshot(session, force=force).get("member"))

    def _auth_me(self, session):
        status, headers, raw = self._request(session, "GET", "/auth/me")
        if status in (401, 403) and parse_error(raw):
            user = {"isAnonymous": True, "id": 0, "permissions": []}
        else:
            data = self._check_json(status, raw, "/auth/me")
            user = data.get("user")
            if not isinstance(user, dict):
                raise ServiceUnavailable(_api_changed("/auth/me"))
        is_member = user.get("isAnonymous") is False and (_as_int(user.get("id")) or 0) > 0
        permissions = frozenset(
            item for item in (user.get("permissions") or []) if isinstance(item, str)
        )
        balance = _as_int(user.get("tokenBalance")) if is_member else None
        return {
            "mode": session.mode,
            "digest": session.digest,
            "member": is_member,
            "member_id": _as_int(user.get("id")) if is_member else None,
            "permissions": permissions,
            "token_balance": balance,
            "fetched_at": self._monotonic(),
        }

    def _login(self, digest, username, password):
        """One sign-in attempt. Returns (session, None) or (None, failure class)."""
        session = _Session(digest, "password")
        body = json.dumps({"username": username, "password": password, "rememberMe": True}).encode("utf-8")
        status, headers, raw = None, {}, b""
        failure = None
        try:
            status, headers, raw = self._exchange(
                session, "POST", API_ROOT + "/auth/login", body, "application/json", API_TIMEOUT_SECONDS
            )
        except APIThrottled as error:
            failure = "rate_limited"
            headers = {"retry-after": str(error.retry_after or "")}
        except (OSError, http.client.HTTPException, ServiceUnavailable, ValueError):
            failure = "unavailable"
        if failure is None and _is_cloudflare_challenge(status, headers, raw):
            failure = "unavailable"
        if failure is None and 200 <= status < 300:
            data = _json_dict(raw) or {}
            auth = data.get("auth")
            auth_id = _as_int(auth.get("id")) if isinstance(auth, dict) else None
            failure = "no_session"
            if auth_id and auth_id > 0 and _has_session_cookie(session.jar):
                try:
                    signed_in = self._ensure_member(session, force=True)
                except APIThrottled:
                    signed_in, failure = False, "rate_limited"
                except (ServiceUnavailable, CloudflareBlockedError, ValueError):
                    signed_in, failure = False, "unavailable"
                if signed_in:
                    self._sessions[digest] = session
                    return session, None
        if failure is None:
            failure = classify_login_failure(status, raw)
            envelope = parse_error(raw)
            code = envelope["code"] if envelope else ""
            if failure == "unknown" and status in (400, 422) and not code.startswith("Auth/"):
                failure = classify_login_failure(status, raw, self._captcha_enabled())
        session.jar.clear()
        ttl = LOGIN_SUPPRESSION_SECONDS.get(failure, LOGIN_SUPPRESSION_SECONDS["unknown"])
        if failure == "rate_limited":
            rate = parse_rate_headers(headers)
            wait = rate["retry_after"] if rate["retry_after"] is not None else rate["reset"]
            if wait is not None:
                ttl = max(1, min(ttl, math.ceil(wait)))
        self._login_suppressed.set(digest, failure, ttl)
        # Only the class is logged: the site's own message could echo the username.
        self._log(
            logging.WARNING,
            "Prijevodi-Online sign-in failed (%s); searching without an account for now",
            failure,
        )
        return None, failure

    def _captcha_enabled(self):
        cached = self._captcha_cache.get("captcha", _MISSING)
        if cached is not _MISSING:
            return cached
        try:
            data = self._api_get(self._anonymous, "/auth/captcha-config")
        except (ServiceUnavailable, APIThrottled, ApiError, ValueError, CloudflareBlockedError):
            # A failed sign-in never fails a search, so neither does this check.
            return None
        captcha = data.get("captcha")
        enabled = captcha.get("enabled") is True if isinstance(captcha, dict) else None
        self._captcha_cache.set("captcha", enabled, CAPTCHA_TTL_SECONDS)
        return enabled

    def _learned_kinds(self, identity):
        kinds = set()
        for kind in ("series", "movies"):
            if identity.member:
                if self._grant_unreliable.get((identity.digest, kind)):
                    kinds.add(kind)
            elif self._anonymous_grant_refused.get(kind):
                kinds.add(kind)
        return frozenset(kinds)

    # Transport

    def _remaining(self):
        return self._call.deadline - self._monotonic()

    def _send(self, method, url, headers, body, timeout):
        """One raw HTTP exchange: (status, headers, body). Redirects are refused."""
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with self._opener.open(request, timeout=timeout) as response:
                return response.status, response.headers, _read_capped(response)
        except urllib.error.HTTPError as error:
            try:
                data = _read_capped(error)
            except Exception:
                data = b""
            return error.code, error.headers, data

    def _pace(self, reserve=True):
        now = self._monotonic()
        delay = self._call.delay_seconds
        if delay > 0 and self._last_request_at is not None:
            wait = self._last_request_at + delay - now
            wait = min(wait, self._call.deadline - now - 1.0)
            if wait > 0:
                self._sleep(wait)
        if reserve:
            self._check_rate_reserve()

    def _check_rate_reserve(self):
        remaining, reset_at = self._rate_remaining, self._rate_reset_at
        if remaining is None or reset_at is None:
            return
        now = self._monotonic()
        if reset_at <= now:
            self._rate_remaining = None
            return
        if remaining > RATE_RESERVE:
            return
        wait = reset_at - now
        if wait <= INLINE_WAIT_MAX_SECONDS and now + wait + 1.0 < self._call.deadline:
            self._sleep(wait)
            self._rate_remaining = None
            return
        raise APIThrottled(
            "Prijevodi-Online's request limit is nearly used up; pausing until it resets",
            retry_after=max(1, math.ceil(wait)),
        )

    def _rate_headroom(self):
        """Requests left above the reserve in the current window, or None if unknown."""
        remaining, reset_at = self._rate_remaining, self._rate_reset_at
        if remaining is None or reset_at is None or reset_at <= self._monotonic():
            return None
        return remaining - RATE_RESERVE

    def _record_rate(self, headers):
        rate = parse_rate_headers(headers)
        if rate["remaining"] is not None:
            self._rate_remaining = rate["remaining"]
            reset = rate["reset"] if rate["reset"] is not None else DEFAULT_RETRY_AFTER_SECONDS
            self._rate_reset_at = self._monotonic() + reset

    def _exchange(self, session, method, url, body, accept, timeout, reserve=True):
        """Pace, stamp the identity's cookies and User-Agent, and send once."""
        self._pace(reserve)
        remaining = self._remaining()
        if remaining <= 0:
            raise _DeadlineExceeded("prijevodi-online.org request ran out of its time budget")
        headers = {
            "User-Agent": session.user_agent,
            "Accept": accept,
            "Accept-Language": ACCEPT_LANGUAGE,
        }
        if body is not None:
            headers["Content-Type"] = "application/json"
        if method == "POST":
            headers["Origin"] = SITE_ORIGIN
            headers["Referer"] = SITE_ORIGIN + "/"
        cookie = _cookie_header(session.jar, url)
        if cookie:
            headers["Cookie"] = cookie
        self._last_request_at = self._monotonic()
        status, raw_headers, data = self._send(method, url, headers, body, min(timeout, remaining))
        pairs = _header_pairs(raw_headers)
        header_map = {str(name).lower(): value for name, value in pairs}
        self._record_rate(header_map)
        # Visitors send no cookies but Cloudflare's own, so only an account
        # session keeps what the site sets.
        if session.mode != "anonymous":
            _extract_cookies(session.jar, url, pairs)
        return int(status), header_map, data or b""

    def _request(
        self,
        session,
        method,
        path,
        query=None,
        json_body=None,
        accept="application/json",
        timeout=API_TIMEOUT_SECONDS,
        attempts=HTTP_ATTEMPTS,
        solve=True,
    ):
        """Send with bounded retries on transport errors, 5xx and short 429 waits."""
        url = _api_url(path, query)
        route = _route(path)
        body = json.dumps(json_body).encode("utf-8") if json_body is not None else None
        solved = False
        attempt = 0
        detail = "no answer"
        while attempt < attempts:
            attempt += 1
            try:
                status, headers, raw = self._exchange(session, method, url, body, accept, timeout)
            except _DeadlineExceeded:
                raise
            except (OSError, http.client.HTTPException) as error:
                detail = type(error).__name__
                if not self._backoff(attempt, attempts):
                    break
                continue
            if _is_cloudflare_challenge(status, headers, raw):
                if method != "GET" or not solve:
                    raise CloudflareBlockedError(
                        "prijevodi-online.org answered with a Cloudflare challenge"
                    )
                if solved:
                    raise CloudflareBlockedError(
                        "prijevodi-online.org is still challenged after a FlareSolverr clearance"
                    )
                self._solve_challenge(session)
                solved = True
                attempt -= 1
                continue
            if status == 429:
                rate = parse_rate_headers(headers)
                wait = rate["retry_after"] if rate["retry_after"] is not None else rate["reset"]
                if (
                    attempt < attempts
                    and wait is not None
                    and wait <= INLINE_WAIT_MAX_SECONDS
                    and self._monotonic() + wait + 1.0 < self._call.deadline
                ):
                    self._sleep(wait)
                    continue
                raise APIThrottled(
                    "Prijevodi-Online rate limited the provider",
                    retry_after=max(1, math.ceil(wait if wait is not None else DEFAULT_RETRY_AFTER_SECONDS)),
                )
            if 500 <= status <= 599:
                detail = f"HTTP {status}"
                if not self._backoff(attempt, attempts):
                    break
                continue
            return status, headers, raw
        raise ServiceUnavailable(
            f"prijevodi-online.org did not answer {route} after {attempt} attempts ({detail})"
        )

    def _backoff(self, attempt, attempts):
        if attempt >= attempts:
            return False
        delay = min(RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1)), RETRY_BACKOFF_CAP_SECONDS)
        if self._monotonic() + delay >= self._call.deadline:
            return False
        self._sleep(delay)
        return True

    def _check_json(self, status, raw, route):
        """The decoded JSON object of a 2xx answer, or the right error for anything else."""
        if 300 <= status < 400 or _is_html_body(raw):
            raise ServiceUnavailable(_api_changed(route))
        data = _json_dict(raw)
        if 200 <= status < 300:
            if data is None:
                raise ServiceUnavailable(_api_changed(route))
            return data
        envelope = parse_error(data)
        code = envelope["code"] if envelope else ""
        if code == "NOT_FOUND" and "route not found" in envelope["message"].lower():
            raise ServiceUnavailable(_api_changed(route))
        if code == "VALIDATION_ERROR":
            raise ValueError(f"Prijevodi-Online rejected the {route} request as invalid; the provider needs an update")
        raise ApiError(
            f"Prijevodi-Online answered {route} with HTTP {status} ({code or 'no error code'})",
            status=status,
            code=code or None,
        )

    def _api_get(self, session, path, query=None):
        status, headers, raw = self._request(session, "GET", path, query)
        return self._check_json(status, raw, _route(path))

    def _paged(self, session, path, query, container_key):
        collected = []
        seen = set()
        route = _route(path)
        for page in range(1, MAX_PAGES + 1):
            page_query = dict(query)
            if page > 1:
                page_query["page"] = page
            data = self._api_get(session, path, page_query)
            items, total = _container(data, container_key, route)
            added = 0
            for item in items:
                item_id = _as_int(item.get("id")) if isinstance(item, dict) else None
                if item_id is None or item_id in seen:
                    continue
                seen.add(item_id)
                collected.append(item)
                added += 1
            # A page that adds nothing new means the site ignores paging.
            if not added or total is None or len(collected) >= total:
                break
        return collected

    # Cloudflare

    def _solve_challenge(self, session):
        """Earn Cloudflare clearance through FlareSolverr, then let the caller replay.

        FlareSolverr only ever visits /api/v1/auth/me: it never sees the URL
        that was challenged, the session cookies or the sign-in details. Only
        the Cloudflare cookies and the User-Agent they are bound to are kept.
        """
        endpoint = self._call.flaresolverr_url
        if not endpoint:
            raise CloudflareBlockedError(
                "prijevodi-online.org answered with a Cloudflare challenge; "
                "configure a FlareSolverr URL in the provider settings to clear it"
            )
        remaining_ms = int(
            (self._remaining() - REPLAY_RESERVE_SECONDS - SOLVER_TRANSPORT_BUFFER_SECONDS) * 1000
        )
        if remaining_ms < MIN_SOLVE_WINDOW_MS:
            raise CloudflareBlockedError(
                "prijevodi-online.org needs a Cloudflare solve but the time budget "
                "leaves no room for one; the next attempt starts fresh"
            )
        payload = {
            "cmd": "request.get",
            "url": AUTH_ME_URL,
            "maxTimeout": min(self._call.flaresolverr_timeout_ms, remaining_ms),
        }
        parsed = self._flaresolverr_transport(payload)
        if not isinstance(parsed, dict) or parsed.get("status") not in (None, "ok"):
            raise CloudflareBlockedError("FlareSolverr did not solve the Prijevodi-Online challenge")
        solution = parsed.get("solution") or {}
        body = str(solution.get("response") or "").encode("utf-8")
        status = _as_int(solution.get("status")) or 0
        if _is_cloudflare_challenge(status, solution.get("headers") or {}, body):
            raise CloudflareBlockedError("FlareSolverr's answer is still a Cloudflare challenge")
        user_agent = _valid_user_agent(str(solution.get("userAgent") or ""))
        if user_agent:
            session.user_agent = user_agent
        for cookie in solution.get("cookies") or []:
            if not isinstance(cookie, dict):
                continue
            name = str(cookie.get("name") or "")
            value = cookie.get("value")
            if not name or value is None or not CLOUDFLARE_COOKIE_RE.match(name):
                continue
            # The same checks a pasted cookie gets.
            if not COOKIE_NAME_RE.match(name) or not COOKIE_VALUE_RE.match(str(value)):
                continue
            for existing in [item for item in session.jar if item.name == name]:
                try:
                    session.jar.clear(existing.domain, existing.path, existing.name)
                except KeyError:  # pragma: no cover, already gone
                    pass
            domain = str(cookie.get("domain") or COOKIE_DOMAIN)
            if not domain.lstrip(".").endswith(SITE_DOMAIN):
                domain = COOKIE_DOMAIN
            session.jar.set_cookie(_jar_cookie(name, value, domain=domain, path=str(cookie.get("path") or "/")))

    def _flaresolverr_transport(self, payload):
        """POST one command to FlareSolverr and return the parsed JSON."""
        endpoint = self._call.flaresolverr_url
        timeout_ms = _as_int(payload.get("maxTimeout")) or self._call.flaresolverr_timeout_ms
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_ms / 1000 + SOLVER_TRANSPORT_BUFFER_SECONDS) as response:
                raw = response.read(MAX_RESPONSE_BYTES)
        except Exception as error:
            raise CloudflareBlockedError(f"FlareSolverr request failed ({type(error).__name__})") from error
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise CloudflareBlockedError("FlareSolverr returned invalid JSON") from error

    # Search

    def _find_series(self, session, title, year):
        stripped, suffix_year = strip_year_suffix(title)
        if year is None:
            year = suffix_year
        queries = []
        for query in (title.strip(), stripped):
            if 2 <= len(query) <= 255 and query not in queries:
                queries.append(query)
        for query in queries:
            key = (normalize_title(query), year)
            cached = self._series_cache.get(key, _MISSING)
            if cached is _MISS:
                continue
            if cached is not _MISSING:
                return cached
            data = self._api_get(
                session, "/search/results", {"q": query, "type": "series", "perPage": SEARCH_PER_PAGE}
            )
            items, _total = _container(data, "results", "/search/results")
            match = match_series(items, query, year)
            if match is None:
                if any(isinstance(item, dict) and _item_title_matches(item, query) for item in items):
                    self._log(logging.INFO, "Prijevodi-Online has several series titled like the query; skipping")
                self._series_cache.set(key, _MISS, SERIES_MISS_TTL_SECONDS)
                continue
            value = {
                "id": _as_int(match.get("id")),
                "slug": str(match.get("slug") or ""),
                "premiereYear": _as_int(match.get("premiereYear")),
            }
            self._series_cache.set(key, value, SERIES_TTL_SECONDS)
            return value
        return None

    def _seasons(self, session, series_id):
        cached = self._seasons_cache.get(series_id)
        if cached is not None:
            return cached
        try:
            data = self._api_get(session, f"/series/{series_id}/seasons")
        except ApiError as error:
            if error.status != 404:
                raise
            # The series was removed or merged on the site since the lookup was
            # cached. Forget the lookup and find nothing for a while, instead of
            # failing, and pausing the provider, on every search for the show.
            self._series_cache.drop_values(lambda value: isinstance(value, dict) and value.get("id") == series_id)
            self._seasons_cache.set(series_id, [], SERIES_MISS_TTL_SECONDS)
            return []
        items, _total = _container(data, "seasons", "/series/seasons")
        self._seasons_cache.set(series_id, items, SEASONS_TTL_SECONDS)
        return items

    def _translations(self, identity, kind, parent_id):
        key = (kind, identity.digest, parent_id)
        cached = self._translations_cache.get(key)
        if cached is not None:
            return cached
        if kind == "series":
            items = self._paged(
                identity.session,
                "/translations/series",
                {"seasonId": parent_id, "perPage": SERIES_TRANSLATIONS_PER_PAGE},
                "translations",
            )
        else:
            items = self._paged(
                identity.session,
                "/translations/movies",
                {"movieId": parent_id, "perPage": MOVIE_TRANSLATIONS_PER_PAGE},
                "movieTranslations",
            )
        # Rows without a readable price are skipped, owned rows aside. If no row
        # carries one, the list's shape changed, and an empty result would hide
        # that from the user.
        if items and not any(
            _item_price(item)[0] or (isinstance(item, dict) and item.get("isPurchased") is True)
            for item in items
        ):
            raise ServiceUnavailable(_api_changed(f"/translations/{kind}"))
        self._translations_cache.set(key, items, TRANSLATIONS_TTL_SECONDS)
        return items

    def _search_episode(self, video, requested, identity, config):
        season = _as_int(video.get("season"))
        episode = _as_int(video.get("episode"))
        series = self._find_series(identity.session, str(video.get("series") or ""), _as_int(video.get("year")))
        if series is None or not series.get("id"):
            return [], _empty_hidden()
        season_id = season_id_for(self._seasons(identity.session, series["id"]), season)
        if season_id is None:
            return [], _empty_hidden()
        site_season = SPECIALS_SEASON if season == 0 else season
        episode_title = _episode_title(video)
        rows = []
        for item in self._translations(identity, "series", season_id):
            if _as_int(item.get("seriesId")) not in (None, series["id"]):
                continue
            if _as_int(item.get("seasonNumber")) != site_season or _as_int(item.get("episodeNumber")) != episode:
                continue
            if season == 0 and normalize_title(item.get("episodeName")) != normalize_title(episode_title):
                continue
            rows.append(item)
        return self._candidates_for(video, rows, "series", requested, identity, config, year=series.get("premiereYear"))

    def _search_movie(self, video, requested, identity, config):
        session = identity.session
        title = str(video.get("title") or "").strip()
        year = _as_int(video.get("year"))
        imdb_id = _normalize_imdb(video.get("imdb_id"))
        hits = []
        if 2 <= len(title) <= 255:
            data = self._api_get(
                session, "/search/results", {"q": title, "type": "movies", "perPage": SEARCH_PER_PAGE}
            )
            items, _total = _container(data, "results", "/search/results")
            hits = match_movies(items, title, year)
        verified = set()
        if hits and imdb_id:
            hits, verified = self._verify_imdb(session, hits, imdb_id)
        elif not hits and (_as_int(video.get("tmdb_id")) or 0) > 0:
            # The site's tmdbId filter is unreliable (many movies carry none),
            # so it is only a fallback, and only a single answer is trusted.
            data = self._api_get(session, "/movies", {"tmdbId": _as_int(video.get("tmdb_id")), "perPage": 5})
            items, total = _container(data, "movies", "/movies")
            if total == 1 and len(items) == 1 and isinstance(items[0], dict) and _as_int(items[0].get("id")):
                hits = [items[0]]
                if imdb_id and _normalize_imdb(items[0].get("imdbId")) == imdb_id:
                    verified.add(_as_int(items[0].get("id")))
        candidates = []
        hidden = _empty_hidden()
        for hit in hits[:MAX_MOVIE_HITS]:
            movie_id = _as_int(hit.get("id"))
            if not movie_id:
                continue
            rows = [
                item
                for item in self._translations(identity, "movies", movie_id)
                if _as_int(item.get("movieId")) in (None, movie_id)
                and (item.get("cdCount") is None or _as_int(item.get("cdCount")) in (0, 1))
            ]
            found, counts = self._candidates_for(
                video, rows, "movies", requested, identity, config,
                year=_as_int(hit.get("year")), verified=movie_id in verified,
            )
            candidates.extend(found)
            for reason in HIDDEN_REASONS:
                hidden[reason] += counts[reason]
        return candidates, hidden

    def _verify_imdb(self, session, hits, imdb_id):
        kept = []
        verified = set()
        for hit in hits[:MAX_MOVIE_HITS]:
            site_imdb = _UNKNOWN
            slug = hit.get("slug")
            if isinstance(slug, str) and slug.strip():
                detail = self._movie_detail(session, slug.strip())
                if detail is not None:
                    site_imdb = _normalize_imdb(detail.get("imdbId"))
            if site_imdb is _UNKNOWN:
                kept.append(hit)
            elif site_imdb is None:
                if len(hits) == 1:
                    kept.append(hit)
            elif site_imdb == imdb_id:
                kept.append(hit)
                verified.add(_as_int(hit.get("id")))
        if verified:
            kept = [hit for hit in kept if _as_int(hit.get("id")) in verified]
        return kept, verified

    def _movie_detail(self, session, slug):
        cached = self._movie_detail_cache.get(slug, _MISSING)
        if cached is not _MISSING:
            return cached
        try:
            data = self._api_get(session, "/movies/by-slug/" + urllib.parse.quote(slug, safe="-._~"))
        except (ServiceUnavailable, ApiError, ValueError, CloudflareBlockedError) as error:
            # A failed check drops only the IMDb verification, never the search.
            self._log(logging.DEBUG, "Prijevodi-Online movie detail check failed (%s)", type(error).__name__)
            return None
        movie = data.get("movie")
        if not isinstance(movie, dict):
            return None
        detail = {"imdbId": movie.get("imdbId")}
        self._movie_detail_cache.set(slug, detail, MOVIE_DETAIL_TTL_SECONDS)
        return detail

    def _candidates_for(self, video, rows, kind, requested, identity, config, year=None, verified=False):
        hidden = _empty_hidden()
        member = identity.member
        snapshot = identity.snapshot
        learned = self._learned_kinds(identity)
        # After an overcharge nothing is bought on the account for a while, so
        # priced rows are hidden as if spending were off.
        spending_on = (
            member and config.get("allow_paid_downloads") is True and not self._overcharged.get(identity.account_key)
        )
        cap = parse_cap(config.get("max_tokens_per_download", DEFAULT_CAP))
        balance = snapshot.get("token_balance") if member else None
        candidates = []
        seen = set()
        for item in rows:
            key = language_for_row(item.get("languageCode"), requested)
            translation_id = _as_int(item.get("id"))
            if key is None or not translation_id or translation_id <= 0 or (translation_id, key) in seen:
                continue
            access = classify_access(item, kind, snapshot, learned)
            if access == "skip":
                continue
            price = _item_price(item)[1]
            reason = hidden_reason(access, price, member, spending_on, cap, balance)
            if reason:
                hidden[reason] += 1
                continue
            seen.add((translation_id, key))
            may_cost = None
            if access == "granted" and spending_on and cap is not None and price and price <= cap:
                may_cost = price
            candidates.append(
                self._candidate(
                    video, item, kind, key, access, price, identity,
                    year=year, verified=verified, may_cost=may_cost,
                )
            )
        return candidates, hidden

    def _candidate(self, video, item, kind, key, access, price, identity, year=None, verified=False, may_cost=None):
        language = language_payload(key)
        language["hi"] = bool(item.get("hearingImpaired"))
        translation_id = _as_int(item.get("id"))
        matches = derive_matches(video, item, kind, verified=verified, year=year)
        score = score_for(matches, kind)
        # The file name and release tokens are the site's public data and feed
        # archive member selection, so they are not scrubbed: a configured
        # username that also appears in a public file name is left as is.
        filename = _candidate_filename(item, kind, video, language)
        uploader = self._scrub(str(item.get("username") or "").strip(), limit=80)
        if access == "priced" and price:
            uploader = f"{uploader} ({tokens_text(price)})".strip()
        return {
            "provider": PROVIDER_ID,
            "id": (
                f"prijevodionline-{'s' if kind == 'series' else 'm'}{translation_id}-{language['alpha3']}"
                f"{'-cyrl' if language.get('script') == 'Cyrl' else ''}"
            ),
            "language": language,
            "release_info": self._scrub(release_info_for(item, access, price, identity.member, kind, may_cost)),
            "filename": filename,
            "matches": matches,
            "score": score,
            "score_without_hash": score,
            "score_out_of": 100,
            "hash_verifiable": False,
            "hearing_impaired_verifiable": True,
            "hearing_impaired": bool(item.get("hearingImpaired")),
            "display": {"source": "prijevodi-online-api", "uploader": uploader},
            "provider_payload": {
                "v": 1,
                "kind": "series" if kind == "series" else "movie",
                "translation_id": translation_id,
                "season": _as_int(video.get("season")) if kind == "series" else None,
                "episode": _as_int(video.get("episode")) if kind == "series" else None,
                "language": language["alpha3"],
                "script": language.get("script"),
                "list_price": price,
                "access": access,
                # The season or movie whose list carried the row, so an owned
                # claim can be checked against the signed-in account's own list.
                "parent_id": _as_int(item.get("seasonId" if kind == "series" else "movieId")),
                "mode": identity.mode,
                "file_name": filename,
                "releases": _payload_releases(item, kind, video),
            },
        }

    # Download

    def _dispatch(self, identity, payload, config):
        kind = "series" if payload["kind"] == "series" else "movies"
        access = payload["access"]
        if not identity.member:
            if access in ("free", "granted"):
                return self._download_anonymous(identity, payload, kind)
            if identity.failure:
                raise AccountLoginFailed(_login_message(identity.failure))
            raise AccountRequired(ACCOUNT_NEEDED_MESSAGE)
        if access == "owned":
            # An owned subtitle is never quoted or bought, whatever this worker
            # remembers: after a restart, in another worker or once a cache has
            # expired, it is still downloaded directly. The claim comes from a
            # search that may have run as another account or before a refund,
            # so the signed-in account's own list must still show it as bought.
            if not self._owned_by_account(identity, payload, kind):
                # A session that ended since the search reads the list as a
                # visitor sees it. Check the session once, and after a fresh
                # sign-in read the account's lists again.
                if not self._call.rechecked and not self._ensure_member(identity.session, force=True):
                    self._call.rechecked = True
                    self._translations_cache.drop_where(lambda key: key[1] == identity.digest)
                    self._renew(identity, config)
                raise PaidDownloadRefused(
                    "Prijevodi-Online does not list this subtitle as bought by the signed-in account; "
                    "search again. Nothing was spent"
                )
            return self._download_member(identity, payload, kind, config)
        if access == "free" and _is_free_price(payload.get("list_price")):
            return self._download_member(identity, payload, kind, config)
        if access == "free":
            # A member's direct download skips the quote, so it needs the 0
            # listed at search time; a missing price is never taken as free.
            raise PaidDownloadRefused(
                "Prijevodi-Online: the price shown at search time is not readable; search again. Nothing was spent"
            )
        if access in ("granted", "priced"):
            return self._spend_and_download(identity, payload, kind, config)
        # account_required: re-check the permissions once before giving up.
        snapshot = self._ensure_snapshot(identity.session, force=True)
        permissions = snapshot.get("permissions") or frozenset()
        needed = f"{kind}.translations.download or {kind}.translations.downloadFree"
        if not snapshot.get("member"):
            if self._call.rechecked:
                raise AccountLoginFailed(LOGIN_FAILURE_MESSAGES["session_refused"])
            self._call.rechecked = True
            self._renew(identity, config)
        if f"{kind}.translations.download" not in permissions and f"{kind}.translations.downloadFree" not in permissions:
            raise AccountRequired(
                f"Prijevodi-Online refused the download for this account. Missing permission: {needed}"
            )
        if _is_free_price(payload.get("list_price")):
            return self._download_member(identity, payload, kind, config)
        promoted = dict(payload)
        promoted["access"] = "granted" if f"{kind}.translations.downloadFree" in permissions else "priced"
        return self._spend_and_download(identity, promoted, kind, config)

    def _owned_by_account(self, identity, payload, kind):
        """Whether the signed-in account's own translation list shows the row as bought.

        A member download of a priced subtitle the account does not own is
        never sent, so a stale or foreign owned claim is refused instead.
        """
        parent_id = payload.get("parent_id")
        if not _is_plain_int(parent_id) or parent_id <= 0:
            return False
        for item in self._translations(identity, kind, parent_id):
            if isinstance(item, dict) and _as_int(item.get("id")) == payload["translation_id"]:
                return classify_access(item, kind, identity.snapshot, ()) == "owned"
        return False

    def _fetch_file(self, session, payload, kind):
        """GET the file and interpret the answer; raises _DownloadRefused on a refusal."""
        route = f"/translations/{kind}/{payload['translation_id']}/download"
        status, headers, raw = self._request(
            session, "GET", route, accept="*/*", timeout=DOWNLOAD_TIMEOUT_SECONDS
        )
        if 300 <= status < 400:
            raise ServiceUnavailable(_api_changed(f"/translations/{kind}/download"))
        envelope = parse_error(raw)
        if envelope:
            code = envelope["code"]
            if code == "Translation/NotFound":
                raise ValueError("the subtitle was removed from Prijevodi-Online")
            if code == "Copyright/InfringementNotice":
                title = envelope["data"].get("title")
                title = _clean_text(title) if isinstance(title, str) else ""
                raise DownloadBlocked(
                    "Prijevodi-Online withholds this subtitle after a copyright notice"
                    + (f" ({self._scrub(title, limit=120)})" if title else "")
                )
            if code == "NOT_FOUND" and "route not found" in envelope["message"].lower():
                raise ServiceUnavailable(_api_changed(f"/translations/{kind}/download"))
            if code == "VALIDATION_ERROR":
                raise ValueError("Prijevodi-Online rejected the download request as invalid; the provider needs an update")
            raise _DownloadRefused(status, code, envelope["message"])
        if status in (401, 402, 403):
            raise _DownloadRefused(status)
        if _is_html_body(raw):
            raise _DownloadRefused(status, "html", html=True)
        if not 200 <= status < 300:
            raise ValueError(f"Prijevodi-Online download answered HTTP {status}")
        return _download_payload(raw, payload)

    def _download_anonymous(self, identity, payload, kind):
        try:
            return self._fetch_file(identity.session, payload, kind)
        except _DownloadRefused as refusal:
            if refusal.html:
                # The app shell where a file belongs is a changed route, not a
                # refusal. Learning from it would hide every visitor result.
                raise ServiceUnavailable(_api_changed(f"/translations/{kind}/download")) from None
            code = refusal.code or ""
            refused = refusal.status in (401, 402, 403) or code.startswith(("Auth/", "Tokens/"))
            if not refused:
                raise ValueError(
                    f"Prijevodi-Online refused the download ({code or 'HTTP ' + str(refusal.status)})"
                ) from None
            if payload["access"] == "granted":
                self._anonymous_grant_refused.set(kind, True, ANONYMOUS_GRANT_REFUSED_TTL_SECONDS)
            if identity.failure:
                raise AccountLoginFailed(_login_message(identity.failure)) from None
            raise AccountRequired(ANONYMOUS_REFUSED_MESSAGE) from None

    def _download_member(self, identity, payload, kind, config, purchased=False):
        try:
            return self._fetch_file(identity.session, payload, kind)
        except _DownloadRefused as refusal:
            if refusal.status in (401, 403) or (refusal.code or "").startswith("Auth/"):
                self._after_auth_refusal(identity, config, refusal.message)
            asks_tokens = refusal.status == 402 or (refusal.code or "").startswith("Tokens/")
            if asks_tokens and payload["access"] == "owned" and not purchased:
                # Listed as bought, yet the site wants tokens. Owned items are
                # never bought, so this is refused rather than quoted.
                raise PaidDownloadRefused(
                    "Prijevodi-Online listed this subtitle as bought, but asked for tokens to download it; "
                    "nothing was spent. Check Purchases on prijevodi-online.org"
                ) from None
            if refusal.status == 402 and purchased:
                raise ValueError(
                    "Prijevodi-Online: the purchase went through, but the site then asked for tokens "
                    "to download it; try the download again later. Bazarr will not buy this subtitle again"
                ) from None
            if refusal.status == 402:
                raise PaidDownloadRefused(
                    "Prijevodi-Online asks for tokens for this subtitle; nothing was spent"
                ) from None
            if refusal.html:
                raise ValueError("Prijevodi-Online returned a web page instead of the subtitle") from None
            raise ValueError(f"Prijevodi-Online refused the download ({refusal.code or 'HTTP ' + str(refusal.status)})") from None

    def _after_auth_refusal(self, identity, config, message):
        """One re-check after a 401/403 on an account call. Always raises.

        A live session means a real permission refusal (AccountRequired). An
        expired one is dropped and signed in again once (_SessionRenewed), or
        the failure is reported (AccountLoginFailed).
        """
        if self._call.rechecked:
            raise AccountLoginFailed(LOGIN_FAILURE_MESSAGES["session_refused"])
        self._call.rechecked = True
        if self._ensure_member(identity.session, force=True):
            permission = _permission_from_message(message)
            detail = f" Missing permission: {permission}" if permission else ""
            raise AccountRequired(f"Prijevodi-Online refused this for the signed-in account.{detail}")
        self._renew(identity, config)

    def _renew(self, identity, config):
        """Replace an expired session by signing in again once. Always raises."""
        session = identity.session
        self._drop_session(session)
        if session.mode == "cookie":
            self._cookie_invalid.set(session.digest, True, COOKIE_INVALID_TTL_SECONDS)
            self._log(logging.WARNING, "Prijevodi-Online session cookie is no longer signed in")
        renewed = self._identity(config)
        if not renewed.member:
            raise AccountLoginFailed(_login_message(renewed.failure or ("cookie_invalid" if session.mode == "cookie" else "session_refused")))
        raise _SessionRenewed(renewed)

    def _spend_and_download(self, identity, payload, kind, config):
        with self._spend_lock:
            access = payload["access"]
            if access not in ("granted", "priced"):
                # Free and owned items are downloaded directly, never quoted or bought.
                raise PaidDownloadRefused(
                    "Prijevodi-Online: only a granted or priced subtitle may be quoted; nothing was spent"
                )
            translation_id = payload["translation_id"]
            allow_paid = config.get("allow_paid_downloads") is True
            cap = parse_cap(config.get("max_tokens_per_download", DEFAULT_CAP))
            list_price = payload.get("list_price")
            list_price = list_price if _is_plain_int(list_price) else None
            if access == "priced":
                if not allow_paid:
                    raise PaidDownloadRefused(SPENDING_OFF_MESSAGE)
                if cap is None:
                    raise PaidDownloadRefused(CAP_INVALID_MESSAGE)
                if list_price is None or list_price < 1:
                    raise PaidDownloadRefused(
                        "Prijevodi-Online: the price shown at search time is not readable; nothing was spent"
                    )
                if list_price > cap:
                    raise PaidDownloadRefused(
                        f"Prijevodi-Online: the price is {tokens_text(list_price)}, above your limit of {cap}; nothing was spent"
                    )
            ledger_key = (identity.account_key, kind, translation_id)
            intent = self._quote(identity, kind, translation_id, config)
            # The echo must name the requested subtitle. The site's schema types
            # translationType as a free string, so only a clear swap of the two
            # request values counts as a mismatch.
            echoed_id = intent.get("translationId")
            echoed_type = intent.get("translationType")
            if (echoed_id is not None and _as_int(echoed_id) != translation_id) or (
                echoed_type in ("series", "movie") and echoed_type != ("series" if kind == "series" else "movie")
            ):
                raise PaidDownloadRefused(
                    "Prijevodi-Online answered the price quote for a different subtitle; nothing was spent"
                )
            action = intent.get("action")
            if action == "download":
                if self._ledger.get(ledger_key) == "uncertain":
                    self._ledger.pop(ledger_key)
                if self._ledger.get(ledger_key) == "confirmed":
                    # Bought by this worker, for example before a fresh sign-in.
                    return self._download_bought(identity, payload, kind, config)
                return self._download_member(identity, payload, kind, config)
            if action != "purchase":
                raise PaidDownloadRefused(
                    "Prijevodi-Online answered the price quote in an unknown way; nothing was spent"
                )
            cost = intent.get("tokenCost")
            cost = cost if _is_plain_int(cost) else None
            if access == "granted":
                self._grant_unreliable.set((identity.digest, kind), True, GRANT_UNRELIABLE_TTL_SECONDS)
            # A purchase this worker already sent comes first, so no later
            # refusal claims that nothing was spent.
            state = self._ledger.get(ledger_key)
            if state == "confirmed":
                raise PurchaseUncertain(ALREADY_BOUGHT_MESSAGE)
            if state in ("sending", "uncertain"):
                raise PurchaseUncertain(UNCERTAIN_MESSAGE)
            if not allow_paid:
                raise PaidDownloadRefused(SPENDING_OFF_MESSAGE)
            if cap is None:
                raise PaidDownloadRefused(CAP_INVALID_MESSAGE)
            if self._overcharged.get(identity.account_key):
                raise PaidDownloadRefused(OVERCHARGED_MESSAGE)
            token = intent.get("token")
            balance = intent.get("balance")
            balance = balance if _is_plain_int(balance) else None
            if cost is None or cost < 1:
                raise PaidDownloadRefused("Prijevodi-Online's price quote is not readable; nothing was spent")
            # The limits the user controls come first, so the refusal names them.
            if cost > cap:
                raise PaidDownloadRefused(
                    f"Prijevodi-Online: the price is now {tokens_text(cost)}, above your limit of {cap}; nothing was spent"
                )
            if list_price is None:
                raise PaidDownloadRefused(
                    f"Prijevodi-Online: the price is now {tokens_text(cost)}, but the price shown at search time "
                    "is not readable; nothing was spent"
                )
            if list_price < 1:
                raise PaidDownloadRefused(
                    f"Prijevodi-Online: the price is now {tokens_text(cost)}, but the subtitle was free at search time; nothing was spent"
                )
            if cost > list_price:
                raise PaidDownloadRefused(
                    f"Prijevodi-Online: the price is now {tokens_text(cost)}, above the {list_price} shown at search time; nothing was spent"
                )
            if balance is not None and balance < cost:
                identity.session.snapshot = None
                raise InsufficientTokens(
                    f"Prijevodi-Online: the subtitle needs {tokens_text(cost)}, the account has {balance}; nothing was spent"
                )
            if intent.get("canAfford") is not True:
                identity.session.snapshot = None
                raise InsufficientTokens(
                    f"Prijevodi-Online says the account cannot buy this subtitle right now ({tokens_text(cost)}); "
                    "nothing was spent"
                )
            if not isinstance(token, str) or not token.strip():
                raise PaidDownloadRefused("Prijevodi-Online's price quote carries no purchase token; nothing was spent")
            headroom = self._rate_headroom()
            if self._remaining() < SPEND_MIN_SECONDS or (headroom is not None and headroom < SPEND_MIN_REQUESTS):
                raise PaidDownloadRefused(BUDGET_MESSAGE)
            return self._confirm_and_download(identity, payload, kind, config, ledger_key, token, cost)

    def _download_bought(self, identity, payload, kind, config, charged=None):
        """Download a subtitle this worker bought. Every failure says tokens were spent.

        The class stays, so the host still pauses the provider the same way.
        """
        try:
            return self._download_member(identity, payload, kind, config, purchased=True)
        except _SessionRenewed:
            raise
        except Exception as failure:
            text = str(failure)
            if "purchase went through" not in text:
                amount = f" ({tokens_text(charged)})" if charged else ""
                failure.args = (
                    f"Prijevodi-Online: the purchase went through{amount}, but the download failed; "
                    f"try it again later. Bazarr will not buy this subtitle again. {text}",
                )
            raise

    def _quote(self, identity, kind, translation_id, config):
        body = {"translationId": translation_id, "translationType": "series" if kind == "series" else "movie"}
        try:
            status, headers, raw = self._request(
                identity.session, "POST", "/purchases/intent", json_body=body,
                attempts=QUOTE_ATTEMPTS, solve=False,
            )
        except CloudflareBlockedError:
            raise PaidDownloadRefused("Prijevodi-Online: Cloudflare challenge; nothing was spent") from None
        envelope = parse_error(raw) if not 200 <= status < 300 else None
        if envelope is not None and status in (401, 403):
            self._after_auth_refusal(identity, config, envelope["message"])
        if envelope is not None:
            code = envelope["code"]
            if code == "Translation/NotFound":
                raise ValueError("the subtitle was removed from Prijevodi-Online")
            if code == "Tokens/InsufficientBalance":
                identity.session.snapshot = None
                raise InsufficientTokens("Prijevodi-Online: the account does not have enough tokens; nothing was spent")
            if code == "Copyright/InfringementNotice":
                raise DownloadBlocked("Prijevodi-Online withholds this subtitle after a copyright notice")
            if not (code == "NOT_FOUND" and "route not found" in envelope["message"].lower()) and code != "VALIDATION_ERROR":
                raise PaidDownloadRefused(
                    f"Prijevodi-Online declined the price quote ({code or 'HTTP ' + str(status)}); nothing was spent"
                )
        data = self._check_json(status, raw, "/purchases/intent")
        intent = data.get("intent")
        if not isinstance(intent, dict):
            raise PaidDownloadRefused("Prijevodi-Online's price quote is not readable; nothing was spent")
        return intent

    def _confirm_and_download(self, identity, payload, kind, config, ledger_key, token, cost):
        """Send the one confirmation this call may send, then fetch the file."""
        session = identity.session
        account_key = identity.account_key
        self._ledger.set(ledger_key, "sending", LEDGER_TTL_SECONDS)
        timeout = max(1.0, min(CONFIRM_TIMEOUT_SECONDS, self._remaining() - 5))
        status, headers, raw, error = None, None, b"", None
        try:
            # Outside the retry loop and never through FlareSolverr: a
            # confirmation is sent once and never replayed.
            status, headers, raw = self._exchange(
                session, "POST", API_ROOT + "/purchases/confirm",
                json.dumps({"token": token}).encode("utf-8"), "application/json", timeout, reserve=False,
            )
        except Exception as caught:  # classified below, never retried
            error = caught
        outcome, detail = classify_confirm_outcome(status, raw, error, headers)
        noun = "series" if kind == "series" else "movie"
        if outcome == "bought":
            self._ledger.set(ledger_key, "confirmed", LEDGER_TTL_SECONDS)
            charged = detail["tokenCost"]
            self._log(
                logging.INFO, "Prijevodi-Online: spent %s on %s subtitle %d",
                tokens_text(charged), noun, payload["translation_id"],
            )
            if charged > cost:
                self._log(
                    logging.ERROR,
                    "Prijevodi-Online charged %s for %s subtitle %d, more than the %d quoted",
                    tokens_text(charged), noun, payload["translation_id"], cost,
                )
                # The log line is easy to miss, so the next purchase refusal
                # tells the user instead, and nothing more is bought for a day.
                self._overcharged.set(account_key, True, LEDGER_TTL_SECONDS)
            session.snapshot = None
            self._translations_cache.drop_where(lambda item: item[1] == identity.digest)
            # The subtitle is owned now. If this download fails, the next
            # attempt's quote answers "download" and nothing is spent again.
            return self._download_bought(identity, payload, kind, config, charged)
        if outcome in ("insufficient", "refused", "auth", "challenge", "not_sent"):
            self._ledger.pop(ledger_key)
        if outcome == "insufficient":
            session.snapshot = None
            raise InsufficientTokens(
                "Prijevodi-Online says the account does not have enough tokens; nothing was spent"
            )
        if outcome == "auth":
            # The site checks the session before it handles the purchase, so
            # nothing was bought. One fresh sign-in and one fresh quote follow.
            self._after_auth_refusal(identity, config, detail["message"] if detail else "")
        if outcome == "refused":
            raise PaidDownloadRefused(
                f"Prijevodi-Online declined the purchase ({detail or 'no error code'}); nothing was spent"
            )
        if outcome == "challenge":
            raise PaidDownloadRefused("Prijevodi-Online: Cloudflare challenge; nothing was spent")
        if outcome == "not_sent":
            raise ServiceUnavailable(
                "Prijevodi-Online could not be reached to confirm the purchase; nothing was spent"
            )
        self._ledger.set(ledger_key, "uncertain", LEDGER_TTL_SECONDS)
        if outcome == "throttled":
            rate = parse_rate_headers(headers)
            wait = rate["retry_after"] if rate["retry_after"] is not None else rate["reset"]
            raise APIThrottled(
                "Prijevodi-Online rate limited the purchase; check Purchases on prijevodi-online.org "
                "before trying again",
                retry_after=max(1, math.ceil(wait if wait is not None else DEFAULT_RETRY_AFTER_SECONDS)),
            )
        raise PurchaseUncertain(UNCERTAIN_MESSAGE)


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Refuse redirects: the old routes' silent 301 to the app shell hid the relaunch."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class _CookieResponse:
    def __init__(self, message):
        self._message = message

    def info(self):
        return self._message


# Helpers


def _empty_hidden():
    return {reason: 0 for reason in HIDDEN_REASONS}


def _validated_payload(payload):
    if not isinstance(payload, dict):
        raise ValueError("prijevodionline download needs a provider payload")
    version = payload.get("v")
    if not _is_plain_int(version) or version != 1:
        raise ValueError("this Prijevodi-Online search result came from an older provider version; search again")
    if payload.get("kind") not in ("series", "movie"):
        raise ValueError("prijevodionline download payload has an unknown kind")
    translation_id = payload.get("translation_id")
    if not _is_plain_int(translation_id) or translation_id <= 0:
        raise ValueError("prijevodionline download payload has no valid translation id")
    if payload.get("access") not in ACCESS_CLASSES:
        raise ValueError("prijevodionline download payload has an unknown access class")
    return dict(payload)


def _login_message(failure):
    return LOGIN_FAILURE_MESSAGES.get(failure, LOGIN_FAILURE_MESSAGES["unknown"])


def _permission_from_message(message):
    text = str(message or "")
    prefix = "Missing permission:"
    if not text.startswith(prefix):
        return None
    permission = text[len(prefix):].strip()
    return permission if PERMISSION_RE.match(permission) and len(permission) <= 160 else None


def _api_changed(route):
    return f"the Prijevodi-Online API changed ({route}); the provider needs an update"


def _api_url(path, query=None):
    url = API_ROOT + path
    if query:
        url += "?" + urllib.parse.urlencode(query)
    return url


def _route(path):
    return re.sub(r"/\d+(?=/|$)", "", path.split("?", 1)[0]) or "/"


def _container(data, key, route):
    container = data.get(key) if isinstance(data, dict) else None
    items = container.get("items") if isinstance(container, dict) else None
    if not isinstance(items, list):
        raise ServiceUnavailable(_api_changed(route))
    return items, _as_int(container.get("total"))


# A per-process key, so a digest of a password or a cookie seen in a state
# dump cannot be checked against guesses offline. Everything keyed by a digest
# lives only as long as the worker process.
_DIGEST_KEY = secrets.token_bytes(32)


def _digest(mode, material):
    message = f"prijevodionline\0v1\0{mode}\0{material}".encode("utf-8")
    return hmac.new(_DIGEST_KEY, message, hashlib.sha256).hexdigest()


def _text(value):
    return value if isinstance(value, str) else ""


def _config_secrets(config):
    values = set()
    for key in ("account_name", "account_password", "session_cookie"):
        value = _text(config.get(key))
        if value:
            values.add(value)
            values.add(value.strip())
    for segment in _text(config.get("session_cookie")).replace("\r", ";").replace("\n", ";").split(";"):
        _name, _, value = segment.partition("=")
        value = value.strip().strip('"')
        if len(value) >= MIN_COOKIE_SECRET_CHARS:
            values.add(value)
    return frozenset(value for value in values if value)


def _valid_user_agent(value):
    value = str(value or "").strip()
    if not value or len(value) > MAX_USER_AGENT_CHARS:
        return None
    if any(not (0x20 <= ord(ch) <= 0x7E) for ch in value):
        return None
    return value


def _request_delay_seconds(config):
    delay = _as_int(config.get("request_delay_ms"))
    if delay is None or delay <= 0:
        return 0.0
    return min(delay, 5000) / 1000.0


def _flaresolverr_url(config):
    return str(config.get("flaresolverr_url") or "").strip()


def _flaresolverr_timeout_ms(config):
    value = _as_int(config.get("flaresolverr_timeout_ms"))
    if value is None:
        value = DEFAULT_FLARESOLVERR_TIMEOUT_MS
    # Capped below the call budget: the solver HTTP call waits the timeout plus
    # transport overhead, and a worker killed mid-solve reports nothing useful.
    return max(5000, min(25000, value))


def _episode_title(video):
    return str((video or {}).get("title") or (video or {}).get("episode_title") or "").strip()


def _normalize_imdb(value):
    text = str(value or "").strip().lower()
    return text if IMDB_RE.match(text) else None


def _candidate_filename(item, kind, video, language):
    name = item.get("fileName")
    if isinstance(name, str) and name.strip():
        base = name.replace("\\", "/").rsplit("/", 1)[-1].strip()
        base = "".join(ch for ch in base if ch.isprintable())
        if base:
            return base[:200]
    if kind == "series":
        slug = _slug(item.get("seriesSlug") or item.get("seriesTitle") or (video or {}).get("series"))
        season = _as_int((video or {}).get("season")) or 0
        episode = _as_int((video or {}).get("episode")) or 0
        return f"prijevodionline.{slug}.s{season:02d}e{episode:02d}.{language['alpha2']}.zip"[:200]
    slug = _slug(item.get("movieSlug") or item.get("movieTitle") or (video or {}).get("title"))
    return f"prijevodionline.{slug}.{language['alpha2']}.zip"[:200]


_RELEASE_NOISE = frozenset(
    {"hr", "sr", "bs", "mk", "cnr", "cg", "cyr", "cir", "lat", "release", "the", "zip", "rar", "srt", "sub"}
)


def _payload_releases(item, kind, video):
    """Release tokens used to pick a member from a multi-release archive."""
    if kind == "series":
        titles = (item.get("seriesTitle"), item.get("episodeName"), (video or {}).get("series"))
        texts = (item.get("name"), item.get("description"), item.get("releaseFormatName"))
    else:
        titles = (item.get("movieTitle"), (video or {}).get("title"))
        texts = (item.get("title"), item.get("releaseFormatName"))
    noise = set(_RELEASE_NOISE)
    for title in titles:
        noise.update(_tokens(title))
    releases = []
    for text in texts:
        for token in _tokens(text):
            if token in noise or token in releases:
                continue
            if re.fullmatch(r"s\d{1,2}e\d{1,3}|\d{1,2}x\d{1,3}", token):
                continue
            releases.append(token)
    return releases[:16]


def _is_plain_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _is_free_price(value):
    """Only an explicit 0 is free; a missing or unreadable price is unknown."""
    return _is_plain_int(value) and value == 0


def _as_int(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else None
    text = str(value).strip()
    if re.fullmatch(r"-?\d{1,18}", text):
        return int(text)
    return None


def _json_dict(body):
    if isinstance(body, dict):
        return body
    if not body:
        return None
    try:
        data = json.loads(body.decode("utf-8") if isinstance(body, bytes) else str(body))
    except (UnicodeDecodeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _header_pairs(headers):
    if not headers:
        return []
    if isinstance(headers, (list, tuple)):
        return [(str(name), str(value)) for name, value in headers]
    items = headers.items()
    return [(str(name), str(value)) for name, value in items]


def _read_capped(response):
    data = response.read(MAX_RESPONSE_BYTES + 1)
    if len(data) > MAX_RESPONSE_BYTES:
        raise ValueError("Prijevodi-Online sent an oversized response")
    return data


def _cookie_header(jar, url):
    probe = urllib.request.Request(url)
    jar.add_cookie_header(probe)
    return probe.get_header("Cookie")


def _extract_cookies(jar, url, pairs):
    message = email.message.Message()
    for name, value in pairs:
        if str(name).lower() in ("set-cookie", "set-cookie2"):
            message[name] = value
    if message.keys():
        jar.extract_cookies(_CookieResponse(message), urllib.request.Request(url))


def _has_session_cookie(jar):
    return any(
        cookie.domain.lstrip(".").endswith(SITE_DOMAIN) and not DROPPED_COOKIE_RE.match(cookie.name)
        for cookie in jar
    )


def _jar_cookie(name, value, domain=COOKIE_DOMAIN, path="/"):
    return Cookie(
        version=0,
        name=str(name),
        value=str(value),
        port=None,
        port_specified=False,
        domain=domain,
        domain_specified=True,
        domain_initial_dot=domain.startswith("."),
        path=path,
        path_specified=True,
        secure=True,
        expires=None,
        discard=True,
        comment=None,
        comment_url=None,
        rest={},
    )


def _is_cloudflare_challenge(status, headers, body):
    """True only for an actual challenge, never for a JSON API error envelope.

    The API answers permission refusals with 403 Auth/Forbidden, and Cloudflare
    proxies every answer ("Server: cloudflare"), so neither means a challenge.
    A challenge announces itself with cf-mitigated: challenge or in the body.
    """
    if (_as_int(status) or 0) not in CLOUDFLARE_CHECK_STATUSES:
        return False
    if parse_error(body if isinstance(body, bytes) else None):
        return False
    if str(_header_value(headers, "cf-mitigated") or "").strip().lower() == "challenge":
        return True
    if (_as_int(status) or 0) not in CLOUDFLARE_STATUS_CODES:
        return False
    text = body.decode("utf-8", "ignore").lower() if isinstance(body, bytes) else str(body or "").lower()
    return any(marker in text for marker in CLOUDFLARE_BODY_MARKERS)


# File answers


def _download_payload(body, payload):
    """Archive or content mode for a downloaded file, or ValueError for a non-file."""
    payload = payload or {}
    if not body or not body.strip():
        raise ValueError("Prijevodi-Online returned an empty download")
    if _is_html_body(body):
        raise ValueError("Prijevodi-Online returned a web page instead of the subtitle")
    if body.startswith(b"PK\x03\x04") and not zipfile.is_zipfile(io.BytesIO(body)):
        raise ValueError("Prijevodi-Online returned a damaged ZIP archive")
    if _is_archive_body(body):
        # The host extracts the archive. A zip member is pinned where the
        # worker can tell which one is wanted; otherwise the host picks by
        # episode.
        archive = {
            "archive_b64": base64.b64encode(body).decode("ascii"),
            "archive_sha256": hashlib.sha256(body).hexdigest(),
        }
        if payload.get("kind") == "movie":
            member = _single_subtitle_member(body)
            if member is not None:
                archive["member"] = member
            else:
                archive["episode"] = None
            return archive
        member = _select_release_member(body, payload)
        if member is not None:
            archive["member"] = member
        else:
            archive["episode"] = payload.get("episode")
        return archive
    if _json_dict(body) is not None:
        raise ValueError("Prijevodi-Online returned an unexpected JSON answer instead of the subtitle")
    return _content_payload(body, _format_for(body, payload.get("file_name")))


def _is_archive_body(body):
    return _is_rar_archive(body) or zipfile.is_zipfile(io.BytesIO(body or b""))


def _is_rar_archive(body):
    return bool(body) and (
        body.startswith(b"Rar!\x1a\x07\x00")
        or body.startswith(b"Rar!\x1a\x07\x01\x00")
    )


def _subtitle_members(body):
    if _is_rar_archive(body) or not zipfile.is_zipfile(io.BytesIO(body)):
        return None
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        return [
            name
            for name in archive.namelist()
            if not name.endswith("/")
            and _subtitle_extension(name)
            and not name.rsplit("/", 1)[-1].startswith(".")
            and not name.startswith("__MACOSX/")
        ]


def _single_subtitle_member(body):
    members = _subtitle_members(body)
    if members is not None and len(members) == 1:
        return members[0]
    return None


def _select_release_member(body, payload):
    """Pin the zip member for the requested season and episode, then by release overlap.

    Returns None for rar (not listable here), a single member, an absent
    episode, or no unique winner, so the host picks by episode instead.
    """
    payload = payload or {}
    members = _subtitle_members(body)
    if members is None or len(members) < 2:
        return None
    season = _as_int(payload.get("season"))
    episode = _as_int(payload.get("episode"))
    pool = members
    if season is not None and episode is not None:
        episode_pool = [name for name in members if _member_matches_episode(name, season, episode)]
        if episode_pool:
            # A lone SxxExx match is a confident pin: the host's episode-only
            # pick is season-blind in a pack that repeats episode numbers.
            if len(episode_pool) == 1:
                return episode_pool[0]
            pool = episode_pool
        elif any(_member_has_episode_marker(name) for name in members):
            return None
    if len(pool) < 2:
        return None
    wanted = set()
    for value in payload.get("releases") or []:
        wanted.update(_tokens(value))
    if not wanted:
        return None
    best, best_score, tied = None, 0, False
    for name in pool:
        score = _member_release_score(name, wanted)
        if score > best_score:
            best, best_score, tied = name, score, False
        elif score == best_score and best is not None:
            tied = True
    if best is None or best_score <= 0 or tied:
        return None
    return best


def _member_release_score(name, release_tokens_set):
    # Token overlap, with a heavy penalty so a forced track never outranks
    # the main subtitle.
    name_tokens = set(_tokens(os.path.basename(name)))
    score = len(release_tokens_set.intersection(name_tokens))
    if "forced" in name_tokens:
        score -= 5
    return score


def _member_matches_episode(name, season, episode):
    # SxxExx with optional separators, and NxNN, both left-bounded so
    # "Extras1E02" never reads as S01E02; (?!\d) keeps e02 from matching e020.
    text = (name or "").lower()
    if re.search(rf"(?<![a-z0-9])s0*{season}[\s._-]*e0*{episode}(?!\d)", text):
        return True
    if re.search(rf"(?<![a-z0-9]){season}x0*{episode}(?!\d)", text):
        return True
    # The whole-token NNN form (S07E20 as "720") must never match "720p".
    return f"{season}{episode:02d}" in _tokens(name)


def _member_has_episode_marker(name):
    text = (name or "").lower()
    if re.search(r"s\d{1,2}[\s._-]*e\d{1,3}", text) or re.search(r"(?<!\d)\d{1,2}x\d{1,3}", text):
        return True
    return any(token.isdigit() and len(token) == 3 for token in _tokens(name))


def _is_html_body(body):
    if not body or not isinstance(body, bytes):
        return False
    head = body[:1024].lstrip().lower()
    return (
        head.startswith(b"<!doctype html")
        or head.startswith(b"<html")
        or head.startswith(b"<?xml")
        or head.startswith(b"<!--")
        or b"<body" in head
        or b"<head" in head
    )


def _subtitle_extension(name):
    lowered = (name or "").lower()
    for extension in SUBTITLE_EXTENSIONS:
        if lowered.endswith(extension):
            return extension[1:]
    return None


def _format_for(body, file_name):
    extension = _subtitle_extension(file_name or "")
    if extension:
        return extension
    head = body[:512].lstrip(b"\xef\xbb\xbf").lstrip()
    if head.startswith(b"WEBVTT"):
        return "vtt"
    if head[:13].lower() == b"[script info]":
        return "ass"
    if re.match(rb"\{\d+\}\{\d+\}", head):
        return "sub"
    return "srt"


def _content_payload(content, subtitle_format):
    # No encoding guess: the host runs chardet, and a worker guess only
    # reintroduces mojibake.
    return {
        "content_b64": base64.b64encode(content).decode("ascii"),
        "content_sha256": hashlib.sha256(content).hexdigest(),
        "content_type": _content_type(subtitle_format),
        "format": subtitle_format,
        "empty": False,
    }


def _content_type(subtitle_format):
    if subtitle_format in {"ass", "ssa"}:
        return "text/x-ssa"
    if subtitle_format == "vtt":
        return "text/vtt"
    if subtitle_format == "sub":
        return "text/plain"
    return "application/x-subrip"


def _clean_text(value):
    return re.sub(r"\s+", " ", "".join(ch for ch in str(value or "") if ch.isprintable())).strip()


def _slug(value):
    return "-".join(_tokens(value)) or "release"


def _tokens(value):
    return [token for token in _normalize(value).split(" ") if token]


def _squash(value):
    return _normalize(value).replace(" ", "")


_NON_ALNUM_RE = re.compile(r"[\W_]+", re.UNICODE)


def _normalize(value):
    if value is None:
        return ""
    decomposed = unicodedata.normalize("NFKD", str(value))
    folded = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return _NON_ALNUM_RE.sub(" ", folded.lower()).strip()
