"""Titulky.com provider for the Bazarr+ Provider Hub catalog."""

import base64
import hashlib
import html
import io
import re
import socket
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import zipfile

PROVIDER_ID = "titulky"
BASE_URL = "https://premium.titulky.com"
DOWNLOAD_URL = f"{BASE_URL}/download.php?id="
HTTP_TIMEOUT_SECONDS = 30
# Transport-level retry for transient network blips (connection reset, DNS,
# timeout, 5xx, 429). Mirrors upstream subliminal's RetryingSession: a single
# blip should not abort a search/download. Non-transient failures (4xx other
# than 429, auth/parse errors) propagate unchanged on the first occurrence.
RETRY_MAX_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 0.5
RETRY_BACKOFF_CAP_SECONDS = 8.0
SUBTITLE_EXTENSIONS = (".srt", ".ass", ".ssa", ".sub", ".vtt")
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 BazarrProviderHub"
)
LANGUAGES = {
    "ces": {"alpha3": "ces", "alpha2": "cs", "flag": "flag-CZ"},
    "slk": {"alpha3": "slk", "alpha2": "sk", "flag": "flag-SK"},
}

_FORM_RE = re.compile(rb'<form\b[^>]*class=["\'][^"\']*\bcloudForm\b[^"\']*["\'][^>]*>(?P<body>.*?)</form>', re.I | re.S)
_ROW_RE = re.compile(rb'<div\b[^>]*class=["\'](?P<class>[^"\']*\brow\b[^"\']*)["\'][^>]*>(?P<body>.*?)</div>', re.I | re.S)
_H5_RE = re.compile(rb"<h5\b[^>]*>(?P<value>.*?)</h5>", re.I | re.S)
_ANCHOR_RE = re.compile(rb'<a\b[^>]*href=["\'](?P<href>[^"\']+)["\'][^>]*>(?P<label>.*?)</a>', re.I | re.S)
_SPAN_RE = re.compile(rb"<span\b[^>]*>(?P<value>.*?)</span>", re.I | re.S)
_ID_RE = re.compile(r"id=(\d+)")
_FPS_RE = re.compile(
    rb'<div\b[^>]*class=["\'][^"\']*\bulozil\b[^"\']*["\'][^>]*>.*?Movieroll\.png.*?(?P<fps>\d+(?:[,.]\d+)?)\s*FPS',
    re.I | re.S,
)
_TAG_RE = re.compile(rb"<[^>]+>")
_WS_BYTES_RE = re.compile(rb"\s+")
_WS_RE = re.compile(r"\s+")
_NON_ALNUM_RE = re.compile(r"[\W_]+", re.UNICODE)


class HttpResponse:
    def __init__(self, status_code, body, headers=None, url=None):
        self.status_code = int(status_code or 0)
        self.body = body if isinstance(body, bytes) else str(body or "").encode("utf-8")
        self.headers = headers or {}
        self.url = url or ""


