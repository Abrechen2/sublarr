import base64
import hashlib
import json
import os
from urllib import parse, request


PROVIDER_ID = "shooter"
SHOOTER_API_URL = "https://www.shooter.cn/api/subapi.php"
_LANGUAGE_TO_SHOOTER = {
    "eng": "eng",
    "zho": "chn",
}
_SUPPORTED_MEDIA = {"movie", "episode"}
_SUPPORTED_FORMATS = {"srt", "ass", "ssa", "sub", "vtt"}
_DEFAULT_TIMEOUT = 10
_SHOOTER_HASH_READ_SIZE = 4096


class ShooterHttpClient:
    def __init__(self, timeout=_DEFAULT_TIMEOUT):
        self.timeout = int(timeout)

    def post(self, url, params):
        query = parse.urlencode(params)
        target = f"{url}?{query}"
        req = request.Request(
            target,
            data=b"",
            method="POST",
            headers={
                "Accept": "application/json",
                "User-Agent": "BazarrProviderHub/1.0",
            },
        )
        with request.urlopen(req, timeout=self.timeout) as response:  # noqa: S310
            return response.read()

    def get(self, url):
        parsed = parse.urlparse(str(url))
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("Shooter download_url must be http or https")
        req = request.Request(
            str(url),
            headers={"User-Agent": "BazarrProviderHub/1.0"},
        )
        with request.urlopen(req, timeout=self.timeout) as response:  # noqa: S310
            return response.read()


def _language_payload(language):
    payload = dict(language or {}) if isinstance(language, dict) else {"alpha3": str(language)}
    payload.setdefault("alpha3", payload.get("alpha2") or "eng")
    payload.setdefault("hi", False)
    payload.setdefault("forced", False)
    return payload


def _video_name(video):
    video = video or {}
    path = _existing_video_path(video)
    if path:
        return path
    name = video.get("name") or video.get("path") or video.get("original_path") or video.get("original_name")
    if name:
        return str(name)
    if video.get("kind") == "episode":
        series = video.get("series") or "episode"
        season = int(video.get("season") or 0)
        episode = int(video.get("episode") or 0)
        return f"{series}.S{season:02d}E{episode:02d}.mkv"
    title = video.get("title") or "movie"
    year = video.get("year")
    return f"{title}.{year}.mkv" if year else f"{title}.mkv"


def _shooter_hash(video):
    hashes = (video or {}).get("hashes") or {}
    value = hashes.get("shooter")
    value = str(value).strip() if value is not None else ""
    if value:
        return value
    return _compute_shooter_hash(_existing_video_path(video))


def _existing_video_path(video):
    for key in ("path", "name", "original_path", "original_name"):
        value = str((video or {}).get(key) or "").strip()
        if value and os.path.isfile(value):
            return value
    return None


