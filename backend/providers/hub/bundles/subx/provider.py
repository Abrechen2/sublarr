"""SubX provider for the Bazarr+ Provider Hub catalog."""

import base64
import hashlib
import io
import json
import os
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import zipfile

PROVIDER_ID = "subx"
BASE_URL = "https://subx-api.duckdns.org"
SEARCH_PATH = "/api/subtitles/search"
USER_AGENT = "BazarrProviderHub/1.0 (+https://github.com/LavX/bazarr-provider-catalog)"
HTTP_TIMEOUT_SECONDS = 10
DOWNLOAD_TIMEOUT_SECONDS = 30
MAX_RETRIES = 3
SUPPORTED_ALPHA3 = "spa"
SUPPORTED_ALPHA2 = "es"
SUBTITLE_EXTENSIONS = (".srt", ".ass", ".ssa", ".vtt", ".sub")
ARCHIVE_EXTENSIONS = (".zip", ".rar")
SPAIN_KEYWORDS = ("espana", "iberico", "castellano", "gallego", "castilla", "europea", "europeo")
_SXXEYY_RE = re.compile(r"\bs0*(?P<season>\d{1,2})[\s._-]*e0*(?P<episode>\d{1,3})(?!\d)", re.I)
_NXNN_RE = re.compile(r"(?<!\d)(?P<season>\d{1,2})x0*(?P<episode>\d{1,3})(?!\d)", re.I)


class RateLimited(RuntimeError):
    def __init__(self, message, retry_after=0):
        super().__init__(message)
        self.retry_after = retry_after


def auth_headers(api_key):
    return {
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}",
        "User-Agent": USER_AGENT,
    }


def _require_api_key(config):
    api_key = str((config or {}).get("api_key") or "").strip()
    if not api_key:
        raise ValueError("SubX api_key is required")
    return api_key


def _alpha3_for_language(language):
    if isinstance(language, dict):
        return language.get("alpha3") or _alpha3_from_alpha2(language.get("alpha2"))
    return str(language) if language else None


def _alpha3_from_alpha2(alpha2):
    return SUPPORTED_ALPHA3 if alpha2 == SUPPORTED_ALPHA2 else None


def _requested_spanish_languages(languages):
    requested = []
    for language in languages or []:
        if _alpha3_for_language(language) != SUPPORTED_ALPHA3:
            continue
        country = (language.get("country") if isinstance(language, dict) else None) or None
        requested.append(country)
    return requested


def language_payload_from_description(description):
    country = "ES" if _is_spain_spanish(description) else "MX"
    return {
        "alpha3": SUPPORTED_ALPHA3,
        "alpha2": SUPPORTED_ALPHA2,
        "country": country,
        "hi": False,
        "forced": False,
    }


def _is_spain_spanish(description):
    normalized = _ascii_lower(description)
    return any(keyword in normalized for keyword in SPAIN_KEYWORDS)