class TitulkyProvider:
    def __init__(self):
        self._logged_in = False
        self._cookies = {}

    def search(self, video, languages, config):
        config = _validated_config(config)
        requested = _requested_languages(languages)
        if not requested:
            return []
        self._ensure_logged_in(config)
        video = video or {}
        imdb_id = _imdb_id(video)
        if not imdb_id:
            return []
        season = _safe_int(video.get("season")) if video.get("kind") == "episode" else 0
        episode = _safe_int(video.get("episode")) if video.get("kind") == "episode" else 0
        if season is None or episode is None:
            return []
        url = build_url({"action": "serial", "step": season, "id": imdb_id[2:]})
        _sleep(config)
        html_body = self._fetch_page(url, allow_redirects=True, config=config)
        rows = parse_browse_page(html_body, requested, episode, config)
        results = []
        for row in rows:
            fps = self._retrieve_subtitles_fps(row["subtitle_id"], config) if config["skip_wrong_fps"] else None
            results.append(_result_from_row(video, row, fps, config))
        return _sort_results(results)

    def download(self, provider_payload, language, config):
        del language
        config = _validated_config(config)
        self._ensure_logged_in(config)
        payload = provider_payload or {}
        url = payload.get("download_url") or payload.get("url")
        if not url:
            raise ValueError("titulky download requires download_url")
        _sleep(config)
        response = self._http_get(url, headers={"Referer": payload.get("page_link") or BASE_URL})
        if response.status_code == 429:
            raise RuntimeError("Too many requests")
        _raise_for_status(response, url)
        return build_download_payload(response.body, payload)

    def _ensure_logged_in(self, config):
        if self._logged_in:
            return
        response = self._http_post(
            BASE_URL,
            data={"LoginName": config["username"], "LoginPassword": config["password"]},
            headers={"Referer": BASE_URL},
        )
        location = _header(response.headers, "location")
        parsed = urllib.parse.parse_qs(urllib.parse.urlparse(location).query)
        msg_type = (parsed.get("msg_type") or [""])[0].lower()
        message = (parsed.get("msg") or [""])[0].lower()
        if response.status_code == 302 and msg_type == "i":
            if "omezen" in _normalize(message):
                raise PermissionError("Titulky VIP account is required")
            self._logged_in = True
            return
        raise PermissionError("Titulky login failed")

    def _retrieve_subtitles_fps(self, subtitle_id, config):
        _sleep(config)
        html_body = self._fetch_page(
            build_url({"action": "detail", "id": subtitle_id}), allow_redirects=True, config=config
        )
        return parse_fps(html_body)

    @staticmethod
    def _is_auth_redirect(response):
        # Titulky bounces unauthenticated/expired sessions to a message page
        # (?msg_type=...), the same marker _ensure_logged_in keys on. With
        # allow_redirects=True the final URL carries it.
        return "msg_type=" in (response.url or "")

    def _fetch_page(self, url, allow_redirects=False, config=None):
        response = self._fetch_response(url, allow_redirects)
        if config is not None and self._logged_in and self._is_auth_redirect(response):
            # Session cookie expired on a reused worker: drop stale auth, re-login, retry once.
            self._logged_in = False
            self._cookies = {}
            self._ensure_logged_in(config)
            response = self._fetch_response(url, allow_redirects)
        if not response.body:
            raise RuntimeError("Titulky returned an empty response")
        return response.body

    def _fetch_response(self, url, allow_redirects=False):
        response = self._http_get(url, allow_redirects=allow_redirects)
        if response.status_code == 429:
            raise RuntimeError("Too many requests")
        _raise_for_status(response, url)
        return response

    def _http_get(self, url, headers=None, timeout=HTTP_TIMEOUT_SECONDS, allow_redirects=False):
        opener = urllib.request.build_opener() if allow_redirects else urllib.request.build_opener(_NoRedirectHandler)
        request = urllib.request.Request(url, headers=self._headers(headers))
        try:
            response = _open_with_retry(opener, request, timeout)
        except urllib.error.HTTPError as error:
            result = _http_error_response(error, url)
            self._store_cookies(result.headers)
            return result
        with response:
            result = HttpResponse(response.getcode(), response.read(), response.headers, response.geturl())
            self._store_cookies(result.headers)
            return result

    def _http_post(self, url, data=None, headers=None, timeout=HTTP_TIMEOUT_SECONDS):
        encoded = urllib.parse.urlencode(data or {}).encode("utf-8")
        merged_headers = {"Content-Type": "application/x-www-form-urlencoded"}
        merged_headers.update(headers or {})
        request = urllib.request.Request(url, data=encoded, headers=self._headers(merged_headers))
        opener = urllib.request.build_opener(_NoRedirectHandler)
        try:
            response = _open_with_retry(opener, request, timeout)
        except urllib.error.HTTPError as error:
            result = _http_error_response(error, url)
            self._store_cookies(result.headers)
            return result
        with response:
            result = HttpResponse(response.getcode(), response.read(), response.headers, response.geturl())
            self._store_cookies(result.headers)
            return result

    def _headers(self, extra=None):
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "sk,cs,en;q=0.7",
            "Connection": "keep-alive",
        }
        if self._cookies:
            headers["Cookie"] = "; ".join(f"{key}={value}" for key, value in sorted(self._cookies.items()))
        headers.update(extra or {})
        return headers

    def _store_cookies(self, headers):
        for value in _header_values(headers, "set-cookie"):
            cookie = value.split(";", 1)[0]
            if "=" not in cookie:
                continue
            name, cookie_value = cookie.split("=", 1)
            self._cookies[name.strip()] = cookie_value.strip()


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def build_url(params):
    return f"{BASE_URL}/?{urllib.parse.urlencode(params).replace('+', '+')}"


