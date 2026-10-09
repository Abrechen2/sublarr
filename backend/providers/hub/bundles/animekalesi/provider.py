"""AnimeKalesi provider for the Bazarr+ Provider Hub catalog."""

import base64 as _base64
import hashlib as _hashlib
import html
import io
import os
import re
import socket
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from html.parser import HTMLParser
from http.cookiejar import CookieJar

PROVIDER_ID = "animekalesi"
BASE_URL = "https://www.animekalesi.com"
SERIES_INDEX_URL = f"{BASE_URL}/tum-anime-serileri.html"
HTTP_TIMEOUT_SECONDS = 15
HTTP_RETRIES = 2
RETRY_BACKOFF_SECONDS = 0.5
RETRY_BACKOFF_CAP_SECONDS = 8.0
RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
SUPPORTED_LANGUAGES = {"tur": "tr"}
ALPHA2_TO_ALPHA3 = {value: key for key, value in SUPPORTED_LANGUAGES.items()}
SUBTITLE_EXTENSIONS = (".srt", ".ass", ".ssa", ".vtt")
SUPPORTED_FILE_EXTENSIONS = SUBTITLE_EXTENSIONS + (".zip",)
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 BazarrProviderHub"
)

_NON_ALNUM_RE = re.compile(r"[\W_]+", re.UNICODE)
_SEASON_RE = re.compile(r"\b(\d{1,2})\s*sezon\b", re.I)
_EPISODE_RE = re.compile(r"\b(\d{1,4})\s*bolum\b", re.I)
_SXXEYY_RE = re.compile(r"\bs0*(\d{1,2})\s*e0*(\d{1,4})\b", re.I)
_EXX_RE = re.compile(r"\be0*(\d{1,4})\b", re.I)
_SRT_CUE_RE = re.compile(
    r"(?m)^\s*\d+\s*\n\s*\d{1,2}:\d{2}:\d{2}[,.]\d{1,3}\s*-->\s*"
    r"\d{1,2}:\d{2}:\d{2}[,.]\d{1,3}"
)
_TURKISH_TRANSLATION = str.maketrans(
    {
        "İ": "i",
        "I": "i",
        "ı": "i",
        "Ğ": "g",
        "ğ": "g",
        "Ü": "u",
        "ü": "u",
        "Ş": "s",
        "ş": "s",
        "Ö": "o",
        "ö": "o",
        "Ç": "c",
        "ç": "c",
    }
)


def normalize_series_name(value):
    if value is None:
        return ""
    translated = str(value).translate(_TURKISH_TRANSLATION)
    decomposed = unicodedata.normalize("NFKD", translated)
    folded = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return _NON_ALNUM_RE.sub(" ", folded.lower()).strip()


def parse_series_index(body):
    rows = []
    for link in _links_inside(body, "td", "bolumler"):
        href = link.get("href") or ""
        if "bolumler-" not in href:
            continue
        title = _series_title(link)
        if not title:
            continue
        rows.append({"title": title, "url": _absolute_url(href)})
    return rows


def select_series(rows, series):
    wanted = normalize_series_name(series)
    if not wanted:
        return None
    partial = []
    for row in rows or []:
        title = normalize_series_name(row.get("title"))
        if not title:
            continue
        if title == wanted:
            return row
        if title in wanted or wanted in title:
            partial.append((len(title), row))
    if not partial:
        return None
    return max(partial, key=lambda item: item[0])[1]


def subtitle_listing_url(series_url):
    url = _absolute_url(series_url)
    parts = urllib.parse.urlsplit(url)
    path_parts = parts.path.rsplit("/", 1)
    basename = path_parts[-1].replace("bolumler-", "altyazib-", 1)
    path = f"{path_parts[0]}/{basename}" if len(path_parts) == 2 and path_parts[0] else f"/{basename}"
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))


def parse_subtitle_listing(body):
    rows = []
    for link in _links_inside(body, "td", "ayazi_indir"):
        href = link.get("href") or ""
        title = _clean_text(link.get("title") or link.get("text") or "")
        normalized_title = normalize_series_name(title)
        if "indir_bolum-" not in href:
            continue
        if "bolum turkce altyazisi" not in normalized_title:
            continue
        season, episode = parse_season_episode(title)
        if episode is None:
            continue
        rows.append(
            {
                "title": title,
                "season": season or 1,
                "episode": episode,
                "url": _absolute_url(href),
            }
        )
    return rows


def parse_season_episode(title):
    normalized = normalize_series_name(title)
    episode_match = _EPISODE_RE.search(normalized)
    if not episode_match:
        return None, None
    season_match = _SEASON_RE.search(normalized)
    season = int(season_match.group(1)) if season_match else 1
    return season, int(episode_match.group(1))


