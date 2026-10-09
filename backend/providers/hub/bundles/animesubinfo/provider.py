"""AnimeSub.info provider for the Bazarr+ Provider Hub catalog."""

import base64 as _base64
import hashlib as _hashlib
import html
import io
import os
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from html.parser import HTMLParser
from http.cookiejar import CookieJar

PROVIDER_ID = "animesubinfo"
BASE_URL = "http://animesub.info"
SEARCH_URL = f"{BASE_URL}/szukaj.php"
DOWNLOAD_URL = f"{BASE_URL}/sciagnij.php"
HTTP_TIMEOUT_SECONDS = 15
HTTP_RETRIES = 2
RETRY_BACKOFF_SECONDS = 0.5
RETRY_BACKOFF_CAP_SECONDS = 8.0
RETRY_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
SUPPORTED_LANGUAGES = {"pol": "pl"}
ALPHA2_TO_ALPHA3 = {value: key for key, value in SUPPORTED_LANGUAGES.items()}
SUBTITLE_EXTENSIONS = (".srt", ".ass", ".ssa", ".sub")
USER_AGENT = os.environ.get("SZ_USER_AGENT", "Sub-Zero/2")

_NON_ALNUM_RE = re.compile(r"[\W_]+", re.UNICODE)
_EPISODE_RE = re.compile(r"\b(?:ep|episode)\s*0*(\d{1,4})\b", re.I)
_SEASON_RE = re.compile(r"\b(?:season|s)\s*0*(\d{1,2})\b|\b(\d{1,2})(?:nd|rd|th)\s+season\b", re.I)
_SEASON_EPISODE_FILE_RE = re.compile(r"(?<![a-z0-9])s\d{1,2}\s*e0*(\d{1,3})(?!\d)", re.I)
_EPISODE_FILE_RE = re.compile(r"\b(?:ep|episode)\s*0*(\d{1,4})\b", re.I)
_EPISODE_X_FILE_RE = re.compile(r"(?<![a-z0-9])\d{1,2}x0*(\d{1,3})(?!\d)", re.I)
_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")


def parse_search_results(body):
    parser = _SubtitleTableParser()
    parser.feed(_decode_body(body))
    rows = []
    for table in parser.tables:
        row = _row_from_table(table)
        if row:
            rows.append(row)
    return rows


def build_search_strategies(video):
    video = video or {}
    kind = video.get("kind")
    strategies = []
    if kind == "episode":
        series = video.get("series")
        if not series:
            return []
        episode_query = _episode_query(series, video)
        if episode_query:
            strategies.extend([("org", episode_query), ("en", episode_query), ("pl", episode_query)])
        else:
            strategies.extend([("org", series), ("en", series), ("pl", series)])
        for alternative in (video.get("alternative_series") or [])[:2]:
            if episode_query:
                strategies.append(("en", _episode_query(alternative, video)))
            strategies.append(("en", alternative))
    elif kind == "movie":
        title = video.get("title")
        if not title:
            return []
        strategies.extend([("org", title), ("en", title), ("pl", title)])
        for alternative in (video.get("alternative_titles") or [])[:2]:
            strategies.extend([("en", alternative), ("org", alternative)])
    return _dedupe_pairs(strategies)


def search_url_for(query, title_type):
    return f"{SEARCH_URL}?{urllib.parse.urlencode({'szukane': query, 'pTitle': title_type, 'pSortuj': 'pobrn'})}"


