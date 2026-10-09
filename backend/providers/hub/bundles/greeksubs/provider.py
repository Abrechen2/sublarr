"""GreekSubs provider for the Bazarr+ Provider Hub catalog."""

import base64
import hashlib
import html
import http.cookiejar
import os
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

PROVIDER_ID = "greeksubs"
BASE_URL = "https://greeksubs.net"
HTTP_TIMEOUT_SECONDS = 20
HTTP_MAX_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 0.5
RETRY_BACKOFF_CAP_SECONDS = 8
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
MAX_RESULTS = 25
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

GREEK_LANGUAGE = {
    "alpha3": "ell",
    "alpha2": "el",
    "hi": False,
    "forced": False,
}
LANGUAGE_BY_ALPHA2 = {"el": "ell", "gr": "ell"}
SUBTITLE_FORMATS = {"srt", "ass", "ssa", "sub", "vtt"}

_WS_RE = re.compile(r"\s+")
_NON_WORD_RE = re.compile(r"[\W_]+", re.UNICODE)
_DOWNLOAD_ID_RE = re.compile(r"downloadMe\(['\"]([^'\"]+)['\"]\)")
_EPISODE_LINK_RE = re.compile(
    r"""<a\b[^>]*href=["'](?P<href>[^"']+)["'][^>]*>(?P<text>.*?)</a>""",
    re.I | re.S,
)
_SEASON_EPISODE_RE = re.compile(r"\bseason\s+0*(\d+)\s+episode\s+0*(\d+)\b", re.I)
_IMDB_RE = re.compile(r"/view/(tt\d+)", re.I)
_TAG_RE = re.compile(r"<[^>]+>")


class _SubtitlePageParser(HTMLParser):
    def __init__(self, page_url):
        super().__init__(convert_charrefs=True)
        self.page_url = page_url
        self.sec_code = ""
        self.title = ""
        self.rows = []
        self._in_title = False
        self._title_text = []
        self._in_table = False
        self._table_depth = 0
        self._in_row = False
        self._in_cell = False
        self._cell_text = []
        self._cells = []
        self._row = {}
        self._in_user = False
        self._user_text = []

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == "title":
            self._in_title = True
            self._title_text = []
            return
        if tag == "input" and attrs_dict.get("id") == "secCode":
            self.sec_code = attrs_dict.get("value", "")
        if tag == "table" and attrs_dict.get("id") == "elSub":
            self._in_table = True
            self._table_depth = 1
            return
        if self._in_table and tag == "table":
            self._table_depth += 1
        if self._in_table and tag == "tr":
            self._in_row = True
            self._cells = []
            self._row = {"page_url": self.page_url}
        if self._in_row and tag == "td":
            self._in_cell = True
            self._cell_text = []
        if self._in_row and tag == "img":
            alpha2 = (attrs_dict.get("alt") or "").lower()
            alpha3 = LANGUAGE_BY_ALPHA2.get(alpha2)
            if alpha3:
                self._row["language"] = alpha3
                self._row["alpha2"] = "el"
        if self._in_row and tag == "button":
            onclick = attrs_dict.get("onclick") or ""
            match = _DOWNLOAD_ID_RE.search(onclick)
            if match:
                self._row["subtitle_id"] = match.group(1)
        if self._in_row and tag == "div" and "userNameBox" in (attrs_dict.get("class") or "").split():
            self._in_user = True
            self._user_text = []

    def handle_data(self, data):
        if self._in_title:
            self._title_text.append(data)
        if self._in_cell:
            self._cell_text.append(data)
        if self._in_user:
            self._user_text.append(data)

    def handle_endtag(self, tag):
        if tag == "title" and self._in_title:
            self._in_title = False
            self.title = _clean_page_title(_clean_text(" ".join(self._title_text)))
        if tag == "td" and self._in_cell:
            self._in_cell = False
            self._cells.append(_clean_text(" ".join(self._cell_text)))
        if tag == "div" and self._in_user:
            self._in_user = False
            user = _clean_text(" ".join(self._user_text))
            if user:
                self._row["uploader"] = user
        if tag == "tr" and self._in_row:
            self._in_row = False
            row = self._finalize_row()
            if row:
                self.rows.append(row)
        if self._in_table and tag == "table":
            self._table_depth -= 1
            if self._table_depth <= 0:
                self._in_table = False
                self._table_depth = 0

    def _finalize_row(self):
        if "subtitle_id" not in self._row or "language" not in self._row:
            return None
        cells = [cell for cell in self._cells if cell]
        release_index = _release_cell_index(cells)
        if release_index is None:
            return None
        downloads = _int_from_text(cells[release_index - 1])
        release = cells[release_index]
        if not release:
            return None
        row = dict(self._row)
        row.update(
            {
                "release": release,
                "downloads": downloads,
                "uploader": row.get("uploader", ""),
            }
        )
        return row


