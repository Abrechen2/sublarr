import base64
import hashlib
import json
import os
import struct
from urllib import error, parse, request


PROVIDER_ID = "subtis"
API_BASE_URL = "https://api.subt.is/v1"
_SUPPORTED_MEDIA = {"movie"}
_DEFAULT_TIMEOUT = 10
_DOWNLOAD_TIMEOUT = 30


class SubtisNotFound(ValueError):
    pass


class SubtisHttpClient:
    def __init__(self, timeout=_DEFAULT_TIMEOUT, download_timeout=_DOWNLOAD_TIMEOUT):
        self.timeout = int(timeout)
        self.download_timeout = int(download_timeout)

    def get_json(self, url):
        req = request.Request(
            str(url),
            headers={
                "Accept": "application/json",
                "User-Agent": "BazarrProviderHub/Subtis/1.0",
            },
        )
        try:
            with request.urlopen(req, timeout=self.timeout) as response:  # noqa: S310
                body = response.read()
        except error.HTTPError as exc:
            if exc.code == 404:
                raise SubtisNotFound("Subtis subtitle not found") from exc
            raise
        try:
            return json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Subtis response is not valid JSON") from exc

    def get_bytes(self, url):
        parsed = parse.urlparse(str(url))
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("Subtis download_url must be http or https")
        req = request.Request(
            str(url),
            headers={"User-Agent": "BazarrProviderHub/Subtis/1.0"},
        )
        with request.urlopen(req, timeout=self.download_timeout) as response:  # noqa: S310
            return response.read()


def _language_payload(language):
    payload = dict(language or {}) if isinstance(language, dict) else {"alpha3": str(language)}
    alpha3 = str(payload.get("alpha3") or "").lower()
    alpha2 = str(payload.get("alpha2") or "").lower()
    if not alpha3:
        alpha3 = "spa" if alpha2 == "es" else alpha2 or "spa"
    if alpha3 == "es":
        alpha3 = "spa"
    payload["alpha3"] = alpha3
    payload.setdefault("alpha2", "es" if alpha3 == "spa" else alpha2)
    payload.setdefault("hi", False)
    payload.setdefault("forced", False)
    return payload


def _is_spanish(language):
    payload = _language_payload(language)
    if payload.get("hi") or payload.get("forced"):
        return False
    return payload.get("alpha3") == "spa" or payload.get("alpha2") == "es"


def _filename(video):
    name = (video or {}).get("name") or (video or {}).get("original_name") or (video or {}).get("original_path")
    if name:
        return os.path.basename(str(name))
    title = (video or {}).get("title") or "movie"
    year = (video or {}).get("year")
    return f"{title}.{year}.mkv" if year else f"{title}.mkv"


def _quote_path(value):
    return parse.quote(str(value), safe="")


def _hash_url(video_hash):
    return f"{API_BASE_URL}/subtitle/find/file/hash/{_quote_path(video_hash)}"


def _bytes_url(size):
    return f"{API_BASE_URL}/subtitle/find/file/bytes/{int(size)}"


def _name_url(filename):
    return f"{API_BASE_URL}/subtitle/find/file/name/{_quote_path(filename)}"


def _alternative_url(filename):
    return f"{API_BASE_URL}/subtitle/file/alternative/{_quote_path(filename)}"


def _known_video_hash(video):
    hashes = (video or {}).get("hashes") or {}
    for key in ("subtis", "opensubtitles", "opensubtitlescom", "bsplayer"):
        value = hashes.get(key)
        if value:
            return str(value).strip()
    name = (video or {}).get("name")
    if name and os.path.exists(str(name)):
        return _compute_file_hash(str(name))
    return None


def _compute_file_hash(path):
    try:
        file_size = os.path.getsize(path)
        if file_size <= 0:
            return None
        chunk_size = min(65536, file_size)
        checksum = file_size
        with open(path, "rb") as handle:
            for offset in (0, max(file_size - chunk_size, 0)):
                handle.seek(offset)
                data = handle.read(chunk_size)
                padding = (8 - (len(data) % 8)) % 8
                if padding:
                    data += b"\0" * padding
                for chunk in struct.iter_unpack("<Q", data):
                    checksum += chunk[0]
        return f"{checksum & 0xFFFFFFFFFFFFFFFF:016x}"
    except OSError:
        return None