def parse_episode_page(body):
    links = _links_inside(body, "div", "altyazi_indir")
    if not links:
        raise ValueError("animekalesi episode page has no download link")
    return {
        "download_url": _absolute_url(links[0]["href"]),
        "uploader": _extract_uploader(body),
    }


def derive_matches(video, series_title, season, episode, release_info=""):
    if not video:
        return []
    matches = []
    wanted = normalize_series_name(video.get("series"))
    candidate = normalize_series_name(series_title)
    alternatives = [normalize_series_name(item) for item in video.get("alternative_series", [])]
    if wanted and (wanted == candidate or wanted in candidate or candidate in wanted):
        matches.append("series")
    elif candidate and candidate in alternatives:
        matches.append("series")
    try:
        wanted_season = int(video.get("season"))
        wanted_episode = int(video.get("episode"))
    except (TypeError, ValueError):
        wanted_season = wanted_episode = None
    if wanted_season is not None and int(season or 1) == wanted_season:
        matches.append("season")
    if wanted_episode is not None and int(episode or 0) == wanted_episode:
        matches.append("episode")
    release_group = video.get("release_group") if isinstance(video, dict) else getattr(video, "release_group", None)
    if release_info and release_group:
        release_group = str(release_group).lower()
        if release_group and release_group in release_info.lower():
            matches.append("release_group")
    return matches


class AnimeKalesiProvider:
    def __init__(self):
        self._cookie_jar = CookieJar()
        self._opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self._cookie_jar))

    def _http_get(self, url, timeout=HTTP_TIMEOUT_SECONDS, referer=None):
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "tr,en-US;q=0.7,en;q=0.3",
            "Connection": "keep-alive",
        }
        if referer:
            headers["Referer"] = referer
        request = urllib.request.Request(url, headers=headers)
        for attempt in range(HTTP_RETRIES + 1):
            try:
                with self._opener.open(request, timeout=timeout) as response:
                    return response.read()
            except urllib.error.HTTPError as error:
                # Retry only on transient server-side statuses (5xx) and rate limiting
                # (429). All other 4xx (auth, not found, gone, ...) propagate unchanged
                # on the first occurrence.
                if error.code not in RETRYABLE_STATUS_CODES or attempt >= HTTP_RETRIES:
                    raise
                time.sleep(_retry_delay(attempt, _retry_after_seconds(error)))
            except (TimeoutError, socket.timeout, urllib.error.URLError):
                # Raw transport failures: connection refused, DNS, reset, timeout.
                if attempt >= HTTP_RETRIES:
                    raise
                time.sleep(_retry_delay(attempt))
        raise RuntimeError("unreachable animekalesi retry state")

    def search(self, video, languages, config):
        if (video or {}).get("kind") != "episode":
            return []
        requested = {_alpha3_for_language(language) for language in languages or []}
        if "tur" not in requested:
            return []
        try:
            wanted_season = int(video.get("season"))
            wanted_episode = int(video.get("episode"))
        except (TypeError, ValueError):
            return []
        if not video.get("series"):
            return []

        config = dict(config or {})
        _sleep(config)
        series = select_series(parse_series_index(self._http_get(SERIES_INDEX_URL)), video.get("series"))
        if not series:
            return []

        listing_url = subtitle_listing_url(series["url"])
        _sleep(config)
        rows = parse_subtitle_listing(self._http_get(listing_url, referer=SERIES_INDEX_URL))
        results = []
        seen = set()
        for row in rows:
            if row["season"] != wanted_season or row["episode"] != wanted_episode:
                continue
            _sleep(config)
            try:
                page = parse_episode_page(self._http_get(row["url"], referer=listing_url))
            except ValueError:
                continue
            key = (page["download_url"], "tur")
            if key in seen:
                continue
            seen.add(key)
            merged = dict(row)
            merged.update(page)
            merged["series_title"] = series["title"]
            results.append(self._result(video, merged))
        return sorted(results, key=lambda item: item["score"], reverse=True)

    def _result(self, video, row):
        alpha3 = "tur"
        alpha2 = SUPPORTED_LANGUAGES[alpha3]
        release_info = f"{row['series_title']} - S{int(row['season']):02d}E{int(row['episode']):02d}"
        if row.get("uploader"):
            release_info = f"{release_info} by {row['uploader']}"
        matches = derive_matches(video, row["series_title"], row["season"], row["episode"], release_info)
        score = 98 if "episode" in matches else 80
        filename = (
            f"animekalesi.{_slug(row['series_title'])}."
            f"s{int(row['season']):02d}e{int(row['episode']):02d}.{alpha2}.srt"
        )
        payload = {
            "provider": PROVIDER_ID,
            "schema": 1,
            "download_url": row["download_url"],
            "page_url": row["url"],
            "filename": filename,
            "season": row["season"],
            "episode": row["episode"],
            "language": alpha3,
            "release_info": release_info,
        }
        return {
            "provider": PROVIDER_ID,
            "id": _stable_id(row["download_url"], alpha3),
            "language": {
                "alpha3": alpha3,
                "alpha2": alpha2,
                "hi": False,
                "forced": False,
            },
            "release_info": release_info,
            "filename": filename,
            "matches": matches,
            "score": score,
            "score_without_hash": score,
            "score_out_of": 100,
            "hash_verifiable": False,
            "hearing_impaired_verifiable": False,
            "hearing_impaired": False,
            "page_link": row["url"],
            "display": {
                "source": "animekalesi",
                "title": row["series_title"],
                "release": release_info,
                "uploader": row.get("uploader"),
            },
            "provider_payload": payload,
        }

    def download(self, provider_payload, language, config):
        del language, config
        payload = provider_payload or {}
        url = payload.get("download_url") or payload.get("url")
        if not url:
            raise ValueError("animekalesi download requires download_url")
        body = self._http_get(url, referer=payload.get("page_url"))
        return _download_payload(body, payload)


