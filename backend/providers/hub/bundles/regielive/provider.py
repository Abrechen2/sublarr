"""RegieLive provider for the Bazarr+ Provider Hub catalog."""

import base64 as _base64
import hashlib as _hashlib
import html
import io
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from http.cookiejar import CookieJar

PROVIDER_ID = "regielive"
API_URL = "https://api.regielive.ro/bazarr/search.php"
DOWNLOAD_ORIGIN = "https://subtitrari.regielive.ro"
HTML_SEARCH_URL = f"{DOWNLOAD_ORIGIN}/cauta.html"
API_HEADER_VALUE = "API-BAZARR-YTZ-SL"
HTTP_TIMEOUT_SECONDS = 15
MAX_RESULTS = 20
SUBTITLE_EXTENSIONS = (".srt", ".ass", ".ssa", ".sub", ".vtt", ".smi", ".sami")
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 BazarrProviderHub"
)

ROMANIAN = {"alpha3": "ron", "alpha2": "ro", "hi": False, "forced": False}

_HTML_SEARCH_ITEM_RE = re.compile(
    r"<li\b[^>]*>(?P<body>.*?)(?=<li\b|</ul>)",
    re.I | re.S,
)
_HTML_TITLE_LINK_RE = re.compile(
    r"<a\b(?P<attrs>[^>]*\bclass=[\"'][^\"']*\btext-xl\b[^\"']*[\"'][^>]*)>"
    r"(?P<title>.*?)</a>\s*<span\b[^>]*>\((?P<year>\d{4})\)</span>",
    re.I | re.S,
)
_HTML_DETAIL_ITEM_RE = re.compile(
    r"<li\b(?=[^>]*\bclass=[\"'][^\"']*\bsubtitrare\b)[^>]*>(?P<body>.*?)</li>",
    re.I | re.S,
)
_HTML_SUBTITLE_TITLE_RE = re.compile(
    r"<span\b(?P<attrs>[^>]*\bid=[\"']sub_(?P<id>\d+)[\"'][^>]*)>(?P<title>.*?)</span>",
    re.I | re.S,
)
_HTML_DOWNLOAD_RE = re.compile(
    r"<a\b[^>]*\bhref=[\"'](?P<href>[^\"']*descarca-[^\"']+\.zip)[\"']",
    re.I | re.S,
)
_HTML_RATING_RE = re.compile(r"\btitle=[\"']Nota\s+(?P<rating>\d+(?:[.,]\d+)?)", re.I)
_TAG_RE = re.compile(r"<[^>]+>")
_WORD_RE = re.compile(r"[a-z0-9]+")
_SXXEXX_RE = re.compile(r"\bs0*(?P<season>\d{1,2})e0*(?P<episode>\d{1,3})\b", re.I)
_X_EPISODE_RE = re.compile(r"\b0*(?P<season>\d{1,2})x0*(?P<episode>\d{1,3})\b", re.I)


def build_query_params(video):
    video = video or {}
    kind = video.get("kind")
    params = {}
    if kind == "movie":
        title = _clean_text(video.get("title"))
        if not title:
            return {}
        params["nume"] = title
    elif kind == "episode":
        series = _clean_text(video.get("series"))
        season = _clean_number(video.get("season"))
        episode = _clean_number(_first_episode(video.get("episode")))
        if not series or season is None or episode is None:
            return {}
        params["nume"] = series
        params["sezon"] = season
        params["episod"] = episode
    else:
        return {}

    year = _clean_number(video.get("year"))
    if year is not None:
        params["an"] = year
    return params