def _compute_shooter_hash(path):
    if not path:
        return None
    filesize = os.path.getsize(path)
    read_size = _SHOOTER_HASH_READ_SIZE
    if filesize < read_size * 2:
        return None
    offsets = (read_size, filesize // 3 * 2, filesize // 3, filesize - read_size * 2)
    hashes = []
    with open(path, "rb") as handle:
        for offset in offsets:
            handle.seek(offset)
            hashes.append(hashlib.md5(handle.read(read_size)).hexdigest())
    return ";".join(hashes)


def _candidate_id(download_url, filehash, language_code):
    digest = hashlib.sha1(f"{filehash}\0{language_code}\0{download_url}".encode("utf-8")).hexdigest()
    return f"shooter-{digest[:16]}"


def _filename_from_url(download_url, language_code, fmt="srt"):
    fmt = fmt or "srt"
    path = parse.urlparse(download_url).path
    basename = os.path.basename(path) or f"shooter.{language_code}.{fmt}"
    if "." not in basename:
        return f"{basename}.{language_code}.{fmt}"
    # Opaque endpoints such as subapi.php carry the real type in Shooter's Ext
    # field, so trust the resolved format over the request path's extension.
    current_ext = basename.rsplit(".", 1)[-1].lower()
    if current_ext not in _SUPPORTED_FORMATS:
        return f"{basename}.{language_code}.{fmt}"
    return basename


def _format_from_filename(filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext if ext in _SUPPORTED_FORMATS else None


def _resolve_format(ext, download_url):
    fmt = str(ext or "").strip().lstrip(".").lower()
    if fmt in _SUPPORTED_FORMATS:
        return fmt
    if fmt:
        # An explicit but unsupported Ext (such as VobSub idx companions) is not
        # a usable single subtitle file, so drop it instead of mislabeling it.
        return None
    basename = os.path.basename(parse.urlparse(download_url).path)
    return _format_from_filename(basename)


def _parse_search_response(body):
    if body == b"\xff":
        return []
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Shooter response is not valid JSON") from exc
    if not isinstance(payload, list):
        raise ValueError("Shooter response must be a list")

    results = []
    for group in payload:
        if not isinstance(group, dict):
            continue
        files = group.get("Files") or []
        if not isinstance(files, list):
            continue
        for item in files:
            if not isinstance(item, dict):
                continue
            link = item.get("Link")
            if isinstance(link, str) and link.startswith(("http://", "https://")):
                results.append((link, item.get("Ext")))
    return results


def _normalize_line_endings(body):
    return body.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _download_response(body, fmt):
    normalized = _normalize_line_endings(body)
    fmt = fmt or "srt"
    return {
        "content_b64": base64.b64encode(normalized).decode("ascii"),
        "content_sha256": hashlib.sha256(normalized).hexdigest(),
        "content_type": _content_type(fmt),
        "format": fmt,
        "encoding": None,
        "empty": False,
    }


def _content_type(fmt):
    if fmt in {"ass", "ssa"}:
        return "text/x-ssa"
    if fmt == "vtt":
        return "text/vtt"
    if fmt == "sub":
        return "text/plain"
    return "application/x-subrip"


class ShooterProvider:
    def __init__(self, http_client=None):
        self.http_client = http_client or ShooterHttpClient()

    def search(self, video, languages, config):
        del config
        video = video or {}
        if video.get("kind") not in _SUPPORTED_MEDIA:
            return []

        filehash = _shooter_hash(video)
        if not filehash:
            return []

        candidates = []
        for item in languages or []:
            language = _language_payload(item)
            alpha3 = language.get("alpha3")
            if language.get("hi") or language.get("forced"):
                continue
            shooter_language = _LANGUAGE_TO_SHOOTER.get(alpha3)
            if not shooter_language:
                continue
            params = {
                "filehash": filehash,
                "pathinfo": os.path.realpath(_video_name(video)),
                "format": "json",
                "lang": shooter_language,
            }
            body = self.http_client.post(SHOOTER_API_URL, params)
            for download_url, ext in _parse_search_response(body):
                fmt = _resolve_format(ext, download_url)
                if not fmt:
                    # Drop companion or unknown files we cannot serve as one subtitle.
                    continue
                filename = _filename_from_url(download_url, alpha3, fmt)
                candidates.append(
                    {
                        "provider": PROVIDER_ID,
                        "id": _candidate_id(download_url, filehash, alpha3),
                        "language": language,
                        "release_info": filehash,
                        "filename": filename,
                        "matches": ["hash"],
                        "score": 100,
                        "score_without_hash": 0,
                        "score_out_of": 100,
                        "hash_verifiable": True,
                        "hearing_impaired_verifiable": False,
                        "hearing_impaired": bool(language.get("hi", False)),
                        "display": {
                            "source": "shooter.cn",
                            "shooter_hash": filehash,
                        },
                        "provider_payload": {
                            "provider": PROVIDER_ID,
                            "schema": 1,
                            "download_url": download_url,
                            "filehash": filehash,
                            "language": alpha3,
                            "format": fmt,
                        },
                    }
                )
        return candidates

    def download(self, provider_payload, language, config):
        del language, config
        payload = dict(provider_payload or {})
        if payload.get("provider") != PROVIDER_ID:
            raise ValueError("Shooter provider payload has wrong provider")
        download_url = str(payload.get("download_url") or "").strip()
        if not download_url:
            raise ValueError("Shooter download_url is required")
        body = self.http_client.get(download_url)
        return _download_response(body, payload.get("format") or _format_from_filename(download_url))