def _ascii_lower(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    return text.encode("ascii", "ignore").decode("ascii").lower()


def _language_matches_request(language_payload, requested_countries):
    country = language_payload.get("country")
    return any(requested is None or requested == country for requested in requested_countries)


def _series_sanitizer(title):
    title = title or ""
    title = re.sub(r"[._]+", " ", str(title))
    return re.sub(r"\s+", " ", title).strip()


def _coerce_titles(value):
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _collect_titles(video, episode=False, max_alts=3):
    video = video or {}
    titles = _coerce_titles(video.get("series") if episode else video.get("title"))
    titles.extend(_coerce_titles(video.get("alternative_series") if episode else video.get("alternative_titles")))
    seen = set()
    result = []
    for title in titles:
        if title in seen:
            continue
        seen.add(title)
        result.append(title)
        if len(result) >= max_alts:
            break
    return result


def build_episode_queries(video):
    video = video or {}
    season = _int_or_none(video.get("season"))
    episode = _int_or_none(video.get("episode"))
    if season is None or episode is None:
        return []
    queries = []
    seen = set()
    for title in _collect_titles(video, episode=True, max_alts=3):
        series = _series_sanitizer(title)
        if not series or series in seen:
            continue
        seen.add(series)
        queries.extend(
            [
                (f"{series} S{season:02d}E{episode:02d}", season, episode),
                (f"{series} S{season:02d}", season, None),
                (series, season, None),
            ]
        )
    return queries


def _movie_queries(video):
    return [(title, None, None) for title in _collect_titles(video, episode=False, max_alts=3)]


def _query_params(video, query, video_type):
    video = video or {}
    params = {
        "limit": 200,
        "video_type": video_type,
    }
    imdb_id = video.get("imdb_id") or video.get("series_imdb_id")
    if imdb_id:
        params["imdb_id"] = imdb_id
    elif query:
        params["title"] = query
    else:
        return None
    year = _int_or_none(video.get("year"))
    if year:
        params["year"] = year
    return params


class SubXProvider:
    def search(self, video, languages, config):
        config = dict(config or {})
        _require_api_key(config)
        requested_countries = _requested_spanish_languages(languages)
        if not requested_countries:
            return []
        video = video or {}
        if video.get("kind") == "episode":
            queries = build_episode_queries(video)
            video_type = "episode"
        elif video.get("kind") == "movie":
            queries = _movie_queries(video)
            video_type = "movie"
        else:
            return []

        seen_params = set()
        for query, season, episode in queries:
            params = _query_params(video, query, video_type)
            if not params:
                continue
            key = tuple(sorted(params.items()))
            if key in seen_params:
                continue
            seen_params.add(key)
            data = self._request_json(SEARCH_PATH, params, config)
            results = self._results_from_items(
                video,
                data.get("items") or [],
                requested_countries,
                season=season,
                episode=episode,
            )
            if results:
                return sorted(results, key=lambda item: item["score"], reverse=True)
            _sleep(config)
        return []

    def _results_from_items(self, video, items, requested_countries, season=None, episode=None):
        exact = []
        season_packs = []
        for item in items:
            item_season = _int_or_none(item.get("season"))
            item_episode = _int_or_none(item.get("episode"))
            if season is not None and item_season != season:
                continue
            if episode is not None:
                if item_episode == episode:
                    target = exact
                elif item_episode is None and item_season == season:
                    target = season_packs
                else:
                    continue
            else:
                target = exact
            result = self._result(video, item, requested_countries, season_pack=target is season_packs)
            if result is not None:
                target.append(result)
        return exact or season_packs

    def _result(self, video, item, requested_countries, season_pack=False):
        item = dict(item or {})
        subtitle_id = item.get("id")
        if not subtitle_id:
            return None
        language = language_payload_from_description(item.get("description") or "")
        if not _language_matches_request(language, requested_countries):
            return None
        matches = derive_matches(video, item, season_pack=season_pack)
        score = compute_score(matches)
        release_info = _release_info(item)
        filename = f"subx.{subtitle_id}.{SUPPORTED_ALPHA2}.zip"
        download_url = item.get("download_url") or f"{BASE_URL}/api/subtitles/{urllib.parse.quote(str(subtitle_id), safe='')}/download"
        page_link = item.get("page_url") or f"{BASE_URL}/api/subtitles/{urllib.parse.quote(str(subtitle_id), safe='')}"
        return {
            "provider": PROVIDER_ID,
            "id": f"subx-{subtitle_id}-{language['country']}",
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
                "source": "subx",
                "title": item.get("title"),
                "release": release_info,
                "uploader": item.get("uploader_name"),
                "downloads": item.get("downloads"),
                "variant": "Spain" if language.get("country") == "ES" else "Latin America",
            },
            "provider_payload": {
                "provider": PROVIDER_ID,
                "schema": 1,
                "subtitle_id": subtitle_id,
                "download_url": download_url,
                "filename": filename,
                "language": language,
                "season": _int_or_none(item.get("season")),
                "episode": _int_or_none(item.get("episode")),
                "season_pack": bool(season_pack),
                "release_info": release_info,
            },
        }

    def download(self, provider_payload, language, config):
        del language
        payload = provider_payload or {}
        subtitle_id = payload.get("subtitle_id")
        download_url = payload.get("download_url")
        if not download_url and subtitle_id:
            download_url = f"{BASE_URL}/api/subtitles/{urllib.parse.quote(str(subtitle_id), safe='')}/download"
        if not download_url:
            raise ValueError("subx download requires download_url or subtitle_id")
        body = self._request_bytes(download_url, dict(config or {}))
        filename = payload.get("filename") or urllib.parse.urlparse(download_url).path.rsplit("/", 1)[-1]
        return build_download_payload(body, filename, payload)

    def _request_json(self, path, params, config):
        api_key = _require_api_key(config)
        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                return self._http_get_json(path, params, api_key, timeout=HTTP_TIMEOUT_SECONDS)
            except RateLimited as error:
                last_error = error
                if attempt == MAX_RETRIES - 1:
                    break
                time.sleep(max(0, error.retry_after))
            except (RuntimeError, ValueError) as error:
                last_error = error
                if attempt == MAX_RETRIES - 1:
                    break
                time.sleep(2 ** attempt)
        if isinstance(last_error, RateLimited):
            raise last_error
        return {"items": [], "total": 0}

    def _request_bytes(self, url, config):
        api_key = _require_api_key(config)
        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                return self._http_get_bytes(url, api_key, timeout=DOWNLOAD_TIMEOUT_SECONDS)
            except RateLimited as error:
                last_error = error
                if attempt == MAX_RETRIES - 1:
                    break
                time.sleep(max(0, error.retry_after))
            except RuntimeError as error:
                last_error = error
                if attempt == MAX_RETRIES - 1:
                    break
                time.sleep(2 ** attempt)
        if last_error:
            raise last_error
        raise RuntimeError("SubX download failed")

    def _http_get_json(self, path, params, api_key, timeout=HTTP_TIMEOUT_SECONDS):
        url = _url_with_params(_absolute_url(path), params)
        body = self._http_request(url, api_key, timeout=timeout)
        try:
            return json.loads(body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("SubX API returned invalid JSON") from exc

    def _http_get_bytes(self, path, api_key, timeout=DOWNLOAD_TIMEOUT_SECONDS):
        return self._http_request(_absolute_url(path), api_key, timeout=timeout)

    def _http_request(self, url, api_key, timeout=HTTP_TIMEOUT_SECONDS):
        request = urllib.request.Request(url, headers=auth_headers(api_key))
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            body = exc.read()
            if exc.code in (400, 404):
                return b'{"items":[],"total":0}'
            if exc.code == 401:
                raise ValueError("SubX api_key is missing or invalid") from exc
            if exc.code == 429:
                retry_after = _int_or_none(exc.headers.get("Retry-After")) or 0
                raise RateLimited(_error_message(body) or "SubX rate limit exceeded", retry_after=retry_after) from exc
            if exc.code >= 500:
                raise RuntimeError(f"SubX server error {exc.code}") from exc
            raise RuntimeError(f"SubX request failed with status {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"SubX request failed: {exc.reason}") from exc


def derive_matches(video, item, season_pack=False):
    video = video or {}
    matches = []

    def add(match):
        if match not in matches:
            matches.append(match)

    if video.get("kind") == "episode":
        if video.get("series"):
            add("series")
            add("title")
        if _int_or_none(video.get("year")):
            add("year")
        video_imdb = video.get("imdb_id") or video.get("series_imdb_id")
        if video_imdb and item.get("imdb_id") == video_imdb:
            add("imdb_id")
        if _int_or_none(item.get("season")) == _int_or_none(video.get("season")):
            add("season")
        if season_pack or _int_or_none(item.get("episode")) == _int_or_none(video.get("episode")):
            add("episode")
        return matches

    if video.get("title"):
        add("title")
    if _int_or_none(video.get("year")) and _int_or_none(item.get("year") or video.get("year")) == _int_or_none(video.get("year")):
        add("year")
    if video.get("imdb_id") and item.get("imdb_id") == video.get("imdb_id"):
        add("imdb_id")
    return matches


def compute_score(matches):
    weights = {
        "title": 25,
        "series": 20,
        "year": 10,
        "imdb_id": 35,
        "season": 15,
        "episode": 20,
    }
    return min(100, sum(weights.get(match, 0) for match in matches))


def _release_info(item):
    title = str(item.get("title") or "").strip()
    description = str(item.get("description") or "").strip()
    if title and description:
        return f"{title} | {description}"
    return title or description or str(item.get("id") or "")


def _absolute_url(path):
    if str(path).startswith(("http://", "https://")):
        return str(path)
    return urllib.parse.urljoin(BASE_URL, str(path))


def _url_with_params(url, params):
    if not params:
        return url
    separator = "&" if urllib.parse.urlparse(url).query else "?"
    return f"{url}{separator}{urllib.parse.urlencode(params)}"


def _error_message(body):
    try:
        data = json.loads((body or b"").decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return data.get("detail") or data.get("message") or data.get("error")


def _sleep(config):
    delay = _int_or_none((config or {}).get("request_delay_ms")) or 0
    if delay > 0:
        time.sleep(min(delay, 5000) / 1000.0)


def _int_or_none(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def build_download_payload(body, filename="", payload=None):
    payload = payload or {}
    if not body:
        raise ValueError("subx downloaded empty subtitle")
    if _is_rar_archive(body) or zipfile.is_zipfile(io.BytesIO(body)):
        # Host-side extraction (Provider Hub v1.1+): hand the raw archive bytes
        # back to the host. SubX serves season packs (multiple episodes in one
        # zip), so when we can cheaply list a zip and find the unique member for
        # the requested season+episode, pin it; the host then reads that exact
        # member instead of guessing by episode. RAR is not stdlib-listable, and
        # an ambiguous/missing match defers to host-side episode selection.
        archive = {
            "archive_b64": base64.b64encode(body).decode("ascii"),
            "archive_sha256": hashlib.sha256(body).hexdigest(),
        }
        member = _select_zip_member(body, payload)
        if member is not None:
            archive["member"] = member
        else:
            archive["episode"] = _int_or_none(payload.get("episode"))
        return archive
    return _content_payload(body, _format_from_filename(filename))


def _select_zip_member(body, payload):
    # List the zip (no extraction or decoding) and pin the member for the
    # requested season+episode. The host does an exact namelist match that
    # hard-fails on mismatch, so only return a name on a confident unique match;
    # otherwise return None so the caller defers to host episode selection.
    payload = payload or {}
    if not zipfile.is_zipfile(io.BytesIO(body)):
        return None
    season = _int_or_none(payload.get("season"))
    episode = _int_or_none(payload.get("episode"))
    # Require both season and episode: SubX season packs reuse episode numbers
    # across seasons, so episode alone is not a confident pin. Movies and
    # season-unaware payloads defer to host-side selection.
    if season is None or episode is None:
        return None
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        names = [
            name
            for name in archive.namelist()
            if not name.endswith("/")
            and _subtitle_extension(name)
            and not os.path.basename(name).startswith(".")
        ]
    if not names:
        return None
    matches = [name for name in names if _member_has_episode(name, season, episode)]
    if len(matches) == 1:
        return matches[0]
    return None


def _member_has_episode(name, season, episode):
    # Match the episode as a delimited token in the member's basename, tolerating
    # a separator between the season and episode parts. When the season is known,
    # require it too (season packs reuse episode numbers across seasons); only
    # fall back to bare episode markers when the season is unknown.
    text = _normalize_member(os.path.basename(name))
    for regex in (_SXXEYY_RE, _NXNN_RE):
        for match in regex.finditer(text):
            if _int_or_none(match.group("episode")) != episode:
                continue
            if season is not None and _int_or_none(match.group("season")) != season:
                continue
            return True
    # Whole-token "{season}{episode:02d}" form, e.g. "101" for S01E01. Require a
    # non-alphanumeric boundary (not just non-digit) so "720" (S07E20) cannot
    # match "720p" and "264" cannot match "x264".
    if season is not None and re.search(rf"(?<![a-z0-9]){season}{episode:02d}(?![a-z0-9])", text):
        return True
    if season is None and re.search(rf"\be0*{episode}(?!\d)", text):
        return True
    return False


def _normalize_member(name):
    text = unicodedata.normalize("NFKD", str(name or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return text.lower()


def _is_rar_archive(body):
    return (body or b"").startswith((b"Rar!\x1a\x07\x00", b"Rar!\x1a\x07\x01\x00"))


def _subtitle_extension(name):
    lower = (name or "").lower()
    for extension in SUBTITLE_EXTENSIONS:
        if lower.endswith(extension):
            return extension.lstrip(".")
    return None


def _format_from_filename(filename):
    extension = _subtitle_extension(filename)
    return extension or "srt"


def _content_payload(body, fmt):
    if not body:
        raise ValueError("subx downloaded empty subtitle")
    return {
        "content_b64": base64.b64encode(body).decode("ascii"),
        "content_sha256": hashlib.sha256(body).hexdigest(),
        "content_type": _content_type(fmt),
        "format": fmt,
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
