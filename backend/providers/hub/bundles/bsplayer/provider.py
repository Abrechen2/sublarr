"""BSPlayer subtitles provider for the Bazarr+ Provider Hub catalog."""

import base64
import gzip
import hashlib
import html
import os
import re
import socket
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

PROVIDER_ID = "bsplayer"
SOAP_NAMESPACE = "http://api.bsplayer-subtitles.com/v1.php"
USER_AGENT = "BSPlayer/2.x (1022.12360)"
DOWNLOAD_USER_AGENT = "Mozilla/4.0 (compatible; Synapse)"
DEFAULT_TIMEOUT_SECONDS = 12
RETRY_MAX_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 0.5
RETRY_BACKOFF_CAP_SECONDS = 8
RETRY_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
SUBDOMAINS = (
    "s1",
    "s2",
    "s3",
    "s4",
    "s5",
    "s6",
    "s7",
    "s8",
    "s101",
    "s102",
    "s103",
    "s104",
    "s105",
    "s106",
    "s107",
    "s108",
    "s109",
)
SUBTITLE_FORMATS = {"srt", "ass", "ssa", "sub", "vtt", "txt"}
SUPPORTED_LANGUAGE_CODES = {
    "ara",
    "bul",
    "ces",
    "dan",
    "deu",
    "ell",
    "eng",
    "fin",
    "fra",
    "hun",
    "ita",
    "jpn",
    "kor",
    "nld",
    "pol",
    "por",
    "ron",
    "rus",
    "spa",
    "swe",
    "tur",
    "ukr",
    "zho",
}
ALPHA3_TO_BSPLAYER = {
    "ara": "ara",
    "bul": "bul",
    "ces": "cze",
    "cze": "cze",
    "dan": "dan",
    "deu": "ger",
    "ger": "ger",
    "ell": "ell",
    "gre": "ell",
    "eng": "eng",
    "fin": "fin",
    "fra": "fre",
    "fre": "fre",
    "hun": "hun",
    "ita": "ita",
    "jpn": "jpn",
    "kor": "kor",
    "nld": "dut",
    "dut": "dut",
    "pol": "pol",
    "por": "por",
    "pob": "pob",
    "ron": "rum",
    "rum": "rum",
    "rus": "rus",
    "spa": "spa",
    "swe": "swe",
    "tur": "tur",
    "ukr": "ukr",
    "zho": "chi",
    "chi": "chi",
}
BSPLAYER_TO_ALPHA3 = {
    "ara": "ara",
    "bul": "bul",
    "cze": "ces",
    "dan": "dan",
    "ger": "deu",
    "ell": "ell",
    "gre": "ell",
    "eng": "eng",
    "fin": "fin",
    "fre": "fra",
    "hun": "hun",
    "ita": "ita",
    "jpn": "jpn",
    "kor": "kor",
    "dut": "nld",
    "pol": "pol",
    "por": "por",
    "pob": "por",
    "rum": "ron",
    "rus": "rus",
    "spa": "spa",
    "swe": "swe",
    "tur": "tur",
    "ukr": "ukr",
    "chi": "zho",
}
ALPHA3_TO_ALPHA2 = {
    "ara": "ar",
    "bul": "bg",
    "ces": "cs",
    "dan": "da",
    "deu": "de",
    "ell": "el",
    "eng": "en",
    "fin": "fi",
    "fra": "fr",
    "hun": "hu",
    "ita": "it",
    "jpn": "ja",
    "kor": "ko",
    "nld": "nl",
    "pol": "pl",
    "por": "pt",
    "ron": "ro",
    "rus": "ru",
    "spa": "es",
    "swe": "sv",
    "tur": "tr",
    "ukr": "uk",
    "zho": "zh",
}


def _retry_status_for_error(exc):
    """Return the HTTP status that makes a urllib failure retryable, else None.

    Only transient transport failures qualify: connection level URLError,
    socket/timeout errors, and HTTP 5xx / 429. A urllib.error.HTTPError with a
    4xx code other than 429 is not transient and must propagate unchanged.
    """
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code if exc.code in RETRY_STATUS_CODES else None
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return 0
    if isinstance(exc, urllib.error.URLError):
        return 0
    return None