def parse_browse_page(body, languages, wanted_episode, config):
    form_match = _FORM_RE.search(body or b"")
    if not form_match:
        return []
    wanted = {_language_key(language) for language in languages}
    rows = []
    current_episode = None
    for match in _ROW_RE.finditer(form_match.group("body")):
        classes = _decode(match.group("class")).split()
        row = match.group("body")
        number_match = _H5_RE.search(row)
        if number_match:
            current_episode = _safe_int(_strip_tags(number_match.group("value")).rstrip("."))
            continue
        if current_episode != wanted_episode or not {"pbl0", "pbl1"}.intersection(classes):
            continue
        anchor = _ANCHOR_RE.search(row)
        if not anchor:
            continue
        language = _language_from_row(row)
        if not language or _language_key(language) not in wanted:
            continue
        approved = "pbl1" in classes
        if config.get("approved_only") and not approved:
            continue
        href = html.unescape(_decode(anchor.group("href")))
        details_link = urllib.parse.urljoin(BASE_URL + "/", href.lstrip("/"))
        id_match = _ID_RE.search(details_link)
        if not id_match:
            continue
        release = _strip_tags(anchor.group("label"))
        if release == "???":
            release = ""
        subtitle_id = id_match.group(1)
        rows.append(
            {
                "subtitle_id": subtitle_id,
                "episode": current_episode,
                "release_info": release,
                "language": language,
                "approved": approved,
                "uploader": _uploader_from_row(row),
                "details_link": details_link,
                "download_url": f"{DOWNLOAD_URL}{subtitle_id}",
            }
        )
    return rows


def parse_fps(body):
    match = _FPS_RE.search(body or b"")
    if not match:
        return None
    return _float(_decode(match.group("fps")).replace(",", "."))


def build_download_payload(body, payload=None):
    payload = payload or {}
    # Reject broken responses up front: download.php can answer with an empty stream or
    # an HTML/error page that would otherwise look like a successful download.
    if not body or not body.strip():
        raise ValueError("titulky returned an empty response")
    if _looks_like_html(body):
        raise ValueError("titulky download did not return a supported subtitle file")
    if _is_archive_body(body):
        # Host-side extraction (Provider Hub v1.1+): hand the raw archive bytes back to
        # the host, which lists it, detects encoding, and picks the member. A Titulky zip
        # can bundle several releases for the same episode (different group / resolution /
        # source) plus an occasional forced track; the host's episode-only pick cannot tell
        # them apart. When we can list a zip we pin the member whose filename overlaps the
        # scored release_info (the old select_subtitle_file intent), preferring non-forced.
        # Otherwise (rar, single member, the requested episode absent, or no unique winner)
        # let the host pick the member by episode.
        archive = {
            "archive_b64": base64.b64encode(body).decode("ascii"),
            "archive_sha256": hashlib.sha256(body).hexdigest(),
        }
        member = _select_release_member(body, payload)
        if member is not None:
            archive["member"] = member
        else:
            archive["episode"] = payload.get("episode")
        return archive
    subtitle_format = _direct_subtitle_format(body, payload)
    if not subtitle_format:
        raise ValueError("titulky download did not return a supported subtitle file")
    # Direct, non-archive subtitle body.
    return _content_payload(body, subtitle_format)


def _is_archive_body(body):
    return _is_rar_archive(body) or zipfile.is_zipfile(io.BytesIO(body or b""))