def parse_search_results(body):
    if not body:
        return []
    try:
        payload = json.loads(_decode(body))
    except (TypeError, ValueError) as exc:
        raise ValueError("regielive returned invalid JSON") from exc
    if not isinstance(payload, dict):
        return []
    groups = payload.get("rezultate")
    if not isinstance(groups, dict):
        return []

    rows = []
    seen = set()
    for group in groups.values():
        if not isinstance(group, dict):
            continue
        subtitles = group.get("subtitrari")
        if not isinstance(subtitles, dict):
            continue
        for subtitle_id, item in subtitles.items():
            if not isinstance(item, dict):
                continue
            key = str(subtitle_id)
            if key in seen:
                continue
            title = _clean_text(item.get("titlu"))
            download_url = _clean_text(item.get("url"))
            if not title or not download_url:
                continue
            seen.add(key)
            rating = item.get("rating")
            rating_value = rating.get("nota") if isinstance(rating, dict) else None
            rows.append(
                {
                    "subtitle_id": key,
                    "title": title,
                    "download_url": download_url,
                    "rating": _safe_float(rating_value),
                }
            )
    return rows


def parse_html_search_results(body, video):
    video = video or {}
    rows = []
    seen = set()
    for match in _HTML_SEARCH_ITEM_RE.finditer(_decode(body)):
        item = match.group("body")
        title_match = _HTML_TITLE_LINK_RE.search(item)
        if not title_match:
            continue
        url = _attr(title_match.group("attrs"), "href")
        title = _strip_tags(title_match.group("title"))
        year = title_match.group("year")
        kind = "episode" if "tag-serial" in item else "movie"
        if not url or not title:
            continue
        row = {
            "title": title,
            "url": urllib.parse.urljoin(DOWNLOAD_ORIGIN, url),
            "year": year,
            "kind": kind,
        }
        key = row["url"]
        if key in seen or not _html_media_matches_video(row, video):
            continue
        seen.add(key)
        rows.append(row)
    return rows


def parse_html_detail_results(body, detail_url):
    rows = []
    for match in _HTML_DETAIL_ITEM_RE.finditer(_decode(body)):
        item = match.group("body")
        title_match = _HTML_SUBTITLE_TITLE_RE.search(item)
        download_match = _HTML_DOWNLOAD_RE.search(item)
        if not title_match or not download_match:
            continue
        title = _strip_tags(title_match.group("title"))
        download_url = urllib.parse.urljoin(detail_url, html.unescape(download_match.group("href")))
        if not title or not download_url:
            continue
        rating_match = _HTML_RATING_RE.search(item)
        rating = _safe_float((rating_match.group("rating") if rating_match else "").replace(",", "."))
        rows.append(
            {
                "subtitle_id": title_match.group("id"),
                "title": title,
                "download_url": download_url,
                "rating": rating,
            }
        )
    return rows