def derive_matches(video, row):
    video = video or {}
    kind = video.get("kind")
    matches = []
    titles = [row.get("title_org"), row.get("title_eng"), row.get("title_alt")]
    normalized_titles = [_normalize(title) for title in titles if title]
    if kind == "episode":
        wanted = _normalize(video.get("series"))
        alternatives = [_normalize(item) for item in video.get("alternative_series", [])]
        if wanted and any(wanted in title or title in wanted for title in normalized_titles):
            matches.append("series")
        elif any(alt and any(alt in title or title in alt for title in normalized_titles) for alt in alternatives):
            matches.append("series")
        season, episode = parse_episode_info(row)
        try:
            wanted_season = int(video.get("season"))
        except (TypeError, ValueError):
            wanted_season = None
        if wanted_season is not None and (season == wanted_season or (wanted_season == 1 and season is None)):
            matches.append("season")
        wanted_episodes = set()
        for key in ("absolute_episode", "episode"):
            try:
                wanted_episodes.add(int(video.get(key)))
            except (TypeError, ValueError):
                pass
        if episode is not None and episode in wanted_episodes:
            matches.append("episode")
        wanted_group = (video.get("release_group") or "").lower()
        if wanted_group and any(wanted_group == group.lower() for group in row.get("release_groups", [])):
            matches.append("release_group")
    elif kind == "movie":
        wanted = _normalize(video.get("title"))
        if wanted and any(wanted in title or title in wanted for title in normalized_titles):
            matches.append("title")
        try:
            year = int(video.get("year"))
        except (TypeError, ValueError):
            year = None
        if year is not None and any(str(year) in str(title or "") for title in titles):
            matches.append("year")
        matches.append("movie")
    if "advanced ssa" in (row.get("format_type") or "").lower():
        matches.append("audio_codec")
    return _dedupe(matches)


def parse_episode_info(row):
    season = None
    episode = None
    for title in (row.get("title_org"), row.get("title_eng"), row.get("title_alt")):
        if title and episode is None:
            match = _EPISODE_RE.search(title)
            if match:
                episode = int(match.group(1))
        if title and season is None:
            match = _SEASON_RE.search(title)
            if match:
                season = int(match.group(1) or match.group(2))
    return season, episode


