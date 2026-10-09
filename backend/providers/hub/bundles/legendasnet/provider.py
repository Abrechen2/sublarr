"""Legendas.net provider for the Bazarr+ Provider Hub catalog."""

import base64
import hashlib
import html
import io
import json
import os
import re
import socket
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import zipfile

PROVIDER_ID = "legendasnet"
BASE_URL = "https://legendas.net"
API_URL = f"{BASE_URL}/api/v1"
HTTP_TIMEOUT_SECONDS = 30
# Transport-level retry for transient network blips only (mirrors upstream
# subliminal's RetryingSession/ProviderRetryMixin: a few tries with backoff).
HTTP_MAX_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 0.5
RETRY_BACKOFF_CAP_SECONDS = 8.0
# HTTP statuses worth retrying: throttling (429) and server-side faults (5xx).
RETRY_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 BazarrProviderHub"
)
LANGUAGE = {"alpha3": "por", "alpha2": "pt", "country_alpha2": "BR"}
SUBTITLE_EXTENSIONS = (".srt", ".ass", ".ssa", ".sub", ".vtt")
_NON_ALNUM_RE = re.compile(r"[\W_]+", re.UNICODE)


class HttpResponse:
    def __init__(self, status, body, headers):
        self.status = int(status)
        self.body = body or b""
        self.headers = dict(headers or {})


def _perform_request(request, timeout):
    # One raw attempt. Preserves the original error-to-response conversion: an
    # HTTPError still becomes an HttpResponse carrying its status/body/headers,
    # so 4xx/5xx/429 keep flowing back to the existing status-mapping callers.
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return HttpResponse(response.status, response.read(), dict(response.headers.items()))
    except urllib.error.HTTPError as error:
        try:
            return HttpResponse(error.code, error.read(), dict(error.headers.items()))
        finally:
            error.close()


def _request_with_retry(request, timeout):
    # Bounded retry around the raw transport only. Retries transient transport
    # exceptions (connection reset/refused, DNS, timeouts) and transient HTTP
    # statuses (429 + 5xx); everything else (success, 4xx) returns on the first
    # attempt and any non-transient exception propagates unchanged.
    last_error = None
    for attempt in range(1, HTTP_MAX_ATTEMPTS + 1):
        try:
            response = _perform_request(request, timeout)
        except (urllib.error.URLError, socket.timeout, TimeoutError) as error:
            last_error = error
            if attempt >= HTTP_MAX_ATTEMPTS:
                raise
            time.sleep(_retry_delay(attempt))
            continue
        if response.status in RETRY_STATUS_CODES and attempt < HTTP_MAX_ATTEMPTS:
            time.sleep(_retry_delay(attempt, response))
            continue
        return response
    # Loop only falls through when the final attempt raised transiently.
    raise last_error


def _retry_delay(attempt, response=None):
    delay = RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1))
    if response is not None and response.status == 429:
        retry_after = _retry_after_seconds(response.headers)
        if retry_after is not None:
            delay = max(delay, retry_after)
    return min(delay, RETRY_BACKOFF_CAP_SECONDS)


def _retry_after_seconds(headers):
    for key, value in (headers or {}).items():
        if str(key).lower() != "retry-after":
            continue
        try:
            seconds = int(str(value).strip())
        except (TypeError, ValueError):
            return None
        return seconds if seconds >= 0 else None
    return None