def _retry_after_seconds(exc):
    """Return a Retry-After delay from a 429 response header, capped, or None."""
    if not isinstance(exc, urllib.error.HTTPError):
        return None
    headers = getattr(exc, "headers", None)
    if headers is None:
        return None
    value = headers.get("Retry-After")
    if not value:
        return None
    try:
        seconds = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    if seconds < 0:
        return None
    return min(seconds, RETRY_BACKOFF_CAP_SECONDS)


def _backoff_seconds(attempt):
    delay = RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1))
    return min(delay, RETRY_BACKOFF_CAP_SECONDS)


def _urlopen_read(request, timeout):
    """Open ``request`` and read the body, retrying transient transport errors.

    Wraps urllib with a bounded retry loop (RETRY_MAX_ATTEMPTS total). Only
    transient failures are retried; everything else propagates on the first
    occurrence exactly as before. The final transient failure is re-raised
    unchanged so callers keep their existing error handling.
    """
    last_exc = None
    for attempt in range(1, RETRY_MAX_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
                return response.read()
        except Exception as exc:  # noqa: BLE001 - re-raised below if not retryable
            status = _retry_status_for_error(exc)
            if status is None or attempt >= RETRY_MAX_ATTEMPTS:
                raise
            last_exc = exc
            retry_after = _retry_after_seconds(exc) if status == 429 else None
            delay = retry_after if retry_after is not None else _backoff_seconds(attempt)
            if delay > 0:
                time.sleep(delay)
    # Unreachable: the loop either returns or raises, but keep mypy/readers happy.
    raise last_exc


class BSPlayerServiceError(RuntimeError):
    """Raised when the BSPlayer SOAP service cannot be queried."""


class BSPlayerApiClient:
    def __init__(self, api_url=None, timeout=DEFAULT_TIMEOUT_SECONDS):
        self.api_url = _normalize_api_url(api_url) if api_url else None
        self.timeout = int(timeout or DEFAULT_TIMEOUT_SECONDS)

    def request(self, func_name, params):
        errors = []
        for url in self._candidate_urls():
            try:
                body = self._post(url, func_name, params)
            except OSError as exc:
                errors.append(str(exc))
                continue
            self.api_url = url
            return body
        message = "; ".join(errors[-3:]) if errors else "no BSPlayer API endpoint available"
        raise BSPlayerServiceError(message)

    def get_bytes(self, url):
        request = urllib.request.Request(
            str(url),
            headers={"User-Agent": DOWNLOAD_USER_AGENT},
        )
        return _urlopen_read(request, timeout=max(self.timeout, 30))

    def _candidate_urls(self):
        if self.api_url:
            yield self.api_url
            return
        for domain in SUBDOMAINS:
            yield f"http://{domain}.api.bsplayer-subtitles.com/v1.php"

    def _post(self, url, func_name, params):
        body = _soap_envelope(func_name, params).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            headers={
                "User-Agent": USER_AGENT,
                "Content-Type": "text/xml; charset=utf-8",
                "Connection": "close",
                "SOAPAction": f'"{SOAP_NAMESPACE}#{func_name}"',
            },
        )
        return _urlopen_read(request, timeout=self.timeout)


def _normalize_api_url(api_url):
    value = str(api_url or "").strip()
    if not value:
        return None
    if not value.startswith(("http://", "https://")):
        value = "http://" + value
    if not value.endswith("/v1.php"):
        value = value.rstrip("/") + "/v1.php"
    return value


def _soap_envelope(func_name, params):
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/" '
        'xmlns:SOAP-ENC="http://schemas.xmlsoap.org/soap/encoding/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        'xmlns:xsd="http://www.w3.org/2001/XMLSchema" '
        f'xmlns:ns1="{SOAP_NAMESPACE}">'
        '<SOAP-ENV:Body SOAP-ENV:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
        f"<ns1:{func_name}>{params}</ns1:{func_name}>"
        "</SOAP-ENV:Body></SOAP-ENV:Envelope>"
    )


def _xml_root(body):
    try:
        return ET.fromstring(body)
    except ET.ParseError as exc:
        raise BSPlayerServiceError("BSPlayer returned invalid XML") from exc


def _local_name(tag):
    return str(tag).rsplit("}", 1)[-1]


def _children(element, name):
    return [child for child in list(element) if _local_name(child.tag) == name]


def _first_child(element, name):
    for child in list(element):
        if _local_name(child.tag) == name:
            return child
    return None


