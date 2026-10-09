"""SubSynchro provider for the Bazarr+ Provider Hub catalog."""

import base64 as _base64
import hashlib as _hashlib
import html
import io
import json
import os
import re
import time
import unicodedata
import urllib.parse
import urllib.request
import zipfile

PROVIDER_ID = "subsynchro"
BASE_URL = "https://www.subsynchro.com"
SEARCH_URL = f"{BASE_URL}/tous-les-films.html"
LEGACY_AJAX_URL = f"{BASE_URL}/include/ajax/subMarin.php"
HTTP_TIMEOUT_SECONDS = 15
MAX_FILM_PAGES = 3
MAX_RELEASE_PAGES = 8
SUPPORTED_LANGUAGES = {"fra": "fr"}
ALPHA2_TO_ALPHA3 = {value: key for key, value in SUPPORTED_LANGUAGES.items()}
SUBTITLE_EXTENSIONS = (".srt", ".ass", ".ssa", ".vtt", ".sub")
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 BazarrProviderHub"
)

_ANCHOR_RE = re.compile(rb"<a\b(?P<attrs>[^>]*)>(?P<label>.*?)</a>", re.I | re.S)
_ANCHOR_OPEN_RE = re.compile(rb"<a\b(?P<attrs>[^>]*)>", re.I | re.S)
_ARTICLE_RE = re.compile(rb"<article\b(?P<attrs>[^>]*)>(?P<body>.*?)</article>", re.I | re.S)
_FILM_HEADER_RE = re.compile(
    rb"<h1\b[^>]*>\s*<strong>(?P<title>.*?)</strong>.*?(?P<year>\d{4})",
    re.I | re.S,
)
_FORMAT_RE = re.compile(rb"Format\s*:\s*(?P<format>[^<\r\n]+)", re.I)
_DOWNLOADS_RE = re.compile(rb"Telechargement\s*:\s*(?P<body>.*?)</li>", re.I | re.S)
_GROUP_RE = re.compile(rb"<strong\b[^>]*class=['\"][^'\"]*\bgroup_name\b[^'\"]*['\"][^>]*>(?P<name>.*?)</strong>", re.I | re.S)
_INPUT_RELEASE_RE = re.compile(
    rb"<input\b(?P<attrs>[^>]*class=['\"][^'\"]*\brelease\b[^'\"]*['\"][^>]*)>",
    re.I | re.S,
)
_NON_ALNUM_RE = re.compile(r"[\W_]+", re.UNICODE)
_TAG_RE = re.compile(rb"<[^>]+>")
_TR_RE = re.compile(rb"<tr\b(?P<attrs>[^>]*)>(?P<body>.*?)</tr>", re.I | re.S)
_WS_BYTES_RE = re.compile(rb"\s+")
_WS_RE = re.compile(r"\s+")


def parse_film_releases(body):
    movie_title, movie_year = _film_identity(body)
    rows = []
    for match in _TR_RE.finditer(body or b""):
        attrs = match.group("attrs")
        release_dom_id = _attr(attrs, "id")
        if not release_dom_id.startswith("release_"):
            continue
        release_id = release_dom_id.split("_", 1)[1]
        classes = _attr(attrs, "class")
        file_count = _file_count(classes, match.group("body"))
        if file_count <= 0:
            continue
        release_href, release_info = _release_link(match.group("body"))
        if not release_href or not release_info:
            continue
        rows.append(
            {
                "release_id": release_id,
                "movie_title": movie_title,
                "movie_year": movie_year,
                "release_info": release_info,
                "release_group": _release_group(match.group("body")),
                "release_url": _absolute_url(release_href),
                "format": _attr(attrs, "data-format"),
                "file_count": file_count,
            }
        )
    return rows