class AnimeSubInfoProvider:
    def __init__(self):
        self._cookie_jar = CookieJar()
        self._opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self._cookie_jar))

    def _http_get(self, url, timeout=HTTP_TIMEOUT_SECONDS, referer=None):
        request = urllib.request.Request(url, headers=_headers(referer=referer))
        return self._open_with_retry(request, timeout)

    def _http_post(self, url, data, timeout=HTTP_TIMEOUT_SECONDS, referer=None):
        encoded = urllib.parse.urlencode(data).encode("iso-8859-2", errors="replace")
        headers = _headers(referer=referer)
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        request = urllib.request.Request(url, data=encoded, headers=headers)
        return self._open_with_retry(request, timeout)

    def _open_with_retry(self, request, timeout):
        # Bounded transport retry around the raw urllib call only. Retries transient
        # failures (connection errors, timeouts, HTTP 5xx and 429) so a single network
        # blip does not abort a search or download. Non-transient errors (HTTP 4xx other
        # than 429, parse errors, etc.) propagate unchanged on the first occurrence.
        for attempt in range(1, HTTP_RETRIES + 2):
            try:
                with self._opener.open(request, timeout=timeout) as response:
                    return response.read()
            except urllib.error.HTTPError as error:
                if error.code not in RETRY_STATUS_CODES or attempt > HTTP_RETRIES:
                    raise
                delay = _retry_after_delay(error) if error.code == 429 else None
                if delay is None:
                    delay = _backoff_delay(attempt)
                time.sleep(delay)
            except (TimeoutError, socket.timeout, urllib.error.URLError):
                if attempt > HTTP_RETRIES:
                    raise
                time.sleep(_backoff_delay(attempt))
        raise RuntimeError("unreachable animesubinfo retry state")

    def search(self, video, languages, config):
        if (video or {}).get("kind") not in {"movie", "episode"}:
            return []
        requested = {_alpha3_for_language(language) for language in languages or []}
        if "pol" not in requested:
            return []
        config = dict(config or {})
        results = []
        seen = set()
        for title_type, query in build_search_strategies(video):
            url = search_url_for(query, title_type)
            _sleep(config)
            rows = parse_search_results(self._http_get(url))
            for row in rows:
                subtitle_id = row["subtitle_id"]
                if subtitle_id in seen:
                    continue
                seen.add(subtitle_id)
                row = dict(row)
                row["search_query"] = query
                row["title_type"] = title_type
                row["search_url"] = url
                results.append(self._result(video, row))
            if rows and (video or {}).get("kind") == "episode" and _contains_episode_marker(query):
                break
        return sorted(results, key=lambda item: item["score"], reverse=True)

    def _result(self, video, row):
        matches = derive_matches(video, row)
        score = _score(matches, row)
        release_info = _release_info(row)
        filename = f"animesubinfo.{_slug(release_info)}.{row['subtitle_id']}.pl.zip"
        payload = {
            "provider": PROVIDER_ID,
            "schema": 1,
            "subtitle_id": row["subtitle_id"],
            "download_hash": row["download_hash"],
            "download_url": row["download_url"],
            "search_url": row["search_url"],
            "search_query": row["search_query"],
            "title_type": row["title_type"],
            "filename": filename,
            "title_org": row.get("title_org"),
            "title_eng": row.get("title_eng"),
            "title_alt": row.get("title_alt"),
            "author": row.get("author"),
            "format_type": row.get("format_type"),
            "size": row.get("size"),
            "download_count": row.get("download_count", 0),
            "description": row.get("description"),
            "release_groups": row.get("release_groups", []),
        }
        season, episode = parse_episode_info(row)
        if season is not None:
            payload["season"] = season
        if episode is not None:
            payload["episode"] = episode
        return {
            "provider": PROVIDER_ID,
            "id": f"animesubinfo-{row['subtitle_id']}-pol",
            "language": {
                "alpha3": "pol",
                "alpha2": "pl",
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
            "page_link": BASE_URL + "/",
            "display": {
                "source": "animesubinfo",
                "title": row.get("title_org") or row.get("title_eng") or row.get("title_alt"),
                "release": release_info,
                "uploader": row.get("author"),
                "downloads": row.get("download_count", 0),
                "format": row.get("format_type"),
            },
            "provider_payload": payload,
        }

    def download(self, provider_payload, language, config):
        del language, config
        payload = dict(provider_payload or {})
        body = self._download_once(payload)
        if _looks_like_security_error(body):
            refreshed = self._refresh_download_hash(payload)
            body = self._download_once(refreshed)
            payload = refreshed
        if _looks_like_security_error(body):
            raise RuntimeError("AnimeSub.info download token was rejected")
        return _download_payload(body, payload)

    def _download_once(self, payload):
        url = payload.get("download_url") or DOWNLOAD_URL
        subtitle_id = payload.get("subtitle_id")
        download_hash = payload.get("download_hash")
        if not subtitle_id or not download_hash:
            raise ValueError("animesubinfo download requires subtitle_id and download_hash")
        data = {"id": subtitle_id, "sh": download_hash, "single_file": "Pobierz napisy"}
        return self._http_post(url, data, referer=payload.get("search_url"))

    def _refresh_download_hash(self, payload):
        query = payload.get("search_query")
        title_type = payload.get("title_type")
        search_url = payload.get("search_url")
        if not search_url:
            if not query or not title_type:
                raise RuntimeError("AnimeSub.info download token expired and cannot be refreshed")
            search_url = search_url_for(query, title_type)
        rows = parse_search_results(self._http_get(search_url))
        for row in rows:
            if row.get("subtitle_id") == payload.get("subtitle_id"):
                refreshed = dict(payload)
                refreshed["download_hash"] = row["download_hash"]
                refreshed["download_url"] = row["download_url"]
                refreshed["search_url"] = search_url
                return refreshed
        raise RuntimeError("AnimeSub.info download token expired and subtitle was not found during refresh")


def _download_payload(body, payload=None):
    payload = payload or {}
    if not body or not body.strip():
        raise ValueError(f"animesubinfo empty download for subtitle {payload.get('subtitle_id')}")
    if zipfile.is_zipfile(io.BytesIO(body)):
        # Host-side extraction (Provider Hub v1.1+): list the zip cheaply with stdlib to
        # pick the member, then hand the raw archive bytes back. The host extracts the
        # member and detects encoding via Subtitle.normalize().
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            member = select_subtitle_file(archive.namelist(), payload)
        return {
            "archive_b64": _base64.b64encode(body).decode("ascii"),
            "archive_sha256": _hashlib.sha256(body).hexdigest(),
            "member": member,
        }
    if _is_rar_archive(body) or _is_7z_archive(body):
        # rar/7z cannot be listed with stdlib; let the host pick the member by episode.
        return {
            "archive_b64": _base64.b64encode(body).decode("ascii"),
            "archive_sha256": _hashlib.sha256(body).hexdigest(),
            "episode": payload.get("episode"),
        }
    # Direct, non-archive subtitle body.
    if _looks_like_html(body):
        raise ValueError(f"animesubinfo returned an HTML/error page for subtitle {payload.get('subtitle_id')}")
    subtitle_format = _subtitle_format_from_body(body) or _format_from_filename(payload.get("filename"))
    return _content_payload(_normalize_line_endings(body), subtitle_format)


def select_subtitle_file(names, payload):
    candidates = [name for name in names if _subtitle_extension(name)]
    if not candidates:
        raise ValueError("animesubinfo archive contains no supported subtitle files")
    try:
        episode = int((payload or {}).get("episode"))
    except (TypeError, ValueError):
        episode = None

    if episode is not None:
        explicit_matches = [name for name in candidates if episode in _explicit_episode_numbers(name)]
        explicit_nonmatches = [
            name
            for name in candidates
            if _explicit_episode_numbers(name) and episode not in _explicit_episode_numbers(name)
        ]
        generic_matches = [
            name
            for name in candidates
            if not _explicit_episode_numbers(name) and _has_standalone_episode_number(name, episode)
        ]
        if explicit_matches:
            candidates = explicit_matches
        elif explicit_nonmatches and generic_matches:
            candidates = generic_matches
        elif explicit_nonmatches:
            raise ValueError("animesubinfo archive contains no subtitle file for requested episode")

    def sort_key(name):
        episode_rank = 1
        if episode is not None and _filename_episode_matches(name, episode):
            episode_rank = 0
        return (episode_rank, _extension_rank(name), len(name), name.lower())

    return sorted(candidates, key=sort_key)[0]


def _explicit_episode_numbers(name):
    basename = os.path.basename(name or "").lower()
    numbers = []
    for pattern in (_SEASON_EPISODE_FILE_RE, _EPISODE_FILE_RE, _EPISODE_X_FILE_RE):
        for match in pattern.finditer(basename):
            try:
                numbers.append(int(match.group(1)))
            except (TypeError, ValueError):
                pass
    return numbers


def _has_standalone_episode_number(name, episode):
    basename = os.path.basename(name or "").lower()
    return re.search(rf"(?<![a-z0-9])0*{int(episode)}(?![a-z0-9])", basename) is not None


def _filename_episode_matches(name, episode):
    explicit_numbers = _explicit_episode_numbers(name)
    if explicit_numbers:
        return int(episode) in explicit_numbers
    return _has_standalone_episode_number(name, episode)


class _SubtitleTableParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []
        self._target_depth = 0
        self._table = None
        self._row = None
        self._cell = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "table":
            if self._target_depth:
                self._target_depth += 1
                return
            table_class = attrs.get("class", "")
            style = attrs.get("style", "").replace(" ", "").lower()
            if "Napisy" in table_class and "text-align:center" in style:
                self._target_depth = 1
                self._table = []
            return
        if self._target_depth != 1:
            return
        if tag == "tr":
            self._row = {
                "class": attrs.get("class", ""),
                "cells": [],
                "inputs": {},
                "form_action": None,
            }
        elif tag == "td" and self._row is not None:
            self._cell = []
        elif tag == "br" and self._cell is not None:
            self._cell.append("\n")
        elif tag == "form" and self._row is not None:
            self._row["form_action"] = attrs.get("action")
        elif tag == "input" and self._row is not None:
            name = attrs.get("name")
            if name:
                self._row["inputs"][name] = html.unescape(attrs.get("value", ""))

    def handle_endtag(self, tag):
        if self._target_depth == 1:
            if tag == "td" and self._row is not None and self._cell is not None:
                self._row["cells"].append(_clean_cell_text("".join(self._cell)))
                self._cell = None
                return
            if tag == "tr" and self._table is not None and self._row is not None:
                self._table.append(self._row)
                self._row = None
                return
            if tag == "table":
                self.tables.append(self._table or [])
                self._table = None
                self._target_depth = 0
                return
        if tag == "table" and self._target_depth:
            self._target_depth -= 1

    def handle_data(self, data):
        if self._target_depth == 1 and self._cell is not None:
            self._cell.append(data)


def _row_from_table(table):
    knap_rows = [row for row in table if "KNap" in row.get("class", "")]
    comment_rows = [row for row in table if "KKom" in row.get("class", "")]
    if len(knap_rows) < 3 or not comment_rows:
        return None
    first = knap_rows[0]["cells"]
    second = knap_rows[1]["cells"]
    third = knap_rows[2]["cells"]
    comment = comment_rows[0]
    subtitle_id = comment["inputs"].get("id")
    download_hash = comment["inputs"].get("sh")
    if not subtitle_id or not download_hash:
        return None
    description = comment["cells"][1] if len(comment["cells"]) > 1 else ""
    row = {
        "subtitle_id": subtitle_id,
        "title_org": first[0] if len(first) > 0 else "",
        "date_added": first[1] if len(first) > 1 else "",
        "format_type": first[3] if len(first) > 3 else "",
        "title_eng": second[0] if len(second) > 0 else "",
        "author": _clean_author(second[1] if len(second) > 1 else ""),
        "size": second[-1] if second else "",
        "title_alt": third[0] if len(third) > 0 else "",
        "download_count": _download_count(third[3] if len(third) > 3 else ""),
        "download_hash": download_hash,
        "download_url": _absolute_url(comment.get("form_action") or "sciagnij.php"),
        "description": description,
    }
    row["release_groups"] = parse_release_groups(description)
    return row


def parse_release_groups(description):
    if not description:
        return []
    match = re.search(r"\bSynchro(?:\s+do)?\s*:?\s*([^\n]+)", description, re.I)
    if not match:
        return []
    text = match.group(1).strip()
    groups = []
    groups.extend(re.findall(r"\[([^\]]+)\]", text))
    cleaned = re.sub(r"\[([^\]]+)\]", r"\1", text)
    cleaned = re.sub(r"\([^)]+\)", "", cleaned)
    for part in cleaned.split(","):
        value = part.strip()
        if value:
            groups.append(value)
    return _dedupe([group.strip() for group in groups if group.strip()])


def _score(matches, row):
    score = 55
    if "title" in matches or "series" in matches:
        score += 18
    if "year" in matches:
        score += 8
    if "season" in matches:
        score += 6
    if "episode" in matches:
        score += 14
    if "release_group" in matches:
        score += 5
    if "audio_codec" in matches:
        score += 4
    try:
        downloads = int(row.get("download_count") or 0)
    except (TypeError, ValueError):
        downloads = 0
    if downloads:
        score += min(downloads // 1000, 4)
    return min(score, 100)


def _episode_query(series, video):
    episode = video.get("absolute_episode")
    if episode:
        try:
            return f"{series} ep{int(episode)}"
        except (TypeError, ValueError):
            return None
    episode = video.get("episode")
    if episode:
        try:
            return f"{series} ep{int(episode):02d}"
        except (TypeError, ValueError):
            return None
    return None


def _contains_episode_marker(value):
    return _EPISODE_RE.search(value or "") is not None


def _release_info(row):
    title_org = row.get("title_org") or ""
    title_eng = row.get("title_eng") or ""
    if title_eng and _normalize(title_eng) != _normalize(title_org):
        return f"{title_org} - {title_eng}".strip(" -")
    return title_org or title_eng or row.get("title_alt") or f"AnimeSub.info {row['subtitle_id']}"


def _looks_like_security_error(body):
    if not body or len(body) > 2048:
        return False
    text = _decode_body(body).lower()
    return "<html" in text and ("zabezpiec" in text or "security" in text or "blad" in text or "błąd" in text)


def _headers(referer=None):
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Charset": "ISO-8859-2,utf-8;q=0.7,*;q=0.3",
        "Accept-Language": "pl,en-US;q=0.7,en;q=0.3",
    }
    if referer:
        headers["Referer"] = referer
    return headers


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


def _backoff_delay(attempt):
    return min(RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1)), RETRY_BACKOFF_CAP_SECONDS)