class LegendasNetProvider:
    def __init__(self):
        self._access_token = None

    def search(self, video, languages, config):
        video = dict(video or {})
        if video.get("kind") not in {"movie", "episode"}:
            return []
        if not _language_requested(languages):
            return []
        config = dict(config or {})
        self._ensure_authenticated(config)
        if video.get("kind") == "episode":
            response = self._search_response(video, config)
            payload = _json_payload(response, "Legendas.net search")
            if _api_reports_empty(payload):
                return []
            items = _episode_items(payload, video)
            return [_candidate(video, item, "episode") for item in items]
        for response in self._movie_search_responses(video, config):
            payload = _json_payload(response, "Legendas.net search")
            if _api_reports_empty(payload):
                continue
            items = payload.get("movies") or []
            if items:
                return [_candidate(video, item, "movie") for item in items]
        return []

    def download(self, provider_payload, language, config):
        del language
        payload = dict(provider_payload or {})
        download_link = payload.get("download_link")
        if not download_link:
            raise ValueError("legendasnet download requires download_link")
        config = dict(config or {})
        self._ensure_authenticated(config)
        url = urllib.parse.urljoin(BASE_URL + "/", str(download_link).lstrip("/"))
        _sleep(config)
        response = self._authenticated_request(
            lambda: self._http_get(url, headers=self._headers(config), timeout=HTTP_TIMEOUT_SECONDS),
            config,
            "Invalid Legendas.net access token",
        )
        if response.status == 429:
            raise RuntimeError("Daily download limit exceeded")
        if response.status in {401, 403}:
            raise PermissionError("Invalid Legendas.net access token")
        _raise_for_status(response, "Legendas.net download")
        # Derive the real subtitle format from the server-provided source (the
        # actual download path and any Content-Disposition filename), not the
        # synthetic ".zip" name stored on the search candidate, so direct
        # ".ass"/".ssa"/".sub"/".vtt" downloads are not mislabeled as ".srt".
        disposition_name = _content_disposition_filename(response.headers)
        return _download_payload(response.body, disposition_name or str(download_link), payload)

    def _search_response(self, video, config):
        if video.get("kind") == "episode":
            url = f"{API_URL}/search/tv"
            body = {
                "page": 1,
                "per_page": 25,
                "tv_episode": _int_or_none(video.get("episode")),
                "tv_season": _int_or_none(video.get("season")),
            }
            imdb_id = _text(video.get("series_imdb_id"))
            if imdb_id:
                body["imdb_id"] = imdb_id
            else:
                body["name"] = _text(video.get("series"))
            return self._api_search_response(url, body, config)
        name = next(iter(_movie_search_names(video)), _text(video.get("title")))
        return self._movie_search_response(video, config, name)

    def _movie_search_responses(self, video, config):
        if _text(video.get("imdb_id")):
            yield self._movie_search_response(video, config, None)
            return
        for name in _movie_search_names(video):
            yield self._movie_search_response(video, config, name)

    def _movie_search_response(self, video, config, name):
        url = f"{API_URL}/search/movie"
        body = {
            "page": 1,
            "per_page": 25,
        }
        imdb_id = _text(video.get("imdb_id"))
        if imdb_id:
            body["imdb_id"] = imdb_id
        elif name:
            body["name"] = name
        return self._api_search_response(url, body, config)

    def _api_search_response(self, url, body, config):
        _sleep(config)
        response = self._authenticated_request(
            lambda: self._http_json(
                "GET",
                url,
                headers=self._headers(config),
                json_body=body,
                timeout=HTTP_TIMEOUT_SECONDS,
            ),
            config,
            "Invalid Legendas.net access token",
        )
        if response.status == 429:
            raise RuntimeError("Legendas.net API throttled")
        if response.status in {401, 403}:
            raise PermissionError("Invalid Legendas.net access token")
        if response.status == 404:
            raise RuntimeError("Legendas.net endpoint not found")
        _raise_for_status(response, "Legendas.net search")
        return response

    def _authenticated_request(self, request, config, failure_message):
        response = request()
        if response.status not in {401, 403}:
            return response

        self._access_token = None
        self._ensure_authenticated(config)
        response = request()
        if response.status in {401, 403}:
            self._access_token = None
            raise PermissionError(failure_message)
        return response

    def _ensure_authenticated(self, config):
        if self._access_token:
            return
        username = _text(config.get("username"))
        password = _text(config.get("password"))
        if not username or not password:
            raise PermissionError("Legendas.net username and password are required")
        response = self._http_json(
            "POST",
            f"{API_URL}/login",
            headers=self._headers(config, authenticated=False),
            json_body={"email": username, "password": password},
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        if response.status == 429:
            raise RuntimeError("Legendas.net API throttled")
        if response.status in {401, 403}:
            raise PermissionError("Invalid Legendas.net username or password")
        _raise_for_status(response, "Legendas.net login")
        payload = _json_payload(response, "Legendas.net login")
        token = _text(payload.get("access_token"))
        if not token:
            raise PermissionError("Legendas.net login did not return an access token")
        self._access_token = token

    def _headers(self, config, authenticated=True):
        headers = {
            "User-Agent": _text(config.get("user_agent")) or USER_AGENT,
            "Accept": "application/json,text/plain,*/*",
        }
        if authenticated and self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"
        return headers

    def _http_json(self, method, url, headers=None, json_body=None, timeout=HTTP_TIMEOUT_SECONDS):
        body = json.dumps(json_body or {}).encode("utf-8") if json_body is not None else None
        request_headers = dict(headers or {})
        request_headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=body, headers=request_headers, method=method)
        return _request_with_retry(request, timeout)

    def _http_get(self, url, headers=None, timeout=HTTP_TIMEOUT_SECONDS):
        request = urllib.request.Request(url, headers=dict(headers or {}), method="GET")
        return _request_with_retry(request, timeout)