def _select_release_member(body, payload):
    # Pin the zip member matching the scored release_info, reproducing the old
    # select_subtitle_file() intent: choose the filename whose tokens overlap the
    # provider's release_info and avoid forced tracks. Listing only, no extraction or
    # decoding: the host reads the named member and runs chardet. Returns None for rar
    # (not stdlib-listable), a single member (nothing to disambiguate), the requested
    # episode being absent, or no unique overlap winner, so the caller falls back to
    # host-side episode selection.
    payload = payload or {}
    if _is_rar_archive(body) or not zipfile.is_zipfile(io.BytesIO(body)):
        return None
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        members = [
            name
            for name in archive.namelist()
            if not name.endswith("/")
            and _subtitle_extension(name)
            and not name.rsplit("/", 1)[-1].startswith(".")
        ]
    if len(members) < 2:
        return None  # a lone member: the host's episode pick already lands here
    # Narrow to the requested episode first; the host can already do this, but a pack with
    # several releases per episode leaves it guessing among the matches.
    season = _safe_int(payload.get("season"))
    episode = _safe_int(payload.get("episode"))
    pool = members
    if season is not None and episode is not None:
        episode_pool = [name for name in members if _member_matches_episode(name, season, episode)]
        if episode_pool:
            pool = episode_pool
        elif any(_member_has_episode_marker(name) for name in members):
            # Episode markers present but none matches the requested one: pinning a member
            # from another episode would hard-fail the host download, so defer.
            return None
    if len(pool) < 2:
        return None  # a single candidate: host episode selection already lands here
    # Score by release_info token overlap and avoid forced tracks, then pin only a unique
    # winner with a positive score. Ties or no overlap mean defer to the host.
    release_tokens = set(_tokens(payload.get("release_info")))
    if not release_tokens:
        return None  # nothing to disambiguate on; let the host pick by episode
    best, best_score, tied = None, 0, False
    for name in pool:
        score = _member_release_score(name, release_tokens)
        if score > best_score:
            best, best_score, tied = name, score, False
        elif score == best_score and best is not None:
            tied = True
    if best is None or best_score <= 0 or tied:
        return None  # cannot confidently disambiguate; let the host pick by episode
    return best


def _member_release_score(name, release_tokens):
    # Mirror the old select_subtitle_file scoring: overlap count between the release_info
    # tokens and the member filename tokens, with a heavy penalty for forced tracks so a
    # forced sidecar never outranks the main subtitle.
    name_tokens = set(_tokens(name))
    score = len(release_tokens.intersection(name_tokens))
    if "forced" in name_tokens:
        score -= 5
    return score


def _member_matches_episode(name, season, episode):
    # Tolerate separated SxxExx tokens (S01.E02, S01 E02, S01-E02) as well as contiguous
    # S01E02; keep (?!\d) so "e02" never matches "e020".
    text = (name or "").lower()
    if re.search(rf"s0*{season}[\s._-]*e0*{episode}(?!\d)", text):
        return True
    if re.search(rf"(?<!\d){season}x0*{episode}(?!\d)", text):
        return True
    # Whole-token NNN form (e.g. S07E20 written as "720"): compare against delimited
    # tokens so "720" never matches inside "720p" and "264" never matches "x264".
    compact = f"{season}{episode:02d}"
    return compact in _tokens(name)


def _member_has_episode_marker(name):
    text = (name or "").lower()
    if re.search(r"s\d{1,2}[\s._-]*e\d{1,3}", text) or re.search(r"(?<!\d)\d{1,2}x\d{1,3}", text):
        return True
    return any(token.isdigit() and len(token) == 3 for token in _tokens(name))


def _result_from_row(video, row, fps, config):
    video = video or {}
    matches = derive_matches(video, row, fps, config)
    score = 1 if not matches and config.get("skip_wrong_fps") else min(100, 45 + len(matches) * 10 + (10 if row["approved"] else 0))
    language = row["language"]
    filename = f"titulky.{row['subtitle_id']}.{language['alpha2']}.zip"
    return {
        "provider": PROVIDER_ID,
        "id": f"titulky-{row['subtitle_id']}-{language['alpha3']}",
        "language": {"alpha3": language["alpha3"], "alpha2": language["alpha2"], "hi": False, "forced": False},
        "release_info": row["release_info"],
        "filename": filename,
        "matches": matches,
        "score": score,
        "score_without_hash": score,
        "score_out_of": 100,
        "hash_verifiable": False,
        "hearing_impaired_verifiable": False,
        "hearing_impaired": False,
        "page_link": row["details_link"],
        "display": {
            "source": "titulky.com",
            "release": row["release_info"],
            "uploader": row["uploader"],
            "approved": row["approved"],
            "fps": fps,
        },
        "provider_payload": {
            "provider": PROVIDER_ID,
            "schema": 1,
            "subtitle_id": row["subtitle_id"],
            "download_url": row["download_url"],
            "page_link": row["details_link"],
            "filename": filename,
            "release_info": row["release_info"],
            "language": language["alpha3"],
            "season": _safe_int(video.get("season")) if video.get("kind") == "episode" else None,
            "episode": row.get("episode"),
            "fps": fps,
        },
    }