def _retry_after_delay(error):
    # Honor a Retry-After header on 429 when it is a small, parseable number of seconds.
    try:
        header = error.headers.get("Retry-After")
    except AttributeError:
        header = None
    if not header:
        return None
    value = str(header).strip()
    if not value.isdigit():
        return None
    return min(float(value), RETRY_BACKOFF_CAP_SECONDS)


def _absolute_url(value):
    joined = urllib.parse.urljoin(f"{BASE_URL}/", html.unescape(str(value or "")))
    parts = urllib.parse.urlsplit(joined)
    path = urllib.parse.quote(parts.path, safe="/%:@+")
    query = urllib.parse.quote(parts.query, safe="=&%:+")
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, query, parts.fragment))


def _download_count(value):
    match = re.search(r"\d+", value or "")
    return int(match.group(0)) if match else 0


def _clean_author(value):
    return re.sub(r"^~+", "", _clean_cell_text(value)).strip()


def _clean_cell_text(value):
    value = html.unescape(str(value or "")).replace("\r", "\n").replace("\xa0", " ")
    lines = [re.sub(r"[ \t\f\v]+", " ", line).strip() for line in value.split("\n")]
    return "\n".join(line for line in lines if line)


def _dedupe(values):
    seen = set()
    output = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output


def _dedupe_pairs(pairs):
    seen = set()
    output = []
    for pair in pairs:
        if not pair[1] or pair in seen:
            continue
        seen.add(pair)
        output.append(pair)
    return output