def _download_payload(body, payload=None):
    payload = payload or {}
    if not body:
        raise ValueError("animekalesi download returned an empty body")
    stream = io.BytesIO(body)
    if zipfile.is_zipfile(stream):
        # Host-side extraction (Provider Hub v1.1+): list the zip with stdlib zipfile to
        # pick the member, then hand the raw archive bytes plus that member name to the
        # host, which extracts it and detects the encoding via Subtitle.normalize().
        with zipfile.ZipFile(stream) as archive:
            selected = select_subtitle_file(archive.namelist(), payload)
        return {
            "archive_b64": _base64.b64encode(body).decode("ascii"),
            "archive_sha256": _hashlib.sha256(body).hexdigest(),
            "member": selected,
        }
    subtitle_format = _subtitle_format_from_body(body) or _format_from_filename(payload.get("filename"))
    if not _is_supported_subtitle_body(body, subtitle_format):
        raise ValueError("animekalesi direct download did not return a supported subtitle")
    return _content_payload(_normalize_line_endings(body), subtitle_format)


def select_subtitle_file(names, payload):
    candidates = [name for name in names if _subtitle_extension(name)]
    if not candidates:
        raise ValueError("animekalesi archive contains no supported subtitle files")
    payload = payload or {}
    try:
        season = int(payload.get("season"))
        episode = int(payload.get("episode"))
    except (TypeError, ValueError):
        season = episode = None
    release_info = normalize_series_name(payload.get("release_info"))

    def score_points(name):
        basename = normalize_series_name(os.path.basename(name))
        points = 0
        if release_info and release_info in basename:
            points = max(points, 120)
        has_marker, marker_matches = _episode_marker_status(basename, season, episode)
        if marker_matches:
            points = max(points, 110)
        if not has_marker and episode is not None and re.search(rf"(^|[^0-9])0*{episode}([^0-9]|$)", basename):
            points = max(points, 90)
        return points

    def score(name):
        points = score_points(name)
        return (points, -_extension_rank(name), -len(name), name.lower())

    best = max(candidates, key=score)
    if season is not None and episode is not None and score_points(best) <= 0:
        if any(_episode_marker_status(normalize_series_name(os.path.basename(name)), season, episode)[0] for name in candidates):
            raise ValueError("animekalesi archive contains no subtitle matching episode")
    return best


def _episode_marker_status(basename, season, episode):
    for match in _SXXEYY_RE.finditer(basename or ""):
        marker_season = int(match.group(1))
        marker_episode = int(match.group(2))
        return True, season is not None and episode is not None and marker_season == season and marker_episode == episode
    for match in _EXX_RE.finditer(basename or ""):
        marker_episode = int(match.group(1))
        return True, episode is not None and marker_episode == episode
    return False, False


def _is_supported_subtitle_body(body, subtitle_format):
    return _subtitle_format_from_body(body) == subtitle_format


def _subtitle_format_from_body(body):
    text = _decode_body(body).lstrip("\ufeff").strip()
    if not text:
        return None
    lowered = text[:4096].lower()
    if lowered.startswith("<!doctype") or lowered.startswith("<html") or "<body" in lowered:
        return None
    if text.startswith("WEBVTT"):
        return "vtt"
    if "[script info]" in lowered or "[events]" in lowered or "dialogue:" in lowered:
        return "ass"
    if _SRT_CUE_RE.search(text):
        return "srt"
    if "-->" in text:
        return "vtt"
    return None


def _links_inside(body, tag, element_id):
    parser = _LinksInsideIdParser(tag, element_id)
    parser.feed(_decode_body(body))
    return parser.links