class _InputParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.inputs = {}

    def handle_starttag(self, tag, attrs):
        if tag != "input":
            return
        attrs_dict = dict(attrs)
        name = attrs_dict.get("name")
        if name:
            self.inputs[name] = attrs_dict.get("value", "")


def parse_subtitle_page(body, page_url):
    parser = _SubtitlePageParser(page_url)
    parser.feed(_decode(body))
    return {
        "sec_code": parser.sec_code,
        "title": parser.title,
        "rows": parser.rows,
    }


def parse_episode_links(body):
    episodes = {}
    text = _decode(body)
    for match in _EPISODE_LINK_RE.finditer(text):
        label = _strip_tags(match.group("text"))
        season_episode = _SEASON_EPISODE_RE.search(label)
        if not season_episode:
            continue
        href = html.unescape(match.group("href"))
        imdb_match = _IMDB_RE.search(href)
        url = urllib.parse.urljoin(BASE_URL + "/", href)
        episodes[(int(season_episode.group(1)), int(season_episode.group(2)))] = {
            "url": url,
            "label": label,
            "episode_imdb_id": imdb_match.group(1) if imdb_match else "",
        }
    return episodes


def extract_download_form(body):
    parser = _InputParser()
    parser.feed(_decode(body))
    required = ("langcode", "uid", "output", "dll")
    if not all(parser.inputs.get(key) for key in required):
        raise ValueError("greeksubs download gate did not expose required form fields")
    return {key: parser.inputs[key] for key in required}


class GreekSubsProvider:
    def __init__(self):
        cookie_jar = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))

    def _http_request(self, url, data=None, timeout=HTTP_TIMEOUT_SECONDS, referer=None):
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        if referer:
            headers["Referer"] = referer
        if data is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        request = urllib.request.Request(url, data=data, headers=headers)
        for attempt in range(1, HTTP_MAX_ATTEMPTS + 1):
            try:
                with self._opener.open(request, timeout=timeout) as response:
                    return response.read()
            except urllib.error.HTTPError as error:
                if error.code not in RETRYABLE_STATUS or attempt >= HTTP_MAX_ATTEMPTS:
                    raise
                _retry_sleep(attempt, error.headers.get("Retry-After") if error.code == 429 else None)
            except (urllib.error.URLError, socket.timeout, TimeoutError):
                if attempt >= HTTP_MAX_ATTEMPTS:
                    raise
                _retry_sleep(attempt, None)
        raise RuntimeError("unreachable greeksubs retry state")

    def search(self, video, languages, config):
        language = _requested_greek(languages)
        if language is None:
            return []
        video = video or {}
        kind = video.get("kind")
        imdb_id = _video_imdb_id(video)
        if kind not in {"movie", "episode"} or not imdb_id:
            return []
        config = config or {}
        start_url = f"{BASE_URL}/en/view/{imdb_id}"
        _sleep(config)
        start_body = self._http_request(start_url)
        page_url = start_url
        page_body = start_body
        if kind == "episode":
            episode_page_url = _episode_page_url(start_body, video)
            if episode_page_url:
                _sleep(config)
                page_url = episode_page_url
                page_body = self._http_request(page_url, referer=start_url)
            elif video.get("imdb_id") and _normalize_imdb_id(video.get("imdb_id")) != imdb_id:
                _sleep(config)
                page_url = f"{BASE_URL}/en/view/{_normalize_imdb_id(video.get('imdb_id'))}"
                page_body = self._http_request(page_url, referer=start_url)
        page = parse_subtitle_page(page_body, page_url)
        if not page["sec_code"]:
            return []
        results = []
        seen = set()
        for row in page["rows"]:
            if row["language"] != "ell":
                continue
            key = row["subtitle_id"]
            if key in seen:
                continue
            seen.add(key)
            results.append(_result(video, page, row, language))
            if len(results) >= MAX_RESULTS:
                break
        return sorted(results, key=lambda item: item.get("score", 0), reverse=True)

    def download(self, provider_payload, language, config):
        del language, config
        payload = provider_payload or {}
        download_url = payload.get("download_url")
        if not download_url:
            raise ValueError("greeksubs download requires download_url")
        page_url = payload.get("page_url") or BASE_URL + "/"
        gate_body = self._http_request(download_url, referer=page_url)
        try:
            form = extract_download_form(gate_body)
        except ValueError as initial_error:
            download_url = self._refresh_download_url(payload, page_url, download_url)
            if not download_url:
                raise initial_error
            gate_body = self._http_request(download_url, referer=page_url)
            try:
                form = extract_download_form(gate_body)
            except ValueError as error:
                raise ValueError(
                    "greeksubs download gate remained invalid after token refresh"
                ) from error
        post_body = urllib.parse.urlencode(form).encode("ascii")
        subtitle_body = self._http_request(download_url, data=post_body, referer=download_url)
        normalized = _normalize_line_endings(subtitle_body)
        if not normalized:
            raise ValueError("greeksubs download returned an empty subtitle")
        subtitle_format = _subtitle_format(form.get("output") or payload.get("filename") or "")
        return _content_payload(normalized, subtitle_format)

    def _refresh_download_url(self, payload, page_url, stale_download_url):
        subtitle_id = str(payload.get("subtitle_id") or "").strip()
        if not subtitle_id:
            raise ValueError("greeksubs expired download requires a subtitle id for refresh")

        parsed_page = urllib.parse.urlsplit(str(page_url))
        base = urllib.parse.urlsplit(BASE_URL)
        if (
            parsed_page.scheme != base.scheme
            or parsed_page.netloc != base.netloc
            or not parsed_page.path.startswith("/en/view/")
        ):
            raise ValueError("greeksubs expired download requires its GreekSubs detail page")

        expected_prefix = f"{BASE_URL}/dll/{urllib.parse.quote(subtitle_id, safe='')}/0/"
        if not str(stale_download_url).startswith(expected_prefix):
            raise ValueError("greeksubs download URL does not match the subtitle id")

        detail_body = self._http_request(page_url)
        page = parse_subtitle_page(detail_body, page_url)
        if not page.get("sec_code") or not any(
            row.get("subtitle_id") == subtitle_id for row in page.get("rows", [])
        ):
            raise ValueError("greeksubs subtitle id was not found on its detail page")

        return f"{expected_prefix}{urllib.parse.quote(page['sec_code'], safe='')}"