def derive_matches(video, row, fps, config):
    if config.get("skip_wrong_fps") and video.get("fps") and fps and not _framerate_equal(video.get("fps"), fps):
        return []
    matches = []
    if video.get("kind") == "episode":
        if video.get("series_imdb_id") and video.get("series_imdb_id") == row.get("imdb_id", video.get("series_imdb_id")):
            matches.extend(["series_imdb_id", "series", "year"])
        if _safe_int(video.get("season")) is not None:
            matches.append("season")
        if _safe_int(video.get("episode")) == row.get("episode"):
            matches.append("episode")
    else:
        if video.get("imdb_id"):
            matches.extend(["imdb_id", "title", "year"])
    release_tokens = set(_tokens(row.get("release_info")))
    resolution = _coerce_text(video.get("resolution")).lower()
    if resolution and resolution in row.get("release_info", "").lower():
        matches.append("resolution")
    source_tokens = _tokens(video.get("source"))
    if source_tokens and all(token in release_tokens for token in source_tokens):
        matches.append("source")
    release_group = _normalize(video.get("release_group"))
    if release_group and release_group in release_tokens:
        matches.append("release_group")
    return matches


def _validated_config(config):
    config = dict(config or {})
    if not config.get("username") or not config.get("password"):
        raise PermissionError("Titulky username and password are required")
    for key in ("approved_only", "skip_wrong_fps"):
        if key not in config:
            config[key] = False
        if type(config[key]) is not bool:
            raise ValueError(f"{key} must be a boolean")
    return config


def _requested_languages(languages):
    requested = []
    seen = set()
    for language in languages or []:
        item = _language_for_request(language)
        if not item or item["alpha3"] in seen:
            continue
        seen.add(item["alpha3"])
        requested.append(item)
    return requested


def _language_for_request(language):
    if not isinstance(language, dict):
        return None
    alpha3 = (language.get("alpha3") or "").lower()
    alpha2 = (language.get("alpha2") or "").lower()
    if alpha3 in LANGUAGES:
        return LANGUAGES[alpha3]
    if alpha2 == "cs":
        return LANGUAGES["ces"]
    if alpha2 == "sk":
        return LANGUAGES["slk"]
    return None


def _language_from_row(row):
    lowered = row.lower()
    if b"flag-cz" in lowered and b"flag-sk" not in lowered:
        return LANGUAGES["ces"]
    if b"flag-sk" in lowered and b"flag-cz" not in lowered:
        return LANGUAGES["slk"]
    return None


def _language_key(language):
    return language.get("alpha3")


def _uploader_from_row(row):
    spans = [_strip_tags(match.group("value")) for match in _SPAN_RE.finditer(row or b"")]
    return spans[-1] if spans else ""


def _imdb_id(video):
    imdb_id = _coerce_text(video.get("series_imdb_id") if video.get("kind") == "episode" else video.get("imdb_id"))
    return imdb_id if imdb_id.startswith("tt") else ""


def _framerate_equal(first, second):
    try:
        first = float(first)
        second = float(second)
    except (TypeError, ValueError):
        return True
    if first == second:
        return True
    if 23.97 <= first <= 24.0 and 23.97 <= second <= 24.0:
        return True
    return False


def _is_rar_archive(body):
    return bool(body) and (
        body.startswith(b"Rar!\x1a\x07\x00")
        or body.startswith(b"Rar!\x1a\x07\x01\x00")
    )


def _subtitle_extension(name):
    lowered = (name or "").lower()
    for extension in SUBTITLE_EXTENSIONS:
        if lowered.endswith(extension):
            return extension[1:]
    return None


def _direct_subtitle_format(body, payload):
    subtitle_format = _subtitle_extension((payload or {}).get("filename", ""))
    if subtitle_format:
        return subtitle_format
    sample = _decode((body or b"")[:4096]).lstrip()
    if sample.upper().startswith("WEBVTT"):
        return "vtt"
    if "[Script Info]" in sample or "[Events]" in sample:
        return "ass"
    if "-->" in sample:
        return "srt"
    return None


def _content_payload(content, subtitle_format):
    # Do not guess an encoding. The host runs chardet via Subtitle.normalize(); a worker
    # guess (especially a legacy codepage that never fails to decode) only reintroduces
    # mojibake. Leave encoding unset and let the host normalize.
    content = _fix_line_endings(content)
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
    return "application/x-subrip"