def parse_release_files(body, release=None):
    release = dict(release or {})
    if not release.get("release_info"):
        release["release_info"] = _release_value(body)
    rows = []
    for match in _ARTICLE_RE.finditer(body or b""):
        attrs = match.group("attrs")
        file_dom_id = _attr(attrs, "id")
        if not file_dom_id.startswith("fichier_"):
            continue
        article = match.group("body")
        filename = _first_h4_link_label(article)
        download_url = _download_url(article)
        if not filename or not download_url:
            continue
        row = dict(release)
        row.update(
            {
                "file_id": file_dom_id.split("_", 1)[1],
                "filename": filename,
                "download_url": _absolute_url(download_url),
                "format": _format_from_article(article) or _subtitle_extension(filename) or "srt",
                "downloads": _downloads_from_article(article),
            }
        )
        rows.append(row)
    return rows


def parse_search_results(body):
    rows = []
    seen = set()
    for attrs, label in _iter_anchors(body):
        href = _attr(attrs, "href")
        if not _looks_like_film_href(href):
            continue
        title = _strip_tags(label)
        if not title:
            continue
        url = _absolute_url(href)
        if url in seen:
            continue
        seen.add(url)
        rows.append(
            {
                "title": title,
                "year": _year_from_film_href(href),
                "url": url,
            }
        )
    return rows


def parse_legacy_ajax_results(body, video=None):
    try:
        parsed = json.loads(_decode(body or b"{}"))
    except (TypeError, ValueError):
        return []
    if parsed.get("status") != 200:
        return []
    rows = []
    for item in parsed.get("data", []):
        if not isinstance(item, dict):
            continue
        filename = _coerce_text(item.get("filename")) or ""
        release_info = _coerce_text(item.get("release")) or filename
        download_url = _coerce_text(item.get("telechargement"))
        if not download_url:
            continue
        title_text = " ".join(
            _coerce_text(item.get(key)) or "" for key in ("titre", "titre_original")
        )
        matches = []
        wanted_title = _coerce_text((video or {}).get("title"))
        wanted_year = _safe_int((video or {}).get("year"))
        if wanted_title and _normalize(wanted_title) in _normalize(title_text):
            matches.append("title")
            if wanted_year is not None:
                matches.append("year")
        rows.append(
            {
                "file_id": _stable_id(download_url),
                "movie_title": wanted_title or _coerce_text(item.get("titre")) or "",
                "movie_year": _safe_int((video or {}).get("year")),
                "release_id": "",
                "release_info": release_info,
                "release_group": "",
                "release_url": download_url,
                "filename": filename,
                "download_url": download_url,
                "format": _subtitle_extension(filename) or "srt",
                "downloads": 0,
                "matches": matches,
            }
        )
    return rows


def derive_matches(video, candidate_title, candidate_year=None):
    if not video:
        return []
    matches = []
    candidate_tokens = set(_tokens(candidate_title))
    title_tokens = _tokens(video.get("title"))
    if title_tokens and all(token in candidate_tokens for token in title_tokens):
        matches.append("title")
    wanted_year = _safe_int(video.get("year"))
    if wanted_year is not None and (
        candidate_year == wanted_year or str(wanted_year) in candidate_tokens
    ):
        matches.append("year")
    release_group = _coerce_text(video.get("release_group"))
    if release_group and _normalize(release_group) in _normalize(candidate_title):
        matches.append("release_group")
    return matches