def _result(video, page, row, language):
    release = row["release"]
    filename = f"greeksubs.{_slug(release)}.{language['alpha2']}.srt"
    download_url = f"{BASE_URL}/dll/{row['subtitle_id']}/0/{page['sec_code']}"
    matches = _derive_matches(video, page.get("title") or "", release)
    return {
        "provider": PROVIDER_ID,
        "id": f"greeksubs-{row['subtitle_id']}",
        "language": dict(language),
        "release_info": release,
        "filename": filename,
        "matches": matches,
        "score": _score(matches, row),
        "score_without_hash": _score(matches, row),
        "score_out_of": 100,
        "hash_verifiable": False,
        "hearing_impaired_verifiable": False,
        "hearing_impaired": False,
        "page_link": row["page_url"],
        "download_count": row["downloads"],
        "display": {
            "source": "greeksubs.net",
            "title": page.get("title") or "",
            "uploader": row.get("uploader") or "",
            "downloads": row["downloads"],
        },
        "provider_payload": {
            "provider": PROVIDER_ID,
            "schema": 1,
            "download_url": download_url,
            "page_url": row["page_url"],
            "subtitle_id": row["subtitle_id"],
            "filename": filename,
        },
    }


def _requested_greek(languages):
    for language in languages or []:
        alpha3 = _alpha3_for(language)
        alpha2 = _alpha2_for(language)
        if alpha3 == "ell" or alpha2 in {"el", "gr"}:
            return dict(GREEK_LANGUAGE)
    return None


def _video_imdb_id(video):
    if video.get("kind") == "episode":
        return _normalize_imdb_id(video.get("series_imdb_id") or video.get("imdb_id"))
    return _normalize_imdb_id(video.get("imdb_id"))


def _normalize_imdb_id(value):
    text = str(value or "").strip().lower()
    if not text:
        return ""
    if text.startswith("tt") and text[2:].isdigit():
        return text
    if text.isdigit():
        return f"tt{text}"
    return ""


def _episode_page_url(body, video):
    try:
        season = int(video.get("season"))
        episode = int(video.get("episode"))
    except (TypeError, ValueError):
        return ""
    return (parse_episode_links(body).get((season, episode)) or {}).get("url", "")


def _derive_matches(video, page_title, release):
    video = video or {}
    haystack = f"{page_title} {release}"
    tokens = set(_tokens(haystack))
    matches = []
    if video.get("kind") == "movie":
        title_tokens = _tokens(video.get("title"))
        if title_tokens and all(token in tokens for token in title_tokens):
            matches.append("title")
        year = video.get("year")
        if year and str(year) in tokens:
            matches.append("year")
        _append_release_match(matches, video, release)
    elif video.get("kind") == "episode":
        series_tokens = _tokens(video.get("series"))
        if series_tokens and all(token in tokens for token in series_tokens):
            matches.append("series")
        season_episode = _season_episode_markers(haystack)
        try:
            expected = (int(video.get("season")), int(video.get("episode")))
        except (TypeError, ValueError):
            expected = None
        if expected and expected in season_episode:
            matches.extend(["season", "episode"])
        elif expected and any(item[0] == expected[0] for item in season_episode):
            matches.append("season")
        _append_release_match(matches, video, release)
    return matches