def _first_text(element, name):
    child = _first_child(element, name)
    if child is None or child.text is None:
        return ""
    return html.unescape(str(child.text)).strip()


def _iter_nodes(root, name):
    for element in root.iter():
        if _local_name(element.tag) == name:
            yield element


def parse_login_token(body):
    root = _xml_root(body)
    for result in _iter_nodes(root, "return"):
        if _first_text(result, "status").upper() == "OK":
            token = _first_text(result, "data")
            if token:
                return token
    raise BSPlayerServiceError("BSPlayer login failed")


def parse_search_response(body):
    root = _xml_root(body)
    search_result = next(_iter_nodes(root, "return"), None)
    if search_result is None:
        return []
    result_node = _first_child(search_result, "result")
    if result_node is not None and _first_text(result_node, "status").upper() != "OK":
        return []
    data_node = _first_child(search_result, "data")
    if data_node is None:
        return []
    items = []
    for item in _children(data_node, "item"):
        sub_id = _first_text(item, "subID")
        download_url = _first_text(item, "subDownloadLink")
        language_code = _first_text(item, "subLang")
        filename = _first_text(item, "subName")
        fmt = _first_text(item, "subFormat") or _format_from_filename(filename)
        if not sub_id or not download_url or not language_code:
            continue
        items.append(
            {
                "sub_id": sub_id,
                "download_url": download_url,
                "language_code": language_code,
                "filename": filename or f"bsplayer-{sub_id}.{fmt}",
                "format": fmt,
            }
        )
    return items


def bsplayer_language_code(language):
    payload = _language_payload(language)
    alpha3 = str(payload.get("alpha3") or "").lower()
    country = str(payload.get("country") or payload.get("region") or "").upper()
    alpha2 = str(payload.get("alpha2") or "").lower()
    if alpha3 == "por" and (country == "BR" or alpha2 in {"pb", "pt-br", "pt_br"}):
        return "pob"
    return ALPHA3_TO_BSPLAYER.get(alpha3)


def _language_payload(language):
    if isinstance(language, dict):
        payload = dict(language)
    else:
        payload = {"alpha3": str(language)}
    alpha3 = str(payload.get("alpha3") or "").lower()
    if not alpha3 and payload.get("alpha2"):
        alpha3 = _alpha2_to_alpha3(str(payload["alpha2"]).lower())
    payload["alpha3"] = alpha3
    payload.setdefault("alpha2", ALPHA3_TO_ALPHA2.get(alpha3))
    payload.setdefault("hi", False)
    payload.setdefault("forced", False)
    return payload


def _alpha2_to_alpha3(alpha2):
    for alpha3, candidate in ALPHA3_TO_ALPHA2.items():
        if candidate == alpha2:
            return alpha3
    return alpha2


def _video_hash(video):
    hashes = (video or {}).get("hashes") or {}
    for key in ("bsplayer", "opensubtitles", "opensubtitlescom"):
        value = hashes.get(key)
        if value:
            return str(value).strip()
    return None


def _video_size(video):
    try:
        value = int((video or {}).get("size"))
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _imdb_id(video):
    value = (video or {}).get("series_imdb_id") if (video or {}).get("kind") == "episode" else (video or {}).get("imdb_id")
    return str(value).strip() if value else "*"


def _matches_for_video(video):
    if (video or {}).get("kind") == "episode":
        return ["series", "season", "episode", "year", "hash"]
    return ["title", "year", "hash"]


def _score_without_hash(matches):
    return 60 if any(match in matches for match in ("title", "series")) else 0


def _format_from_filename(filename):
    suffix = os.path.basename(str(filename or "")).rsplit(".", 1)
    if len(suffix) == 2:
        fmt = suffix[-1].lower()
        if fmt in SUBTITLE_FORMATS:
            return fmt
    return "srt"


def _download_response(content, fmt):
    return {
        "content_b64": base64.b64encode(content).decode("ascii") if content else "",
        "content_sha256": hashlib.sha256(content).hexdigest() if content else "",
        "content_type": "application/x-subrip",
        "format": fmt or "srt",
        "encoding": None,
        "empty": not bool(content),
    }


def _decode_download(body):
    if body.startswith(b"\x1f\x8b"):
        return gzip.decompress(body)
    return body


def _sleep_from_config(config):
    try:
        delay_ms = int((config or {}).get("request_delay_ms") or 0)
    except (TypeError, ValueError):
        delay_ms = 0
    if delay_ms > 0:
        time.sleep(min(delay_ms, 10000) / 1000.0)