class SubsynchroProvider:
    def _http_request(self, url, data=None, timeout=HTTP_TIMEOUT_SECONDS, referer=None):
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.7,en;q=0.6",
        }
        if data is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        if referer:
            headers["Referer"] = referer
        request = urllib.request.Request(url, data=data, headers=headers)
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()

    def search(self, video, languages, config):
        if (video or {}).get("kind") != "movie":
            return []
        requested = {_alpha3_for_language(language) for language in languages or []}
        if "fra" not in requested:
            return []
        title = _coerce_text((video or {}).get("title"))
        if not title:
            return []
        config = dict(config or {})
        try:
            results = self._search_current_site(video, title, config)
        except Exception:
            results = []
        if not results:
            results = self._search_legacy_ajax(video, title, config)
        return sorted(results, key=lambda item: item["score"], reverse=True)

    def _search_current_site(self, video, title, config):
        _sleep(config)
        post_body = urllib.parse.urlencode({"q": title}).encode("ascii")
        body = self._http_request(SEARCH_URL, data=post_body)
        results = self._results_from_film_body(video, body, SEARCH_URL, config)
        if results:
            return results
        for page in _rank_film_pages(video, parse_search_results(body))[:MAX_FILM_PAGES]:
            _sleep(config)
            film_body = self._http_request(page["url"], referer=SEARCH_URL)
            results.extend(self._results_from_film_body(video, film_body, page["url"], config))
            if results:
                return results
        return results

    def _results_from_film_body(self, video, body, referer, config):
        results = []
        seen = set()
        wanted_year = _safe_int((video or {}).get("year"))
        _film_title, film_year = _film_identity(body)
        if wanted_year is not None and film_year is not None and film_year != wanted_year:
            return results
        releases = _rank_releases(video, parse_film_releases(body))
        for release in releases[:MAX_RELEASE_PAGES]:
            _sleep(config)
            release_body = self._http_request(release["release_url"], referer=referer)
            for item in parse_release_files(release_body, release):
                key = (item.get("file_id"), item.get("download_url"))
                if key in seen:
                    continue
                seen.add(key)
                results.append(self._result(video, item))
        return results

    def _search_legacy_ajax(self, video, title, config):
        del config
        params = {"title": title}
        year = (video or {}).get("year")
        if year:
            params["year"] = year
        url = f"{LEGACY_AJAX_URL}?{urllib.parse.urlencode(params)}"
        try:
            rows = parse_legacy_ajax_results(self._http_request(url), video)
        except Exception:
            rows = []
        return [self._result(video, row) for row in rows]

    def _result(self, video, item):
        filename = item.get("filename") or _download_filename(item.get("download_url")) or "subsynchro.srt"
        release_info = item.get("release_info") or filename
        candidate_title = " ".join(
            part
            for part in [
                item.get("movie_title"),
                str(item.get("movie_year") or ""),
                release_info,
                filename,
            ]
            if part
        )
        matches = list(dict.fromkeys(item.get("matches") or derive_matches(video, candidate_title, item.get("movie_year"))))
        score = 95 if {"title", "year"} <= set(matches) else 80 if "title" in matches else 60
        file_id = item.get("file_id") or _stable_id(item.get("download_url") or filename)
        return {
            "provider": PROVIDER_ID,
            "id": f"subsynchro-{file_id}",
            "language": {
                "alpha3": "fra",
                "alpha2": "fr",
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
            "page_link": item.get("release_url") or item.get("download_url"),
            "display": {
                "source": "subsynchro",
                "title": item.get("movie_title"),
                "release": release_info,
                "format": item.get("format"),
                "downloads": item.get("downloads"),
            },
            "provider_payload": {
                "provider": PROVIDER_ID,
                "schema": 1,
                "file_id": file_id,
                "release_id": item.get("release_id") or "",
                "url": item.get("download_url"),
                "page_url": item.get("release_url") or item.get("download_url"),
                "filename": filename,
                "language": "fra",
            },
        }

    def download(self, provider_payload, language, config):
        del language, config
        payload = provider_payload or {}
        url = payload.get("url")
        if not url:
            raise ValueError("subsynchro download requires url")
        body = self._http_request(url, referer=payload.get("page_url"))
        return extract_download(body, payload)


def extract_download(body, payload=None):
    payload = payload or {}
    if not body:
        return _content_payload(b"", "srt", empty=True)
    stream = io.BytesIO(body)
    if zipfile.is_zipfile(stream):
        stream.seek(0)
        with zipfile.ZipFile(stream) as archive:
            member = select_subtitle_file(archive.namelist())
        # Host-side extraction (Provider Hub v1.1+): we still list the zip cheaply with
        # stdlib zipfile to pick the member, but hand the raw archive bytes back to the
        # host, which extracts that member and detects encoding via Subtitle.normalize().
        return {
            "archive_b64": _base64.b64encode(body).decode("ascii"),
            "archive_sha256": _hashlib.sha256(body).hexdigest(),
            "member": member,
        }
    subtitle_format = _subtitle_extension(payload.get("filename", ""))
    if not subtitle_format or _looks_like_html(body):
        raise ValueError("subsynchro download did not return a supported subtitle archive")
    return _content_payload(_normalize_line_endings(body), subtitle_format)


def select_subtitle_file(names):
    for name in names:
        basename = os.path.basename(name)
        if basename.startswith("."):
            continue
        if _subtitle_extension(name):
            return name
    raise ValueError("subsynchro archive contains no supported subtitle files")


def _film_identity(body):
    match = _FILM_HEADER_RE.search(body or b"")
    if not match:
        return "", None
    return _strip_tags(match.group("title")), _safe_int(_decode(match.group("year")))


def _release_link(row_body):
    for match in _ANCHOR_OPEN_RE.finditer(row_body or b""):
        attrs = match.group("attrs")
        href = _attr(attrs, "href")
        title = _attr(attrs, "title")
        if href.endswith(".html") and "/" in href and title:
            return href, html.unescape(title).strip()
    return "", ""


def _release_group(row_body):
    match = _GROUP_RE.search(row_body or b"")
    return _strip_tags(match.group("name")) if match else ""


def _release_value(body):
    for match in _INPUT_RELEASE_RE.finditer(body or b""):
        value = _attr(match.group("attrs"), "value")
        if value:
            return value
    return ""


def _first_h4_link_label(article):
    h4_match = re.search(rb"<h4\b[^>]*>(?P<body>.*?)</h4>", article or b"", re.I | re.S)
    if not h4_match:
        return ""
    for _attrs, label in _iter_anchors(h4_match.group("body")):
        text = _strip_tags(label)
        if text:
            return text
    return ""


def _download_url(article):
    for attrs, _label in _iter_anchors(article):
        classes = _attr(attrs, "class")
        href = _attr(attrs, "href")
        if "telecharger" in classes and href:
            return href
    return ""


def _format_from_article(article):
    match = _FORMAT_RE.search(article or b"")
    return (_decode(match.group("format")).strip().lower() if match else "").lstrip(".")


def _downloads_from_article(article):
    match = _DOWNLOADS_RE.search(article or b"")
    return _int_from_text(_strip_tags(match.group("body"))) if match else 0


def _file_count(classes, row_body):
    match = re.search(r"\bfichier_(\d+)\b", classes or "")
    if match:
        return _safe_int(match.group(1)) or 0
    col_match = re.search(rb"<td\b[^>]*class=['\"][^'\"]*\bcol6\b[^'\"]*['\"][^>]*>(?P<body>.*?)</td>", row_body or b"", re.I | re.S)
    return _int_from_text(_strip_tags(col_match.group("body"))) if col_match else 0


def _iter_anchors(body):
    for match in _ANCHOR_RE.finditer(body or b""):
        yield match.group("attrs"), match.group("label")


def _attr(attrs, name):
    if not attrs:
        return ""
    pattern = re.compile(rb"\b" + re.escape(name.encode("ascii")) + rb"\s*=\s*(['\"])(?P<value>.*?)\1", re.I | re.S)
    match = pattern.search(attrs)
    return html.unescape(_decode(match.group("value"))).strip() if match else ""


def _rank_film_pages(video, pages):
    ranked = []
    wanted_tokens = _tokens((video or {}).get("title"))
    wanted_norm = _normalize((video or {}).get("title"))
    wanted_year = _safe_int((video or {}).get("year"))
    for index, page in enumerate(pages):
        title_norm = _normalize(page.get("title"))
        title_tokens = set(_tokens(page.get("title")))
        page_year = _safe_int(page.get("year"))
        if wanted_year is not None and page_year is not None and page_year != wanted_year:
            continue
        score = 0
        if wanted_tokens and all(token in title_tokens for token in wanted_tokens):
            score = 80
        if wanted_norm and title_norm == wanted_norm:
            score = 110
        if wanted_year is not None and page_year == wanted_year:
            score += 20
        if score:
            ranked.append((page, score, index))
    ranked.sort(key=lambda item: (-item[1], item[2]))
    return [page for page, _score, _index in ranked]


def _rank_releases(video, releases):
    ranked = []
    for index, release in enumerate(releases):
        matches = derive_matches(
            video,
            f"{release.get('movie_title', '')} {release.get('movie_year', '')} {release.get('release_info', '')}",
            release.get("movie_year"),
        )
        score = len(matches)
        ranked.append((release, score, index))
    ranked.sort(key=lambda item: (-item[1], item[2]))
    return [release for release, _score, _index in ranked]


def _alpha3_for_language(language):
    if not isinstance(language, dict):
        return None
    alpha3 = (language.get("alpha3") or "").lower()
    if alpha3:
        return alpha3
    return ALPHA2_TO_ALPHA3.get((language.get("alpha2") or "").lower())


def _looks_like_film_href(href):
    return re.match(r"^\d{4}/\d+-[^/]+\.html$", href or "") is not None


def _year_from_film_href(href):
    match = re.match(r"^(\d{4})/", href or "")
    return int(match.group(1)) if match else None


def _absolute_url(url):
    if not url:
        return ""
    return urllib.parse.urljoin(f"{BASE_URL}/", html.unescape(url))


def _download_filename(url):
    path = urllib.parse.urlparse(url or "").path
    return os.path.basename(path)


def _stable_id(value):
    return _hashlib.sha1(_coerce_text(value).encode("utf-8")).hexdigest()[:16]


def _subtitle_extension(name):
    lowered = (name or "").lower()
    for extension in SUBTITLE_EXTENSIONS:
        if lowered.endswith(extension):
            return extension[1:]
    return None


def _content_payload(content, subtitle_format, empty=False):
    # Do not guess an encoding. The host runs chardet via Subtitle.normalize(); a worker
    # guess (especially latin-1, which never fails to decode) only reintroduces mojibake.
    if empty:
        return {
            "content_b64": "",
            "content_sha256": "",
            "content_type": _content_type(subtitle_format),
            "format": subtitle_format,
            "empty": True,
        }
    return {
        "content_b64": _base64.b64encode(content).decode("ascii"),
        "content_sha256": _hashlib.sha256(content).hexdigest(),
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


def _looks_like_html(body):
    sample = (body or b"").lstrip()[:512].lower()
    return sample.startswith((b"<!doctype html", b"<html")) or b"<title" in sample


def _sleep(config):
    delay_ms = (config or {}).get("request_delay_ms", 0) or 0
    if delay_ms > 0:
        time.sleep(min(delay_ms, 5000) / 1000.0)


def _int_from_text(text):
    match = re.search(r"\d+", text or "")
    return int(match.group(0)) if match else 0


def _safe_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _strip_tags(value):
    stripped = _TAG_RE.sub(b"", value or b"")
    stripped = _WS_BYTES_RE.sub(b" ", stripped).strip()
    return _WS_RE.sub(" ", html.unescape(_decode(stripped))).strip()


def _tokens(value):
    return [token for token in _normalize(_coerce_text(value)).split(" ") if token]


def _normalize(value):
    if value is None:
        return ""
    decomposed = unicodedata.normalize("NFKD", str(value))
    folded = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return _NON_ALNUM_RE.sub(" ", folded.lower()).strip()


def _coerce_text(value):
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return " ".join(str(item) for item in value if item not in (None, ""))
    return str(value)


def _decode(value):
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return value.decode("utf-8", errors="replace")