def _fix_line_endings(content):
    return (content or b"").replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _looks_like_html(body):
    sample = (body or b"")[:512].lstrip().lower()
    return sample.startswith(b"<!doctype html") or sample.startswith(b"<html") or b"<body" in sample


def _open_with_retry(opener, request, timeout):
    # Bounded transport retry around the raw urllib call only. Transient blips
    # (connection reset/DNS/refused, timeouts, 5xx, 429) get up to
    # RETRY_MAX_ATTEMPTS tries with exponential backoff; the final failure is
    # re-raised so the caller's existing error handling runs unchanged. Anything
    # non-transient (4xx other than 429, parse/auth errors) propagates on the
    # first occurrence because it is never matched here.
    last_error = None
    for attempt in range(1, RETRY_MAX_ATTEMPTS + 1):
        try:
            return opener.open(request, timeout=timeout)
        except urllib.error.HTTPError as error:
            if not _is_retryable_status(error.code) or attempt >= RETRY_MAX_ATTEMPTS:
                raise
            delay = _retry_after_seconds(error) if error.code == 429 else None
            error.close()
            last_error = error
        except (urllib.error.URLError, socket.timeout, TimeoutError) as error:
            if attempt >= RETRY_MAX_ATTEMPTS:
                raise
            delay = None
            last_error = error
        _sleep_backoff(attempt, delay)
    # Unreachable in practice: the loop either returns, retries, or re-raises.
    raise last_error


def _is_retryable_status(code):
    code = int(code or 0)
    return code == 429 or 500 <= code <= 599


def _retry_after_seconds(error):
    headers = getattr(error, "headers", None)
    value = _header(headers, "retry-after") if headers else ""
    seconds = _float(value)
    if seconds is None or seconds < 0:
        return None
    return min(seconds, RETRY_BACKOFF_CAP_SECONDS)


def _backoff_delay(attempt):
    return min(RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1)), RETRY_BACKOFF_CAP_SECONDS)


def _sleep_backoff(attempt, override=None):
    delay = override if override is not None else _backoff_delay(attempt)
    if delay > 0:
        time.sleep(delay)


def _http_error_response(error, url):
    headers = error.headers if getattr(error, "headers", None) else {}
    try:
        body = error.read()
    finally:
        error.close()
    return HttpResponse(error.code, body, headers, url)


def _raise_for_status(response, url):
    if response.status_code >= 400:
        raise urllib.error.HTTPError(url, response.status_code, f"HTTP {response.status_code}", response.headers, None)


def _sort_results(results):
    return sorted(results, key=lambda item: item["score"], reverse=True)


def _sleep(config):
    delay_ms = (config or {}).get("request_delay_ms", 0) or 0
    if delay_ms > 0:
        time.sleep(min(delay_ms, 5000) / 1000.0)


def _header(headers, name):
    values = _header_values(headers, name)
    return values[-1] if values else ""


def _header_values(headers, name):
    wanted = name.lower()
    if not headers:
        return []
    if hasattr(headers, "get_all"):
        return [str(value) for value in (headers.get_all(name) or headers.get_all(wanted) or [])]
    if isinstance(headers, dict):
        values = []
        for key, value in headers.items():
            if str(key).lower() == wanted:
                if isinstance(value, (list, tuple)):
                    values.extend(str(item) for item in value)
                else:
                    values.append(str(value))
        return values
    values = []
    for key, value in headers:
        if str(key).lower() == wanted:
            values.append(str(value))
    return values


def _strip_tags(value):
    stripped = _TAG_RE.sub(b"", value or b"")
    stripped = _WS_BYTES_RE.sub(b" ", stripped).strip()
    return _WS_RE.sub(" ", html.unescape(_decode(stripped))).strip()


def _tokens(value):
    return [token for token in _normalize(value).split(" ") if token]


def _normalize(value):
    if value is None:
        return ""
    decomposed = unicodedata.normalize("NFKD", str(value))
    folded = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return _NON_ALNUM_RE.sub(" ", folded.lower()).strip()


def _coerce_text(value):
    if value is None:
        return ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    return html.unescape(str(value)).strip()


def _safe_int(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _float(value):
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _decode(value):
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return value.decode("utf-8", errors="replace")