def _escape_param(value):
    return html.escape(str(value), quote=False)


class BSPlayerProvider:
    def __init__(self, api_client=None):
        self.api_client = api_client

    def _client(self, config):
        if self.api_client is not None:
            return self.api_client
        config = dict(config or {})
        return BSPlayerApiClient(
            api_url=config.get("api_url"),
            timeout=config.get("timeout_seconds") or DEFAULT_TIMEOUT_SECONDS,
        )

    def search(self, video, languages, config):
        video = video or {}
        if video.get("kind") not in {"movie", "episode"}:
            return []
        video_hash = _video_hash(video)
        video_size = _video_size(video)
        if not video_hash or not video_size:
            return []

        requested = _requested_languages(languages)
        if not requested:
            return []

        client = self._client(config)
        token = parse_login_token(
            client.request(
                "logIn",
                "<username></username><password></password><AppID>BSPlayer v2.67</AppID>",
            )
        )
        try:
            _sleep_from_config(config)
            language_ids = ",".join(sorted(requested))
            params = (
                f"<handle>{_escape_param(token)}</handle>"
                f"<movieHash>{_escape_param(video_hash)}</movieHash>"
                f"<movieSize>{video_size}</movieSize>"
                f"<languageId>{_escape_param(language_ids)}</languageId>"
                f"<imdbId>{_escape_param(_imdb_id(video))}</imdbId>"
            )
            items = parse_search_response(client.request("searchSubtitles", params))
        finally:
            try:
                client.request("logOut", f"<handle>{_escape_param(token)}</handle>")
            except Exception:
                pass

        return [
            _candidate(item, video, _language_for_result(item["language_code"], languages))
            for item in items
            if item["language_code"] in requested
        ]

    def download(self, provider_payload, language, config):
        del language
        payload = dict(provider_payload or {})
        if payload.get("provider") != PROVIDER_ID:
            raise ValueError("BSPlayer payload belongs to a different provider")
        download_url = payload.get("download_url")
        if not download_url:
            raise ValueError("BSPlayer download requires download_url in provider_payload")
        body = self._client(config).get_bytes(download_url)
        if body == b"500":
            raise BSPlayerServiceError("BSPlayer download returned server error 500")
        content = _decode_download(body)
        return _download_response(content, payload.get("format") or _format_from_filename(payload.get("filename")))


def _requested_languages(languages):
    requested = {}
    for language in languages or []:
        payload = _language_payload(language)
        if payload.get("hi") or payload.get("forced"):
            continue
        code = bsplayer_language_code(payload)
        if code:
            requested[code] = payload
    return requested


def _language_for_result(language_code, requested_languages):
    target = str(language_code or "").lower()
    for language in requested_languages or []:
        if bsplayer_language_code(language) == target:
            return _language_payload(language)
    alpha3 = BSPLAYER_TO_ALPHA3.get(target, target)
    payload = {"alpha3": alpha3, "alpha2": ALPHA3_TO_ALPHA2.get(alpha3), "hi": False, "forced": False}
    if target == "pob":
        payload["country"] = "BR"
    return payload


def _candidate(item, video, language):
    matches = _matches_for_video(video)
    fmt = item.get("format") or _format_from_filename(item.get("filename"))
    return {
        "provider": PROVIDER_ID,
        "id": f"bsplayer-{item['sub_id']}",
        "language": language,
        "release_info": item.get("filename") or f"BSPlayer {item['sub_id']}",
        "filename": item.get("filename") or f"bsplayer-{item['sub_id']}.{fmt}",
        "matches": matches,
        "score": 100,
        "score_without_hash": _score_without_hash(matches),
        "score_out_of": 100,
        "hash_verifiable": True,
        "hearing_impaired_verifiable": False,
        "hearing_impaired": False,
        "display": {
            "source": "api.bsplayer-subtitles.com",
            "format": fmt,
        },
        "provider_payload": {
            "provider": PROVIDER_ID,
            "schema": 1,
            "subtitle_id": item["sub_id"],
            "download_url": item["download_url"],
            "filename": item.get("filename") or "",
            "format": fmt,
        },
    }


def _clean_xml_text(value):
    return re.sub(r"\s+", " ", html.unescape(str(value or ""))).strip()