def _download_payload(body, filename, provider_payload):
    provider_payload = provider_payload or {}
    # Reject broken responses: a 200 with an empty stream or an HTML/error page
    # would otherwise look like a successful download but yields no subtitle.
    if not body or not body.strip():
        raise ValueError("legendasnet download returned an empty body")
    if _is_html_body(body):
        raise ValueError("legendasnet download returned an HTML/error page")
    stream = io.BytesIO(body)
    if zipfile.is_zipfile(stream):
        # Host-side extraction (Provider Hub v1.1+): the provider still lists the
        # zip cheaply with stdlib to pick the member, but hands the raw archive
        # back to the host, which extracts it and detects the encoding.
        with zipfile.ZipFile(stream) as archive:
            member = _first_subtitle_file(archive.namelist())
        return _archive_payload(body, member=member)
    if _is_rar_archive(body) or _is_7z_archive(body):
        # No stdlib listing for rar/7z; let the host pick the member by episode.
        return _archive_payload(body, episode=provider_payload.get("episode"))
    # Direct, non-archive subtitle body.
    return _content_payload(body, _direct_format(filename, body))


def _archive_payload(body, member=None, episode=None):
    payload = {
        "archive_b64": base64.b64encode(body).decode("ascii"),
        "archive_sha256": hashlib.sha256(body).hexdigest(),
    }
    if member is not None:
        payload["member"] = member
    else:
        payload["episode"] = episode
    return payload


def _direct_format(filename, body):
    # Prefer the real extension carried by the server filename/path. Only fall
    # back to sniffing the bytes when the source name has no subtitle extension,
    # so we never report ".srt" for a direct ".ass"/".ssa"/".sub"/".vtt" file.
    extension = _subtitle_extension(filename or "")
    if extension:
        return extension
    return _format_from_content(body) or "srt"


def _format_from_content(body):
    head = (body or b"")[:512].lstrip(b"\xef\xbb\xbf").lstrip()
    lowered = head.lower()
    if lowered.startswith(b"webvtt"):
        return "vtt"
    if lowered.startswith(b"[script info]") or b"\n[script info]" in lowered:
        return "ass"
    return None


def _content_disposition_filename(headers):
    value = ""
    for key, header_value in (headers or {}).items():
        if str(key).lower() == "content-disposition":
            value = str(header_value or "")
            break
    if not value:
        return ""
    match = re.search(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)\"?", value, re.IGNORECASE)
    if not match:
        return ""
    return urllib.parse.unquote(match.group(1)).strip()


def _candidate(video, item, kind):
    forced = _is_forced(item)
    release_info = _text(item.get("release_name")) or "Legendas.net subtitle"
    file_id = item.get("id")
    tmdb_id = item.get("tmdb_id")
    if kind == "episode":
        page_link = f"{BASE_URL}/tv_legenda?movie_id={tmdb_id}&legenda_id={file_id}"
    else:
        page_link = f"{BASE_URL}/legenda?movie_id={tmdb_id}&legenda_id={file_id}"
    matches = derive_matches(video, item, kind)
    score = _score(matches)
    language = dict(LANGUAGE, hi=False, forced=forced)
    filename = f"legendasnet.{file_id or _slug(release_info)}.pt-br.zip"
    return {
        "provider": PROVIDER_ID,
        "id": f"legendasnet-{file_id}-por-BR",
        "language": language,
        "release_info": release_info,
        "filename": filename,
        "matches": matches,
        "score": score,
        "score_without_hash": score,
        "score_out_of": 100,
        "hash_verifiable": False,
        "hearing_impaired_verifiable": False,
        "hearing_impaired": False,
        "page_link": page_link,
        "display": {
            "source": "legendas.net",
            "release": release_info,
            "uploader": item.get("uploader") or "",
            "forced": forced,
        },
        "provider_payload": {
            "provider": PROVIDER_ID,
            "schema": 1,
            "file_id": file_id,
            "download_link": item.get("path") or "",
            "filename": filename,
            "language": "por-BR",
            "forced": forced,
            "release_info": release_info,
            "page_link": page_link,
            # Carried for host-side member selection when the archive is rar/7z
            # (which the worker cannot list with stdlib zipfile).
            "season": _int_or_none(item.get("season")) if kind == "episode" else None,
            "episode": _int_or_none(item.get("episode")) if kind == "episode" else None,
        },
    }


def derive_matches(video, item, kind):
    video = video or {}
    release_info = _text(item.get("release_name"))
    release_tokens = _release_tokens(release_info)
    matches = []
    if kind == "episode":
        matches.extend(["series", "series_imdb_id"])
        if _int_or_none(video.get("season")) == _int_or_none(item.get("season")):
            matches.append("season")
        if _int_or_none(video.get("episode")) == _int_or_none(item.get("episode")):
            matches.append("episode")
    else:
        matches.extend(["title", "imdb_id"])
        if video.get("year") and str(video.get("year")) in release_tokens:
            matches.append("year")
    for key in ("source", "resolution", "video_codec", "audio_codec", "release_group"):
        value = video.get(key)
        if value and _contains_release_value(release_tokens, value):
            matches.append(key)
    return _unique(matches)