def _append_release_match(matches, video, release):
    source = _clean_text(video.get("source") or "").lower()
    resolution = _clean_text(video.get("resolution") or "").lower()
    release_lower = _clean_text(release).lower()
    if source and source in release_lower:
        matches.append("source")
    if resolution and resolution in release_lower:
        matches.append("resolution")


def _season_episode_markers(text):
    markers = []
    lowered = text.lower()
    for match in re.finditer(r"(?<!\d)s0*(\d{1,2})[ ._-]*e0*(\d{1,3})(?!\d)", lowered):
        markers.append((int(match.group(1)), int(match.group(2))))
    for match in re.finditer(r"(?<!\d)0*(\d{1,2})x0*(\d{1,3})(?!\d)", lowered):
        markers.append((int(match.group(1)), int(match.group(2))))
    for match in _SEASON_EPISODE_RE.finditer(lowered):
        markers.append((int(match.group(1)), int(match.group(2))))
    return markers


def _score(matches, row):
    score = 60 + min(int(row.get("downloads") or 0) // 1000, 10)
    weights = {
        "title": 15,
        "year": 15,
        "series": 15,
        "season": 10,
        "episode": 15,
        "source": 5,
        "resolution": 5,
    }
    return min(100, score + sum(weights.get(match, 0) for match in matches))


def _content_payload(content, subtitle_format):
    return {
        "content_b64": base64.b64encode(content).decode("ascii"),
        "content_sha256": hashlib.sha256(content).hexdigest(),
        "content_type": _content_type(subtitle_format),
        "format": subtitle_format,
        "encoding": _encoding_for(content),
        "empty": False,
    }


def _subtitle_format(filename):
    suffix = os.path.splitext(filename)[1].lstrip(".").lower()
    return suffix if suffix in SUBTITLE_FORMATS else "srt"


def _content_type(subtitle_format):
    return {
        "srt": "application/x-subrip",
        "ass": "text/x-ssa",
        "ssa": "text/x-ssa",
        "sub": "text/plain",
        "vtt": "text/vtt",
    }.get(subtitle_format, "text/plain")


def _encoding_for(content):
    try:
        content.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        return "latin-1"


def _normalize_line_endings(content):
    return (content or b"").replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _sleep(config):
    delay = int((config or {}).get("request_delay_ms") or 0)
    if delay > 0:
        time.sleep(delay / 1000)


def _retry_sleep(attempt, retry_after):
    delay = RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1))
    after = _retry_after_seconds(retry_after)
    if after is not None:
        delay = max(delay, after)
    time.sleep(min(delay, RETRY_BACKOFF_CAP_SECONDS))


def _retry_after_seconds(value):
    if not value:
        return None
    try:
        return max(0.0, float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def _decode(body):
    if isinstance(body, str):
        return body
    return (body or b"").decode("utf-8", "ignore")


def _clean_page_title(value):
    value = re.sub(r"^subtitle\s+for\s+", "", value or "", flags=re.I)
    value = re.sub(r"\s*\|\s*greek\s+subs\s*$", "", value, flags=re.I)
    return _clean_text(value)


def _strip_tags(value):
    return _clean_text(_TAG_RE.sub(" ", html.unescape(value or "")))


def _clean_text(value):
    return _WS_RE.sub(" ", html.unescape(str(value or ""))).strip()


def _int_from_text(value):
    digits = re.sub(r"\D+", "", value or "")
    return int(digits) if digits else 0


def _release_cell_index(cells):
    start = 1
    for index, cell in enumerate(cells):
        if cell.lower() == "download":
            start = index + 1
            break
    for index in range(start, len(cells) - 1):
        if re.fullmatch(r"[\d,\s]+", cells[index] or ""):
            return index + 1
    return None


def _tokens(value):
    return [token for token in _NON_WORD_RE.sub(" ", str(value or "").lower()).split() if token]


def _slug(value):
    slug = re.sub(r"[^A-Za-z0-9]+", ".", value or "").strip(".")
    return slug or "subtitle"


def _alpha3_for(language):
    if isinstance(language, dict):
        return str(language.get("alpha3") or "").lower()
    return str(language or "").lower()


def _alpha2_for(language):
    if isinstance(language, dict):
        return str(language.get("alpha2") or "").lower()
    return ""