class RegieLiveProvider:
    def __init__(self):
        cookie_jar = CookieJar()
        self._opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))

    def _http_get(self, url, headers=None, timeout=HTTP_TIMEOUT_SECONDS, referer=None):
        merged_headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json,text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,ro;q=0.8",
        }
        if headers:
            merged_headers.update(headers)
        if referer:
            merged_headers["Referer"] = referer
        request = urllib.request.Request(url, headers=merged_headers)
        try:
            with self._opener.open(request, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                raise RuntimeError("regielive rate limit reached") from exc
            if exc.code == 403:
                raise RuntimeError("regielive rejected the request") from exc
            raise RuntimeError(f"regielive HTTP {exc.code}") from exc
        except OSError as exc:
            raise RuntimeError("regielive request failed") from exc

    def search(self, video, languages, config):
        if not _requests_romanian(languages):
            return []
        params = build_query_params(video)
        if not params:
            return []

        _sleep(config)
        url = f"{API_URL}?{urllib.parse.urlencode(params)}"
        try:
            body = self._http_get(url, headers={"RL-API": API_HEADER_VALUE})
            rows = parse_search_results(body)
        except RuntimeError as exc:
            if "rejected the request" not in str(exc):
                raise
            rows = self._search_html(video, config or {})
        results = [self._result(video or {}, row) for row in rows]
        results.sort(key=lambda item: (-item["score"], item["release_info"].lower()))
        return results[:MAX_RESULTS]

    def _search_html(self, video, config):
        query = _html_query(video)
        if not query:
            return []
        search_url = f"{HTML_SEARCH_URL}?{urllib.parse.urlencode({'s': query})}"
        _sleep(config)
        search_body = self._http_get(search_url)
        rows = []
        for media in parse_html_search_results(search_body, video)[:3]:
            # Serial root pages only render the default/latest season, so an older
            # season request must follow the explicit season URL instead.
            detail_url = _season_detail_url(media["url"], video)
            _sleep(config)
            detail_body = self._http_get(detail_url, referer=search_url)
            for row in parse_html_detail_results(detail_body, detail_url):
                if not _html_subtitle_matches_video(row, video):
                    continue
                row = dict(row)
                row["year"] = media.get("year")
                rows.append(row)
        return rows

    def download(self, provider_payload, language, config):
        del language
        payload = provider_payload or {}
        download_url = _clean_text(payload.get("download_url") or payload.get("url"))
        if not download_url:
            raise ValueError("regielive download requires download_url in provider_payload")

        _sleep(config)
        self._http_get(DOWNLOAD_ORIGIN)
        _sleep(config)
        archive_body = self._http_get(download_url, referer=DOWNLOAD_ORIGIN)
        if archive_body.strip() == b"500":
            raise ValueError("regielive returned server error 500")
        return _download_payload(archive_body)

    def _result(self, video, row):
        matches = derive_matches(video, row["title"])
        score = min(100, 80 + int(round(row["rating"] * 2)))
        if "episode" in matches:
            score = max(score, 96)
        elif "year" in matches:
            score = max(score, 92)
        return {
            "provider": PROVIDER_ID,
            "id": f"regielive-{row['subtitle_id']}",
            "language": dict(ROMANIAN),
            "release_info": row["title"],
            "filename": f"regielive.{row['subtitle_id']}.srt",
            "matches": matches,
            "score": score,
            "score_without_hash": score,
            "score_out_of": 100,
            "hash_verifiable": False,
            "hearing_impaired_verifiable": False,
            "hearing_impaired": False,
            "download_count": int(round(row["rating"] * 100)) if row["rating"] else 0,
            "page_link": row["download_url"],
            "display": {
                "source": "RegieLive",
                "title": row["title"],
                "rating": row["rating"],
            },
            "provider_payload": {
                "provider": PROVIDER_ID,
                "schema": 1,
                "subtitle_id": row["subtitle_id"],
                "download_url": row["download_url"],
                "filename": row["title"],
            },
        }


def derive_matches(video, release_info):
    video = video or {}
    release_text = _clean_text(release_info).lower()
    matches = []
    if video.get("kind") == "episode":
        if video.get("series"):
            matches.append("series")
        if video.get("season") is not None:
            matches.append("season")
        if video.get("episode") is not None:
            matches.append("episode")
        if video.get("year") is not None:
            matches.append("year")
    elif video.get("kind") == "movie":
        if video.get("title"):
            matches.append("title")
        if video.get("year") is not None:
            matches.append("year")

    release_group = _clean_text(video.get("release_group")).lower()
    if release_group and release_group in release_text:
        matches.append("release_group")
        matches.append("hash")
    return matches


def select_zip_member(body):
    try:
        archive = zipfile.ZipFile(io.BytesIO(body or b""))
    except zipfile.BadZipFile as exc:
        raise ValueError("regielive download is not a ZIP archive") from exc

    candidates = []
    for name in archive.namelist():
        basename = os.path.basename(name)
        lowered = basename.lower()
        if not basename or basename.startswith("."):
            continue
        if not lowered.endswith(SUBTITLE_EXTENSIONS):
            continue
        candidates.append(name)
    if not candidates:
        raise ValueError("regielive archive contained no subtitle files")
    candidates.sort(key=lambda name: (not name.lower().endswith(".srt"), len(name), name.lower()))
    return candidates[0]


def _requests_romanian(languages):
    for language in languages or []:
        if not isinstance(language, dict):
            continue
        # RegieLive only exposes normal subtitles, so a forced-only or HI-only
        # Romanian request must be skipped rather than served a regular subtitle.
        if language.get("forced") or language.get("hi"):
            continue
        alpha3 = (language.get("alpha3") or "").lower()
        alpha2 = (language.get("alpha2") or "").lower()
        if alpha3 == "ron" or alpha2 == "ro":
            return True
    return False


def _html_query(video):
    video = video or {}
    if video.get("kind") == "movie":
        return _clean_text(video.get("title"))
    if video.get("kind") == "episode":
        return _clean_text(video.get("series"))
    return ""


def _season_detail_url(media_url, video):
    video = video or {}
    if video.get("kind") != "episode":
        return media_url
    season = _clean_number(video.get("season"))
    if season is None:
        return media_url
    base = media_url if media_url.endswith("/") else media_url + "/"
    return urllib.parse.urljoin(base, f"sezonul-{season}/")


def _html_media_matches_video(row, video):
    video = video or {}
    if video.get("kind") and row.get("kind") and row["kind"] != video["kind"]:
        return False
    expected_year = _clean_number(video.get("year"))
    if expected_year and row.get("year") and expected_year != str(row["year"]):
        return False
    expected_title = _html_query(video)
    if expected_title and _normalized_words(row.get("title")) != _normalized_words(expected_title):
        return False
    return True


def _html_subtitle_matches_video(row, video):
    video = video or {}
    if video.get("kind") != "episode":
        return True
    try:
        expected_season = int(video.get("season"))
        expected_episode = int(_first_episode(video.get("episode")))
    except (TypeError, ValueError):
        return True
    release = _clean_text(row.get("title"))
    for pattern in (_SXXEXX_RE, _X_EPISODE_RE):
        match = pattern.search(release)
        if match:
            return int(match.group("season")) == expected_season and int(match.group("episode")) == expected_episode
    return False


def _normalized_words(value):
    return " ".join(_WORD_RE.findall(_clean_text(value).lower()))


def _attr(tag, name):
    match = re.search(rf"\b{name}\s*=\s*([\"'])(?P<value>.*?)\1", tag or "", re.I | re.S)
    return html.unescape(match.group("value")) if match else ""


def _strip_tags(value):
    return _clean_text(_TAG_RE.sub(" ", value or ""))


def _clean_text(value):
    if value is None:
        return ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    return " ".join(html.unescape(str(value)).split())


def _clean_number(value):
    if value is None or value == "":
        return None
    try:
        return str(int(value))
    except (TypeError, ValueError):
        return None


def _first_episode(value):
    # Bazarr passes multi-episode releases as a list such as [1, 2]; collapse it
    # to the lowest episode so the search still targets a concrete episode.
    if isinstance(value, (list, tuple)):
        numbers = [number for number in (_clean_number(item) for item in value) if number is not None]
        if not numbers:
            return None
        return min(numbers, key=int)
    return value


def _safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _decode(body):
    if isinstance(body, str):
        return body
    return (body or b"").decode("utf-8", errors="replace")


def _download_payload(body):
    # Reject broken responses up front: the download endpoint can answer with an empty
    # stream or an HTML/error page that would otherwise look like a successful download.
    if not body or not body.strip():
        raise ValueError("regielive downloaded empty subtitle")
    if _is_html_body(body):
        raise ValueError("regielive returned an HTML/error page")
    if _is_archive_body(body):
        # Host-side extraction (Provider Hub v1.1+): hand the raw archive bytes back to
        # the host, which extracts the selected member and detects encoding. The worker
        # still lists the zip cheaply to pick the member it selected before.
        payload = {
            "archive_b64": _base64.b64encode(body).decode("ascii"),
            "archive_sha256": _hashlib.sha256(body).hexdigest(),
        }
        if zipfile.is_zipfile(io.BytesIO(body)):
            payload["member"] = select_zip_member(body)
        return payload
    raise ValueError("regielive download is not a ZIP archive")


def _is_archive_body(body):
    if not body:
        return False
    return (
        zipfile.is_zipfile(io.BytesIO(body))
        or body.startswith(b"Rar!")
        or body.startswith(b"7z\xbc\xaf\x27\x1c")
    )


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


def _sleep(config):
    delay_ms = (config or {}).get("request_delay_ms", 0) or 0
    try:
        delay_ms = int(delay_ms)
    except (TypeError, ValueError):
        delay_ms = 0
    if delay_ms > 0:
        time.sleep(min(delay_ms, 5000) / 1000.0)