def _size(video):
    raw = (video or {}).get("size")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _parse_api_payload(payload):
    if not isinstance(payload, dict):
        return None
    subtitle = payload.get("subtitle")
    if not isinstance(subtitle, dict):
        return None
    download_url = subtitle.get("subtitle_link")
    if not isinstance(download_url, str) or not download_url:
        return None
    title = payload.get("title")
    title_name = "Unknown"
    if isinstance(title, dict) and title.get("title_name"):
        title_name = str(title["title_name"]).strip() or "Unknown"
    return download_url, title_name


def _normalize_text(value):
    return "".join(char.lower() if char.isalnum() else " " for char in str(value)).split()


def _matches(video, title_name, method):
    if method == "hash":
        return ["hash"]
    haystack = set(_normalize_text(title_name))
    matches = []
    title = (video or {}).get("title")
    if title and set(_normalize_text(title)).issubset(haystack):
        matches.append("title")
    year = (video or {}).get("year")
    if year and str(year) in haystack:
        matches.append("year")
    return matches


def _candidate_id(method, url):
    digest = hashlib.sha1(f"{method}\0{url}".encode("utf-8")).hexdigest()
    return f"subtis-{digest[:16]}"


def _format_from_url(url):
    path = parse.urlparse(str(url)).path
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else "srt"
    return ext if ext in {"srt", "ass", "ssa", "sub", "vtt"} else "srt"


def _download_response(body, fmt):
    if not body:
        return {
            "content_b64": "",
            "content_sha256": "",
            "content_type": "application/x-subrip",
            "format": fmt or "srt",
            "encoding": None,
            "empty": True,
        }
    return {
        "content_b64": base64.b64encode(body).decode("ascii"),
        "content_sha256": hashlib.sha256(body).hexdigest(),
        "content_type": "application/x-subrip",
        "format": fmt or "srt",
        "encoding": None,
        "empty": False,
    }


class SubtisProvider:
    def __init__(self, http_client=None):
        self.http_client = http_client or SubtisHttpClient()

    def search(self, video, languages, config):
        del config
        video = video or {}
        if video.get("kind") not in _SUPPORTED_MEDIA:
            return []
        language = next((_language_payload(item) for item in languages or [] if _is_spanish(item)), None)
        if language is None:
            return []

        filename = _filename(video)
        cascade = []
        video_hash = _known_video_hash(video)
        if video_hash:
            cascade.append(("hash", _hash_url(video_hash), True))
        size = _size(video)
        if size:
            cascade.append(("bytes", _bytes_url(size), True))
        cascade.append(("name", _name_url(filename), True))
        cascade.append(("alternative", _alternative_url(filename), False))

        for method, url, synced in cascade:
            try:
                payload = self.http_client.get_json(url)
            except SubtisNotFound:
                payload = None
            parsed = _parse_api_payload(payload)
            if not parsed:
                continue
            download_url, title_name = parsed
            release_info = title_name if synced else f"{title_name} [fuzzy match]"
            fmt = _format_from_url(download_url)
            score = 100 if method == "hash" else 60 if synced else 40
            score_without_hash = 60 if method == "hash" else score
            return [
                {
                    "provider": PROVIDER_ID,
                    "id": _candidate_id(method, url),
                    "language": language,
                    "release_info": release_info,
                    "filename": os.path.basename(parse.urlparse(download_url).path) or f"subtis.{fmt}",
                    "matches": _matches(video, title_name, method),
                    "score": score,
                    "score_without_hash": score_without_hash,
                    "score_out_of": 100,
                    "hash_verifiable": method == "hash",
                    "hearing_impaired_verifiable": False,
                    "hearing_impaired": False,
                    "display": {
                        "source": "api.subt.is",
                        "method": method,
                        "synced": synced,
                    },
                    "provider_payload": {
                        "provider": PROVIDER_ID,
                        "schema": 1,
                        "download_url": download_url,
                        "method": method,
                        "format": fmt,
                    },
                }
            ]
        return []

    def download(self, provider_payload, language, config):
        del language, config
        payload = dict(provider_payload or {})
        if payload.get("provider") != PROVIDER_ID:
            raise ValueError("Subtis provider payload has wrong provider")
        download_url = str(payload.get("download_url") or "").strip()
        if not download_url:
            raise ValueError("Subtis download_url is required")
        return _download_response(
            self.http_client.get_bytes(download_url),
            payload.get("format") or _format_from_url(download_url),
        )