def _episode_items(payload, video):
    wanted_season = _int_or_none((video or {}).get("season"))
    wanted_episode = _int_or_none((video or {}).get("episode"))
    items = []
    for item in payload.get("tv_shows") or []:
        if _int_or_none(item.get("season")) != wanted_season:
            continue
        if _int_or_none(item.get("episode")) != wanted_episode:
            continue
        items.append(item)
    return items


def _language_requested(languages):
    for language in languages or []:
        if not isinstance(language, dict):
            continue
        alpha3 = _text(language.get("alpha3"))
        country = _text(language.get("country") or language.get("country_alpha2")).upper()
        if alpha3 in {"por-BR", "pob"}:
            return True
        if alpha3 == "por" and country == "BR":
            return True
    return False


def _movie_search_names(video):
    names = []

    def add(value):
        text = _text(value)
        if text and text not in names:
            names.append(text)

    video = video or {}
    add(video.get("title"))
    add(video.get("original_title"))
    for key in ("alternative_titles", "alternative_title"):
        value = video.get(key)
        if isinstance(value, (list, tuple, set)):
            for item in value:
                add(item)
        else:
            add(value)
    return names


def _is_forced(item):
    comment = _normalize((item or {}).get("comment"))
    return "forced" in comment or "foreign" in comment


def _api_reports_empty(payload):
    if payload.get("success") is False:
        return True
    if payload.get("status") is False:
        return True
    return False


def _json_payload(response, context):
    try:
        return json.loads((response.body or b"{}").decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError(f"{context}: invalid JSON response") from error


def _raise_for_status(response, context):
    if response.status >= 400:
        raise RuntimeError(f"{context}: HTTP {response.status}")


def _first_subtitle_file(names):
    subtitle_names = [name for name in names if _subtitle_extension(name) and not os.path.basename(name).startswith(".")]
    if subtitle_names:
        return subtitle_names[0]
    if names:
        return names[0]
    raise ValueError("legendasnet archive contains no files")


def _is_rar_archive(body):
    return bool(body) and (body.startswith(b"Rar!\x1a\x07\x00") or body.startswith(b"Rar!\x1a\x07\x01\x00"))


def _is_7z_archive(body):
    return bool(body) and body.startswith(b"7z\xbc\xaf\x27\x1c")


def _is_html_body(body):
    if not body:
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


def _content_payload(content, subtitle_format):
    # Do not guess an encoding. The host runs chardet via Subtitle.normalize(); a
    # worker guess (especially latin-1, which never fails to decode) only
    # reintroduces mojibake. Leave encoding unset and let the host normalize.
    content = _normalize_line_endings(content or b"")
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


def _normalize_line_endings(content):
    return (content or b"").replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _subtitle_extension(name):
    lowered = (name or "").lower()
    for extension in SUBTITLE_EXTENSIONS:
        if lowered.endswith(extension):
            return extension[1:]
    return None


def _score(matches):
    weights = {
        "title": 25,
        "imdb_id": 25,
        "series": 20,
        "series_imdb_id": 25,
        "season": 10,
        "episode": 15,
        "year": 8,
        "release_group": 8,
        "source": 4,
        "resolution": 4,
        "video_codec": 3,
        "audio_codec": 3,
    }
    return min(100, 30 + sum(weights.get(match, 0) for match in matches))


def _contains_release_value(release_tokens, value):
    wanted = _release_tokens(value)
    return bool(wanted) and all(token in release_tokens for token in wanted)


def _release_tokens(value):
    return {token for token in re.split(r"[^A-Za-z0-9]+", str(value or "").lower()) if token}


def _normalize(value):
    text = str(value or "")
    decomposed = unicodedata.normalize("NFKD", text)
    folded = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return _NON_ALNUM_RE.sub(" ", folded.lower()).strip()


def _slug(value):
    slug = "-".join(token for token in _normalize(value).split() if token)[:80].strip("-")
    return slug or "subtitle"


def _text(value):
    if value is None:
        return ""
    if isinstance(value, str):
        return html.unescape(value).strip()
    return str(value).strip()


def _int_or_none(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _sleep(config):
    try:
        delay_ms = int((config or {}).get("request_delay_ms") or 0)
    except (TypeError, ValueError):
        delay_ms = 0
    if delay_ms > 0:
        time.sleep(min(delay_ms, 5000) / 1000.0)


def _unique(values):
    seen = set()
    result = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