def _normalize(value):
    if value is None:
        return ""
    return _NON_ALNUM_RE.sub(" ", str(value).lower()).strip()


def _slug(value):
    return re.sub(r"\s+", "-", _normalize(value)).strip("-") or "subtitle"


def _format_from_filename(filename):
    return _subtitle_extension(filename or "") or "srt"


def _subtitle_format_from_body(body):
    normalized = _normalize_line_endings(body or b"").lstrip(b"\xef\xbb\xbf")
    sample = normalized[:4096].lstrip().lower()
    if not sample or sample.startswith(b"<!doctype") or sample.startswith(b"<html") or b"<html" in sample[:200]:
        return None
    if b"[v4 styles]" in sample:
        return "ssa"
    if b"[script info]" in sample or b"[events]" in sample or b"dialogue:" in sample:
        return "ass"
    if re.search(
        rb"(?m)^\s*\d+\s*\n\s*\d{2}:\d{2}:\d{2}[,.]\d{3}\s+-->\s+\d{2}:\d{2}:\d{2}",
        normalized,
    ):
        return "srt"
    return None


def _subtitle_extension(name):
    lowered = (name or "").lower()
    for extension in SUBTITLE_EXTENSIONS:
        if lowered.endswith(extension):
            return extension[1:]
    return None


def _extension_rank(name):
    suffix = "." + (name or "").rsplit(".", 1)[-1].lower()
    return {".srt": 0, ".ass": 1, ".ssa": 2, ".sub": 3}.get(suffix, 9)


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
    if subtitle_format == "sub":
        return "text/plain"
    return "application/x-subrip"


def _is_rar_archive(body):
    return bool(body) and (body.startswith(b"Rar!\x1a\x07\x00") or body.startswith(b"Rar!\x1a\x07\x01\x00"))


def _is_7z_archive(body):
    return bool(body) and body.startswith(b"7z\xbc\xaf\x27\x1c")


def _looks_like_html(body):
    if not body:
        return False
    head = body[:1024].lstrip().lower()
    return head.startswith(b"<!doctype html") or head.startswith(b"<html") or b"<html" in head[:200]


def _normalize_line_endings(body):
    return (body or b"").replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _decode_body(body):
    if isinstance(body, bytes):
        try:
            return body.decode("utf-8")
        except UnicodeDecodeError:
            return body.decode("iso-8859-2", errors="replace")
    return str(body or "")