class _LinksInsideIdParser(HTMLParser):
    def __init__(self, tag, element_id):
        super().__init__(convert_charrefs=True)
        self._tag = tag
        self._element_id = element_id
        self._depth = 0
        self._current = None
        self.links = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if self._depth:
            self._depth += 1
            if tag == "a" and attrs.get("href"):
                self._current = {
                    "href": html.unescape(attrs.get("href", "")),
                    "title": html.unescape(attrs.get("title", "")),
                    "text_parts": [],
                }
            return
        if tag == self._tag and attrs.get("id") == self._element_id:
            self._depth = 1

    def handle_endtag(self, tag):
        if self._current is not None and tag == "a":
            self._current["text"] = _clean_text(" ".join(self._current.pop("text_parts")))
            self.links.append(self._current)
            self._current = None
        if self._depth:
            self._depth -= 1

    def handle_data(self, data):
        if self._current is not None:
            self._current["text_parts"].append(data)


def _extract_uploader(body):
    chunks = _text_chunks(body)
    for index, chunk in enumerate(chunks):
        if "Altyazı/Çeviri:" not in chunk:
            continue
        after = chunk.split("Altyazı/Çeviri:", 1)[1].strip()
        if after:
            return after
        if index + 1 < len(chunks):
            return chunks[index + 1].strip() or None
    return None


def _text_chunks(body):
    parser = _TextChunkParser()
    parser.feed(_decode_body(body))
    return [_clean_text(chunk) for chunk in parser.chunks if _clean_text(chunk)]


class _TextChunkParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.chunks = []

    def handle_data(self, data):
        value = _clean_text(data)
        if value:
            self.chunks.append(value)


def _series_title(link):
    title = _clean_text(link.get("text") or link.get("title") or "")
    title = re.sub(r"\s+İndir ve İzle\s*$", "", title, flags=re.I)
    title = re.sub(r"\s+Indir ve Izle\s*$", "", title, flags=re.I)
    return title.strip()


def _alpha3_for_language(language):
    if not isinstance(language, dict):
        return None
    alpha3 = (language.get("alpha3") or "").lower()
    if alpha3:
        return alpha3
    return ALPHA2_TO_ALPHA3.get((language.get("alpha2") or "").lower())


def _sleep(config):
    delay_ms = (config or {}).get("request_delay_ms", 0) or 0
    if delay_ms > 0:
        time.sleep(min(delay_ms, 5000) / 1000.0)


def _retry_delay(attempt, retry_after=None):
    # attempt is 0-based: 0 before the first retry, 1 before the second.
    backoff = RETRY_BACKOFF_SECONDS * (2 ** attempt)
    if retry_after is not None and retry_after > backoff:
        backoff = retry_after
    return min(backoff, RETRY_BACKOFF_CAP_SECONDS)


def _retry_after_seconds(error):
    # Honor a Retry-After header (seconds form) when the server sends one on a 429.
    headers = getattr(error, "headers", None)
    value = headers.get("Retry-After") if headers else None
    if not value:
        return None
    try:
        seconds = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return seconds if seconds >= 0 else None


def _stable_id(url, alpha3):
    digest = _hashlib.sha1(f"{url}:{alpha3}".encode("utf-8")).hexdigest()[:16]
    return f"animekalesi-{digest}"


def _absolute_url(value):
    joined = urllib.parse.urljoin(f"{BASE_URL}/", html.unescape(str(value or "")))
    parts = urllib.parse.urlsplit(joined)
    path = urllib.parse.quote(parts.path, safe="/%:@+")
    query = urllib.parse.quote(parts.query, safe="=&%:+")
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, query, parts.fragment))


def _slug(value):
    normalized = normalize_series_name(value)
    return re.sub(r"\s+", "-", normalized).strip("-") or "anime"


def _format_from_filename(filename):
    return _subtitle_extension(filename or "") or "srt"


def _subtitle_extension(name):
    lowered = (name or "").lower()
    for extension in SUBTITLE_EXTENSIONS:
        if lowered.endswith(extension):
            return extension[1:]
    return None


def _extension_rank(name):
    suffix = "." + (name or "").rsplit(".", 1)[-1].lower()
    return {".srt": 0, ".ass": 1, ".ssa": 2, ".vtt": 3}.get(suffix, 9)


def _content_payload(body, subtitle_format):
    # Do not guess an encoding. The host runs chardet via Subtitle.normalize(); a worker
    # guess (especially a legacy codepage that never fails to decode) only reintroduces
    # mojibake. Leave encoding unset and let the host normalize.
    subtitle_format = subtitle_format or "srt"
    return {
        "content_b64": _base64.b64encode(body).decode("ascii"),
        "content_sha256": _hashlib.sha256(body).hexdigest(),
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


def _normalize_line_endings(body):
    return (body or b"").replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _clean_text(value):
    return re.sub(r"\s+", " ", html.unescape(str(value or ""))).strip()


def _decode_body(body):
    if isinstance(body, bytes):
        return body.decode("utf-8", errors="replace")
    return str(body or "")
